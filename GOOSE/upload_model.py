from roboflow import Roboflow
import os

# Securely load API Key
api_key = os.getenv("ROBOFLOW_API_KEY", "YOUR_ROBOFLOW_API_KEY")

rf = Roboflow(api_key=api_key)
workspace = rf.workspace("droneai-vwpho")

workspace.deploy_model(
    model_type="yolo26",
    model_path="./assets/models/",  # Point to the DIRECTORY
    filename="targetModel.pt",      # Point to the FILE
    project_ids=["targetpractice"],
    model_name="v1"
)
