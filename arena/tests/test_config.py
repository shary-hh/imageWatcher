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
    assert cfg.get("snap_enabled") is True
    assert cfg.get("color_zoom") == 11
    assert cfg.get("favorite_tools") == [
        "color", "magnifier", "ruler", "whiteboard",
    ]

    cfg["save_format"] = "jpg"
    cfg["delay_seconds"] = 7
    cfg.save()
    assert config_module.CONFIG_FILE.exists()

    reloaded = config_module.Config()
    assert reloaded.get("save_format") == "jpg"
    assert reloaded.get("delay_seconds") == 7


def test_capture_bar_shows_favorite_tools(pump):
    from imagewatcher.app import CaptureBar

    class _App:
        def favorite_tool_ids(self):
            return ["color", "ruler"]

        def open_favorite(self, tool_id):
            pass

        def do_capture(self, mode):
            pass

        def open_tool(self, name):
            pass

        def _design_tools_menu(self):
            from gi.repository import Gtk

            return Gtk.MenuItem(label="tools")

        def _capture_menu(self, include_primary=True):
            from gi.repository import Gtk

            return Gtk.MenuItem(label="capture")

        def _favorites_menu(self):
            from gi.repository import Gtk

            return Gtk.MenuItem(label="favorites")

    bar = CaptureBar(_App())
    try:
        pump(120)
        assert bar.favorites_box.get_visible()
        assert len(bar.favorites_box.get_children()) == 2
    finally:
        bar.destroy()


def test_capture_menu_groups_capture_modes():
    from types import SimpleNamespace

    from gi.repository import Gtk

    from imagewatcher.app import Application

    app = SimpleNamespace(do_capture=lambda mode: None)

    def labels(item):
        result = []
        for child in item.get_submenu().get_children():
            box = child.get_child()
            if isinstance(box, Gtk.Box):
                for widget in box.get_children():
                    if isinstance(widget, Gtk.Label):
                        result.append(widget.get_text())
        return result

    full = labels(Application._capture_menu(app))
    assert "Pantalla completa" in full
    assert "Region" in full
    assert "Ventana con desplazamiento" in full
    assert "Monitor principal" in full

    secondary = labels(Application._capture_menu(app, include_primary=False))
    assert "Pantalla completa" not in secondary
    assert "Region fija" in secondary
    assert "Captura freehand" in secondary


def test_favorite_tools_are_filtered_and_dispatched():
    from types import SimpleNamespace

    from imagewatcher.app import Application

    app = SimpleNamespace(
        config={"favorite_tools": ["color", "unknown", "color", "protractor"]}
    )
    assert Application.favorite_tool_ids(app) == ["color", "protractor"]

    calls = []
    app.open_tool = lambda name: calls.append(("tool", name))
    app.open_editor_blank = lambda: calls.append(("editor",))
    Application.open_favorite(app, "color")
    Application.open_favorite(app, "editor")
    Application.open_favorite(app, "unknown")
    assert calls == [("tool", "color"), ("editor",)]


def test_color_history_uses_selected_format():
    from types import SimpleNamespace

    from imagewatcher.app import Application

    app = SimpleNamespace(config={"color_format": "rgb"})
    assert Application._format_color_value(app, "#FF0000") == "rgb(255, 0, 0)"
    app.config["color_format"] = "hex"
    assert Application._format_color_value(app, "#00FF00") == "#00FF00"


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
