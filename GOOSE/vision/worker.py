import threading
import time
import math
import logging
import cv2
import numpy as np

from vision.sampler import HybridSampler
from vision.position_estimator import PositionEstimator

logger = logging.getLogger(__name__)

class VisionWorker(threading.Thread):
    def __init__(self, controller, detector, calibration=None, autopilot=None):
        super().__init__()
        self.controller = controller
        self.detector = detector
        self.calibration = calibration     # <-- Store Calibration
        self.autopilot = autopilot         # <-- Store Autopilot
        self.running = True
        self._lock = threading.Lock()
        self._detections = []
        self._pose = None
        self.conf_threshold = 0.5
        self.sampler = HybridSampler()
        self.pose_estimator = PositionEstimator()
        self.daemon = True
        self._primary_center = None
        self._primary_miss_streak = 0
        self._fallback_min_conf = 0.12
        self._max_candidates_for_pose = 4
        self._frame_counter = 0
        self._last_vision_log_time = 0.0
        self._last_target_info_time = 0.0
        self._control_min_conf = 0.30
        self.detection_enabled = True
        self.is_paused = False

    def _is_pose_control_valid(self, det, est):
        """Minimal gating — only reject truly unusable poses."""
        x1, y1, x2, y2 = det['box']
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        area_ratio = float(w * h) / float(960 * 720)

        if area_ratio < 0.0035:
            return False, "box_too_small"
        if est is None or est.is_coasted:
            return False, "pose_missing"
        if est.confidence < self._control_min_conf:
            return False, "pose_low_conf"
        # Relaxed range to allow very close approaches (down to ~8cm) and far tracking (up to 450cm)
        if est.z_cm < 8 or est.z_cm > 450:
            return False, "pose_range"
        return True, "ok"

    def _select_primary_detection(self, detections):
        """Select a single stable target using confidence, box area, and temporal proximity."""
        filtered = []
        for d in detections:
            x1, y1, x2, y2 = d['box']
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            area_ratio = float(w * h) / float(960 * 720)
            if w < 24 or h < 24 or area_ratio < 0.002:
                continue
            filtered.append(d)

        detections = filtered
        if not detections:
            self._primary_miss_streak += 1
            if self._primary_miss_streak > 12:
                self._primary_center = None
            return None

        self._primary_miss_streak = 0
        if self._primary_center is None:
            best = max(detections, key=lambda d: d['conf'])
            self._primary_center = best['center']
            return best

        frame_diag = math.hypot(960.0, 720.0)

        def _score(det):
            x1, y1, x2, y2 = det['box']
            area = max(1.0, float((x2 - x1) * (y2 - y1)))
            area_term = min(1.0, area / 120000.0)
            dist = math.hypot(det['center'][0] - self._primary_center[0], det['center'][1] - self._primary_center[1])
            dist_term = min(1.0, dist / frame_diag)
            return (1.20 * det['conf']) + (0.30 * area_term) - (0.65 * dist_term)

        best = max(detections, key=_score)
        self._primary_center = best['center']
        return best

    def _select_pose_validated_target(self, frame_bgr, detections):
        """Pick target by mask geometry quality, not just detector confidence."""
        if not detections:
            return None, None

        ranked = sorted(detections, key=lambda d: d['conf'], reverse=True)[:self._max_candidates_for_pose]
        frame_diag = math.hypot(960.0, 720.0)

        best_det = None
        best_pose = None
        best_score = -1e9

        for d in ranked:
            est = self.pose_estimator.estimate(frame_bgr, roi_box=d['box'])
            if est is None or est.is_coasted:
                continue
            if est.z_cm < 30 or est.z_cm > 450:
                continue
            if est.confidence < 0.20:
                continue

            dist_term = 0.0
            if self._primary_center is not None:
                px_dist = math.hypot(d['center'][0] - self._primary_center[0], d['center'][1] - self._primary_center[1])
                dist_term = min(1.0, px_dist / frame_diag)

            score = (1.60 * est.confidence) + (0.40 * d['conf']) - (0.35 * dist_term)
            if score > best_score:
                best_score = score
                best_det = d
                best_pose = est

        return best_det, best_pose

    @property
    def latest_detections(self):
        with self._lock:
            return list(self._detections)

    @latest_detections.setter
    def latest_detections(self, value):
        with self._lock:
            self._detections = value

    @property
    def latest_pose(self):
        with self._lock:
            return self._pose

    @latest_pose.setter
    def latest_pose(self, value):
        with self._lock:
            self._pose = value

    def run(self):
        logger.info("Vision Worker Started (Hybrid Sampling Active)")
        while self.running:
            if self.is_paused:
                self.latest_detections = []
                self.latest_pose = None
                time.sleep(0.1)
                continue
            frame = self.controller.get_frame()
            if frame is not None and frame.size > 0:
                self._frame_counter += 1
                if self.detector and self.detection_enabled:
                    try:
                        sampling_threshold = min(0.10, self.conf_threshold)
                        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                        _, all_detections = self.detector.detect(frame_bgr, conf_threshold=sampling_threshold, draw_center=False)
                        display_dets = [d for d in all_detections if d['conf'] >= self.conf_threshold]
                        candidate_dets = display_dets if display_dets else [d for d in all_detections if d['conf'] >= self._fallback_min_conf]

                        primary_det, pose_from_primary = self._select_pose_validated_target(frame_bgr, candidate_dets)
                        if primary_det is None:
                            primary_det = self._select_primary_detection(candidate_dets)

                        if primary_det:
                            self.latest_detections = [primary_det]
                            if pose_from_primary is None:
                                pose_from_primary = self.pose_estimator.estimate(frame_bgr, roi_box=primary_det['box'])

                            control_ok = False
                            control_reason = "pose_missing"
                            if pose_from_primary is not None:
                                control_ok, control_reason = self._is_pose_control_valid(primary_det, pose_from_primary)

                            if control_ok:
                                self.latest_pose = pose_from_primary
                            else:
                                self.latest_pose = None

                            now_target = time.monotonic()
                            if now_target - self._last_target_info_time > 0.6:
                                box = primary_det['box']
                                if self.latest_pose is not None:
                                    pose_state = f"control(c={self.latest_pose.confidence:.2f},z={self.latest_pose.z_cm:.1f})"
                                else:
                                    pose_state = f"rejected({control_reason})"
                                logger.info(
                                    "[Vision|Target] center=%s box=[%d,%d,%d,%d] conf=%.2f all=%d pass=%d pose=%s",
                                    primary_det['center'],
                                    box[0],
                                    box[1],
                                    box[2],
                                    box[3],
                                    primary_det['conf'],
                                    len(all_detections),
                                    len(display_dets),
                                    pose_state,
                                )
                                self._last_target_info_time = now_target
                        else:
                            self.latest_detections = []
                            self.latest_pose = None
                            now_target = time.monotonic()
                            if now_target - self._last_target_info_time > 1.0:
                                logger.info("[Vision|Target] no target selected (all=%d pass=%d)", len(all_detections), len(display_dets))
                                self._last_target_info_time = now_target

                        now = time.monotonic()
                        if now - self._last_vision_log_time > 1.0:
                            pose = self.latest_pose
                            logger.debug(
                                "[Vision] frame=%d all=%d display=%d primary=%s conf_thr=%.2f pose=%s",
                                self._frame_counter,
                                len(all_detections),
                                len(display_dets),
                                primary_det['center'] if primary_det else None,
                                self.conf_threshold,
                                f"x={pose.x_cm:.1f} y={pose.y_cm:.1f} z={pose.z_cm:.1f} c={pose.confidence:.2f}" if pose else "None",
                            )
                            self._last_vision_log_time = now

                        self.sampler.process_frame(frame, all_detections)
                    except Exception:
                        logger.exception("Vision Error")
            else:
                time.sleep(0.01)
        self.sampler.close()

    def stop(self):
        self.running = False
