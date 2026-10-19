"""Tema e helpers de interfaz compartidos (GTK3).

Centraliza el CSS de la aplicacion y utilidades para construir botones con
icono, tiles, cabeceras y tarjetas, de forma consistente en todas las ventanas.
"""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402

APP_ID = "imagewatcher"
APP_NAME = "imageWatcher"
APP_CLASS = "imageWatcher"

ACCENT = "#2f7bff"
BG = "#1b202a"
BG_ALT = "#232b38"
BG_HOVER = "#313c4e"
BORDER = "#333d4e"
TEXT = "#e9edf5"
TEXT_DIM = "#9aa5b8"

CSS = f"""
window.imagewatcher {{
    background-color: {BG};
    color: {TEXT};
}}
window.imagewatcher label {{ color: {TEXT}; }}

headerbar {{
    background-image: none;
    background-color: {BG_ALT};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
    box-shadow: none;
    min-height: 42px;
}}
headerbar .title {{ font-weight: 700; font-size: 13px; color: {TEXT}; }}
headerbar .subtitle {{ color: {TEXT_DIM}; font-size: 11px; }}
headerbar button {{
    background-image: none;
    background-color: transparent;
    border: none;
    box-shadow: none;
    color: {TEXT};
}}
headerbar button:hover {{ background-color: {BG_HOVER}; border-radius: 8px; }}

.imagewatcher-bar {{
    background-image: linear-gradient(180deg, #2c3646, #212936);
    border: 1px solid {BORDER};
    border-radius: 18px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.55);
    padding: 6px;
}}
.imagewatcher-bar button {{
    background-image: none;
    background-color: transparent;
    border: 1px solid transparent;
    box-shadow: none;
    color: {TEXT};
    padding: 4px 8px;
}}
.imagewatcher-bar button:hover {{
    background-color: {BG_HOVER};
    border: 1px solid #48566e;
    border-radius: 12px;
}}
.imagewatcher-bar button:active,
.imagewatcher-bar button:checked {{
    background-image: none;
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 12px;
    color: #ffffff;
}}
.imagewatcher-bar separator {{ background-color: #3b475d; min-width: 1px; margin: 8px 6px; }}
.tile-label {{ font-size: 11px; color: #cbd4e3; }}
.imagewatcher-bar button:active .tile-label,
.imagewatcher-bar button:checked .tile-label {{ color: #ffffff; }}
.brand {{ font-weight: 800; letter-spacing: 1px; color: #6db2ff; font-size: 14px; }}
.brand-sub {{ color: {TEXT_DIM}; font-size: 10px; }}

.toolstrip {{
    background-color: {BG_ALT};
    border-bottom: 1px solid {BORDER};
    padding: 5px;
}}
.toolstrip button {{
    background-image: none;
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px;
    color: {TEXT};
    min-width: 30px;
    min-height: 30px;
}}
.toolstrip button:hover {{ background-color: {BG_HOVER}; border-color: #48566e; }}
.toolstrip button:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    color: #ffffff;
}}
.toolstrip separator {{ background-color: {BORDER}; margin: 4px 6px; }}

.optionsbar {{
    background-color: {BG_ALT};
    border-bottom: 1px solid {BORDER};
    padding: 6px 10px;
}}
.optionsbar label {{ color: {TEXT_DIM}; }}

.card {{
    background-color: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 12px;
}}
.section-title {{ font-weight: 700; color: #cfd7e6; font-size: 12px; }}
.swatch-big {{ border-radius: 10px; border: 1px solid {BORDER}; }}
.mono {{ font-family: "DejaVu Sans Mono", monospace; }}
.format-row {{ border-radius: 8px; padding: 3px 6px; }}
.format-row:hover {{ background-color: {BG_HOVER}; }}
.dim {{ color: {TEXT_DIM}; }}
.accent {{ color: #6db2ff; }}

.pill {{
    background-color: {BG_ALT};
    border: 1px solid {BORDER};
    border-radius: 20px;
    box-shadow: 0 8px 22px rgba(0, 0, 0, 0.5);
    padding: 6px 8px;
}}
.pill button {{
    background-image: none;
    background-color: transparent;
    border: none;
    box-shadow: none;
    color: {TEXT};
    padding: 6px;
}}
.pill button:hover {{ background-color: {BG_HOVER}; border-radius: 12px; }}
.pill button:checked {{ background-color: {ACCENT}; border-radius: 12px; color: #ffffff; }}
.pill separator {{ background-color: {BORDER}; margin: 6px; }}

menu, .menu {{
    background-image: none;
    background-color: {BG_ALT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px;
}}
menu > menuitem, .menu > menuitem {{
    background-image: none;
    background-color: transparent;
    border-radius: 6px;
    padding: 4px 8px;
}}
menu menuitem, menu menuitem label, .menu menuitem {{
    color: {TEXT};
}}
menu menuitem:hover, menu menuitem:focus {{
    background-image: none;
    background-color: {ACCENT};
}}
menu menuitem:hover label, menu menuitem:focus label {{
    color: #ffffff;
}}
menu menuitem:disabled label {{
    color: {TEXT_DIM};
}}
menu separator {{
    background-color: {BORDER};
    margin: 4px 0;
}}

.imagewatcher-bar button:focus,
.toolstrip button:focus,
.pill button:focus,
headerbar button:focus {{
    box-shadow: none;
    outline-style: none;
    outline-width: 0;
}}
.imagewatcher-bar button:focus:not(:active):not(:checked) {{ background-color: transparent; }}

whiteboard > * {{ }}
"""

