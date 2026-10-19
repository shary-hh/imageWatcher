"""Pruebas de los atajos globales."""
import pytest

from imagewatcher.actions import HOTKEY_ACTIONS, HOTKEY_DEFAULTS
from imagewatcher.hotkeys import HotkeyManager


def test_actions_registry_is_complete():
    names = [action for action, _label, _group, _default in HOTKEY_ACTIONS]
    assert len(names) >= 20
    assert len(names) == len(set(names))
    assert set(names) == set(HOTKEY_DEFAULTS)
    for action in (
        "fullscreen", "window", "region", "fixed", "freehand", "scrolling",
        "delayed", "monitor", "repeat", "editor", "recorder", "color",
        "magnifier", "ruler", "crosshair", "protractor", "whiteboard",
        "hide_overlays", "preferences", "welcome", "show_bar", "hide_bar", "quit",
    ):
        assert action in HOTKEY_DEFAULTS


def test_parse_modifiers_and_key():
    manager = HotkeyManager()
    assert manager._parse("Ctrl+Alt+1") == (0x0004 | 0x0008, "1")
    assert manager._parse("Print") == (0, "print")
    assert manager._parse("Shift+Alt+P") == (0x0001 | 0x0008, "p")
    assert manager._parse("") is None


def test_preferences_lists_every_hotkey_action(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from gi.repository import Gtk

    from imagewatcher import app as app_module
    from imagewatcher import config as config_module
    from imagewatcher.config import Config

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(
        app_module.Gtk.Dialog, "run", lambda self: Gtk.ResponseType.CANCEL
    )

    dialog = app_module.PreferencesDialog(SimpleNamespace(config=Config(), bar=None))
    expected = {action for action, _label, _group, _default in HOTKEY_ACTIONS}
    assert set(dialog.hotkey_entries) == expected
    assert dialog.show_bar_check.get_active() is True
    assert dialog.snap_check.get_active() is True
    assert dialog.color_zoom_spin.get_value() == 11
    assert dialog.favorite_checks["color"].get_active() is True
    assert dialog.favorite_checks["magnifier"].get_active() is True
    assert dialog.favorite_checks["protractor"].get_active() is False


def test_grab_and_release():
    manager = HotkeyManager()
    manager.set_callbacks({"fullscreen": lambda: None})
    manager.start(
        {
            "fullscreen": "Ctrl+Alt+1",
            "region": "Ctrl+Alt+2",
            "window": "Ctrl+Alt+3",
            "repeat": "Ctrl+Alt+4",
        }
    )
    manager.stop()
    assert isinstance(manager.failures, list)


def test_reports_conflict_without_crashing():
    first = HotkeyManager()
    first.start({"fullscreen": "Ctrl+Alt+8"})
    second = HotkeyManager()
    second.start({"fullscreen": "Ctrl+Alt+8"})
    try:
        # La segunda instancia no debe reventar; puede reportar conflicto.
        assert isinstance(second.failures, list)
    finally:
        first.stop()
        second.stop()
