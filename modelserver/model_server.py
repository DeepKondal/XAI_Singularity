from fastapi import FastAPI, BackgroundTasks, HTTPException ,File
from pydantic import BaseModel
import Model_ResNet
import os
import torch
# from attention_extractor import AttentionExtractor  
from fastapi import UploadFile
import import_ipynb
import matplotlib.pyplot as plt
import json
from generateTemporalSpatial import process_video, create_sample_frames_visualization, AttentionExtractor

app = FastAPI()
# Initialize STAA
attention_extractor = AttentionExtractor(model_name="facebook/timesformer-base-finetuned-k400", device="cuda" if torch.cuda.is_available() else "cpu")
# Output directory
OUTPUT_DIR = "video_results"
os.makedirs(OUTPUT_DIR, exist_ok=True)


class DatasetPaths(BaseModel):
    dataset_id: str  # Add dataset_id field to the request body

def run_model_async(dataset_id, model_func):
    # Use dataset_id as needed in your model_func
    dataset_paths = f"dataprocess/datasets/{dataset_id}"
    model_func(dataset_paths)


@app.post("/resnet/{dataset_id}/{perturbation_func_name}/{severity}")
async def run_model1_background(dataset_id: str, perturbation_func_name: str, severity: int, background_tasks: BackgroundTasks):
    local_original_dataset_path = f"/home/z/Music/devnew_xaiservice/XAIport/datasets/{dataset_id}"
    local_perturbed_dataset_path = f"/home/z/Music/devnew_xaiservice/XAIport/datasets/{dataset_id}_{perturbation_func_name}_{severity}"

    # 构建 dataset_paths 列表
    dataset_paths = [local_original_dataset_path, local_perturbed_dataset_path]

    # 异步运行模型
    background_tasks.add_task(Model_ResNet.model_run, dataset_paths)

    return {
        "message": f"ResNet run for dataset {dataset_id} with perturbation {perturbation_func_name} and severity {severity} has started, results will be uploaded to Blob storage after computation."
    }


# video explanation
extractor = AttentionExtractor(
    model_name="facebook/timesformer-base-finetuned-k400",
    device="cuda" if torch.cuda.is_available() else "cpu",
)


# ORIGINAL_VIDEO_DIR = "dataprocess/videos"
# ADVERSARIAL_VIDEO_DIR = "dataprocess/FGSM"
# OUTPUT_DIR = "video_results"
# os.makedirs(OUTPUT_DIR, exist_ok=True)



# CLEAN_SUBDIR = "clean"
# FGSM_SUBDIR = "adversarial"
# os.makedirs(os.path.join(OUTPUT_DIR, "original"), exist_ok=True)
# os.makedirs(os.path.join(OUTPUT_DIR, "adversarial"), exist_ok=True)

# @app.post("/facebook/timesformer-base-finetuned-k400/{dataset_id}")
# async def video_explain(dataset_id: str):

#     # Process clean videos
#     clean_video_dir = "dataprocess/videos"
#     fgsm_video_dir = "dataprocess/FGSM"

#     results = []

#     # Process both clean and FGSM videos
#     for video_type, video_dir, result_dir in [
#         ("clean", clean_video_dir, CLEAN_SUBDIR),
#         ("adversarial", fgsm_video_dir, FGSM_SUBDIR)
#     ]:
#         video_files = [f for f in os.listdir(video_dir) if f.endswith(".mp4")]

#         for video_file in video_files:
#             video_path = os.path.join(video_dir, video_file)
#             try:
#                 # Extract attention and logits
#                 spatial_attention, temporal_attention, frames, logits = extractor.extract_attention(video_path)
#                 prediction_idx = torch.argmax(logits, dim=1).item()
#                 prediction = extractor.model.config.id2label[prediction_idx]

#                 # Create a unique directory for storing the results of this video type
#                 video_result_dir = os.path.join(OUTPUT_DIR, result_dir, os.path.splitext(video_file)[0])
#                 os.makedirs(video_result_dir, exist_ok=True)

#                 # Save visualizations
#                 extractor.visualize_attention(
#                     spatial_attention, temporal_attention, frames, video_result_dir, prediction, video_type
#                 )

#                 results.append({
#                     "video_file": video_file,
#                     "video_type": video_type,
#                     "prediction": prediction,
#                     "results_dir": video_result_dir
#                 })

#             except Exception as e:
#                 results.append({
#                     "video_file": video_file,
#                     "video_type": video_type,
#                     "error": str(e)
#                 })

#     return {"results": results}
# CLEAN_VIDEO_DIR = "dataprocess/test_video"
# ADVERSARIAL_VIDEO_DIR = "dataprocess/FGSM"
# OUTPUT_DIR = "output"
# os.makedirs(OUTPUT_DIR, exist_ok=True)

# @app.post("/process-video/{video_name}")
# async def process_and_visualize_video(video_name: str):
#     try:
#         # Paths for clean and adversarial videos
#         clean_video_path = os.path.join(CLEAN_VIDEO_DIR, video_name)
#         adversarial_video_path = os.path.join(ADVERSARIAL_VIDEO_DIR, video_name)

