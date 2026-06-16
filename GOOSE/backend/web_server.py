import os
import sys
import time
import logging
import cv2
import threading
import json
import math
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.drone import DroneController
from core.telemetry import TelemetryService
from core.drone_registry import DroneRegistry
from core.flight_recorder import FlightRecorder
from core.autopilot import AutoPilot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GooseWebServer")

app = FastAPI(title="GOOSE Drone Cockpit Server")

controller = DroneController()
telemetry = TelemetryService()
registry = DroneRegistry()
recorder = FlightRecorder()
autopilot = AutoPilot()

# Replay state
replay_thread = None
is_replay_running = False

# Manual RC safety timeout tracking
last_rc_received_time = time.time()

# Flight Settings state
flight_settings = {
    "max_altitude_m": 15.0,
    "max_distance_m": 60.0,
    "sensitivity": 75.0,
    "manual_speed": 60.0,
    "control_mode": 2,
}

def stop_replay_session(reason="stop", send_stop=True, join=True):
    global is_replay_running, replay_thread
    logger.info(f"Stopping replay session: reason={reason}")
    is_replay_running = False
    recorder.stop_replay()
    
    if join and replay_thread is not None:
        try:
            replay_thread.join(timeout=1.0)
        except Exception:
            pass
        replay_thread = None
        
    if send_stop and controller.is_connected:
        controller.send_stop()

def on_drone_connection_lost():
    global connected_ip, is_video_recording
    logger.warning("Watchdog connection loss callback triggered!")
    
    # Disable autopilot, replay, recording, telemetry
    stop_replay_session("connection_lost", send_stop=False, join=False)
    if autopilot.active:
        autopilot.disengage()
    if recorder.is_recording:
        recorder.stop_recording()
    if is_video_recording:
        is_video_recording = False
    telemetry.stop()
    connected_ip = None

controller.on_connection_lost = on_drone_connection_lost

def apply_control_settings(lr, fb, ud, yv):
    # 1. Apply sensitivity scaling
    sens = flight_settings.get("sensitivity", 75.0)
    scale = max(0.1, min(1.0, sens / 100.0))
    
    lr = int(lr * scale)
    fb = int(fb * scale)
    ud = int(ud * scale)
    yv = int(yv * scale)
    
    # 2. Apply altitude limit (prevent upward movement if alt limit reached/exceeded)
    max_alt_cm = flight_settings.get("max_altitude_m", 15.0) * 100.0
    if telemetry.height >= max_alt_cm and ud > 0:
        ud = 0
        
    # 3. Apply distance limit (prevent movement further away from starting position)
    max_dist_cm = flight_settings.get("max_distance_m", 60.0) * 100.0
    current_dist_cm = math.sqrt(telemetry.pos_x**2 + telemetry.pos_y**2)
    if current_dist_cm >= max_dist_cm:
        if telemetry.pos_x * fb > 0:
            fb = 0
        if telemetry.pos_y * lr > 0:
            lr = 0
            
    return lr, fb, ud, yv

connected_ip = None
yolo_enabled = False
detector = None

autopilot_thread = None
is_autopilot_running = False

# Video recording state
video_recorder_thread = None
is_video_recording = False
video_writer = None
video_writer_lock = threading.Lock()
video_file_path = None

camera_direction = 0

latest_detections = []
detections_lock = threading.Lock()
is_yolo_working = True
yolo_worker_thread = None

def load_detector():
    global detector
    if detector is not None:
        return
    try:
        model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "models")
        onnx_path = os.path.join(model_dir, "targetModel.onnx")
        pt_path = os.path.join(model_dir, "targetModel.pt")
        selected_path = onnx_path if os.path.exists(onnx_path) else (pt_path if os.path.exists(pt_path) else None)
        if selected_path:
            logger.info(f"Loading YOLO model for web server: {selected_path}")
            from vision.detector import ObjectDetector
            detector = ObjectDetector(selected_path)
            detector.load_model()
        else:
            logger.error("No model file found for YOLO overlay")
    except Exception as e:
        logger.error(f"Failed to load YOLO model: {e}")

