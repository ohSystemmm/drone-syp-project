import cv2
import numpy as np
import math
from typing import Optional, Tuple

class EdgePoseSolver:
    """
    Library-optimized Ellipse-to-3D Pose Solver.
    Uses YOLO ROI to prevent hallucinations.
    """
    def __init__(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray, real_radius_cm: float = 25.0):
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.real_radius = real_radius_cm

    def solve_from_frame(self, roi_bgr: np.ndarray, offset: Tuple[int, int] = (0, 0)) -> Optional[dict]:
        # 1. Color Filter for Red/Orange ring
        hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        # Tighter HSV: require decent saturation (70+) and brightness (60+)
        # to reject background reds (wood, carpet, skin)
        mask = cv2.bitwise_or(cv2.inRange(hsv, (0, 70, 60), (12, 255, 255)),
                              cv2.inRange(hsv, (165, 70, 60), (180, 255, 255)))
        
        # Clean up mask noise with larger kernel for better gap-bridging
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        
        # 2. Extract contours from color mask ONLY
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: return None
        best_contour = max(contours, key=cv2.contourArea)
        if len(best_contour) < 15: return None

        # 3. Standard Library Ellipse Fit
        try: ellipse = cv2.fitEllipse(best_contour)
        except: return None

        # 4. Analytical Pose (Library solvePnP style)
        pose = self.solve_pose_analytical(ellipse, offset)
        if pose:
            # Shift ellipse center from ROI-local to full-frame coordinates
            (ex, ey), (d1, d2), angle = ellipse
            pose['ellipse'] = ((ex + offset[0], ey + offset[1]), (d1, d2), angle)
            pose['contour'] = best_contour
        return pose

    def solve_pose_analytical(self, ellipse: Tuple, offset: Tuple[int, int] = (0, 0)) -> Optional[dict]:
        (xc, yc), (d1, d2), angle_deg = ellipse
        xc += offset[0]; yc += offset[1]
        major, minor = max(d1, d2) / 2.0, min(d1, d2) / 2.0
        if major == 0: return None

        # Standard Pinhole Math (Senior Library standard)
        z = (self.real_radius * self.camera_matrix[0,0]) / major
        x = (xc - self.camera_matrix[0,2]) * z / self.camera_matrix[0,0]
        y = (yc - self.camera_matrix[1,2]) * z / self.camera_matrix[1,1]
        
        # Angle from axis ratio (acos of perspective distortion)
        angle_rad = math.acos(np.clip(minor/major, 0, 1))
        
        # Decompose tilt into X and Y components based on ellipse rotation
        # If angle_deg=0, major is vertical, so squash is horizontal -> tilt around Y
        # OpenCV angle_deg is from vertical, clockwise.
        # We'll map this to a coordinate system where 0 is tilt around X (squash Y).
        rot_rad = math.radians(angle_deg)
        tilt_x = math.degrees(angle_rad * math.cos(rot_rad))
        tilt_y = math.degrees(angle_rad * math.sin(rot_rad))
        
        return {
            'x_cm': x, 'y_cm': y, 'z_cm': z,
            'tilt_x': tilt_x, 'tilt_y': tilt_y,
            'confidence': minor / major,
            'normal': np.array([0, 0, -1]) # Target facing drone
        }
