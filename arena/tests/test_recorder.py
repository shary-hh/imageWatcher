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
    return RecorderWindow(_Config())


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
