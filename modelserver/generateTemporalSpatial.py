import os
import av
import torch
import numpy as np
from transformers import TimesformerForVideoClassification, AutoImageProcessor
import matplotlib.pyplot as plt
from tqdm import tqdm
import cv2
import json
import logging
from scipy.signal import savgol_filter, find_peaks
import matplotlib.gridspec as gridspec

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class AttentionExtractor:
    def __init__(self, model_name, device='cuda' if torch.cuda.is_available() else 'cpu'):
        self.model = TimesformerForVideoClassification.from_pretrained(model_name)
        self.model.to(device)
        self.device = device
        self.image_processor = AutoImageProcessor.from_pretrained(model_name)

    def extract_attention(self, frames):
        inputs = self.image_processor(frames, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs, output_attentions=True)
        last_layer_attention = outputs.attentions[-1]
        spatial_attention = last_layer_attention.mean(1)
        return spatial_attention.cpu().numpy(), outputs.logits.cpu().numpy()

    def apply_attention_heatmap(self, frame, attention):
        att_map = attention[1:].reshape(int(np.sqrt(attention.shape[0]-1)), -1)
        att_resized = cv2.resize(att_map, (frame.shape[1], frame.shape[0]))
        att_norm = (att_resized - att_resized.min()) / (att_resized.max() - att_resized.min())
        heatmap = cv2.applyColorMap(np.uint8(255 * att_norm), cv2.COLORMAP_JET)
        blend = cv2.addWeighted(frame, 0.7, heatmap, 0.3, 0)
        return blend

def multi_scale_attention(extractor, frames):
    scales = [0.5, 0.75, 1.0, 1.25, 1.5]
    attentions = []
    for scale in scales:
        scaled_frames = [cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR) for frame in frames]
        attention, _ = extractor.extract_attention(scaled_frames)
        attentions.append(attention)
    return np.mean(attentions, axis=0)

def exponential_smoothing(data, alpha=0.3):
    smoothed = [data[0]]
    for i in range(1, len(data)):
        smoothed.append(alpha * data[i] + (1 - alpha) * smoothed[-1])
    return smoothed

