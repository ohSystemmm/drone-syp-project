"""
DroneManager — Full-screen overlay for managing drone fleet.

Provides UI to:
  - View all registered drones (name, IP, last-used)
  - Add new drones (IP + optional nickname)
  - Edit existing drone names / IPs
  - Delete drones from the registry
  - Connect to a selected drone
"""

import logging
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.behaviors import ButtonBehavior
from kivy.properties import (
    StringProperty, BooleanProperty, NumericProperty, ListProperty
)
from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock

logger = logging.getLogger(__name__)


class DroneCard(ButtonBehavior, BoxLayout):
    """A single drone entry in the fleet list."""
    drone_name = StringProperty("")
    drone_ip = StringProperty("")
    last_used = StringProperty("")
    is_active = BooleanProperty(False)
    is_editing = BooleanProperty(False)


class DroneManager(FloatLayout):
    """Full-screen drone fleet management overlay."""
    is_open = BooleanProperty(False)

    # "Add drone" form fields
    new_drone_ip = StringProperty("")
    new_drone_name = StringProperty("")

    # Edit mode tracking
    editing_ip = StringProperty("")
    editing_name = StringProperty("")
    edit_original_ip = StringProperty("")

    def on_touch_down(self, touch):
        """Consume all touches when panel is open (block underlying UI)."""
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
        self.refresh_drone_list()

    def close(self):
        self.is_open = False
        app = App.get_running_app()
        app.close_drone_manager()

    # ── List management ──────────────────────────────────────────

    def _get_grid(self):
        try:
            return self.ids.drone_grid
        except AttributeError:
            return None

    def refresh_drone_list(self):
        """Rebuild the drone card list from the registry."""
        grid = self._get_grid()
        if not grid:
            return

        grid.clear_widgets()

        app = App.get_running_app()
        registry = app.drone_registry
        drones = registry.list_all()
        active_ip = registry.last_active_ip

        for d in drones:
            ip = d.get("ip", "")
            name = d.get("name", "")
            last = d.get("last_used", "")

            # Friendly date
            if last:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(last)
                    last = dt.strftime("%b %d, %H:%M")
                except Exception:
                    last = last[:16]

            card = DroneCard(
                drone_name=name,
                drone_ip=ip,
                last_used=last,
                is_active=(ip == active_ip and app.controller.is_connected),
            )
            card.bind(on_release=lambda c: self.on_drone_card_pressed(c))
            grid.add_widget(card)

    # ── Actions ──────────────────────────────────────────────────

    def add_drone(self):
        """Add a drone from the form fields."""
        ip = self.new_drone_ip.strip()
        name = self.new_drone_name.strip()

        if not ip:
            logger.warning("[DroneManager] Cannot add drone: empty IP")
            return

        app = App.get_running_app()
        app.drone_registry.add_or_update(ip, name=name)
        logger.info("[DroneManager] Added drone %s (%s)", ip, name)

        # Reset form
        self.new_drone_ip = ""
        self.new_drone_name = ""
        try:
            self.ids.input_ip.text = ""
            self.ids.input_name.text = ""
        except Exception:
            pass

        self.refresh_drone_list()

    def on_drone_card_pressed(self, card):
        """Show edit controls for the pressed drone."""
        pass  # Tapping is handled via inline buttons in KV

    def connect_drone(self, ip):
        """Disconnect current drone and connect to the selected IP."""
        app = App.get_running_app()

        # Disconnect first if connected
        if app.controller.is_connected:
            app.controller.disconnect()
            app.root.ids.header.is_connected = False
            app.root.ids.header.status_text = "DISCONNECTED"

        # Update args IP and reconnect
        if app.args:
            app.args.ip = ip
        app.drone_registry.last_active_ip = ip
        app.drone_registry._save()

        self.close()
        Clock.schedule_once(lambda dt: app.connect_to_drone(), 0.3)

    def delete_drone(self, ip):
        """Remove a drone from the registry."""
        app = App.get_running_app()
        app.drone_registry.remove(ip)
        logger.info("[DroneManager] Removed drone %s", ip)
        self.refresh_drone_list()

    def start_edit(self, ip, name):
        """Begin editing a drone entry."""
        self.edit_original_ip = ip
        self.editing_ip = ip
        self.editing_name = name

        # Mark the correct card as editing
        grid = self._get_grid()
        if grid:
            for child in grid.children:
                if isinstance(child, DroneCard):
                    child.is_editing = (child.drone_ip == ip)

    def save_edit(self):
        """Save edits to the drone entry."""
        app = App.get_running_app()
        registry = app.drone_registry

        old_ip = self.edit_original_ip
        new_ip = self.editing_ip.strip()
        new_name = self.editing_name.strip()

        if not new_ip:
            return

        if old_ip != new_ip:
            # IP changed: remove old, add new
            registry.remove(old_ip)
            registry.add_or_update(new_ip, name=new_name)
        else:
            registry.set_name(old_ip, new_name)

        self.cancel_edit()
        self.refresh_drone_list()

    def cancel_edit(self):
        """Cancel edit mode on all cards."""
        self.edit_original_ip = ""
        self.editing_ip = ""
        self.editing_name = ""

        grid = self._get_grid()
        if grid:
            for child in grid.children:
                if isinstance(child, DroneCard):
                    child.is_editing = False
