import av
import torch
import numpy as np
from transformers import TimesformerForVideoClassification, AutoImageProcessor
from PIL import Image
import matplotlib.pyplot as plt
from tqdm import tqdm
import random
import os 

class AttentionExtractor:
    def __init__(self, model_name, device='cpu'):
        self.model = TimesformerForVideoClassification.from_pretrained(model_name)
        self.model.to(device)
        self.device = device
        self.image_processor = AutoImageProcessor.from_pretrained(model_name, use_fast=True)
        # self.image_processor = AutoImageProcessor.from_pretrained(model_name)

    def print_model_structure(self):
        print(self.model)

    def extract_attention(self, video_path, num_frames=8):
        container = av.open(video_path)
        frames = [frame.to_image() for frame in container.decode(video=0)]
        sampled_frames = [frames[i] for i in np.linspace(0, len(frames) - 1, num_frames, dtype=int)]
        
        inputs = self.image_processor(sampled_frames, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self.model(**inputs, output_attentions=True)
        
        # Extract attention from the last layer
        last_layer_attention = outputs.attentions[-1]
        
        # Extract spatial attention (average over heads)
        spatial_attention = last_layer_attention.mean(1)
        
        # Extract temporal attention (use the attention of the CLS token to all frames)
        temporal_attention = spatial_attention[:, 0, 1:num_frames+1]
        
        return spatial_attention, temporal_attention, sampled_frames, outputs.logits

    def visualize_attention(self, spatial_attention, temporal_attention, frames, save_path, prediction, true_label):
        num_frames = len(frames)
        
        # Visualize spatial attention
        for i, frame in enumerate(frames):
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 10))
            
            # Original frame
            ax1.imshow(frame)
            ax1.axis('off')
            ax1.set_title(f"Original Frame {i+1}")
            
            # Spatial attention heatmap
            att_map = spatial_attention[0, i+1, 1:].reshape(int(np.sqrt(spatial_attention.shape[2]-1)), -1).cpu().numpy()
            att_resized = Image.fromarray(att_map).resize(frame.size, Image.BICUBIC)
            att_resized = np.array(att_resized)
            
            # Normalize attention values
            att_norm = (att_resized - att_resized.min()) / (att_resized.max() - att_resized.min())
            
            # Convert frame to numpy array if it's not already
            frame_array = np.array(frame)
            
            # Create a heatmap overlay
            heatmap = plt.cm.hot(att_norm)
            heatmap = heatmap[..., :3]  # Remove alpha channel
            
            # Blend original frame with heatmap
            blend = 0.7 * frame_array / 255 + 0.3 * heatmap
            blend = np.clip(blend, 0, 1)
            
            # Display blended image
            im = ax2.imshow(blend)
            ax2.axis('off')
            ax2.set_title(f"Spatial Attention Heatmap Frame {i+1}")
            
            plt.colorbar(im, ax=ax2, label='Attention Intensity')
            plt.tight_layout()
            plt.savefig(f"{save_path}_frame_{i+1}_spatial_attention.png", dpi=300, bbox_inches='tight')
            plt.close()
        
        # Visualize temporal attention
        temporal_att = temporal_attention[0].cpu().numpy()
        plt.figure(figsize=(15, 5))
        plt.imshow(temporal_att.reshape(1, -1), aspect='auto', interpolation='nearest')
        plt.colorbar(label='Attention')
        plt.title(f"Temporal Attention (Pred: {prediction}, True: {true_label})")
        plt.xlabel("Frame")
        plt.ylabel("CLS Token Attention")
        plt.savefig(f"{save_path}_temporal_attention.png", dpi=300, bbox_inches='tight')
        plt.close()

        # Print attention shapes for debugging
        print(f"Spatial attention shape: {spatial_attention.shape}")
        print(f"Temporal attention shape: {temporal_attention.shape}")

def load_labels(label_file):
    labels = {}
    with open(label_file, 'r') as f:
        for line in f:
            video_name, label = line.strip().split()
            labels[video_name] = int(label)
    return labels

def process_videos(config):
    extractor = AttentionExtractor(config['model_name'])
    
    if config['print_model']:
        extractor.print_model_structure()
    
    labels = load_labels(config['label_file'])
    
    all_video_files = [f for f in os.listdir(config['video_directory']) if f.endswith('.mp4')]
    selected_videos = random.sample(all_video_files, min(config['num_videos'], len(all_video_files)))
    
    for video_file in tqdm(selected_videos, desc="Processing videos"):
        video_path = os.path.join(config['video_directory'], video_file)
        spatial_attention, temporal_attention, frames, logits = extractor.extract_attention(video_path)
        
        prediction = torch.argmax(logits, dim=1).item()
        true_label = labels.get(video_file, labels.get(video_file.split('.')[0], "Unknown"))
        
        save_path = os.path.join(config['output_directory'], video_file.split('.')[0])
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        extractor.visualize_attention(spatial_attention, temporal_attention, frames, save_path, prediction, true_label)
        
        print(f"Processed {video_file}: Prediction = {prediction}, True Label = {true_label}")
        print(f"Results saved in: {save_path}")

if __name__ == "__main__":
    config = {
        'model_name': 'facebook/timesformer-base-finetuned-k400',
        'video_directory': 'dataprocess/videos',
        'output_directory': 'datasets/videos',
        'label_file': 'archive/kinetics400_val_list_videos.txt',
        'num_videos': 10,
        'print_model': True  # 设置为 True 以打印模型结构
    }
    
    process_videos(config)