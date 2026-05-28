from roboflow import Roboflow
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Securely load configuration from environment variables
api_key = os.getenv("ROBOFLOW_API_KEY")
workspace_id = os.getenv("WORKSPACE_ID", "droneai-vwpho")
project_id = os.getenv("PROJECT_ID", "targetpractice")

if not api_key:
    print("Error: ROBOFLOW_API_KEY not found in environment or .env file.")
else:
    rf = Roboflow(api_key=api_key)
    workspace = rf.workspace(workspace_id)

    workspace.deploy_model(
        model_type="yolo26",
        model_path="./assets/models/",  # Point to the DIRECTORY
        filename="targetModel.pt",      # Point to the FILE
        project_ids=[project_id],
        model_name="v1"
    )