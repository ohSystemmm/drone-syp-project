import pygame
import json
import os
import time

class JoystickHandler:
    def __init__(self, config_file="flight_data/joystick_config.json"):
        self.config_file = config_file
        self.joystick = None
        self.is_connected = False
        
        # Default mapping (can be updated via calibration)
        # axes: 0=Roll, 1=Pitch, 2=Throttle, 3=Yaw
        self.mapping = {
            'roll_axis': 0,
            'pitch_axis': 1,
            'throttle_axis': 2,
            'yaw_axis': 3
        }
        
        # Configuration properties
        self.config = {
            'invert_roll': False,
            'invert_pitch': False,
            'invert_throttle': False,
            'invert_yaw': False,
            'deadzone': 0.1,  # 10% deadzone
            'expo': 0.5       # Exponential curve for finer center control
        }
        
        self.load_config()
        self.init_joystick()

    def init_joystick(self, target_index=0):
        pygame.joystick.init()
        self.joystick = None
        self.is_connected = False
        
        count = pygame.joystick.get_count()
        if count > 0:
            # Ensure target is valid
            idx = target_index if target_index < count else 0
            self.joystick = pygame.joystick.Joystick(idx)
            self.joystick.init()
            self.is_connected = True
            name = self.joystick.get_name()
            print(f"Joystick connected [{idx + 1}/{count}]: {name}")
        else:
            print("No joystick detected.")

    def cycle_joystick(self):
        """Switches to the next available joystick."""
        count = pygame.joystick.get_count()
        if count <= 1:
            print("No other joysticks to cycle to.")
            return
            
        current_id = self.joystick.get_id() if self.joystick else -1
        next_id = (current_id + 1) % count
        
        # Cleanup old
        if self.joystick:
            self.joystick.quit()
            
        print(f"Cycling joystick from {current_id} to {next_id}...")
        self.init_joystick(next_id)

    def get_raw_sticks(self):
        """
        Returns the raw (-1.0 to 1.0) un-curved inputs of the gimbals.
        Returns (roll, pitch, throttle, yaw). 
        This is purely for the visualizer HUD.
        """
        if not self.is_connected or not self.joystick:
            return 0.0, 0.0, 0.0, 0.0
            
        try:
            pygame.event.pump()
            raw_roll = self.joystick.get_axis(self.mapping['roll_axis'])
            raw_pitch = self.joystick.get_axis(self.mapping['pitch_axis'])
            raw_throttle = self.joystick.get_axis(self.mapping['throttle_axis'])
            raw_yaw = self.joystick.get_axis(self.mapping['yaw_axis'])
            
            # Apply inversions for visualizer so it matches flight behavior
            if self.config['invert_roll']: raw_roll = -raw_roll
            if self.config['invert_pitch']: raw_pitch = -raw_pitch
            if self.config['invert_throttle']: raw_throttle = -raw_throttle
            if self.config['invert_yaw']: raw_yaw = -raw_yaw
            
            return raw_roll, raw_pitch, raw_throttle, raw_yaw
        except Exception:
            return 0.0, 0.0, 0.0, 0.0

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    if 'mapping' in data:
                        self.mapping.update(data['mapping'])
                    if 'config' in data:
                        self.config.update(data['config'])
                print(f"Loaded joystick config from {self.config_file}")
            except Exception as e:
                print(f"Error loading joystick config: {e}")

    def save_config(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        data = {
            'mapping': self.mapping,
            'config': self.config
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
            print(f"Saved joystick config to {self.config_file}")
        except Exception as e:
            print(f"Error saving joystick config: {e}")

    def apply_curve(self, value, deadzone, expo):
        """Applies deadzone and exponential curve to normalized raw axis value (-1 to 1)."""
        if abs(value) < deadzone:
            return 0.0
        
        # Re-scale so value after deadzone goes from 0 to 1
        val_sign = 1 if value > 0 else -1
        val_mag = (abs(value) - deadzone) / (1.0 - deadzone)
        
        # Apply exponential curve: y = expo * x^3 + (1 - expo) * x
        val_curved = expo * (val_mag ** 3) + (1.0 - expo) * val_mag
        
        return val_curved * val_sign

    def get_rc_inputs(self):
        """Returns (lr, fb, ud, yv) commands scaled for Tello (-100 to 100)."""
        if not self.is_connected or not self.joystick:
            return 0, 0, 0, 0

        # Attempt to reconnect/refresh if there are issues
        pygame.event.pump()
        
        try:
            # Read raw axes
            raw_roll = self.joystick.get_axis(self.mapping['roll_axis'])
            raw_pitch = self.joystick.get_axis(self.mapping['pitch_axis'])
            raw_throttle = self.joystick.get_axis(self.mapping['throttle_axis'])
            raw_yaw = self.joystick.get_axis(self.mapping['yaw_axis'])
            
            # Apply inversions
            if self.config['invert_roll']: raw_roll = -raw_roll
            if self.config['invert_pitch']: raw_pitch = -raw_pitch
            if self.config['invert_throttle']: raw_throttle = -raw_throttle
            if self.config['invert_yaw']: raw_yaw = -raw_yaw

            # Apply curves mapped from -1.0 to 1.0
            dz = self.config['deadzone']
            ex = self.config['expo']
            
            roll_norm = self.apply_curve(raw_roll, dz, ex)
            pitch_norm = self.apply_curve(raw_pitch, dz, ex)
            throttle_norm = self.apply_curve(raw_throttle, dz, ex)
            yaw_norm = self.apply_curve(raw_yaw, dz, ex)

            # Direct mapping: stick (-1 to 1) directly maps to RC speed (-100 to 100)
            lr = int(roll_norm * 100)
            fb = int(pitch_norm * 100)
            ud = int(-throttle_norm * 100) # Negate because up (-1) is up on stick, but we want positive for Tello up
            yv = int(yaw_norm * 100)

            return lr, fb, ud, yv
            
        except Exception as e:
            print(f"Error reading joystick: {e}")
            return 0, 0, 0, 0

    def get_button_events(self):
        """Yields button press events (index). Call inside event loop."""
        for event in pygame.event.get(eventtype=[pygame.JOYBUTTONDOWN]):
            if event.joy == self.joystick.get_id():
                yield event.button

