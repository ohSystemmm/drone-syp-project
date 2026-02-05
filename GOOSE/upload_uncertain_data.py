import os
import argparse
from roboflow import Roboflow

def upload_to_roboflow(folder="./flight_data/uncertain/", api_key="YOUR_ROBOFLOW_API_KEY"):
    """
    Uploads images from the uncertainty folder to Roboflow with the 'to-label' tag.
    """
    # Workspace/Project details as requested
    WORKSPACE_ID = "droneai-vwpho"
    PROJECT_ID = "targetpractice"
    TAG = "to-label"

    if not os.path.exists(folder):
        print(f"Error: Folder {folder} does not exist.")
        return

    # Initialize Roboflow
    rf = Roboflow(api_key=api_key)
    project = rf.workspace(WORKSPACE_ID).project(PROJECT_ID)

    # Get all images
    images = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    if not images:
        print("No uncertain images found to upload.")
        return

    print(f"Starting upload of {len(images)} images to {WORKSPACE_ID}/{PROJECT_ID}...")

    for img_name in images:
        path = os.path.join(folder, img_name)
        try:
            print(f"Uploading {img_name}...")
            project.upload(path, tag=TAG)
        except Exception as e:
            print(f"Failed to upload {img_name}: {e}")

    print("Upload complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload uncertainty-sampled images to Roboflow.")
    parser.add_argument("--folder", default="./flight_data/uncertain/", help="Path to uncertainty images")
    parser.add_argument("--key", default="YOUR_ROBOFLOW_API_KEY", help="Roboflow API Key")
    args = parser.parse_args()

    upload_to_roboflow(folder=args.folder, api_key=args.key)