import cv2
import numpy as np
import os
from vision.position_estimator import PositionEstimator
from vision.detector import ObjectDetector

def test_on_real_image():
    # 1. Load the provided image
    possible_paths = [
        "../../Downloads/IMG_20260416_100651.jpg",
        "IMG_20260416_100651.jpg",
        os.path.join(os.path.expanduser("~"), "Downloads", "IMG_20260416_100651.jpg")
    ]
    
    img = None
    for p in possible_paths:
        if os.path.exists(p):
            img = cv2.imread(p)
            if img is not None:
                print(f"Loaded image from: {p}")
                break
    
    if img is None:
        print("Error: Could not find the image 'IMG_20260416_100651.jpg'.")
        return

    # 2. Initialize Actual Detector and Estimator
    model_path = "GOOSE/assets/models/targetModel.onnx"
    detector = ObjectDetector(model_path)
    detector.load_model()
    
    h, w = img.shape[:2]
    estimator = PositionEstimator(frame_width=w, frame_height=h)

    # 3. Detect using the real ONNX model
    _, detections = detector.detect(img, conf_threshold=0.3)
    
    if not detections:
        print("Model failed to detect target in this image.")
        return
        
    # Select the best detection
    best_det = max(detections, key=lambda d: d['conf'])
    roi_box = best_det['box']
    print(f"Model Detection: {roi_box} (conf: {best_det['conf']:.2f})")

    # 4. Estimate Pose using the model's box
    est = estimator.estimate(img, roi_box)
    
    if est:
        print("\n--- Pose Estimation Result (Using Real Model Box) ---")
        print(f"Distance (Z):   {est.z_cm:>6.1f} cm")
        print(f"Lateral (X):    {est.x_cm:>6.1f} cm")
        print(f"Vertical (Y):   {est.y_cm:>6.1f} cm")
        print(f"Tilt Angle:     {est.angle_deg:>6.1f} deg")
        if est.sector_data:
            print(f"Closest Sector: {est.sector_data['closest_sector_idx']}")
        
        # 5. Draw and Save
        out = estimator.draw_estimate(img.copy(), est)
        cv2.imwrite("real_test_result.jpg", out)
        print("\nVisualized result saved to 'real_test_result.jpg'")
    else:
        print("Pose estimation failed.")

if __name__ == "__main__":
    test_on_real_image()


if __name__ == "__main__":
    test_on_real_image()
