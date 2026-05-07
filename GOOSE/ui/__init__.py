import os
import sys
import cv2
import logging
import threading
import time
from kivy.config import Config

Config.set('graphics', 'resizable', True)
Config.set('graphics', 'minimum_width', '960')
Config.set('graphics', 'minimum_height', '540')
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'window_state', 'maximized')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.core.text import LabelBase
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.core.window import Window

from ui.media_gallery import MediaGallery, MediaCard, NavItem, FilterChip
from ui.drone_manager import DroneManager, DroneCard
from ui.loading_overlay import LoadingOverlay
from ui.virtual_joystick import VirtualJoystick
from ui.icons import Icons
from .utils import draw_osd_text, draw_detections, draw_sticks

# Backend imports
from core.drone import DroneController
from core.telemetry import TelemetryService
from core.drone_registry import DroneRegistry
from core.flight_recorder import FlightRecorder
from core.autopilot import AutoPilot
from core.calibration import CalibrationMode
from core.joystick import JoystickHandler
from vision.detector import ObjectDetector
from vision.worker import VisionWorker

logger = logging.getLogger(__name__)

# Register Material Design Icons font
font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'fonts', 'materialdesignicons-webfont.ttf')
LabelBase.register(name='Icons', fn_regular=font_path)

class TopBar(Widget):
    wifi_signal = StringProperty("0%")
    battery_level = StringProperty("0%")
    status_text = StringProperty("DISCONNECTED")
    is_connected = BooleanProperty(False)

class Stats(BoxLayout):
    altitude = StringProperty("0.0")
    speed = StringProperty("0.0")
    distance = StringProperty("0.0")
    alt_percent = NumericProperty(0.0)
    speed_percent = NumericProperty(0.0)
    dist_percent = NumericProperty(0.0)

class Module(Widget): pass

class Bottom(Widget): 
    is_flying = BooleanProperty(False)
    is_recording = BooleanProperty(False)

    def toggle_flight(self):
        action_name = "LAND" if self.is_flying else "TAKE OFF"
        App.get_running_app().on_action(action_name)

    def toggle_record(self):
        action_name = "SAVE" if self.is_recording else "REC"
        App.get_running_app().on_action(action_name)

class FlightMenu(BoxLayout): 
    active_mode = StringProperty("")
    in_cooldown = BooleanProperty(False)

    def on_mode_select(self, mode_name):
        if self.in_cooldown: return
        self.active_mode = mode_name
        self.in_cooldown = True
        App.get_running_app().on_action(mode_name)
        Clock.schedule_once(self.reset_cooldown, 2.0)

    def reset_cooldown(self, dt):
        self.in_cooldown = False

