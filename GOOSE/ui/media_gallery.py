import os
import datetime
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    StringProperty, BooleanProperty, NumericProperty, ListProperty, ObjectProperty
)
from kivy.animation import Animation
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.button import Button

class HoverBehavior(object):
    """
    A mixin class to add hover detection behavior to Kivy widgets.
    Binds Window.mouse_pos when the widget has a parent/root window,
    and unbinds it when removed to prevent memory leaks.
    """
    hovered = BooleanProperty(False)
    _hovered_widgets = set()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(parent=self._on_parent_change)

    def _on_parent_change(self, widget, parent):
        if parent:
            Window.bind(mouse_pos=self.on_mouse_pos)
        else:
            Window.unbind(mouse_pos=self.on_mouse_pos)
            if self in HoverBehavior._hovered_widgets:
                HoverBehavior._hovered_widgets.remove(self)
                self._update_system_cursor()
            self.hovered = False

    def on_mouse_pos(self, window, pos):
        if not self.get_root_window():
            return False
            
        # Get position relative to the widget's coordinate space
        local_x, local_y = self.to_widget(*pos)
        inside = (0 <= local_x <= self.width) and (0 <= local_y <= self.height)
        
        if inside != self.hovered:
            self.hovered = inside
            if inside:
                HoverBehavior._hovered_widgets.add(self)
            else:
                if self in HoverBehavior._hovered_widgets:
                    HoverBehavior._hovered_widgets.remove(self)
            self._update_system_cursor()
        return False

    def _update_system_cursor(self):
        if HoverBehavior._hovered_widgets:
            Window.set_system_cursor('hand')
        else:
            Window.set_system_cursor('arrow')


class ClickableLabel(HoverBehavior, ButtonBehavior, Label):
    """A label that responds to click and hover behaviors."""
    pass


class ClickableBox(HoverBehavior, ButtonBehavior, BoxLayout):
    """A box layout that responds to click and hover behaviors."""
    pass


class HoverButton(HoverBehavior, Button):
    """A standard button that changes cursor and properties on hover."""
    pass


class MediaCard(HoverBehavior, ButtonBehavior, BoxLayout):
    """Individual media item card in the gallery grid."""
    filename = StringProperty("")
    file_size = StringProperty("0 MB")
    file_date = StringProperty("")
    is_video = BooleanProperty(False)
    is_favorited = BooleanProperty(False)
    is_selected = BooleanProperty(False)
    # Color for the placeholder thumbnail gradient
    thumb_color = ListProperty([0.15, 0.2, 0.25, 1])


class NavItem(HoverBehavior, ButtonBehavior, BoxLayout):
    """Sidebar navigation item."""
    icon = StringProperty("")
    text = StringProperty("")
    is_active = BooleanProperty(False)


class PresetCard(HoverBehavior, ButtonBehavior, BoxLayout):
    """Preset matrix patterns selection card."""
    text = StringProperty("")
    icon = StringProperty("")
    pattern_string = StringProperty("")
    grid_id = ObjectProperty(None, allownone=True)
    color_theme = ListProperty([0.2, 0.6, 1, 1])


class FilterChip(HoverBehavior, ButtonBehavior, BoxLayout):
    """Filter chip/tag button in the filter bar."""
    text = StringProperty("")
    is_active = BooleanProperty(False)
    has_dropdown = BooleanProperty(False)


from kivy.uix.image import Image
from kivy.uix.video import Video
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.graphics import Color, RoundedRectangle, Line, Ellipse, Rectangle
from kivy.uix.widget import Widget

