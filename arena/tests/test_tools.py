"""Pruebas de las herramientas de diseno."""
import pytest
from gi.repository import Gdk, Gtk

from imagewatcher.tools import color_picker, magnifier, ruler, crosshair, protractor, whiteboard
from imagewatcher.tools.overlay import open_overlay

WINDOW_OPENERS = {
    "color_picker": color_picker.open_color_picker,
    "magnifier": magnifier.open_magnifier,
    "ruler": ruler.open_ruler,
    "crosshair": crosshair.open_crosshair,
    "protractor": protractor.open_protractor,
    "whiteboard": lambda: whiteboard.open_whiteboard(),
}

OVERLAY_MODES = ["crosshair", "ruler", "protractor", "magnifier"]


class _Escape:
    keyval = Gdk.KEY_Escape


def test_glyphs_render():
    from imagewatcher import ui

    kinds = [
        "move", "select", "lasso", "pen", "marker", "highlighter", "airbrush", "calligraphy",
        "line", "arrow", "rect", "ellipse", "callout", "text", "stamp", "cursor",
        "blur", "pixelate", "retouch", "eraser", "fill", "undo", "redo", "zoom-in",
        "zoom-out", "fit", "copy", "save", "display", "window", "region", "record",
        "more", "color", "ruler", "crosshair", "protractor", "clock", "settings",
    ]
    for kind in kinds:
        pixbuf = ui.glyph_pixbuf(kind, 22)
        assert pixbuf is not None and pixbuf.get_width() == 22
    assert ui.glyph_pixbuf("select", 22).get_has_alpha()


def test_color_formats():
    rgb = (18, 52, 86)
    assert color_picker.format_color(rgb, "hex") == "#123456"
    assert color_picker.format_color(rgb, "HTML").lower() == "#123456"
    assert color_picker.format_color(rgb, "rgb") == "rgb(18, 52, 86)"
    assert color_picker.format_color(rgb, "c++") == "RGB(18, 52, 86)"
    assert color_picker.format_color(rgb, "delphi") == "$563412"
    assert color_picker.format_color((255, 0, 0), "hsl") == "hsl(0, 100%, 50%)"
    assert color_picker.format_color((255, 0, 0), "hsv") == "hsv(0, 100%, 100%)"


def test_palette_history_uses_selected_format(pump):
    panel = color_picker.ColorPanel(color_format="rgb")
    try:
        panel._add_swatch((255, 0, 0))
        row = panel.palette.get_children()[-1].get_child()
        area = row.get_child()
        assert area.get_tooltip_text() == "rgb(255, 0, 0)"
        panel._copy_swatch((0, 255, 0))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        assert clipboard.wait_for_text() == "rgb(0, 255, 0)"
    finally:
        panel.destroy()


@pytest.mark.parametrize("name", list(WINDOW_OPENERS))
def test_tool_window_visible_not_dock_and_closes_with_escape(pump, name):
    window = WINDOW_OPENERS[name]()
    pump(200)
    assert window.get_visible()
    assert window.get_type_hint().value_nick != "dock"
    assert window._on_key(window, _Escape())
    pump(120)
    assert window not in Gtk.Window.list_toplevels()


@pytest.mark.parametrize("mode", OVERLAY_MODES)
def test_desktop_overlay_fullscreen_and_click_through(pump, mode):
    overlay = open_overlay(mode)
    pump(250)
    allocation = overlay.get_allocation()
    assert allocation.width > 0 and allocation.height > 0
    assert overlay.get_type_hint().value_nick in ("notification", "dock", "normal")
    overlay.destroy()
    pump(80)
    assert overlay not in Gtk.Window.list_toplevels()


def test_reused_interactive_overlay_keeps_receiving_clicks():
    from types import SimpleNamespace

    from imagewatcher.app import Application

    class _Overlay:
        interactive = True

        def __init__(self):
            self.calls = []

        def get_visible(self):
            return False

        def set_mode(self, mode):
            self.calls.append(("mode", mode))

        def reset(self):
            self.calls.append("reset")

        def show_all(self):
            self.calls.append("show")

        def _make_click_through(self):
            self.calls.append("click_through")

        def _make_interactive(self):
            self.calls.append("interactive")

        def _grab_focus(self):
            self.calls.append("focus")
            return False

        def start(self):
            self.calls.append("start")

    overlay = _Overlay()
    app = SimpleNamespace(
        _overlays={"crosshair": overlay}, _sync_escape_grab=lambda: None
    )
    assert Application._toggle_overlay(app, "crosshair") is overlay
    assert "reset" in overlay.calls
    assert "interactive" in overlay.calls
    assert "click_through" not in overlay.calls


def test_color_zoom_is_configurable(pump):
    loupe = color_picker.ColorLoupe(zoom=20)
    try:
        assert loupe.zoom == 20
        assert loupe.view_size == color_picker.VIEW_PIXELS * 20
    finally:
        loupe.destroy()

    panel = color_picker.ColorPanel(zoom=20)
    try:
        assert panel.zoom == 20
        assert panel.preview.get_size_request() == (
            color_picker.SAMPLE * 20,
            color_picker.SAMPLE * 20,
        )
    finally:
        panel.destroy()


def test_color_loupe_picks_from_frozen_screen(pump):
    picked = {}
    loupe = color_picker.ColorLoupe(lambda rgb, hexv: picked.update(rgb=rgb, hex=hexv))
    pump(150)
    loupe.pointer = (100, 100)
    loupe._pick()
    pump(80)
    assert "hex" in picked
    assert picked["hex"].startswith("#")


