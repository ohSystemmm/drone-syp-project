from kivy.uix.widget import Widget
from kivy.properties import NumericProperty, ReferenceListProperty
from kivy.lang import Builder
from kivy.graphics import Color, Line, Ellipse
from kivy.vector import Vector

Builder.load_string('''
<VirtualJoystick>:
    canvas:
        # Background pad
        Color:
            rgba: 0.2, 0.2, 0.2, 0.5
        Ellipse:
            pos: self.pos
            size: self.size
        
        # Center marker
        Color:
            rgba: 0.5, 0.5, 0.5, 0.5
        Line:
            circle: (self.center_x, self.center_y, 4)
            width: 2
            
        # Outer boundary ring
        Color:
            rgba: 0.4, 0.4, 0.4, 0.8
        Line:
            ellipse: (self.x, self.y, self.width, self.height)
            width: 1.5

        # The draggable stick
        Color:
            rgba: 0.2, 0.7, 1, 0.8
        Ellipse:
            pos: (self.stick_x - self.stick_radius, self.stick_y - self.stick_radius)
            size: (self.stick_radius * 2, self.stick_radius * 2)
            
        Color:
            rgba: 1, 1, 1, 0.5
        Line:
            circle: (self.stick_x, self.stick_y, self.stick_radius - 2)
            width: 1.5
''')

class VirtualJoystick(Widget):
    """
    A simple virtual onscreen joystick.
    Values normalized between -1.0 and 1.0.
    """
    pad_radius = NumericProperty(0)
    stick_radius = NumericProperty(30)
    
    stick_x = NumericProperty(0)
    stick_y = NumericProperty(0)
    stick_pos = ReferenceListProperty(stick_x, stick_y)
    
    # Normalized outputs (-1.0 to 1.0)
    out_x = NumericProperty(0.0)
    out_y = NumericProperty(0.0)

    def on_size(self, *args):
        self.pad_radius = min(self.width, self.height) / 2
        self.reset_stick()

    def on_pos(self, *args):
        self.reset_stick()

    def reset_stick(self):
        self.stick_pos = self.center
        self.out_x = 0.0
        self.out_y = 0.0

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self.update_stick(touch.pos)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.update_stick(touch.pos)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.reset_stick()
            return True
        return super().on_touch_up(touch)

    def update_stick(self, pos):
        # Calculate vector from center to touch
        vec = Vector(*pos) - Vector(*self.center)
        distance = vec.length()
        
        # Clamp distance to pad radius
        max_dist = self.pad_radius - self.stick_radius/2
        if distance > max_dist:
            vec = vec.normalize() * max_dist
            
        self.stick_pos = Vector(*self.center) + vec
        
        # Calculate normalized outputs (-1.0 to 1.0)
        # Apply a small deadzone (e.g., 10%)
        norm_x = vec.x / max_dist
        norm_y = vec.y / max_dist
        
        deadzone = 0.1
        if abs(norm_x) < deadzone: norm_x = 0.0
        if abs(norm_y) < deadzone: norm_y = 0.0
            
        self.out_x = norm_x
        self.out_y = norm_y