class LEDPixel(Widget):
    """
    Individually addressable grid element representing one physical pixel on the Tello's 8x8 LED matrix.
    Uses Canvas instructions instead of child widgets to minimize layout pass overhead and optimize render cycles.
    """
    state_color = StringProperty('0')
    
    def __init__(self, index, **kwargs):
        super().__init__(**kwargs)
        self.pixel_index = index
        # Bind property listeners to redraw triggers to support reactive visual state updates
        self.bind(pos=self.redraw, size=self.redraw, state_color=self.redraw)
        
    def redraw(self, *args):
        # Clear existing graphics buffers to prevent graphic artifact accumulation
        self.canvas.before.clear()
        self.canvas.clear()
        
        # Consistent color token palette matching the physical LED matrix color spectrum
        colors = {
            '0': (20/255, 26/255, 42/255, 1),   # Matrix Off (Deep Blue-Grey background)
            'r': (255/255, 60/255, 80/255, 1),   # High-intensity Red
            'b': (0/255, 160/255, 255/255, 1),  # Vivid Blue
            'p': (180/255, 70/255, 255/255, 1)  # Vivid Purple
        }
        
        with self.canvas.before:
            Color(*colors[self.state_color])
            RoundedRectangle(pos=self.pos, size=self.size, radius=[4])


class LEDDrawingGrid(GridLayout):
    """
    Interactive drawing canvas wrapping 64 LEDPixel instances.
    Implements multi-touch/drag collision handling to bypass Kivy Button's touch ingestion,
    enabling natural gesture painting across the matrix.
    """
    active_color = StringProperty('r')  # The currently selected brush state
    
    def __init__(self, **kwargs):
        kwargs.setdefault('cols', 8)
        kwargs.setdefault('rows', 8)
        kwargs.setdefault('spacing', 3)
        super().__init__(**kwargs)
        self.pixels = []
        for i in range(64):
            pixel = LEDPixel(index=i)
            self.add_widget(pixel)
            self.pixels.append(pixel)
            
    def on_touch_down(self, touch):
        # Intercept touch events falling within bounding box to start drawing
        if self.collide_point(*touch.pos):
            touch.grab(self)
            self.paint_at_touch(touch.pos)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        # Process drag gestures: paint intersecting pixels on motion events
        if touch.grab_current is self:
            self.paint_at_touch(touch.pos)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def paint_at_touch(self, pos):
        # Convert window/parent coordinate pos to LEDDrawingGrid's local coordinates
        local_x, local_y = self.to_local(*pos)
        
        # Check if coordinates are within the grid bounds
        if 0 <= local_x < self.width and 0 <= local_y < self.height:
            # Map coordinates to 8x8 row/col grid
            col = int(local_x / (self.width / 8.0))
            row = int(local_y / (self.height / 8.0))
            
            # Clamp bounds to make sure we don't index out of range
            col = max(0, min(7, col))
            row = max(0, min(7, row))
            
            # Since Kivy local_y grows bottom-to-top, but our pixels are added top-to-bottom:
            grid_row = 7 - row
            pixel_index = grid_row * 8 + col
            
            if 0 <= pixel_index < len(self.pixels):
                pixel = self.pixels[pixel_index]
                if pixel.state_color != self.active_color:
                    pixel.state_color = self.active_color

    def load_pattern_string(self, pattern_string):
        """Loads a 64-character pattern string into the grid colors."""
        if not pattern_string or len(pattern_string) != 64:
            return
        for i, char in enumerate(pattern_string):
            if i < len(self.pixels):
                if char in ('0', 'r', 'b', 'p'):
                    self.pixels[i].state_color = char

    def get_pattern_string(self):
        """Serializes current grid state into a 64-character payload string for SDK dispatch."""
        return "".join(p.state_color for p in self.pixels)

    def clear_grid(self):
        """Resets all matrix pixels back to the Off state ('0')."""
        for p in self.pixels:
            p.state_color = '0'

    def load_pattern_string(self, pattern_str):
        """Deserializes a 64-character payload string to load a pattern state onto the canvas grid."""
        if len(pattern_str) == 64:
            for i, char in enumerate(pattern_str):
                if char in ('0', 'r', 'b', 'p'):
                    self.pixels[i].state_color = char

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
    scroll_color = StringProperty("r")
    scroll_dir = StringProperty("l")

    def on_touch_down(self, touch):
        """Consume all touches when gallery is open (block underlying UI)."""
        if not self.is_open:
            return False
        # Give children the first opportunity to ingest the touch event
        if super().on_touch_down(touch):
            return True
        # Block the event from passing through to underlying dashboard widgets
        if self.collide_point(*touch.pos):
            return True
        return False

    def on_touch_move(self, touch):
        if not self.is_open:
            return False
        if super().on_touch_move(touch):
            return True
        if self.collide_point(*touch.pos):
            return True
        return False

    def on_touch_up(self, touch):
        if not self.is_open:
            return False
        if super().on_touch_up(touch):
            return True
        if self.collide_point(*touch.pos):
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
        """Simulate syncing media from drone with proper loading state and HUD messages."""
        app = App.get_running_app()
        from ui.icons import Icons
        app.show_loading(
            "Syncing Media", 
            "Establishing connection and pulling media files...", 
            Icons.sync
        )
        
        # Schedule the simulated sync to finish after a 1.5s delay
        from kivy.clock import Clock
        def complete_sync(dt):
            self.load_recordings()
            self.update_storage_stats()
            app.hide_loading()
            app.show_hud_message("Sync Completed: 4 new media files retrieved")
            
        Clock.schedule_once(complete_sync, 1.5)

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
            elif value == "Settings":
                sm.current = "Settings"
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
            try:
                map_widget = FlightPathMap(size_hint=(1, 1))
                content.add_widget(map_widget)
                # Bind size and pos changes to redraw the map dynamically when dimensions update
                map_widget.bind(size=lambda *x: map_widget.redraw_map(), pos=lambda *x: map_widget.redraw_map())
                map_widget.load_flight_data(filepath)
            except Exception as e:
                print(f"[Gallery] Error loading flight log map: {e}")
                from kivy.uix.label import Label
                content.add_widget(Label(text=f"Error reading log map: {e}", color=(1, 0.3, 0.3, 1)))
        else:
            img = Image(source=filepath)
            content.add_widget(img)

    def close_viewer(self):
        viewer = self.ids.media_viewer
        viewer.active = False
        self.ids.viewer_content.clear_widgets()

    def open_in_system_viewer(self):
        """Open the active media file in the system's default viewer/application."""
        viewer = self.ids.media_viewer
        filepath = getattr(viewer, 'source', None)
        if filepath and os.path.exists(filepath):
            try:
                os.startfile(filepath)
            except Exception as e:
                print(f"[Gallery] Failed to open in system viewer: {e}")


