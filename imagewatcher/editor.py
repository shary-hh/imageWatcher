"""Editor de imagenes con anotaciones y efectos (estilo PicPick)."""
import math
import os
import random
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402
from PIL import (  # noqa: E402
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFilter,
    ImageFont,
    ImageOps,
)

from . import __version__, capture, share, ui  # noqa: E402
from .gtk_util import pil_to_pixbuf  # noqa: E402

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
]
FONT_CANDIDATES_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def load_font(size, bold=False):
    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except Exception:
        return ImageFont.load_default()


def channel_balance(image, red=0, green=0, blue=0):
    """Balance de color: ganancia por canal (-100..100) con Pillow."""
    r, g, b, a = image.split()

    def adjust(channel, gain):
        offset = int(gain * 2.55)
        return channel.point(lambda value: max(0, min(255, value + offset)))

    return Image.merge("RGBA", (adjust(r, red), adjust(g, green), adjust(b, blue), a))


def add_drop_shadow(image, offset=14, blur=12, opacity=60):
    """Sombra paralela: copia difuminada de la silueta (Pillow)."""
    alpha = image.getchannel("A")
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda value: int(value * opacity / 100)))
    shadow = shadow.filter(ImageFilter.GaussianBlur(max(0, blur)))
    canvas = Image.new("RGBA", (image.width + offset * 2, image.height + offset * 2), (0, 0, 0, 0))
    canvas.alpha_composite(shadow, (offset, offset))
    canvas.alpha_composite(image, (0, 0))
    return canvas


TOOLS = [
    ("select", "Seleccion"),
    ("lasso", "Seleccion libre"),
    ("pen", "Lapiz"),
    ("marker", "Rotulador"),
    ("highlighter", "Resaltador"),
    ("airbrush", "Aerografo"),
    ("calligraphy", "Caligrafia"),
    ("line", "Linea"),
    ("arrow", "Flecha"),
    ("rect", "Rectangulo"),
    ("ellipse", "Elipse"),
    ("callout", "Globo"),
    ("text", "Texto"),
    ("stamp", "Numero"),
    ("cursor", "Cursor"),
    ("blur", "Desenfoque"),
    ("pixelate", "Mosaico"),
    ("retouch", "Retoque"),
    ("eraser", "Borrador"),
    ("fill", "Relleno"),
]

TOOL_ICONS = {
    "select": ("edit-select-all", "Seleccionar region para recortar"),
    "lasso": ("edit-select", "Seleccion a mano alzada"),
    "pen": ("draw-freehand", "Lapiz"),
    "marker": ("draw-path", "Rotulador"),
    "highlighter": ("format-text-underline", "Resaltador"),
    "airbrush": ("weather-fog", "Aerografo"),
    "calligraphy": ("format-text-bold", "Caligrafia"),
    "line": ("draw-line", "Linea"),
    "arrow": ("go-next", "Flecha"),
    "rect": ("draw-rectangle", "Rectangulo"),
    "ellipse": ("draw-ellipse", "Elipse"),
    "callout": ("dialog-information", "Globo de texto"),
    "text": ("insert-text", "Texto"),
    "stamp": ("emblem-important", "Sello numerado"),
    "cursor": ("input-mouse", "Sello de cursor"),
    "blur": ("weather-fog", "Desenfoque por region"),
    "pixelate": ("view-grid", "Mosaico / pixelado"),
    "retouch": ("applications-graphics", "Retoque (desenfoque de pincel)"),
    "eraser": ("edit-clear", "Borrador"),
    "fill": ("fill-color", "Relleno (bote de pintura)"),
}


