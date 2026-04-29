import cv2
import numpy as np
from vision.aruco_calibrator import ArucoCalibrator

def test():
    img = cv2.imread("image copy.png")
    if img is None:
        print("Could not load image.png")
        return

    # standard Tello-like matrix
    camera_matrix = np.array([[921.0, 0, 480.0], [0, 921.0, 360.0], [0, 0, 1]])
    dist_coeffs = np.array([-0.044, 0.124, 0.0, 0.0, -0.158])

    cal = ArucoCalibrator()
    
    # Try 1: Standard detection
    res, ids, corners = cal.detect(img, camera_matrix, dist_coeffs)
    print(f"Standard Detection: IDs found: {ids}")

    # Try 2: CLAHE Pre-processing (for the backlighting)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_clahe = clahe.apply(gray)
    img_clahe = cv2.cvtColor(gray_clahe, cv2.COLOR_GRAY2BGR)
    res2, ids2, corners2 = cal.detect(img_clahe, camera_matrix, dist_coeffs)
    print(f"CLAHE Detection: IDs found: {ids2}")

    # Debug draw
    out = cal.draw_markers(img.copy())
    cv2.imwrite("debug_aruco.png", out)
    print("Debug image saved to debug_aruco.png")

if __name__ == "__main__":
    test()