_provider = None


def install_theme():
    """Registra el CSS global una sola vez y pide tema oscuro de widgets."""
    global _provider
    try:
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-application-prefer-dark-theme", True)
    except Exception:
        pass
    if _provider is not None:
        return
    _provider = Gtk.CssProvider()
    try:
        _provider.load_from_data(CSS.encode("utf-8"))
    except Exception:
        return
    screen = Gdk.Screen.get_default()
    if screen is not None:
        Gtk.StyleContext.add_provider_for_screen(
            screen, _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


def has_icon(name):
    if not name:
        return False
    try:
        return Gtk.IconTheme.get_default().has_icon(name)
    except Exception:
        return False


def make_icon(name, size=18, fallback="image-x-generic"):
    chosen = name if has_icon(name) else (fallback if has_icon(fallback) else None)
    if chosen is None:
        return None
    image = Gtk.Image.new_from_icon_name(chosen, Gtk.IconSize.BUTTON)
    image.set_pixel_size(size)
    return image


def button(label=None, icon_name=None, tooltip=None, on_click=None, style=None, icon_size=16):
    widget = Gtk.Button()
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    image = make_icon(icon_name, icon_size) if icon_name else None
    if image is not None:
        box.pack_start(image, False, False, 0)
    label_widget = None
    if label:
        label_widget = Gtk.Label(label=label)
        box.pack_start(label_widget, False, False, 0)
    if image is not None or label:
        widget.add(box)
    widget._box = box
    widget._label_widget = label_widget
    widget._image = image
    if tooltip:
        widget.set_tooltip_text(tooltip)
    if style:
        widget.get_style_context().add_class(style)
    if on_click:
        widget.connect("clicked", on_click)
    return widget


def set_button_label(widget, text):
    """Cambia el texto de un boton creado con button() de forma fiable."""
    label_widget = getattr(widget, "_label_widget", None)
    if label_widget is not None:
        label_widget.set_text(text)
    else:
        widget.set_label(text)


def tile(icon_name, label, tooltip=None, on_click=None):
    widget = Gtk.Button()
    widget.get_style_context().add_class("tile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    image = make_icon(icon_name, 22)
    if image is not None:
        box.pack_start(image, False, False, 0)
    caption = Gtk.Label(label=label)
    caption.get_style_context().add_class("tile-label")
    box.pack_start(caption, False, False, 0)
    widget.add(box)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    if on_click:
        widget.connect("clicked", on_click)
    return widget


def toggle_icon(icon_name, tooltip=None, group=None, icon_size=18):
    widget = Gtk.RadioButton()
    if group is not None:
        widget.join_group(group)
    image = make_icon(icon_name, icon_size)
    if image is not None:
        widget.add(image)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


# --------------------------------------------------------------------- glyphs
# Iconos monocromos dibujados con Cairo: consistentes con cualquier tema.
GLYPH_COLOR = (0.87, 0.90, 0.96)


def glyph_pixbuf(kind, size=22, color=GLYPH_COLOR, line=1.9):
    import cairo

    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(surface)
    cr.scale(size / 24.0, size / 24.0)
    cr.set_source_rgb(*color)
    cr.set_line_width(line)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    try:
        _draw_glyph(cr, kind, color)
    except Exception:
        pass
    return Gdk.pixbuf_get_from_surface(surface, 0, 0, size, size)


def _draw_glyph(cr, kind, color):
    import cairo

    def line(x1, y1, x2, y2):
        cr.move_to(x1, y1)
        cr.line_to(x2, y2)
        cr.stroke()

    def rect(x, y, w, h):
        cr.rectangle(x, y, w, h)
        cr.stroke()

    def circle(cx, cy, r, fill=False):
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.fill() if fill else cr.stroke()

    if kind == "select":
        cr.set_dash([2.5, 2.5])
        rect(3.5, 5.5, 17, 13)
        cr.set_dash([])
    elif kind == "lasso":
        cr.move_to(8, 6)
        cr.curve_to(19, 3, 21, 13, 14, 16)
        cr.curve_to(7, 19, 3, 12, 8, 9)
        cr.stroke()
        line(11, 17, 9, 21)
    elif kind == "pen":
        line(8, 16, 17, 7)
        cr.move_to(5, 19)
        cr.line_to(8, 16)
        cr.line_to(6.5, 20.5)
        cr.close_path()
        cr.stroke()
        line(15.5, 5.5, 18.5, 8.5)
    elif kind == "marker":
        cr.set_line_width(5.5)
        line(7, 17, 16, 8)
        cr.set_line_width(1.9)
    elif kind == "highlighter":
        cr.set_source_rgba(color[0], color[1], color[2], 0.5)
        cr.set_line_width(7)
        line(6, 18, 18, 6)
        cr.set_line_width(1.9)
    elif kind == "airbrush":
        circle(12, 12, 6)
        for dot in ((9, 10), (14, 9), (10, 14), (15, 13), (12, 12)):
            circle(dot[0], dot[1], 0.9, fill=True)
    elif kind == "calligraphy":
        cr.move_to(6, 15)
        cr.line_to(15, 6)
        cr.line_to(19, 10)
        cr.line_to(10, 19)
        cr.close_path()
        cr.stroke()
    elif kind == "line":
        line(5, 19, 19, 5)
    elif kind == "arrow":
        line(5, 19, 18, 6)
        cr.move_to(18, 6)
        cr.line_to(12.5, 7)
        cr.move_to(18, 6)
        cr.line_to(17, 11.5)
        cr.stroke()
    elif kind == "rect":
        rect(4.5, 6.5, 15, 11)
    elif kind == "ellipse":
        cr.save()
        cr.translate(12, 12)
        cr.scale(7, 5.5)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()
    elif kind == "callout":
        cr.move_to(8, 4.5)
        cr.line_to(16, 4.5)
        cr.arc(16, 9, 4.5, -math.pi / 2, math.pi / 2)
        cr.line_to(9, 13.5)
        cr.line_to(6, 19)
        cr.line_to(8, 13.5)
        cr.arc(8, 9, 4.5, math.pi / 2, 1.5 * math.pi)
        cr.close_path()
        cr.stroke()
    elif kind == "text":
        line(6, 6, 18, 6)
        line(12, 6, 12, 18)
        line(9, 18, 15, 18)
    elif kind == "stamp":
        circle(12, 12, 8)
        circle(12, 12, 2, fill=True)
    elif kind == "cursor":
        cr.move_to(8, 3)
        cr.line_to(8, 18)
        cr.line_to(12, 14)
        cr.line_to(15, 20)
        cr.line_to(17.5, 19)
        cr.line_to(14.5, 13)
        cr.line_to(19, 13)
        cr.close_path()
        cr.stroke()
    elif kind == "blur":
        cr.set_dash([2, 2.2])
        circle(12, 12, 8)
        cr.set_dash([])
        circle(12, 12, 3, fill=True)
    elif kind == "pixelate":
        rect(4.5, 4.5, 6, 6)
        rect(13.5, 4.5, 6, 6)
        rect(4.5, 13.5, 6, 6)
        cr.rectangle(13.5, 13.5, 6, 6)
        cr.fill()
    elif kind == "retouch":
        cr.move_to(12, 4)
        cr.curve_to(5, 12, 6, 19, 12, 19)
        cr.curve_to(18, 19, 19, 12, 12, 4)
        cr.close_path()
        cr.stroke()
    elif kind == "eraser":
        cr.move_to(4, 14)
        cr.line_to(12, 6)
        cr.line_to(20, 14)
        cr.line_to(16, 18)
        cr.line_to(8, 18)
        cr.close_path()
        cr.stroke()
        line(7, 11, 15, 11)
    elif kind == "fill":
        cr.move_to(6, 11)
        cr.line_to(12, 5)
        cr.line_to(20, 13)
        cr.line_to(14, 19)
        cr.close_path()
        cr.stroke()
        circle(4.5, 18, 2.2)
    elif kind == "undo":
        cr.arc(12, 13, 7, math.radians(200), math.radians(340))
        cr.stroke()
        line(5, 8, 5, 14)
        line(5, 14, 11, 14)
    elif kind == "redo":
        cr.save()
        cr.translate(24, 0)
        cr.scale(-1, 1)
        cr.arc(12, 13, 7, math.radians(200), math.radians(340))
        cr.stroke()
        line(5, 8, 5, 14)
        line(5, 14, 11, 14)
        cr.restore()
    elif kind == "zoom-in":
        circle(10.5, 10.5, 6.5)
        line(15.5, 15.5, 20.5, 20.5)
        line(7.5, 10.5, 13.5, 10.5)
        line(10.5, 7.5, 10.5, 13.5)
    elif kind == "zoom-out":
        circle(10.5, 10.5, 6.5)
        line(15.5, 15.5, 20.5, 20.5)
        line(7.5, 10.5, 13.5, 10.5)
    elif kind == "fit":
        line(4, 9, 4, 4); line(4, 4, 9, 4)
        line(15, 4, 20, 4); line(20, 4, 20, 9)
        line(20, 15, 20, 20); line(20, 20, 15, 20)
        line(9, 20, 4, 20); line(4, 20, 4, 15)
    elif kind == "copy":
        rect(8.5, 3.5, 12, 12)
        rect(3.5, 8.5, 12, 12)
    elif kind == "save":
        cr.rectangle(5.5, 4.5, 13, 15)
        cr.stroke()
        line(9, 4.5, 9, 9); line(9, 9, 15, 9); line(15, 9, 15, 4.5)
        line(8.5, 15.5, 15.5, 15.5)
    elif kind == "display":
        rect(3.5, 5.5, 17, 12)
        line(9, 20, 15, 20)
        line(12, 17.5, 12, 20)
    elif kind == "window":
        rect(3.5, 4.5, 17, 15)
        line(3.5, 8.5, 20.5, 8.5)
        circle(6.5, 6.5, 0.8, fill=True)
        circle(9, 6.5, 0.8, fill=True)
    elif kind == "region":
        cr.set_dash([2.5, 2.5])
        rect(4, 6, 16, 12)
        cr.set_dash([])
        for cx, cy in ((4, 6), (20, 6), (4, 18), (20, 18)):
            circle(cx, cy, 1.1, fill=True)
    elif kind == "record":
        circle(12, 12, 7, fill=True)
    elif kind == "more":
        for cy in (6, 12, 18):
            circle(12, cy, 1.4, fill=True)
    elif kind == "color":
        cr.move_to(12, 4)
        cr.curve_to(5, 12, 6, 19, 12, 19)
        cr.curve_to(18, 19, 19, 12, 12, 4)
        cr.close_path()
        cr.stroke()
        circle(12, 14, 2.4, fill=True)
    elif kind == "ruler":
        cr.save()
        cr.translate(12, 12)
        cr.rotate(-math.pi / 4)
        cr.rectangle(-8, -3, 16, 6)
        cr.stroke()
        for x in (-5, -2, 1, 4):
            cr.move_to(x, -3)
            cr.line_to(x, -0.5)
        cr.restore()
        cr.stroke()
    elif kind == "crosshair":
        circle(12, 12, 5)
        line(12, 2, 12, 7)
        line(12, 17, 12, 22)
        line(2, 12, 7, 12)
        line(17, 12, 22, 12)
    elif kind == "protractor":
        cr.arc(12, 15, 8, math.pi, 2 * math.pi)
        cr.stroke()
        line(4, 15, 20, 15)
        line(12, 15, 18.5, 10)
        circle(12, 15, 1.2, fill=True)
    elif kind == "clock":
        circle(12, 12, 8)
        line(12, 12, 12, 7)
        line(12, 12, 16, 14)
    elif kind == "settings":
        circle(12, 12, 3.4)
        for i in range(8):
            angle = i * math.pi / 4
            cr.move_to(12 + 5.2 * math.cos(angle), 12 + 5.2 * math.sin(angle))
            cr.line_to(12 + 8 * math.cos(angle), 12 + 8 * math.sin(angle))
        cr.stroke()


def glyph_image(kind, size=20, color=GLYPH_COLOR):
    pixbuf = glyph_pixbuf(kind, size, color)
    return Gtk.Image.new_from_pixbuf(pixbuf) if pixbuf is not None else None


def glyph_toggle(kind, tooltip=None, group=None, size=20):
    widget = Gtk.RadioButton()
    if group is not None:
        widget.join_group(group)
    image = glyph_image(kind, size)
    if image is not None:
        widget.add(image)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    return widget


def glyph_button(kind, tooltip=None, on_click=None, size=18):
    widget = Gtk.Button()
    image = glyph_image(kind, size)
    if image is not None:
        widget.add(image)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    if on_click:
        widget.connect("clicked", on_click)
    return widget


def glyph_tile(kind, label, tooltip=None, on_click=None, size=22):
    widget = Gtk.Button()
    widget.get_style_context().add_class("tile")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    image = glyph_image(kind, size)
    if image is not None:
        box.pack_start(image, False, False, 0)
    caption = Gtk.Label(label=label)
    caption.get_style_context().add_class("tile-label")
    box.pack_start(caption, False, False, 0)
    widget.add(box)
    if tooltip:
        widget.set_tooltip_text(tooltip)
    if on_click:
        widget.connect("clicked", on_click)
    return widget


def menu_item(label, kind=None, callback=None):
    item = Gtk.MenuItem()
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    if kind:
        image = glyph_image(kind, 16)
        if image is not None:
            row.pack_start(image, False, False, 0)
    row.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
    item.add(row)
    if callback:
        item.connect("activate", callback)
    return item


def header(title, subtitle=None, icon_name=None):
    bar = Gtk.HeaderBar()
    bar.set_show_close_button(True)
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
    image = make_icon(icon_name, 22) if icon_name else None
    if image is not None:
        box.pack_start(image, False, False, 0)
    titles = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    titles.set_valign(Gtk.Align.CENTER)
    title_label = Gtk.Label(label=title, xalign=0)
    title_label.get_style_context().add_class("title")
    titles.pack_start(title_label, False, False, 0)
    subtitle_label = None
    if subtitle:
        subtitle_label = Gtk.Label(label=subtitle, xalign=0)
        subtitle_label.get_style_context().add_class("subtitle")
        titles.pack_start(subtitle_label, False, False, 0)
    box.pack_start(titles, False, False, 0)
    bar.set_custom_title(box)
    bar.title_label = title_label
    bar.subtitle_label = subtitle_label
    return bar


def apply_dark(window):
    window.get_style_context().add_class("imagewatcher")


def set_app_identity():
    """Mejora la integracion con el escritorio (WM_CLASS e icono)."""
    try:
        from gi.repository import GLib

        GLib.set_prgname(APP_ID)
        GLib.set_application_name(APP_NAME)
    except Exception:
        pass
    try:
        Gdk.set_program_class(APP_CLASS)
    except Exception:
        pass

    if has_icon(APP_ID):
        Gtk.Window.set_default_icon_name(APP_ID)
        return
    try:
        from pathlib import Path

        asset = Path(__file__).resolve().parent.parent / "packaging" / "assets" / "imagewatcher.svg"
        if asset.exists():
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(asset), 256, 256)
            Gtk.Window.set_default_icon(pixbuf)
            return
    except Exception:
        pass
    Gtk.Window.set_default_icon_name("accessories-screenshot")

