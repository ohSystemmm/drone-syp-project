import cv2
import numpy as np
import math
from vision.sector_pose import SectorPoseSolver

def test_sector_pose():
    # Load the screenshot/drawing provided by the user
    img = cv2.imread("image copy.png")
    if img is None:
        print("Could not load 'image copy.png'")
        return

    # 1. Generate mask for the red ring
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # Red has two ranges in HSV
    mask1 = cv2.inRange(hsv, (0, 70, 50), (10, 255, 255))
    mask2 = cv2.inRange(hsv, (170, 70, 50), (180, 255, 255))
    mask = cv2.bitwise_or(mask1, mask2)

    # 2. Find centroid
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        print("No red ring detected in the image.")
        return
    
    cnt = max(contours, key=cv2.contourArea)
    M = cv2.moments(cnt)
    if M["m00"] == 0: return
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    # 3. Setup Solver (50cm diameter -> 25cm radius)
    camera_matrix = np.array([[921.0, 0, 480.0], [0, 921.0, 360.0], [0, 0, 1]])
    solver = SectorPoseSolver(camera_matrix, real_radius_cm=25.0)

    # 4. Solve
    results = solver.solve_from_mask(mask, (cx, cy))
    
    if results:
        print(f"Centroid: ({cx}, {cy})")
        print(f"Closest Sector Index: {results['closest_sector_idx']}")
        print(f"Tilt Factor X: {results['tilt_x_factor']:.3f}")
        print(f"Tilt Factor Y: {results['tilt_y_factor']:.3f}")
        
        # 5. Visualize
        out = solver.visualize(img, (cx, cy), results)
        cv2.circle(out, (cx, cy), 5, (255, 0, 0), -1)
        cv2.imwrite("debug_sector_pose.png", out)
        print("Result saved to debug_sector_pose.png")

if __name__ == "__main__":
    test_sector_pose()
