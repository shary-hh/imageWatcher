"""Selector de color tipo cuentagotas con lupa + panel de paleta.

La lupa (ColorLoupe) es un overlay transitorio que sigue al cursor. El panel
(ColorPanel) se puede embeber en la ventana de herramientas.
"""
import colorsys
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from .. import ui  # noqa: E402
from ..capture import capture_region, capture_screen  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402

SAMPLE = 15
ZOOM = 14
FORMATS = ["HEX", "RGB", "HSL", "HSV", "HTML", "C++", "Delphi"]

VIEW_PIXELS = 13
VIEW_SCALE = 11
VIEW_SIZE = VIEW_PIXELS * VIEW_SCALE


def format_color(rgb, fmt):
    """Formatea un color RGB en el formato pedido (hex/rgb/hsl/hsv/...)."""
    r, g, b = rgb
    fmt = fmt.lower()
    if fmt in ("hex", "html"):
        return f"#{r:02X}{g:02X}{b:02X}"
    if fmt == "rgb":
        return f"rgb({r}, {g}, {b})"
    if fmt == "hsl":
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        return f"hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)"
    if fmt in ("hsv", "hsb"):
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        return f"hsv({round(h * 360)}, {round(s * 100)}%, {round(v * 100)}%)"
    if fmt == "c++":
        return f"RGB({r}, {g}, {b})"
    if fmt == "delphi":
        return f"${b:02X}{g:02X}{r:02X}"
    return f"#{r:02X}{g:02X}{b:02X}"


def _contrast(rgb):
    r, g, b = rgb
    return (0, 0, 0) if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else (255, 255, 255)


def _hex_to_rgb(value):
    try:
        value = value.lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return None


def _rounded_rect(cr, x, y, w, h, radius):
    cr.new_sub_path()
    cr.arc(x + w - radius, y + radius, radius, -math.pi / 2, 0)
    cr.arc(x + w - radius, y + h - radius, radius, 0, math.pi / 2)
    cr.arc(x + radius, y + h - radius, radius, math.pi / 2, math.pi)
    cr.arc(x + radius, y + radius, radius, math.pi, 1.5 * math.pi)
    cr.close_path()


def _enable_transparency(window):
    screen = window.get_screen()
    visual = screen.get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)
    window.set_app_paintable(True)


