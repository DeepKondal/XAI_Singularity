from azure.storage.blob import BlobServiceClient
import os
from dotenv import load_dotenv

# 获取脚本文件的绝对路径
script_dir = os.path.dirname(os.path.abspath(__file__))

# 加载 .env 文件中的环境变量
load_dotenv()

# 从环境变量中获取连接字符串
connect_str = os.getenv('AZURE_STORAGE_CONNECTION_STRING')

# 创建 BlobServiceClient 对象
blob_service_client = BlobServiceClient.from_connection_string(connect_str)

# 选择或创建容器
container_name = 'xaidata12'
container_client = blob_service_client.get_container_client(container_name)

# 检查容器是否存在，如果不存在则创建
try:
    container_properties = container_client.get_container_properties()
    print("容器已存在。")
except Exception as e:
    print("容器不存在，正在创建...")
    container_client.create_container()

def upload_file_to_blob(file_name, blob_name):
    file_name = os.path.abspath(file_name)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(file_name, "rb") as data:
        blob_client.upload_blob(data, overwrite=True)
    print(f"'{file_name}' 上传至 Blob 存储中的 '{blob_name}' 完成。")

def download_file_from_blob(blob_name, download_file_name):
    download_file_name = os.path.abspath(download_file_name)
    os.makedirs(os.path.dirname(download_file_name), exist_ok=True)
    blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
    with open(download_file_name, "wb") as download_file:
        download_file.write(blob_client.download_blob().readall())
    print(f"'{blob_name}' 从 Blob 存储下载至 '{download_file_name}' 完成。")

def up_cloud(local_directory, cloud_directory):
    local_directory = os.path.abspath(local_directory)

    for root, dirs, files in os.walk(local_directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            blob_name = os.path.join(cloud_directory, os.path.relpath(file_path, local_directory)).replace("\\", "/")
            upload_file_to_blob(file_path, blob_name)


def down_cloud(blob_directory, local_directory):
    local_directory = os.path.join(script_dir, local_directory)
    local_directory = os.path.abspath(local_directory)

    blobs = container_client.list_blobs(name_starts_with=blob_directory)
    for blob in blobs:
        blob_name = blob.name
        local_file_path = os.path.join(local_directory, os.path.relpath(blob_name, blob_directory)).replace("\\", "/")
        download_file_from_blob(blob_name, local_file_path)

# 示例用法
# up_cloud("./dataprocess/datasets/t1", "datasets")  # 上传 't1' 文件夹到云端 'datasets' 文件夹中
# down_cloud("datasets/t1", "./download/t1")  # 从云端的 'datasets/t1' 下载文件夹到本地
