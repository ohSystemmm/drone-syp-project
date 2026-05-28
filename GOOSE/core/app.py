import os
import sys
import threading
import time
import datetime
import logging
import cv2
import numpy as np
import pygame

from core.drone import DroneController
from vision.detector import ObjectDetector
from core.autopilot import AutoPilot
from core.calibration import CalibrationMode
from vision.worker import VisionWorker
from vision.room_3d_view import Room3DView
from core.joystick import JoystickHandler
from core.flight_recorder import FlightRecorder
from core.joystick_calibration import JoystickCalibrationMode
from core.control_center import ControlCenterUI
from core.telemetry import TelemetryService
from core.drone_registry import DroneRegistry
from core.data_factory import DataFactory
from ui import draw_osd_text, draw_detections, draw_sticks

logger = logging.getLogger(__name__)

class GooseApp:
    SCREEN_WIDTH = 960
    SCREEN_HEIGHT = 720
    SPEED = 100
    YAW_SPEED = 100
    UD_SPEED = 100

    def __init__(self, args):
        self.args = args
        self.controller = DroneController()
        self.drone_registry = DroneRegistry()
        self.telemetry = TelemetryService()
        self.autopilot = AutoPilot()
        self.room_view = Room3DView()
        self.flight_recorder = FlightRecorder()
        self.calibration = CalibrationMode()
        self.joy_handler = JoystickHandler()
        self.joy_calib = JoystickCalibrationMode(self.joy_handler)
        self.cc_ui = ControlCenterUI(joy_handler=self.joy_handler)
        self.data_factory = DataFactory(aruco_cal=None, enable_aruco=False)
        
        self.vision_thread = None
        self.detector = None
        self.out_writer = None
        self.fallback_frame = None
        
        self.conf_threshold = 0.25
        self.detection_enabled = True
        self.data_collection_active = False
        self.swap_rb = False
        self.run = True
        
        self._last_main_frame_id = None
        self._last_main_debug_time = 0.0
        self._last_auto_rc = [0, 0, 0, 0]

    def _init_pygame(self):
        pygame.init()
        self.win = pygame.display.set_mode((self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        pygame.display.set_caption("Tello Control Center + AI Vision (Async)")
        self.font = pygame.font.SysFont(None, 24)
        self.mode_font = pygame.font.SysFont(None, 36)
        self.telem_font = pygame.font.SysFont(None, 22)

    def _setup_video_recording(self):
        rec_dir = "GOOSE/recordings" if os.path.exists("GOOSE") else "recordings"
        os.makedirs(rec_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        video_filename = os.path.join(rec_dir, f"flight_{timestamp}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.out_writer = cv2.VideoWriter(video_filename, fourcc, 30.0, (960, 720))
        if not self.out_writer.isOpened():
            logger.critical("Could not initialize VideoWriter at %s", video_filename)
        else:
            logger.info("Recording video to: %s", video_filename)

    def _load_model(self):
        model_dir = "GOOSE/assets/models" if os.path.exists("GOOSE") else "assets/models"
        onnx_path = os.path.join(model_dir, "targetModel.onnx")
        pt_path = os.path.join(model_dir, "targetModel.pt")

        selected_path = None
        if self.args.model == 'onnx' and os.path.exists(onnx_path):
            selected_path = onnx_path
        elif self.args.model == 'pt' and os.path.exists(pt_path):
            selected_path = pt_path
        else:
            if os.path.exists(onnx_path): selected_path = onnx_path
            elif os.path.exists(pt_path): selected_path = pt_path

        if selected_path:
            logger.info("Loading model: %s", selected_path)
            self.detector = ObjectDetector(selected_path)
            self.detector.load_model()
            self.vision_thread = VisionWorker(self.controller, self.detector, self.calibration, self.autopilot)
            self.vision_thread.start()
            
            saved_scale = CalibrationMode.load_z_scale()
            if saved_scale is not None:
                self.vision_thread.pose_estimator.Z_SCALE = saved_scale
        else:
            logger.warning("Vision disabled (No model found).")

    def _load_fallback_frame(self):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        fallback_paths = [
            os.path.join(base_dir, "ui", "example-background", "example-background.png"),
            os.path.join(base_dir, "ui", "example-background.png")
        ]
        for p in fallback_paths:
            if os.path.exists(p):
                img = cv2.imread(p)
                if img is not None:
                    self.fallback_frame = cv2.resize(img, (self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
                    break

    def _handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.run = False
            
            if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
                self.cc_ui.toggle()
                continue
            
            action = self.cc_ui.handle_event(event)
            if action:
                self._handle_ui_action(action)
            elif event.type == pygame.KEYDOWN and not self.cc_ui.waiting_for_input:
                self._handle_keyboard_shortcuts(event)

    def _handle_ui_action(self, action):
        logger.info("UI action: %s", action)
        if action == "takeoff":
            try:
                self.controller.takeoff()
                self.flight_recorder.record_event("takeoff")
                self.telemetry.notify_takeoff()
            except Exception: logger.exception("Takeoff Error")
        elif action == "land":
            try:
                self.controller.land()
                self.flight_recorder.record_event("land")
                self.telemetry.notify_land()
            except Exception: logger.exception("Land Error")
        elif action == "emergency":
            if self.autopilot: self.autopilot.disengage()
            self.controller.emergency()
        elif action.startswith("flip_"): self.controller.flip(action[-1])
        elif action == "auto_toggle": self.autopilot.toggle()
        elif action == "calib_vis": self.calibration.toggle(ground_mode=False)
        elif action == "calib_stk": self.joy_calib.toggle()
        elif action == "rec_calib":
            pose = self.vision_thread.latest_pose if self.vision_thread else None
            if self.calibration.active: self.calibration.record_sample(pose)
        elif action == "cycle_joy": self.joy_handler.cycle_joystick()

    def _handle_keyboard_shortcuts(self, event):
        if event.key == pygame.K_F8:
            self.data_collection_active = not self.data_collection_active
            logger.info("[Main] DATA COLLECTION: %s", 'ACTIVE' if self.data_collection_active else 'OFF')
        elif event.key == pygame.K_F9:
            if self.flight_recorder.is_recording: self.flight_recorder.stop_recording()
            else: self.flight_recorder.start_recording()
        elif event.key == pygame.K_F12:
            logger.info("[Main] F12: Switching to downward camera")
            self.controller.set_camera_direction(1)
        elif event.key == pygame.K_F10:
            if self.flight_recorder.is_replaying: self.flight_recorder.stop_replay()
            elif not self.flight_recorder.is_recording:
                if self.flight_recorder.load_latest(): self.flight_recorder.start_replay()
        elif event.key == pygame.K_F6: self.calibration.toggle(ground_mode=True)
        elif event.key == pygame.K_SPACE and self.calibration.active:
            pose = self.vision_thread.latest_pose if self.vision_thread else None
            self.calibration.record_sample(pose)
        elif event.key == pygame.K_c: self.swap_rb = not self.swap_rb
        elif event.key == pygame.K_F11:
            self.detection_enabled = not self.detection_enabled
            logger.info("[Main] Detection toggle: %s", "ON" if self.detection_enabled else "OFF")

    def _get_keyboard_movement(self):
        lr, fb, ud, yv = 0, 0, 0, 0
        manual_input = False
        keys = pygame.key.get_pressed()

        if keys[pygame.K_LEFT] or keys[pygame.K_a]: lr = -self.SPEED; manual_input = True
        elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: lr = self.SPEED; manual_input = True
        if keys[pygame.K_UP] or keys[pygame.K_w]: fb = self.SPEED; manual_input = True
        elif keys[pygame.K_DOWN] or keys[pygame.K_s]: fb = -self.SPEED; manual_input = True
        if keys[pygame.K_SPACE]: ud = self.UD_SPEED; manual_input = True
        elif keys[pygame.K_LSHIFT]: ud = -self.UD_SPEED; manual_input = True
        if keys[pygame.K_q]: yv = -self.YAW_SPEED; manual_input = True
        elif keys[pygame.K_e]: yv = self.YAW_SPEED; manual_input = True

        if manual_input and self.autopilot: self.autopilot.disengage()
        if keys[pygame.K_ESCAPE]:
            if self.autopilot: self.autopilot.disengage()
            self.controller.emergency()
        if keys[pygame.K_LEFTBRACKET]: self.conf_threshold = max(0.1, self.conf_threshold - 0.01)
        if keys[pygame.K_RIGHTBRACKET]: self.conf_threshold = min(1.0, self.conf_threshold + 0.01)

        return [lr, fb, ud, yv]

    def start(self):
        if not self.controller.connect(host=self.args.ip, port=self.args.port):
            logger.critical("Failed to connect to drone. Exiting.")
            return

        self.drone_registry.add_or_update(self.args.ip)
        drone_name = self.drone_registry.get_name(self.args.ip)
        self.telemetry.start(self.controller.tello, ip_address=self.args.ip, drone_name=drone_name)

        self._load_model()
        self._load_fallback_frame()
        self._setup_video_recording()
        self._init_pygame()

        try:
            while self.run:
                self._handle_events()
                if self.vision_thread:
                    self.vision_thread.conf_threshold = self.conf_threshold
                    self.vision_thread.detection_enabled = self.detection_enabled

                current_frame = self.controller.get_frame()
                current_pose = self.vision_thread.latest_pose if self.vision_thread else None
                current_detections = self.vision_thread.latest_detections if self.vision_thread else []
                
                is_new_frame = current_frame is not None and id(current_frame) != self._last_main_frame_id
                if is_new_frame: self._last_main_frame_id = id(current_frame)

                if self.data_collection_active and self.autopilot.active and current_frame is not None:
                    self.data_factory.update_jitter(time.time())
                    self.data_factory.collect(current_frame, current_pose, self.autopilot)

                self._update_control(is_new_frame, current_pose, current_detections)
                
                # Debug logging
                now_dbg = time.monotonic()
                if now_dbg - self._last_main_debug_time > 1.0:
                    bbox_center = current_detections[0]['center'] if current_detections else None
                    logger.debug(
                        "[Main] ap_active=%s phase=%s dets=%d pose=%s bbox=%s data_collect=%s",
                        self.autopilot.active,
                        self.autopilot.phase,
                        len(current_detections),
                        f"x={current_pose.x_cm:.1f} y={current_pose.y_cm:.1f} z={current_pose.z_cm:.1f} c={current_pose.confidence:.2f}" if current_pose else "None",
                        bbox_center,
                        self.data_collection_active,
                    )
                    self._last_main_debug_time = now_dbg

                self._draw(current_frame, current_pose, current_detections, is_new_frame)
                
                try:
                    self.room_view.update(current_pose, autopilot=self.autopilot, debug_frame=current_frame, is_flying=self.controller.is_flying)
                except Exception: logger.exception("RoomView Error")
                
                cv2.waitKey(1)
                self.cc_ui.draw(self.win)
                pygame.display.update()
                pygame.time.delay(16)
        except KeyboardInterrupt: logger.info("[App] Shutdown requested")
        finally: self.cleanup()

    def _update_control(self, is_new_frame, current_pose, current_detections):
        if self.cc_ui.active:
            rc_vals = [0, 0, 0, 0]
            joy_rc = [0, 0, 0, 0]
        else:
            rc_vals = self._get_keyboard_movement()
            joy_rc = self.joy_handler.get_rc_inputs()

        if self.joy_calib.active: self.joy_calib.update()

        if self.flight_recorder.is_replaying:
            self._handle_replay()
        elif self.autopilot.active and self.vision_thread and not self.calibration.active and not self.joy_calib.active:
            if is_new_frame:
                bbox_center = current_detections[0]['center'] if current_detections else None
                bbox_ratio = self._get_bbox_ratio(current_detections)
                self._last_auto_rc = self.autopilot.compute(current_pose, bbox_center=bbox_center, bbox_ratio=bbox_ratio)
            self.controller.send_rc_control(*self._last_auto_rc)
            self.flight_recorder.record_rc(*self._last_auto_rc)
        elif not self.calibration.active and not self.joy_calib.active:
            final_rc = [rc_vals[i] if rc_vals[i] != 0 else joy_rc[i] for i in range(4)]
            self.controller.send_rc_control(*final_rc)
            self.flight_recorder.record_rc(*final_rc)
        else:
            self.controller.send_rc_control(0, 0, 0, 0)

        if self.calibration.active and self.vision_thread:
            self.calibration._current_z_scale = self.vision_thread.pose_estimator.Z_SCALE
            if self.calibration.feed_pose(current_pose):
                if self.calibration.computed_scale is not None:
                    self.vision_thread.pose_estimator.Z_SCALE = self.calibration.computed_scale
                self.calibration.state = self.calibration.STATE_INACTIVE

    def _get_bbox_ratio(self, detections):
        if not detections: return None
        b = detections[0]['box']
        bh = b[3] - b[1]
        if bh > 0 and b[0] > 20 and b[1] > 20 and b[2] < 940 and b[3] < 700:
            return bh / 720.0
        return None

    def _handle_replay(self):
        replay_evt = self.flight_recorder.get_replay_event()
        if replay_evt == "takeoff": self.controller.takeoff()
        elif replay_evt == "land": self.controller.land()
        replay_rc = self.flight_recorder.get_replay_rc()
        if replay_rc:
            self.controller.send_rc_control(*replay_rc)
            self.flight_recorder.record_rc(*replay_rc)
        else: self.controller.send_rc_control(0, 0, 0, 0)

    def _draw(self, frame, pose, detections, is_new_frame):
        if frame is None and self.fallback_frame is not None:
            frame = self.fallback_frame.copy()
            stream_status = "NO STREAM (fallback)"
        elif frame is None:
            self.win.fill((0, 0, 0))
            draw_osd_text(self.win, "Waiting for video stream...", (self.SCREEN_WIDTH//2-100, self.SCREEN_HEIGHT//2), self.font)
            return
        else: stream_status = "CONNECTED"

        display_frame = frame.copy()
        display_frame = draw_detections(display_frame, detections)
        if pose and self.vision_thread:
            is_align = self.autopilot.active and self.autopilot.phase == "ALIGN"
            display_frame = self.vision_thread.pose_estimator.draw_estimate(display_frame, pose, show_heatmap=is_align)

        if is_new_frame and self.out_writer:
            try:
                rec_frame = cv2.cvtColor(display_frame, cv2.COLOR_RGB2BGR)
                self.out_writer.write(rec_frame)
            except Exception: logger.exception("Recording Error")

        if self.swap_rb: display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        display_frame = np.rot90(display_frame)
        display_frame = np.flipud(display_frame)
        surf = pygame.surfarray.make_surface(display_frame)
        if surf.get_size() != (self.SCREEN_WIDTH, self.SCREEN_HEIGHT):
            surf = pygame.transform.scale(surf, (self.SCREEN_WIDTH, self.SCREEN_HEIGHT))
        self.win.blit(surf, (0, 0))

        self._draw_hud(stream_status)

    def _draw_hud(self, stream_status):
        status_text = "CONNECTED" if self.controller.is_connected else "DISCONNECTED"
        status_color = (50, 255, 50) if self.controller.is_connected else (255, 50, 50)
        ip_label = f" ({self.telemetry.drone_name})" if self.telemetry.drone_name else ""
        draw_osd_text(self.win, f"DRONE: {status_text} | {self.args.ip}{ip_label}", (15, 15), self.font, status_color)
        
        mode_text = f"AUTO: {self.autopilot.phase}" if self.autopilot.active else "MANUAL"
        mode_color = (255, 255, 0) if self.autopilot.active else (200, 200, 200)
        mode_w = self.mode_font.size(mode_text)[0]
        draw_osd_text(self.win, mode_text, (self.SCREEN_WIDTH - mode_w - 15, 15), self.mode_font, mode_color)

        shortcuts = "SPACE: Lock | P: Auto | F9: Rec | F10: Play | ESC: KILL"
        short_w = self.font.size(shortcuts)[0]
        draw_osd_text(self.win, shortcuts, (self.SCREEN_WIDTH - short_w - 15, self.SCREEN_HEIGHT - 35), self.font, (255, 200, 100))

        if self.flight_recorder.is_recording:
            draw_osd_text(self.win, f"REC ● {self.flight_recorder.recording_duration:.1f}s", (15, 45), self.font, (255, 50, 50))
        elif self.flight_recorder.is_replaying:
            e, t = self.flight_recorder.replay_progress
            draw_osd_text(self.win, f"REPLAY ▶ {e:.1f}/{t:.1f}s", (15, 45), self.font, (50, 200, 255))

        if not self.detection_enabled: draw_osd_text(self.win, "DETECT: OFF", (15, 70), self.font, (180, 180, 50))

        telem_lines = self.telemetry.get_osd_lines()
        for i, line in enumerate(telem_lines):
            tw = self.telem_font.size(line)[0]
            draw_osd_text(self.win, line, (self.SCREEN_WIDTH - tw - 15, 45 + i * 20), self.telem_font, (150, 220, 255))

        if self.joy_handler.is_connected and not self.joy_calib.active:
            draw_sticks(self.win, self.joy_handler.get_raw_sticks(), self.SCREEN_WIDTH//2 - 90, self.SCREEN_HEIGHT - 100)

    def cleanup(self):
        if self.vision_thread:
            self.vision_thread.stop()
            self.vision_thread.join(timeout=2.0)
        if self.out_writer: self.out_writer.release()
        try: self.controller.cleanup()
        except Exception: logger.exception("Cleanup Error")
        self.room_view.close()
        self.telemetry.stop()
        pygame.quit()
        logger.info("Shutdown complete.")