def process_video(video_path, output_dir, extractor, sampling_rate=2, temporal_smoothing_window=5):
    os.makedirs(output_dir, exist_ok=True)
    frames_dir = os.path.join(output_dir, 'frames')
    os.makedirs(frames_dir, exist_ok=True)

    container = av.open(video_path)
    video_stream = container.streams.video[0]
    fps = video_stream.average_rate
    total_frames = video_stream.frames
    
    # 创建输出视频文件
    output_path = os.path.join(output_dir, f"{os.path.basename(video_path).split('.')[0]}_heatmap.mp4")
    output = av.open(output_path, mode='w')
    output_stream = output.add_stream('h264', rate=fps)
    output_stream.width = video_stream.width
    output_stream.height = video_stream.height
    output_stream.pix_fmt = 'yuv420p'

    frames = []
    attention_data = []
    frame_count = 0
    attention_buffer = []
    all_logits = []

    for frame in tqdm(container.decode(video=0), desc="Processing frames", total=total_frames):
        frame_rgb = frame.to_rgb().to_ndarray()
        frames.append(frame_rgb)
        
        if len(frames) == 8:
            spatial_attention = multi_scale_attention(extractor, frames)
            logits = extractor.extract_attention(frames)[1]
            all_logits.append(logits)
            
            for i in range(8):
                attention = spatial_attention[0, i+1]
                attention_buffer.append(attention)
                
                if len(attention_buffer) >= temporal_smoothing_window:
                    smoothed_attention = np.mean(attention_buffer[-temporal_smoothing_window:], axis=0)
                    heatmap_frame = extractor.apply_attention_heatmap(frames[i], smoothed_attention)
                    
                    if frame_count % sampling_rate == 0:
                        frame_filename = f"{os.path.basename(video_path).split('.')[0]}_frame_{frame_count+1}_spatial_attention.png"
                        cv2.imwrite(os.path.join(frames_dir, frame_filename), cv2.cvtColor(heatmap_frame, cv2.COLOR_RGB2BGR))
                        
                        attention_data.append({
                            "frame_index": frame_count,
                            "max_attention": float(smoothed_attention[1:].max()),
                            "min_attention": float(smoothed_attention[1:].min()),
                            "mean_attention": float(smoothed_attention[1:].mean())
                        })
                    
                    # 将每一帧都写入输出视频
                    out_frame = av.VideoFrame.from_ndarray(heatmap_frame, format='rgb24')
                    packet = output_stream.encode(out_frame)
                    output.mux(packet)
                
                frame_count += 1
            
            frames = frames[7:]

    # Process remaining frames
    if frames:
        padding = [frames[-1]] * (8 - len(frames))
        spatial_attention = multi_scale_attention(extractor, frames + padding)
        logits = extractor.extract_attention(frames + padding)[1]
        all_logits.append(logits)
        
        for i in range(len(frames)):
            attention = spatial_attention[0, i+1]
            attention_buffer.append(attention)
            
            smoothed_attention = np.mean(attention_buffer[-temporal_smoothing_window:], axis=0)
            heatmap_frame = extractor.apply_attention_heatmap(frames[i], smoothed_attention)
            
            if frame_count % sampling_rate == 0:
                frame_filename = f"{os.path.basename(video_path).split('.')[0]}_frame_{frame_count+1}_spatial_attention.png"
                cv2.imwrite(os.path.join(frames_dir, frame_filename), cv2.cvtColor(heatmap_frame, cv2.COLOR_RGB2BGR))
                
                attention_data.append({
                    "frame_index": frame_count,
                    "max_attention": float(smoothed_attention[1:].max()),
                    "min_attention": float(smoothed_attention[1:].min()),
                    "mean_attention": float(smoothed_attention[1:].mean())
                })
            
            # 将每一帧都写入输出视频
            out_frame = av.VideoFrame.from_ndarray(heatmap_frame, format='rgb24')
            packet = output_stream.encode(out_frame)
            output.mux(packet)
            
            frame_count += 1

    # Flush encoder
    packet = output_stream.encode(None)
    output.mux(packet)
    output.close()

    # Apply exponential smoothing to attention data
    smoothed_attention = exponential_smoothing([frame['mean_attention'] for frame in attention_data])
    for i, att in enumerate(smoothed_attention):
        attention_data[i]['mean_attention'] = att

    # Save attention data
    with open(os.path.join(output_dir, f"{os.path.basename(video_path).split('.')[0]}_rs.json"), 'w') as f:
        json.dump(attention_data, f)

    overall_logits = np.mean(all_logits, axis=0)
    predicted_label = int(np.argmax(overall_logits))

    return predicted_label, frames_dir, os.path.join(output_dir, f"{os.path.basename(video_path).split('.')[0]}_rs.json"), output_path