class ColorLoupe(Gtk.Window):
    """Cuentagotas a pantalla completa con lupa junto al cursor."""

    FORMAT_ORDER = ["hex", "rgb", "hsl", "hsv", "html", "c++", "delphi"]

    def __init__(self, on_pick=None, on_cancel=None, base=None, color_format="hex", history=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        ui.install_theme()
        self.on_pick = on_pick
        self.on_cancel = on_cancel
        self.history = list(history or [])[:10]
        self.formats = list(self.FORMAT_ORDER)
        fmt = str(color_format).lower()
        self.format_index = self.formats.index(fmt) if fmt in self.formats else 0
        self.color_format = self.formats[self.format_index]
        self.base = base if base is not None else capture_screen()
        self.pointer = get_pointer_position()
        self._timer = None

        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(True)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        _enable_transparency(self)

        width, height = self.base.width, self.base.height
        self.set_default_size(width, height)
        self.move(0, 0)
        self.resize(width, height)

        self.area = Gtk.DrawingArea()
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
            | Gdk.EventMask.SCROLL_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("motion-notify-event", self._on_motion)
        self.area.connect("scroll-event", self._on_scroll)
        self.add(self.area)
        self.connect("key-press-event", self._on_key)
        self.connect("map", lambda *_: self.start())
        self.connect("unmap", lambda *_: self.stop())
        self.connect("destroy", lambda *_: self.stop())

        self.show_all()
        self.present()
        GLib.timeout_add(40, self._grab)
        self.start()

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(40, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _grab(self):
        try:
            window = self.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair"))
                self.grab_focus()
        except Exception:
            pass
        return False

    def _tick(self):
        try:
            self.pointer = get_pointer_position()
            self.area.queue_draw()
        except Exception:
            pass
        return self._timer is not None

    def _on_motion(self, _widget, event):
        self.pointer = (int(event.x), int(event.y))
        self.area.queue_draw()
        return True

    def _current_rgb(self):
        x, y = self.pointer
        x = max(0, min(self.base.width - 1, x))
        y = max(0, min(self.base.height - 1, y))
        return self.base.getpixel((x, y))[:3]

    def _copy_live(self):
        """Copia el color actual en el formato vigente (sin cerrar la lupa)."""
        value = format_color(self._current_rgb(), self.color_format)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        clipboard.store()
        return value

    def _on_scroll(self, _widget, event):
        """Rueda arriba/abajo: cambia el formato y actualiza el color copiado."""
        if event.direction == Gdk.ScrollDirection.UP:
            self.format_index = (self.format_index + 1) % len(self.formats)
        elif event.direction == Gdk.ScrollDirection.DOWN:
            self.format_index = (self.format_index - 1) % len(self.formats)
        elif event.direction == Gdk.ScrollDirection.SMOOTH:
            if event.delta_y < 0:
                self.format_index = (self.format_index + 1) % len(self.formats)
            elif event.delta_y > 0:
                self.format_index = (self.format_index - 1) % len(self.formats)
            else:
                return False
        else:
            return False
        self.color_format = self.formats[self.format_index]
        self._copy_live()
        self.area.queue_draw()
        return True

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._cancel()
            return True
        return False

    def _on_press(self, _widget, event):
        if event.button == 1:
            self._pick()
        else:
            self._cancel()
        return True

    def _cancel(self):
        if self.on_cancel:
            self.on_cancel()
        self.destroy()

    def _pick(self):
        x, y = self.pointer
        x = max(0, min(self.base.width - 1, x))
        y = max(0, min(self.base.height - 1, y))
        rgb = self.base.getpixel((x, y))[:3]
        value = format_color(rgb, self.color_format)
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        clipboard.store()
        if self.on_pick:
            self.on_pick(rgb, value)
        self.destroy()

    def _sample(self, x, y):
        x = max(0, min(self.base.width - 1, x))
        y = max(0, min(self.base.height - 1, y))
        return self.base.getpixel((x, y))[:3]

    def _on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        px, py = self.pointer
        rgb = self._sample(px, py)

        cr.set_source_rgba(0.11, 0.65, 0.98, 0.55)
        cr.set_line_width(1)
        cr.move_to(0, py + 0.5)
        cr.line_to(self.base.width, py + 0.5)
        cr.move_to(px + 0.5, 0)
        cr.line_to(px + 0.5, self.base.height)
        cr.stroke()

        self._draw_loupe(cr, px, py, rgb)

        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(13)
        hint = "Clic: copiar color     Rueda: cambiar formato     Esc: cancelar"
        extents = cr.text_extents(hint)
        hx = (self.base.width - extents.width) / 2
        cr.set_source_rgba(0, 0, 0, 0.6)
        _rounded_rect(cr, hx - 12, 14, extents.width + 24, extents.height + 16, 8)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(hx, 14 + extents.height + 2)
        cr.show_text(hint)
        return False

    def _draw_loupe(self, cr, px, py, rgb):
        half = VIEW_PIXELS // 2
        pad = 8
        bar_h = 46
        hist_h = 24 if self.history else 0
        box_w = VIEW_SIZE + pad * 2
        box_h = VIEW_SIZE + pad * 2 + bar_h + hist_h

        bx = px + 22
        by = py + 22
        if bx + box_w > self.base.width:
            bx = px - 22 - box_w
        if by + box_h > self.base.height:
            by = py - 22 - box_h
        bx = max(4, bx)
        by = max(4, by)

        cr.set_source_rgba(0, 0, 0, 0.35)
        _rounded_rect(cr, bx + 3, by + 3, box_w, box_h, 12)
        cr.fill()
        cr.set_source_rgba(0.11, 0.13, 0.17, 0.97)
        _rounded_rect(cr, bx, by, box_w, box_h, 12)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.14)
        cr.set_line_width(1)
        _rounded_rect(cr, bx + 0.5, by + 0.5, box_w - 1, box_h - 1, 12)
        cr.stroke()

        origin_x = bx + pad
        origin_y = by + pad
        for j in range(-half, half + 1):
            for i in range(-half, half + 1):
                r, g, b = self._sample(px + i, py + j)
                cr.set_source_rgb(r / 255, g / 255, b / 255)
                cr.rectangle(
                    origin_x + (i + half) * VIEW_SCALE,
                    origin_y + (j + half) * VIEW_SCALE,
                    VIEW_SCALE,
                    VIEW_SCALE,
                )
                cr.fill()

        cx = origin_x + half * VIEW_SCALE
        cy = origin_y + half * VIEW_SCALE
        cr.set_source_rgba(0, 0, 0, 0.8)
        cr.set_line_width(3)
        cr.rectangle(cx - 1.5, cy - 1.5, VIEW_SCALE + 3, VIEW_SCALE + 3)
        cr.stroke()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(1.5)
        cr.rectangle(cx, cy, VIEW_SCALE, VIEW_SCALE)
        cr.stroke()

        bar_y = origin_y + VIEW_SIZE + pad
        r, g, b = rgb
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        _rounded_rect(cr, origin_x, bar_y, VIEW_SIZE, bar_h, 8)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.18)
        _rounded_rect(cr, origin_x + 0.5, bar_y + 0.5, VIEW_SIZE - 1, bar_h - 1, 8)
        cr.stroke()

        text_color = _contrast(rgb)
        cr.set_source_rgb(text_color[0] / 255, text_color[1] / 255, text_color[2] / 255)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(17)
        cr.move_to(origin_x + 10, bar_y + 21)
        cr.show_text(format_color(rgb, self.color_format))
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(11)
        cr.move_to(origin_x + 10, bar_y + 37)
        cr.show_text(f"{self.color_format.upper()}   RGB {r}, {g}, {b}")

        if self.history:
            self._draw_history(cr, origin_x, bar_y + bar_h + 4)

    def _draw_history(self, cr, x, y):
        size = 18
        gap = 4
        for stale in self.history:
            rgb = _hex_to_rgb(stale)
            if rgb is None:
                continue
            cr.set_source_rgb(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255)
            cr.rectangle(x, y, size, size)
            cr.fill()
            cr.set_source_rgba(1, 1, 1, 0.25)
            cr.set_line_width(1)
            cr.rectangle(x + 0.5, y + 0.5, size - 1, size - 1)
            cr.stroke()
            x += size + gap
            if x + size > self.base.width:
                break


