import os
from PIL import Image
import json
from torchvision.models import resnet50
from torchvision import transforms
import torch
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix
from tqdm import tqdm
import shutil  
from sklearn.metrics import roc_curve, auc, precision_recall_fscore_support, confusion_matrix
from sklearn.preprocessing import label_binarize
import matplotlib.pyplot as plt
import json
import torch
from sklearn.metrics import precision_recall_fscore_support, confusion_matrix
import numpy as np
from scipy.stats import ks_2samp 
def calculate_ks_statistic(distribution1, distribution2):
    ks_statistic, p_value = ks_2samp(distribution1, distribution2)
    return ks_statistic
#from functionaltool.cloudstorage import up_cloud, down_cloud
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
current_dir = "XAIport"
#dataset_path = f"{current_dir}/imagenet/val_images10k"



original_dataset_probs = None
# for dataset_path in dataset_paths: 部分



def model_run(dataset_paths):
    for dataset_path in dataset_paths:

        dataset = load_images_from_directory(dataset_path)

        with open("index/imagenet_class_index.json", "r") as f:
            imagenet_class_index = json.load(f)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print("Using:", device)

        label_to_index_description = {v[0]: (k, v[1]) for k, v in imagenet_class_index.items()}

        model = resnet50(pretrained=True).to(device)
        model.eval()
        model_name = "ResNet50"

        normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            normalize
        ])

        true_labels = []
        predicted_labels = []
        predicted_probs = []

        dataset_name = os.path.basename(dataset_path)
        target_dir = os.path.join("performance", dataset_path + "_" + model_name)
        os.makedirs(target_dir, exist_ok=True)
        
        num_classes = 1000

        for img, label, filename in tqdm(dataset):
            img = ensure_rgb(img)
            img_tensor = transform(img).to(device)

            with torch.no_grad():
                logits = model(img_tensor.unsqueeze(0))
                probabilities = torch.softmax(logits, dim=1).cpu().numpy()[0]

            index_str, _ = label_to_index_description.get(label, (None, None))
            if index_str is None:
                continue
            true_label = int(index_str)
            true_labels.append(true_label)
            predicted_labels.append(np.argmax(probabilities))
            predicted_probs.append(probabilities)

        true_labels_binary = label_binarize(true_labels, classes=range(num_classes))
        predicted_probs = np.array(predicted_probs)

        fpr, tpr, _ = roc_curve(true_labels_binary.ravel(), predicted_probs.ravel())
        roc_auc = auc(fpr, tpr)

        class_auc_scores = []
        for i in range(num_classes):
            true_binary = (np.array(true_labels) == i).astype(int)
            pred_probs = predicted_probs[:, i]
            fpr, tpr, _ = roc_curve(true_binary, pred_probs)
            auc_score = auc(fpr, tpr)
            class_auc_scores.append(auc_score)
        roc_auc_one_vs_rest = np.mean(class_auc_scores)

        # plt.figure()
        # plt.plot(fpr, tpr, color='blue', lw=2, label='Micro-Average ROC curve (area = {0:0.4f})'.format(roc_auc))
        # plt.plot([0, 1], [0, 1], 'k--', lw=2)
        # plt.xlim([0.0, 1.0])
        # plt.ylim([0.0, 1.05])
        # plt.xlabel('False Positive Rate')
        # plt.ylabel('True Positive Rate')
        # plt.title('Micro-Average Receiver Operating Characteristic')
        # plt.legend(loc="lower right")


        # plt.figure()
        # plt.plot(range(num_classes), class_auc_scores, color='blue', lw=2, label='One-vs-All ROC curve (area = {0:0.4f})'.format(roc_auc_one_vs_rest))
        # plt.plot([0, num_classes], [0.5, 0.5], 'k--', lw=2)
        # plt.xlim([0, num_classes])
        # plt.ylim([0.0, 1.05])
        # plt.xlabel('Class')
        # plt.ylabel('AUC Score')
        # plt.title('One-vs-All Receiver Operating Characteristic')
        # plt.legend(loc="lower right")


        precision, recall, f1_score, _ = precision_recall_fscore_support(true_labels, predicted_labels, average='macro')

        cm = confusion_matrix(true_labels, predicted_labels)
        tp = np.diag(cm)
        fp = cm.sum(axis=0) - tp
        fn = cm.sum(axis=1) - tp
        tn = cm.sum() - (fp + fn + tp)



        # 其他代码保持不变，直到结果的保存部分

        metrics_filename = f"{model_name}_{dataset_name}_metrics.txt"
        metrics_path = os.path.join(target_dir, metrics_filename)

        # metrics_filename = f"{model_name}_{dataset_name}_metrics.txt"
        # metrics_path = os.path.join(target_dir, metrics_filename)
        
        if dataset_path == dataset_paths[0]:
            original_dataset_probs = [max(probs) for probs in predicted_probs]  # 选择最高的概率值
        else:
            # 对于攻击数据集
            attacked_dataset_probs = [max(probs) for probs in predicted_probs]
            ks_statistic = calculate_ks_statistic(original_dataset_probs, attacked_dataset_probs)
            print(f"K-S statistic for {os.path.basename(dataset_path)}: {ks_statistic:.5f}")

            # 将K-S值写入度量文件
            with open(metrics_path, "a") as f:
                f.write(f"K-S Statistic (vs original): {ks_statistic:.5f}\n")

        with open(metrics_path, "w") as f:
            f.write(f"Micro-Average AUC: {roc_auc:.5f}\n")
            f.write(f"One-vs-All Average AUC: {roc_auc_one_vs_rest:.5f}\n")
            f.write(f"Precision (macro-average): {precision:.5f}\n")
            f.write(f"Recall (macro-average): {recall:.5f}\n")
            f.write(f"F1 Score (macro-average): {f1_score:.5f}\n")
            f.write(f"True Positives (per class): {tp.tolist()}\n")
            f.write(f"False Positives (per class): {fp.tolist()}\n")
            f.write(f"False Negatives (per class): {fn.tolist()}\n")
            f.write(f"True Negatives (per class): {tn.tolist()}\n")

        print(f"Metrics saved to {metrics_path}")

        local_performance_path = "/home/z/Music/devnew_xaiservice/XAIport/modelserver/performance/datasets"
        cloud_performance_path = "modelperformance"

        # 执行上传
        # up_cloud(local_performance_path, cloud_performance_path)

        print("Upload to cloud storage completed.")


