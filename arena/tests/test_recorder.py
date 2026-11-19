"""Pruebas del grabador de pantalla."""
import subprocess
from pathlib import Path

import pytest
from gi.repository import GLib
from PIL import Image

from imagewatcher import capture
from imagewatcher.recorder import RecorderWindow, video_to_gif


class _Config:
    def __init__(self):
        self.data = {
            "record_fps": 25,
            "record_audio": False,
            "record_countdown": 3,
            "record_format": "mp4",
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


def test_gif_format_records_temp_video_and_disables_audio(monkeypatch):
    from imagewatcher import recorder as recorder_module

    if capture.is_wayland():
        pytest.skip("la prueba usa la captura x11")
    monkeypatch.setattr(recorder_module, "has_encoder", lambda _name: True)

    recorder = _recorder()
    recorder.region = Image.new("RGBA", (720, 153))
    recorder.region_offset = (10, 20)
    recorder._set_area_mode("region")
    recorder.audio_check.set_active(True)
    try:
        recorder.format_combo.set_active_id("gif")
        assert recorder._is_gif()
        assert not recorder.audio_check.get_sensitive()
        assert "15" in recorder.fps_spin.get_tooltip_text()

        cmd = recorder._build_command()
        assert cmd is not None
        assert recorder.output_path.endswith(".gif")
        assert recorder._temp_path.endswith(".mp4")
        assert cmd[-1] == recorder._temp_path
        assert "pulse" not in cmd
        # Las regiones impares no pueden codificarse como yuv420p.
        assert "crop=trunc(iw/2)*2:trunc(ih/2)*2" in cmd

        recorder.format_combo.set_active_id("mp4")
        assert not recorder._is_gif()
        cmd = recorder._build_command()
        assert cmd is not None
        assert recorder.output_path.endswith(".mp4")
        assert recorder._temp_path is None
        assert "15" not in (recorder.fps_spin.get_tooltip_text() or "")
    finally:
        recorder.destroy()


def test_recording_failure_is_reported_from_ffmpeg_stderr():
    import io

    recorder = _recorder()
    recorder.process = type("_Proc", (), {"poll": lambda self: 1})()
    recorder._stderr_file = io.BytesIO(
        b"[libx264] height not divisible by 2 (720x153)\nConversion failed!\n"
    )
    try:
        assert recorder._tick() is False
        assert "height not divisible" in recorder.status.get_text()
        assert recorder.process is None
    finally:
        recorder._close_stderr()
        recorder.destroy()


def test_video_to_gif_rejects_empty_input(tmp_path):
    empty = tmp_path / "vacio.mp4"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeError, match="vacio"):
        video_to_gif(str(empty), str(tmp_path / "salida.gif"))


def test_start_with_region_uses_the_editable_overlay():
    recorder = _recorder()
    recorder._can_start = lambda: True
    recorder.region = Image.new("RGBA", (200, 100))
    recorder._set_area_mode("region")
    recorder.countdown_spin.set_value(4)
    calls = []
    recorder._begin_region_countdown = lambda seconds: calls.append(("region", seconds))
    recorder._begin_countdown = lambda seconds: calls.append(("count", seconds))
    recorder._start_recording = lambda: calls.append(("record",))
    try:
        recorder._start()
        assert calls == [("region", 4)]
    finally:
        recorder.destroy()


def test_area_combo_opens_the_picker_only_when_needed():
    recorder = _recorder()
    calls = []
    recorder._pick_region = lambda *_: calls.append("pick")
    try:
        recorder.area_combo.set_active_id("region")
        assert calls == ["pick"]

        calls.clear()
        recorder.region = Image.new("RGBA", (200, 100))
        recorder._update_area_ui()
        recorder.area_combo.set_active_id("fullscreen")
        recorder.area_combo.set_active_id("region")
        assert calls == []
    finally:
        recorder.destroy()


def test_area_mode_switches_between_fullscreen_and_region(monkeypatch):
    from types import SimpleNamespace

    from imagewatcher import recorder as recorder_module

    if capture.is_wayland():
        pytest.skip("la prueba usa la captura x11")
    monkeypatch.setattr(recorder_module, "has_encoder", lambda _name: True)
    monkeypatch.setattr(
        recorder_module.capture,
        "monitor_geometries",
        lambda: [SimpleNamespace(x=0, y=0, width=800, height=600)],
    )

    recorder = _recorder()
    recorder.region = Image.new("RGBA", (320, 200))
    recorder.region_offset = (40, 50)
    try:
        recorder._set_area_mode("fullscreen")
        cmd = recorder._build_command()
        assert cmd[cmd.index("-video_size") + 1] == "800x600"
        assert cmd[cmd.index("-i") + 1].endswith("+0,0")

        recorder._set_area_mode("region")
        recorder._update_area_ui()
        cmd = recorder._build_command()
        assert cmd[cmd.index("-video_size") + 1] == "320x200"
        assert cmd[cmd.index("-i") + 1].endswith("+40,50")
        assert recorder.pick_button.get_label() == "Ajustar 320x200"

        recorder._set_area_mode("fullscreen")
        recorder._update_area_ui()
        assert recorder.pick_button.get_label() == "Elegir region..."
    finally:
        recorder.destroy()


def test_initial_region_rect_uses_current_selection():
    recorder = _recorder()
    base = Image.new("RGBA", (800, 600))
    try:
        assert recorder._initial_region_rect(base) is None
        recorder.region = Image.new("RGBA", (320, 200))
        recorder.region_offset = (40, 50)
        assert recorder._initial_region_rect(base) == (40, 50, 320, 200)
    finally:
        recorder.destroy()


def test_region_selection_updates_the_pick_button(monkeypatch):
    from imagewatcher import recorder as recorder_module
    from imagewatcher import region as region_module

    if capture.is_wayland():
        pytest.skip("la prueba usa la captura x11")

    recorder = _recorder()
    captured = {}

    class _Selector:
        def __init__(self, base, on_done, on_cancel=None, detect_windows=True,
                     initial_rect=None, **_kwargs):
            captured["done"] = on_done
            captured["initial"] = initial_rect

        def _finish_accept(self, rect):
            captured["rect"] = rect

    monkeypatch.setattr(region_module, "RegionSelector", _Selector)
    monkeypatch.setattr(
        recorder_module.capture,
        "capture_screen",
        lambda: Image.new("RGBA", (800, 600)),
    )
    try:
        recorder._pick_region()
        assert captured["initial"] is None
        captured["done"](Image.new("RGBA", (200, 100)))
        assert recorder.pick_button.get_label() == "Ajustar 200x100"
        assert recorder.region.size == (200, 100)
        assert recorder.area_combo.get_active_id() == "region"

        recorder._pick_region()
        assert captured["initial"] == (0, 0, 200, 100)
    finally:
        recorder.destroy()


def test_video_to_gif_generates_animated_gif(tmp_path):
    from imagewatcher.recorder import ffmpeg_path

    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        pytest.skip("ffmpeg no esta instalado")
    video = tmp_path / "entrada.mp4"
    result = subprocess.run(
        [
            ffmpeg, "-y", "-f", "lavfi", "-i",
            "testsrc=size=64x48:rate=10:duration=1",
            "-c:v", "mpeg4", str(video),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        pytest.skip(f"no se pudo crear el video de prueba: {result.stderr[-200:]}")
    gif = tmp_path / "salida.gif"
    video_to_gif(str(video), str(gif), fps=10)
    assert gif.exists()
    assert gif.stat().st_size > 0
    assert gif.read_bytes()[:6] in (b"GIF89a", b"GIF87a")
