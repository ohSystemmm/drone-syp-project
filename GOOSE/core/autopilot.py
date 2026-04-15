"""
AutoPilot — Simplified finite-state controller for autonomous ring flight.

Phases:
    ALIGN    — Center the target in frame (X/Y) and close to working distance (Z).
               Y-target is offset upward to compensate for the Tello's downward camera tilt.
    APPROACH — Push forward while maintaining alignment.
    PUNCH    — Full-speed burst through the ring.
    DONE     — Motors idle after punch completes.

Design principles:
    - Let the Kalman filter in PositionEstimator handle smoothing; don't re-filter here.
    - Minimal gating: if we have a pose, use it. If we don't, stop and search.
    - PID controllers do the heavy lifting. No orbit mechanics, no pitch compensation.
    - Bbox fallback provides coarse control when full pose is unavailable.
"""

import logging
import math
import time

logger = logging.getLogger(__name__)


class PIDController:
    """PID controller with output clamping and derivative low-pass filter."""

    def __init__(self, kp, ki, kd, output_limit=60):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.output_limit = output_limit
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None
        self._d_filtered = 0.0

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0
        self._prev_time = None
        self._d_filtered = 0.0

    def set_gains(self, kp, ki, kd, output_limit=None):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        if output_limit is not None:
            self.output_limit = output_limit
        self.reset()

    def compute(self, error):
        now = time.monotonic()
        if self._prev_time is None:
            dt = 0.03
        else:
            dt = max(now - self._prev_time, 0.001)
        self._prev_time = now

        p = self.kp * error
        self._integral += error * dt
        max_integral = self.output_limit / max(self.ki, 0.001)
        self._integral = max(-max_integral, min(max_integral, self._integral))
        i = self.ki * self._integral

        d_raw = (error - self._prev_error) / dt
        self._d_filtered = 0.3 * d_raw + 0.7 * self._d_filtered
        d = self.kd * self._d_filtered
        self._prev_error = error

        output = p + i + d
        return max(-self.output_limit, min(self.output_limit, output))


# --- Phase constants ---
PHASE_ALIGN = "ALIGN"
PHASE_APPROACH = "APPROACH"
PHASE_PUNCH = "PUNCH"
PHASE_DONE = "DONE"


