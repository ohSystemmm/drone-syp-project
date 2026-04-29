"""
Distance Calibration Module

Interactive calibration flow:
    1. Press F5 to enter calibration mode
    2. Place drone at displayed distance from target
    3. Press SPACE to record measurement
    4. Repeat for each distance step
    5. System computes Z_SCALE and saves to config

The calibration uses multiple known distances and linear regression
to find the best Z_SCALE multiplier.
"""

import json
import math
import os
import time
import numpy as np


# Calibration distances in cm (camera-to-target)
CALIBRATION_DISTANCES = [50, 100, 150, 200]

# Ground mode needs larger distances — drone can't see the full target up close
GROUND_CALIBRATION_DISTANCES = [150, 200, 250, 300]

# Target center height above floor (outer diameter 50cm → center at 25cm)
TARGET_CENTER_HEIGHT = 25.0

# Where to save calibration results
CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "..", "assets", "calibration.json")


class CalibrationMode:
    """
    Manages distance calibration.
    Now includes 'Auto-Calibration' which runs silently in the background.
    """
    SAMPLES_PER_DISTANCE = 15
    STATE_INACTIVE = "INACTIVE"
    STATE_WAITING = "WAITING"
    STATE_MEASURING = "MEASURING"
    STATE_DONE = "DONE"

    def __init__(self):
        self.state = self.STATE_INACTIVE
        self.step_index = 0
        self.raw_samples = []
        self.aruco_samples = []
        self.data_points = []
        self.computed_scale = None
        self.ground_mode = False
        self.aruco_calibrator = None
        self._last_aruco_dist = None
        self._current_z_scale = 1.0  # Track current Z_SCALE for raw conversion

    @property
    def active(self):
        return self.state != self.STATE_INACTIVE

    @property
    def _distances(self):
        return GROUND_CALIBRATION_DISTANCES if self.ground_mode else CALIBRATION_DISTANCES

    @property
    def current_target_distance(self):
        if self.step_index < len(self._distances):
            return self._distances[self.step_index]
        return None

    def start(self, ground_mode=False):
        """Enter calibration mode."""
        self.state = self.STATE_WAITING
        self.step_index = 0
        self.raw_samples = []
        self.aruco_samples = []
        self.data_points = []
        self.computed_scale = None
        self._last_aruco_dist = None
        self.ground_mode = ground_mode
        mode_label = "GROUND" if ground_mode else "AIRBORNE"
        print(f"\n{'='*50}")
        print(f"  CALIBRATION MODE ({mode_label})")
        dists = self._distances
        if ground_mode:
            print(f"  Place drone & target on the floor")
            print(f"  {dists[0]}cm from camera to target")
            print(f"  (height offset {TARGET_CENTER_HEIGHT}cm auto-corrected)")
        else:
            print(f"  Place drone exactly {dists[0]}cm from target")
        print(f"  Then press SPACE to record.")
        print(f"  Press F5/F6 again to cancel.")
        print(f"{'='*50}\n")

    def cancel(self):
        """Exit calibration mode without saving."""
        self.state = self.STATE_INACTIVE
        print("[Calibration] Cancelled.")

    def toggle(self, ground_mode=False):
        """Toggle calibration mode on/off."""
        if self.active:
            self.cancel()
        else:
            self.start(ground_mode=ground_mode)

    def record_sample(self, pose):
        """
        Called when user presses SPACE during calibration.
        Start collecting samples from the current pose.
        """
        if self.state != self.STATE_WAITING:
            return

        if pose is None:
            print("[Calibration] No tracking! Make sure the target is visible.")
            return

        self.state = self.STATE_MEASURING
        self.raw_samples = []
        self.aruco_samples = []
        print(f"[Calibration] Recording at {self.current_target_distance}cm...")

    def feed_pose(self, pose):
        """
        Feed a pose estimate during the MEASURING state.
        Collects SAMPLES_PER_DISTANCE raw Z values and averages them.

        Returns True if a calibration step was completed.
        """
        if self.state != self.STATE_MEASURING:
            return False

        if pose is None:
            return False

        # Divide out the current Z_SCALE to get the raw (unscaled) Z value.
        # The estimator applies Z_SCALE before returning pose.z_cm.
        raw_z = pose.z_cm / max(self._current_z_scale, 0.01)
        self.raw_samples.append(raw_z)

        if len(self.raw_samples) >= self.SAMPLES_PER_DISTANCE:
            avg_z = np.mean(self.raw_samples)
            floor_dist = self.current_target_distance

            # Determine ground-truth distance
            if self.aruco_samples:
                # ArUco ground-truth is most accurate (Z is the 3rd element)
                actual = np.mean([s[2] for s in self.aruco_samples])
                print(f"[Calibration] ArUco ground-truth {actual:.1f}cm → "
                      f"estimated {avg_z:.1f}cm (raw scale = {actual / avg_z:.2f}x)")
            elif self.ground_mode:
                actual = math.sqrt(floor_dist ** 2 + TARGET_CENTER_HEIGHT ** 2)
                print(f"[Calibration] Floor {floor_dist}cm → 3D {actual:.1f}cm → "
                      f"estimated {avg_z:.1f}cm (raw scale = {actual / avg_z:.2f}x)")
            else:
                actual = floor_dist
                print(f"[Calibration] Distance {actual}cm → estimated {avg_z:.1f}cm "
                      f"(raw scale = {actual / avg_z:.2f}x)")

            self.data_points.append((actual, avg_z))

            self.step_index += 1
            if self.step_index >= len(self._distances):
                self._finish()
            else:
                next_dist = self._distances[self.step_index]
                self.state = self.STATE_WAITING
                self.raw_samples = []
                self.aruco_samples = []
                if self.ground_mode:
                    print(f"\n  Now place {next_dist}cm apart on floor and press SPACE.\n")
                else:
                    print(f"\n  Now place drone at {next_dist}cm and press SPACE.\n")

            return True
        return False

    def _finish(self):
        """Compute Z_SCALE from collected data points."""
        actuals = np.array([d[0] for d in self.data_points])
        estimated = np.array([d[1] for d in self.data_points])

        # Compute best-fit scale: minimize sum of (actual - scale * estimated)²
        # Optimal: scale = sum(actual * estimated) / sum(estimated²)
        self.computed_scale = float(np.sum(actuals * estimated) / np.sum(estimated ** 2))

        mode_label = "GROUND" if self.ground_mode else "AIRBORNE"
        print(f"\n{'='*50}")
        print(f"  CALIBRATION COMPLETE ({mode_label})")
        print(f"  Computed Z_SCALE = {self.computed_scale:.3f}")
        print(f"")
        for actual, est in self.data_points:
            corrected = est * self.computed_scale
            err = abs(corrected - actual)
            print(f"    {actual:>6.1f}cm actual → {est:.0f}cm raw → {corrected:.0f}cm corrected (err: {err:.0f}cm)")
        print(f"{'='*50}\n")

        self._save(self.computed_scale)
        self.state = self.STATE_DONE

    def _save(self, z_scale):
        """Save calibration to JSON file."""
        data = {
            "z_scale": z_scale,
            "calibration_points": [
                {"actual_cm": a, "estimated_cm": e}
                for a, e in self.data_points
            ],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        os.makedirs(os.path.dirname(CALIBRATION_FILE), exist_ok=True)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[Calibration] Saved to {CALIBRATION_FILE}")

    @staticmethod
    def load_z_scale():
        """Load Z_SCALE from saved calibration file, or return default."""
        try:
            with open(CALIBRATION_FILE, "r") as f:
                data = json.load(f)
            scale = data.get("z_scale", 2.5)
            print(f"[Calibration] Loaded Z_SCALE = {scale:.3f} from calibration file")
            return scale
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return None  # No calibration file found

    def get_hud_text(self):
        """Return lines of text to show on the HUD during calibration."""
        lines = []
        mode_label = "GROUND" if self.ground_mode else "AIRBORNE"
        if self.state == self.STATE_WAITING:
            dist = self.current_target_distance
            step = self.step_index + 1
            total = len(self._distances)
            lines.append(f"{mode_label} CALIBRATION ({step}/{total})")
            if self.ground_mode:
                lines.append(f"Drone & target on floor")
                lines.append(f"{dist}cm camera to target")
            else:
                lines.append(f"Place drone at {dist}cm")
            if self._last_aruco_dist is not None:
                aruco_z = self._last_aruco_dist[2]
                lines.append(f"ArUco: {aruco_z:.1f}cm")
            lines.append("Press SPACE to record")
        elif self.state == self.STATE_MEASURING:
            n = len(self.raw_samples)
            total = self.SAMPLES_PER_DISTANCE
            lines.append(f"MEASURING... ({n}/{total})")
        elif self.state == self.STATE_DONE:
            lines.append(f"CALIBRATION DONE")
            lines.append(f"Z_SCALE = {self.computed_scale:.3f}")
            lines.append("Press F5/F6 to exit")
        return lines