def test_ruler_measures_distance(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("ruler")
    try:
        pump(120)
        overlay.points = [(100, 100)]
        overlay.pointer = (400, 500)
        assert overlay._copy_ruler() == "500 px  (300 x 400)  13.23 cm"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        assert clipboard.wait_for_text() == "500 px  (300 x 400)  13.23 cm"
    finally:
        overlay.destroy()


def test_protractor_measures_angle(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("protractor")
    try:
        pump(120)
        overlay.points = [(100, 100), (200, 100)]
        overlay.pointer = (100, 200)
        assert overlay._protractor_angle() == 90.0
        assert overlay._copy_protractor() == "90.0 grados"
    finally:
        overlay.destroy()


def test_overlay_escape_hides(pump):
    overlay = open_overlay("ruler")
    try:
        pump(120)

        class _Escape:
            keyval = Gdk.KEY_Escape

        assert overlay._on_key(overlay.area, _Escape())
        assert not overlay.get_visible()
    finally:
        overlay.destroy()


def test_escape_grab_toggles_with_overlays(pump):
    from imagewatcher.app import Application

    app = Application()
    try:
        pump(150)
        assert app._escape_active is False
        app._toggle_overlay("ruler")
        pump(120)
        assert app._escape_active is True
        app._hide_overlays()
        pump(120)
        assert app._escape_active is False
    finally:
        app.hotkeys.stop()
        app._escape_grabber.stop()
        for widget in app._overlays.values():
            widget.destroy()


def test_recorder_closes_with_escape(pump):
    from imagewatcher.config import Config
    from imagewatcher.recorder import RecorderWindow

    window = RecorderWindow(Config())
    try:
        pump(120)

        class _Escape:
            keyval = Gdk.KEY_Escape

        assert window._on_key(window, _Escape())
        assert not window.get_visible()
    finally:
        window.destroy()


def test_color_loupe_wheel_updates_format_and_clipboard(pump):
    loupe = color_picker.ColorLoupe(color_format="hex")
    try:
        pump(120)
        loupe.stop()
        loupe.pointer = (100, 100)
        loupe._copy_live()

        class _WheelDown:
            direction = Gdk.ScrollDirection.DOWN
            delta_y = 0

        loupe._on_scroll(loupe.area, _WheelDown)
        assert loupe.color_format == "delphi"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        assert clipboard.wait_for_text() == color_picker.format_color(
            loupe._current_rgb(), "delphi"
        )
    finally:
        loupe.destroy()


def test_crosshair_exits_after_selection(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("crosshair")
    try:
        pump(120)

        class _Click:
            def __init__(self, x, y, button=1):
                self.x, self.y, self.button = x, y, button

        overlay._snap_x = []
        overlay._snap_y = []
        overlay._on_press(overlay.area, _Click(100, 100))
        assert overlay.anchor == (100, 100)
        # Un clic sin arrastre mantiene la esquina fijada.
        overlay._on_release(overlay.area, _Click(100, 100))
        assert overlay.get_visible()
        assert overlay.anchor == (100, 100)
        overlay._on_press(overlay.area, _Click(300, 250))
        assert not overlay.get_visible()
    finally:
        overlay.destroy()


def test_crosshair_drag_copies_on_release(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("crosshair")
    try:
        pump(120)

        class _Click:
            def __init__(self, x, y, button=1):
                self.x, self.y, self.button = x, y, button

        overlay._snap_x = []
        overlay._snap_y = []
        overlay._on_press(overlay.area, _Click(100, 100))
        overlay.pointer = (340, 260)
        overlay._on_release(overlay.area, _Click(340, 260))
        assert not overlay.get_visible()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        assert clipboard.wait_for_text() == "240 x 160 px"
    finally:
        overlay.destroy()


def test_crosshair_reset_clears_selection(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("crosshair")
    try:
        pump(120)
        overlay.anchor = (100, 100)
        overlay.points = [(1, 2)]
        overlay._dragging = True
        overlay.reset()
        assert overlay.anchor is None
        assert overlay.points == []
        assert overlay._dragging is False
    finally:
        overlay.destroy()


def test_crosshair_snaps_to_detected_lines(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("crosshair")
    try:
        pump(120)
        overlay._snap_x = [100, 200]
        overlay._snap_y = [150]
        assert overlay._snap((106, 144)) == (100, 150)
        assert overlay._snap((120, 170)) == (120, 170)
        assert overlay._snap_value(205, [100, 200]) == 200
        assert overlay._snap_value(250, [100, 200]) == 250
    finally:
        overlay.destroy()


def test_crosshair_copies_selection_size(pump):
    from imagewatcher.tools.overlay import DesktopOverlay

    overlay = DesktopOverlay("crosshair")
    try:
        pump(120)
        overlay.anchor = (100, 100)
        overlay.pointer = (340, 260)
        assert overlay._copy_size() == "240 x 160 px"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        assert clipboard.wait_for_text() == "240 x 160 px"
    finally:
        overlay.destroy()


def test_whiteboard_serializes_strokes():
    window = whiteboard.open_whiteboard()
    try:
        window.panel.strokes = [
            {"color": (255, 0, 0, 255), "width": 3, "points": [(0, 0), (50, 50)]}
        ]
        assert len(window.panel.strokes) == 1
    finally:
        window.destroy()