def video_recorder_loop(output_path, fps=30.0):
    global is_video_recording, video_writer, yolo_enabled
    logger.info(f"Video recorder thread started. Output path: {output_path}")
    
    frame_delay = 1.0 / fps
    
    while is_video_recording:
        loop_start = time.time()
        
        if controller.is_connected and controller.frame_reader:
            try:
                frame = controller.frame_reader.frame
                if frame is not None and frame.size > 0:
                    # djitellopy frames are in RGB, convert to BGR for OpenCV
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    if yolo_enabled:
                        with detections_lock:
                            active_detections = list(latest_detections)
                            from vision.draw import draw_detections
                            frame_bgr = draw_detections(frame_bgr, active_detections)
                                
                    with video_writer_lock:
                        if video_writer is None:
                            height, width = frame_bgr.shape[:2]
                            media_dir = os.path.dirname(output_path)
                            os.makedirs(media_dir, exist_ok=True)
                            
                            # Try avc1 first for browser compatibility. If it fails, fallback to mp4v.
                            try:
                                fourcc = cv2.VideoWriter_fourcc(*'avc1')
                                video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                                if not video_writer.isOpened():
                                    raise Exception("Failed to open with avc1")
                                logger.info(f"Initialized VideoWriter with avc1 codec at {width}x{height}")
                            except Exception as e:
                                logger.warning(f"Failed to initialize VideoWriter with avc1 codec: {e}. Falling back to mp4v.")
                                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                                video_writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
                                if not video_writer.isOpened():
                                    logger.error(f"Failed to open VideoWriter with mp4v codec at {output_path}")
                                    is_video_recording = False
                                    break
                                logger.info(f"Initialized VideoWriter with mp4v codec at {width}x{height}")
                                
                        if video_writer is not None:
                            video_writer.write(frame_bgr)
            except Exception as e:
                logger.error(f"Error writing frame to video: {e}")
        
        # Calculate precise sleep to maintain requested FPS
        elapsed = time.time() - loop_start
        sleep_time = max(0.005, frame_delay - elapsed)
        time.sleep(sleep_time)

    # Release video writer
    with video_writer_lock:
        if video_writer is not None:
            video_writer.release()
            video_writer = None
            logger.info("VideoWriter released successfully")

def detect_downward_target(frame_bgr):
    """
    Classic CV fallback for downward camera: detects circular rings
    in greyscale using Hough Circle Transform.
    """
    import numpy as np
    try:
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 0)
        
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=1.2,
            minDist=80,
            param1=70,
            param2=45,
            minRadius=15,
            maxRadius=85
        )
        
        detections = []
        if circles is not None:
            circles = np.round(circles[0, :]).astype("int")
            for (x, y, r) in circles[:1]:  # Use top candidate
                x1 = max(0, x - r)
                y1 = max(0, y - r)
                x2 = min(frame_bgr.shape[1], x + r)
                y2 = min(frame_bgr.shape[0], y + r)
                
                detections.append({
                    'box': [int(x1), int(y1), int(x2), int(y2)],
                    'center': (int(x), int(y)),
                    'conf': 0.85,
                    'class': 0,
                    'name': "landing_ring",
                    'track_id': None
                })
            return detections
    except Exception as e:
        logger.error(f"Downward circle detection error: {e}")
    return []

def yolo_worker_loop():
    global is_yolo_working, latest_detections, yolo_enabled, detector, camera_direction
    logger.info("Async YOLO/CV worker thread started")
    
    while is_yolo_working:
        loop_start = time.time()
        
        if yolo_enabled and controller.is_connected and controller.frame_reader:
            try:
                frame = controller.frame_reader.frame
                if frame is not None and frame.size > 0:
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    if camera_direction == 1:
                        # Downward camera: Run Hough Circle Detection (classic CV)
                        detections = detect_downward_target(frame_bgr)
                    else:
                        # Forward camera: Run YOLO Model Inference
                        load_detector()
                        if detector and detector.model:
                            _, detections = detector.detect(frame_bgr, conf_threshold=0.5)
                        else:
                            detections = []
                            
                    with detections_lock:
                        latest_detections = detections
                else:
                    with detections_lock:
                        latest_detections = []
            except Exception as e:
                logger.error(f"Error in async YOLO/CV worker: {e}")
        else:
            with detections_lock:
                latest_detections = []
                
        # Limit loop rate to ~12 FPS to keep CPU utilization low and stream smooth
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, 0.08 - elapsed)
        time.sleep(sleep_time)