class AutoPilot:
    """
    Simplified autopilot.  Three active phases, one set of PID controllers,
    minimal gating.
    """

    # --- Tuning knobs (all distances in cm, angles in degrees) ---

    # ALIGN: where we want to be before approaching
    ALIGN_DISTANCE = 100.0          # Target Z to hold during alignment
    ALIGN_X_TOL = 25.0              # X error tolerance for "centered"
    ALIGN_Y_TOL = 25.0              # Y error tolerance for "centered"
    ALIGN_Z_TOL = 50.0              # Z error tolerance for "at distance" (wide: Z_SCALE may be uncalibrated)
    ALIGN_ANGLE_TOL = 45.0          # Max acceptable tilt angle (reduced from 70° to ensure ring is upright)
    ALIGN_HOLD_TIME = 0.7           # Seconds target must stay aligned (increased from 0.3 for stability)
    ALIGN_MIN_CONF = 0.25           # Minimum confidence to proceed with alignment (safety threshold)

    # APPROACH: closing the distance
    APPROACH_SPEED = 80             # Forward speed at max distance
    APPROACH_MIN_SPEED = 20         # Forward speed at min distance
    APPROACH_TIMEOUT = 10.0         # Seconds before giving up and re-aligning (increased to give more time)
    APPROACH_RECENTER_XY = 40.0     # XY error that triggers re-align (relaxed from 30cm)
    APPROACH_RECENTER_TIME = 1.5    # Seconds of bad centering before reset (increased from 0.4s)
    APPROACH_DRIFT_MIN_FB = 12      # Minimum forward speed to maintain progress even when off-center

    # PUNCH: final burst
    PUNCH_DISTANCE = 80.0           # Z below which we commit to punch
    PUNCH_SPEED = 100               # Forward speed during punch
    PUNCH_DURATION = 2.5            # Seconds of forward push
    PUNCH_CONF_MIN = 0.35           # Min confidence to enter punch (lowered to 0.35 to match tracking minimum)
    PUNCH_LOCK_TIME = 0.5           # Seconds of lock before punch triggers (increased from 0.2 for stability)

    # APPROACH vertical control (preventing 1-meter dive when ring fills frame)
    APPROACH_Y_DEADZONE = 40.0      # Larger deadzone for vertical during approach (vs 4cm in align)
    Y_ERROR_MAX = 50.0               # Cap on Y error to prevent extreme commands from miscalibration
    RING_FILL_THRESHOLD = 0.65       # bbox_ratio > this = ring fills frame, freeze vertical

    # General control
    MAX_SPEED = 80                  # Global PID output limit
    MIN_SPEED = 12                  # Tello deadzone floor
    DEADZONE = 4.0                  # Error deadzone (cm)

    # Tracking limits
    TRACKING_TIMEOUT = 0.5          # Seconds without pose before entering search
    TRACKING_MIN_CONF = 0.30        # Minimum usable pose confidence
    TRACKING_MIN_DIST = 15.0        # Minimum usable Z
    TRACKING_MAX_DIST = 400.0       # Maximum usable Z

    # Search behavior
    SEARCH_DELAY = 1.5              # Seconds before starting yaw search
    SEARCH_YAW_SPEED = 15           # Yaw speed during search

    # Camera tilt compensation — Tello camera points downward at ~11°.
    # The ring must appear in the upper ~25-40% of frame to be at the drone's
    # true flight-path center.  The Y correction scales with Z distance:
    #   y_correction = z_cm * tan(tilt_deg)
    CAMERA_TILT_DEG = 11.0

    # Target position (frame-center = 0,0)
    TARGET_X = 0.0
    TARGET_Y = 0.0

    def __init__(self):
        self.active = False
        self.phase = PHASE_ALIGN

        # Timing state
        self._last_pose_time = 0.0
        self._align_stable_since = None
        self._punch_start_time = None
        self._approach_start_time = None
        self._punch_lock_since = None
        self._recenter_since = None
        self._no_track_since = None

        # Last outputs (used for punch decay)
        self._last_lr = 0
        self._last_ud = 0

        # Logging throttle
        self._last_log_time = 0.0

        # PID controllers
        self.pid_lr = PIDController(kp=0.6, ki=0.005, kd=0.5, output_limit=self.MAX_SPEED)
        self.pid_ud = PIDController(kp=0.8, ki=0.005, kd=0.4, output_limit=self.MAX_SPEED)
        self.pid_fb = PIDController(kp=0.7, ki=0.01,  kd=0.1, output_limit=self.MAX_SPEED)
        self.pid_yaw = PIDController(kp=0.35, ki=0.005, kd=0.05, output_limit=30)

    # --- Public interface ---

    @property
    def phase_display(self):
        return self.phase if self.active else "OFF"

    def toggle(self):
        self.active = not self.active
        if self.active:
            self._reset_all()
            print("[AutoPilot] ENGAGED — Phase: ALIGN")
            logger.info("[AutoPilot] ENGAGED")
        else:
            print("[AutoPilot] DISENGAGED — Manual control active")
            logger.info("[AutoPilot] DISENGAGED")
        return self.active

    def disengage(self):
        if self.active:
            self.active = False
            self._reset_all()
            print("[AutoPilot] DISENGAGED (manual override)")
            logger.info("[AutoPilot] DISENGAGED (manual override)")

    def compute(self, pose, bbox_center=None, bbox_ratio=None):
        """
        Main entry point.  Returns (lr, fb, ud, yv) RC command tuple.
        Called once per new frame from the main loop.
        """
        if not self.active:
            return 0, 0, 0, 0

        now = time.monotonic()

        # PUNCH runs open-loop — no pose needed
        if self.phase == PHASE_PUNCH:
            return self._compute_punch(now)

        if self.phase == PHASE_DONE:
            return 0, 0, 0, 0

        # --- Pose validation ---
        if pose is not None:
            usable, reason = self._is_pose_usable(pose)
            if not usable:
                pose = None  # Fall through to no-tracking path

        # --- Pose/bbox cross-check ---
        if pose is not None and bbox_center is not None:
            bbox_err_x = bbox_center[0] - 480
            if abs(bbox_err_x) > 80 and abs(pose.x_cm) > 5.0:
                # If bbox and pose disagree on which side the target is, trust bbox
                if (bbox_err_x > 0) != (pose.x_cm > 0):
                    logger.warning(
                        "[AutoPilot] Pose/bbox disagree: bbox_cx=%d vs pose_x=%.1f — bbox fallback",
                        bbox_center[0], pose.x_cm,
                    )
                    return self._compute_bbox_fallback(bbox_center)

        # --- No usable pose ---
        if pose is None:
            if bbox_center is not None:
                return self._compute_bbox_fallback(bbox_center)
            return self._handle_no_tracking(now)

        # --- We have a valid pose ---
        self._last_pose_time = now
        self._no_track_since = None

        if self.phase == PHASE_ALIGN:
            cmd = self._compute_align(pose, now)
        elif self.phase == PHASE_APPROACH:
            cmd = self._compute_approach(pose, now, bbox_ratio)
        else:
            cmd = (0, 0, 0, 0)

        self._log_state(pose, cmd, now)
        return cmd

    # --- Phase: ALIGN ---

    def _compute_align(self, pose, now):
        x_err = pose.x_cm - self.TARGET_X
        y_err = pose.y_cm - self.TARGET_Y - self._tilt_offset(pose.z_cm)
        z_err = pose.z_cm - self.ALIGN_DISTANCE

        x_dz = self._apply_deadzone(x_err, self.DEADZONE)
        y_dz = self._apply_deadzone(y_err, self.DEADZONE)
        z_dz = self._apply_deadzone(z_err, self.DEADZONE)

        lr = self._apply_min_speed(self.pid_lr.compute(x_dz))
        ud_raw = self._apply_min_speed(-self.pid_ud.compute(y_dz))
        fb = self._apply_min_speed(self.pid_fb.compute(z_dz))

        # Rate-limit UD to prevent violent dives when pose first appears
        MAX_UD_CHANGE = 15
        ud = int(max(self._last_ud - MAX_UD_CHANGE, min(self._last_ud + MAX_UD_CHANGE, ud_raw)))

        # Yaw tracks X error to face the target
        # Decouple: if large X error, use yaw only (no strafe) to avoid oscillation
        yaw_dz = self._apply_deadzone(x_err, self.DEADZONE)
        if abs(x_err) > self.ALIGN_X_TOL * 2:
            yv = self._apply_min_speed(self.pid_yaw.compute(yaw_dz))
            lr = 0  # Let yaw handle it, don't also strafe
        else:
            yv = 0
            self.pid_yaw.reset()

        # Don't push forward unless reasonably centered
        if abs(x_err) > self.ALIGN_X_TOL * 2 or abs(y_err) > self.ALIGN_Y_TOL * 2:
            fb = 0

        # Check alignment
        aligned = (
            abs(x_err) < self.ALIGN_X_TOL
            and abs(y_err) < self.ALIGN_Y_TOL
            and abs(z_err) < self.ALIGN_Z_TOL
            and pose.angle_deg < self.ALIGN_ANGLE_TOL
            and pose.confidence >= self.ALIGN_MIN_CONF
        )

        if aligned:
            if self._align_stable_since is None:
                self._align_stable_since = now
            elif (now - self._align_stable_since) >= self.ALIGN_HOLD_TIME:
                self._transition_to_approach()
        else:
            self._align_stable_since = None

        self._last_lr = lr
        self._last_ud = ud
        return lr, fb, ud, yv

    # --- Phase: APPROACH ---

    def _compute_approach(self, pose, now, bbox_ratio=None):
        if self._approach_start_time is None:
            self._approach_start_time = now

        # How far we still need to go (0.0 = at punch distance, 1.0 = at align distance)
        z_remaining = max(0.0, pose.z_cm - self.PUNCH_DISTANCE)
        approach_range = max(self.ALIGN_DISTANCE - self.PUNCH_DISTANCE, 1.0)
        dist_frac = min(1.0, z_remaining / approach_range)

        # Forward speed scales with distance
        fb = int(self.APPROACH_MIN_SPEED + (self.APPROACH_SPEED - self.APPROACH_MIN_SPEED) * dist_frac)

        # XY correction — tighter PID gains for approach
        x_err = pose.x_cm - self.TARGET_X
        y_err = pose.y_cm - self.TARGET_Y - self._tilt_offset(pose.z_cm)

        x_dz = self._apply_deadzone(x_err, self.DEADZONE)
        y_dz = self._apply_deadzone(y_err, self.DEADZONE)
        yaw_dz = self._apply_deadzone(x_err, self.DEADZONE)

        lr = self._apply_min_speed(self.pid_lr.compute(x_dz))
        yv = self._apply_min_speed(self.pid_yaw.compute(yaw_dz))

        # --- Vertical control with ring-fill detection ---
        # If ring fills the frame (large bbox_ratio), freeze vertical position.
        # This prevents the ~1 meter dive that occurs when PID tries to correct
        # based on miscalibrated distance or frame geometry.
        ring_is_large = bbox_ratio is not None and bbox_ratio > self.RING_FILL_THRESHOLD

        if ring_is_large:
            # Ring fills frame → altitude is likely OK, don't adjust vertically
            ud = 0
            logger.debug("[AutoPilot|APPROACH] Ring is large (ratio=%.2f) → freezing UD", bbox_ratio)
        else:
            # Ring is small/distant → use normal PID but with increased deadzone
            y_dz_approach = self._apply_deadzone(y_err, self.APPROACH_Y_DEADZONE)
            # Cap Y error to prevent extreme commands from miscalibrated systems
            y_dz_approach = max(-self.Y_ERROR_MAX, min(self.Y_ERROR_MAX, y_dz_approach))
            ud = self._apply_min_speed(-self.pid_ud.compute(y_dz_approach))

        # Slow down if we're off-center, but maintain minimum forward motion
        xy_err = math.hypot(x_err, y_err)
        if xy_err > self.APPROACH_RECENTER_XY:
            fb = max(self.APPROACH_DRIFT_MIN_FB, fb // 2)  # Reduce forward speed but keep moving

        self._last_lr = lr
        self._last_ud = ud

        # --- Re-center check: if way off for too long, go back to ALIGN ---
        if xy_err > self.APPROACH_RECENTER_XY:
            if self._recenter_since is None:
                self._recenter_since = now
            elif (now - self._recenter_since) >= self.APPROACH_RECENTER_TIME:
                logger.warning("[AutoPilot] Off-center for too long -> ALIGN (xy_err=%.1f)", xy_err)
                self._reset_to_align()
                return 0, 0, 0, 0
        else:
            self._recenter_since = None

        # --- Approach timeout ---
        if (now - self._approach_start_time) >= self.APPROACH_TIMEOUT:
            logger.warning("[AutoPilot] APPROACH timeout -> ALIGN")
            self._reset_to_align()
            return 0, 0, 0, 0

        # --- Punch lock: at close range with good tracking ---
        if pose.z_cm <= self.PUNCH_DISTANCE and pose.confidence >= self.PUNCH_CONF_MIN:
            if self._punch_lock_since is None:
                self._punch_lock_since = now
            elif (now - self._punch_lock_since) >= self.PUNCH_LOCK_TIME:
                self.phase = PHASE_PUNCH
                self._punch_start_time = now
                logger.info("[AutoPilot] APPROACH -> PUNCH at z=%.1f conf=%.2f", pose.z_cm, pose.confidence)
                return lr, self.PUNCH_SPEED, ud, 0
        else:
            self._punch_lock_since = None

        return lr, fb, ud, yv

    # --- Phase: PUNCH ---

    def _compute_punch(self, now):
        elapsed = now - self._punch_start_time
        if elapsed >= self.PUNCH_DURATION:
            self.phase = PHASE_DONE
            logger.info("[AutoPilot] PUNCH complete -> DONE")
            return 0, 0, 0, 0

        # Decay lateral corrections as we punch through
        decay = max(0.0, 1.0 - elapsed / self.PUNCH_DURATION)
        lr = int(self._last_lr * decay * 0.3)
        ud = int(self._last_ud * decay * 0.3)
        return lr, self.PUNCH_SPEED, ud, 0

    # --- Bbox fallback ---

    def _compute_bbox_fallback(self, bbox_center):
        """Proportional control when only the bounding box is available.
        Yaw and strafe are decoupled to prevent oscillation."""
        cx, cy = bbox_center
        err_x = cx - 480
        # Gentle upward offset for camera tilt (80px ≈ upper 39%)
        target_y = int(360 - 80)
        err_y = cy - target_y

        # Vertical correction — gentle gain, capped, and rate-limited
        ud_raw = int(self._apply_deadzone(err_y, 20) * -0.20)
        ud_raw = max(-20, min(20, ud_raw))
        # Rate-limit UD to prevent violent dives
        MAX_UD_CHANGE = 10
        ud = int(max(self._last_ud - MAX_UD_CHANGE, min(self._last_ud + MAX_UD_CHANGE, ud_raw)))
        if ud != 0 and abs(ud) < self.MIN_SPEED:
            ud = self.MIN_SPEED if ud > 0 else -self.MIN_SPEED

        # Decouple lateral vs yaw:
        #   Large X error (>60px): yaw only — rotate to face the target
        #   Small X error (<60px): strafe only — fine-tune position
        abs_x = abs(err_x)
        if abs_x > 60:
            lr = 0
            yv = int(self._apply_deadzone(err_x, 25) * 0.15)
            yv = self._apply_min_speed(max(-30, min(30, yv)))
        else:
            yv = 0
            lr = int(self._apply_deadzone(err_x, 15) * 0.25)
            lr = self._apply_min_speed(max(-self.MAX_SPEED, min(self.MAX_SPEED, lr)))

        # Nudge forward if target is roughly centered
        fb = 15 if abs_x < 50 and abs(err_y) < 50 else 0

        self._last_ud = ud

        logger.debug(
            "[AutoPilot|BBOX] center=%s err=(%d,%d) cmd=(lr=%d, fb=%d, ud=%d, yv=%d)",
            bbox_center, err_x, err_y, lr, fb, ud, yv,
        )
        return lr, fb, ud, yv

    # --- No tracking / search ---

    def _handle_no_tracking(self, now):
        """No pose and no bbox.  Wait, then slowly yaw to search."""
        self._align_stable_since = None
        self._punch_lock_since = None
        self._recenter_since = None

        if self._no_track_since is None:
            self._no_track_since = now

        time_lost = now - self._no_track_since
        if time_lost >= self.SEARCH_DELAY and self.phase == PHASE_ALIGN:
            # Simple yaw search — no sweep reversal complexity
            logger.debug("[AutoPilot] Search yaw (lost=%.1fs)", time_lost)
            return 0, 0, 0, self.SEARCH_YAW_SPEED

        return 0, 0, 0, 0

    # --- Pose validation ---

    def _is_pose_usable(self, pose):
        if getattr(pose, "is_coasted", False):
            return False, "coasted"
        if pose.confidence < self.TRACKING_MIN_CONF:
            return False, f"low_conf({pose.confidence:.0%})"
        if pose.z_cm < self.TRACKING_MIN_DIST:
            return False, f"too_close({pose.z_cm:.0f}cm)"
        if pose.z_cm > self.TRACKING_MAX_DIST:
            return False, f"too_far({pose.z_cm:.0f}cm)"
        return True, None

    # --- Transitions ---

    def _transition_to_approach(self):
        print("[AutoPilot] Target Locked! -> APPROACH")
        logger.info("[AutoPilot] ALIGN -> APPROACH")
        self.phase = PHASE_APPROACH
        # Tighter lateral gains for approach with slightly higher limits for responsiveness
        self.pid_lr.set_gains(kp=1.2, ki=0.05, kd=0.5, output_limit=25)
        self.pid_ud.set_gains(kp=1.2, ki=0.05, kd=0.5, output_limit=25)
        self.pid_yaw.set_gains(kp=0.5, ki=0.05, kd=0.15, output_limit=40)
        self._approach_start_time = None
        self._punch_lock_since = None
        self._recenter_since = None

    def _reset_to_align(self):
        print("[AutoPilot] Re-centering -> ALIGN")
        logger.warning("[AutoPilot] APPROACH -> ALIGN (re-center)")
        self.phase = PHASE_ALIGN
        self._restore_align_gains()
        self._align_stable_since = None
        self._approach_start_time = None
        self._punch_lock_since = None
        self._recenter_since = None

    def _restore_align_gains(self):
        self.pid_lr.set_gains(kp=0.6, ki=0.005, kd=0.5, output_limit=self.MAX_SPEED)
        self.pid_ud.set_gains(kp=0.8, ki=0.005, kd=0.4, output_limit=self.MAX_SPEED)
        self.pid_fb.set_gains(kp=0.7, ki=0.01,  kd=0.1, output_limit=self.MAX_SPEED)
        self.pid_yaw.set_gains(kp=0.35, ki=0.005, kd=0.05, output_limit=30)

    def _reset_all(self):
        self.phase = PHASE_ALIGN
        self._restore_align_gains()
        self._last_pose_time = time.monotonic()
        self._align_stable_since = None
        self._punch_start_time = None
        self._approach_start_time = None
        self._punch_lock_since = None
        self._recenter_since = None
        self._no_track_since = None
        self._last_lr = 0
        self._last_ud = 0
        self._last_log_time = 0.0

    # --- Utilities ---

    @staticmethod
    def _apply_deadzone(error, deadzone):
        if abs(error) < deadzone:
            return 0.0
        return error - math.copysign(deadzone, error)

    def _tilt_offset(self, z_cm):
        """Camera tilt Y compensation that scales with distance, capped to prevent
        wild corrections when Z_SCALE is uncalibrated."""
        offset = z_cm * math.tan(math.radians(self.CAMERA_TILT_DEG))
        return min(offset, 25.0)  # Cap at 25cm regardless of Z

    def _apply_min_speed(self, value):
        val_int = int(value)
        if val_int == 0:
            return 0
        if abs(val_int) < self.MIN_SPEED:
            return self.MIN_SPEED if val_int > 0 else -self.MIN_SPEED
        return val_int

    def _log_state(self, pose, cmd, now):
        if (now - self._last_log_time) < 0.5:
            return
        lr, fb, ud, yv = cmd
        logger.info(
            "[AutoPilot|%s] cmd=(%d,%d,%d,%d) pose=(x=%.1f y=%.1f z=%.1f a=%.1f c=%.2f)",
            self.phase, lr, fb, ud, yv,
            pose.x_cm, pose.y_cm, pose.z_cm, pose.angle_deg, pose.confidence,
        )
        self._last_log_time = now