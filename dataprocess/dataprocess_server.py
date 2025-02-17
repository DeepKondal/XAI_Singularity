import aiofiles
import os
from DataProcess import DataProcess
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
import shutil
import os
import zipfile
from typing import List
from fastapi import BackgroundTasks
import pandas as pd
import av
import numpy as np
from adversarial import evaluate_and_generate_adversarial
app = FastAPI()

data_processor = DataProcess(base_storage_address="datasets")

# Load Kinetics-400 metadata into DataProcess
data_processor.load_metadata(
    labels_csv="dataprocess/kinetics_400_labels.csv",
    video_list_txt="dataprocess/kinetics400_val_list_videos.txt"
)

@app.get("/")
async def root():
    return {"message": "Server is running"}
@app.post("/upload-dataset/{dataset_id}")
async def upload_dataset(dataset_id: str, zip_file: UploadFile = File(...)):
    # Ensure temp directory exists
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)

    # Save ZIP file
    temp_file = f"{temp_dir}/{zip_file.filename}"
    with open(temp_file, "wb") as buffer:
        shutil.copyfileobj(zip_file.file, buffer)

    # Prepare dataset directory
    dataset_dir = f"datasets/{dataset_id}"
    os.makedirs(dataset_dir, exist_ok=True)

    # Extract ZIP file
    with zipfile.ZipFile(temp_file, 'r') as zip_ref:
        for member in zip_ref.infolist():
            # Skip directories
            if member.is_dir():
                continue

            # Construct target file path without top-level directory
            target_path = os.path.join(dataset_dir, '/'.join(member.filename.split('/')[1:]))

            # Create any intermediate directories
            os.makedirs(os.path.dirname(target_path), exist_ok=True)

            # Extract file to the target path
            with zip_ref.open(member, 'r') as source, open(target_path, 'wb') as target:
                shutil.copyfileobj(source, target)

    # cloud_upload_path = os.path.join("datasets", dataset_id)
    # up_cloud(dataset_dir, cloud_upload_path)

    # return {"message": "Dataset uploaded to local storage and Azure Blob Storage successfully"}

    os.remove(temp_file)

    return {"message": "Dataset uploaded and extracted successfully"}



@app.get("/get-dataset-info/{dataset_id}")
async def get_dataset_info(dataset_id: str):
    try:
        info = data_processor.get_dataset_info(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return info




@app.delete("/delete-dataset/{dataset_id}")
async def delete_dataset(dataset_id: str):
    try:
        data_processor.delete_dataset(dataset_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "Dataset deleted successfully"}

@app.get("/download-dataset/{dataset_id}")
async def download_dataset(dataset_id: str, download_path: str):
    try:
        data_processor.download_dataset(dataset_id, download_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "Dataset downloaded successfully"}


# @app.post("/apply-perturbation/{dataset_id}/{perturbation_func_name}/{severity}")
# async def apply_perturbation(background_tasks: BackgroundTasks, dataset_id: str, perturbation_func_name: str, severity: int):
#     # 确认扰动函数存在于 DataProcess 类中且可调用
#     if not hasattr(DataProcess.DataProcess, perturbation_func_name) or not callable(getattr(DataProcess.DataProcess, perturbation_func_name)):
#         raise HTTPException(status_code=400, detail="Unsupported or invalid perturbation function.")

#     # 获取对应的扰动函数
#     perturbation_func = getattr(DataProcess.DataProcess, perturbation_func_name)

#     # 异步执行扰动应用
#     background_tasks.add_task(data_processor.apply_image_perturbation, dataset_id, perturbation_func, severity)

#     return {"message": "Perturbation process started."}


@app.post("/apply-perturbation/{dataset_id}/{perturbation_func_name}/{severity}")
async def apply_perturbation(background_tasks: BackgroundTasks, dataset_id: str, perturbation_func_name: str, severity: int):
    """
    Apply perturbation or adversarial attack on videos within the specified dataset.
    If 'adversarial_attack' is chosen, the FGSM-based attack will be applied.
    """
    dataset_path = "dataprocess/test_video"

    if perturbation_func_name == "adversarial_attack":
        # Apply adversarial attack using the provided FGSM implementation
        config = {
            'model_name': 'facebook/timesformer-base-finetuned-k400',
            'video_directory': dataset_path,  # Input directory
            'label_file': 'dataprocess/kinetics400_val_list_videos.txt',
            'epsilon': severity / 10.0  # Map severity to epsilon value (0.1, 0.2, etc.)
        }

        background_tasks.add_task(evaluate_and_generate_adversarial, config)
        return {"message": "Adversarial attack process started."}
    else:
        # Apply general image perturbations using DataProcess class
        if not hasattr(DataProcess, perturbation_func_name) or not callable(getattr(DataProcess, perturbation_func_name)):
            raise HTTPException(status_code=400, detail="Unsupported or invalid perturbation function.")

        perturbation_func = getattr(DataProcess, perturbation_func_name)
        background_tasks.add_task(data_processor.apply_image_perturbation, dataset_id, perturbation_func, severity)

        return {"message": "Perturbation process started."}
# Load Kinetics-400 metadata
@app.post("/process-kinetics-dataset")
async def process_kinetics_dataset(data: dict):
    """
    Process a directory of Kinetics-400 videos.
    """
    video_dir = data.get("video_dir")
    num_frames = data.get("num_frames", 8)

    if not video_dir or not os.path.exists(video_dir):
        raise HTTPException(status_code=400, detail="Invalid or missing 'video_dir'")

    try:
        results = []
        for video_file in os.listdir(video_dir):
            if video_file.endswith(".mp4"):
                video_path = os.path.join(video_dir, video_file)
                # Process the video using metadata loaded in DataProcess
                result = data_processor.process_kinetics_video(video_path, num_frames=num_frames)
                results.append(result)

        return {"message": "Kinetics-400 dataset processed successfully", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)