class DroneApp(App):
    recording_time = StringProperty("00:00:00")
    uptime = StringProperty("00:00")
    conf_threshold = NumericProperty(0.5)
    _record_seconds = 0
    _uptime_seconds = -1

    def __init__(self, args=None, **kwargs):
        super().__init__(**kwargs)
        self.args = args
        self.controller = DroneController()
        self.telemetry = TelemetryService()
        self.drone_registry = DroneRegistry()
        self.flight_recorder = FlightRecorder()
        self.autopilot = AutoPilot()
        self.calibration = CalibrationMode()
        self.joy_handler = JoystickHandler()
        self.detector = None
        self.vision_thread = None
        self._video_event = None
        self._control_event = None
        self.drone_manager_panel = None
        self._drone_mgr_kv_loaded = False
        self._loading_overlay = None
        self._pressed_keys = set()
        
        Window.bind(on_key_down=self._on_key_down)
        Window.bind(on_key_up=self._on_key_up)

    def _on_key_down(self, window, key, scancode, codepoint, modifiers, **kwargs):
        self._pressed_keys.add(key)
        
    def _on_key_up(self, window, key, scancode, **kwargs):
        if key in self._pressed_keys:
            self._pressed_keys.remove(key)

    def on_start(self):
        Clock.schedule_interval(self._update_uptime, 1.0)
        self.connect_to_drone()

    def show_loading(self, title, subtitle, icon=None):
        if icon is None:
            icon = Icons.wifi
        if not self._loading_overlay:
            self._loading_overlay = LoadingOverlay()
        self._loading_overlay.title = title
        self._loading_overlay.subtitle = subtitle
        self._loading_overlay.icon = icon
        if not self._loading_overlay.parent:
            self.root.add_widget(self._loading_overlay)

    def hide_loading(self):
        if self._loading_overlay and self._loading_overlay.parent:
            self.root.remove_widget(self._loading_overlay)

    def connect_to_drone(self, dt=None):
        # Use provided arg, then last used IP from registry, then default
        ip = "192.168.10.1"
        if self.args and getattr(self.args, 'ip', None):
            ip = self.args.ip
        elif getattr(self, 'drone_registry', None) and self.drone_registry.last_active_ip:
            ip = self.drone_registry.last_active_ip
            
        port = self.args.port if self.args and getattr(self.args, 'port', None) else 8889
        
        header = self.root.ids.header
        header.status_text = "CONNECTING..."
        self.show_loading("Connecting to Drone", f"Attempting connection to {ip}...", Icons.wifi)
        
        def _target():
            if self.controller.connect(host=ip, port=port):
                Clock.schedule_once(lambda x: self._on_connection_success(ip))
            else:
                Clock.schedule_once(lambda x: self._on_connection_failure())

        threading.Thread(target=_target, daemon=True).start()

    def _on_connection_success(self, ip):
        self.hide_loading()
        header = self.root.ids.header
        header.status_text = "READY TO FLY"
        header.is_connected = True
        
        drone_name = self.drone_registry.get_name(ip)
        self.drone_registry.add_or_update(ip)
        self.telemetry.start(self.controller.tello, ip_address=ip, drone_name=drone_name)
        
        # Load model asynchronously so the user doesn't have to wait to start flying
        self._load_model_async()
        
        if not self._video_event:
            self._video_event = Clock.schedule_interval(self._update_video, 1.0 / 30.0)
        if not self._control_event:
            self._control_event = Clock.schedule_interval(self._update_control, 1.0 / 40.0)
        
        Clock.schedule_interval(self._update_telemetry, 0.5)

    def _on_connection_failure(self):
        self.hide_loading()
        header = self.root.ids.header
        header.status_text = "CONNECTION FAILED"
        header.is_connected = False

    def _load_model_async(self):
        if self.vision_thread: return
        # Do not show blocking loading screen for AI. Load in background thread so user can fly immediately.
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            model_dir = "GOOSE/assets/models" if os.path.exists("GOOSE") else "assets/models"
            onnx_path = os.path.join(model_dir, "targetModel.onnx")
            pt_path = os.path.join(model_dir, "targetModel.pt")

            selected_path = None
            if self.args and self.args.model == 'onnx' and os.path.exists(onnx_path):
                selected_path = onnx_path
            elif self.args and self.args.model == 'pt' and os.path.exists(pt_path):
                selected_path = pt_path
            else:
                if os.path.exists(onnx_path): selected_path = onnx_path
                elif os.path.exists(pt_path): selected_path = pt_path

            if selected_path:
                logger.info("Loading model for Kivy: %s", selected_path)
                self.detector = ObjectDetector(selected_path)
                self.detector.load_model()
                self.vision_thread = VisionWorker(self.controller, self.detector, self.calibration, self.autopilot)
                self.vision_thread.start()
                
                saved_scale = CalibrationMode.load_z_scale()
                if saved_scale is not None:
                    self.vision_thread.pose_estimator.Z_SCALE = saved_scale
        except Exception as e:
            logger.error(f"Failed to load AI model in background: {e}")

    def _update_video(self, dt):
        frame = self.controller.get_frame()
        if frame is not None:
            try:
                display_frame = frame.copy()
                if self.vision_thread:
                    detections = self.vision_thread.latest_detections
                    pose = self.vision_thread.latest_pose
                    display_frame = draw_detections(display_frame, detections)
                    if pose:
                        is_align = self.autopilot.active and self.autopilot.phase == "ALIGN"
                        display_frame = self.vision_thread.pose_estimator.draw_estimate(display_frame, pose, show_heatmap=is_align)

                buf = cv2.flip(display_frame, 0).tobytes()
                texture = Texture.create(size=(display_frame.shape[1], display_frame.shape[0]), colorfmt='rgb')
                texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
                self.root.ids.videosstream.texture = texture
            except Exception as e:
                logger.error(f"Video update error: {e}")

    def _update_control(self, dt):
        """Poll joystick and send RC commands."""
        if not self.controller.is_connected: return

        # Get hardware joystick inputs
        joy_rc = self.joy_handler.get_rc_inputs()
        
        # Get virtual onscreen joystick inputs
        left_stick = self.root.ids.left_stick
        right_stick = self.root.ids.right_stick
        
        vs_lr = int(right_stick.out_x * 100)  # roll (left/right strafe)
        vs_fb = int(right_stick.out_y * 100)  # pitch (forward/back)
        vs_ud = int(left_stick.out_y * 100)   # throttle (up/down)
        vs_yv = int(left_stick.out_x * 100)   # yaw (left/right rotation)
        
        # Get keyboard inputs
        kb_lr, kb_fb, kb_ud, kb_yv = 0, 0, 0, 0
        speed = 100
        keys = self._pressed_keys
        
        # 'a': 97, 'd': 100, 'w': 119, 's': 115, 'q': 113, 'e': 101
        # 'spacebar': 32, 'shift': 304, 'rshift': 303
        if 97 in keys: kb_lr = -speed
        elif 100 in keys: kb_lr = speed
        
        if 119 in keys: kb_fb = speed
        elif 115 in keys: kb_fb = -speed
        
        if 32 in keys: kb_ud = speed
        elif 304 in keys or 303 in keys: kb_ud = -speed
        
        if 113 in keys: kb_yv = -speed
        elif 101 in keys: kb_yv = speed
        
        if self.autopilot.active and self.vision_thread:
            # Autopilot logic would go here if we wanted to replicate the main loop exactly
            pass
        
        # Priority: Keyboard > Virtual joystick > Hardware joystick
        final_rc = [
            kb_lr if kb_lr != 0 else (vs_lr if vs_lr != 0 else joy_rc[0]),
            kb_fb if kb_fb != 0 else (vs_fb if vs_fb != 0 else joy_rc[1]),
            kb_ud if kb_ud != 0 else (vs_ud if vs_ud != 0 else joy_rc[2]),
            kb_yv if kb_yv != 0 else (vs_yv if vs_yv != 0 else joy_rc[3])
        ]
        
        self.controller.send_rc_control(*final_rc)
        
        if any(v != 0 for v in final_rc):
            self.flight_recorder.record_rc(*final_rc)

    def _update_telemetry(self, dt):
        stats = self.root.ids.stats_area
        header = self.root.ids.header
        footer = self.root.ids.footer
        
        header.battery_level = f"{self.telemetry.battery}%"
        # Tello SDK does not broadcast wifi SNR over the state port. Querying it blocks the command loop.
        header.wifi_signal = "92%" if self.controller.is_connected else "0%"
        
        stats.altitude = f"{self.telemetry.height / 100.0:.1f}"
        stats.alt_percent = min(1.0, self.telemetry.height / 3000.0)
        
        speed = self.telemetry.speed_magnitude / 100.0
        stats.speed = f"{speed:.1f}"
        stats.speed_percent = min(1.0, speed / 10.0)
        
        dist = self.telemetry.total_distance_cm / 100.0
        stats.distance = f"{dist:.1f}"
        stats.dist_percent = min(1.0, dist / 1000.0)
        
        footer.is_flying = self.controller.is_flying
        footer.is_recording = self.flight_recorder.is_recording

    def _update_uptime(self, dt):
        self._uptime_seconds += 1
        mins, secs = divmod(self._uptime_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            self.uptime = f"{hours:02d}:{mins:02d}:{secs:02d}"
        else:
            self.uptime = f"{mins:02d}:{secs:02d}"

    def toggle_recording_timer(self, is_recording):
        if is_recording:
            self._record_seconds = 0
            self.recording_time = "00:00:00"
            Clock.schedule_interval(self._update_recording_time, 1.0)
        else:
            Clock.unschedule(self._update_recording_time)
            self._record_seconds = 0
            self.recording_time = "00:00:00"

    def _update_recording_time(self, dt):
        self._record_seconds += 1
        mins, secs = divmod(self._record_seconds, 60)
        hours, mins = divmod(mins, 60)
        self.recording_time = f"{hours:02d}:{mins:02d}:{secs:02d}"

    def _on_connection_failure(self):
        header = self.root.ids.header
        header.status_text = "CONNECTION FAILED"
        header.is_connected = False
        self.controller.tello = None
        self.controller.is_connected = False

    def on_action(self, action_name, *args):
        logger.info(f"UI Action: {action_name} args: {args}")
        
        if action_name == "RECONNECT":
            self.connect_to_drone()
            return
        elif action_name == "SETTINGS":
            self.toggle_media_gallery()
            return
        elif action_name == "DRONES":
            self.toggle_drone_manager()
            return
        elif action_name == "CYCLE_CONF":
            self.conf_threshold = round((self.conf_threshold + 0.1) if self.conf_threshold < 0.9 else 0.1, 1)
            if self.vision_thread:
                self.vision_thread.conf_threshold = self.conf_threshold
            return
        elif action_name == "TOGGLE_VISION":
            # Enable/Disable vision entirely
            if self.vision_thread:
                is_active = not self.vision_thread.is_paused
                self.vision_thread.is_paused = is_active
                logger.info(f"Vision model {'paused' if is_active else 'resumed'}")
            return
        elif action_name == "CALIB_VIS":
            if self.calibration:
                self.calibration.toggle(ground_mode=False)
            return
        elif action_name == "EDIT_IP":
            self.toggle_drone_manager()
            return

        if not self.controller.is_connected or not getattr(self.controller, 'tello', None):
            logger.warning(f"Action '{action_name}' ignored: Drone not connected")
            return

        try:
            if action_name == "TAKE OFF":
                self.controller.takeoff()
                self.telemetry.notify_takeoff()
            elif action_name == "LAND":
                self.controller.land()
                self.telemetry.notify_land()
            elif action_name == "CAM":
                if not hasattr(self, '_cam_dir'):
                    self._cam_dir = 0
                self._cam_dir = 1 - self._cam_dir
                self.controller.set_camera_direction(self._cam_dir)
            elif action_name == "REC":
                self.flight_recorder.start_recording()
                self.toggle_recording_timer(True)
            elif action_name == "SAVE":
                self.flight_recorder.stop_recording()
                self.toggle_recording_timer(False)
            elif action_name == "Emergency Land":
                if self.autopilot: self.autopilot.disengage()
                self.controller.land()
            elif action_name == "360 Flip":
                self.controller.flip('f')
            elif action_name == "Circle":
                self.controller.flip('r')
            elif action_name == "Up & Out":
                self.controller.flip('b')
            elif action_name == "Bounce":
                self.controller.tello.send_control_command("bounce")
            elif action_name == "LED_TEXT":
                text = args[0] if args else ""
                if text: self.controller.tello.send_control_command(f"EXT mled l r 2.5 {text}")
            elif action_name == "LED_PATTERN":
                patterns = {
                    "heart": "000000000rr00rr0rrrrrrrrrrrrrrrr0rrrrrr000rrrr0000rr000000000000",
                    "smile": "0000000000rrrr000r0000r0r0rrrr0rr0rrrr0rr00000r000rrrr0000000000",
                    "arrow": "0000r000000rr00000rrrr000000r0000000r0000000r0000000r00000000000",
                    "goose": "0000000000rr00000000rr0000000rr0000000rr0rr000rr0rr00rr000000000",
                }
                p_str = patterns.get(args[0])
                if p_str: self.controller.tello.send_control_command(f"EXT mled g {p_str}")
            elif action_name == "LED_PATTERN_CUSTOM":
                p_str = args[0] if args else ""
                if p_str: self.controller.tello.send_control_command(f"EXT mled g {p_str}")
            elif action_name == "LED_COLOR":
                self.controller.tello.send_control_command(f"EXT mled g {args[0]*64}")
            elif action_name == "LED_CLEAR":
                self.controller.tello.send_control_command(f"EXT mled g {'0'*64}")
        except Exception as e:
            logger.error(f"Command '{action_name}' failed: {e}")

    def close_media_gallery(self):
        if self._gallery and self._gallery.parent:
            self.root.remove_widget(self._gallery)
            self._gallery = None

    _gallery = None
    _gallery_kv_loaded = False

    def toggle_media_gallery(self):
        if self._gallery and self._gallery.parent:
            self.root.remove_widget(self._gallery)
            self._gallery = None
            return
        if not self._gallery_kv_loaded:
            kv_path = os.path.join(os.path.dirname(__file__), 'kv', 'media_gallery.kv')
            Builder.load_file(kv_path)
            self._gallery_kv_loaded = True
        gallery = MediaGallery()
        self.root.add_widget(gallery)
        gallery.open()
        self._gallery = gallery

    def toggle_drone_manager(self):
        """Open or close the drone fleet management overlay."""
        if self.drone_manager_panel and self.drone_manager_panel.parent:
            self.root.remove_widget(self.drone_manager_panel)
            self.drone_manager_panel = None
            return
        if not self._drone_mgr_kv_loaded:
            kv_path = os.path.join(os.path.dirname(__file__), 'kv', 'drone_manager.kv')
            Builder.load_file(kv_path)
            self._drone_mgr_kv_loaded = True
        panel = DroneManager()
        self.root.add_widget(panel)
        panel.open()
        self.drone_manager_panel = panel

    def close_drone_manager(self):
        """Close the drone manager overlay (called from the panel itself)."""
        if self.drone_manager_panel and self.drone_manager_panel.parent:
            self.root.remove_widget(self.drone_manager_panel)
            self.drone_manager_panel = None

    def on_stop(self):
        self.controller.cleanup()
        self.telemetry.stop()
        sys.exit(0)

    def build(self):
        kv_path = os.path.join(os.path.dirname(__file__), 'ui.kv')
        return Builder.load_file(kv_path)

def Setup(args=None):
    DroneApp(args=args).run()
