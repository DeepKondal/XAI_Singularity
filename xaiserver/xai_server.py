from pydantic import BaseModel
from typing import List
import logging
import cam_resnet
from fastapi import FastAPI, BackgroundTasks, HTTPException,Request
import aiohttp
import os
from attention_extractor import AttentionExtractor  
import torch 
app = FastAPI()
staa_model = AttentionExtractor("facebook/timesformer-base-finetuned-k400", device="cpu")
class XAIRequest(BaseModel):
    dataset_id: str
    algorithms: List[str]

async def async_http_post(url, json_data=None, files=None):
    """
    Make asynchronous POST requests to a given URL with JSON data or files.
    """
    async with aiohttp.ClientSession() as session:
        if json_data:
            response = await session.post(url, json=json_data)
        elif files:
            response = await session.post(url, data=files)
        else:
            response = await session.post(url)

        if response.status != 200:
            logging.error(f"Error in POST request to {url}: {response.status} - {await response.text()}")
            raise HTTPException(status_code=response.status, detail=await response.text())

        return await response.json()
async def download_dataset(dataset_id: str) -> str:
    """Download the dataset and return the local dataset path."""
    try:
        local_dataset_path = f"/home/z/Music/devnew_xaiservice/XAIport/datasets/{dataset_id}"
        #down_cloud(f"datasets/{dataset_id}", local_dataset_path)
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


extractor = AttentionExtractor("facebook/timesformer-base-finetuned-k400")
class VideoExplainRequest(BaseModel):
    video_path: str
    num_frames: int = 8


import traceback

@app.post("/staa-video-explain/")
async def staa_video_explain(request: VideoExplainRequest):
    try:
        video_path = request.video_path
        num_frames = request.num_frames

        print(f"🟢 Received XAI request: Video={video_path}, Frames={num_frames}")

        # Check if file exists
        if not os.path.exists(video_path):
            print(f"❌ ERROR: Video file not found: {video_path}")
            raise HTTPException(status_code=400, detail=f"Video file not found: {video_path}")

        # Run XAI processing
        spatial_attention, temporal_attention, frames, logits = staa_model.extract_attention(video_path, num_frames)
        prediction_idx = torch.argmax(logits, dim=1).item()
        prediction = staa_model.model.config.id2label[prediction_idx]

        print(f"✅ XAI Processing Successful: {prediction}")

        return {
            "prediction": prediction,
            "spatial_attention": spatial_attention.tolist(),
            "temporal_attention": temporal_attention.tolist(),
        }

    except Exception as e:
        error_message = traceback.format_exc()  # Get full error traceback
        print(f"🚨 XAI Processing Failed: {error_message}")
        raise HTTPException(status_code=500, detail=f"Error processing video: {error_message}")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
