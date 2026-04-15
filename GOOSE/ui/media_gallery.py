import os
import datetime
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    StringProperty, BooleanProperty, NumericProperty, ListProperty
)
from kivy.animation import Animation
from kivy.app import App


class MediaCard(ButtonBehavior, BoxLayout):
    """Individual media item card in the gallery grid."""
    filename = StringProperty("")
    file_size = StringProperty("0 MB")
    file_date = StringProperty("")
    is_video = BooleanProperty(False)
    is_favorited = BooleanProperty(False)
    is_selected = BooleanProperty(False)
    # Color for the placeholder thumbnail gradient
    thumb_color = ListProperty([0.15, 0.2, 0.25, 1])


class NavItem(ButtonBehavior, BoxLayout):
    """Sidebar navigation item."""
    icon = StringProperty("")
    text = StringProperty("")
    is_active = BooleanProperty(False)


class FilterChip(ButtonBehavior, BoxLayout):
    """Filter chip/tag button in the filter bar."""
    text = StringProperty("")
    is_active = BooleanProperty(False)
    has_dropdown = BooleanProperty(False)


class MediaGallery(FloatLayout):
    """Full-screen Media Gallery overlay."""
    is_open = BooleanProperty(False)
    active_nav = StringProperty("All Media")
    selection_mode = BooleanProperty(False)
    selected_count = NumericProperty(0)
    total_items = NumericProperty(0)
    shown_items = NumericProperty(0)
    storage_used = StringProperty("0 MB")
    storage_total = StringProperty("2.0 GB")
    storage_percent = NumericProperty(0)

    def on_touch_down(self, touch):
        """Consume all touches when gallery is open (block underlying UI)."""
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
        """Initialize the gallery content."""
        self.is_open = True
        self.load_recordings()

    def toggle_selection_mode(self):
        self.selection_mode = not self.selection_mode
        if not self.selection_mode:
            self.selected_count = 0
            # Deselect all cards
            grid = self._get_grid()
            if grid:
                for child in grid.children:
                    if isinstance(child, MediaCard):
                        child.is_selected = False

    def set_active_nav(self, nav_name):
        self.active_nav = nav_name

    def _get_grid(self):
        """Find the media grid widget by id."""
        try:
            return self.ids.media_grid
        except AttributeError:
            return None

    def load_recordings(self):
        """Scan the recordings directory and populate the media grid."""
        grid = self._get_grid()
        if not grid:
            return

        grid.clear_widgets()

        # Find recordings directory
        base_dir = os.path.dirname(os.path.dirname(__file__))
        rec_dir = os.path.join(base_dir, "recordings")
        if not os.path.exists(rec_dir):
            rec_dir = os.path.join(os.path.dirname(base_dir), "recordings")

        files = []
        total_size = 0

        if os.path.exists(rec_dir):
            for f in sorted(os.listdir(rec_dir), reverse=True):
                filepath = os.path.join(rec_dir, f)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    size_bytes = stat.st_size
                    total_size += size_bytes
                    mod_time = datetime.datetime.fromtimestamp(stat.st_mtime)

                    # Format size
                    if size_bytes >= 1024 * 1024:
                        size_str = f"{size_bytes / (1024*1024):.1f} MB"
                    elif size_bytes >= 1024:
                        size_str = f"{size_bytes / 1024:.1f} KB"
                    else:
                        size_str = f"{size_bytes} B"

                    # Format date
                    date_str = mod_time.strftime("%b %d, %H:%M")

                    is_video = f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))

                    # Assign varying placeholder colors for visual variety
                    color_index = len(files) % 5
                    colors = [
                        [0.1, 0.18, 0.22, 1],
                        [0.12, 0.16, 0.2, 1],
                        [0.08, 0.15, 0.2, 1],
                        [0.14, 0.18, 0.16, 1],
                        [0.12, 0.14, 0.22, 1],
                    ]

                    files.append({
                        'filename': f,
                        'file_size': size_str,
                        'file_date': date_str,
                        'is_video': is_video,
                        'thumb_color': colors[color_index],
                    })

        # Update storage info
        if total_size >= 1024 * 1024 * 1024:
            self.storage_used = f"{total_size / (1024**3):.1f} GB"
        elif total_size >= 1024 * 1024:
            self.storage_used = f"{total_size / (1024**2):.1f} MB"
        else:
            self.storage_used = f"{total_size / 1024:.1f} KB"

        # Assume 2GB total storage for percentage
        total_storage = 2.0 * 1024 * 1024 * 1024
        self.storage_percent = min(total_size / total_storage, 1.0)
        self.total_items = len(files)
        self.shown_items = len(files)

        # Create MediaCard widgets
        for f_info in files:
            card = MediaCard(
                filename=f_info['filename'],
                file_size=f_info['file_size'],
                file_date=f_info['file_date'],
                is_video=f_info['is_video'],
                thumb_color=f_info['thumb_color'],
            )
            card.bind(on_release=self._on_card_pressed)
            grid.add_widget(card)

        # Add an "Import Media" placeholder card
        import_card = MediaCard(
            filename="Import Media",
            file_size="",
            file_date="",
            is_video=False,
            thumb_color=[0.08, 0.1, 0.14, 0.5],
        )
        grid.add_widget(import_card)

    def _on_card_pressed(self, card):
        if self.selection_mode:
            card.is_selected = not card.is_selected
            grid = self._get_grid()
            if grid:
                self.selected_count = sum(
                    1 for c in grid.children
                    if isinstance(c, MediaCard) and c.is_selected
                )
