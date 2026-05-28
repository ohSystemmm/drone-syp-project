import cv2
import numpy as np
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple
from vision.edge_pose import EdgePoseSolver
from vision.sector_pose import SectorPoseSolver

class PoseKalmanFilter:
    """Kalman filter for 3D pose smoothing with dynamic dt and Innovation Gating."""
    def __init__(self, process_noise=1e-2, measurement_noise=5.0):
        self.kf = cv2.KalmanFilter(6, 3, 0)
        dt = 0.033
        self.kf.transitionMatrix = np.array([
            [1, 0, 0, dt, 0,  0],[0, 1, 0, 0,  dt, 0],[0, 0, 1, 0,  0,  dt],[0, 0, 0, 1,  0,  0], [0, 0, 0, 0,  1,  0],[0, 0, 0, 0,  0,  1],
        ], dtype=np.float32)
        self.kf.measurementMatrix = np.array([[1, 0, 0, 0, 0, 0],[0, 1, 0, 0, 0, 0], [0, 0, 1, 0, 0, 0],
        ], dtype=np.float32)
        self.kf.processNoiseCov = np.eye(6, dtype=np.float32) * process_noise
        self.kf.measurementNoiseCov = np.eye(3, dtype=np.float32) * measurement_noise
        self.kf.errorCovPost = np.eye(6, dtype=np.float32) * 100
        self._initialized = False
        self._last_time = None
        self._consecutive_misses = 0
        self.MAX_COAST_FRAMES = 45

    def update(self, x, y, z, override_noise: Optional[float] = None):
        now = time.monotonic()
        dt = (now - self._last_time) if self._last_time else 0.033
        self._last_time = now
        
        # Cap dt to prevent wild jumps if thread stalled
        dt = max(0.001, min(dt, 0.1))
        self.kf.transitionMatrix[0, 3] = dt
        self.kf.transitionMatrix[1, 4] = dt
        self.kf.transitionMatrix[2, 5] = dt

        predicted = self.kf.predict()
        
        # --- INNOVATION GATING (Zero-Delay Outlier Rejection) ---
        if self._initialized:
            pred_x, pred_y, pred_z = float(predicted[0][0]), float(predicted[1][0]), float(predicted[2][0])
            # If measurement jumps impossibly far in a single frame, reject it and coast
            # Relaxed from 40 to 60 for better tracking of fast-moving targets
            if abs(x - pred_x) > 60 or abs(y - pred_y) > 60 or abs(z - pred_z) > 60:
                self.kf.statePost = predicted.copy()
                return pred_x, pred_y, pred_z

        measurement = np.array([[x], [y], [z]], dtype=np.float32)

        old_noise = None
        if override_noise is not None:
            old_noise = self.kf.measurementNoiseCov.copy()
            self.kf.measurementNoiseCov = np.eye(3, dtype=np.float32) * float(override_noise)

        if not self._initialized:
            self.kf.statePost = np.array([[x], [y], [z], [0], [0], [0]], dtype=np.float32)
            self._initialized = True
            if old_noise is not None:
                self.kf.measurementNoiseCov = old_noise
            return x, y, z
            
        self.kf.correct(measurement)
        if old_noise is not None:
            self.kf.measurementNoiseCov = old_noise
            
        self._consecutive_misses = 0
        state = self.kf.statePost
        return float(state[0]), float(state[1]), float(state[2])

    def predict_only(self):
        if not self._initialized: return None
        self._consecutive_misses += 1
        if self._consecutive_misses > self.MAX_COAST_FRAMES:
            self._initialized = False
            return None
        predicted = self.kf.predict()
        self.kf.statePost = predicted.copy()
        return float(predicted[0]), float(predicted[1]), float(predicted[2])

