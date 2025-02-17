from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List
import logging
import cam_resnet
from functionaltool.cloudstorage import up_cloud, down_cloud  # Assuming these functions are defined elsewhere

app = FastAPI()

class XAIRequest(BaseModel):
    dataset_id: str
    algorithms: List[str]

async def download_dataset(dataset_id: str) -> str:
    """Download the dataset and return the local dataset path."""
    try:
        local_dataset_path = f"datasets/{dataset_id}"
        down_cloud(f"datasets/{dataset_id}", local_dataset_path)
        return local_dataset_path
    except Exception as e:
        logging.error(f"Error downloading dataset {dataset_id}: {e}")
        raise

async def run_xai_process(dataset_id: str, algorithm_names: List[str]):
    try:
        local_dataset_path = await download_dataset(dataset_id)
        dataset_dirs = [local_dataset_path]

        # 将算法名称转换为算法类
        selected_algorithms = [cam_resnet.CAM_ALGORITHMS_MAPPING[name] for name in algorithm_names]

        cam_resnet.xai_run(dataset_dirs, selected_algorithms)
        # 处理上传结果和其他后续处理
    except Exception as e:
        logging.error(f"Error in run_xai_process: {e}")
        raise


@app.post("/cam_xai")
async def run_xai(request: XAIRequest, background_tasks: BackgroundTasks):
    try:
        background_tasks.add_task(run_xai_process, request.dataset_id, request.algorithms)
        return {"message": "XAI processing for dataset has started successfully."}
    except Exception as e:
        logging.error(f"Error in run_xai endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
