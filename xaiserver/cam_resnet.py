import os
from PIL import Image
import json
from torchvision.models import resnet50
import warnings
warnings.filterwarnings('ignore')
from codecarbon import track_emissions
from torchvision import transforms
from pytorch_grad_cam import (
    GradCAM, HiResCAM, ScoreCAM, GradCAMPlusPlus,
    AblationCAM, XGradCAM, EigenCAM, EigenGradCAM,
    LayerCAM, FullGrad, GradCAMElementWise
)
from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget
from pytorch_grad_cam.utils.image import show_cam_on_image
from typing import List, Callable, Optional
import numpy as np
import cv2
import torch
from tqdm import tqdm
# from functionaltool.cloudstorage import up_cloud, down_cloud

# 在 cam_resnet 模块中定义
CAM_ALGORITHMS_MAPPING = {
    "GradCAM": GradCAM,
    "HiResCAM": HiResCAM,
    "GradCAMPlusPlus": GradCAMPlusPlus,
    "XGradCAM": XGradCAM,
    "LayerCAM": LayerCAM
}


# Function to load images
def load_images_from_directory(root_path: str):
    dataset = []
    for label in os.listdir(root_path):
        label_path = os.path.join(root_path, label)
        if os.path.isdir(label_path):
            for image_file in os.listdir(label_path):
                image_path = os.path.join(label_path, image_file)
                if image_path.lower().endswith(('.png', '.jpg', '.jpeg')):
                    img = Image.open(image_path)
                    dataset.append((img, label, image_file))
    return dataset
def ensure_rgb(img):
    if img.mode != 'RGB':
        return img.convert('RGB')
    return img

# Define the transformation pipeline to apply to each image
transform = transforms.Compose([
    transforms.Resize((224, 224)),  # Resize the image to 224x224 pixels
    transforms.ToTensor()            # Convert the image to a PyTorch tensor
])
# current_dir = "/home/workstation/code/XAImethods/CAIN"
# detail_dir = "/imagenet/val_images10k_attack/gaussian_noise/2_ResNet"

# dataset_path = f"{current_dir}{detail_dir}"

#current_dir = "/home/z/Music/devnew_xaiservice/XAIport/"
        # dataset_path = f"{current_dir}{detail_dir}"
        # dataset = load_images_from_directory(dataset_path)

# def xai_run(dataset_dirs):
#     for dataset_path in dataset_dirs:
#         # 直接使用 dataset_path，因为它已经是完整的路径
#         dataset = load_images_from_directory(dataset_path)

#         with open("index/imagenet_class_index.json", "r") as f:
#             imagenet_class_index = json.load(f)


#CAM_ALGORITHMS = [GradCAM, HiResCAM, GradCAMPlusPlus, XGradCAM, LayerCAM]

