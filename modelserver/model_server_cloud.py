from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import Model_ResNet
from functionaltool.cloudstorage import up_cloud, down_cloud
import os

app = FastAPI()

class DatasetPaths(BaseModel):
    dataset_id: str  # Add dataset_id field to the request body

def run_model_async(dataset_id, model_func):
    # Use dataset_id as needed in your model_func
    dataset_paths = f"dataprocess/datasets/{dataset_id}"
    model_func(dataset_paths)


@app.post("/resnet/{dataset_id}/{perturbation_func_name}/{severity}")
async def run_model1_background(dataset_id: str, perturbation_func_name: str, severity: int, background_tasks: BackgroundTasks):
    # 定义本地数据集路径
    local_original_dataset_path = f"datasets/{dataset_id}"
    local_perturbed_dataset_path = f"datasets/{dataset_id}_{perturbation_func_name}_{severity}"

    # 异步下载原始数据集和受扰动数据集
    background_tasks.add_task(down_cloud, f"datasets/{dataset_id}", local_original_dataset_path)
    background_tasks.add_task(down_cloud, f"datasets/{dataset_id}/{perturbation_func_name}/{severity}", local_perturbed_dataset_path)

    # 构建 dataset_paths 列表
    dataset_paths = [local_original_dataset_path, local_perturbed_dataset_path]

    # 异步运行模型
    background_tasks.add_task(Model_ResNet.model_run, dataset_paths)

    return {
        "message": f"ResNet run for dataset {dataset_id} with perturbation {perturbation_func_name} and severity {severity} has started, results will be uploaded to Blob storage after computation."
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
