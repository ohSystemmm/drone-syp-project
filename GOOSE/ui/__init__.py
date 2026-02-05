import os
from kivy.config import Config

Config.set('graphics', 'width', '1920')
Config.set('graphics', 'height', '1080')
Config.set('graphics', 'resizable', False)

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout

class TopBar(Widget): pass
class Stats(BoxLayout): pass
class Module(Widget): pass
class Bottom(Widget): pass

class DroneApp(App):
    def build(self):
        kv_path = os.path.join(os.path.dirname(__file__), 'ui.kv')
        return Builder.load_file(kv_path)

def Setup():
    DroneApp().run()