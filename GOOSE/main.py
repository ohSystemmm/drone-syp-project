import os
import sys
# Set environment variables to suppress OpenCV/FFmpeg noisy UDP decoding warnings
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "loglevel;quiet"
os.environ["OPENCV_LOG_LEVEL"] = "FATAL"

import pygame
import cv2
import numpy as np
import argparse
import threading
import time
import copy
import datetime
import logging
import math
from logging.handlers import RotatingFileHandler

# djitellopy uses PyAV for video decoding. PyAV directly wraps libavcodec.
# We must silence libavcodec logging to stop the "left block unavailable" spam.
import av
av.logging.set_level(av.logging.FATAL)

from core.drone import DroneController
from vision.detector import ObjectDetector
from core.autopilot import AutoPilot
from core.calibration import CalibrationMode
from vision.sampler import HybridSampler
from vision.position_estimator import PositionEstimator, PoseEstimate
from vision.room_3d_view import Room3DView
from core.joystick import JoystickHandler
from core.flight_recorder import FlightRecorder
from core.joystick_calibration import JoystickCalibrationMode
from core.control_center import ControlCenterUI
from core.telemetry import TelemetryService
from core.drone_registry import DroneRegistry

# IMPORTANT: This must come AFTER imports. djitellopy sets LOGGER.setLevel(logging.INFO)
# as a class-level attribute when the Tello class is defined, which overwrites any
# setLevel call made before the import. Placing it here ensures it takes effect.
logging.getLogger('djitellopy').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def setup_logging():
    logs_dir = os.path.join("GOOSE", "logs") if os.path.exists("GOOSE") else "logs"
    os.makedirs(logs_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(logs_dir, f"goose_debug_{ts}.log")

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(log_path, maxBytes=8 * 1024 * 1024, backupCount=4, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    logger.info("Debug logging initialized: %s", log_path)
    return log_path

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 720
SPEED = 100
YAW_SPEED = 100
UD_SPEED = 100 

class VisionWorker(threading.Thread):
    def __init__(self, controller, detector, calibration=None, autopilot=None):
        super().__init__()
        self.controller = controller
        self.detector = detector
        self.calibration = calibration     # <-- Store Calibration
        self.autopilot = autopilot         # <-- Store Autopilot
        self.running = True
        self._lock = threading.Lock()
        self._detections =[]
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
        self.detection_enabled = True  # 5.6: can be toggled off

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
        # Autopilot has TRACKING_MIN_DIST=15, PUNCH_DISTANCE=80, ALIGN_DISTANCE=100, TRACKING_MAX_DIST=400
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
            # Reject tiny/degenerate detections that are almost always noise.
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
            # Keep candidate selection permissive. Strict gating is applied later
            # before control commands are allowed.
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
            return list(self._detections)  # Return a copy

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
        processed_count = 0
        none_count = 0
        while self.running:
            frame = self.controller.get_frame()
            if frame is not None and frame.size > 0:
                self._frame_counter += 1
                none_count = 0
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

def init_window():
    pygame.init()
    win = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Tello Control Center + AI Vision (Async)")
    return win

def get_keyboard_input(controller, current_threshold, autopilot=None):
    lr, fb, ud, yv = 0, 0, 0, 0
    new_threshold = current_threshold
    manual_input = False
    
    keys = pygame.key.get_pressed()

    # Movement
    if keys[pygame.K_LEFT] or keys[pygame.K_a]: lr = -SPEED; manual_input = True
    elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: lr = SPEED; manual_input = True

    if keys[pygame.K_UP] or keys[pygame.K_w]: fb = SPEED; manual_input = True
    elif keys[pygame.K_DOWN] or keys[pygame.K_s]: fb = -SPEED; manual_input = True

    # Altitude
    if keys[pygame.K_SPACE]: ud = UD_SPEED; manual_input = True
    elif keys[pygame.K_LSHIFT]: ud = -UD_SPEED; manual_input = True

    # Rotation
    if keys[pygame.K_q]: yv = -YAW_SPEED; manual_input = True
    elif keys[pygame.K_e]: yv = YAW_SPEED; manual_input = True

    if manual_input and autopilot:
        autopilot.disengage()

    # Emergency Kill Switch
    if keys[pygame.K_ESCAPE]: 
        print("!!! EMERGENCY STOP INITIATED !!!")
        if autopilot:
            autopilot.disengage()
        controller.emergency()

    # Threshold Adjustment
    if keys[pygame.K_LEFTBRACKET]: new_threshold = max(0.1, current_threshold - 0.01)
    if keys[pygame.K_RIGHTBRACKET]: new_threshold = min(1.0, current_threshold + 0.01)

    return [lr, fb, ud, yv], new_threshold

def draw_osd_text(surface, text, position, font_obj, text_color=(255, 255, 255), bg_color=(0, 0, 0, 150)):
    text_surf = font_obj.render(text, True, text_color)
    x, y = position
    bg_rect = pygame.Rect(x - 5, y - 5, text_surf.get_width() + 10, text_surf.get_height() + 10)
    shape_surf = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
    pygame.draw.rect(shape_surf, bg_color, shape_surf.get_rect(), border_radius=5)
    surface.blit(shape_surf, bg_rect.topleft)
    surface.blit(text_surf, position)

def draw_detections(frame, detections):
    for d in detections:
        box = d['box']
        x1, y1, x2, y2 = box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cx, cy = d['center']
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1) 
        track_id = d.get('track_id')
        id_text = f"ID: {track_id} " if track_id is not None else ""
        label = f"{id_text}{d['name']} {d['conf']:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return frame

def parse_args():
    parser = argparse.ArgumentParser(description='Tello Drone Control with YOLO')
    parser.add_argument('--model', type=str, choices=['onnx', 'pt', 'auto'], default='auto',
                        help='Force model type: onnx or pt')
    parser.add_argument('--ip', type=str, default='192.168.10.1', help='Tello IP address')
    parser.add_argument('--port', type=int, default=8889, help='Tello UDP port')
    return parser.parse_args()

def main():
    log_path = setup_logging()
    logger.info("Starting main loop")
    args = parse_args()
    controller = DroneController()
    
    if not controller.connect(host=args.ip, port=args.port):
        logger.critical("Failed to connect to drone. Exiting.")
        return

    # Drone Registry — track IPs and names
    drone_registry = DroneRegistry()
    drone_registry.add_or_update(args.ip)
    drone_name = drone_registry.get_name(args.ip)

    # Telemetry Service — poll sensors in background
    telemetry = TelemetryService()
    telemetry.start(controller.tello, ip_address=args.ip, drone_name=drone_name)

    # Model Loading
    model_dir = "GOOSE/assets/models"
    if not os.path.exists(model_dir): model_dir = "assets/models"
    onnx_path = os.path.join(model_dir, "targetModel.onnx")
    pt_path = os.path.join(model_dir, "targetModel.pt")
    
    selected_path = None
    if args.model == 'onnx':
        if os.path.exists(onnx_path): selected_path = onnx_path
    elif args.model == 'pt':
        if os.path.exists(pt_path): selected_path = pt_path
    else: # auto
        if os.path.exists(onnx_path): selected_path = onnx_path
        elif os.path.exists(pt_path): selected_path = pt_path

    autopilot = AutoPilot()
    room_view = Room3DView()
    flight_recorder = FlightRecorder()
    calibration = CalibrationMode()
    calibration.aruco_calibrator = None
    detection_enabled = True  # 5.6: Detection toggle

    detector = None
    vision_thread = None

    if selected_path:
        logger.info("Loading model: %s", selected_path)
        detector = ObjectDetector(selected_path)
        detector.load_model()
        vision_thread = VisionWorker(controller, detector, calibration, autopilot)
        vision_thread.start()
        logger.info("VisionWorker thread started.")
    else:
        logger.warning("Vision disabled (No model found at specified paths).")

    # Setup Video Recording
    rec_dir = "GOOSE/recordings"
    if not os.path.exists("GOOSE"): rec_dir = "recordings" 
    if not os.path.exists(rec_dir): os.makedirs(rec_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = os.path.join(rec_dir, f"flight_{timestamp}.mp4")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_writer = cv2.VideoWriter(video_filename, fourcc, 30.0, (960, 720))
    
    if not out_writer.isOpened():
        logger.critical("Could not initialize VideoWriter at %s", video_filename)
    else:
        logger.info("Recording video to: %s", video_filename)

    win = init_window()
    font = pygame.font.SysFont(None, 24)
    mode_font = pygame.font.SysFont(None, 36)
    conf_threshold = 0.25
    swap_rb = False
    
    # Joystick Setup
    joy_handler = JoystickHandler()
    joy_calib = JoystickCalibrationMode(joy_handler)
    cc_ui = ControlCenterUI(joy_handler=joy_handler)
    
    # Data Factory Setup
    from core.data_factory import DataFactory
    data_factory = DataFactory(aruco_cal=None, enable_aruco=False)
    data_collection_active = False

    # Load saved calibration if available
    saved_scale = CalibrationMode.load_z_scale()
    if saved_scale is not None and vision_thread:
        vision_thread.pose_estimator.Z_SCALE = saved_scale

    _last_main_frame_id = None
    _last_main_debug_time = 0.0
    _last_auto_rc = [0, 0, 0, 0]
    _last_autopilot_phase = None  # Track phase transitions for camera switching

    run = True
    try:
        while run:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run = False
                
                if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                    cc_ui.toggle()
                    continue
                
                action = cc_ui.handle_event(event)

                if action:
                    logger.info("UI action: %s", action)
                    if action == "takeoff":
                        try:
                            controller.takeoff()
                            flight_recorder.record_event("takeoff")
                            telemetry.notify_takeoff()
                        except Exception:
                            logger.exception("Takeoff Error")
                    elif action == "land":
                        try:
                            controller.land()
                            flight_recorder.record_event("land")
                            telemetry.notify_land()
                        except Exception:
                            logger.exception("Land Error")
                    elif action == "emergency":
                        if autopilot: autopilot.disengage()
                        controller.emergency()
                    elif action == "flip_f": controller.flip('f')
                    elif action == "flip_b": controller.flip('b')
                    elif action == "flip_l": controller.flip('l')
                    elif action == "flip_r": controller.flip('r')
                    elif action == "auto_toggle":
                        autopilot.toggle()
                    elif action == "calib_vis":
                        calibration.toggle(ground_mode=False)
                    elif action == "calib_stk":
                        joy_calib.toggle()
                    elif action == "rec_calib":
                        pose = vision_thread.latest_pose if vision_thread else None
                        if calibration.active:
                            calibration.record_sample(pose)
                    elif action == "cycle_joy":
                        joy_handler.cycle_joystick()
                
                elif event.type == pygame.KEYDOWN and not cc_ui.waiting_for_input:
                    if event.key == pygame.K_F8:
                        data_collection_active = not data_collection_active
                        logger.info("[Main] DATA COLLECTION: %s", 'ACTIVE' if data_collection_active else 'OFF')
                    elif event.key == pygame.K_F9:
                        if flight_recorder.is_recording:
                            path = flight_recorder.stop_recording()
                            if path:
                                print(f"[FlightRecorder] Saved: {path}")
                        else:
                            if flight_recorder.is_replaying:
                                flight_recorder.stop_replay()
                            flight_recorder.start_recording()
                            print("[FlightRecorder] Recording started...")
                    elif event.key == pygame.K_F10:
                        if flight_recorder.is_replaying:
                            flight_recorder.stop_replay()
                            print("[FlightRecorder] Replay stopped.")
                        elif not flight_recorder.is_recording:
                            if flight_recorder.load_latest():
                                flight_recorder.start_replay()
                                print("[FlightRecorder] Replay started!")
                            else:
                                print("[FlightRecorder] No recordings found.")
                    elif event.key == pygame.K_F6:
                        calibration.toggle(ground_mode=True)
                    elif event.key == pygame.K_SPACE and calibration.active:
                        pose = vision_thread.latest_pose if vision_thread else None
                        calibration.record_sample(pose)
                    elif event.key == pygame.K_c:
                        swap_rb = not swap_rb
                    elif event.key == pygame.K_F11:
                        detection_enabled = not detection_enabled
                        state = "ON" if detection_enabled else "OFF"
                        print(f"[Main] Object Detection: {state}")
                        logger.info("[Main] Detection toggle: %s", state)

            if vision_thread:
                vision_thread.conf_threshold = conf_threshold
                vision_thread.detection_enabled = detection_enabled

            current_frame = controller.get_frame()

            if data_collection_active and autopilot.active:
                data_factory.update_jitter(time.time())
                # Perform the data collection
                if current_frame is not None:
                    pose = vision_thread.latest_pose if vision_thread else None
                    data_factory.collect(current_frame, pose, autopilot)

            if cc_ui.active:
                rc_vals = [0, 0, 0, 0]
                joy_rc = [0, 0, 0, 0]
            else:
                rc_vals, conf_threshold = get_keyboard_input(controller, conf_threshold, autopilot)
                joy_rc = joy_handler.get_rc_inputs()

            if joy_calib.active:
                joy_calib.update()

            is_new_frame = current_frame is not None and id(current_frame) != _last_main_frame_id

            if is_new_frame:
                _last_main_frame_id = id(current_frame)
            
            
            # --- THE FIX: Capture state ONCE per loop to prevent race conditions ---
            current_pose = vision_thread.latest_pose if vision_thread else None
            current_detections = vision_thread.latest_detections if vision_thread else []
            current_bbox_center = current_detections[0]['center'] if current_detections else None
            current_bbox_ratio = None
            if current_detections:
                b = current_detections[0]['box']
                bw, bh = b[2] - b[0], b[3] - b[1]
                # Only trust bbox ratio when the entire ring is in-frame (not clipped at edges)
                bbox_fully_visible = b[0] > 20 and b[1] > 20 and b[2] < 940 and b[3] < 700
                if bh > 0 and bbox_fully_visible:
                    current_bbox_ratio = bw / bh

            now_dbg = time.monotonic()
            if now_dbg - _last_main_debug_time > 1.0:
                logger.debug(
                    "[Main] ap_active=%s phase=%s dets=%d pose=%s bbox=%s data_collect=%s",
                    autopilot.active,
                    autopilot.phase,
                    len(current_detections),
                    f"x={current_pose.x_cm:.1f} y={current_pose.y_cm:.1f} z={current_pose.z_cm:.1f} c={current_pose.confidence:.2f}" if current_pose else "None",
                    current_bbox_center,
                    data_collection_active,
                )
                _last_main_debug_time = now_dbg

            # --- Flight Replay Override ---
            if flight_recorder.is_replaying:
                replay_evt = flight_recorder.get_replay_event()
                if replay_evt == "takeoff":
                    controller.takeoff()
                elif replay_evt == "land":
                    controller.land()

                replay_rc = flight_recorder.get_replay_rc()
                if replay_rc is not None:
                    controller.send_rc_control(*replay_rc)
                    flight_recorder.record_rc(*replay_rc)  # no-op if not recording
                else:
                    controller.send_rc_control(0, 0, 0, 0)
            elif autopilot.active and vision_thread and not calibration.active and not joy_calib.active:
                # --- Camera switching for downward camera phases ---
                if autopilot.phase != _last_autopilot_phase:
                    if autopilot.phase == "CENTER":
                        logger.info("[Main] Phase transition to CENTER — switching to downward camera")
                        controller.set_camera_direction(1)  # 1 = downward camera
                    elif _last_autopilot_phase == "CENTER" or _last_autopilot_phase == "DESCENT":
                        if autopilot.phase == "DONE":
                            logger.info("[Main] Phase transition to DONE — switching back to forward camera")
                            controller.set_camera_direction(0)  # 0 = forward camera
                    _last_autopilot_phase = autopilot.phase

                # Only compute PID when we have a new frame to prevent derivative spikes
                if is_new_frame:
                    _last_auto_rc = autopilot.compute(current_pose, bbox_center=current_bbox_center, bbox_ratio=current_bbox_ratio)
                controller.send_rc_control(*_last_auto_rc)
                flight_recorder.record_rc(*_last_auto_rc)
            elif not calibration.active and not joy_calib.active:
                final_rc = [0, 0, 0, 0]
                for i in range(4):
                    final_rc[i] = rc_vals[i] if rc_vals[i] != 0 else joy_rc[i]
                controller.send_rc_control(*final_rc)
                flight_recorder.record_rc(*final_rc)
            else:
                controller.send_rc_control(0, 0, 0, 0)

            if calibration.active and vision_thread:
                calibration._current_z_scale = vision_thread.pose_estimator.Z_SCALE
                # Use current_pose here
                if calibration.feed_pose(current_pose):
                    if calibration.computed_scale is not None:
                        vision_thread.pose_estimator.Z_SCALE = calibration.computed_scale
                    calibration.state = calibration.STATE_INACTIVE
            
            frame = current_frame

            if frame is not None:
                display_frame = frame.copy() 
                # Use captured detections
                display_frame = draw_detections(display_frame, current_detections)
                if current_pose and vision_thread:
                    # Use captured pose
                    display_frame = vision_thread.pose_estimator.draw_estimate(display_frame, current_pose)
                
                    
                if is_new_frame:
                    try:
                        record_frame = cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR)
                        out_writer.write(record_frame)
                    except Exception:
                        logger.exception("Recording Error")

                if swap_rb:
                    display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
                display_frame = np.rot90(display_frame)
                display_frame = np.flipud(display_frame)
                surf = pygame.surfarray.make_surface(display_frame)
                if (surf.get_width() != SCREEN_WIDTH) or (surf.get_height() != SCREEN_HEIGHT):
                    surf = pygame.transform.scale(surf, (SCREEN_WIDTH, SCREEN_HEIGHT))
                win.blit(surf, (0, 0))

                status_text = "CONNECTED" if controller.is_connected else "DISCONNECTED"
                status_color = (50, 255, 50) if controller.is_connected else (255, 50, 50)
                ip_label = f" ({telemetry.drone_name})" if telemetry.drone_name else ""
                draw_osd_text(win, f"DRONE: {status_text} | {args.ip}{ip_label}", (15, 15), font, status_color)
                
                if autopilot.active:
                    phase = autopilot.phase
                    mode_text = f"AUTO: {phase}"
                    mode_color = (255, 255, 0)
                else:
                    mode_text = "MANUAL"; mode_color = (200, 200, 200)
                
                mode_w = mode_font.size(mode_text)[0]
                draw_osd_text(win, mode_text, (SCREEN_WIDTH - mode_w - 15, 15), mode_font, mode_color)

                shortcuts = "SPACE: Lock | P: Auto | F9: Rec | F10: Play | ESC: KILL"
                short_w = font.size(shortcuts)[0]
                draw_osd_text(win, shortcuts, (SCREEN_WIDTH - short_w - 15, SCREEN_HEIGHT - 35), font, (255, 200, 100))

                # Flight Recorder OSD
                if flight_recorder.is_recording:
                    rec_dur = flight_recorder.recording_duration
                    rec_text = f"REC ● {rec_dur:.1f}s"
                    draw_osd_text(win, rec_text, (15, 45), font, (255, 50, 50))
                elif flight_recorder.is_replaying:
                    elapsed, total = flight_recorder.replay_progress
                    rep_text = f"REPLAY ▶ {elapsed:.1f}/{total:.1f}s"
                    draw_osd_text(win, rep_text, (15, 45), font, (50, 200, 255))

                # Detection toggle indicator
                if not detection_enabled:
                    draw_osd_text(win, "DETECT: OFF", (15, 70), font, (180, 180, 50))

                # Telemetry OSD (right side, below mode)
                telem_lines = telemetry.get_osd_lines()
                telem_font = pygame.font.SysFont(None, 22)
                for i, line in enumerate(telem_lines):
                    tw = telem_font.size(line)[0]
                    draw_osd_text(win, line, (SCREEN_WIDTH - tw - 15, 45 + i * 20), telem_font, (150, 220, 255))

                if joy_handler.is_connected and not joy_calib.active:
                    raw_sticks = joy_handler.get_raw_sticks()
                    def draw_sticks(surface, sticks, x, y, size=80):
                        roll, pitch, throttle, yaw = sticks
                        surface.fill((0, 0, 0, 150), pygame.Rect(x, y, size, size))
                        surface.fill((0, 0, 0, 150), pygame.Rect(x + size + 20, y, size, size))
                        lx = x + size//2 + int(yaw * size//2)
                        ly = y + size//2 - int(throttle * size//2)
                        rx = x + size + 20 + size//2 + int(roll * size//2)
                        ry = y + size//2 + int(pitch * size//2)
                        pygame.draw.circle(surface, (255, 255, 255), (lx, ly), 6)
                        pygame.draw.circle(surface, (255, 255, 255), (rx, ry), 6)
                    draw_sticks(win, raw_sticks, SCREEN_WIDTH//2 - 90, SCREEN_HEIGHT - 100)

            else:
                win.fill((0, 0, 0))
                text = font.render("Waiting for video stream...", True, (255, 255, 255))
                win.blit(text, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2))

            try:
                # Use current_pose instead of vision_thread.latest_pose
                room_view.update(current_pose, autopilot=autopilot, debug_frame=frame, is_flying=controller.is_flying)
            except KeyboardInterrupt:
                raise
            except Exception:
                logger.exception("RoomView Error")
            cv2.waitKey(1)
            cc_ui.draw(win)
            pygame.display.update()
            pygame.time.delay(16)
    except KeyboardInterrupt:
        logger.info("[Main] Keyboard interrupt received — shutting down.")
    finally:
        if vision_thread:
            vision_thread.stop()
            try:
                vision_thread.join(timeout=2.0)
            except KeyboardInterrupt:
                logger.info("[Main] Keyboard interrupt while waiting for VisionWorker shutdown.")
            if vision_thread.is_alive():
                logger.warning("[Main] VisionWorker did not exit within 2.0s")
        if out_writer:
            try:
                out_writer.release()
            except KeyboardInterrupt:
                logger.info("[Main] Keyboard interrupt during video writer shutdown.")
        try:
            controller.cleanup()
        except KeyboardInterrupt:
            logger.info("[Main] Keyboard interrupt during cleanup — forcing final state reset.")
            controller.is_connected = False
            controller.frame_reader = None
        except Exception:
            logger.exception("Cleanup Error")
        room_view.close()
        telemetry.stop()
        pygame.quit()
        logger.info("Shutdown complete. Log file: %s", log_path)

if __name__ == "__main__":
    main()

