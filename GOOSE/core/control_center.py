import pygame
import json
import os

class ControlCenterUI:
    """
    Provides a Pygame overlay to manage key and button bindings interactively.
    """
    def __init__(self, joy_handler=None, config_file="flight_data/keybindings.json"):
        self.config_file = config_file
        self.joy_handler = joy_handler
        self.active = False
        
        # Default bindings
        # Format: action_name: {"type": "key"|"btn", "val": int}
        self.bindings = {
            "takeoff": {"type": "key", "val": pygame.K_t},
            "land": {"type": "key", "val": pygame.K_l},
            "emergency": {"type": "key", "val": pygame.K_ESCAPE},
            "flip_f": {"type": "btn", "val": 0},
            "flip_b": {"type": "btn", "val": 3},
            "flip_l": {"type": "btn", "val": 2},
            "flip_r": {"type": "btn", "val": 1},
            "auto_toggle": {"type": "key", "val": pygame.K_p},
            "ai_toggle": {"type": "key", "val": pygame.K_g},
            "calib_vis": {"type": "key", "val": pygame.K_F5},
            "calib_stk": {"type": "key", "val": pygame.K_F7},
            "rec_calib": {"type": "key", "val": pygame.K_c},
            "cycle_joy": {"type": "key", "val": pygame.K_n},
        }
        
        self.actions_display_names = {
            "takeoff": "Takeoff",
            "land": "Land",
            "emergency": "Emergency Stop (KILL)",
            "flip_f": "Flip Forward",
            "flip_b": "Flip Backward",
            "flip_l": "Flip Left",
            "flip_r": "Flip Right",
            "auto_toggle": "Toggle Autopilot",
            "ai_toggle": "Toggle Gemini AI",
            "calib_vis": "Toggle Vision Calib",
            "calib_stk": "Toggle Stick Calib",
            "rec_calib": "Capture Vision Sample",
            "cycle_joy": "Cycle Active Joystick",
            "inv_roll": "Invert Roll Axis",
            "inv_pitch": "Invert Pitch Axis",
            "inv_yaw": "Invert Yaw Axis",
            "inv_thr": "Invert Throttle Axis",
        }
        
        self.load_config()
        
        self.font = pygame.font.SysFont(None, 42)
        self.small_font = pygame.font.SysFont(None, 32)
        
        self.waiting_for_input = None # Action name we are waiting for
        self.rects = {} # Action name -> pygame.Rect for clicking
        
    def toggle(self):
        self.active = not self.active
        self.waiting_for_input = None
        
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    data = json.load(f)
                    self.bindings.update(data)
            except Exception as e:
                print(f"Error loading keybindings: {e}")
                
    def save_config(self):
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.bindings, f, indent=4)
        except Exception as e:
            print(f"Error saving keybindings: {e}")
            
    def get_binding_name(self, action):
        if action in ["inv_roll", "inv_pitch", "inv_yaw", "inv_thr"]:
            if self.joy_handler:
                mapping = {"inv_roll": "invert_roll", "inv_pitch": "invert_pitch", "inv_yaw": "invert_yaw", "inv_thr": "invert_throttle"}
                return "ON" if self.joy_handler.config[mapping[action]] else "OFF"
            return "N/A"
            
        bind = self.bindings.get(action)
        if not bind: return "Unbound"
        
        if bind["type"] == "key":
            return pygame.key.name(bind["val"]).upper()
        elif bind["type"] == "btn":
            return f"Joy Button {bind['val']}"
        return "Unbound"
        
    def handle_event(self, event):
        """
        Returns an action string if one was triggered, else None.
        If UI is active, handles binding instead.
        """
        if self.active:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Check if clicked on a binding
                for action, rect in self.rects.items():
                    if rect.collidepoint(event.pos):
                        if action in ["inv_roll", "inv_pitch", "inv_yaw", "inv_thr"]:
                            if self.joy_handler:
                                mapping = {"inv_roll": "invert_roll", "inv_pitch": "invert_pitch", "inv_yaw": "invert_yaw", "inv_thr": "invert_throttle"}
                                conf_key = mapping[action]
                                self.joy_handler.config[conf_key] = not self.joy_handler.config[conf_key]
                                self.joy_handler.save_config()
                            return None
                            
                        self.waiting_for_input = action
                        return None
                        
            if self.waiting_for_input:
                action = self.waiting_for_input
                if event.type == pygame.KEYDOWN:
                    # Ignore escape so they can cancel
                    if event.key == pygame.K_ESCAPE and action != "emergency":
                        self.waiting_for_input = None
                    else:
                        self.bindings[action] = {"type": "key", "val": event.key}
                        self.waiting_for_input = None
                        self.save_config()
                elif event.type == pygame.JOYBUTTONDOWN:
                    self.bindings[action] = {"type": "btn", "val": event.button}
                    self.waiting_for_input = None
                    self.save_config()
            return None
            
        else:
            # Check if event triggers any action
            for action, bind in self.bindings.items():
                if bind["type"] == "key" and event.type == pygame.KEYDOWN and event.key == bind["val"]:
                    return action
                elif bind["type"] == "btn" and event.type == pygame.JOYBUTTONDOWN and event.button == bind["val"]:
                    return action
        return None
        
    def draw(self, surface):
        if not self.active:
            return
            
        # Draw semi-transparent background overlay
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 220)) # Darken background more heavily for readability
        surface.blit(overlay, (0, 0))
        
        # Draw Title
        title = self.font.render("--- CONTROL CENTER KEYBINDINGS ---", True, (255, 255, 255))
        surface.blit(title, (surface.get_width()//2 - title.get_width()//2, 40))
        
        self.rects = {}
        items = list(self.actions_display_names.items())
        half = (len(items) + 1) // 2
        
        for i, (action, display_name) in enumerate(items):
            col = i // half
            row = i % half
            
            x_base = 30 if col == 0 else surface.get_width()//2 + 10
            y_offset = 100 + row * 45
            
            # Action Name
            name_surf = self.small_font.render(display_name, True, (200, 200, 200))
            surface.blit(name_surf, (x_base, y_offset))
            
            # Binding Value / Button
            is_waiting = (self.waiting_for_input == action)
            bind_text = "Press any key/btn..." if is_waiting else self.get_binding_name(action)
            color = (255, 255, 0) if is_waiting else (100, 255, 100)
            
            bind_surf = self.small_font.render(bind_text, True, color)
            
            # Draw button background
            btn_x = x_base + 240
            btn_w = 200
            
            btn_rect = pygame.Rect(btn_x, y_offset - 5, btn_w, 35)
            # Hover effect
            mouse_pos = pygame.mouse.get_pos()
            bg_color = (80, 80, 80) if btn_rect.collidepoint(mouse_pos) else (50, 50, 50)
            pygame.draw.rect(surface, bg_color, btn_rect, border_radius=5)
            
            if is_waiting:
                pygame.draw.rect(surface, (255, 255, 0), btn_rect, width=2, border_radius=5)
                
            surface.blit(bind_surf, (btn_x + 10, y_offset))
            self.rects[action] = btn_rect
            
        # Draw close instruction
        close_text = self.small_font.render("Press TAB to close Control Center", True, (150, 150, 150))
        surface.blit(close_text, (surface.get_width()//2 - close_text.get_width()//2, surface.get_height() - 40))