def autopilot_worker_loop():
    global is_autopilot_running, autopilot, latest_detections, camera_direction, last_rc_received_time, is_replay_running
    logger.info("Autopilot worker thread started")
    
    while is_autopilot_running:
        loop_start = time.time()
        
        if autopilot and autopilot.active and controller.is_connected:
            with detections_lock:
                active_detections = list(latest_detections)
                
            bbox_center = None
            bbox_ratio = None
            if active_detections:
                primary = active_detections[0]
                bbox_center = primary['center']
                x1, y1, x2, y2 = primary['box']
                w = x2 - x1
                h = y2 - y1
                frame_area = 320.0 * 240.0 if camera_direction == 1 else 960.0 * 720.0
                bbox_ratio = float(w * h) / frame_area
                
            frame_sz = (320, 240) if camera_direction == 1 else (960, 720)
            lr, fb, ud, yv = autopilot.compute(pose=None, bbox_center=bbox_center, bbox_ratio=bbox_ratio, frame_size=frame_sz)
            
            if autopilot.active:
                if recorder.is_recording:
                    recorder.record_rc(lr, fb, ud, yv)
                controller.send_rc_control(lr, fb, ud, yv)
        else:
            # Check for manual RC drift safety timeout
            now = time.time()
            if controller.is_connected and not is_replay_running:
                if now - last_rc_received_time > 0.25 and controller._last_rc_values != (0, 0, 0, 0):
                    logger.warning("[Server] Manual RC timeout detected (>250ms). Stopping drone drift.")
                    controller.send_stop()
        
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, 0.05 - elapsed)
        time.sleep(sleep_time)

# Video streaming helper
def get_video_frame():
    """Generates MJPEG frames from the Tello video feed, emitting only new frames."""
    global yolo_enabled
    logger.info("Starting MJPEG video frame generator loop")
    last_frame_id = None  # Track Python object id() to detect new frames
    while True:
        if controller.is_connected and controller.frame_reader:
            try:
                frame = controller.frame_reader.frame
                # Only encode & yield when djitellopy has decoded a genuinely new frame
                # (it replaces the .frame attribute with a new ndarray each time)
                if frame is not None and frame.size > 0 and id(frame) != last_frame_id:
                    last_frame_id = id(frame)
                    # Tello frames from djitellopy are in RGB, convert to BGR for OpenCV
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

                    if yolo_enabled:
                        with detections_lock:
                            active_detections = list(latest_detections)
                            from vision.draw import draw_detections
                            frame_bgr = draw_detections(frame_bgr, active_detections)

                    ret, jpeg = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
                    time.sleep(0.005)  # New frame sent — poll quickly for the next one
                    continue
            except Exception as e:
                logger.error(f"Error reading/encoding frame: {e}")
        else:
            # Disconnected — show offline screen
            last_frame_id = None  # Reset so first real frame is always sent
            try:
                img = cv2.imread(os.path.join(os.path.dirname(__file__), "assets", "logo.png"))
                if img is None:
                    import numpy as np
                    img = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(img, "STREAM OFFLINE", (170, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 160, 255), 2)
                ret, jpeg = cv2.imencode('.jpg', img)
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            except Exception:
                pass
        time.sleep(0.033)  # ~30 FPS poll rate when idle / waiting for new frame


# Models
class ConnectionRequest(BaseModel):
    ip: str

class RCRequest(BaseModel):
    lr: int
    fb: int
    ud: int
    yv: int

class LEDPatternRequest(BaseModel):
    pattern: str

class LEDTextRequest(BaseModel):
    text: str
    color: str = "r"
    direction: str = "l"
    speed: float = 1.0

class FlightSettingsRequest(BaseModel):
    max_altitude_m: float
    max_distance_m: float
    sensitivity: float
    manual_speed: float
    control_mode: int

