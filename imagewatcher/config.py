"""Persistencia de configuracion en ~/.config/imagewatcher/config.json."""
import json
import os
from pathlib import Path

from . import __app_id__
from .actions import HOTKEY_DEFAULTS

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / __app_id__
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS = {
    "save_dir": str(Path.home() / "Pictures" / "imageWatcher"),
    "save_format": "png",
    "jpeg_quality": 90,
    "auto_save": False,
    "copy_to_clipboard": True,
    "open_editor": True,
    "capture_cursor": False,
    "show_capture_bar": True,
    "snap_enabled": True,
    "delay_seconds": 3,
    "last_region": None,
    "fixed_region_size": [360, 360],
    "hotkeys": dict(HOTKEY_DEFAULTS),
    "hotkeys_enabled": True,
    "color_format": "hex",
    "color_zoom": 11,
    "color_history": [],
    "record_fps": 25,
    "record_audio": False,
    "theme": "system",
    "show_welcome": True,
}


class Config:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULTS))
        self.load()

    def load(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            self._merge(self.data, stored)
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            pass

    def _merge(self, base, extra):
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._merge(base[key], value)
            else:
                base[key] = value

    def save(self):
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2, ensure_ascii=False)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)

    def ensure_save_dir(self):
        path = Path(self.data["save_dir"]).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path
