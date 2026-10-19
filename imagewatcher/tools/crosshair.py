"""Punto de mira: coordenadas del puntero (panel embebible)."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import ui  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402


class CrosshairPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        ui.apply_dark(self)
        self.pointer = get_pointer_position()
        self.frozen = None
        self._timer = None
        self._last_pos = None

        self.area = Gtk.DrawingArea()
        self.area.set_size_request(-1, 130)
        self.area.connect("draw", self._on_draw)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("card")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.add(self.area)
        self.pack_start(frame, True, True, 0)

        self.readout = Gtk.Label(label="X = -   Y = -")
        self.readout.set_markup("<span size='x-large'>X = -   Y = -</span>")
        self.pack_start(self.readout, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        freeze = ui.button(label="Congelar / seguir", icon_name="media-playback-pause",
                           on_click=self._toggle_freeze)
        buttons.pack_start(freeze, True, True, 0)
        copy = ui.button(label="Copiar coords", icon_name="edit-copy", on_click=self._copy)
        buttons.pack_start(copy, True, True, 0)
        self.pack_start(buttons, False, False, 0)

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(50, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _toggle_freeze(self, *_):
        self.frozen = None if self.frozen else self.pointer

    def _copy(self, *_):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(f"{self.pointer[0]}, {self.pointer[1]}", -1)
        clipboard.store()

    def _tick(self):
        try:
            if self.frozen is not None:
                return True
            position = get_pointer_position()
            if position == self._last_pos:
                return True
            self._last_pos = position
            self.pointer = position
            self.readout.set_markup(
                f"<span size='x-large'>X = {self.pointer[0]}   Y = {self.pointer[1]}</span>"
            )
            self.area.queue_draw()
        except Exception:
            pass
        return True

    def _on_draw(self, _widget, cr):
        alloc = self.area.get_allocation()
        width, height = alloc.width, alloc.height
        cr.set_source_rgb(0.12, 0.13, 0.15)
        cr.rectangle(0, 0, width, height)
        cr.fill()
        cx, cy = width / 2, height / 2
        cr.set_source_rgba(0.11, 0.65, 0.98, 0.9)
        cr.set_line_width(1)
        cr.move_to(0, cy + 0.5)
        cr.line_to(width, cy + 0.5)
        cr.move_to(cx + 0.5, 0)
        cr.line_to(cx + 0.5, height)
        cr.stroke()
        cr.set_source_rgb(1, 0.25, 0.25)
        cr.set_line_width(1.5)
        cr.arc(cx, cy, 22, 0, 6.2832)
        cr.stroke()
        cr.move_to(cx - 30, cy)
        cr.line_to(cx - 6, cy)
        cr.move_to(cx + 6, cy)
        cr.line_to(cx + 30, cy)
        cr.move_to(cx, cy - 30)
        cr.line_to(cx, cy - 6)
        cr.move_to(cx, cy + 6)
        cr.line_to(cx, cy + 30)
        cr.stroke()
        cr.arc(cx, cy, 2, 0, 6.2832)
        cr.fill()
        return False


class CrosshairWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Punto de mira")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(380, 260)
        self.set_keep_above(True)
        self.set_titlebar(ui.header("Punto de mira", "Coordenadas del puntero", "mark-location"))
        self.panel = CrosshairPanel()
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


def open_crosshair():
    return CrosshairWindow()
