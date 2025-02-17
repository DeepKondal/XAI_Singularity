from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import List
import logging
import cam_resnet

app = FastAPI()

class XAIRequest(BaseModel):
    dataset_id: str
    algorithms: List[str]

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

######Shap and LIME
    
# import warnings
# warnings.filterwarnings('ignore') 



from fool_shap_lime.adversarial_models import * 
from fool_shap_lime.utils import *
from fool_shap_lime.get_data import *

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

import numpy as np
import pandas as pd

import lime
import lime.lime_tabular
import shap
from copy import deepcopy


# Get the data set and do some preprocessing
params = Params("xaiserver/fool_shap_lime/model_configurations/experiment_params.json")
np.random.seed(params.seed)
X, y, cols = get_and_preprocess_compas_data(params)

# Add a random column -- this is what we'll have LIME/SHAP explain.
X['unrelated_column'] = np.random.choice([0,1],size=X.shape[0])
features = [c for c in X]

categorical_feature_name = ['two_year_recid', 'c_charge_degree_F', 'c_charge_degree_M',\
                            'sex_Female', 'sex_Male', 'race', 'unrelated_column']

categorical_feature_indcs = [features.index(c) for c in categorical_feature_name]

race_indc = features.index('race')
unrelated_indcs = features.index('unrelated_column')
X = X.values


class racist_model_f:
    # Decision rule: classify negatively if race is black
    def predict(self,X):
        return np.array([params.negative_outcome if x[race_indc] > 0 else params.positive_outcome for x in X])

    def predict_proba(self, X): 
        return one_hot_encode(self.predict(X))

    def score(self, X,y):
        return np.sum(self.predict(X)==y) / len(X)
    
class innocuous_model_psi:
    # Decision rule: classify according to randomly drawn column 'unrelated column'
    def predict(self,X):
        return np.array([params.negative_outcome if x[unrelated_indcs] > 0 else params.positive_outcome for x in X])

    def predict_proba(self, X): 
        return one_hot_encode(self.predict(X))

    def score(self, X,y):
        return np.sum(self.predict(X)==y) / len(X)

# Split the data and normalize
xtrain,xtest,ytrain,ytest = train_test_split(X,y)
xtest_not_normalized = deepcopy(xtest)
ss = StandardScaler().fit(xtrain)
xtrain = ss.transform(xtrain)
xtest = ss.transform(xtest)

# Train the adversarial model for LIME with f and psi 
adv_lime = Adversarial_Lime_Model(racist_model_f(), innocuous_model_psi()).\
            train(xtrain, ytrain, feature_names=features, categorical_features=categorical_feature_indcs)


@app.post("/lime")
async def lime_explanation():
    # Example functionality
    ex_indc = np.random.choice(xtest.shape[0])
    
    normal_explainer = lime.lime_tabular.LimeTabularExplainer(xtrain, feature_names=adv_lime.get_column_names(),
                                                              discretize_continuous=False, categorical_features=categorical_feature_indcs)
    normal_exp = normal_explainer.explain_instance(xtest[ex_indc], racist_model_f().predict_proba).as_list()
    
    adv_explainer = lime.lime_tabular.LimeTabularExplainer(xtrain, feature_names=adv_lime.get_column_names(), 
                                                           discretize_continuous=False, categorical_features=categorical_feature_indcs)
    adv_exp = adv_explainer.explain_instance(xtest[ex_indc], adv_lime.predict_proba).as_list()
    
    fidelity_score = adv_lime.fidelity(xtest[ex_indc:ex_indc+1])
    
    return {"Explanation on biased f": normal_exp[:3], "Explanation on adversarial model": adv_exp[:3], "Prediction fidelity": fidelity_score}

@app.post("/shap")
async def shap_explanation():
    # Select a random instance to explain
    to_examine = np.random.choice(xtest.shape[0])

    # Train the adversarial model for SHAP with f and psi
    adv_shap = Adversarial_Kernel_SHAP_Model(racist_model_f(), innocuous_model_psi()).train(xtrain, ytrain, feature_names=features)
    
    # Set the background distribution for the SHAP explainer using kmeans
    background_distribution = shap.kmeans(xtrain, 10)
    
    # Explain the biased model
    biased_kernel_explainer = shap.KernelExplainer(racist_model_f().predict, background_distribution)
    biased_shap_values = biased_kernel_explainer.shap_values(xtest[to_examine:to_examine+1])
    
    # Explain the adversarial model
    adv_kernel_explainer = shap.KernelExplainer(adv_shap.predict, background_distribution)
    adv_shap_values = adv_kernel_explainer.shap_values(xtest[to_examine:to_examine+1])
    
    # Calculate fidelity
    fidelity_score = adv_shap.fidelity(xtest[to_examine:to_examine+1])
    
    # Since SHAP values are numpy arrays, convert them to lists for JSON serialization
    return {
        "Biased SHAP Values": biased_shap_values[0].tolist(),
        "Adversarial SHAP Values": adv_shap_values[0].tolist(),
        "Fidelity Score": fidelity_score
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
