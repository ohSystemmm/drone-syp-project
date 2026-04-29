import pygame
import time

class JoystickCalibrationMode:
    STATE_INACTIVE = 0
    STATE_CENTERING = 1
    STATE_EXTENTS = 2
    STATE_MAP_THROTTLE = 3
    STATE_MAP_YAW = 4
    STATE_MAP_PITCH = 5
    STATE_MAP_ROLL = 6
    STATE_DONE = 7
    
    def __init__(self, joystick_handler):
        self.joystick_handler = joystick_handler
        self.state = self.STATE_INACTIVE
        self.active = False
        
        self.start_time = 0
        self.duration = 5.0 # seconds per calibration step

        # Temporary calibration data
        self.centers = {}
        self.mins = {}
        self.maxs = {}
        
        # Detected mappings
        self.new_mapping = {}
        self.new_config = {}

    def toggle(self):
        if self.active:
            self.cancel()
        else:
            self.start()

    def start(self):
        if not self.joystick_handler.is_connected or not self.joystick_handler.joystick:
            print("Cannot calibrate: No joystick connected.")
            return

        self.active = True
        self.state = self.STATE_CENTERING
        self.start_step()
        
        # Initialize temp data
        num_axes = self.joystick_handler.joystick.get_numaxes()
        for i in range(num_axes):
            self.mins[i] = 1.0
            self.maxs[i] = -1.0
            self.centers[i] = 0.0
            
    def cancel(self):
        self.active = False
        self.state = self.STATE_INACTIVE
        print("Joystick Calibration Cancelled.")

    def start_step(self):
        self.start_time = time.time()

    def update(self):
        """Called every frame. Returns True if calibration just finished."""
        if not self.active or not self.joystick_handler.joystick:
            return False

        current_time = time.time()
        elapsed = current_time - self.start_time
        
        num_axes = self.joystick_handler.joystick.get_numaxes()
        joy = self.joystick_handler.joystick

        if self.state == self.STATE_CENTERING:
            # Continuously average centers? Or just grab them at the end.
            # Let's just grab them at the end of the 3 seconds.
            if elapsed >= 3.0:
                for i in range(num_axes):
                    self.centers[i] = joy.get_axis(i)
                self.state = self.STATE_EXTENTS
                self.start_step()

        elif self.state == self.STATE_EXTENTS:
            # Track min/max continuously
            for i in range(num_axes):
                v = joy.get_axis(i)
                if v < self.mins[i]: self.mins[i] = v
                if v > self.maxs[i]: self.maxs[i] = v
                
            if elapsed >= 5.0:
                self.state = self.STATE_MAP_THROTTLE
                self.start_step()

        elif self.state in [self.STATE_MAP_THROTTLE, self.STATE_MAP_YAW, self.STATE_MAP_PITCH, self.STATE_MAP_ROLL]:
            # Look for max deviation from center
            max_dev_axis = -1
            max_dev_val = 0.0
            raw_val = 0.0
            
            for i in range(num_axes):
                v = joy.get_axis(i)
                dev = abs(v - self.centers[i])
                if dev > 0.5: # Threshold to detect movement
                    if dev > max_dev_val:
                        max_dev_val = dev
                        max_dev_axis = i
                        raw_val = v
            
            # Require 2 seconds to hold the position
            if max_dev_axis != -1 and elapsed > 2.0:
                is_negative = (raw_val - self.centers[max_dev_axis]) < 0
                
                if self.state == self.STATE_MAP_THROTTLE:
                    self.new_mapping['throttle_axis'] = max_dev_axis
                    # UP is negative on most joysticks, Tello throttle UP is positive.
                    # We negate throttle in joystick handler `ud = int(-throttle_norm * 100)`.
                    # So if UP stick yields NEGATIVE axis value, no inversion needed.
                    # If UP stick yields POSITIVE axis value, inversion needed.
                    self.new_config['invert_throttle'] = not is_negative
                    self.state = self.STATE_MAP_YAW
                    self.start_step()
                    
                elif self.state == self.STATE_MAP_YAW:
                    self.new_mapping['yaw_axis'] = max_dev_axis
                    # LEFT stick yields NEGATIVE axis value on most joysticks.
                    # Tello expects yaw LEFT to be negative.
                    # So if LEFT is negative, no inversion.
                    self.new_config['invert_yaw'] = not is_negative
                    self.state = self.STATE_MAP_PITCH
                    self.start_step()
                    
                elif self.state == self.STATE_MAP_PITCH:
                    self.new_mapping['pitch_axis'] = max_dev_axis
                    # UP stick (forward) yields NEGATIVE axis.
                    # Tello expects forward to be POSITIVE.
                    # We map `fb = int(pitch_norm * 100)` in level mode.
                    # If UP is negative, we need to invert it so it becomes positive.
                    self.new_config['invert_pitch'] = is_negative
                    self.state = self.STATE_MAP_ROLL
                    self.start_step()
                    
                elif self.state == self.STATE_MAP_ROLL:
                    self.new_mapping['roll_axis'] = max_dev_axis
                    # RIGHT stick yields POSITIVE axis.
                    # Tello expects right to be POSITIVE.
                    # If RIGHT is positive, no inversion.
                    self.new_config['invert_roll'] = is_negative
                    self.state = self.STATE_DONE

        elif self.state == self.STATE_DONE:
            # Save results
            self.joystick_handler.mapping.update(self.new_mapping)
            self.joystick_handler.config.update(self.new_config)
            self.joystick_handler.save_config()
            self.active = False
            self.state = self.STATE_INACTIVE
            print("Calibration Complete! Config Saved.")
            return True

        return False

    def get_hud_text(self):
        if not self.active:
            return []

        lines = ["--- JOYSTICK CALIBRATION ---"]
        
        elapsed = time.time() - self.start_time
        
        if self.state == self.STATE_CENTERING:
            remain = max(0, 3.0 - elapsed)
            lines.append("Let go of all sticks (Center them)")
            lines.append(f"Recording in {remain:.1f}s...")
        elif self.state == self.STATE_EXTENTS:
            remain = max(0, 5.0 - elapsed)
            lines.append("Move all sticks in full circles!")
            lines.append(f"Recording min/max in {remain:.1f}s...")
        elif self.state == self.STATE_MAP_THROTTLE:
            lines.append("Push the LEFT stick UP (Throttle Up)")
            lines.append(f"Hold for {(max(0, 2.0-elapsed)):.1f}s")
        elif self.state == self.STATE_MAP_YAW:
            lines.append("Push the LEFT stick LEFT (Yaw Left)")
            lines.append(f"Hold for {(max(0, 2.0-elapsed)):.1f}s")
        elif self.state == self.STATE_MAP_PITCH:
            lines.append("Push the RIGHT stick UP (Pitch Forward)")
            lines.append(f"Hold for {(max(0, 2.0-elapsed)):.1f}s")
        elif self.state == self.STATE_MAP_ROLL:
            lines.append("Push the RIGHT stick RIGHT (Roll Right)")
            lines.append(f"Hold for {(max(0, 2.0-elapsed)):.1f}s")
            
        lines.append("Press F7 to Cancel")
        return lines
