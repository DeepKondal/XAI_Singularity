import aiofiles
import os
import DataProcess
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException
import shutil
import os
import zipfile
from typing import List
from fastapi import BackgroundTasks


import importlib.util
import sys

module_name = 'functionaltool.cloudstorage'
module_file_path = '/home/z/Music/devnew_xaiservice/XAIport/functionaltool/cloudstorage.py'

spec = importlib.util.spec_from_file_location(module_name, module_file_path)
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)

up_cloud = module.up_cloud
down_cloud = module.down_cloud


from functionaltool.cloudstorage import up_cloud, down_cloud

app = FastAPI()

data_processor = DataProcess.DataProcess(base_storage_address="datasets")



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

    # 在成功解压缩文件后，上传整个数据集文件夹到云存储
    cloud_upload_path = os.path.join("datasets", dataset_id)
    up_cloud(dataset_dir, cloud_upload_path)

    return {"message": "Dataset uploaded to local storage and Azure Blob Storage successfully"}

    # Clean up
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


@app.post("/apply-perturbation/{dataset_id}/{perturbation_func_name}/{severity}")
async def apply_perturbation(background_tasks: BackgroundTasks, dataset_id: str, perturbation_func_name: str, severity: int):
    # 确认扰动函数存在于 DataProcess 类中且可调用
    if not hasattr(DataProcess.DataProcess, perturbation_func_name) or not callable(getattr(DataProcess.DataProcess, perturbation_func_name)):
        raise HTTPException(status_code=400, detail="Unsupported or invalid perturbation function.")

    # 获取对应的扰动函数
    perturbation_func = getattr(DataProcess.DataProcess, perturbation_func_name)

    # 异步执行扰动应用
    background_tasks.add_task(data_processor.apply_image_perturbation, dataset_id, perturbation_func, severity)

    return {"message": "Perturbation process started."}



if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
