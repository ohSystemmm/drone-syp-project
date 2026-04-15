import os
import sys
from kivy.config import Config

Config.set('graphics', 'resizable', True)
Config.set('graphics', 'minimum_width', '960')
Config.set('graphics', 'minimum_height', '540')
Config.set('graphics', 'fullscreen', '0')
Config.set('graphics', 'window_state', 'maximized')

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.widget import Widget
from kivy.uix.boxlayout import BoxLayout
from kivy.core.text import LabelBase
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import Clock
from ui.media_gallery import MediaGallery, MediaCard, NavItem, FilterChip

# Register Material Design Icons font
font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'fonts', 'materialdesignicons-webfont.ttf')
LabelBase.register(name='Icons', fn_regular=font_path)

class TopBar(Widget): pass
class Stats(BoxLayout): pass
class Module(Widget): pass

class Bottom(Widget): 
    is_flying = BooleanProperty(False)
    is_recording = BooleanProperty(False)

    def toggle_flight(self):
        self.is_flying = not self.is_flying
        action_name = "LAND" if self.is_flying else "TAKE OFF"
        print(f"[UI Event] UI Flight Toggle: {action_name}")
        App.get_running_app().on_action(action_name)

    def toggle_record(self):
        self.is_recording = not self.is_recording
        action_name = "SAVE" if self.is_recording else "REC"
        print(f"[UI Event] UI Record Toggle: {action_name}")
        app = App.get_running_app()
        app.toggle_recording_timer(self.is_recording)
        app.on_action(action_name)

    def on_action(self, action_name):
        print(f"[UI Event] UI Placeholder: {action_name} button pressed")

class FlightMenu(BoxLayout): 
    active_mode = StringProperty("")
    in_cooldown = BooleanProperty(False)

    def on_mode_select(self, mode_name):
        if self.in_cooldown:
            print(f"[UI Event] Ignored {mode_name} - currently in 2s cooldown")
            return

        self.active_mode = mode_name
        self.in_cooldown = True
        print(f"[UI Event] UI Placeholder: {mode_name} mode activated!")
        
        # Dispatch the general app action too, so logic can hook in
        App.get_running_app().on_action(mode_name)

        Clock.schedule_once(self.reset_cooldown, 2.0)

    def reset_cooldown(self, dt):
        self.in_cooldown = False
        print("[UI Event] Cooldown finished, buttons active again.")

    def on_action(self, action_name):
        print(f"[UI Event] UI Placeholder: {action_name} button pressed")

class DroneApp(App):
    recording_time = StringProperty("00:00:00")
    uptime = StringProperty("00:00")
    _record_seconds = 0
    _record_event = None
    _uptime_seconds = -1  # Starts at -1 so first tick makes it 00:00

    def on_start(self):
        Clock.schedule_interval(self._update_uptime, 1.0)
        # Call it once immediately to display 00:00 initially if needed,
        # but the property init value does that.
        
    def _update_uptime(self, dt):
        self._uptime_seconds += 1
        mins, secs = divmod(self._uptime_seconds, 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            self.uptime = f"{hours:02d}:{mins:02d}:{secs:02d}"
        else:
            self.uptime = f"{mins:02d}:{secs:02d}"

    def toggle_recording_timer(self, is_recording):
        if is_recording:
            self._record_seconds = 0
            self.recording_time = "00:00:00"
            self._record_event = Clock.schedule_interval(self._update_recording_time, 1.0)
        else:
            if self._record_event:
                self._record_event.cancel()
                self._record_event = None
            self._record_seconds = 0
            self.recording_time = "00:00:00"

    def _update_recording_time(self, dt):
        self._record_seconds += 1
        mins, secs = divmod(self._record_seconds, 60)
        hours, mins = divmod(mins, 60)
        self.recording_time = f"{hours:02d}:{mins:02d}:{secs:02d}"

    _gallery = None
    _gallery_kv_loaded = False

    def toggle_media_gallery(self):
        """Toggle the Media Gallery overlay on/off."""
        if self._gallery and self._gallery.parent:
            # Gallery is showing — remove it
            self.root.remove_widget(self._gallery)
            self._gallery = None
            return

        # Load KV once
        if not self._gallery_kv_loaded:
            kv_path = os.path.join(os.path.dirname(__file__), 'kv', 'media_gallery.kv')
            Builder.load_file(kv_path)
            self._gallery_kv_loaded = True

        # Create and add gallery
        gallery = MediaGallery()
        gallery.size_hint = (1, 1)
        gallery.pos_hint = {"x": 0, "y": 0}
        gallery.opacity = 1
        self.root.add_widget(gallery)
        gallery.open()
        self._gallery = gallery

    def close_media_gallery(self):
        """Called by the gallery close button."""
        if self._gallery and self._gallery.parent:
            self.root.remove_widget(self._gallery)
            self._gallery = None

    def on_action(self, action_name):
        if action_name == "SETTINGS":
            self.toggle_media_gallery()
            return
        print(f"[UI Event] UI Placeholder: {action_name} button pressed")

    def on_request_close(self, *args):
        # Ensure Kivy window close shuts down the whole process
        print("[UI] Request close received, exiting application")
        self.stop()
        return False

    def on_stop(self):
        # Close process to avoid leftover threads
        print("[UI] App stopped, exiting process")
        sys.exit(0)

    def build(self):
        kv_path = os.path.join(os.path.dirname(__file__), 'ui.kv')
        return Builder.load_file(kv_path)

def Setup():
    DroneApp().run()