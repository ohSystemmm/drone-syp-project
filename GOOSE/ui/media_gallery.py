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


from kivy.uix.image import Image
from kivy.uix.video import Video
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label

class LEDDrawingGrid(GridLayout):
    def __init__(self, **kwargs):
        kwargs.setdefault('cols', 8)
        kwargs.setdefault('rows', 8)
        kwargs.setdefault('spacing', 2)
        super().__init__(**kwargs)
        self.pixels = []
        for i in range(64):
            btn = Button(background_normal='', background_color=(0.1, 0.1, 0.1, 1))
            btn.pixel_index = i
            btn.state_color = '0' # off
            btn.bind(on_release=self.on_pixel_press)
            self.add_widget(btn)
            self.pixels.append(btn)
    
    def on_pixel_press(self, btn):
        # Cycle colors: 0 -> r -> b -> p -> 0
        cycle = {'0': ('r', (1, 0, 0, 1)), 
                 'r': ('b', (0, 0, 1, 1)), 
                 'b': ('p', (0.5, 0, 0.5, 1)), 
                 'p': ('0', (0.1, 0.1, 0.1, 1))}
        new_state, new_color = cycle[btn.state_color]
        btn.state_color = new_state
        btn.background_color = new_color

    def get_pattern_string(self):
        return "".join(p.state_color for p in self.pixels)

    def clear_grid(self):
        for p in self.pixels:
            p.state_color = '0'
            p.background_color = (0.1, 0.1, 0.1, 1)

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
        self.update_storage_stats()

    def update_storage_stats(self):
        """Calculate real storage usage from the recordings directory."""
        base_dir = os.path.dirname(os.path.dirname(__file__))
        rec_dir = os.path.join(base_dir, "recordings")
        if not os.path.exists(rec_dir):
            rec_dir = os.path.join(os.path.dirname(base_dir), "recordings")
        
        total_size = 0
        if os.path.exists(rec_dir):
            for f in os.listdir(rec_dir):
                fp = os.path.join(rec_dir, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)

        if total_size >= 1024 * 1024 * 1024:
            self.storage_used = f"{total_size / (1024**3):.1f} GB"
        elif total_size >= 1024 * 1024:
            self.storage_used = f"{total_size / (1024**2):.1f} MB"
        else:
            self.storage_used = f"{total_size / 1024:.1f} KB"

        # Limit to 2GB for the UI bar
        self.storage_percent = min(total_size / (2.0 * 1024**3), 1.0)

    def sync_from_drone(self):
        """Simulate syncing media from drone (placeholder for actual FTP pull if needed)."""
        app = App.get_running_app()
        if app.controller.is_connected:
            print("[Gallery] Syncing media from drone...")
            # Tello doesn't support easy media pull via SDK (usually manual SD card)
            # but we can refresh local recordings list
            self.load_recordings()
            self.update_storage_stats()

    def cloud_backup(self):
        """Trigger a cloud backup of all recordings."""
        print("[Gallery] Starting Cloud Backup...")
        # Placeholder for actual upload logic

    def download_selected(self):
        print("[Gallery] Downloading selected items...")

    def favorite_selected(self):
        print("[Gallery] Favoriting selected items...")

    def delete_selected(self):
        print("[Gallery] Deleting selected items...")
        grid = self._get_grid()
        if not grid: return
        
        base_dir = os.path.dirname(os.path.dirname(__file__))
        rec_dir = os.path.join(base_dir, "recordings")
        if not os.path.exists(rec_dir):
            rec_dir = os.path.join(os.path.dirname(base_dir), "recordings")
            
        cards_to_remove = []
        for child in grid.children:
            if isinstance(child, MediaCard) and getattr(child, 'is_selected', False) and child.filename != "Import Media":
                cards_to_remove.append(child)
                filepath = os.path.join(rec_dir, child.filename)
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"Failed to delete {filepath}: {e}")
        
        for card in cards_to_remove:
            grid.remove_widget(card)
        
        self.selected_count = 0
        self.selection_mode = False
        self.update_storage_stats()

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

    def on_active_nav(self, instance, value):
        sm = self.ids.get('content_manager')
        if sm:
            if value == "Drone LED":
                sm.current = "LED"
            elif value == "Drone Fleet":
                # Close the gallery and open the DroneManager overlay
                app = App.get_running_app()
                self.parent.remove_widget(self)
                app._gallery = None
                app.on_action("DRONES")
            else:
                sm.current = "Media"
                self.load_recordings()

    def _get_grid(self):
        """Find the media grid widget by id."""
        try:
            return self.ids.media_grid
        except AttributeError:
            return None

    def load_recordings(self):
        """Scan the recordings directory and populate the media grid with filters."""
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

        # Define category filters
        show_all = self.active_nav == "All Media"
        show_photos = self.active_nav == "Photos"
        show_videos = self.active_nav == "Videos"
        show_favorites = self.active_nav == "Favorites"

        if os.path.exists(rec_dir):
            for f in sorted(os.listdir(rec_dir), reverse=True):
                filepath = os.path.join(rec_dir, f)
                if os.path.isfile(filepath):
                    is_video = f.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
                    is_photo = f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))
                    is_log = f.lower().endswith('.json')
                    
                    # Filtering logic
                    if self.active_nav == "Flight Logs":
                        if not is_log: continue
                    elif not show_all:
                        if show_photos and not is_photo: continue
                        if show_videos and not is_video: continue
                        # Favorites placeholder check (assuming we don't have a DB yet, just show none)
                        if show_favorites: continue 
                    else:
                        # In "All Media", ignore .json logs to avoid clutter, unless specifically asked
                        if is_log: continue 

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
        else:
            self.view_media(card.filename)

    def view_media(self, filename):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        rec_dir = os.path.join(base_dir, "recordings")
        if not os.path.exists(rec_dir):
            rec_dir = os.path.join(os.path.dirname(base_dir), "recordings")
        
        filepath = os.path.join(rec_dir, filename)
        if not os.path.exists(filepath): return

        viewer = self.ids.media_viewer
        viewer.source = filepath
        viewer.active = True
        
        content = self.ids.viewer_content
        content.clear_widgets()
        
        is_video = filename.lower().endswith(('.mp4', '.avi', '.mov', '.mkv'))
        is_log = filename.lower().endswith('.json')
        if is_video:
            v = Video(source=filepath, state='play', options={'eos': 'loop'})
            content.add_widget(v)
        elif is_log:
            # Simple text display for the log
            try:
                import json
                with open(filepath, 'r') as f:
                    log_data = json.load(f)
                text = json.dumps(log_data, indent=2)
            except Exception as e:
                text = f"Error reading log:\n{e}"
            from kivy.uix.label import Label
            lbl = Label(text=text, font_size='11sp', color=(0.8, 0.9, 1, 1), 
                        text_size=(content.width - 40, None), 
                        halign='left', valign='top')
            lbl.bind(width=lambda *x: lbl.setter('text_size')(lbl, (lbl.width, None)))
            lbl.bind(texture_size=lbl.setter('size'))
            from kivy.uix.scrollview import ScrollView
            sv = ScrollView(size_hint=(1, 1))
            sv.add_widget(lbl)
            content.add_widget(sv)
        else:
            img = Image(source=filepath)
            content.add_widget(img)

    def close_viewer(self):
        viewer = self.ids.media_viewer
        viewer.active = False
        self.ids.viewer_content.clear_widgets()
