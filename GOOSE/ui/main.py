from kivy.app import App
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout 
from kivy.lang import Builder
from kivy.config import Config

Config.set('graphics', 'width', '1920')
Config.set('graphics', 'height', '1080')
Config.set('graphics', 'resizable', False)

class TopBar(Widget):
    pass
class Stats(Widget):
    pass
class Module(Widget):
    pass
class Bottom(Widget):
    pass

class DroneApp(App):
    def build(self):
        return Builder.load_file('ui.kv')

if __name__ == '__main__':
    DroneApp().run()