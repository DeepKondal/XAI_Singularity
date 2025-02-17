'''
Version 0.0.1
This is the previous try to create a server that can handle the pipeline of the XAI service.
Without the status check system, we can't correctly run the whole pipeline.
This must be reconstructed to a new version.
'''
from fastapi import FastAPI, HTTPException, Request
import httpx
import json
import os
import asyncio
import logging
from common.neo4j_client import ProvenanceModel
import datetime



app = FastAPI(title="Coordination Center")
#Provenance_logic
provenance = ProvenanceModel()


# Traffic Counters
#traffic_count = {"8002": 0, "8005": 0}

async def async_http_post(url, json_data=None, files=None):
    async with httpx.AsyncClient(timeout=120.0) as client:  # Timeout set to 60 seconds
        if json_data:
            response = await client.post(url, json=json_data)
        elif files:
            response = await client.post(url, files=files)
        else:
            response = await client.post(url)

        # 检查是否是307重定向响应
        if response.status_code == 307:
            redirect_url = response.headers.get('Location')
            if redirect_url:
                print(f"Redirecting to {redirect_url}")
                return await async_http_post(redirect_url, json_data, files)

        if response.status_code != 200:
            print(f"Error response: {response.text}")  # 打印出错误响应内容
            logging.error(f"Error in POST to {url}: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)

        return response.json()


# 处理上传配置
async def process_upload_config(upload_config):
    # for dataset_id, dataset_info in upload_config['datasets'].items():
    #     url = upload_config['server_url'] + f"/upload-dataset/{dataset_id}"
    #     local_zip_file_path = dataset_info['local_zip_path']  # 每个数据集的本地 ZIP 文件路径

    #     async with httpx.AsyncClient() as client:
    #         with open(local_zip_file_path, 'rb') as f:
    #             files = {'zip_file': (os.path.basename(local_zip_file_path), f)}
    #             response = await client.post(url, files=files)
    #         response.raise_for_status()

    #     # 可以添加更多的逻辑处理上传后的结果
    #     print(f"Uploaded dataset {dataset_id} successfully.")
    for dataset_id, dataset_info in upload_config['datasets'].items():
            local_video_dir = dataset_info.get('local_video_dir')

            if not local_video_dir or not os.path.exists(local_video_dir):
                raise HTTPException(status_code=400, detail=f"Video directory {local_video_dir} not found.")

            # Use the endpoint /process-kinetics-dataset to process the video directory
            url = upload_config['server_url'] + "/process-kinetics-dataset"
            json_data = {"video_dir": local_video_dir, "num_frames": 8}

            # Trigger video processing
            await async_http_post(url, json_data=json_data)
            print(f"Processed video dataset {dataset_id} successfully.")



# 处理扰动配置
async def process_perturbation_config(perturbation_config):
    if not perturbation_config['datasets']:
        print("No perturbation configured, skipping this step.")
        return
    url = perturbation_config['server_url']
    for dataset, settings in perturbation_config['datasets'].items():

        if settings['perturbation_type'] == "none":        #skip perturbation if perturbation_type is none
            print(f"Skipping perturbation for dataset {dataset}.")
            continue
        full_url = f"{url}/apply-perturbation/{dataset}/{settings['perturbation_type']}/{settings['severity']}"
        await async_http_post(full_url)

async def process_model_config(model_config, run_id):
    base_urls = model_config['base_urls']  # Dynamically pick from config
    dataset_id = "kinetics_400"
    load_split = model_config["load_split"]  # P value (percentage of requests to go to new model)

    video_dir = "dataprocess/videos"
    video_files = sorted([f for f in os.listdir(video_dir) if f.endswith(".mp4")])  # Ensure consistent order

    # 🟢 Dynamically ensure 8002 is first and 8005 is second
    old_model_server, new_model_server = sorted(base_urls, key=lambda url: url.split(":")[-1])

    # 🟢 Assign videos based on P (Strangler Pattern)
    total_videos = len(video_files)
    num_to_old_model = int((load_split / 100) * total_videos)  # Videos going to old model (8002)
    num_to_new_model = total_videos - num_to_old_model  # Videos staying in new model (8005)

    videos_for_old_model = video_files[:num_to_old_model]  # First P% go to old model
    videos_for_new_model = video_files[num_to_old_model:]  # Remaining go to new model

    for video_file in video_files:
        try:
            # 🟢 Dynamically assign based on video list
            chosen_server = old_model_server if video_file in videos_for_old_model else new_model_server
            full_url = f"{chosen_server}/{model_config['models']['kinetics_video']['model_name']}/kinetics_video"

            # 🟢 Update traffic count safely
            server_port = chosen_server.split(":")[-1]
            traffic_count.setdefault(server_port, 0)
            traffic_count[server_port] += 1

            print(f"📡 Routing {video_file} to: {full_url} "
                  f"(Total requests - {old_model_server}: {traffic_count[old_model_server.split(':')[-1]]}, "
                  f"{new_model_server}: {traffic_count[new_model_server.split(':')[-1]]})")

            # Send request per video
            response = await async_http_post(full_url, json_data={"video_path": os.path.join(video_dir, video_file)})

            # Process response
            for result in response.get("results", []):
                video_filename = result.get("video_file", "Unknown")
                prediction = result.get("prediction", "Unknown")

                # Save predictions
                provenance.create_model_prediction(video_filename, prediction)
                provenance.link_processing_to_prediction("Model Processing", video_filename)
                provenance.link_dataset_to_prediction(dataset_id, video_filename)
                provenance.link_pipeline_to_prediction(run_id, video_filename)

                print(f"✅ Prediction for {video_filename}: {prediction}")

        except Exception as e:
            print(f"❌ Error processing {video_file}: {e}")  # Ensure next video gets processed



async def process_xai_config(xai_config):
    xai_server = xai_config['base_url']  # XAI service at port 8003

    for dataset, settings in xai_config['datasets'].items():
        video_dir = settings.get('video_path', '')
        num_frames = settings.get('num_frames', 8)

        if not os.path.isdir(video_dir):
            print(f"⚠ Video path {video_dir} is not a directory. Skipping XAI processing.")
            continue

        video_files = [os.path.abspath(os.path.join(video_dir, f)) for f in os.listdir(video_dir) if f.endswith(".mp4")]

        if not video_files:
            print(f"⚠ No video files found in {video_dir}. Skipping XAI processing.")
            continue

        for video_file in video_files:
            try:
                data = {
                    "video_path": video_file,
                    "num_frames": num_frames
                }

                print(f"📡 Sending XAI request to {xai_server} for {video_file}")
                xai_full_url = f"{xai_server}/staa-video-explain/"
                xai_response = await async_http_post(xai_full_url, json_data=data)
                print(f"✅ XAI response for {video_file}: {xai_response}")

            except Exception as e:
                print(f"❌ Error processing XAI from {xai_server} for video {video_file}: {e}")

# 处理评估配置
async def process_evaluation_config(evaluation_config):
    base_url = evaluation_config['base_url']
    for dataset, settings in evaluation_config['datasets'].items():
        data = {
            "dataset_id": dataset,
            "model_name": settings['model_name'],
            "perturbation_func": settings['perturbation_func'],
            "severity": settings['severity'],
            "cam_algorithms": settings['algorithms']
        }
        full_url = f"{base_url}/evaluate_cam"
        await async_http_post(full_url, json_data=data)

# 按顺序处理每个配置步骤
async def process_pipeline_step(config, step_key, process_function):
    if step_key in config:
        await process_function(config[step_key])



async def run_pipeline_from_config(config):
    run_id = f"run_{datetime.datetime.now().isoformat()}"

    try:
        provenance.create_pipeline_run(run_id, datetime.datetime.now().isoformat(), "Running")
        dataset_id = "kinetics_400"
        provenance.create_dataset(dataset_id, "Kinetics-400", "dataprocess/videos/")
    except Exception as e:
        logging.error(f"❌ Failed to create provenance records: {e}")

    try:
        await process_pipeline_step(config, 'upload_config', process_upload_config)
        provenance.create_processing_step("Upload Data", "upload", str(config["upload_config"]))
        provenance.link_pipeline_step(run_id, "Upload Data")
        provenance.link_dataset_to_processing(dataset_id, "Upload Data")  # 🆕 Link dataset to processing

    except Exception as e:
        logging.error(f"❌ Upload processing failed: {e}")

    try:
        await process_pipeline_step(config, 'perturbation_config', process_perturbation_config)
        provenance.create_processing_step("Apply Perturbation", "perturbation", str(config["perturbation_config"]))
        provenance.link_pipeline_step(run_id, "Apply Perturbation")
    except Exception as e:
        logging.error(f"❌ Perturbation processing failed: {e}")

    try:
        await process_pipeline_step(config, 'model_config', lambda cfg: process_model_config(cfg, run_id))
        provenance.create_processing_step("Model Processing", "model", str(config["model_config"]))
        provenance.link_pipeline_step(run_id, "Model Processing")
    except Exception as e:
        logging.error(f"❌ Model processing failed: {e}")

    try:
        await process_pipeline_step(config, 'xai_config', process_xai_config)
        provenance.create_processing_step("XAI Analysis", "XAI", str(config["xai_config"]))
        provenance.link_pipeline_step(run_id, "XAI Analysis")
    except Exception as e:
        logging.error(f"❌ XAI processing failed: {e}")

    try:
        provenance.create_pipeline_run(run_id, datetime.datetime.now().isoformat(), "Completed")
    except Exception as e:
        logging.error(f"❌ Failed to mark pipeline as completed in provenance: {e}")

    print(f"✅ Pipeline {run_id} execution completed.")


pipeline_status = {}

@app.post("/run_pipeline/")
async def run_pipeline(request: Request):
    config = await request.json()
    run_id = f"run_{datetime.datetime.now().isoformat()}"
    pipeline_status[run_id] = "Running"

    try:
        await run_pipeline_from_config(config)
        pipeline_status[run_id] = "Completed"
        # Print final traffic distribution
        print(f"📊 Final Traffic Stats: Model Server (8002) → {traffic_count['8002']} requests, New Model Server (8005) → {traffic_count['8005']} requests")
        return {"message": f"Pipeline {run_id} executed successfully"}
    except Exception as e:
        pipeline_status[run_id] = f"Failed: {str(e)}"
        return HTTPException(status_code=500, detail=str(e))

@app.get("/pipeline_status/{run_id}")
async def get_pipeline_status(run_id: str):
    status = pipeline_status.get(run_id, "Not Found")
    return {"run_id": run_id, "status": status}

# 加载配置文件
def load_config():
    with open("config.json", "r") as file:
        return json.load(file)
    


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8880)




# 主函数
def main():
    config = load_config()
    asyncio.run(run_pipeline_from_config(config))

if __name__ == "__main__":
    main()


