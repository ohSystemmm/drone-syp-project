import cv2
import logging
import numpy as np
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

MARKER_SIZE_CM = 3.6
RING_RADIUS_CM = 25.0
RING_THICKNESS_CM = 2.0 

class ArucoCalibrator:
    """Robust ArUco detector (simplified version without profile switching)."""
    RING_LAYOUT_ROT_DEG = 45.0

    BASE_MARKER_CENTERS_3D = {
        0: np.array([0.0, -RING_RADIUS_CM, 0.0]),
        1: np.array([RING_RADIUS_CM, 0.0, 0.0]),
        2: np.array([0.0, RING_RADIUS_CM, 0.0]),
        3: np.array([-RING_RADIUS_CM, 0.0, 0.0]),
        4: np.array([0.0, -RING_RADIUS_CM, -RING_THICKNESS_CM]),
        5: np.array([-RING_RADIUS_CM, 0.0, -RING_THICKNESS_CM]),
        6: np.array([0.0, RING_RADIUS_CM, -RING_THICKNESS_CM]),
        7: np.array([RING_RADIUS_CM, 0.0, -RING_THICKNESS_CM]),
    }

    DICT_IDS = {
        "4x4_50": cv2.aruco.DICT_4X4_50,
        "4x4_100": cv2.aruco.DICT_4X4_100,
        "5x5_50": cv2.aruco.DICT_5X5_50,
    }

    # Add AprilTag families when available in current OpenCV build.
    if hasattr(cv2.aruco, "DICT_APRILTAG_16h5"):
        DICT_IDS["apriltag_16h5"] = cv2.aruco.DICT_APRILTAG_16h5
    if hasattr(cv2.aruco, "DICT_APRILTAG_25h9"):
        DICT_IDS["apriltag_25h9"] = cv2.aruco.DICT_APRILTAG_25h9
    if hasattr(cv2.aruco, "DICT_APRILTAG_36h10"):
        DICT_IDS["apriltag_36h10"] = cv2.aruco.DICT_APRILTAG_36h10
    if hasattr(cv2.aruco, "DICT_APRILTAG_36h11"):
        DICT_IDS["apriltag_36h11"] = cv2.aruco.DICT_APRILTAG_36h11

    # Standard "balanced" settings now hardcoded
    ACTIVE_DICTS = ["4x4_50", "4x4_100", "5x5_50", "apriltag_36h11", "apriltag_36h10", "apriltag_25h9", "apriltag_16h5"]
    DETECTION_SCALES = [1.0, 1.35]
    CLAHE_CLIP = 3.2
    CLAHE_GRID = (8, 8)
    GAMMA = 1.0

    def __init__(self):
        self._detectors = {}
        self._params = {}
        self._clahe = cv2.createCLAHE(clipLimit=self.CLAHE_CLIP, tileGridSize=self.CLAHE_GRID)
        self._marker_centers_3d = self._build_rotated_marker_layout(self.RING_LAYOUT_ROT_DEG)
        self._build_detectors()
        self._apply_global_params()

        # All detected IDs/corners in current frame (includes unknown IDs)
        self._last_detected_corners = {}
        # Known IDs only (present in MARKER_CENTERS_3D), used for pose
        self._last_corners = {}
        self._last_ids = []
        self._last_distance = None
        self._last_tvec = None
        self._last_ring_center_px = None
        self._last_dict_name = "-"
        self._last_debug_log_time = 0.0
        logger.info("[ArUco] Initialized. Rotation=%.1f deg", self.RING_LAYOUT_ROT_DEG)

    def _build_rotated_marker_layout(self, rot_deg: float):
        theta = np.deg2rad(rot_deg)
        c, s = float(np.cos(theta)), float(np.sin(theta))
        rot = np.array([[c, -s], [s, c]], dtype=np.float64)
        out = {}
        for marker_id, p in self.BASE_MARKER_CENTERS_3D.items():
            xy = rot @ np.array([p[0], p[1]], dtype=np.float64)
            out[marker_id] = np.array([xy[0], xy[1], p[2]], dtype=np.float64)
        return out

    def _build_detectors(self):
        for dict_name, dict_id in self.DICT_IDS.items():
            dictionary = cv2.aruco.getPredefinedDictionary(dict_id)
            params = cv2.aruco.DetectorParameters()
            detector = cv2.aruco.ArucoDetector(dictionary, params)
            self._detectors[dict_name] = detector
            self._params[dict_name] = params

    def _apply_global_params(self):
        for params in self._params.values():
            params.minMarkerPerimeterRate = 0.004
            params.maxMarkerPerimeterRate = 5.0
            params.polygonalApproxAccuracyRate = 0.06
            params.minCornerDistanceRate = 0.02
            params.minDistanceToBorder = 1
            params.maxErroneousBitsInBorderRate = 0.7
            params.errorCorrectionRate = 0.8
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
            params.cornerRefinementWinSize = 7
            params.cornerRefinementMaxIterations = 60
            params.cornerRefinementMinAccuracy = 0.01
            params.adaptiveThreshWinSizeMin = 3
            params.adaptiveThreshWinSizeMax = 35
            params.adaptiveThreshWinSizeStep = 4
            params.adaptiveThreshConstant = 6
            if hasattr(params, "useAruco3Detection"):
                params.useAruco3Detection = True

    def _clear_last(self):
        self._last_detected_corners = {}
        self._last_corners = {}
        self._last_ids = []
        self._last_distance = None
        self._last_tvec = None
        self._last_ring_center_px = None
        self._last_dict_name = "-"

    def _gamma_correct(self, gray: np.ndarray, gamma: float) -> np.ndarray:
        if abs(gamma - 1.0) < 1e-6:
            return gray
        inv = 1.0 / max(gamma, 1e-6)
        lut = np.array([((i / 255.0) ** inv) * 255.0 for i in range(256)], dtype=np.uint8)
        return cv2.LUT(gray, lut)

    def _merge_unique(self, corners, ids):
        merged = {}
        if ids is None or len(ids) == 0:
            return merged
        for idx, marker_id in enumerate(ids.flatten().tolist()):
            cnr = corners[idx][0].astype(np.float32)
            perim = float(cv2.arcLength(cnr, True))
            if marker_id not in merged or perim > merged[marker_id][1]:
                merged[marker_id] = (cnr, perim)
        return {mid: v[0] for mid, v in merged.items()}

    def _detect_best(self, gray: np.ndarray):
        gamma_img = self._gamma_correct(gray, self.GAMMA)
        clahe_img = self._clahe.apply(gamma_img)
        
        variants = [("gray", gamma_img), ("clahe", clahe_img)]
        
        best = None
        best_score = (-1, -1.0)

        for dict_name in self.ACTIVE_DICTS:
            if dict_name not in self._detectors:
                continue
            detector = self._detectors[dict_name]

            for _, variant in variants:
                for scale in self.DETECTION_SCALES:
                    img = variant
                    if scale != 1.0:
                        img = cv2.resize(variant, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

                    corners, ids, _ = detector.detectMarkers(img)
                    if ids is None or len(ids) == 0:
                        continue

                    if scale != 1.0:
                        inv = 1.0 / scale
                        for c in corners:
                            c[0][:, 0] *= inv
                            c[0][:, 1] *= inv

                    merged = self._merge_unique(corners, ids)
                    if not merged:
                        continue

                    score = (len(merged), float(sum(cv2.arcLength(c.astype(np.float32), True) for c in merged.values())))
                    if score > best_score:
                        best_score = score
                        best = (dict_name, merged)
        return best

    def detect(self, frame_bgr, camera_matrix, dist_coeffs=None):
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        best = self._detect_best(gray)

        if best is None:
            self._clear_last()
            return None, [], {}

        dict_name, merged = best
        self._last_dict_name = dict_name
        self._last_ids = sorted(merged.keys())
        self._last_detected_corners = merged
        self._last_corners = {mid: cnr for mid, cnr in merged.items() if mid in self._marker_centers_3d}

        centers = [np.mean(c, axis=0) for c in self._last_detected_corners.values()]
        self._last_ring_center_px = tuple(np.mean(centers, axis=0).astype(int)) if centers else None

        if not self._last_corners:
            self._last_distance = None
            self._last_tvec = None
            return None, self._last_ids, {}

        obj_pts, img_pts = [], []
        h = MARKER_SIZE_CM / 2.0
        for mid, cnr in self._last_corners.items():
            c3d = self._marker_centers_3d[mid]
            obj_pts.append(np.array([c3d + [-h, -h, 0], c3d + [h, -h, 0], c3d + [h, h, 0], c3d + [-h, h, 0]]))
            img_pts.append(cnr.astype(np.float64))

        dist = dist_coeffs if dist_coeffs is not None else np.zeros((5, 1), dtype=np.float64)
        method = cv2.SOLVEPNP_IPPE_SQUARE if len(self._last_corners) == 1 else cv2.SOLVEPNP_ITERATIVE
        obj = np.vstack(obj_pts)
        img = np.vstack(img_pts)

        if len(self._last_corners) >= 2:
            success, rvec, tvec, _ = cv2.solvePnPRansac(obj, img, camera_matrix, dist, flags=cv2.SOLVEPNP_ITERATIVE)
        else:
            success, rvec, tvec = cv2.solvePnP(obj, img, camera_matrix, dist, flags=method)

        if not success:
            self._last_distance = None
            self._last_tvec = None
            return None, self._last_ids, self._last_corners

        self._last_distance = float(np.linalg.norm(tvec))
        self._last_tvec = tvec
        return (float(tvec[0][0]), float(tvec[1][0]), float(tvec[2][0])), self._last_ids, self._last_corners

    def draw_markers(self, frame):
        n_markers = len(self._last_detected_corners)
        n_known = len(self._last_corners)

        for mid, pts in self._last_detected_corners.items():
            p = pts.astype(int)
            color = (0, 255, 0) if mid in self._marker_centers_3d else (80, 200, 255)
            cv2.polylines(frame, [p], True, color, 2)
            center = np.mean(p, axis=0).astype(int)
            cv2.putText(frame, f"#{mid}", (center[0] - 10, center[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        if self._last_ring_center_px is not None:
            cv2.drawMarker(frame, self._last_ring_center_px, (0, 255, 255), cv2.MARKER_CROSS, 26, 2)

        dist_txt = f"{self._last_distance:.0f}cm" if self._last_distance else "-"
        hud_text = f"ArUco: {n_markers} seen ({n_known} known) | {dist_txt}"
        cv2.putText(frame, hud_text, (frame.shape[1] - 380, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        return frame
