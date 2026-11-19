"""Pruebas del grabador de pantalla."""
from pathlib import Path

from gi.repository import GLib

from imagewatcher.recorder import RecorderWindow


class _Config:
    def __init__(self):
        self.data = {
            "record_fps": 25,
            "record_audio": False,
            "record_countdown": 3,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def __setitem__(self, key, value):
        self.data[key] = value

    def save(self):
        pass

    def ensure_save_dir(self):
        return Path("/tmp")


def _recorder():
    return RecorderWindow(_Config(), countdown_overlay=False)


def test_recorder_countdown_starts_recording():
    recorder = _recorder()
    recorder._can_start = lambda: True
    calls = []
    recorder._start_recording = lambda: calls.append(True)
    recorder.countdown_spin.set_value(2)
    try:
        recorder._start()
        assert recorder._countdown_timer is not None
        assert recorder.stop_btn.get_sensitive()
        assert recorder.timer_label.get_text() == "2"

        GLib.source_remove(recorder._countdown_timer)
        recorder._countdown_tick()
        assert recorder.timer_label.get_text() == "1"

        recorder._countdown_tick()
        assert calls == [True]
        assert recorder._countdown_timer is None
    finally:
        recorder._cancel_countdown()
        recorder.destroy()


def test_recorder_countdown_can_be_cancelled():
    recorder = _recorder()
    recorder._can_start = lambda: True
    recorder._start_recording = lambda: None
    recorder.countdown_spin.set_value(5)
    try:
        recorder._start()
        assert recorder._countdown_timer is not None
        recorder._stop()
        assert recorder._countdown_timer is None
        assert "cancelada" in recorder.status.get_text()
        assert recorder.start_btn.get_sensitive()
    finally:
        recorder.destroy()


def test_countdown_updates_fullscreen_overlay():
    recorder = _recorder()

    class _Overlay:
        def __init__(self):
            self.value = None
            self.destroyed = False

        def set_remaining(self, value):
            self.value = value

        def destroy(self):
            self.destroyed = True

    overlay = _Overlay()
    recorder.countdown_overlay_enabled = True
    recorder._countdown_overlay = overlay
    recorder._countdown_remaining = 4
    try:
        recorder._show_countdown()
        assert overlay.value == 4
        recorder._hide_countdown_overlay()
        assert overlay.destroyed
        assert recorder._countdown_overlay is None
    finally:
        recorder.destroy()


def test_toggle_recording_starts_and_stops():
    recorder = _recorder()
    recorder._can_start = lambda: True
    calls = []

    def start():
        calls.append("start")
        recorder.process = object()  # la grabacion ya esta en marcha

    recorder._start = start
    recorder._stop = lambda: calls.append("stop")
    recorder.present = lambda: calls.append("present")
    try:
        recorder.toggle_recording()
        assert calls == ["start"]

        recorder.process = object()  # simula una grabacion activa
        recorder.toggle_recording()
        assert calls == ["start", "stop", "present"]
        recorder.process = None
    finally:
        recorder.destroy()
