import os
import shutil
from PIL import Image
import numpy as np
import random, av
import pandas as pd
from PIL import Image, ImageFilter
import aiofiles
import asyncio
from azure.storage.blob.aio import BlobServiceClient


class DataProcess:
    def __init__(self, base_storage_address):
        self.datasets = {}
        self.dataset_properties = {}
        self.base_storage_address = base_storage_address 
        self.metadata = {} # New class attribute


    async def upload_dataset(self, data_files, dataset_id, data_type):
        """异步上传数据集"""
        if dataset_id in self.datasets:
            raise ValueError("Dataset ID already exists.")

        dataset_dir = os.path.join(self.base_storage_address, data_type, dataset_id)

        if not os.path.exists(dataset_dir):
            os.makedirs(dataset_dir)

        for file_path in data_files:
            label = os.path.basename(os.path.dirname(file_path))
            label_dir = os.path.join(dataset_dir, label)
            if not os.path.exists(label_dir):
                os.makedirs(label_dir)

            file_extension = os.path.splitext(file_path)[1]
            dest_file_name = os.path.splitext(os.path.basename(file_path))[0] + file_extension
            dest_file_path = os.path.join(label_dir, dest_file_name)

            async with aiofiles.open(file_path, 'rb') as src, aiofiles.open(dest_file_path, 'wb') as dst:
                await dst.write(await src.read())
        print(f"Dataset '{dataset_id}' uploaded. Current dataset properties: {self.dataset_properties}")

        self.datasets[dataset_id] = data_files
        self.dataset_properties[dataset_id] = {
            "storage_address": dataset_dir,
            "data_type": data_type,
            "num_files": len(data_files)
        }



    def get_dataset_info(self, dataset_id):
        """ 获取数据集的信息 """
        if dataset_id not in self.datasets:
            raise ValueError("Dataset ID does not exist.")
        return self.dataset_properties[dataset_id]



    def delete_dataset(self, dataset_id):
        """ 删除整个数据集 """
        if dataset_id not in self.datasets:
            raise ValueError("Dataset ID does not exist.")
        
        dataset_dir = self.dataset_properties[dataset_id]["storage_address"]
        shutil.rmtree(dataset_dir)
        del self.datasets[dataset_id]
        del self.dataset_properties[dataset_id]

    def download_dataset(self, dataset_id, download_path):
        """ 下载整个数据集 """
        if dataset_id not in self.datasets:
            raise ValueError("Dataset ID does not exist.")

        dataset_dir = self.dataset_properties[dataset_id]["storage_address"]
        shutil.copytree(dataset_dir, download_path)


    import numpy as np
    from PIL import Image

    def gaussian_noise(image, severity=1):
        """ 对图像添加高斯噪声 """
        c = [0.08, 0.12, 0.18, 0.26, 0.38][severity - 1]

        pil_image = np.array(image) / 255.0
        noise = np.random.randn(*pil_image.shape) * c
        noisy_image = np.clip(pil_image + noise, 0, 1) * 255
        return Image.fromarray(noisy_image.astype(np.uint8))


    def blur(self, image, severity=1):
        """ 对图像应用模糊效果 """
        from PIL import ImageFilter
        c = [ImageFilter.BLUR, ImageFilter.GaussianBlur(2), ImageFilter.GaussianBlur(3), ImageFilter.GaussianBlur(5), ImageFilter.GaussianBlur(7)][severity - 1]
        return image.filter(c)
    


    async def apply_image_perturbation(self, dataset_id, perturbation_func, severity=1):
        """ Apply a perturbation to all images in a dataset """

        dataset_dir = os.path.join(self.base_storage_address, dataset_id)


        # New folder for perturbed images
        perturbed_folder_name = f"{dataset_id}_{perturbation_func.__name__}_{severity}"
        perturbed_folder_path = os.path.join(dataset_dir, '..', perturbed_folder_name)
        os.makedirs(perturbed_folder_path, exist_ok=True)

        # Iterate over each label folder in the dataset
        for label in os.listdir(dataset_dir):
            label_dir = os.path.join(dataset_dir, label)
            if not os.path.isdir(label_dir):
                continue  # Skip if not a directory

            # Create corresponding label folder in the perturbed folder
            perturbed_label_dir = os.path.join(perturbed_folder_path, label)
            os.makedirs(perturbed_label_dir, exist_ok=True)

            for file in os.listdir(label_dir):
                file_path = os.path.join(label_dir, file)
                if os.path.isfile(file_path) and file.lower().endswith(('.png', '.jpg', '.jpeg')):
                    image = await asyncio.to_thread(Image.open, file_path)
                    perturbed_image = await asyncio.to_thread(perturbation_func, image, severity)

                    perturbed_path = os.path.join(perturbed_label_dir, file)
                    await asyncio.to_thread(perturbed_image.save, perturbed_path)
                    print(f"Saved perturbed image to {perturbed_path}")
        tasks = []
        for label_dir_name in os.listdir(dataset_dir):
            label_dir_path = os.path.join(dataset_dir, label_dir_name)
            if not os.path.isdir(label_dir_path):
                continue

            perturbed_label_dir = os.path.join(perturbed_folder_path, label_dir_name)
            os.makedirs(perturbed_label_dir, exist_ok=True)

            for file_name in os.listdir(label_dir_path):
                file_path = os.path.join(label_dir_path, file_name)
                if os.path.isfile(file_path) and file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    tasks.append(self._process_and_save_image(file_path, perturbed_label_dir, perturbation_func, severity))

        await asyncio.gather(*tasks)

        # # 上传到云端
        # cloud_upload_path = os.path.join("datasets", perturbed_folder_name)
        # up_cloud(perturbed_folder_path, cloud_upload_path)

        return perturbed_folder_path
    


    async def _process_and_save_image(self, file_path, perturbed_label_dir, perturbation_func, severity):
        """异步处理和保存单个图像"""
        image = Image.open(file_path)
        perturbed_image = perturbation_func(image, severity)

        perturbed_path = os.path.join(perturbed_label_dir, os.path.basename(file_path))
        perturbed_image.save(perturbed_path)
        print(f"Saved perturbed image to {perturbed_path}")

    def get_dataset_paths(self, dataset_id, perturbation_func_name, severity):
        """ Get dataset_dir and perturbed_dataset_path based on inputs """
        if dataset_id not in self.dataset_properties:
            raise ValueError("Dataset ID does not exist.")
        
        dataset_dir = self.dataset_properties[dataset_id]["storage_address"]
        perturbed_folder_name = f"{dataset_id}_perturbation_{perturbation_func_name}_{severity}"
        perturbed_dataset_path = os.path.join(dataset_dir, '..', perturbed_folder_name)
        
        return dataset_dir, perturbed_dataset_path
    
