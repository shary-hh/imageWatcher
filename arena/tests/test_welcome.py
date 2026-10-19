"""Pruebas de la pantalla de bienvenida."""
from imagewatcher import config as config_module


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")


def test_welcome_window_shows_and_remembers_choice(monkeypatch, tmp_path, pump):
    _patch_paths(monkeypatch, tmp_path)
    from imagewatcher.app import Application

    app = Application()
    try:
        window = app.show_welcome()
        pump(100)
        assert window.get_visible()
        assert window.show_on_start.get_active() is True

        window.show_on_start.set_active(False)
        window._on_start()
        pump(50)
        assert not window.get_visible()
        assert app.config.get("show_welcome") is False
        assert config_module.CONFIG_FILE.exists()
    finally:
        app.hotkeys.stop()
        app._escape_grabber.stop()
        app.bar.destroy()