def create_sample_frames_visualization(video_name, num_segments=8, results_dir='attention_results'):
    try:
        # Load data
        json_path = os.path.join(results_dir, f"{video_name}_rs.json")
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        
        with open(json_path, 'r') as f:
            attention_data = json.load(f)
        
        # Extract temporal attention
        temporal_attention = np.array([frame['mean_attention'] for frame in attention_data])
        frame_indices = np.array([frame['frame_index'] for frame in attention_data])
        
        # Apply Savitzky-Golay filter for additional smoothing
        window_length = min(len(temporal_attention) // 2 * 2 + 1, 21)  # Must be odd and not exceed data length
        temporal_attention_smoothed = savgol_filter(temporal_attention, window_length, 3)
        
        # Normalize temporal attention
        temporal_attention_smoothed = (temporal_attention_smoothed - temporal_attention_smoothed.min()) / (temporal_attention_smoothed.max() - temporal_attention_smoothed.min())
        
        # Select key frames based on local maxima
        peaks, _ = find_peaks(temporal_attention_smoothed, distance=len(temporal_attention_smoothed)//num_segments)
        if len(peaks) < num_segments:
            additional_frames = np.linspace(0, len(temporal_attention_smoothed)-1, num_segments-len(peaks), dtype=int)
            key_frame_indices = np.sort(np.concatenate([peaks, additional_frames]))
        else:
            key_frame_indices = peaks[:num_segments]
        
        # Create figure
        fig = plt.figure(figsize=(16, 9))  # 16:9 aspect ratio
        gs = gridspec.GridSpec(2, 1, height_ratios=[1, 2])
        
        # Plot temporal saliency
        ax1 = plt.subplot(gs[0])
        ax1.plot(frame_indices, temporal_attention_smoothed, color='blue', alpha=0.7, linewidth=2)
        ax1.scatter(frame_indices[key_frame_indices], temporal_attention_smoothed[key_frame_indices], color='red', s=100, zorder=5)
        for idx in key_frame_indices:
            ax1.axvline(x=frame_indices[idx], color='gray', linestyle='--', alpha=0.5)
        ax1.set_xlabel("Frame Number", fontsize=18)
        ax1.set_ylabel("Temporal Saliency", fontsize=18)
        ax1.set_xlim(frame_indices[0], frame_indices[-1])
        ax1.set_ylim(0, 1)
        ax1.tick_params(axis='both', which='major', labelsize=14)
        ax1.set_title(f"Temporal Saliency and Key Frames - {video_name}", fontsize=20)
        
        # Display key frames
        ax2 = plt.subplot(gs[1])
        ax2.axis('off')
        frames_loaded = 0
        for i, idx in enumerate(key_frame_indices):
            frame_number = frame_indices[idx]
            frame_path = os.path.join(results_dir, 'frames', f"{video_name}_frame_{frame_number}_spatial_attention.png")
            
            if os.path.exists(frame_path):
                frame = cv2.imread(frame_path)
                if frame is not None:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    ax_sub = ax2.inset_axes([i/num_segments, 0, 1/num_segments - 0.01, 1], transform=ax2.transAxes)
                    ax_sub.imshow(frame)
                    ax_sub.axis('off')
                    ax_sub.set_title(f"Frame {frame_number}", fontsize=14)
                    frames_loaded += 1
                else:
                    print(f"Failed to load frame: {frame_path}")
            else:
                print(f"Frame not found: {frame_path}")
        
        if frames_loaded == 0:
            print(f"No frames were loaded for {video_name}. Check the 'frames' directory and file names.")
        else:
            print(f"Successfully loaded {frames_loaded} frames for {video_name}.")
        
        plt.tight_layout()
        output_path = os.path.join(results_dir, f"{video_name}_sample_frames.png")
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"Sample frames visualization saved to: {output_path}")
        return output_path
    except Exception as e:
        print(f"Error in create_sample_frames_visualization for video {video_name}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise

def load_video_labels(label_file):
    video_labels = {}
    with open(label_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 2:
                video_name, label = parts
                video_labels[video_name.split('.')[0]] = int(label)  # Remove .mp4 extension
            else:
                logging.warning(f"Skipping invalid line: {line.strip()}")
    logging.info(f"Loaded {len(video_labels)} video labels")
    logging.info(f"Unique labels in the dataset: {set(video_labels.values())}")
    return video_labels

def get_videos_by_label(video_labels, target_label):
    matching_videos = [video for video, label in video_labels.items() if label == target_label]
    logging.info(f"Found {len(matching_videos)} videos for label {target_label}")
    return matching_videos

def process_videos(config):
    extractor = AttentionExtractor(config['model_name'])
    
    video_labels = load_video_labels(config['label_file'])
    
    target_videos = get_videos_by_label(video_labels, config['target_label'])
    
    if not target_videos:
        logging.warning(f"No videos found for label {config['target_label']}")
        return

    for video_name in tqdm(target_videos, desc="Processing videos"):
        video_path = os.path.join(config['video_directory'], video_name + '.mp4')
        
        if not os.path.exists(video_path):
            logging.warning(f"Video file not found: {video_path}")
            continue
        
        video_output_dir = os.path.join(config['output_directory'], video_name)
        predicted_label, frames_dir, json_path, heatmap_video_path = process_video(video_path, video_output_dir, extractor)
        
        create_sample_frames_visualization(video_name, results_dir=video_output_dir)
        
        print(f"Processed {video_name}")
        print(f"Predicted Label: {predicted_label}")

if __name__ == "__main__":
    config = {
        'model_name': 'facebook/timesformer-base-finetuned-k400',
        'video_directory': 'dataprocess/test_video',
        'output_directory': 'video_results',
        'label_file': 'dataprocess/kinetics400_val_list_videos.txt',
        'target_label': int(input("Enter the target label number: "))
    }
    
    try:
        process_videos(config)
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        import traceback
        traceback.print_exc()