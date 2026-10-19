"""Pruebas de la configuracion persistente."""
from imagewatcher import config as config_module


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")


def test_defaults_and_persistence(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    cfg = config_module.Config()
    assert cfg.get("save_format") == "png"
    assert cfg.get("copy_to_clipboard") is True
    assert cfg.get("show_capture_bar") is True

    cfg["save_format"] = "jpg"
    cfg["delay_seconds"] = 7
    cfg.save()
    assert config_module.CONFIG_FILE.exists()

    reloaded = config_module.Config()
    assert reloaded.get("save_format") == "jpg"
    assert reloaded.get("delay_seconds") == 7


def test_capture_bar_visibility_preference():
    from types import SimpleNamespace

    from imagewatcher.app import Application

    calls = []
    app = SimpleNamespace(
        config={"show_capture_bar": False},
        bar=SimpleNamespace(
            show_all=lambda: calls.append("show"),
            present=lambda: calls.append("present"),
            hide=lambda: calls.append("hide"),
        ),
    )
    Application._set_bar_visible(app, True)
    assert calls == []
    Application._set_bar_visible(app, True, force=True)
    assert calls == ["show", "present"]
    Application._set_bar_visible(app, False)
    assert calls[-1] == "hide"


def test_hotkey_defaults(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    hotkeys = config_module.Config().get("hotkeys")
    assert "fullscreen" in hotkeys
    assert "region" in hotkeys
    for action in ("scrolling", "delayed", "editor", "recorder", "color", "quit"):
        assert action in hotkeys
        assert isinstance(hotkeys[action], str)
    assert hotkeys["fullscreen"] == "Ctrl+Alt+1"


def test_partial_file_is_merged_with_defaults(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    config_module.CONFIG_FILE.write_text('{"save_format": "bmp"}', encoding="utf-8")
    cfg = config_module.Config()
    assert cfg.get("save_format") == "bmp"
    assert cfg.get("jpeg_quality") == 90


def test_ensure_save_dir(monkeypatch, tmp_path):
    _patch_paths(monkeypatch, tmp_path)
    cfg = config_module.Config()
    cfg["save_dir"] = str(tmp_path / "capturas")
    directory = cfg.ensure_save_dir()
    assert directory.exists()


def test_color_history_accumulates(monkeypatch, tmp_path, pump):
    _patch_paths(monkeypatch, tmp_path)
    from imagewatcher.app import Application

    app = Application()
    try:
        app._remember_color((255, 0, 0))
        app._remember_color((0, 255, 0))
        app._remember_color((255, 0, 0))  # repetido -> vuelve al frente
        history = app.config.get("color_history")
        assert history[0] == "#FF0000"
        assert "#00FF00" in history
        assert history.count("#FF0000") == 1
        assert len(history) <= 16
        menu = app._color_history_menu()
        assert menu.get_submenu() is not None
        swatch = app._swatch_pixbuf("#FF0000")
        assert swatch.get_pixels()[0:3] == bytes([255, 0, 0])
        app._clear_color_history()
        assert app.config.get("color_history") == []
    finally:
        app.hotkeys.stop()
        app._escape_grabber.stop()
        for widget in list(app._overlays.values()):
            widget.destroy()
