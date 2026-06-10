"""
TelemetryService — Periodically polls drone sensors and tracks flight statistics.

Exposes:
    .battery, .height, .speed_x/y/z, .pitch, .roll, .yaw
    .flight_duration_s, .total_distance_cm
    .ip_address, .drone_name
"""

import time
import math
import threading
import logging

logger = logging.getLogger(__name__)


class TelemetryService:
    POLL_INTERVAL = 0.5  # seconds between sensor polls

    def __init__(self):
        # Sensor readings (updated by _poll)
        self.battery = 0
        self.height = 0        # cm (TOF)
        self.speed_x = 0       # cm/s
        self.speed_y = 0
        self.speed_z = 0
        self.pitch = 0         # degrees
        self.roll = 0
        self.yaw = 0
        self.temperature = 0   # °C

        # Flight statistics
        self.flight_duration_s = 0.0
        self.total_distance_cm = 0.0
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.flight_path = []
        self._flight_start_time = None
        self._last_odo_time = None

        # Identity
        self.ip_address = ""
        self.drone_name = ""

        # Internal
        self._tello = None
        self._running = False
        self._thread = None

    def start(self, tello, ip_address="", drone_name=""):
        """Begin polling telemetry from a connected Tello instance."""
        self._tello = tello
        self.ip_address = ip_address
        self.drone_name = drone_name
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("[Telemetry] Started polling (ip=%s, name=%s)", ip_address, drone_name)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("[Telemetry] Stopped")

    def notify_takeoff(self):
        """Call when drone takes off to start flight timer."""
        self._flight_start_time = time.monotonic()
        self._last_odo_time = time.monotonic()
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.flight_path = [{"x": 0.0, "y": 0.0, "z": 0.0, "yaw": 0.0}]
        logger.info("[Telemetry] Flight timer started and positions reset")

    def notify_land(self):
        """Call when drone lands to stop flight timer."""
        if self._flight_start_time:
            self.flight_duration_s += time.monotonic() - self._flight_start_time
        self._flight_start_time = None
        self._last_odo_time = None
        logger.info("[Telemetry] Flight timer stopped. Total: %.1fs, Distance: %.0fcm",
                     self.flight_duration_s, self.total_distance_cm)

    def reset_stats(self):
        """Reset flight duration and distance for a new session."""
        self.flight_duration_s = 0.0
        self.total_distance_cm = 0.0
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.flight_path = []
        self._flight_start_time = None
        self._last_odo_time = None

    @property
    def current_flight_time(self):
        """Returns total flight time including current flight segment."""
        total = self.flight_duration_s
        if self._flight_start_time:
            total += time.monotonic() - self._flight_start_time
        return total

    @property
    def speed_magnitude(self):
        """Returns scalar speed in cm/s."""
        return math.sqrt(self.speed_x**2 + self.speed_y**2 + self.speed_z**2)

    def _poll_loop(self):
        while self._running and self._tello:
            try:
                self.battery = self._tello.get_battery()
                self.height = self._tello.get_distance_tof()
                self.speed_x = self._tello.get_speed_x()
                self.speed_y = self._tello.get_speed_y()
                self.speed_z = self._tello.get_speed_z()
                self.pitch = self._tello.get_pitch()
                self.roll = self._tello.get_roll()
                self.yaw = self._tello.get_yaw()
                try:
                    self.temperature = self._tello.get_temperature()
                except Exception:
                    pass

                # Odometry: integrate speed over time
                now = time.monotonic()
                if self._last_odo_time and self._flight_start_time:
                    dt = now - self._last_odo_time
                    self.total_distance_cm += self.speed_magnitude * dt
                    
                    # Track relative movement (dead reckoning)
                    self.pos_x += self.speed_x * dt
                    self.pos_y += self.speed_y * dt
                    
                    self.flight_path.append({
                        "x": round(self.pos_x, 1),
                        "y": round(self.pos_y, 1),
                        "z": round(self.height, 1),
                        "yaw": round(self.yaw, 1)
                    })
                    if len(self.flight_path) > 2000:
                        self.flight_path.pop(0)
                self._last_odo_time = now

            except Exception:
                # Drone may be disconnecting — don't spam logs
                pass

            time.sleep(self.POLL_INTERVAL)

    def get_osd_lines(self):
        """Returns formatted telemetry strings for OSD display."""
        lines = []
        lines.append(f"BAT: {self.battery}%")
        lines.append(f"ALT: {self.height}cm")
        lines.append(f"SPD: {self.speed_magnitude:.0f}cm/s")
        lines.append(f"P:{self.pitch:+.0f} R:{self.roll:+.0f} Y:{self.yaw:+.0f}")

        ft = self.current_flight_time
        mins, secs = divmod(int(ft), 60)
        lines.append(f"FLT: {mins}:{secs:02d} | {self.total_distance_cm/100:.1f}m")

        if self.drone_name:
            lines.append(f"NAME: {self.drone_name}")

        return lines
