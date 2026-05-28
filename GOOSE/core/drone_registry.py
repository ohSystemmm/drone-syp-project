"""
DroneRegistry — Persistent storage for drone IPs, names, and last-used info.

Stores a JSON file at assets/drone_registry.json:
{
    "drones": [
        {"ip": "192.168.10.1", "name": "Tello #1", "last_used": "2026-04-08T09:00:00"},
        {"ip": "192.168.0.102", "name": "Training Drone", "last_used": "2026-04-07T14:30:00"}
    ],
    "last_active_ip": "192.168.0.102"
}
"""

import json
import os
import datetime
import logging

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "assets", "drone_registry.json"
)


class DroneRegistry:
    def __init__(self, path=None):
        self.path = path or DEFAULT_REGISTRY_PATH
        self.drones = []
        self.last_active_ip = None
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r') as f:
                data = json.load(f)
            self.drones = data.get("drones", [])
            self.last_active_ip = data.get("last_active_ip")
            logger.info("[DroneRegistry] Loaded %d drones from %s", len(self.drones), self.path)
        except (FileNotFoundError, json.JSONDecodeError):
            self.drones = []
            self.last_active_ip = None

    def _save(self):
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            data = {
                "drones": self.drones,
                "last_active_ip": self.last_active_ip,
            }
            with open(self.path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("[DroneRegistry] Failed to save: %s", e)

    def add_or_update(self, ip: str, name: str = ""):
        """Add a new drone or update existing entry. Marks as last used."""
        for drone in self.drones:
            if drone["ip"] == ip:
                if name:
                    drone["name"] = name
                drone["last_used"] = datetime.datetime.now().isoformat()
                self.last_active_ip = ip
                self._save()
                return
        # New entry
        self.drones.append({
            "ip": ip,
            "name": name or f"Drone-{ip.split('.')[-1]}",
            "last_used": datetime.datetime.now().isoformat(),
        })
        self.last_active_ip = ip
        self._save()
        logger.info("[DroneRegistry] Added drone: %s (%s)", ip, name)

    def get_name(self, ip: str) -> str:
        """Get the user-assigned name for a drone IP."""
        for drone in self.drones:
            if drone["ip"] == ip:
                return drone.get("name", "")
        return ""

    def set_name(self, ip: str, name: str):
        """Set/update the drone name for a given IP."""
        for drone in self.drones:
            if drone["ip"] == ip:
                drone["name"] = name
                self._save()
                return True
        return False

    def list_all(self):
        """Returns list of all registered drones sorted by last_used (newest first)."""
        return sorted(self.drones, key=lambda d: d.get("last_used", ""), reverse=True)

    def remove(self, ip: str):
        """Remove a drone entry."""
        self.drones = [d for d in self.drones if d["ip"] != ip]
        if self.last_active_ip == ip:
            self.last_active_ip = self.drones[0]["ip"] if self.drones else None
        self._save()
