from djitellopy import Tello
import time

class DroneController:
    def __init__(self):
        self.tello = None
        self.is_connected = False
        self.frame_reader = None

    def connect(self, host="192.168.10.1", port=8889):
        """Connects to the Tello drone and starts video stream with optimizations."""
        try:
            self.tello = Tello(host=host, port=port)
            self.tello.connect()
            print(f"Connected to {host}:{port}. Battery: {self.tello.get_battery()}%")
            
            # --- VIDEO OPTIMIZATIONS ---
            # Set to max quality as suggested
            self.tello.set_video_bitrate(Tello.BITRATE_5MBPS)
            self.tello.set_video_resolution(Tello.RESOLUTION_720P)
            
            self.tello.streamoff() # Reset stream
            self.tello.streamon()
            
            # Stabilization delay: Tello needs a moment to start the UDP stream 
            # before the frame reader attempts to grab the first frame.
            print("Starting video stream, waiting for stabilization...")
            time.sleep(2.0) 
            
            # Background thread that captures frames
            self.frame_reader = self.tello.get_frame_read()
            
            # Test frame grab
            if self.frame_reader.frame is not None:
                self.is_connected = True
                print("Video stream initialized successfully.")
            else:
                print("Warning: Stream initialized but no frames received yet.")
                self.is_connected = True # Still connected, might just need more time
                
        except Exception as e:
            print(f"Connection Error: {e}")
            self.is_connected = False

    def disconnect(self):
        """Stops video stream and disconnects."""
        try:
            if self.frame_reader:
                self.frame_reader.stop()
            if self.tello:
                self.tello.streamoff()
                self.tello.end()
        except Exception as e:
            print(f"Disconnect error: {e}")
        finally:
            self.is_connected = False
            self.frame_reader = None

    def emergency(self):
        """Immediate motor cutoff (Kill Switch)."""
        try:
            if self.tello:
                self.tello.emergency()
        except Exception as e:
            print(f"Emergency command failed: {e}")
        finally:
            self.is_connected = False

    def takeoff(self):
        """Initiates takeoff if connected and not already flying."""
        if self.is_connected and self.tello and not self.tello.is_flying:
            self.tello.takeoff()

    def land(self):
        """Initiates landing if connected and flying."""
        if self.is_connected and self.tello and self.tello.is_flying:
            self.tello.land()

    def send_rc_control(self, lr, fb, ud, yv):
        """Sends RC control commands if connected."""
        if self.is_connected and self.tello:
            try:
                self.tello.send_rc_control(lr, fb, ud, yv)
            except Exception:
                pass # Prevent crashing on transient comms errors

    def get_frame(self):
        """Returns the most recent video frame from the drone (NumPy array)."""
        if self.frame_reader:
            return self.frame_reader.frame
        return None

    def cleanup(self):
        """Lands and closes connection."""
        try:
            if self.frame_reader:
                self.frame_reader.stop()
            if self.is_connected and self.tello:
                if self.tello.is_flying:
                    self.tello.land()
                self.tello.end()
        except:
            pass