class EditorWindow(Gtk.Window):
    def __init__(self, image, config, capture_callback=None):
        super().__init__(title="imageWatcher - Editor")
        self.config = config
        self.capture_callback = capture_callback
        self.set_default_size(1024, 720)

        self.image = image.convert("RGBA")
        self.original = self.image.copy()
        self.current_path = None
        self.modified = False
        self.undo_stack = []
        self.redo_stack = []
        self._pixbuf = None

        self.tool = "pen"
        self.stroke_color = (230, 30, 30, 255)
        self.stroke_width = 3
        self.font_size = 22
        self.fill_shapes = False
        self._fill_color = None
        self.stamp_number = 1
        self._pending_crop = None
        self._pending_lasso = None

        self.scale = 1.0
        self._auto_fit = True
        self.offset = [0.0, 0.0]
        self.drag = None
        self.panning = None

        self._build_ui()
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", self._on_delete)
        self._refresh_pixbuf()
        self._status("Listo")
        self.show_all()

    # ================================================================== UI
    def _build_ui(self):
        ui.install_theme()
        ui.apply_dark(self)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        self.set_titlebar(self._build_header())
        root.pack_start(self._build_toolstrip(), False, False, 0)
        root.pack_start(self._build_optionsbar(), False, False, 0)

        self.canvas = Gtk.DrawingArea()
        self.canvas.set_size_request(200, 150)
        self.canvas.set_can_focus(True)
        self.canvas.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.SCROLL_MASK
            | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        self.canvas.connect("draw", self._on_draw)
        self.canvas.connect("button-press-event", self._on_press)
        self.canvas.connect("button-release-event", self._on_release)
        self.canvas.connect("motion-notify-event", self._on_motion)
        self.canvas.connect("scroll-event", self._on_scroll)
        self.canvas.connect("size-allocate", self._on_size_allocate)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.canvas)
        root.pack_start(scroller, True, True, 0)

        self.statusbar = Gtk.Statusbar()
        self._status_context = self.statusbar.get_context_id("editor")
        root.pack_start(self.statusbar, False, False, 0)

    def _build_header(self):
        bar = ui.header("Editor de imagenes", "Anota, recorta y da estilo")
        self._header = bar

        menu_button = Gtk.MenuButton()
        menu_icon = ui.make_icon("open-menu-symbolic", 18)
        menu_button.add(menu_icon if menu_icon is not None else Gtk.Label(label="Menu"))
        menu_button.set_tooltip_text("Menu")
        menu_button.set_popup(self._build_menu())
        bar.pack_start(menu_button)

        for kind, tooltip, callback in [
            ("undo", "Deshacer (Ctrl+Z)", lambda *_: self._undo()),
            ("redo", "Rehacer (Ctrl+Y)", lambda *_: self._redo()),
            ("zoom-out", "Alejar", lambda *_: self._zoom(0.8)),
            ("zoom-in", "Acercar", lambda *_: self._zoom(1.25)),
            ("fit", "Ajustar a ventana (Ctrl+0)", lambda *_: self._fit_to_window()),
        ]:
            bar.pack_start(ui.glyph_button(kind, tooltip, callback))

        for kind, tooltip, callback in [
            ("copy", "Copiar al portapapeles (Ctrl+C)", lambda *_: self._copy_clipboard()),
            ("save", "Guardar (Ctrl+S)", lambda *_: self._save_file()),
        ]:
            bar.pack_end(ui.glyph_button(kind, tooltip, callback))
        return bar

    def _build_menu(self):
        menu = Gtk.Menu()
        items = [
            ("Archivo", [
                ("_Abrir...", self._open_file),
                ("_Guardar", self._save_file),
                ("Guardar _como...", self._save_file_as),
                ("sep", None),
                ("_Copiar al portapapeles", self._copy_clipboard),
                ("_Imprimir...", self._print_image),
                ("Abrir con _programa externo", self._open_external),
                ("Compartir por _URL...", self._share_url),
                ("Crear _nueva captura", self._new_capture),
                ("sep", None),
                ("_Cerrar", lambda *_: self.close()),
            ]),
            ("Editar", [
                ("_Deshacer", self._undo),
                ("_Rehacer", self._redo),
                ("sep", None),
                ("_Recortar a seleccion", self._crop_to_selection),
                ("_Redimensionar...", self._resize_dialog),
                ("sep", None),
                ("_Invertir colores", self._invert_selection_placeholder),
            ]),
            ("Ver", [
                ("Acercar", lambda *_: self._zoom(1.25)),
                ("Alejar", lambda *_: self._zoom(0.8)),
                ("100%", lambda *_: self._set_zoom(1.0)),
                ("Ajustar a ventana", self._fit_to_window),
            ]),
            ("Efectos", [
                ("Escala de grises", lambda *_: self._apply_effect("grayscale")),
                ("Invertir colores", lambda *_: self._apply_effect("invert")),
                ("Desenfoque", lambda *_: self._apply_effect("blur")),
                ("Enfocar", lambda *_: self._apply_effect("sharpen")),
                ("Mosaico / pixelado", lambda *_: self._apply_effect("pixelate")),
                ("sep", None),
                ("Brillo y contraste...", self._brightness_contrast_dialog),
                ("Color y saturacion...", self._color_saturation_dialog),
                ("Balance de color...", self._color_balance_dialog),
                ("Sombra paralela...", self._drop_shadow_dialog),
                ("sep", None),
                ("Borde / marco...", self._frame_dialog),
                ("Marca de agua...", self._watermark_dialog),
            ]),
            ("Transformar", [
                ("Rotar 90 (horario)", lambda *_: self._apply_effect("rotate_cw")),
                ("Rotar 90 (antihorario)", lambda *_: self._apply_effect("rotate_ccw")),
                ("Rotar 180", lambda *_: self._apply_effect("rotate_180")),
                ("Voltear horizontal", lambda *_: self._apply_effect("flip_h")),
                ("Voltear vertical", lambda *_: self._apply_effect("flip_v")),
            ]),
            ("Ayuda", [("Acerca de", self._about)]),
        ]
        for label, entries in items:
            menu_item = Gtk.MenuItem(label=label)
            submenu = Gtk.Menu()
            for text, callback in entries:
                if text == "sep":
                    submenu.append(Gtk.SeparatorMenuItem())
                    continue
                entry = Gtk.MenuItem(label=text)
                entry.connect("activate", callback)
                submenu.append(entry)
            menu_item.set_submenu(submenu)
            menu.append(menu_item)
        menu.show_all()
        return menu

    def _build_toolstrip(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        outer.get_style_context().add_class("toolstrip")
        self.tool_buttons = {}
        group = None
        # Separadores tras estos grupos para que la cinta se lea mejor.
        group_ends = {"lasso", "calligraphy", "callout", "cursor"}
        for tool_id, label in TOOLS:
            _icon_name, tooltip = TOOL_ICONS.get(tool_id, (None, label))
            button = ui.glyph_toggle(tool_id, tooltip, group, size=20)
            if group is None:
                group = button
            button.connect("toggled", self._on_tool_toggled, tool_id)
            outer.pack_start(button, False, False, 0)
            self.tool_buttons[tool_id] = button
            if tool_id in group_ends:
                outer.pack_start(self._separator(), False, False, 4)
        self.tool_buttons["pen"].set_active(True)
        return outer

    def _build_optionsbar(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.get_style_context().add_class("optionsbar")

        outer.pack_start(Gtk.Label(label="Color"), False, False, 0)
        self.color_button = Gtk.ColorButton()
        self.color_button.set_rgba(self._rgba_from_tuple(self.stroke_color))
        self.color_button.set_tooltip_text("Color del trazo")
        self.color_button.connect("color-set", self._on_color_set)
        outer.pack_start(self.color_button, False, False, 0)

        self.fill_check = Gtk.CheckButton(label="Rellenar")
        self.fill_check.set_tooltip_text("Rellenar formas")
        self.fill_check.connect("toggled", self._on_fill_toggled)
        outer.pack_start(self.fill_check, False, False, 0)

        outer.pack_start(self._separator(), False, False, 4)

        outer.pack_start(Gtk.Label(label="Grosor"), False, False, 0)
        width_adj = Gtk.Adjustment(value=self.stroke_width, lower=1, upper=60, step_increment=1)
        self.width_spin = Gtk.SpinButton(adjustment=width_adj)
        self.width_spin.connect("value-changed", self._on_width_changed)
        outer.pack_start(self.width_spin, False, False, 0)

        outer.pack_start(self._separator(), False, False, 4)

        outer.pack_start(Gtk.Label(label="Texto"), False, False, 0)
        font_adj = Gtk.Adjustment(value=self.font_size, lower=8, upper=200, step_increment=2)
        self.font_spin = Gtk.SpinButton(adjustment=font_adj)
        self.font_spin.connect("value-changed", self._on_font_changed)
        outer.pack_start(self.font_spin, False, False, 0)

        hint = Gtk.Label(label="Rueda: zoom  -  Boton central: mover")
        hint.get_style_context().add_class("dim")
        outer.pack_end(hint, False, False, 0)
        return outer

    def _separator(self):
        return Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)

    # ================================================================== estado
    def _status(self, message):
        if not hasattr(self, "statusbar"):
            return
        self.statusbar.pop(self._status_context)
        self.statusbar.push(self._status_context, message)

    def _refresh_pixbuf(self):
        self._pixbuf = pil_to_pixbuf(self.image)

    def _push_undo(self):
        self.undo_stack.append(self.image.copy())
        if len(self.undo_stack) > 40:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.modified = True

    def _set_image(self, image, refresh_original=False):
        self.image = image.convert("RGBA")
        if refresh_original:
            self.original = self.image.copy()
        self._refresh_pixbuf()
        self.queue_draw()

    # ================================================================== transform
    def _recompute_transform(self):
        area_w = self.canvas.get_allocated_width()
        area_h = self.canvas.get_allocated_height()
        if area_w <= 1 or area_h <= 1:
            return
        if self._auto_fit:
            self.scale = min(area_w / self.image.width, area_h / self.image.height, 1.0)
        self.offset[0] = (area_w - self.image.width * self.scale) / 2
        self.offset[1] = (area_h - self.image.height * self.scale) / 2
        self._update_header()

    def _update_header(self):
        header = getattr(self, "_header", None)
        if header is None or getattr(header, "subtitle_label", None) is None:
            return
        header.subtitle_label.set_text(
            f"{self.image.width} x {self.image.height} px     {int(round(self.scale * 100))}%"
        )

    def _to_image(self, x, y):
        return ((x - self.offset[0]) / self.scale, (y - self.offset[1]) / self.scale)

    def _on_size_allocate(self, _widget, _alloc):
        self._recompute_transform()
        self.queue_draw()

    def _zoom(self, factor):
        self._auto_fit = False
        self.scale = max(0.05, min(8.0, self.scale * factor))
        self._recompute_transform()
        self.queue_draw()

    def _set_zoom(self, value):
        self._auto_fit = False
        self.scale = value
        self._recompute_transform()
        self.queue_draw()

    def _fit_to_window(self, *_):
        self._auto_fit = True
        self._recompute_transform()
        self.queue_draw()

    # ================================================================== events
    def _on_tool_toggled(self, button, tool_id):
        if button.get_active():
            self.tool = tool_id
            self._status(f"Herramienta: {dict(TOOLS).get(tool_id, tool_id)}")

    def _on_color_set(self, button):
        rgba = button.get_rgba()
        self.stroke_color = (
            int(rgba.red * 255),
            int(rgba.green * 255),
            int(rgba.blue * 255),
            int(rgba.alpha * 255),
        )

    def _on_fill_toggled(self, button):
        self.fill_shapes = button.get_active()

    def _on_width_changed(self, spin):
        self.stroke_width = int(spin.get_value())

    def _on_font_changed(self, spin):
        self.font_size = int(spin.get_value())

    def _on_press(self, _widget, event):
        self.canvas.grab_focus()
        if event.button == 2:
            self.panning = (event.x, event.y, self.offset[0], self.offset[1])
            return True
        if event.button != 1:
            return False
        x, y = self._to_image(event.x, event.y)
        if self.tool == "text":
            self._text_tool_at(x, y)
            return True
        if self.tool == "stamp":
            self._commit_stamp(x, y)
            return True
        if self.tool == "cursor":
            self._commit_cursor_stamp(x, y)
            return True
        if self.tool == "fill":
            self._commit_fill(x, y)
            return True
        self.drag = {"tool": self.tool, "start": (x, y), "points": [(x, y)]}
        return True

    def _on_motion(self, _widget, event):
        if self.panning:
            dx = event.x - self.panning[0]
            dy = event.y - self.panning[1]
            self.offset[0] = self.panning[2] + dx
            self.offset[1] = self.panning[3] + dy
            self.queue_draw()
            return True
        if self.drag:
            x, y = self._to_image(event.x, event.y)
            self.drag["end"] = (x, y)
            if self.tool in (
                "pen", "marker", "highlighter", "eraser",
                "airbrush", "calligraphy", "retouch", "lasso",
            ):
                self.drag["points"].append((x, y))
            self.queue_draw()
            self._status(f"x={int(x)}  y={int(y)}")
            return True
        return False

    def _on_release(self, _widget, event):
        if self.panning and event.button == 2:
            self.panning = None
            return True
        if not self.drag:
            return False
        drag = self.drag
        self.drag = None
        x, y = self._to_image(event.x, event.y)
        drag["end"] = (x, y)
        self._commit_drag(drag)
        return True

    def _on_scroll(self, _widget, event):
        delta = 0.0
        if event.direction == Gdk.ScrollDirection.SMOOTH:
            try:
                _ok, _dx, delta = event.get_scroll_deltas()
            except Exception:
                delta = 0.0
        elif event.direction == Gdk.ScrollDirection.UP:
            delta = -1.0
        elif event.direction == Gdk.ScrollDirection.DOWN:
            delta = 1.0
        if not delta:
            return False
        factor = max(0.5, min(2.0, 1.0 - delta * 0.12))
        self._zoom(factor)
        return True

    def _on_key(self, _widget, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK:
            if event.keyval == Gdk.KEY_z:
                self._undo()
                return True
            if event.keyval in (Gdk.KEY_y,):
                self._redo()
                return True
            if event.keyval == Gdk.KEY_s:
                self._save_file()
                return True
            if event.keyval == Gdk.KEY_c:
                self._copy_clipboard()
                return True
            if event.keyval == Gdk.KEY_0:
                self._fit_to_window()
                return True
            if event.keyval in (Gdk.KEY_plus, Gdk.KEY_equal, Gdk.KEY_KP_Add):
                self._zoom(1.25)
                return True
            if event.keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
                self._zoom(0.8)
                return True
        return False

    # ================================================================== drawing
    def _on_draw(self, _widget, cr):
        cr.set_source_rgb(0.13, 0.14, 0.16)
        cr.paint()

        self._recompute_transform()
        ox, oy = self.offset
        scale = self.scale
        iw = self.image.width * scale
        ih = self.image.height * scale

        # Sombra suave bajo la imagen
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(ox + 5, oy + 5, iw, ih)
        cr.fill()

        # Tablero de ajedrez (transparencia) bajo la imagen
        cr.save()
        cr.rectangle(ox, oy, iw, ih)
        cr.clip()
        cr.set_source(self._checker_pattern())
        cr.rectangle(ox, oy, iw, ih)
        cr.fill()
        cr.restore()

        # Imagen
        if self._pixbuf:
            cr.save()
            cr.translate(ox, oy)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
            cr.rectangle(0, 0, self.image.width, self.image.height)
            cr.clip()
            cr.paint()
            cr.restore()

        # Previsualizacion de la herramienta activa
        if self.drag:
            cr.save()
            cr.translate(ox, oy)
            cr.scale(scale, scale)
            self._draw_preview(cr, self.drag)
            cr.restore()

        # Borde
        cr.set_source_rgba(0.5, 0.55, 0.65, 0.9)
        cr.set_line_width(1)
        cr.rectangle(ox - 0.5, oy - 0.5, iw + 1, ih + 1)
        cr.stroke()
        return False

    def _checker_pattern(self):
        import cairo

        if getattr(self, "_checker", None) is None:
            surface = cairo.ImageSurface(cairo.FORMAT_RGB24, 16, 16)
            context = cairo.Context(surface)
            context.set_source_rgb(0.20, 0.21, 0.24)
            context.paint()
            context.set_source_rgb(0.26, 0.27, 0.31)
            context.rectangle(0, 0, 8, 8)
            context.fill()
            context.rectangle(8, 8, 8, 8)
            context.fill()
            self._checker = cairo.SurfacePattern(surface)
            self._checker.set_extend(cairo.EXTEND_REPEAT)
        return self._checker

    def _draw_preview(self, cr, drag):
        color = self.stroke_color
        cr.set_source_rgba(color[0] / 255, color[1] / 255, color[2] / 255, color[3] / 255)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        tool = drag["tool"]
        start = drag["start"]
        end = drag.get("end", start)
        width = self.stroke_width

        if tool in ("pen", "line", "marker", "highlighter", "eraser"):
            if tool == "highlighter":
                cr.set_source_rgba(color[0] / 255, color[1] / 255, color[2] / 255, 0.35)
                width = max(width, 14)
            points = drag["points"] if tool != "line" else [start, end]
            if len(points) >= 2:
                cr.set_line_width(width)
                cr.move_to(*points[0])
                for point in points[1:]:
                    cr.line_to(*point)
                cr.stroke()
        elif tool == "arrow":
            self._cairo_arrow(cr, start, end, width)
        elif tool == "rect":
            cr.set_line_width(width)
            cr.rectangle(min(start[0], end[0]), min(start[1], end[1]), abs(end[0] - start[0]), abs(end[1] - start[1]))
            if self.fill_shapes:
                cr.fill_preserve()
            cr.stroke()
        elif tool == "ellipse":
            cr.set_line_width(width)
            cx = (start[0] + end[0]) / 2
            cy = (start[1] + end[1]) / 2
            rx = abs(end[0] - start[0]) / 2
            ry = abs(end[1] - start[1]) / 2
            cr.save()
            cr.translate(cx, cy)
            cr.scale(rx or 1, ry or 1)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            if self.fill_shapes:
                cr.fill_preserve()
            cr.stroke()
        elif tool in ("blur", "pixelate"):
            x = min(start[0], end[0])
            y = min(start[1], end[1])
            cr.set_line_width(1.5)
            cr.rectangle(x, y, abs(end[0] - start[0]), abs(end[1] - start[1]))
            cr.stroke()
        elif tool == "select":
            x = min(start[0], end[0])
            y = min(start[1], end[1])
            cr.set_line_width(1.5)
            cr.set_dash([6, 4])
            cr.rectangle(x, y, abs(end[0] - start[0]), abs(end[1] - start[1]))
            cr.stroke()
            cr.set_dash([])

    def _cairo_arrow(self, cr, start, end, width):
        cr.set_line_width(width)
        cr.move_to(*start)
        cr.line_to(*end)
        cr.stroke()
        size = max(12, width * 3.5)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        cr.move_to(*end)
        cr.line_to(end[0] - size * math.cos(angle - 0.4), end[1] - size * math.sin(angle - 0.4))
        cr.line_to(end[0] - size * math.cos(angle + 0.4), end[1] - size * math.sin(angle + 0.4))
        cr.close_path()
        cr.fill()

    # ================================================================== commit
    def _commit_drag(self, drag):
        tool = drag["tool"]
        start = drag["start"]
        end = drag.get("end", start)
        color = self.stroke_color
        width = self.stroke_width

        if tool == "select":
            rect = (
                int(min(start[0], end[0])),
                int(min(start[1], end[1])),
                int(abs(end[0] - start[0])),
                int(abs(end[1] - start[1])),
            )
            if rect[2] > 2 and rect[3] > 2:
                self._pending_crop = rect
                self._pending_lasso = None
                self._status("Seleccion lista. Usa Editar > Recortar a seleccion.")
            self.queue_draw()
            return

        if tool == "lasso":
            points = [(int(px), int(py)) for px, py in drag["points"]]
            if len(points) > 2:
                self._pending_lasso = points
                self._pending_crop = None
                self._status("Seleccion libre lista. Usa Editar > Recortar a seleccion.")
            self.queue_draw()
            return

        if tool in ("pen", "marker", "highlighter", "eraser", "airbrush", "calligraphy", "retouch"):
            points = [(int(px), int(py)) for px, py in drag["points"]]
            if len(points) == 1:
                points.append((points[0][0] + 1, points[0][1] + 1))
            self._push_undo()
            if tool == "eraser":
                self._raster_erase(points, width)
            elif tool == "marker":
                self._raster_alpha_line(points, max(width, 6), (color[0], color[1], color[2], 150))
            elif tool == "highlighter":
                self._raster_alpha_line(points, max(width, 14), (color[0], color[1], color[2], 90))
            elif tool == "airbrush":
                self._raster_airbrush(points, max(width, 8), color)
            elif tool == "calligraphy":
                self._raster_calligraphy(points, max(width, 6), color)
            elif tool == "retouch":
                self._raster_retouch(points, max(width * 3, 24))
            else:
                self._raster_line(points, width, color)
        elif tool == "line":
            self._push_undo()
            self._raster_line([(int(start[0]), int(start[1])), (int(end[0]), int(end[1]))], width, color)
        elif tool == "arrow":
            self._push_undo()
            self._raster_arrow(start, end, width, color)
        elif tool == "rect":
            self._push_undo()
            self._raster_rect(start, end, width, color)
        elif tool == "ellipse":
            self._push_undo()
            self._raster_ellipse(start, end, width, color)
        elif tool == "callout":
            self._push_undo()
            self._raster_callout(start, end, width, color)
        elif tool in ("blur", "pixelate"):
            self._push_undo()
            self._raster_region_effect(start, end, tool)

        self._refresh_pixbuf()
        self.modified = True
        self.queue_draw()

    # ---- rasterizadores PIL
    @staticmethod
    def _round_caps(draw, points, width, fill):
        radius = width / 2
        for point in (points[0], points[-1]):
            draw.ellipse(
                [point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius],
                fill=fill,
            )

    def _raster_line(self, points, width, color):
        draw = ImageDraw.Draw(self.image)
        draw.line(points, fill=color, width=width, joint="curve")
        self._round_caps(draw, points, width, color)

    def _raster_alpha_line(self, points, width, color):
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.line(points, fill=color, width=width, joint="curve")
        self._round_caps(draw, points, width, color)
        self.image = Image.alpha_composite(self.image, layer)

    def _raster_erase(self, points, width):
        mask = Image.new("L", self.image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.line(points, fill=255, width=width, joint="curve")
        self._round_caps(draw, points, width, 255)
        if self.original.size == self.image.size:
            self.image.paste(self.original, (0, 0), mask)

    def _raster_arrow(self, start, end, width, color):
        draw = ImageDraw.Draw(self.image)
        draw.line([tuple(start), tuple(end)], fill=color, width=width)
        size = max(12, width * 3.5)
        angle = math.atan2(end[1] - start[1], end[0] - start[0])
        head = [
            (end[0], end[1]),
            (end[0] - size * math.cos(angle - 0.4), end[1] - size * math.sin(angle - 0.4)),
            (end[0] - size * math.cos(angle + 0.4), end[1] - size * math.sin(angle + 0.4)),
        ]
        draw.polygon(head, fill=color)

    def _raster_rect(self, start, end, width, color):
        draw = ImageDraw.Draw(self.image)
        box = [min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])]
        if self.fill_shapes:
            draw.rectangle(box, fill=color)
        else:
            draw.rectangle(box, outline=color, width=width)

    def _raster_ellipse(self, start, end, width, color):
        draw = ImageDraw.Draw(self.image)
        box = [min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])]
        if self.fill_shapes:
            draw.ellipse(box, fill=color)
        else:
            draw.ellipse(box, outline=color, width=width)

    def _raster_region_effect(self, start, end, kind):
        box = (
            int(min(start[0], end[0])),
            int(min(start[1], end[1])),
            int(max(start[0], end[0])),
            int(max(start[1], end[1])),
        )
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            return
        region = self.image.crop(box)
        if kind == "blur":
            region = region.filter(ImageFilter.GaussianBlur(6))
        else:
            small = region.resize(
                (max(1, region.width // 12), max(1, region.height // 12)), Image.NEAREST
            )
            region = small.resize((box[2] - box[0], box[3] - box[1]), Image.NEAREST)
        self.image.paste(region, (box[0], box[1]))

    def _raster_airbrush(self, points, radius, color):
        """Aerografo: salpica puntos aleatorios alrededor del trazo."""
        draw = ImageDraw.Draw(self.image)
        for point in points:
            for _ in range(max(6, radius)):
                angle = random.uniform(0, 2 * math.pi)
                distance = random.uniform(0, radius)
                px = int(point[0] + math.cos(angle) * distance)
                py = int(point[1] + math.sin(angle) * distance)
                draw.point((px, py), fill=color)

    def _raster_calligraphy(self, points, width, color):
        """Caligrafia: grosor segun la direccion del trazo (plumilla inclinada)."""
        nib = math.radians(45)
        draw = ImageDraw.Draw(self.image)
        for index in range(1, len(points)):
            x0, y0 = points[index - 1]
            x1, y1 = points[index]
            if x0 == x1 and y0 == y1:
                continue
            angle = math.atan2(y1 - y0, x1 - x0)
            stroke = max(1, int(width * (0.25 + 0.75 * abs(math.sin(angle - nib)))))
            draw.line([(x0, y0), (x1, y1)], fill=color, width=stroke)

    def _raster_retouch(self, points, radius):
        """Retoque: desenfoque parcial siguiendo el pincel (Pillow)."""
        if not points:
            return
        mask = Image.new("L", self.image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        for point in points:
            mask_draw.ellipse(
                [point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius],
                fill=120,
            )
        blurred = self.image.filter(ImageFilter.GaussianBlur(max(3, radius / 4)))
        self.image = Image.composite(blurred, self.image, mask)

    def _raster_callout(self, start, end, width, color):
        """Globo de texto (forma + rabillo) con Pillow."""
        draw = ImageDraw.Draw(self.image)
        x0, x1 = sorted((int(start[0]), int(end[0])))
        y0, y1 = sorted((int(start[1]), int(end[1])))
        if x1 - x0 < 10 or y1 - y0 < 10:
            return
        radius = max(6, width * 2)
        draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, outline=color, width=width)
        tail_x = x0 + (x1 - x0) // 4
        draw.polygon(
            [(tail_x, y1), (tail_x + 18, y1), (tail_x - 6, y1 + 22)],
            fill=color,
        )

    def _commit_cursor_stamp(self, x, y):
        """Sello de cursor: flecha tipica dibujada con Pillow."""
        self._push_undo()
        draw = ImageDraw.Draw(self.image)
        scale = max(1, self.stroke_width)
        arrow = [
            (0, 0), (0, 14), (4, 10), (7, 16), (10, 14), (7, 9), (12, 9),
        ]
        points = [(x + px * scale, y + py * scale) for px, py in arrow]
        draw.polygon(points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
        self._refresh_pixbuf()
        self.queue_draw()

    def _commit_stamp(self, x, y):
        self._push_undo()
        draw = ImageDraw.Draw(self.image)
        radius = max(12, self.stroke_width * 4)
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=self.stroke_color,
            outline=(255, 255, 255, 255),
            width=2,
        )
        font = load_font(int(radius * 1.2), bold=True)
        text = str(self.stamp_number)
        bbox = draw.textbbox((0, 0), text, font=font)
        tx = x - (bbox[2] - bbox[0]) / 2 - bbox[0]
        ty = y - (bbox[3] - bbox[1]) / 2 - bbox[1]
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
        self.stamp_number += 1
        self._refresh_pixbuf()
        self.queue_draw()

    def _commit_fill(self, x, y):
        self._push_undo()
        try:
            ImageDraw.floodfill(self.image, (int(x), int(y)), self.stroke_color, thresh=40)
        except Exception:
            pass
        self._refresh_pixbuf()
        self.queue_draw()

    def _text_tool_at(self, x, y):
        dialog = Gtk.Dialog(title="Insertar texto", transient_for=self, modal=True)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Aceptar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        entry = Gtk.Entry()
        entry.set_width_chars(40)
        entry.connect("activate", lambda *_: dialog.response(Gtk.ResponseType.OK))
        box.pack_start(Gtk.Label(label="Texto:", xalign=0), False, False, 0)
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        text = entry.get_text()
        dialog.destroy()
        if response != Gtk.ResponseType.OK or not text:
            return
        self._push_undo()
        draw = ImageDraw.Draw(self.image)
        font = load_font(self.font_size)
        draw.text(
            (int(x), int(y)),
            text,
            font=font,
            fill=self.stroke_color,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 180),
        )
        self._refresh_pixbuf()
        self.queue_draw()

    # ================================================================== edicion
    def _undo(self):
        if not self.undo_stack:
            self._status("Nada que deshacer")
            return
        self.redo_stack.append(self.image.copy())
        self._set_image(self.undo_stack.pop())
        self._status("Deshecho")

    def _redo(self):
        if not self.redo_stack:
            self._status("Nada que rehacer")
            return
        self.undo_stack.append(self.image.copy())
        self._set_image(self.redo_stack.pop())
        self._status("Rehecho")

    def _crop_to_selection(self, *_):
        lasso = getattr(self, "_pending_lasso", None)
        rect = getattr(self, "_pending_crop", None)
        if lasso:
            xs = [p[0] for p in lasso]
            ys = [p[1] for p in lasso]
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            if box[2] - box[0] < 2 or box[3] - box[1] < 2:
                return
            self._push_undo()
            cropped = self.image.crop(box)
            mask = Image.new("L", cropped.size, 0)
            ImageDraw.Draw(mask).polygon(
                [(p[0] - box[0], p[1] - box[1]) for p in lasso], fill=255
            )
            transparent = Image.new("RGBA", cropped.size, (0, 0, 0, 0))
            cropped = Image.composite(cropped, transparent, mask)
            self.image = cropped
            self.original = self.image.copy()
            self._pending_lasso = None
            self._refresh_pixbuf()
            self._fit_to_window()
            self._status("Recortado a la seleccion libre")
            return
        if not rect:
            self._status("Primero selecciona una region con la herramienta Seleccion")
            return
        self._push_undo()
        self.image = self.image.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
        self.original = self.image.copy()
        self._pending_crop = None
        self._refresh_pixbuf()
        self._fit_to_window()
        self._status("Recortado")

    def _invert_selection_placeholder(self, *_):
        self._push_undo()
        self._set_image(ImageOps.invert(self.image.convert("RGB")).convert("RGBA"), refresh_original=True)
        self._status("Colores invertidos")

    def _apply_effect(self, name):
        self._push_undo()
        image = self.image
        if name == "grayscale":
            gray = ImageOps.grayscale(image.convert("RGB"))
            image = Image.merge("RGBA", (gray, gray, gray, image.getchannel("A")))
        elif name == "invert":
            rgb = ImageOps.invert(image.convert("RGB"))
            image = Image.merge("RGBA", (*rgb.split(), image.getchannel("A")))
        elif name == "blur":
            image = image.filter(ImageFilter.GaussianBlur(3))
        elif name == "sharpen":
            image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=150, threshold=3))
        elif name == "pixelate":
            small = image.resize((max(1, image.width // 16), max(1, image.height // 16)), Image.NEAREST)
            image = small.resize((image.width, image.height), Image.NEAREST)
        elif name == "rotate_cw":
            image = image.rotate(-90, expand=True)
        elif name == "rotate_ccw":
            image = image.rotate(90, expand=True)
        elif name == "rotate_180":
            image = image.rotate(180, expand=True)
        elif name == "flip_h":
            image = ImageOps.mirror(image)
        elif name == "flip_v":
            image = ImageOps.flip(image)
        image = image.convert("RGBA")
        self._set_image(image, refresh_original=True)
        self._fit_to_window()
        self._status(f"Efecto aplicado: {name}")

    def _resize_dialog(self, *_):
        dialog = Gtk.Dialog(title="Redimensionar", transient_for=self, modal=True)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Aceptar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        box.set_margin_top(10)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        width_spin = Gtk.SpinButton.new_with_range(1, 20000, 1)
        width_spin.set_value(self.image.width)
        height_spin = Gtk.SpinButton.new_with_range(1, 20000, 1)
        height_spin.set_value(self.image.height)
        keep = Gtk.CheckButton(label="Mantener proporcion")
        keep.set_active(True)

        ratio = self.image.width / self.image.height

        def on_width(_spin):
            if keep.get_active():
                height_spin.set_value(round(width_spin.get_value() / ratio))

        def on_height(_spin):
            if keep.get_active():
                width_spin.set_value(round(height_spin.get_value() * ratio))

        width_spin.connect("value-changed", on_width)
        height_spin.connect("value-changed", on_height)
        grid.attach(Gtk.Label(label="Ancho:", xalign=0), 0, 0, 1, 1)
        grid.attach(width_spin, 1, 0, 1, 1)
        grid.attach(Gtk.Label(label="Alto:", xalign=0), 0, 1, 1, 1)
        grid.attach(height_spin, 1, 1, 1, 1)
        box.pack_start(grid, False, False, 0)
        box.pack_start(keep, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            new_size = (int(width_spin.get_value()), int(height_spin.get_value()))
            dialog.destroy()
            self._push_undo()
            self._set_image(self.image.resize(new_size, Image.LANCZOS), refresh_original=True)
            self._fit_to_window()
            self._status(f"Redimensionado a {new_size[0]}x{new_size[1]}")
            return
        dialog.destroy()

    def _slider_dialog(self, title, entries, apply_callback):
        dialog = Gtk.Dialog(title=title, transient_for=self, modal=True)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Aceptar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        scales = {}
        for label, low, high, value in entries:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.pack_start(Gtk.Label(label=label, width_chars=16, xalign=0), False, False, 0)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, low, high, 1)
            scale.set_value(value)
            scale.set_size_request(220, -1)
            row.pack_start(scale, True, True, 0)
            box.pack_start(row, False, False, 0)
            scales[label] = scale
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            values = {label: scale.get_value() for label, scale in scales.items()}
            dialog.destroy()
            self._push_undo()
            self._set_image(apply_callback(self.image, values), refresh_original=True)
            self._status(f"{title} aplicado")
            return
        dialog.destroy()

    def _brightness_contrast_dialog(self, *_):
        def apply(image, values):
            out = ImageEnhance.Brightness(image.convert("RGB")).enhance(values["Brillo"] / 50.0)
            out = ImageEnhance.Contrast(out).enhance(values["Contraste"] / 50.0)
            return Image.merge("RGBA", (*out.split(), image.getchannel("A")))

        self._slider_dialog(
            "Brillo y contraste",
            [("Brillo", 0, 100, 50), ("Contraste", 0, 100, 50)],
            apply,
        )

    def _color_saturation_dialog(self, *_):
        def apply(image, values):
            out = ImageEnhance.Color(image.convert("RGB")).enhance(values["Saturacion"] / 50.0)
            out = ImageEnhance.Sharpness(out).enhance(values["Nitidez"] / 50.0)
            return Image.merge("RGBA", (*out.split(), image.getchannel("A")))

        self._slider_dialog(
            "Color y saturacion",
            [("Saturacion", 0, 100, 50), ("Nitidez", 0, 100, 50)],
            apply,
        )

    def _color_balance_dialog(self, *_):
        def apply(image, values):
            return channel_balance(
                image,
                values["Rojo"] - 50,
                values["Verde"] - 50,
                values["Azul"] - 50,
            )

        self._slider_dialog(
            "Balance de color",
            [("Rojo", 0, 100, 50), ("Verde", 0, 100, 50), ("Azul", 0, 100, 50)],
            apply,
        )

    def _drop_shadow_dialog(self, *_):
        def apply(image, values):
            return add_drop_shadow(
                image,
                int(values["Desplazamiento"]),
                int(values["Desenfoque"]),
                int(values["Opacidad"]),
            )

        self._slider_dialog(
            "Sombra paralela",
            [("Desplazamiento", 0, 60, 14), ("Desenfoque", 0, 40, 12), ("Opacidad", 0, 100, 60)],
            apply,
        )

    def _frame_dialog(self, *_):
        def apply(image, values):
            size = int(values["Grosor"])
            color = (255, 255, 255, 255)
            new = Image.new("RGBA", (image.width + size * 2, image.height + size * 2), color)
            new.paste(image, (size, size), image)
            return new

        self._slider_dialog("Borde / marco", [("Grosor", 1, 80, 12)], apply)

    def _watermark_dialog(self, *_):
        text = "PICPICK"
        opacity = 90
        dialog = Gtk.Dialog(title="Marca de agua", transient_for=self, modal=True)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Aceptar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_spacing(6)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        entry = Gtk.Entry()
        entry.set_text(text)
        box.pack_start(Gtk.Label(label="Texto:", xalign=0), False, False, 0)
        box.pack_start(entry, False, False, 0)
        dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK:
            text = entry.get_text() or "PICPICK"
            dialog.destroy()
            self._push_undo()
            base = self.image
            layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(layer)
            font = load_font(max(24, base.width // 14), bold=True)
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            tile = Image.new("RGBA", (tw + 80, th + 80), (0, 0, 0, 0))
            tdraw = ImageDraw.Draw(tile)
            tdraw.text((40, 40), text, font=font, fill=(255, 255, 255, opacity))
            tile = tile.rotate(30, expand=True)
            for y in range(0, base.height, tile.height):
                for x in range(0, base.width, tile.width):
                    layer.alpha_composite(tile, (x, y))
            self._set_image(Image.alpha_composite(base, layer), refresh_original=True)
            self._status("Marca de agua aplicada")
            return
        dialog.destroy()

    # ================================================================== archivo
    def _open_file(self, *_):
        dialog = Gtk.FileChooserDialog(
            title="Abrir imagen",
            parent=self,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Abrir", Gtk.ResponseType.ACCEPT)
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Imagenes")
        filter_images.add_mime_type("image/*")
        filter_images.add_pattern("*.png")
        filter_images.add_pattern("*.jpg")
        filter_images.add_pattern("*.jpeg")
        filter_images.add_pattern("*.bmp")
        filter_images.add_pattern("*.gif")
        dialog.add_filter(filter_images)
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            dialog.destroy()
            try:
                self._set_image(Image.open(path).convert("RGBA"), refresh_original=True)
                self.current_path = path
                self._fit_to_window()
                self._status(f"Abierto: {path}")
            except Exception as exc:
                self._status(f"Error al abrir: {exc}")
            return
        dialog.destroy()

    def _save_file(self, *_):
        if not self.current_path:
            return self._save_file_as()
        try:
            self._write_image(self.current_path)
            self.modified = False
            self._status(f"Guardado: {self.current_path}")
        except Exception as exc:
            self._status(f"Error al guardar: {exc}")
        return False

    def _save_file_as(self, *_):
        dialog = Gtk.FileChooserDialog(
            title="Guardar como",
            parent=self,
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Guardar", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        try:
            directory = self.config.ensure_save_dir()
            dialog.set_current_folder(str(directory))
        except Exception:
            pass
        fmt = self.config.get("save_format", "png")
        dialog.set_current_name(f"captura.{fmt}")
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            dialog.destroy()
            try:
                self._write_image(path)
                self.current_path = path
                self.modified = False
                self._status(f"Guardado: {path}")
            except Exception as exc:
                self._status(f"Error al guardar: {exc}")
            return self.current_path
        dialog.destroy()
        return None

    def _write_image(self, path):
        image = self.image
        lower = path.lower()
        if lower.endswith((".jpg", ".jpeg")):
            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            background.save(path, quality=self.config.get("jpeg_quality", 90))
        elif lower.endswith(".bmp"):
            image.convert("RGB").save(path)
        elif lower.endswith(".gif"):
            image.convert("RGB").save(path)
        elif lower.endswith(".pdf"):
            image.convert("RGB").save(path, "PDF", resolution=100.0)
        else:
            image.save(path)
        self.config["save_format"] = lower.rsplit(".", 1)[-1]

    def _copy_clipboard(self, *_):
        capture.copy_image_to_clipboard(self.image)
        self._status("Copiado al portapapeles")

    def _print_image(self, *_):
        operations = Gtk.PrintOperation()
        operations.set_n_pages(1)
        pixbuf = pil_to_pixbuf(self.image)

        def on_draw(_operation, context, _page_nr):
            cr = context.get_cairo_context()
            page_w = context.get_width()
            page_h = context.get_height()
            scale = min(page_w / self.image.width, page_h / self.image.height)
            width = self.image.width * scale
            height = self.image.height * scale
            cr.save()
            cr.translate((page_w - width) / 2, (page_h - height) / 2)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
            cr.rectangle(0, 0, self.image.width, self.image.height)
            cr.fill()
            cr.restore()

        operations.connect("draw-page", on_draw)
        operations.run(Gtk.PrintOperationAction.PRINT_DIALOG, self)

    def _export_temp(self):
        import tempfile

        directory = tempfile.mkdtemp(prefix="imagewatcher-")
        filename = f"captura_{time.strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(directory, filename)
        self.image.save(path)
        return path, filename

    def _open_external(self, *_):
        try:
            path, _name = self._export_temp()
            share.open_with_external(path)
            self._status("Abierto con el programa externo")
        except Exception as exc:
            self._status(f"No se pudo abrir externamente: {exc}")

    def _share_url(self, *_):
        try:
            path, filename = self._export_temp()
            if getattr(self, "_share", None) is None:
                self._share = share.LocalShare(os.path.dirname(path))
            url = self._share.start(filename)
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(url, -1)
            clipboard.store()
            dialog = Gtk.MessageDialog(
                transient_for=self, modal=True, message_type=Gtk.MessageType.INFO,
                buttons=Gtk.ButtonsType.OK,
                text="Enlace de red listo (copiado al portapapeles)",
            )
            dialog.format_secondary_text(url)
            dialog.run()
            dialog.destroy()
        except Exception as exc:
            self._status(f"No se pudo compartir: {exc}")

    def _new_capture(self, *_):
        if self.capture_callback:
            self.capture_callback()

    def _about(self, *_):
        dialog = Gtk.AboutDialog(transient_for=self, modal=True)
        dialog.set_program_name("imageWatcher")
        dialog.set_version(__version__)
        dialog.set_comments("Clon libre inspirado en PicPick para Linux Mint (GTK3).")
        dialog.run()
        dialog.destroy()

    def _on_delete(self, *_):
        share_server = getattr(self, "_share", None)
        if share_server is not None:
            share_server.stop()
            self._share = None
        return False

    def _rgba_from_tuple(self, color):
        rgba = Gdk.RGBA()
        rgba.red = color[0] / 255
        rgba.green = color[1] / 255
        rgba.blue = color[2] / 255
        rgba.alpha = color[3] / 255 if len(color) > 3 else 1.0
        return rgba

    def queue_draw(self):
        if hasattr(self, "canvas"):
            self.canvas.queue_draw()
