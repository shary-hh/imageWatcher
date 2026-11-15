"""Pruebas de la capa de compatibilidad con Wayland."""
from PIL import Image

from imagewatcher import capture, session
from imagewatcher.hotkeys import HotkeyManager


def test_session_detection(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    assert session.is_wayland() is True
    assert capture.is_wayland() is True
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    assert session.is_wayland() is False


def test_portal_trigger_format():
    manager = HotkeyManager()
    assert manager._portal_trigger("Ctrl+Alt+1") == "CTRL+ALT+1"
    assert manager._portal_trigger("Shift+Alt+P") == "SHIFT+ALT+P"
    assert manager._portal_trigger("Super+Print") == "LOGO+Print"
    assert manager._portal_trigger("Escape") == "Escape"


def test_wayland_capture_uses_portal(tmp_path, monkeypatch):
    path = tmp_path / "shot.png"
    Image.new("RGBA", (80, 60), (10, 20, 30, 255)).save(path)

    monkeypatch.setattr(session, "is_wayland", lambda: True)
    monkeypatch.setattr(capture, "is_wayland", lambda: True)
    monkeypatch.setattr(
        session, "portal_screenshot", lambda interactive=False, timeout=30: str(path)
    )
    image = capture.capture_screen()
    assert image.size == (80, 60)
    assert image.mode == "RGBA"


def test_wayland_monitor_crop_uses_scale(monkeypatch):
    monkeypatch.setattr(capture, "_monitor_bounds", lambda: (0, 0, 960, 540))
    image = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
    cropped = capture._crop_logical_box(image, (480, 270, 480, 270))
    assert cropped.size == (960, 540)
    assert capture.image_to_logical_box((480, 270, 960, 540), image) == (
        240,
        135,
        480,
        270,
    )


def test_recorder_backend_wayland(monkeypatch):
    from imagewatcher import recorder

    monkeypatch.setattr(recorder.capture, "is_wayland", lambda: True)
    monkeypatch.setattr(recorder.session, "is_gnome", lambda: False)
    monkeypatch.setattr(recorder.session, "is_kde", lambda: False)
    monkeypatch.setattr(
        recorder.shutil, "which", lambda name: "/usr/bin/wf-recorder" if name == "wf-recorder" else None
    )
    assert recorder._detect_backend() == "wf-recorder"


def test_region_preview_translates_to_source(pump):
    from imagewatcher.region import RegionSelector

    source = Image.new("RGBA", (800, 600), (1, 2, 3, 255))
    selector = RegionSelector(
        source,
        lambda image: None,
        fixed_size=(200, 100),
        preview_size=(400, 300),
        snap_enabled=False,
    )
    pump(100)
    try:
        assert selector.base.size == (400, 300)
        assert selector.fixed_size == (100, 50)
        assert selector.rect_to_source((150, 125, 100, 50)) == (300, 250, 200, 100)
        assert selector.points_to_source([(10, 20), (30, 40)]) == [(20, 40), (60, 80)]
    finally:
        selector.destroy()
