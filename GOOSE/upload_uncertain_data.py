import os
import argparse
from roboflow import Roboflow
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def upload_to_roboflow(folder="./flight_data/uncertain/", api_key=None):
    """
    Uploads images from the uncertainty folder to Roboflow with the 'to-label' tag.
    """
    # Load from environment variables with fallbacks
    api_key = api_key or os.getenv("ROBOFLOW_API_KEY")
    workspace_id = os.getenv("WORKSPACE_ID", "droneai-vwpho")
    project_id = os.getenv("PROJECT_ID", "targetpractice")
    tag = os.getenv("TAG", "to-label")

    if not api_key:
        print("Error: Roboflow API Key not found. Set ROBOFLOW_API_KEY in .env or use --key.")
        return

    if not os.path.exists(folder):
        print(f"Error: Folder {folder} does not exist.")
        return

    # Initialize Roboflow
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(workspace_id).project(project_id)

    # Get all images
    images = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not images:
        print("No uncertain images found to upload.")
        return

    print(f"Starting upload of {len(images)} images to {workspace_id}/{project_id}...")

    for img_name in images:
        path = os.path.join(folder, img_name)
        try:
            print(f"Uploading {img_name}...")
            project.upload(path, tag=tag)
        except Exception as e:
            print(f"Failed to upload {img_name}: {e}")

    print("Upload complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload uncertainty-sampled images to Roboflow.")
    parser.add_argument("--folder", default="./flight_data/uncertain/", help="Path to uncertainty images")
    parser.add_argument("--key", help="Roboflow API Key (overrides .env)")
    args = parser.parse_args()

    upload_to_roboflow(folder=args.folder, api_key=args.key)