class FlightPathMap(Widget):
    """
    Renders a 2D reconstructed flight path from an RC command recording.
    Highlights coordinates by altitude using color interpolation from Red (low) to Green (high).
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.positions = []
        self.bounds = (0, 0, 0, 0, 0, 0, 1, 1, 1)

    def load_flight_data(self, filepath):
        import json
        import math
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"[FlightPathMap] Error loading flight log: {e}")
            return
            
        rc_commands = data.get("rc_commands", [])
        events = data.get("events", [])
        
        # Dead reckoning integration to estimate (x,y,z) trajectory
        positions = [] # list of (x, y, z)
        
        # Scaling factors
        K_xy = 0.02   # m/s per stick unit
        K_z = 0.01    # m/s per stick unit
        K_yaw = 1.2   # deg/s per stick unit
        
        x, y, z = 0.0, 0.0, 0.0
        yaw = 0.0
        
        # Parse events to find takeoff/land times
        takeoff_time = None
        land_time = None
        for evt in events:
            if evt.get("type") == "takeoff":
                takeoff_time = evt.get("t")
            elif evt.get("type") == "land":
                land_time = evt.get("t")
                
        last_t = 0.0
        is_airborne = False
        
        # Add starting point
        positions.append((x, y, z))
        
        for cmd in rc_commands:
            t = cmd.get("t", 0.0)
            lr = cmd.get("lr", 0)
            fb = cmd.get("fb", 0)
            ud = cmd.get("ud", 0)
            yv = cmd.get("yv", 0)
            
            dt = t - last_t
            if dt <= 0:
                dt = 0.01
            last_t = t
            
            # Check airborne state from events
            if takeoff_time is not None and t >= takeoff_time:
                is_airborne = True
                if len(positions) == 1 and z == 0.0:
                    z = 1.0 # Set initial takeoff height
            if land_time is not None and t >= land_time:
                is_airborne = False
                
            # If not airborne, commands don't move the drone
            if is_airborne:
                # Update yaw (heading)
                yaw += yv * K_yaw * dt
                yaw_rad = math.radians(yaw)
                
                # Local velocities
                vx_local = lr * K_xy
                vy_local = fb * K_xy
                
                # Rotate to global coordinates
                vx_global = vx_local * math.cos(yaw_rad) - vy_local * math.sin(yaw_rad)
                vy_global = vx_local * math.sin(yaw_rad) + vy_local * math.cos(yaw_rad)
                
                x += vx_global * dt
                y += vy_global * dt
                z += ud * K_z * dt
                z = max(0.0, z) # Cannot go below ground
                
            positions.append((x, y, z))
            
        self.draw_path(positions)

    def draw_path(self, positions):
        self.canvas.clear()
        if not positions or len(positions) < 2:
            return
            
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        zs = [p[2] for p in positions]
        
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        min_z, max_z = min(zs), max(zs)
        
        dx = max_x - min_x
        dy = max_y - min_y
        dz = max_z - min_z
        
        # Add padding to bounding box
        padding = 1.0
        min_x -= padding
        max_x += padding
        min_y -= padding
        max_y += padding
        dx = max_x - min_x
        dy = max_y - min_y
        
        # Avoid zero division
        if dx == 0: dx = 1.0
        if dy == 0: dy = 1.0
        if dz == 0: dz = 1.0
        
        self.positions = positions
        self.bounds = (min_x, max_x, min_y, max_y, min_z, max_z, dx, dy, dz)
        self.redraw_map()

    def redraw_map(self):
        self.canvas.clear()
        if not self.positions or len(self.positions) < 2:
            return
            
        min_x, max_x, min_y, max_y, min_z, max_z, dx, dy, dz = self.bounds
        
        margin = 30
        draw_w = self.width - 2 * margin
        draw_h = self.height - 2 * margin
        if draw_w <= 0 or draw_h <= 0:
            return
            
        scale_x = draw_w / dx
        scale_y = draw_h / dy
        scale = min(scale_x, scale_y)
        
        offset_x = margin + (draw_w - dx * scale) / 2
        offset_y = margin + (draw_h - dy * scale) / 2
        
        def to_screen(sx, sy):
            px = offset_x + (sx - min_x) * scale
            py = offset_y + (sy - min_y) * scale
            return self.x + px, self.y + py
            
        with self.canvas:
            # Draw grid lines/background
            Color(0.1, 0.15, 0.25, 0.5)
            # Draw a subtle bounding rectangle
            Line(rectangle=(self.x + margin, self.y + margin, draw_w, draw_h), width=1)
            
            # Draw grid coordinate lines
            for i in range(1, 5):
                # Vertical grid lines
                lx = self.x + margin + i * (draw_w / 5.0)
                Line(points=[lx, self.y + margin, lx, self.y + margin + draw_h], width=0.5)
                # Horizontal grid lines
                ly = self.y + margin + i * (draw_h / 5.0)
                Line(points=[self.x + margin, ly, self.x + margin + draw_w, ly], width=0.5)
                
            # Draw path segments colored by height
            for i in range(len(self.positions) - 1):
                p1 = self.positions[i]
                p2 = self.positions[i+1]
                
                screen_p1 = to_screen(p1[0], p1[1])
                screen_p2 = to_screen(p2[0], p2[1])
                
                avg_z = (p1[2] + p2[2]) / 2.0
                t = (avg_z - min_z) / dz
                t = max(0.0, min(1.0, t))
                
                # Interpolate between Red (t=0) and Green (t=1)
                Color(1.0 - t, t, 0.0, 1.0)
                Line(points=[screen_p1[0], screen_p1[1], screen_p2[0], screen_p2[1]], width=2.5)
                
            # Draw start marker (blue circle)
            start_p = to_screen(self.positions[0][0], self.positions[0][1])
            Color(0.0, 0.6, 1.0, 1.0)
            Ellipse(pos=(start_p[0] - 6, start_p[1] - 6), size=(12, 12))
            
            # Draw end marker (yellow circle)
            end_p = to_screen(self.positions[-1][0], self.positions[-1][1])
            Color(1.0, 0.8, 0.0, 1.0)
            Ellipse(pos=(end_p[0] - 6, end_p[1] - 6), size=(12, 12))
