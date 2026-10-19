"""Transportador: mide angulos en pantalla (panel embebible)."""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import ui  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402


class ProtractorPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ui.apply_dark(self)
        self.pointer = get_pointer_position()
        self._timer = None
        self._last_pos = None

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._on_draw)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("card")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.add(self.area)
        self.pack_start(frame, True, True, 0)

        self.readout = Gtk.Label()
        self.readout.set_markup("<span size='x-large'>0.0 grados</span>")
        self.pack_start(self.readout, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        copy = ui.button(label="Copiar angulo", icon_name="edit-copy", on_click=self._copy)
        buttons.pack_start(copy, True, True, 0)
        self.pack_start(buttons, False, False, 0)

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(60, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _origin(self):
        try:
            window = self.area.get_window()
            if window is not None:
                coords = window.get_root_coords(0, 0)
                if isinstance(coords, tuple) and len(coords) == 2:
                    return coords
        except Exception:
            pass
        try:
            return self.get_toplevel().get_position()
        except Exception:
            return (0, 0)

    def _angle(self):
        ox, oy = self._origin()
        alloc = self.area.get_allocation()
        cx = ox + alloc.width / 2
        cy = oy + alloc.height / 2
        px, py = self.pointer
        return math.degrees(math.atan2(cy - py, px - cx)) % 360

    def _tick(self):
        try:
            position = get_pointer_position()
            if position == self._last_pos:
                return True
            self._last_pos = position
            self.pointer = position
            self.readout.set_markup(f"<span size='x-large'>{self._angle():.1f} grados</span>")
            self.area.queue_draw()
        except Exception:
            pass
        return True

    def _copy(self, *_):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(f"{self._angle():.1f}", -1)
        clipboard.store()

    def _on_draw(self, _widget, cr):
        alloc = self.area.get_allocation()
        width, height = alloc.width, alloc.height
        radius = max(30, min(width, height) / 2 - 24)
        cx, cy = width / 2, height / 2
        cr.set_source_rgb(0.12, 0.13, 0.15)
        cr.paint()
        cr.set_source_rgba(0.9, 0.9, 0.95, 0.9)
        cr.set_line_width(1.5)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(11)
        for degree in range(0, 360, 5):
            a = math.radians(degree)
            inner = radius - (14 if degree % 10 == 0 else 7)
            cr.move_to(cx + inner * math.cos(a), cy - inner * math.sin(a))
            cr.line_to(cx + radius * math.cos(a), cy - radius * math.sin(a))
            if degree % 30 == 0:
                cr.move_to(cx + (radius - 28) * math.cos(a) - 8, cy - (radius - 28) * math.sin(a) + 4)
                cr.show_text(str(degree))
        cr.stroke()
        angle = self._angle()
        cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
        cr.set_line_width(2)
        cr.move_to(cx, cy)
        cr.line_to(cx + radius * math.cos(math.radians(angle)), cy - radius * math.sin(math.radians(angle)))
        cr.stroke()
        cr.arc(cx, cy, 4, 0, 2 * math.pi)
        cr.fill()
        return False


class ProtractorWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Transportador")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(460, 560)
        self.set_keep_above(True)
        self.set_titlebar(ui.header("Transportador", "Mide angulos en pantalla", "accessories-character-map"))
        self.panel = ProtractorPanel()
        self.add(self.panel)
        self.connect("key-press-event", self._on_key)
        self.connect("destroy", lambda *_: self.panel.stop())
        self.show_all()
        self.present()
        self.panel.start()

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False


def open_protractor():
    return ProtractorWindow()