@app.post("/api/connect")
def connect_drone(req: ConnectionRequest):
    global connected_ip
    if controller.connection_state == "connecting":
        raise HTTPException(status_code=409, detail="A connection attempt is already in progress. Please wait.")
    try:
        if controller.is_connected:
            stop_replay_session("reconnect", send_stop=False, join=True)
            controller.disconnect()
            telemetry.stop()
            connected_ip = None

        logger.info(f"Connecting to Tello drone at {req.ip}")
        success = controller.connect(host=req.ip)
        if success:
            connected_ip = req.ip
            drone_name = registry.get_name(req.ip)
            registry.add_or_update(req.ip)
            telemetry.start(controller.tello, ip_address=req.ip, drone_name=drone_name)
            return {"status": "success", "message": f"Connected to drone at {req.ip}"}
        else:
            raise HTTPException(status_code=500, detail="Drone connection timed out or failed")
    except Exception as e:
        logger.exception("Connect endpoint crashed")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/disconnect")
def disconnect_drone():
    global connected_ip
    try:
        stop_replay_session("disconnect", send_stop=False, join=True)
        controller.disconnect()
        telemetry.stop()
        connected_ip = None
        return {"status": "success", "message": "Disconnected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/takeoff")
def takeoff():
    if not controller.is_connected or not controller.tello:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        controller.takeoff()
        telemetry.notify_takeoff()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/land")
def land():
    if not controller.is_connected or not controller.tello:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        controller.land()
        telemetry.notify_land()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/emergency")
def emergency():
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        controller.emergency()
        telemetry.notify_land()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class FlipRequest(BaseModel):
    direction: str

@app.post("/api/flip")
def flip(req: FlipRequest):
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    if req.direction not in ('l', 'r', 'f', 'b'):
        raise HTTPException(status_code=400, detail="Direction must be l, r, f, or b")
    try:
        controller.flip(req.direction)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CameraRequest(BaseModel):
    direction: int

@app.post("/api/camera")
def set_camera(req: CameraRequest):
    global camera_direction
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        success = controller.set_camera_direction(req.direction)
        if success:
            camera_direction = req.direction
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/rc")
def rc_control(req: RCRequest):
    global last_rc_received_time
    last_rc_received_time = time.time()
    if not controller.is_connected or not controller.tello:
        return {"status": "error", "message": "Drone not connected"}
        
    # Check if any manual command is non-zero
    is_manual_active = (req.lr != 0 or req.fb != 0 or req.ud != 0 or req.yv != 0)
    if is_manual_active and autopilot.active:
        logger.info("[Server] Manual override detected, disengaging autopilot")
        autopilot.disengage()
        
    try:
        # Apply flight settings (sensitivity and geofences)
        lr, fb, ud, yv = apply_control_settings(req.lr, req.fb, req.ud, req.yv)
        
        # If recording is active, record the commands
        if recorder.is_recording:
            recorder.record_rc(lr, fb, ud, yv)
            
        controller.send_rc_control(lr, fb, ud, yv)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/led/pattern")
