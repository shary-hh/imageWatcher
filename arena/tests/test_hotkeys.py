"""Pruebas de los atajos globales."""
import pytest

from imagewatcher.hotkeys import HotkeyManager


def test_parse_modifiers_and_key():
    manager = HotkeyManager()
    assert manager._parse("Ctrl+Alt+1") == (0x0004 | 0x0008, "1")
    assert manager._parse("Print") == (0, "print")
    assert manager._parse("Shift+Alt+P") == (0x0001 | 0x0008, "p")
    assert manager._parse("") is None


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
