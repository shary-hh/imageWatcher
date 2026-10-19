"""Regla de pixeles: mide distancias en pantalla (panel embebible)."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from .. import ui  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402


class RulerPanel(Gtk.Box):
    def __init__(self, dpi=96):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        ui.apply_dark(self)
        self.dpi = dpi
        self.orientation = "h"
        self.origin = None
        self._timer = None
        self._last_pos = None

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.get_style_context().add_class("optionsbar")
        self.h_btn = Gtk.RadioButton(label="Horizontal")
        self.v_btn = Gtk.RadioButton(label="Vertical")
        self.v_btn.join_group(self.h_btn)
        self.h_btn.connect("toggled", self._on_orientation, "h")
        self.v_btn.connect("toggled", self._on_orientation, "v")
        controls.pack_start(self.h_btn, False, False, 0)
        controls.pack_start(self.v_btn, False, False, 0)
        controls.pack_start(Gtk.Label(label="DPI"), False, False, 8)
        dpi_adj = Gtk.Adjustment(value=dpi, lower=50, upper=400, step_increment=1)
        dpi_spin = Gtk.SpinButton(adjustment=dpi_adj)
        dpi_spin.connect("value-changed", self._on_dpi)
        controls.pack_start(dpi_spin, False, False, 0)
        origin_btn = ui.button(label="Fijar origen", icon_name="mark-location",
                               on_click=self._set_origin)
        controls.pack_start(origin_btn, False, False, 0)
        self.pack_start(controls, False, False, 0)

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._on_draw)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("card")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.add(self.area)
        self.pack_start(frame, True, True, 0)

        self.readout = Gtk.Label(label="Fija un origen para medir")
        self.readout.set_xalign(0)
        self.readout.get_style_context().add_class("mono")
        self.pack_start(self.readout, False, False, 0)

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(60, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _on_orientation(self, button, value):
        if button.get_active():
            self.orientation = value
            self.area.queue_draw()

    def _on_dpi(self, spin):
        self.dpi = int(spin.get_value())
        self.area.queue_draw()

    def _set_origin(self, *_):
        self.origin = get_pointer_position()
        self.readout.set_text(f"Origen fijado en {self.origin}")

    def _tick(self):
        try:
            if not self.origin:
                return True
            position = get_pointer_position()
            if position == self._last_pos:
                return True
            self._last_pos = position
            x, y = position
            dx = x - self.origin[0]
            dy = y - self.origin[1]
            dist = (dx * dx + dy * dy) ** 0.5
            cm = dist / self.dpi * 2.54
            inch = dist / self.dpi
            self.readout.set_text(
                f"dx={dx} px  dy={dy} px  -  distancia={dist:.0f} px  ({cm:.2f} cm / {inch:.2f} in)"
            )
        except Exception:
            pass
        return True

    def _on_draw(self, _widget, cr):
        alloc = self.area.get_allocation()
        length = alloc.width if self.orientation == "h" else alloc.height
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.set_source_rgb(0.1, 0.1, 0.1)
        cr.set_line_width(1)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(10)
        for value in range(0, length + 1, 5):
            tick = 18 if value % 50 == 0 else (10 if value % 10 == 0 else 5)
            if self.orientation == "h":
                cr.move_to(value + 0.5, 0)
                cr.line_to(value + 0.5, tick)
                if value % 50 == 0:
                    cr.move_to(value + 2, tick + 10)
                    cr.show_text(str(value))
            else:
                cr.move_to(0, value + 0.5)
                cr.line_to(tick, value + 0.5)
                if value % 50 == 0:
                    cr.save()
                    cr.move_to(tick + 10, value + 10)
                    cr.rotate(-1.5708)
                    cr.show_text(str(value))
                    cr.restore()
        cr.stroke()
        return False


class RulerWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Regla de pixeles")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(760, 220)
        self.set_keep_above(True)
        self.set_titlebar(ui.header("Regla de pixeles", "Mide en px, cm y pulgadas", "applications-science"))
        self.panel = RulerPanel()
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


def open_ruler():
    return RulerWindow()
