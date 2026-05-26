import os
import logging
from kivy.uix.floatlayout import FloatLayout
from kivy.properties import BooleanProperty, NumericProperty
from kivy.app import App

logger = logging.getLogger(__name__)

class TutorialOverlay(FloatLayout):
    """Full-screen interactive tutorial overlay."""
    is_open = BooleanProperty(False)
    current_slide = NumericProperty(0)
    total_slides = NumericProperty(4)

    def on_touch_down(self, touch):
        """Block touches from reaching the flight controls below while tutorial is open."""
        if self.collide_point(*touch.pos):
            super().on_touch_down(touch)
            return True
        return False

    def on_touch_move(self, touch):
        if self.collide_point(*touch.pos):
            super().on_touch_move(touch)
            return True
        return False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            super().on_touch_up(touch)
            return True
        return False

    def open(self):
        self.is_open = True
        self.current_slide = 0
        try:
            self.ids.carousel.index = 0
        except AttributeError:
            pass

    def next_slide(self):
        try:
            carousel = self.ids.carousel
            if carousel.index < self.total_slides - 1:
                carousel.load_next()
                self.current_slide = carousel.index
            else:
                self.close_tutorial()
        except Exception as e:
            logger.error(f"Error switching tutorial slide: {e}")
            self.close_tutorial()

    def prev_slide(self):
        try:
            carousel = self.ids.carousel
            if carousel.index > 0:
                carousel.load_previous()
                self.current_slide = carousel.index
        except Exception as e:
            logger.error(f"Error switching tutorial slide: {e}")

    def on_slide_change(self, index):
        self.current_slide = index

    def close_tutorial(self):
        self.is_open = False
        app = App.get_running_app()
        if hasattr(app, 'close_tutorial'):
            app.close_tutorial()

        # Save completion state persistently
        try:
            config_dir = "GOOSE/flight_data" if os.path.exists("GOOSE") else "flight_data"
            os.makedirs(config_dir, exist_ok=True)
            marker_path = os.path.join(config_dir, "tutorial_completed.txt")
            with open(marker_path, "w") as f:
                f.write("completed")
        except Exception as e:
            logger.error(f"Failed to save tutorial completion state: {e}")

    @staticmethod
    def is_completed():
        try:
            config_dir = "GOOSE/flight_data" if os.path.exists("GOOSE") else "flight_data"
            marker_path = os.path.join(config_dir, "tutorial_completed.txt")
            return os.path.exists(marker_path)
        except Exception:
            return False
