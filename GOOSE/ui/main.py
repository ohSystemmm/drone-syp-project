from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout 
from kivy.lang import Builder
from kivy.utils import get_color_from_hex

class TopBar(Widget):
    pass

class DroneApp(App):
    def build(self):
        return Builder.load_file('ui.kv')

if __name__ == '__main__':
    DroneApp().run()