@dataclass
class PoseEstimate:
    x_cm: float
    y_cm: float
    z_cm: float
    angle_deg: float
    confidence: float
    tilt_x_deg: float = 0.0
    tilt_y_deg: float = 0.0
    normal: Optional[np.ndarray] = None
    is_coasted: bool = False
    is_partial: bool = False
    ellipse: Optional[Tuple] = None
    best_contour: Optional[np.ndarray] = None
    target_px: Optional[Tuple[int, int]] = None
    display_ellipse: Optional[Tuple] = None       # Ellipse in distorted frame coords (for drawing)
    display_target_px: Optional[Tuple[int, int]] = None  # Center in distorted frame coords
    sector_data: Optional[dict] = None           # Data from 8-area perspective method
    roi_box: Optional[Tuple[int, int, int, int]] = None # The bounding box used for primary pose

class PositionEstimator:
    OUTER_DIAMETER = 50.0
    REAL_RADIUS = OUTER_DIAMETER / 2.0
    CALIBRATED_FX = 921.0
    CALIBRATED_FY = 921.0
    CALIBRATED_CX = 480.0
    CALIBRATED_CY = 360.0
    DIST_COEFFS = np.array([-0.044, 0.124, 0.0, 0.0, -0.158], dtype=np.float64)

    def __init__(self, frame_width=960, frame_height=720):
        scale_x, scale_y = frame_width / 960.0, frame_height / 720.0
        self.camera_matrix = np.array([[self.CALIBRATED_FX * scale_x, 0, self.CALIBRATED_CX * scale_x],[0, self.CALIBRATED_FY * scale_y, self.CALIBRATED_CY * scale_y],
            [0, 0, 1]
        ], dtype=np.float64)
        
        self._kalman = PoseKalmanFilter()
        self.edge_solver = EdgePoseSolver(self.camera_matrix, self.DIST_COEFFS, self.REAL_RADIUS)
        self.sector_solver = SectorPoseSolver(self.camera_matrix, self.REAL_RADIUS)
        self.Z_SCALE = 1.0
        self._last_raw_z = None
        self.target_history = [] # For heatmap
        self.MAX_HISTORY = 50

    def estimate(self, frame_bgr, roi_box=None) -> Optional[PoseEstimate]:
        """
        Estimate 3D pose using Mask-Refined BBox Logic.
        - Z: Calculated from the Major Axis of the refined ring mask.
        - Position (X, Y): Calculated from the centroid of the refined mask.
        - Tilt: Derived from the refined mask's aspect ratio and sector areas.
        """
        if not roi_box:
            return self._coast_kalman()

        x1, y1, x2, y2 = roi_box
        # Crop ROI strictly to the bbox
        rx1, ry1, rx2, ry2 = int(x1), int(y1), int(x2), int(y2)
        roi_frame = frame_bgr[max(0, ry1):ry2, max(0, rx1):rx2]
        if roi_frame.size == 0: return self._coast_kalman()

        # 1. Professional Masking (Tight Hue + Saturation)
        hsv = cv2.cvtColor(roi_frame, cv2.COLOR_BGR2HSV)
        
        lower_red1 = np.array([0, 167, 0])
        upper_red1 = np.array([10, 255, 255])
        lower_red2 = np.array([160, 167, 0])
        upper_red2 = np.array([180, 255, 255])
        
        mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
        mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
        mask = cv2.bitwise_or(mask1, mask2)
        
        # Clean up with morphological ops (Morph Size 13)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.dilate(mask, kernel, iterations=1)

        # 2. Extract the actual ring using Contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        valid_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > 449]
        if not valid_contours: return self._coast_kalman()

        # Pick the largest contour
        best_contour = max(valid_contours, key=cv2.contourArea)
        
        # Create ring_mask for sector_solver
        ring_mask = np.zeros_like(mask)
        cv2.drawContours(ring_mask, [best_contour], -1, 255, thickness=cv2.FILLED)
        
        # Get refined geometry from the contour
        tx, ty, tw, th = cv2.boundingRect(best_contour)
        
        # Refined global coordinates
        ref_x1, ref_y1 = rx1 + tx, ry1 + ty
        ref_x2, ref_y2 = ref_x1 + tw, ref_y1 + th
        refined_bbox = (ref_x1, ref_y1, ref_x2, ref_y2)
        
        # 3. Geometric Pose from Ellipse
        display_ellipse = None
        if len(best_contour) >= 5:
            ellipse = cv2.fitEllipse(best_contour)
            (ell_x, ell_y), (minor_axis, major_axis), ell_angle = ellipse
            
            global_cx = rx1 + ell_x
            global_cy = ry1 + ell_y
            tcx = ell_x
            tcy = ell_y
            
            display_ellipse = ((global_cx, global_cy), (minor_axis, major_axis), ell_angle)
            
            raw_z = (self.OUTER_DIAMETER * self.camera_matrix[0,0]) / max(major_axis, 1.0)
            
            ratio = min(1.0, minor_axis / max(major_axis, 1.0))
            tilt_magnitude_deg = math.degrees(math.acos(ratio))
        else:
            tcx = tx + tw / 2.0
            tcy = ty + th / 2.0
            global_cx = rx1 + tcx
            global_cy = ry1 + tcy
            major_px = max(tw, th)
            raw_z = (self.OUTER_DIAMETER * self.camera_matrix[0,0]) / max(major_px, 1.0)
            tilt_magnitude_deg = 0.0
            
        z_cm_scaled = raw_z * self.Z_SCALE

        x_cm = (global_cx - self.camera_matrix[0,2]) * raw_z / self.camera_matrix[0,0]
        y_cm = (global_cy - self.camera_matrix[1,2]) * raw_z / self.camera_matrix[1,1]

        # 5. Sector analysis for Tilt Direction
        sector_res = self.sector_solver.solve_from_mask(ring_mask, (tcx, tcy))
        
        tilt_x, tilt_y = 0.0, 0.0
        if sector_res:
            if tw > th: # Horizontal major axis -> vertical tilt (X-rot)
                tilt_x = tilt_magnitude_deg if sector_res['tilt_x_factor'] < 0 else -tilt_magnitude_deg
            else: # Vertical major axis -> horizontal tilt (Y-rot)
                tilt_y = tilt_magnitude_deg if sector_res['tilt_y_factor'] < 0 else -tilt_magnitude_deg

        filtered_x, filtered_y, filtered_z = self._kalman.update(x_cm, y_cm, z_cm_scaled)

        # Update History
        self.target_history.append((int(global_cx), int(global_cy)))
        if len(self.target_history) > self.MAX_HISTORY:
            self.target_history.pop(0)

        # Shift best_contour to global coords for visualization
        best_contour[:, 0, 0] += rx1
        best_contour[:, 0, 1] += ry1

        return PoseEstimate(
            x_cm=round(filtered_x, 1), y_cm=round(filtered_y, 1), z_cm=round(filtered_z, 1),
            angle_deg=round(tilt_magnitude_deg, 1),
            confidence=0.98,
            tilt_x_deg=round(tilt_x, 1), 
            tilt_y_deg=round(tilt_y, 1),
            normal=np.array([0,0,-1]), 
            ellipse=None, 
            best_contour=best_contour, 
            target_px=(int(global_cx), int(global_cy)),
            display_ellipse=display_ellipse, 
            display_target_px=(int(global_cx), int(global_cy)),
            sector_data=sector_res,
            roi_box=refined_bbox 
        )

    def _coast_kalman(self):
        res = self._kalman.predict_only()
        if not res: return None
        return PoseEstimate(x_cm=round(res[0], 1), y_cm=round(res[1], 1), z_cm=round(res[2], 1),
                            angle_deg=0.0, confidence=0.3, is_coasted=True, target_px=None)

    def draw_estimate(self, frame, est: PoseEstimate, show_heatmap: bool = False) -> np.ndarray:
        color = (255, 255, 0) if not est.is_coasted else (100, 100, 100)
        
        # 0. Heatmap (Drawn first to be in background)
        if show_heatmap and self.target_history:
            heatmap_overlay = np.zeros_like(frame)
            for i, pos in enumerate(self.target_history):
                # Increasing intensity (blue to red) for more recent points
                # Here we use Red channel for heatmap
                intensity = int(255 * (i + 1) / len(self.target_history))
                cv2.circle(heatmap_overlay, pos, 15, (0, 0, intensity), -1)
            cv2.addWeighted(heatmap_overlay, 0.5, frame, 1.0, 0, frame)

        # 1. Draw Refined ROI Box (The "Real" Source)
        if est.roi_box is not None:
            x1, y1, x2, y2 = est.roi_box
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 1)
            cv2.putText(frame, "REFINED RING BBOX", (int(x1), int(y1)-5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

        # 2. Sector Visualization Overlay (Centered on refined target)
        if est.sector_data and not est.is_coasted:
            overlay = frame.copy()
            cx, cy = est.display_target_px
            max_dim = max(est.roi_box[2]-est.roi_box[0], est.roi_box[3]-est.roi_box[1]) / 2
            
            for i in range(8):
                start_angle = -180 + (i * 45)
                end_angle = -180 + ((i + 1) * 45)
                s_color = (0, 255, 0) if i == est.sector_data['closest_sector_idx'] else (200, 200, 200)
                cv2.ellipse(overlay, (int(cx), int(cy)), (int(max_dim), int(max_dim)), 
                            0, start_angle, end_angle, s_color, -1)
                
            cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

        # 3. Draw Ring Geometry (Fine Detection)
        if est.best_contour is not None:
            cv2.drawContours(frame, [est.best_contour.astype(np.int32)], -1, color, 1)
        
        disp_el = est.display_ellipse
        if disp_el:
            cv2.ellipse(frame, disp_el, (0, 255, 255), 2)

        # 4. Draw Sector-based "Closest" side indicator
        if est.sector_data and not est.is_coasted:
            idx = est.sector_data['closest_sector_idx']
            cx, cy = est.display_target_px
            angle_rad = -math.pi + (idx * math.pi / 4) + (math.pi / 8)
            tip_x = int(cx + 80 * math.cos(angle_rad))
            tip_y = int(cy + 80 * math.sin(angle_rad))
            cv2.line(frame, (int(cx), int(cy)), (tip_x, tip_y), (0, 255, 0), 2)
            cv2.putText(frame, "CLOSEST", (tip_x, tip_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 5. Draw Crosshair and Tracker
        marker_px = est.display_target_px
        if marker_px is not None:
            cx, cy = marker_px
            # Professional Tracker Corners
            t_size = 20
            t_thick = 2
            t_color = (0, 255, 255)
            # Top-left
            cv2.line(frame, (cx - t_size, cy - t_size), (cx - t_size + 10, cy - t_size), t_color, t_thick)
            cv2.line(frame, (cx - t_size, cy - t_size), (cx - t_size, cy - t_size + 10), t_color, t_thick)
            # Top-right
            cv2.line(frame, (cx + t_size, cy - t_size), (cx + t_size - 10, cy - t_size), t_color, t_thick)
            cv2.line(frame, (cx + t_size, cy - t_size), (cx + t_size, cy - t_size + 10), t_color, t_thick)
            # Bottom-left
            cv2.line(frame, (cx - t_size, cy + t_size), (cx - t_size + 10, cy + t_size), t_color, t_thick)
            cv2.line(frame, (cx - t_size, cy + t_size), (cx - t_size, cy + t_size - 10), t_color, t_thick)
            # Bottom-right
            cv2.line(frame, (cx + t_size, cy + t_size), (cx + t_size - 10, cy + t_size), t_color, t_thick)
            cv2.line(frame, (cx + t_size, cy + t_size), (cx + t_size, cy + t_size - 10), t_color, t_thick)

            cv2.circle(frame, marker_px, 5, (0, 0, 255), -1)
            cv2.drawMarker(frame, marker_px, (0, 255, 255), cv2.MARKER_CROSS, 15, 2)
        
        # 6. HUD Text
        for i, text in enumerate([f"X: {est.x_cm:+.1f}", f"Y: {est.y_cm:+.1f}", f"Z: {est.z_cm:.1f}", f"Tilt: {est.angle_deg:.1f}deg"]):
            cv2.putText(frame, text, (10, 30 + i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 3)
            cv2.putText(frame, text, (10, 30 + i*25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 1)
        
        return frame
