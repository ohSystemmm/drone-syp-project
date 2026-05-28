import threading
import logging
import time
from djitellopy import Tello

logger = logging.getLogger(__name__)

class DroneController:
    WATCHDOG_PING_INTERVAL = 3.0   # seconds between heartbeat checks
    WATCHDOG_TIMEOUT = 10.0        # seconds before declaring connection lost

    def __init__(self):
        self.tello = None
        self.is_connected = False
        self.frame_reader = None
        self._is_flying_manual = False
        self._command_in_progress = False
        self._has_taken_off = False
        # RC Throttling state
        self._last_rc_values = (0, 0, 0, 0)
        self._last_rc_time = 0
        self._rc_log_counter = 0
        # Connection watchdog
        self._watchdog_running = False
        self._watchdog_thread = None
        self._last_successful_ping = 0
        self.on_connection_lost = None  # callback: fn() called on disconnect

    def _restart_video_stream(self, reason="manual"):
        """Safely restart video stream and recreate frame reader without UDP port collisions."""
        if not self.tello:
            return False
        logger.warning("[Drone] Restarting video stream (reason=%s)", reason)
        try:
            if self.frame_reader:
                try:
                    self.frame_reader.stop()
                except BaseException:
                    pass
                self.frame_reader = None

            try:
                self.tello.streamoff()
            except BaseException:
                pass

            time.sleep(0.35)
            self.tello.streamon()
            time.sleep(0.35)
            self.frame_reader = self.tello.get_frame_read()
            logger.info("[Drone] Video stream restart succeeded (reason=%s)", reason)
            return True
        except BaseException as e:
            print(f"[Drone] Stream restart failed ({reason}): {e}")
            logger.exception("[Drone] Stream restart failed (reason=%s)", reason)
            return False

    def _is_airborne_by_tof(self, threshold_cm=20, samples=3, delay=0.15):
        """Best-effort airborne check using TOF sensor samples."""
        if not self.tello:
            return False
        hits = 0
        for _ in range(samples):
            try:
                if self.tello.get_distance_tof() > threshold_cm:
                    hits += 1
            except BaseException:
                pass
            time.sleep(delay)
        return hits >= max(1, (samples // 2) + 1)

    @property
    def is_flying(self):
        """Robust flight state: uses manual flag + TOF sensor sanity check."""
        if not self.tello: return False
        try:
            # If height is > 15cm, we are almost certainly flying
            tof_height = self.tello.get_distance_tof()
            return tof_height > 15 or self._is_flying_manual
        except:
            return self._is_flying_manual

    def connect(self, host="192.168.10.1", port=8889):
        """Connects to the Tello drone and starts video stream."""
        self.is_connected = False
        self._is_flying_manual = False
        self._has_taken_off = False
        self._stream_stall_since = None  # Track stream stalls for recovery
        try:
            print(f"Connecting to Tello at {host}...")
            logger.info("[Drone] Connecting to %s:%s", host, port)
            self.tello = Tello(host=host)
            
            # Important: Set a longer timeout for slow Wi-Fi
            self.tello.RESPONSE_TIMEOUT = 10.0
            
            self.tello.connect()
            print(f"Connected to {host}. Battery: {self.tello.get_battery()}%")
            logger.info("[Drone] Connected. Battery=%s%%", self.tello.get_battery())
            
            # Configure video for reliability before starting stream
            print("Initializing video stream...")
            self.tello.streamoff()
            time.sleep(0.5)

            # Set resolution and FPS BEFORE streamon for consistent behavior
            self.tello.set_video_resolution(Tello.RESOLUTION_720P)
            # 30 FPS ensures PyAV gets enough frames to start decoding without throwing ExitError
            self.tello.set_video_fps(Tello.FPS_30)
            # Bitrate fallback: some firmware/AP combos reject specific bitrate commands.
            bitrate_set = False
            for bitrate in (Tello.BITRATE_3MBPS, Tello.BITRATE_2MBPS, Tello.BITRATE_1MBPS):
                try:
                    self.tello.set_video_bitrate(bitrate)
                    bitrate_set = True
                    logger.info("[Drone] Video bitrate set to %s", bitrate)
                    break
                except BaseException:
                    logger.debug("[Drone] Video bitrate command failed for %s", bitrate)
                    continue
            if not bitrate_set:
                print("[Drone] Warning: Could not set requested video bitrate; using drone default.")

            self.tello.streamon()
            
            self.frame_reader = self.tello.get_frame_read()
            
            # Wait for first frame to verify stream
            for _ in range(20):
                if self.frame_reader.frame is not None:
                    print("Video stream ready.")
                    logger.info("[Drone] Video stream ready")
                    self.is_connected = True
                    self._start_watchdog()
                    return True
                time.sleep(0.2)
            
            print("Warning: Connected but video stream timed out.")
            logger.warning("[Drone] Connected but video stream timed out")
            self.is_connected = True
            self._start_watchdog()
            return True
                
        except BaseException as e:
            if "Command 'command' was unsuccessful" in str(e):
                logger.error("[Drone] Connection failed: Drone not found or not in SDK mode (No response to 'command')")
            else:
                logger.exception("[Drone] Connection failed")
            
            self.is_connected = False
            self.tello = None # Clear stale object
            return False

    def _start_watchdog(self):
        """Start background watchdog that pings the drone periodically."""
        self._watchdog_running = True
        self._last_successful_ping = time.time()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()
        logger.info("[Drone] Connection watchdog started")

    def _stop_watchdog(self):
        self._watchdog_running = False

    def _watchdog_loop(self):
        while self._watchdog_running and self.is_connected:
            try:
                # Try to get battery — cheapest SDK ping
                bat = self.tello.get_battery()
                if bat is not None:
                    self._last_successful_ping = time.time()
            except Exception:
                pass

            # Check if we've timed out
            elapsed = time.time() - self._last_successful_ping
            if elapsed > self.WATCHDOG_TIMEOUT and self.is_connected:
                logger.critical("[Drone] CONNECTION LOST — no response for %.1fs. Auto-landing.", elapsed)
                print(f"[Drone] CONNECTION LOST — auto-landing!")
                self._emergency_auto_land()
                if self.on_connection_lost:
                    try:
                        self.on_connection_lost()
                    except Exception:
                        pass
                break

            time.sleep(self.WATCHDOG_PING_INTERVAL)

    def _emergency_auto_land(self):
        """Best-effort landing when connection is degraded."""
        try:
            if self._is_flying_manual or self._has_taken_off:
                self.tello.land()
                self._is_flying_manual = False
                self._has_taken_off = False
                logger.info("[Drone] Emergency auto-land executed")
        except Exception:
            logger.exception("[Drone] Emergency auto-land failed")

    def disconnect(self):
        """Stops video stream and disconnects."""
        try:
            if self.frame_reader:
                try:
                    self.frame_reader.stop()
                except BaseException:
                    pass
            if self.tello:
                try:
                    self.tello.streamoff()
                except BaseException:
                    pass
                if hasattr(self.tello, "is_flying"):
                    self.tello.is_flying = False
                try:
                    self.tello.end()
                except BaseException:
                    pass
        except Exception as e:
            print(f"Disconnect error: {e}")
            logger.exception("[Drone] Disconnect error")
        finally:
            self.is_connected = False
            self.frame_reader = None
            self._is_flying_manual = False
            self._has_taken_off = False

    def emergency(self):
        """Immediate motor cutoff (Kill Switch)."""
        try:
            if self.tello:
                self.tello.emergency()
        except BaseException as e:
            print(f"Emergency command failed: {e}")
            logger.exception("[Drone] Emergency command failed")
        finally:
            self.is_connected = False
            logger.warning("[Drone] Emergency triggered")

    def takeoff(self):
        """Initiates takeoff in a non-blocking background thread."""
        if not self.is_connected or self.is_flying or self._command_in_progress or self._has_taken_off:
            return
        
        def _exec():
            self._command_in_progress = True
            print("[Drone] Executing TAKEOFF...")
            logger.info("[Drone] TAKEOFF start")
            try:
                takeoff_ok = False
                last_error = None
                for attempt in range(2):
                    logger.debug("[Drone] TAKEOFF attempt=%d", attempt + 1)
                    try:
                        self.tello.takeoff()
                        takeoff_ok = True
                        logger.info("[Drone] TAKEOFF command acknowledged")
                        break
                    except BaseException as e:
                        last_error = e
                        # If command ACK is lost but drone actually lifted, accept it.
                        if self._is_airborne_by_tof():
                            takeoff_ok = True
                            print("[Drone] TAKEOFF ACK missing, but TOF indicates airborne.")
                            logger.warning("[Drone] TAKEOFF ACK missing, TOF indicates airborne")
                            break
                        time.sleep(0.6)

                if takeoff_ok:
                    self._is_flying_manual = True
                    self._has_taken_off = True
                    logger.info("[Drone] TAKEOFF complete")
                else:
                    print(f"Takeoff Error: {last_error}")
                    logger.error("[Drone] TAKEOFF failed: %s", last_error)
            except BaseException as e:
                print(f"Takeoff Error: {e}")
                logger.exception("[Drone] TAKEOFF exception")
            finally:
                self._command_in_progress = False

        threading.Thread(target=_exec, daemon=True).start()

    def land(self):
        """Initiates landing in a non-blocking background thread."""
        if not self.is_connected or not self.is_flying or self._command_in_progress:
            return

        def _exec():
            self._command_in_progress = True
            print("[Drone] Executing LAND...")
            logger.info("[Drone] LAND start")
            try:
                self.tello.land()
                self._is_flying_manual = False
                self._has_taken_off = False # Reset on manual land
                logger.info("[Drone] LAND complete")
            except BaseException as e:
                print(f"Land Error: {e}")
                logger.exception("[Drone] LAND failed")
            finally:
                self._command_in_progress = False

        threading.Thread(target=_exec, daemon=True).start()

    def send_rc_control(self, lr, fb, ud, yv):
        """
        Sends RC control commands if connected.
        Throttled to max 20Hz (50ms) to prevent UDP flooding the drone.
        """
        if not (self.is_connected and self.tello) or self._command_in_progress:
            return

        now = time.time()
        current_values = (lr, fb, ud, yv)

        time_since_last = now - self._last_rc_time
        if (current_values != self._last_rc_values and time_since_last >= 0.05) or time_since_last > 0.2:
            try:
                self.tello.send_rc_control(lr, fb, ud, yv)
                self._last_rc_values = current_values
                self._last_rc_time = now
                self._rc_log_counter += 1
                if self._rc_log_counter % 25 == 0:
                    logger.debug("[Drone] RC sent lr=%d fb=%d ud=%d yv=%d", lr, fb, ud, yv)
            except BaseException:
                pass

    def get_frame(self):
        """
        Returns the most recent video frame from the drone.
        Includes automatic stream recovery if frames stall for >3 seconds.
        """
        if not self.frame_reader:
            return None

        frame = self.frame_reader.frame
        now = time.time()

        if frame is not None:
            self._stream_stall_since = None
            return frame

        # Track how long we've had no frames
        if self._stream_stall_since is None:
            self._stream_stall_since = now
        elif now - self._stream_stall_since > 3.0 and self.is_connected and self.tello:
            # Stream has stalled for 3+ seconds — force IDR keyframe via stream restart
            print("[Drone] Stream stall detected — restarting video stream...")
            logger.warning("[Drone] Stream stall detected")
            ok = self._restart_video_stream(reason="stall")
            if ok:
                self._stream_stall_since = now  # Reset timer to avoid rapid retries

        return None

    def flip(self, direction):
        """Commands the drone to flip in the specified direction."""
        if not (self.is_connected and self.tello) or self._command_in_progress:
            return

        try:
            if direction in ['l', 'r', 'f', 'b']:
                self.tello.flip(direction)
        except BaseException as e:
            print(f"Flip failed: {e}")

    def set_camera_direction(self, direction):
        """
        Switch camera direction.
        direction: 0 = forward/RGB (1080x720), 1 = downward/IR (320x240)
        Returns True if successful.

        NOTE: Does NOT restart video stream to avoid H.264 decoder corruption
        when switching between different resolutions.
        """
        if not (self.is_connected and self.tello):
            logger.warning("[Drone] Cannot switch camera — not connected")
            return False

        try:
            logger.info("[Drone] Switching camera to direction=%d", direction)
            self.tello.set_video_direction(direction)
            time.sleep(1.0)  # Give camera time to switch and stabilize
            logger.info("[Drone] Camera switch successful")
            return True
        except BaseException as e:
            logger.exception("[Drone] Camera switch failed: %s", e)
            print(f"[Drone] Camera switch failed: {e}")
            return False

    def cleanup(self):
        """Lands and closes connection."""
        self._stop_watchdog()
        try:
            if self.frame_reader:
                try:
                    self.frame_reader.stop()
                except BaseException:
                    pass
            if self.is_connected and self.tello:
                try:
                    self.tello.send_rc_control(0, 0, 0, 0)
                except BaseException:
                    pass

                was_flying = self.is_flying
                if was_flying:
                    if self._is_airborne_by_tof(samples=2):
                        landed = False
                        for attempt in range(2):
                            try:
                                self.tello.land()
                                landed = True
                                logger.info("[Drone] Cleanup land succeeded (attempt=%d)", attempt + 1)
                                break
                            except BaseException as e:
                                # If command fails but TOF shows we are already down, treat as success.
                                if not self._is_airborne_by_tof(samples=2):
                                    landed = True
                                    logger.warning("[Drone] Cleanup land ACK failed but TOF indicates landed")
                                    break
                                if attempt == 1:
                                    print(f"[Cleanup] Land failed: {e}")
                                    logger.exception("[Drone] Cleanup land failed")
                        if not landed:
                            logger.warning("[Drone] Cleanup land unresolved after retries")

                self._is_flying_manual = False
                self._has_taken_off = False
                if hasattr(self.tello, "is_flying"):
                    self.tello.is_flying = False

                try:
                    self.tello.streamoff()
                except BaseException:
                    pass
                try:
                    self.tello.end()
                except BaseException:
                    pass
        except Exception as e:
            print(f"[Cleanup] Error: {e}")
            logger.exception("[Drone] Cleanup error")
        finally:
            self.is_connected = False
            self.frame_reader = None
            self._is_flying_manual = False
            self._has_taken_off = False
            logger.info("[Drone] Cleanup complete")