def led_pattern(req: LEDPatternRequest):
    if not controller.is_connected or not controller.tello:
        raise HTTPException(status_code=400, detail="Drone not connected")
    if len(req.pattern) != 64:
        raise HTTPException(status_code=400, detail="Pattern must be exactly 64 characters")
    try:
        controller.tello.send_command_without_return(f"EXT mled g {req.pattern}")
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/led/text")
def led_text(req: LEDTextRequest):
    if not controller.is_connected or not controller.tello:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        speed = max(0.1, min(2.5, req.speed))
        controller.tello.send_command_without_return(
            f"EXT mled {req.direction} {req.color} {speed} {req.text}"
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/telemetry")
def get_telemetry():
    is_flying = controller.is_flying if controller.is_connected else False
    return {
        "connected": controller.is_connected,
        "flying": is_flying,
        "ip": connected_ip or "",
        "drone_name": telemetry.drone_name if controller.is_connected else "",
        "battery": telemetry.battery if controller.is_connected else 0,
        "height": telemetry.height if controller.is_connected else 0,
        "speed_x": telemetry.speed_x if controller.is_connected else 0,
        "speed_y": telemetry.speed_y if controller.is_connected else 0,
        "speed_z": telemetry.speed_z if controller.is_connected else 0,
        "speed": telemetry.speed_magnitude if controller.is_connected else 0,
        "pitch": telemetry.pitch if controller.is_connected else 0,
        "roll": telemetry.roll if controller.is_connected else 0,
        "yaw": telemetry.yaw if controller.is_connected else 0,
        "temperature": telemetry.temperature if controller.is_connected else 0,
        "flight_duration": telemetry.current_flight_time if controller.is_connected else 0,
        "total_distance": telemetry.total_distance_cm if controller.is_connected else 0,
        "autopilot_active": autopilot.active,
        "autopilot_phase": autopilot.phase_display,
        "pos_x": telemetry.pos_x if controller.is_connected else 0.0,
        "pos_y": telemetry.pos_y if controller.is_connected else 0.0,
        "flight_path": telemetry.flight_path if controller.is_connected else [],
    }

@app.post("/api/telemetry/reset")
def reset_telemetry():
    telemetry.reset_stats()
    return {"status": "success"}

class YoloConfigRequest(BaseModel):
    enabled: bool

@app.get("/api/settings/yolo")
def get_yolo_config():
    return {"enabled": yolo_enabled}

@app.post("/api/settings/yolo")
def set_yolo_config(req: YoloConfigRequest):
    global yolo_enabled
    yolo_enabled = req.enabled
    logger.info(f"YOLO vision overlay {'enabled' if yolo_enabled else 'disabled'}")
    return {"status": "success", "enabled": yolo_enabled}

@app.get("/api/settings/flight")
def get_flight_settings():
    return flight_settings

@app.post("/api/settings/flight")
def update_flight_settings(req: FlightSettingsRequest):
    flight_settings["max_altitude_m"] = req.max_altitude_m
    flight_settings["max_distance_m"] = req.max_distance_m
    flight_settings["sensitivity"] = req.sensitivity
    flight_settings["manual_speed"] = req.manual_speed
    flight_settings["control_mode"] = req.control_mode
    logger.info(f"Updated flight settings: {flight_settings}")
    return flight_settings

@app.get("/api/video")
def video_feed():
    return StreamingResponse(get_video_frame(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/media")
def list_media():
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flight_data")
    files = []
    if os.path.exists(media_dir):
        for root, dirs, filenames in os.walk(media_dir):
            for fname in sorted(filenames, reverse=True):
                fpath = os.path.join(root, fname)
                ext = os.path.splitext(fname)[1].lower()
                if ext in ('.jpg', '.jpeg', '.png', '.mp4', '.avi'):
                    stat = os.stat(fpath)
                    files.append({
                        "id": len(files) + 1,
                        "name": fname,
                        "type": "video" if ext in ('.mp4', '.avi') else "photo",
                        "date": time.strftime('%Y-%m-%d', time.localtime(stat.st_mtime)),
                        "size": f"{stat.st_size / (1024*1024):.1f} MB",
                        "path": os.path.relpath(fpath, media_dir).replace("\\", "/"),
                    })
    return files

@app.get("/api/media/file/{file_path:path}")
def serve_media_file(file_path: str):
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flight_data")
    full_path = os.path.normpath(os.path.join(media_dir, file_path))
    if not full_path.startswith(os.path.normpath(media_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    ext = os.path.splitext(full_path)[1].lower()
    media_types = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.mp4': 'video/mp4', '.avi': 'video/x-msvideo'}
    from fastapi.responses import FileResponse
    return FileResponse(full_path, media_type=media_types.get(ext, 'application/octet-stream'))

@app.delete("/api/media/{file_path:path}")
def delete_media_file(file_path: str):
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flight_data")
    full_path = os.path.normpath(os.path.join(media_dir, file_path))
    if not full_path.startswith(os.path.normpath(media_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    os.remove(full_path)
    return {"status": "success"}

@app.post("/api/led/clear")
def led_clear():
    if not controller.is_connected or not controller.tello:
        raise HTTPException(status_code=400, detail="Drone not connected")
    try:
        controller.tello.send_command_without_return("EXT mled g " + "0" * 64)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Drone Registry ---

@app.get("/api/registry")
def list_drones():
    return {"drones": registry.list_all(), "last_active_ip": registry.last_active_ip}

class DroneNameRequest(BaseModel):
    ip: str
    name: str

@app.post("/api/registry/rename")
def rename_drone(req: DroneNameRequest):
    success = registry.set_name(req.ip, req.name)
    if not success:
        raise HTTPException(status_code=404, detail="Drone not found")
    return {"status": "success"}

class DroneRemoveRequest(BaseModel):
    ip: str

@app.post("/api/registry/remove")
def remove_drone(req: DroneRemoveRequest):
    registry.remove(req.ip)
    return {"status": "success"}

# --- Media Library ---

MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flight_data")
os.makedirs(MEDIA_DIR, exist_ok=True)

@app.get("/api/media")
def list_media():
    """List all photos and videos in the flight_data directory."""
    items = []
    allowed_ext = {".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".mp4": "video", ".avi": "video"}
    try:
        for fname in sorted(os.listdir(MEDIA_DIR), reverse=True):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in allowed_ext:
                continue
            fpath = os.path.join(MEDIA_DIR, fname)
            stat = os.stat(fpath)
            size_kb = stat.st_size / 1024
            size_str = f"{size_kb:.0f} KB" if size_kb < 1024 else f"{size_kb/1024:.1f} MB"
            import datetime
            date_str = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            items.append({
                "id": fname,
                "name": fname,
                "type": allowed_ext[ext],
                "path": fname,  # relative filename, used for serving/deleting
                "date": date_str,
                "size": size_str,
            })
    except Exception as e:
        logger.error(f"Error listing media: {e}")
    return items

@app.get("/api/media/file/{filepath:path}")
def serve_media_file(filepath: str):
    """Serve a media file from the flight_data directory."""
    # Security: resolve and ensure path stays inside MEDIA_DIR
    full_path = os.path.realpath(os.path.join(MEDIA_DIR, filepath))
    if not full_path.startswith(os.path.realpath(MEDIA_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    ext = os.path.splitext(full_path)[1].lower()
    media_type_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                      ".mp4": "video/mp4", ".avi": "video/x-msvideo"}
    return FileResponse(full_path, media_type=media_type_map.get(ext, "application/octet-stream"))

@app.delete("/api/media/{filepath:path}")
def delete_media_file(filepath: str):
    """Delete a media file from the flight_data directory."""
    full_path = os.path.realpath(os.path.join(MEDIA_DIR, filepath))
    if not full_path.startswith(os.path.realpath(MEDIA_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    try:
        os.remove(full_path)
        return {"status": "deleted", "path": filepath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Delete failed: {e}")

@app.post("/api/snapshot")
def take_snapshot():
    """Capture the current video frame and save it as a JPEG photo."""
    if not controller.is_connected or not controller.frame_reader:
        raise HTTPException(status_code=400, detail="Drone not connected or stream not ready")
    frame = controller.frame_reader.frame
    if frame is None or frame.size == 0:
        raise HTTPException(status_code=503, detail="No video frame available")
    try:
        import numpy as np
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        os.makedirs(MEDIA_DIR, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"photo_{timestamp}.jpg"
        out_path = os.path.join(MEDIA_DIR, filename)
        cv2.imwrite(out_path, frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
        logger.info(f"[Snapshot] Saved to {out_path}")
        return {"status": "ok", "filename": filename, "path": filename}
    except Exception as e:
        logger.exception("[Snapshot] Failed to save photo")
        raise HTTPException(status_code=500, detail=f"Snapshot failed: {e}")

# --- Independent Video Recording ---

@app.post("/api/video/start")
def start_video_recording():
    """Start video recording independently (without starting RC flight recorder)."""
    global is_video_recording, video_recorder_thread, video_file_path
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    if is_video_recording:
        return {"status": "already_recording", "path": video_file_path}
    is_video_recording = True
    os.makedirs(MEDIA_DIR, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    video_file_path = os.path.join(MEDIA_DIR, f"video_{timestamp}.mp4")
    video_recorder_thread = threading.Thread(target=video_recorder_loop, args=(video_file_path,), daemon=True)
    video_recorder_thread.start()
    logger.info(f"[Video] Recording started: {video_file_path}")
    return {"status": "recording", "path": video_file_path}

@app.post("/api/video/stop")
def stop_video_recording():
    """Stop video recording."""
    global is_video_recording, video_recorder_thread, video_file_path
    if not is_video_recording:
        return {"status": "not_recording"}
    is_video_recording = False
    if video_recorder_thread is not None:
        video_recorder_thread.join(timeout=3.0)
        video_recorder_thread = None
    saved_path = video_file_path
    logger.info(f"[Video] Recording stopped: {saved_path}")
    return {"status": "stopped", "path": saved_path}

@app.get("/api/video/status")
def video_recording_status():
    return {"is_recording": is_video_recording, "path": video_file_path}

# --- Flight Recorder ---

@app.post("/api/recorder/start")
def start_recording():
    """Start RC flight path recording only (video is controlled separately via /api/video/start)."""
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    recorder.start_recording()
    return {"status": "success", "recording": True}

@app.post("/api/recorder/stop")
def stop_recording():
    """Stop RC flight path recording only."""
    path = recorder.stop_recording()
    return {"status": "success", "path": path}

@app.get("/api/recorder/status")
def recorder_status():
    return {
        "is_recording": recorder.is_recording,
        "is_replaying": recorder.is_replaying,
        "duration": recorder.recording_duration if recorder.is_recording else 0,
    }

@app.get("/api/recorder/list")
def list_recordings():
    return recorder.list_recordings()

class ReplayRequest(BaseModel):
    path: str

def replay_worker_loop():
    global is_replay_running
    logger.info("Replay worker thread started")
    recorder.start_replay()
    
    while is_replay_running and recorder.is_replaying:
        loop_start = time.time()
        
        if not controller.is_connected or not controller.tello:
            logger.warning("[Replay] Drone disconnected, aborting replay")
            break
            
        event = recorder.get_replay_event()
        if event:
            logger.info(f"[Replay] Triggering event: {event}")
            try:
                if event == "takeoff":
                    controller.takeoff()
                    telemetry.notify_takeoff()
                elif event == "land":
                    controller.land()
                    telemetry.notify_land()
            except Exception as e:
                logger.error(f"[Replay] Event {event} failed: {e}")
                
        rc = recorder.get_replay_rc()
        if rc:
            lr, fb, ud, yv = rc
            controller.send_rc_control(lr, fb, ud, yv)
        else:
            break
            
        elapsed = time.time() - loop_start
        sleep_time = max(0.01, 0.05 - elapsed)
        time.sleep(sleep_time)
        
    logger.info("Replay worker thread finished")
    is_replay_running = False
    recorder.stop_replay()
    if controller.is_connected:
        controller.send_stop()

@app.post("/api/recorder/replay")
def start_replay(req: ReplayRequest):
    global is_replay_running, replay_thread
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
        
    stop_replay_session("new replay requested", join=True)
    
    if autopilot.active:
        autopilot.disengage()
        
    loaded = recorder.load_recording(req.path)
    if not loaded:
        raise HTTPException(status_code=404, detail="Recording not found")
        
    is_replay_running = True
    replay_thread = threading.Thread(target=replay_worker_loop, daemon=True)
    replay_thread.start()
    return {"status": "success"}

@app.post("/api/recorder/replay/stop")
def stop_replay():
    stop_replay_session("manual stop", join=False)
    return {"status": "success"}

@app.post("/api/autopilot/toggle")
def toggle_autopilot():
    if not controller.is_connected:
        raise HTTPException(status_code=400, detail="Drone not connected")
    
    if autopilot.active:
        autopilot.disengage()
    else:
        if camera_direction == 1:
            autopilot.engage_downward()
        else:
            autopilot.toggle()
            
    return {
        "status": "success",
        "active": autopilot.active,
        "phase": autopilot.phase_display
    }

frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_frontend")
if not os.path.exists(frontend_path):
    os.makedirs(frontend_path, exist_ok=True)

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404 and not request.url.path.startswith("/api"):
        index_file = os.path.join(frontend_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
    return await http_exception_handler(request, exc)

app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")

is_yolo_working = True
yolo_worker_thread = threading.Thread(target=yolo_worker_loop, daemon=True)
yolo_worker_thread.start()

is_autopilot_running = True
autopilot_thread = threading.Thread(target=autopilot_worker_loop, daemon=True)
autopilot_thread.start()

if __name__ == "__main__":
    import uvicorn
    # Start uvicorn server on port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000)
