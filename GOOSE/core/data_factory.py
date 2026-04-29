import cv2
import numpy as np
import json
import os
import time
import datetime
import random
from vision.aruco_calibrator import ArucoCalibrator
from vision.position_estimator import PositionEstimator
from core.autopilot import AutoPilot

class DataFactory:
    """
    The "Autonomous Data Factory"
    Flies the drone using PID while logging ArUco 'Oracle' poses vs Raw Frames.
    This creates the perfect dataset for training an RL bot or a Vision Refinement model.
    """
    
    def __init__(self, output_dir="flight_data/training_set", aruco_cal=None, enable_aruco=True):
        self.output_dir = output_dir
        self.session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_path = os.path.join(self.output_dir, self.session_id)
        os.makedirs(self.save_path, exist_ok=True)
        
        self.enable_aruco = bool(enable_aruco)
        if self.enable_aruco:
            self.aruco_cal = aruco_cal if aruco_cal else ArucoCalibrator()
        else:
            self.aruco_cal = None
        self.log_file = open(os.path.join(self.save_path, "metadata.jsonl"), "w")
        self.frame_count = 0
        
        # Jitter parameters for diverse data collection
        self.jitter_active = False
        self.target_offset = [0, 0, 0] # x, y, z offsets from standard ALIGN point
        self._last_jitter_time = 0

    def collect(self, frame, pose_edge, autopilot):
        """
        Processes a frame and logs data.
        """
        # 1. Get ArUco "Oracle" Ground Truth
        cam_matrix = autopilot._cam_matrix if hasattr(autopilot, '_cam_matrix') else None
        dist_coeffs = autopilot._dist_coeffs if hasattr(autopilot, '_dist_coeffs') else None
        
        if cam_matrix is None:
            cam_matrix = np.array([[921.0, 0, 480.0], [0, 921.0, 360.0], [0, 0, 1]])
            dist_coeffs = np.array([-0.044, 0.124, 0.0, 0.0, -0.158])

        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if self.enable_aruco and self.aruco_cal is not None:
            aruco_pose, ids, _ = self.aruco_cal.detect(frame_bgr, cam_matrix, dist_coeffs)
        else:
            aruco_pose, ids = None, []
        
        # 2. LOG EVERYTHING while active (Senior RL approach: need negatives too)
        self.frame_count += 1
        img_name = f"frame_{self.frame_count:05d}.jpg"
        img_path = os.path.join(self.save_path, img_name)
        
        # Only save every 3rd frame if oracle is missing to save space
        if aruco_pose is None and self.frame_count % 3 != 0:
            return False

        cv2.imwrite(img_path, frame_bgr)
        
        metadata = {
            "frame": img_name,
            "timestamp": time.time(),
            "oracle_visible": aruco_pose is not None,
            "oracle_pose": {
                "x": float(aruco_pose[0]) if aruco_pose else None,
                "y": float(aruco_pose[1]) if aruco_pose else None,
                "z": float(aruco_pose[2]) if aruco_pose else None
            },
            "edge_pose": {
                "x": float(pose_edge.x_cm) if pose_edge else None,
                "y": float(pose_edge.y_cm) if pose_edge else None,
                "z": float(pose_edge.z_cm) if pose_edge else None,
                "conf": float(pose_edge.confidence) if pose_edge else 0.0
            },
            "autopilot_phase": autopilot.phase,
            "jitter_offset": self.target_offset
        }
        
        self.log_file.write(json.dumps(metadata) + "\n")
        self.log_file.flush()
        return True

    def update_jitter(self, now):
        """
        Randomizes the autopilot setpoint to collect data from different angles.
        """
        if now - self._last_jitter_time > 2.0: # Change offset every 2 seconds
            self.target_offset = [
                random.uniform(-30, 30), # X jitter
                random.uniform(-20, 20), # Y jitter
                random.uniform(-40, 40)  # Z jitter
            ]
            self._last_jitter_time = now
            print(f"[DataFactory] New Jitter Setpoint: {self.target_offset}")
        
        return self.target_offset

    def close(self):
        self.log_file.close()
        print(f"[DataFactory] Dataset saved to {self.save_path} ({self.frame_count} samples)")
