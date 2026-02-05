import cv2
import os
import time
from concurrent.futures import ThreadPoolExecutor

class HybridSampler:
    """
    Implements Hybrid Sampling for Active Learning.
    - Context Collection: Saves frames at a fixed interval (e.g., 5 FPS).
    - Uncertainty Collection: Saves frames where model confidence is between 0.20 and 0.60.
    """
    def __init__(self, base_dir="./flight_data", context_fps=5, stream_fps=30):
        # Use absolute path to avoid confusion about where files are being saved
        self.base_dir = os.path.abspath(base_dir)
        self.context_dir = os.path.join(self.base_dir, "context")
        self.uncertain_dir = os.path.join(self.base_dir, "uncertain")
        
        os.makedirs(self.context_dir, exist_ok=True)
        os.makedirs(self.uncertain_dir, exist_ok=True)
        
        print(f"[Sampler] Initialized. Saving to: {self.base_dir}")
        
        # Calculate frame interval to achieve desired context FPS
        self.context_interval = max(1, int(stream_fps / context_fps))
        self.frame_count = 0
        
        # Use a ThreadPoolExecutor for lightweight, non-blocking disk writes
        self.executor = ThreadPoolExecutor(max_workers=2)

    def _save_image(self, path, frame_rgb):
        """Helper to save image in background. Converts RGB to BGR for OpenCV."""
        try:
            # Tello frames from djitellopy are RGB
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
            success = cv2.imwrite(path, frame_bgr)
            if not success:
                print(f"[Sampler] Failed to write image to {path}")
            # Success is silent to avoid flooding the console, 
            # but you can add a print here if you want to see every save.
        except Exception as e:
            print(f"[Sampler] Error saving image: {e}")

    def process_frame(self, frame, detections):
        """
        Main entry point for sampling logic. Call this within your inference loop.
        :param frame: The raw video frame (numpy array).
        :param detections: List of detection dicts.
        """
        self.frame_count += 1
        timestamp = int(time.time())
        
        # 1. Context Collection (Fixed FPS)
        if self.frame_count % self.context_interval == 0:
            context_path = os.path.join(self.context_dir, f"context_{timestamp}_{self.frame_count}.jpg")
            self.executor.submit(self._save_image, context_path, frame.copy())

        # 2. Uncertainty Collection (Confidence between 0.20 and 0.60)
        uncertain_detections = [d for d in detections if 0.20 <= d.get('conf', 0) <= 0.60]
        
        if uncertain_detections:
            best_conf = uncertain_detections[0]['conf']
            uncertain_path = os.path.join(
                self.uncertain_dir, 
                f"uncertain_{best_conf:.2f}_{timestamp}.jpg"
            )
            print(f"[Sampler] Uncertainty Trigger! Conf: {best_conf:.2f}. Saving frame...")
            self.executor.submit(self._save_image, uncertain_path, frame.copy())

    def close(self):
        """Shut down the background executor."""
        print("[Sampler] Shutting down...")
        self.executor.shutdown(wait=True) # Wait for final writes on exit