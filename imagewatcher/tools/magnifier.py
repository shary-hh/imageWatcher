"""Lupa: amplia la zona de pantalla bajo el cursor (panel embebible)."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from .. import ui  # noqa: E402
from ..capture import capture_region  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402


class MagnifierPanel(Gtk.Box):
    def __init__(self, zoom=6, sample=40):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        ui.apply_dark(self)
        self.zoom = zoom
        self.sample = sample
        self._image = None
        self._timer = None
        self._last_pos = None

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls.get_style_context().add_class("optionsbar")
        controls.pack_start(Gtk.Label(label="Zoom"), False, False, 0)
        zoom_adj = Gtk.Adjustment(value=zoom, lower=2, upper=20, step_increment=1)
        zoom_spin = Gtk.SpinButton(adjustment=zoom_adj)
        zoom_spin.connect("value-changed", self._on_zoom)
        controls.pack_start(zoom_spin, False, False, 0)
        self.coords = Gtk.Label(label="")
        self.coords.get_style_context().add_class("mono")
        controls.pack_end(self.coords, False, False, 0)
        self.pack_start(controls, False, False, 0)

        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._on_draw)
        frame = Gtk.Frame()
        frame.get_style_context().add_class("card")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        frame.add(self.area)
        self.pack_start(frame, True, True, 0)

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(80, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _on_zoom(self, spin):
        self.zoom = int(spin.get_value())

    def _tick(self):
        try:
            x, y = get_pointer_position()
            if (x, y) == self._last_pos:
                return True
            self._last_pos = (x, y)
            half = self.sample // 2
            image = Image.new("RGBA", (self.sample, self.sample), (30, 30, 30, 255))
            region = capture_region(x - half, y - half, self.sample, self.sample)
            image.paste(region, (0, 0))
            self._image = image
            self.coords.set_text(f"x={x}  y={y}")
            self.area.queue_draw()
        except Exception:
            pass
        return True

    def _on_draw(self, _widget, cr):
        image = self._image
        alloc = self.area.get_allocation()
        cr.set_source_rgb(0.12, 0.13, 0.15)
        cr.paint()
        if image is None or alloc.width < 2:
            return False
        factor = min(alloc.width / self.sample, alloc.height / self.sample)
        big = image.resize(
            (int(self.sample * factor), int(self.sample * factor)), Image.NEAREST
        )
        big = big.convert("RGBA")
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            big.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
            big.width, big.height, big.width * 4,
        ).copy()
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()

        cell = factor
        cr.set_source_rgba(0, 0, 0, 0.22)
        for i in range(self.sample + 1):
            cr.rectangle(i * cell, 0, 1, big.height)
            cr.rectangle(0, i * cell, big.width, 1)
        cr.fill()
        cr.set_source_rgba(1, 0.2, 0.2, 0.95)
        cr.set_line_width(1)
        cr.rectangle(
            big.width / 2 - cell / 2, big.height / 2 - cell / 2, cell, cell
        )
        cr.stroke()
        return False


class MagnifierWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Lupa")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(360, 420)
        self.set_keep_above(True)
        self.set_titlebar(ui.header("Lupa", "Amplia la zona bajo el cursor", "zoom-in"))
        self.panel = MagnifierPanel()
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


def open_magnifier():
    return MagnifierWindow()