# kinetcs dataset process
    def load_metadata(self, labels_csv, video_list_txt):
        self.metadata['labels'] = pd.read_csv(labels_csv)
        self.metadata['video_map'] = {}
        with open(video_list_txt, "r") as f:
            for line in f:
                video_name, label = line.strip().split()
                self.metadata['video_map'][video_name] = label

    def get_label(self, video_name):
        if 'video_map' not in self.metadata:
            raise ValueError("Metadata not loaded. Call load_metadata() first.")
        return self.metadata['video_map'].get(video_name, "Unknown")

    def process_kinetics_video(self, video_path, num_frames=8):
        video_name = os.path.splitext(os.path.basename(video_path))[0]
        output_dir = os.path.join(self.base_storage_address, "videos", video_name)
        os.makedirs(output_dir, exist_ok=True)

        container = av.open(video_path)
        frames = [frame.to_image() for frame in container.decode(video=0)]
        sampled_frames = [frames[i] for i in np.linspace(0, len(frames) - 1, num_frames, dtype=int)]

        for idx, frame in enumerate(sampled_frames):
            frame.save(os.path.join(output_dir, f"frame_{idx + 1}.jpg"))

        label = self.get_label(video_name)
        return {"video_name": video_name, "label": label, "frame_dir": output_dir}