#         # Check if clean video exists
#         if not os.path.exists(clean_video_path):
#             raise HTTPException(status_code=404, detail=f"Video '{video_name}' not found in {CLEAN_VIDEO_DIR}.")

#         # Initialize response dictionary
#         response = {"video_name": video_name, "message": "Processing completed"}

#         # Process CLEAN Video
#         clean_output_dir = os.path.join(OUTPUT_DIR, "clean", video_name)
#         os.makedirs(clean_output_dir, exist_ok=True)
        
#         clean_predicted_label, clean_frames_dir, clean_json_path, clean_heatmap_video_path = process_video(
#             clean_video_path, clean_output_dir, extractor=attention_extractor
#         )

#         clean_visualization_path = create_sample_frames_visualization(
#             video_name=os.path.splitext(video_name)[0],
#             results_dir=clean_output_dir
#         )

#         response["clean_video"] = {
#             "predicted_label": clean_predicted_label,
#             "frames_directory": clean_frames_dir,
#             "attention_json_path": clean_json_path,
#             "heatmap_video_path": clean_heatmap_video_path,
#             "visualization_path": clean_visualization_path
#         }

#         # Process ADVERSARIAL Video if it exists
#         if os.path.exists(adversarial_video_path):
#             adversarial_output_dir = os.path.join(OUTPUT_DIR, "adversarial", video_name)
#             os.makedirs(adversarial_output_dir, exist_ok=True)

#             adv_predicted_label, adv_frames_dir, adv_json_path, adv_heatmap_video_path = process_video(
#                 adversarial_video_path, adversarial_output_dir, extractor=attention_extractor
#             )

#             adv_visualization_path = create_sample_frames_visualization(
#                 video_name=os.path.splitext(video_name)[0] ,
#                 results_dir=adversarial_output_dir
#             )

#             response["adversarial_video"] = {
#                 "predicted_label": adv_predicted_label,
#                 "frames_directory": adv_frames_dir,
#                 "attention_json_path": adv_json_path,
#                 "heatmap_video_path": adv_heatmap_video_path,
#                 "visualization_path": adv_visualization_path
#             }
#         else:
#             response["adversarial_video"] = {"message": "No adversarial version found."}

#         return response

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

CLEAN_VIDEO_DIR = "dataprocess/test_video"
ADVERSARIAL_VIDEO_DIR = "dataprocess/FGSM"
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.post("/process-videos")
async def process_and_visualize_all_videos():
    try:
        response = {"message": "Processing all videos", "clean_videos": [], "adversarial_videos": []}

        # Process Clean Videos
        if os.path.exists(CLEAN_VIDEO_DIR):
            clean_videos = [f for f in os.listdir(CLEAN_VIDEO_DIR) if f.endswith(".mp4")]
            for video_name in clean_videos:
                clean_video_path = os.path.join(CLEAN_VIDEO_DIR, video_name)
                clean_output_dir = os.path.join(OUTPUT_DIR, "clean", video_name)
                os.makedirs(clean_output_dir, exist_ok=True)

                clean_predicted_label, clean_frames_dir, clean_json_path, clean_heatmap_video_path = process_video(
                    clean_video_path, clean_output_dir, extractor=attention_extractor
                )

                clean_visualization_path = create_sample_frames_visualization(
                    video_name=os.path.splitext(video_name)[0],
                    results_dir=clean_output_dir
                )

                response["clean_videos"].append({
                    "video_name": video_name,
                    "predicted_label": clean_predicted_label,
                    "frames_directory": clean_frames_dir,
                    "attention_json_path": clean_json_path,
                    "heatmap_video_path": clean_heatmap_video_path,
                    "visualization_path": clean_visualization_path
                })

        # Process Adversarial Videos
        if os.path.exists(ADVERSARIAL_VIDEO_DIR):
            adversarial_videos = [f for f in os.listdir(ADVERSARIAL_VIDEO_DIR) if f.endswith(".mp4")]
            for video_name in adversarial_videos:
                adversarial_video_path = os.path.join(ADVERSARIAL_VIDEO_DIR, video_name)
                adversarial_output_dir = os.path.join(OUTPUT_DIR, "adversarial", video_name)
                os.makedirs(adversarial_output_dir, exist_ok=True)

                adv_predicted_label, adv_frames_dir, adv_json_path, adv_heatmap_video_path = process_video(
                    adversarial_video_path, adversarial_output_dir, extractor=attention_extractor
                )

                adv_visualization_path = create_sample_frames_visualization(
                    video_name=os.path.splitext(video_name)[0],
                    results_dir=adversarial_output_dir
                )

                response["adversarial_videos"].append({
                    "video_name": video_name,
                    "predicted_label": adv_predicted_label,
                    "frames_directory": adv_frames_dir,
                    "attention_json_path": adv_json_path,
                    "heatmap_video_path": adv_heatmap_video_path,
                    "visualization_path": adv_visualization_path
                })

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)