def xai_run(dataset_dirs, cam_algorithms):
    for dataset_path in dataset_dirs:
        dataset = load_images_from_directory(dataset_path)
        dataset_name = os.path.basename(dataset_path)
        local_save_dir = os.path.join("xairesult", dataset_name)
        cloud_save_dir = os.path.join("xairesult", dataset_name)

        with open("index/imagenet_class_index.json", "r") as f:
            imagenet_class_index = json.load(f)
        # Determine device
        if torch.cuda.is_available():
            device = torch.device("cuda")
            print("Using CUDA!")
        else:
            device = torch.device("cpu")
            print("Using CPU!")

        # ResNet Model Wrapper
        class ResNetWrapper(torch.nn.Module):
            def __init__(self, model):
                super(ResNetWrapper, self).__init__()
                self.model = model

            def forward(self, x):
                return self.model(x)
            
        label_to_index_description = {v[0]: (k, v[1]) for k, v in imagenet_class_index.items()}


        # Initialize the model and target layer
        model = resnet50(pretrained=True).to(device)
        model_wrapper = ResNetWrapper(model).to(device)
        target_layer_gradcam = model.layer4[-1].conv3

        # Options: GradCAM, HiResCAM, GradCAMPlusPlus, XGradCAM, 
        # EigenGradCAM, LayerCAM, GradCAMElementWise
        # #    GradCAM, HiResCAM, GradCAMPlusPlus, XGradCAM, LayerCAM, GradCAMElementWise
        # CAM_ALGORITHMS = [GradCAM, HiResCAM, GradCAMPlusPlus, XGradCAM, LayerCAM]

        for CAM_ALGORITHM in cam_algorithms:
            cam_algorithm_name = CAM_ALGORITHM.__name__
                
            def run_grad_cam_on_image(model: torch.nn.Module,
                                    target_layer: torch.nn.Module,
                                    targets_for_gradcam: List[Callable],
                                    input_tensor: torch.nn.Module,
                                    input_image: Image,
                                    reshape_transform: Optional[Callable] = None,
                                    method: Callable = CAM_ALGORITHM):
                with method(model=model,
                            target_layers=[target_layer],
                            reshape_transform=reshape_transform) as cam:
                    repeated_tensor = input_tensor[None, :].repeat(len(targets_for_gradcam), 1, 1, 1)
                    batch_results = cam(input_tensor=repeated_tensor,
                                        targets=targets_for_gradcam)
                    results = []
                    grayscale_cams = []
                    for grayscale_cam in batch_results:
                        # Ensure the input image is transformed to match the model input dimensions
                        # Ensure the input image is transformed to match the model input dimensions
                        transformed_input_image = transform(input_image).numpy().transpose(1, 2, 0)
                        visualization = show_cam_on_image(np.float32(transformed_input_image), grayscale_cam, use_rgb=True)



                        results.append(visualization)
                        grayscale_cams.append(grayscale_cam)
                    return np.hstack(results), grayscale_cams


            def print_top_categories(model, img_tensor, top_k=5):
                logits = model(img_tensor.unsqueeze(0))
                indices = logits.cpu()[0, :].detach().numpy().argsort()[-top_k :][::-1]
                for i in indices:
                    print(f"Predicted class {i}: {imagenet_class_index[str(i)][1]}")

            def get_top_k_targets(model, input_tensor, k=5):
                logits = model(input_tensor.unsqueeze(0))
                top_k_indices = logits[0].argsort(descending=True)[:k].cpu().numpy()
                return [ClassifierOutputTarget(index) for index in top_k_indices]

            def apply_mask_to_image(image_path, mask_path, output_path):
                # Read the original image and mask
                original_image = cv2.imread(image_path)
                grayscale_mask = np.load(mask_path)
                
                # Ensure the mask has the same dimensions as the image
                h, w, _ = original_image.shape
                grayscale_mask = cv2.resize(grayscale_mask, (w, h))
                
                # Normalize grayscale mask to [0, 1]
                grayscale_mask = (grayscale_mask - grayscale_mask.min()) / (grayscale_mask.max() - grayscale_mask.min())

                # Convert the mask to 3D
                grayscale_mask_3d = np.repeat(grayscale_mask[:, :, np.newaxis], 3, axis=2)
                
                # Apply the mask to the original image
                masked_image = (original_image * grayscale_mask_3d).astype(np.uint8)
                
                # Save the masked image
                cv2.imwrite(output_path, masked_image)

            # Prepare for the main loop
            BATCH_SIZE = 100
            num_batches = len(dataset) // BATCH_SIZE + (1 if len(dataset) % BATCH_SIZE != 0 else 0)

            #save_dir = f"{current_dir}/results/{detail_dir}/resnet50/{cam_algorithm_name}"
            save_dir = os.path.join(local_save_dir, "resnet50", cam_algorithm_name)

            if not os.path.exists(save_dir):
                os.makedirs(save_dir)

            def ensure_rgb(img):
                if img.mode != 'RGB':
                    return img.convert('RGB')
                return img

            model = resnet50(pretrained=True).to(device)
            target_layer_gradcam = model.layer4[-1].conv3  # Last convolutional layer of ResNet50
            transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor()
            ])


            for batch_num in range(num_batches):
                start_idx = batch_num * BATCH_SIZE
                end_idx = min((batch_num + 1) * BATCH_SIZE, len(dataset))

                # Initialize ResNet50


                for idx in tqdm(range(start_idx, end_idx)):
                    img, label, filename = dataset[idx]
                    try:
                        #torch.cuda.empty_cache()
                        img = ensure_rgb(img)
                        img_tensor = transform(img).to(device)

                        # Map label to ImageNet index
                        index_description = label_to_index_description.get(label)
                        if index_description is None:
                            print(f"Warning: Label '{label}' not found in the JSON file!")
                            continue

                        index_str, description = index_description
                        index = int(index_str)
                        dynamic_targets_for_gradcam = [ClassifierOutputTarget(index)]

                        gradcam_result, grayscale_cams = run_grad_cam_on_image(
                            model=model,
                            target_layer=target_layer_gradcam,
                            targets_for_gradcam=dynamic_targets_for_gradcam,
                            input_tensor=img_tensor,
                            input_image=img,
                            reshape_transform=None  # No reshape required for ResNet50
                        )

                        logits = model(img_tensor.unsqueeze(0))
                        top_indices = logits[0].argsort(descending=True)[:].cpu().numpy()
                        predictions = {index: {"score": logits[0][index].item(), "label": imagenet_class_index[str(index)][1]} for index in top_indices}

                        img_dir = os.path.join(save_dir, filename.rsplit('.', 1)[0])
                        if not os.path.exists(img_dir):
                            os.makedirs(img_dir)

                        true_label_file = os.path.join(img_dir, 'true_label.txt')
                        with open(true_label_file, 'w') as f:
                            f.write(str(label))

                        img_name = os.path.join(img_dir, "original.jpg")
                        gradcam_name = os.path.join(img_dir, "gradcam.jpg")
                        grayscale_name = os.path.join(img_dir, "grayscale.jpg")
                        grayscale_npy_name = os.path.join(img_dir, "grayscale.npy")
                        scores_name = os.path.join(img_dir, "scores.npy")
                        info_name = os.path.join(img_dir, "info.txt")
                        masked_image_name = os.path.join(img_dir, "masked_image.jpg")

                        img.save(img_name)
                        Image.fromarray(gradcam_result).save(gradcam_name)
                        Image.fromarray((grayscale_cams[0] * 255).astype(np.uint8)).save(grayscale_name)
                        np.save(grayscale_npy_name, grayscale_cams[0])

                        
                        apply_mask_to_image(img_name, grayscale_npy_name, masked_image_name)
                        # 对masked_image.jpg进行model inference
                        masked_image = Image.open(masked_image_name).resize((384, 384))
                        masked_tensor = transforms.ToTensor()(masked_image).to(device)
                        masked_logits = model(masked_tensor.unsqueeze(0))

                        top_indices_masked = masked_logits[0].argsort(descending=True)[:].cpu().numpy()
                        #predictions_masked = {index: {"score": masked_logits[0][index].item(), "label": model.config.id2label[index]} for index in top_indices_masked}
                        predictions_masked = {index: {"score": masked_logits[0][index].item(), "label": imagenet_class_index[str(index)][1]} for index in top_indices_masked}

                    
                        # 保存masked_image的inference结果到info_masked.txt
                        info_masked_name = os.path.join(img_dir, "info_masked.txt")
                        with open(info_masked_name, 'w') as f:
                            for index, data in predictions_masked.items():
                                label = data["label"]
                                score = data["score"]
                                f.write(f"Class {index} ({label}): {score:.2f}\n")


                        scores = [data["score"] for _, data in predictions.items()]
                        np.save(scores_name, scores)

                        with open(info_name, 'w') as f:
                            for index, data in predictions.items():
                                label = data["label"]
                                score = data["score"]
                                f.write(f"Class {index} ({label}): {score:.2f}\n")
                    except Exception as e:
                        print(f"Error processing {filename}: {str(e)}")
            # up_cloud(save_dir, os.path.join(cloud_save_dir, "resnet50", cam_algorithm_name))
            print(f"{CAM_ALGORITHM} processing completed.")

