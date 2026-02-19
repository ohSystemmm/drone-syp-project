import pygame
import cv2
import numpy as np
import os
import argparse
import threading
import time
import datetime

from core.drone import DroneController
from vision.detector import ObjectDetector
from vision.sampler import HybridSampler
from ui import Setup 

# NOTE: This Pygame window is a temporary placeholder.
# Backend-focused branch: Kivy is not used here.

SCREEN_WIDTH = 960
SCREEN_HEIGHT = 720
SPEED = 100
YAW_SPEED = 60
UD_SPEED = 60 

class VisionWorker(threading.Thread):
    def __init__(self, controller, detector):
        super().__init__()
        self.controller = controller
        self.detector = detector
        self.running = True
        self.latest_detections = []
        self.conf_threshold = 0.5
        self.sampler = HybridSampler() # Active Learning Sampler
        self.daemon = True # Kill thread if main program exits

    def run(self):
        print("Vision Worker Started (Hybrid Sampling Active)")
        processed_count = 0
        none_count = 0
        while self.running:
            frame = self.controller.get_frame()
            if frame is not None:
                none_count = 0 # Reset
                if self.detector:
                    try:
                        # Run detection at 0.20 to capture uncertainty candidates (0.2-0.6)
                        sampling_threshold = min(0.20, self.conf_threshold)
                        _, all_detections = self.detector.detect(frame, conf_threshold=sampling_threshold, draw_center=False)
                        
                        # Filter for display detections
                        self.latest_detections = [d for d in all_detections if d['conf'] >= self.conf_threshold]
                        
                        # Process sampling (Context + Uncertainty)
                        self.sampler.process_frame(frame, all_detections)
                        
                        processed_count += 1
                        if processed_count % 100 == 0:
                            print(f"[VisionWorker] Heartbeat: Processed {processed_count} frames...")
                            
                    except Exception as e:
                        print(f"Vision Error: {e}")
            else:
                none_count += 1
                if none_count % 300 == 0: # Every ~3 seconds
                    print("[VisionWorker] WARNING: No frames received from drone stream.")
            
            # Prevent CPU pinning
            time.sleep(0.01)
        
        self.sampler.close()

    def stop(self):
        self.running = False

def init_window():
    pygame.init()
    win = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Tello Control Center + AI Vision (Async)")
    return win

def get_keyboard_input(controller, current_threshold):
    lr, fb, ud, yv = 0, 0, 0, 0
    new_threshold = current_threshold
    
    keys = pygame.key.get_pressed()

    # Movement
    if keys[pygame.K_LEFT] or keys[pygame.K_a]: lr = -SPEED
    elif keys[pygame.K_RIGHT] or keys[pygame.K_d]: lr = SPEED

    if keys[pygame.K_UP] or keys[pygame.K_w]: fb = SPEED
    elif keys[pygame.K_DOWN] or keys[pygame.K_s]: fb = -SPEED

    # Altitude
    if keys[pygame.K_SPACE]: ud = UD_SPEED
    elif keys[pygame.K_LSHIFT]: ud = -UD_SPEED

    # Rotation
    if keys[pygame.K_q]: yv = -YAW_SPEED
    elif keys[pygame.K_e]: yv = YAW_SPEED

    # Management
    if keys[pygame.K_t]: controller.takeoff()
    if keys[pygame.K_l]: controller.land()
    
    # Emergency Kill Switch (Issue #17)
    if keys[pygame.K_ESCAPE]: 
        print("!!! EMERGENCY STOP INITIATED !!!")
        controller.emergency()

    # Threshold Adjustment
    if keys[pygame.K_LEFTBRACKET]: new_threshold = max(0.1, current_threshold - 0.01)
    if keys[pygame.K_RIGHTBRACKET]: new_threshold = min(1.0, current_threshold + 0.01)
    
    # 'C' key handled in main event loop for single-press toggle
    return [lr, fb, ud, yv], new_threshold

def draw_detections(frame, detections):
    """
    Draws boxes and centers on the frame manually.
    """
    for d in detections:
        box = d['box']
        x1, y1, x2, y2 = box
        
        # Draw Box (Green)
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        # Draw Center
        cx, cy = d['center']
        cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1) # Red center dot
        
        # Label
        track_id = d.get('track_id')
        id_text = f"ID: {track_id} " if track_id is not None else ""
        label = f"{id_text}{d['name']} {d['conf']:.2f}"
        
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
    return frame