class ColorPanel(Gtk.Box):
    """Panel de paleta/formatos embebible."""

    def __init__(self, on_pick=None, color_format="hex"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        ui.apply_dark(self)
        self.on_pick = on_pick
        self.color_format = str(color_format).lower()
        self.current = (0, 0, 0)
        self.history = []
        self._frozen = False
        self._sample_image = None
        self._loupe = None
        self._timer = None
        self._last_pos = None

        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        self.pack_start(self._build_preview(), False, False, 0)
        self.pack_start(self._build_swatch(), False, False, 0)
        self.pack_start(self._section("Formatos (clic para copiar)"), False, False, 0)
        self.pack_start(self._build_formats(), False, False, 0)
        self.pack_start(self._section("Paleta de muestras"), False, False, 0)

        self.palette = Gtk.FlowBox()
        self.palette.set_max_children_per_line(10)
        self.palette.set_selection_mode(Gtk.SelectionMode.NONE)
        self.palette.set_row_spacing(4)
        self.palette.set_column_spacing(4)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(90)
        scroll.add(self.palette)
        self.pack_start(scroll, True, True, 0)

        self.pack_start(self._build_buttons(), False, False, 0)

    def start(self):
        if self._timer is None:
            self._timer = GLib.timeout_add(80, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def _section(self, text):
        label = Gtk.Label(label=text, xalign=0)
        label.get_style_context().add_class("section-title")
        return label

    def _build_preview(self):
        frame = Gtk.Frame()
        frame.get_style_context().add_class("card")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        self.preview = Gtk.DrawingArea()
        self.preview.set_size_request(SAMPLE * ZOOM, SAMPLE * ZOOM)
        self.preview.connect("draw", self._draw_preview)
        self.preview.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.preview.connect("button-press-event", lambda *_: (self._launch_loupe(), True)[1])
        frame.add(self.preview)
        return frame

    def _build_swatch(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.swatch = Gtk.DrawingArea()
        self.swatch.set_size_request(96, 96)
        self.swatch.get_style_context().add_class("swatch-big")
        self.swatch.connect("draw", self._draw_swatch)
        box.pack_start(self.swatch, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_valign(Gtk.Align.CENTER)
        self.hex_label = Gtk.Label(label="#000000", xalign=0)
        self.hex_label.set_markup("<span size='xx-large' weight='bold'>#000000</span>")
        self.rgb_label = Gtk.Label(label="rgb(0, 0, 0)", xalign=0)
        self.rgb_label.get_style_context().add_class("dim")
        texts.pack_start(self.hex_label, False, False, 0)
        texts.pack_start(self.rgb_label, False, False, 0)
        box.pack_start(texts, True, True, 0)
        return box

    def _build_formats(self):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("card")
        self.formats = {}
        for fmt in FORMATS:
            row = Gtk.EventBox()
            row.get_style_context().add_class("format-row")
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            name = Gtk.Label(label=fmt, xalign=0)
            name.set_size_request(64, -1)
            name.get_style_context().add_class("dim")
            value = Gtk.Label(label="-", xalign=0)
            value.get_style_context().add_class("mono")
            line.pack_start(name, False, False, 0)
            line.pack_start(value, True, True, 0)
            row.add(line)
            row.connect("button-press-event", self._on_format_clicked, fmt)
            card.pack_start(row, False, False, 0)
            self.formats[fmt] = value
        return card

    def _build_buttons(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.capture_button = ui.button(
            label="Cuentagotas", icon_name="color-select",
            tooltip="Elegir un color en la pantalla con la lupa",
            style="suggested-action", on_click=self._launch_loupe)
        box.pack_start(self.capture_button, True, True, 0)
        self.freeze_button = ui.button(
            label="Congelar", icon_name="media-playback-pause",
            tooltip="Congelar el muestreo del cursor", on_click=self._on_freeze)
        box.pack_start(self.freeze_button, True, True, 0)
        box.pack_start(ui.button(label="HSV", icon_name="applications-graphics",
                                 tooltip="Selector tipo Photoshop (RGB/HSV/hex)",
                                 on_click=self._open_hsv), True, True, 0)
        return box

    def _open_hsv(self, *_):
        dialog = Gtk.ColorChooserDialog(
            title="Selector de color", transient_for=self.get_toplevel()
        )
        dialog.set_use_alpha(False)
        r, g, b = self.current
        rgba = Gdk.RGBA(r / 255, g / 255, b / 255, 1.0)
        dialog.set_rgba(rgba)
        if dialog.run() == Gtk.ResponseType.OK:
            chosen = dialog.get_rgba()
            self.current = (
                int(chosen.red * 255), int(chosen.green * 255), int(chosen.blue * 255)
            )
            self.history.append(self.current)
            self._add_swatch(self.current)
            self._frozen = True
            ui.set_button_label(self.freeze_button, "Reanudar")
            self._refresh()
            if self.on_pick:
                self.on_pick(self.current)
        dialog.destroy()

    def _tick(self):
        if self._frozen:
            return True
        try:
            position = get_pointer_position()
            if position == self._last_pos:
                return True
            self._last_pos = position
            x, y = position
            half = SAMPLE // 2
            image = Image.new("RGBA", (SAMPLE, SAMPLE), (60, 60, 60, 255))
            region = capture_region(x - half, y - half, SAMPLE, SAMPLE)
            image.paste(region, (0, 0))
            if region.width > half and region.height > half:
                self.current = region.getpixel((half, half))[:3]
            self._sample_image = image
            self._refresh()
        except Exception:
            pass
        return True

    def _refresh(self):
        self.preview.queue_draw()
        self.swatch.queue_draw()
        r, g, b = self.current
        self.hex_label.set_markup(f"<span size='xx-large' weight='bold'>#{r:02X}{g:02X}{b:02X}</span>")
        self.rgb_label.set_text(f"rgb({r}, {g}, {b})")
        for fmt, label in self.formats.items():
            label.set_text(format_color(self.current, fmt))

    def _draw_preview(self, _widget, cr):
        image = self._sample_image
        if image is None:
            return False
        big = image.resize((SAMPLE * ZOOM, SAMPLE * ZOOM), Image.NEAREST)
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            big.tobytes(), GdkPixbuf.Colorspace.RGB, True, 8,
            big.width, big.height, big.width * 4,
        ).copy()
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        center = SAMPLE * ZOOM / 2
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.set_line_width(1)
        cr.rectangle(center - ZOOM / 2, center - ZOOM / 2, ZOOM, ZOOM)
        cr.stroke()
        cr.set_source_rgba(0, 0, 0, 0.8)
        cr.rectangle(center - ZOOM / 2 - 1, center - ZOOM / 2 - 1, ZOOM + 2, ZOOM + 2)
        cr.stroke()
        return False

    def _draw_swatch(self, widget, cr):
        r, g, b = self.current
        alloc = widget.get_allocation()
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        cr.rectangle(0, 0, alloc.width, alloc.height)
        cr.fill()
        return False

    def _launch_loupe(self, *_):
        base = capture_screen()
        self._loupe = ColorLoupe(self._on_loupe_pick, on_cancel=self._on_loupe_done, base=base)

    def _on_loupe_done(self):
        pass

    def _on_loupe_pick(self, rgb, hex_value):
        self.current = rgb
        self.history.append(rgb)
        self._add_swatch(rgb)
        self._frozen = True
        ui.set_button_label(self.freeze_button, "Reanudar")
        self._refresh()
        if self.on_pick:
            self.on_pick(rgb)

    def _on_freeze(self, *_):
        self._frozen = not self._frozen
        ui.set_button_label(self.freeze_button, "Reanudar" if self._frozen else "Congelar")
        return False

    def _on_format_clicked(self, _widget, _event, fmt):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(format_color(self.current, fmt), -1)
        clipboard.store()
        return True

    def _add_swatch(self, rgb):
        area = Gtk.DrawingArea()
        area.set_size_request(28, 28)
        area._color = rgb
        area.connect("draw", self._draw_swatch_item)
        area.set_tooltip_text(format_color(rgb, self.color_format))
        row = Gtk.EventBox()
        row.add(area)
        row.connect("button-press-event", lambda *_: self._copy_swatch(rgb))
        self.palette.add(row)
        self.palette.show_all()

    def _copy_swatch(self, rgb):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(format_color(rgb, self.color_format), -1)
        clipboard.store()

    def _draw_swatch_item(self, widget, cr):
        r, g, b = widget._color
        alloc = widget.get_allocation()
        size = min(alloc.width, alloc.height)
        cr.set_source_rgb(r / 255, g / 255, b / 255)
        cr.rectangle(1, 1, size - 2, size - 2)
        cr.fill()
        cr.set_source_rgba(0, 0, 0, 0.4)
        cr.rectangle(0.5, 0.5, size - 1, size - 1)
        cr.stroke()
        return False


class ColorPickerWindow(Gtk.Window):
    """Ventana de paleta independiente (opcional)."""

    def __init__(self, on_pick=None, color_format="hex"):
        super().__init__(title="Paleta de colores")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(360, 720)
        self.set_keep_above(True)
        self.set_titlebar(ui.header("Paleta de colores", "Cuentagotas y formatos", "color-select"))
        self.panel = ColorPanel(on_pick, color_format=color_format)
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


def open_color_picker(on_pick=None, color_format="hex", history=None):
    """Cuentagotas con lupa (overlay transitorio)."""
    def report(rgb, value):
        if on_pick:
            on_pick(rgb)
        try:
            import subprocess
            from shutil import which

            notifier = which("notify-send")
            if notifier:
                subprocess.Popen([notifier, "Color copiado", value])
        except Exception:
            pass

    return ColorLoupe(
        report, base=capture_screen(), color_format=color_format, history=history
    )


def open_palette(on_pick=None, color_format="hex"):
    return ColorPickerWindow(on_pick, color_format=color_format)
