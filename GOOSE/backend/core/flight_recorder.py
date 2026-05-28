"""
FlightRecorder — Record and replay drone RC commands for repeatable flights.

Usage:
    recorder = FlightRecorder()
    recorder.start_recording()
    # ... in main loop:
    recorder.record_rc(lr, fb, ud, yv)
    recorder.record_event("takeoff")
    recorder.stop_recording()

    recorder.load_latest()
    recorder.start_replay()
    # ... in main loop:
    rc = recorder.get_replay_rc()  # returns (lr, fb, ud, yv) or None
    evt = recorder.get_replay_event()  # returns event string or None
"""

import json
import os
import time
import datetime
import logging
import glob

logger = logging.getLogger(__name__)


class FlightRecorder:
    # Minimum interval between recorded RC samples (seconds).
    # At 60 Hz main loop, 50 ms gives ~20 samples/s — more than enough fidelity.
    RC_SAMPLE_INTERVAL = 0.05

    def __init__(self, recordings_dir=None):
        if recordings_dir is None:
            # Auto-detect project layout
            if os.path.exists("GOOSE/recordings"):
                recordings_dir = "GOOSE/recordings"
            elif os.path.exists("recordings"):
                recordings_dir = "recordings"
            else:
                recordings_dir = "GOOSE/recordings"
        self.recordings_dir = recordings_dir
        os.makedirs(self.recordings_dir, exist_ok=True)

        # --- Recording state ---
        self.is_recording = False
        self._rec_start = 0.0
        self._rec_events = []
        self._rec_commands = []
        self._last_rc_sample_time = 0.0
        self._last_rc_values = None

        # --- Replay state ---
        self.is_replaying = False
        self._replay_data = None
        self._replay_start = 0.0
        self._replay_rc_idx = 0
        self._replay_evt_idx = 0
        self._replay_path = None

    # ------------------------------------------------------------------ #
    #  RECORDING
    # ------------------------------------------------------------------ #

    def start_recording(self):
        """Begin a new recording session."""
        self.is_recording = True
        self._rec_start = time.monotonic()
        self._rec_events = []
        self._rec_commands = []
        self._last_rc_sample_time = 0.0
        self._last_rc_values = None
        logger.info("[FlightRecorder] Recording STARTED")

    def record_event(self, event_type: str):
        """Record a discrete event (e.g. 'takeoff', 'land')."""
        if not self.is_recording:
            return
        t = time.monotonic() - self._rec_start
        self._rec_events.append({"t": round(t, 4), "type": event_type})
        logger.debug("[FlightRecorder] Event recorded: %s @ %.3fs", event_type, t)

    def record_rc(self, lr: int, fb: int, ud: int, yv: int):
        """Record an RC command sample (throttled to RC_SAMPLE_INTERVAL)."""
        if not self.is_recording:
            return

        now = time.monotonic()
        t = now - self._rec_start
        current = (lr, fb, ud, yv)

        # Throttle: only record if enough time passed OR values changed
        elapsed = now - self._last_rc_sample_time
        if elapsed < self.RC_SAMPLE_INTERVAL and current == self._last_rc_values:
            return

        self._rec_commands.append({
            "t": round(t, 4),
            "lr": lr, "fb": fb, "ud": ud, "yv": yv,
        })
        self._last_rc_sample_time = now
        self._last_rc_values = current

    def stop_recording(self, name=None):
        """Stop recording and save to a JSON file. Returns the file path.
        
        Args:
            name: Optional user-chosen name for the recording.
                  If None, auto-generates from timestamp.
        """
        if not self.is_recording:
            return None

        self.is_recording = False
        duration = time.monotonic() - self._rec_start

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        if name:
            # Sanitize name for filesystem
            safe_name = "".join(c if c.isalnum() or c in ('-', '_', ' ') else '_' for c in name)
            filename = f"flight_rec_{ts}_{safe_name}.json"
        else:
            filename = f"flight_rec_{ts}.json"
        path = os.path.join(self.recordings_dir, filename)

        data = {
            "version": 1,
            "name": name or ts,
            "date": datetime.datetime.now().isoformat(),
            "duration_s": round(duration, 2),
            "num_commands": len(self._rec_commands),
            "num_events": len(self._rec_events),
            "events": self._rec_events,
            "rc_commands": self._rec_commands,
        }

        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("[FlightRecorder] Recording SAVED: %s (%d cmds, %d events, %.1fs)",
                        path, len(self._rec_commands), len(self._rec_events), duration)
        except Exception as e:
            logger.exception("[FlightRecorder] Failed to save recording")
            return None

        self._rec_events = []
        self._rec_commands = []
        return path

    def rename_recording(self, path, new_name):
        """Update the 'name' field inside an existing recording file."""
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            data["name"] = new_name
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info("[FlightRecorder] Renamed recording: %s → '%s'", path, new_name)
            return True
        except Exception:
            logger.exception("[FlightRecorder] Failed to rename recording")
            return False

    def list_recordings(self):
        """Returns a list of all saved recordings with metadata.
        
        Each entry: {"path": str, "name": str, "date": str, "duration_s": float, "num_commands": int}
        Sorted newest first.
        """
        pattern = os.path.join(self.recordings_dir, "flight_rec_*.json")
        files = sorted(glob.glob(pattern), reverse=True)
        recordings = []
        for fpath in files:
            try:
                with open(fpath, 'r') as f:
                    data = json.load(f)
                recordings.append({
                    "path": fpath,
                    "name": data.get("name", os.path.basename(fpath)),
                    "date": data.get("date", ""),
                    "duration_s": data.get("duration_s", 0),
                    "num_commands": data.get("num_commands", len(data.get("rc_commands", []))),
                })
            except Exception:
                recordings.append({"path": fpath, "name": os.path.basename(fpath), "date": "", "duration_s": 0, "num_commands": 0})
        return recordings

    # ------------------------------------------------------------------ #
    #  REPLAY
    # ------------------------------------------------------------------ #

    def load_recording(self, path: str) -> bool:
        """Load a specific recording file."""
        try:
            with open(path, 'r') as f:
                self._replay_data = json.load(f)
            self._replay_path = path
            logger.info("[FlightRecorder] Loaded recording: %s (%.1fs, %d cmds)",
                        path,
                        self._replay_data.get("duration_s", 0),
                        len(self._replay_data.get("rc_commands", [])))
            return True
        except Exception as e:
            logger.exception("[FlightRecorder] Failed to load recording: %s", path)
            return False

    def load_latest(self) -> bool:
        """Load the most recent recording file from the recordings directory."""
        pattern = os.path.join(self.recordings_dir, "flight_rec_*.json")
        files = sorted(glob.glob(pattern))
        if not files:
            logger.warning("[FlightRecorder] No recordings found in %s", self.recordings_dir)
            return False
        return self.load_recording(files[-1])

    def start_replay(self):
        """Begin replaying the loaded recording."""
        if not self._replay_data:
            logger.warning("[FlightRecorder] No recording loaded, cannot replay")
            return False
        self.is_replaying = True
        self._replay_start = time.monotonic()
        self._replay_rc_idx = 0
        self._replay_evt_idx = 0
        logger.info("[FlightRecorder] Replay STARTED")
        return True

    def get_replay_rc(self):
        """
        Returns (lr, fb, ud, yv) for the current replay time.
        Returns None when replay is finished.
        """
        if not self.is_replaying or not self._replay_data:
            return None

        elapsed = time.monotonic() - self._replay_start
        commands = self._replay_data.get("rc_commands", [])

        if not commands:
            self._finish_replay()
            return None

        # Advance index to the latest command at or before current time
        while (self._replay_rc_idx < len(commands) - 1 and
               commands[self._replay_rc_idx + 1]["t"] <= elapsed):
            self._replay_rc_idx += 1

        # Check if we've passed the end of the recording
        duration = self._replay_data.get("duration_s", 0)
        if elapsed > duration:
            self._finish_replay()
            return None

        cmd = commands[self._replay_rc_idx]
        return (cmd["lr"], cmd["fb"], cmd["ud"], cmd["yv"])

    def get_replay_event(self):
        """
        Returns the next event string if its timestamp has been reached.
        Returns None otherwise.
        """
        if not self.is_replaying or not self._replay_data:
            return None

        elapsed = time.monotonic() - self._replay_start
        events = self._replay_data.get("events", [])

        if self._replay_evt_idx < len(events):
            evt = events[self._replay_evt_idx]
            if evt["t"] <= elapsed:
                self._replay_evt_idx += 1
                return evt["type"]

        return None

    def stop_replay(self):
        """Manually stop replay."""
        if self.is_replaying:
            self._finish_replay()

    def _finish_replay(self):
        self.is_replaying = False
        self._replay_rc_idx = 0
        self._replay_evt_idx = 0
        logger.info("[FlightRecorder] Replay FINISHED")

    @property
    def replay_progress(self):
        """Returns (elapsed, total) seconds for OSD display."""
        if not self.is_replaying or not self._replay_data:
            return (0, 0)
        elapsed = time.monotonic() - self._replay_start
        total = self._replay_data.get("duration_s", 0)
        return (min(elapsed, total), total)

    @property
    def recording_duration(self):
        """Returns current recording duration in seconds."""
        if not self.is_recording:
            return 0
        return time.monotonic() - self._rec_start