def parse_args():
    parser = argparse.ArgumentParser(description='Tello Drone Control with YOLO')
    parser.add_argument('--model', type=str, choices=['onnx', 'pt', 'auto'], default='auto',
                        help='Force model type: onnx or pt')
    # Connection parameters (Issue #18)
    parser.add_argument('--ip', type=str, default='192.168.10.1', help='Tello IP address')
    parser.add_argument('--port', type=int, default=8889, help='Tello UDP port')
    return parser.parse_args()

def main():
    args = parse_args()
    
    controller = DroneController()
    
    # Attempt connection with specified parameters (Issue #18)
    print(f"Attempting to connect to drone at {args.ip}:{args.port}...")
    controller.connect(host=args.ip, port=args.port)

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

    detector = None
    vision_thread = None

    if selected_path:
        print(f"Loading Model: {selected_path}")
        detector = ObjectDetector(selected_path)
        detector.load_model()
        # Start Vision Thread
        vision_thread = VisionWorker(controller, detector)
        vision_thread.start()
        print("VisionWorker thread started.")
    else:
        print("Warning: Vision disabled (No model found at specified paths).")

    # Setup Video Recording
    rec_dir = "GOOSE/recordings"
    if not os.path.exists("GOOSE"): rec_dir = "recordings" # Run from root
    if not os.path.exists(rec_dir): os.makedirs(rec_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    video_filename = os.path.join(rec_dir, f"flight_{timestamp}.mp4")
    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out_writer = cv2.VideoWriter(video_filename, fourcc, 30.0, (960, 720))
    
    if not out_writer.isOpened():
        print(f"CRITICAL ERROR: Could not initialize VideoWriter at {video_filename}")
    else:
        print(f"Recording video to: {video_filename}")

    win = init_window()
    font = pygame.font.SysFont(None, 24)
    conf_threshold = 0.5
    swap_rb = False 

    run = True
    while run:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_c:
                    swap_rb = not swap_rb
                    print(f"Swapped R/B channels. Now: {'BGR->RGB' if swap_rb else 'Raw'}")

        # 1. Update Threshold in Vision Thread
        if vision_thread:
            vision_thread.conf_threshold = conf_threshold

        # 2. Controls
        rc_vals, conf_threshold = get_keyboard_input(controller, conf_threshold)
        controller.send_rc_control(*rc_vals)

        # 3. Video Display & Recording
        frame = controller.get_frame()
        if frame is not None:
            # RECORD RAW FRAME
            try:
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                out_writer.write(frame_bgr)
            except Exception as e:
                pass

            # Get latest detections from thread
            detections = vision_thread.latest_detections if vision_thread else []
            
            # Prepare for Display
            display_frame = frame.copy() 
            display_frame = draw_detections(display_frame, detections)
            
            if swap_rb:
                display_frame = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            
            # Rotation/Flip for Pygame
            display_frame = np.rot90(display_frame)
            display_frame = np.flipud(display_frame)

            surf = pygame.surfarray.make_surface(display_frame)
            if (surf.get_width() != SCREEN_WIDTH) or (surf.get_height() != SCREEN_HEIGHT):
                surf = pygame.transform.scale(surf, (SCREEN_WIDTH, SCREEN_HEIGHT))
            
            win.blit(surf, (0, 0))

            # OSD
            status_text = "CONNECTED" if controller.is_connected else "DISCONNECTED"
            label = f"Status: {status_text} | IP: {args.ip}:{args.port} | Conf: {conf_threshold:.2f} | ESC for Kill Switch"
            text_surf = font.render(label, True, (255, 0, 0))
            win.blit(text_surf, (10, 10))

        else:
            win.fill((0, 0, 0))
            text = font.render("Waiting for video stream...", True, (255, 255, 255))
            win.blit(text, (SCREEN_WIDTH//2 - 100, SCREEN_HEIGHT//2))

        pygame.display.update()
        pygame.time.delay(16) 

    # Cleanup
    if vision_thread:
        vision_thread.stop()
        vision_thread.join()
    
    if out_writer:
        out_writer.release()
        print("Video Saved.")

    controller.cleanup()
    pygame.quit()

if __name__ == "__main__":
    Setup()
    main()
