from djitellopy import Tello
import time

class DroneController:
    def __init__(self):
        self.tello = Tello()
        self.is_connected = False

    def connect(self):
        """Connects to the Tello drone."""
        try:
            self.tello.connect()
            self.tello.streamoff()
            self.tello.streamon()
            self.is_connected = True
            print(f"Connected. Battery: {self.tello.get_battery()}%")
        except Exception as e:
            print(f"Connection Error: {e}")
            self.is_connected = False

    def takeoff(self):
        """Initiates takeoff if connected and not already flying."""
        if self.is_connected and not self.tello.is_flying:
            self.tello.takeoff()
            time.sleep(1) # Safety buffer

    def land(self):
        """Initiates landing if connected and flying."""
        if self.is_connected and self.tello.is_flying:
            self.tello.land()

    def send_rc_control(self, lr, fb, ud, yv):
        """Sends RC control commands if connected."""
        if self.is_connected:
            try:
                self.tello.send_rc_control(lr, fb, ud, yv)
            except Exception:
                pass # Prevent crashing on transient comms errors

    def cleanup(self):
        """Lands and closes connection."""
        try:
            if self.is_connected and self.tello.is_flying:
                self.tello.land()
        except:
            pass
