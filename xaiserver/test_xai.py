from attention_extractor import AttentionExtractor  
import torch
import os

# Initialize model
staa_model = AttentionExtractor("facebook/timesformer-base-finetuned-k400", device="cpu")

# Test Video Path
video_path = "dataprocess/videos/test_video.mp4"  # Replace with actual video file

if not os.path.exists(video_path):
    print(f"❌ ERROR: Video file not found at {video_path}")
else:
    print(f"✅ Found video file at {video_path}")

    try:
        # Run STAA attention extraction
        spatial_attention, temporal_attention, frames, logits = staa_model.extract_attention(video_path, num_frames=8)
        prediction_idx = torch.argmax(logits, dim=1).item()
        prediction = staa_model.model.config.id2label[prediction_idx]

        print(f"✅ Prediction: {prediction}")
    except Exception as e:
        print(f"❌ ERROR in AttentionExtractor: {e}")
