import torch
import av
import numpy as np
from tqdm import tqdm
import os
import torch.nn.functional as F
from transformers import TimesformerForVideoClassification, AutoImageProcessor
from sklearn.metrics import precision_recall_fscore_support, accuracy_score

def load_video(video_path, num_frames=32):
    frames = []
    container = av.open(video_path)
    
    for frame in container.decode(video=0):
        frames.append(frame.to_rgb().to_ndarray())
        if len(frames) == num_frames:
            break
    
    while len(frames) < num_frames:
        frames.append(frames[-1])
    
    return np.stack(frames)
 

def load_labels(label_file):
    labels = {}
    with open(label_file, 'r') as f:
        for line in f:
            video_name, label = line.strip().split()
            labels[video_name.split('.')[0]] = int(label)
    return labels

def fgsm_attack(model, data, epsilon, labels, device):

    data.pixel_values.requires_grad = True
    
    outputs = model(**data)
    loss = F.cross_entropy(outputs.logits, labels)
    model.zero_grad()
    loss.backward()
    

    data_grad = data.pixel_values.grad.data.sign()
    

    perturbed_data = data.copy()
    perturbed_data.pixel_values = data.pixel_values + epsilon * data_grad
    

    perturbed_data.pixel_values = torch.clamp(perturbed_data.pixel_values, 0, 1)
    
    return perturbed_data

def save_video_frames(frames, output_path, fps=30):
    """
    将帧保存为视频文件
    """
    container = av.open(output_path, mode='w')
    stream = container.add_stream('h264', rate=fps)
    stream.width = frames.shape[3]
    stream.height = frames.shape[2]
    
    for frame in frames:
        frame = frame.permute(1, 2, 0).numpy()
        frame = (frame * 255).astype(np.uint8)
        frame = av.VideoFrame.from_ndarray(frame, format='rgb24')
        packet = stream.encode(frame)
        container.mux(packet)
    
    # Flush the stream
    packet = stream.encode(None)
    container.mux(packet)
    container.close()

def evaluate_and_generate_adversarial(config):

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = TimesformerForVideoClassification.from_pretrained(config['model_name']).to(device)
    processor = AutoImageProcessor.from_pretrained(config['model_name'])
    model.eval()

    video_labels = load_labels(config['label_file'])
    
    adv_video_dir = os.path.join(os.path.dirname(config['video_directory']), 'FGSM')
    os.makedirs(adv_video_dir, exist_ok=True)

    clean_preds = []
    adv_preds = []
    all_labels = []
    video_files = [f for f in os.listdir(config['video_directory']) if f.endswith('.mp4')]
    
    for video_file in tqdm(video_files, desc="Processing videos"):
        video_name = video_file.split('.')[0]
        

        if video_name not in video_labels:
            continue
            
        true_label = video_labels[video_name]
        video_path = os.path.join(config['video_directory'], video_file)
        
        try:

            frames = load_video(video_path)
            inputs = processor(list(frames), return_tensors="pt").to(device)
            labels = torch.tensor([true_label]).to(device)
            

            with torch.no_grad():
                clean_outputs = model(**inputs)
                clean_pred = clean_outputs.logits.argmax(-1).cpu().numpy()[0]
            
    
            perturbed_inputs = fgsm_attack(model, inputs, config['epsilon'], labels, device)
            

            with torch.no_grad():
                adv_outputs = model(**perturbed_inputs)
                adv_pred = adv_outputs.logits.argmax(-1).cpu().numpy()[0]
            

            adv_frames = perturbed_inputs.pixel_values[0].cpu().detach()
            adv_video_path = os.path.join(adv_video_dir, video_file)
            save_video_frames(adv_frames, adv_video_path)
            

            clean_preds.append(clean_pred)
            adv_preds.append(adv_pred)
            all_labels.append(true_label)
            
        except Exception as e:
            print(f"Error processing {video_file}: {str(e)}")
            continue
    

    clean_precision, clean_recall, clean_f1, _ = precision_recall_fscore_support(
        all_labels, clean_preds, average='weighted'
    )
    clean_accuracy = accuracy_score(all_labels, clean_preds)
    

    adv_precision, adv_recall, adv_f1, _ = precision_recall_fscore_support(
        all_labels, adv_preds, average='weighted'
    )
    adv_accuracy = accuracy_score(all_labels, adv_preds)
    

    results = {
        'clean': {
            'accuracy': float(clean_accuracy),
            'precision': float(clean_precision),
            'recall': float(clean_recall),
            'f1': float(clean_f1)
        },
        'adversarial': {
            'accuracy': float(adv_accuracy),
            'precision': float(adv_precision),
            'recall': float(adv_recall),
            'f1': float(adv_f1)
        }
    }
    
    print("\nClean Performance Metrics:")
    print(f"Accuracy: {clean_accuracy:.4f}")
    print(f"Precision: {clean_precision:.4f}")
    print(f"Recall: {clean_recall:.4f}")
    print(f"F1 Score: {clean_f1:.4f}")
    
    print("\nAdversarial Performance Metrics:")
    print(f"Accuracy: {adv_accuracy:.4f}")
    print(f"Precision: {adv_precision:.4f}")
    print(f"Recall: {adv_recall:.4f}")
    print(f"F1 Score: {adv_f1:.4f}")
    
    return results

if __name__ == "__main__":
    config = {
        'model_name': 'facebook/timesformer-base-finetuned-k400',
        'video_directory': 'dataprocess/test_video', # input
        'label_file': 'dataprocess/kinetics400_val_list_videos.txt',# config['label_file']
        'epsilon': 0.1  
    }
    
    results = evaluate_and_generate_adversarial(config)