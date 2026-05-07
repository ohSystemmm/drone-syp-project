"""
LoadingOverlay — Full-screen overlay for showing loading/connecting states.
"""

from kivy.uix.floatlayout import FloatLayout
from kivy.properties import StringProperty, BooleanProperty, NumericProperty
from kivy.lang import Builder
from kivy.clock import Clock
import math

Builder.load_string('''
#:import Icons ui.icons.Icons

<LoadingSpinner@Widget>:
    angle: 0
    canvas.before:
        PushMatrix
        Rotate:
            angle: self.angle
            axis: 0, 0, 1
            origin: self.center
    canvas:
        Color:
            rgba: (0.2, 0.7, 1, 1)
        Line:
            circle: (self.center_x, self.center_y, 24, 0, 270)
            width: 2.5
            cap: 'round'
    canvas.after:
        PopMatrix

<LoadingOverlay>:
    size_hint: 1, 1
    pos_hint: {"x": 0, "y": 0}
    opacity: self.bg_opacity

    # Dimmed backdrop
    canvas.before:
        Color:
            rgba: (0, 0, 0, 0.85)
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'
        size_hint: None, None
        size: 400, 200
        pos_hint: {"center_x": 0.5, "center_y": 0.5}
        spacing: 20
        
        Widget:
        
        FloatLayout:
            size_hint_y: None
            height: 60
            
            # Static icon in middle
            Label:
                text: root.icon
                font_name: 'Icons'
                font_size: '28sp'
                color: (1, 1, 1, 0.5)
                pos_hint: {"center_x": 0.5, "center_y": 0.5}
                
            # Rotating spinner
            LoadingSpinner:
                id: spinner
                size_hint: None, None
                size: 60, 60
                pos_hint: {"center_x": 0.5, "center_y": 0.5}

        Label:
            text: root.title
            font_size: '20sp'
            bold: True
            color: (1, 1, 1, 1)
            size_hint_y: None
            height: 30
            
        Label:
            text: root.subtitle
            font_size: '13sp'
            color: (0.6, 0.7, 0.8, 1)
            size_hint_y: None
            height: 20
            text_size: self.width, None
            halign: 'center'
            valign: 'middle'
            
        Widget:
''')

class LoadingOverlay(FloatLayout):
    title = StringProperty("Connecting...")
    subtitle = StringProperty("Please wait")
    icon = StringProperty("\U000F05A9")  # mdi-wifi
    bg_opacity = NumericProperty(0.0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._spin_event = None

    def on_parent(self, widget, parent):
        if parent:
            self._spin_event = Clock.schedule_interval(self._update_spinner, 1.0 / 60.0)
            from kivy.animation import Animation
            Animation(bg_opacity=1.0, duration=0.3).start(self)
        else:
            if self._spin_event:
                self._spin_event.cancel()
                self._spin_event = None

    def _update_spinner(self, dt):
        spinner = self.ids.spinner
        spinner.angle -= dt * 300  # Rotate 300 degrees per second
