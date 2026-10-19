"""Overlay de seleccion de region con la seleccion editable.

Tras arrastrar una region rectangular, es posible **moverla** (arrastrando desde
dentro) y **redimensionarla** (arrastrando los tiradores de esquinas/bordes) antes
de confirmar con Enter o doble clic. Esc cancela.
"""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from PIL import Image, ImageChops, ImageDraw  # noqa: E402

from .gtk_util import pil_to_pixbuf  # noqa: E402

HANDLE = 9
CORNERS = {"nw", "ne", "sw", "se"}
EDGES = {"n", "s", "e", "w"}


def extract_freehand(base_image, points):
    """Recorta ``base_image`` con una mascara poligonal.

    Devuelve una imagen RGBA del bounding box del trazo, con transparencia
    fuera del poligono. ``points`` son coordenadas absolutas de la captura.
    """
    if base_image is None or len(points) < 3:
        return None
    xs = [int(point[0]) for point in points]
    ys = [int(point[1]) for point in points]
    left = max(0, min(xs))
    top = max(0, min(ys))
    right = min(base_image.width, max(xs) + 1)
    bottom = min(base_image.height, max(ys) + 1)
    width = right - left
    height = bottom - top
    if width <= 2 or height <= 2:
        return None

    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(
        [(x - left, y - top) for x, y in points], fill=255
    )
    image = base_image.crop((left, top, right, bottom)).convert("RGBA")
    image.putalpha(ImageChops.multiply(image.getchannel("A"), mask))
    return image


class FixedRegionDialog(Gtk.Dialog):
    """Pide el tamano de la region fija y recuerda el ultimo usado."""

    def __init__(self, parent=None, size=(360, 360)):
        super().__init__(title="Captura de region fija", transient_for=parent, modal=True)
        try:
            from . import ui

            ui.apply_dark(self)
        except Exception:
            pass
        self.set_resizable(False)
        self.set_border_width(12)
        self.set_default_response(Gtk.ResponseType.OK)
        self.add_buttons(
            "Cancelar", Gtk.ResponseType.CANCEL,
            "Capturar", Gtk.ResponseType.OK,
        )

        box = self.get_content_area()
        box.set_spacing(10)
        label = Gtk.Label(
            label="Elige el tamano. Despues mueve el raton y haz clic para capturar.",
            xalign=0,
        )
        label.set_line_wrap(True)
        box.pack_start(label, False, False, 0)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        grid.attach(Gtk.Label(label="Ancho:", xalign=0), 0, 0, 1, 1)
        width = int(size[0]) if size else 360
        height = int(size[1]) if size else 360
        self.width_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.width_spin.set_value(max(1, width))
        grid.attach(self.width_spin, 1, 0, 1, 1)

        grid.attach(Gtk.Label(label="Alto:", xalign=0), 0, 1, 1, 1)
        self.height_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.height_spin.set_value(max(1, height))
        grid.attach(self.height_spin, 1, 1, 1, 1)
        box.pack_start(grid, False, False, 0)
        self.show_all()

    def get_size(self):
        return (int(self.width_spin.get_value()), int(self.height_spin.get_value()))


def ask_fixed_size(parent=None, last_size=(360, 360)):
    """Muestra el dialogo de region fija. Devuelve ``(w, h)`` o ``None``."""
    dialog = FixedRegionDialog(parent, last_size)
    try:
        if dialog.run() == Gtk.ResponseType.OK:
            return dialog.get_size()
        return None
    finally:
        dialog.destroy()


def _cursor_name(handle):
    return {
        "nw": "nw-resize", "se": "se-resize",
        "ne": "ne-resize", "sw": "sw-resize",
        "n": "n-resize", "s": "s-resize",
        "e": "e-resize", "w": "w-resize",
    }.get(handle, "crosshair")


class RegionSelector(Gtk.Window):
    """Selector de region con seleccion movible y redimensionable."""

    def __init__(self, base_image, on_done, on_cancel=None, detect_windows=True,
                 fixed_size=None, freehand=False, initial_rect=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.base = base_image
        self._pixbuf = pil_to_pixbuf(base_image)
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.detect_windows = detect_windows
        self.fixed_size = tuple(int(v) for v in fixed_size) if fixed_size else None
        self.freehand_mode = bool(freehand)
        self._freehand_points = []

        self.rect = None            # (x, y, w, h) confirmada o en edicion
        self.mode = None            # creating | moving | resizing | freehand
        self.handle = None
        self._drag_start = None
        self._rect_start = None
        self.pointer = (0, 0)
        self.hover_rect = None
        self._last_hover = None
        self._last_click = (0, 0, 0)

        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)
        self.set_accept_focus(True)
        self.set_type_hint(
            Gdk.WindowTypeHint.OVERLAY if hasattr(Gdk.WindowTypeHint, "OVERLAY")
            else Gdk.WindowTypeHint.DOCK
        )

        width, height = self.base.width, self.base.height
        self.set_default_size(width, height)
        self.move(0, 0)
        self.resize(width, height)

        if self.fixed_size:
            if initial_rect:
                self.rect = self._clamp_rect(*initial_rect)
            else:
                self.rect = self._center_rect(width / 2, height / 2, *self.fixed_size)

        self.area = Gtk.DrawingArea()
        self.area.set_size_request(width, height)
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
            | Gdk.EventMask.KEY_PRESS_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("button-release-event", self._on_release)
        self.area.connect("motion-notify-event", self._on_motion)
        self.add(self.area)

        self.connect("key-press-event", self._on_key)
        self.connect("destroy", self._on_destroy)

        self.set_can_focus(True)
        self.show_all()
        self.fullscreen()
        self.present()
        GLib.timeout_add(50, self._grab)

    def _grab(self):
        try:
            window = self.get_window()
            if window:
                self._set_cursor("crosshair")
                self.grab_focus()
        except Exception:
            pass
        return False

    def _set_cursor(self, name):
        try:
            cursor = Gdk.Cursor.new_from_name(Gdk.Display.get_default(), name)
            window = self.area.get_window() or self.get_window()
            if window is not None:
                window.set_cursor(cursor)
        except Exception:
            pass

    # ------------------------------------------------------------------ events
    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._finish_cancel()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.freehand_mode and len(self._freehand_points) >= 3:
                self._finish_freehand()
            elif self.rect:
                self._finish_accept(self.rect)
            return True
        return False

    def _on_press(self, _widget, event):
        self.area.grab_focus()
        x, y = int(event.x), int(event.y)
        if event.button == 3:
            self._finish_cancel()
            return True
        if event.button != 1:
            return False

        if self.fixed_size:
            self.rect = self._center_rect(x, y, *self.fixed_size)
            self._finish_accept(self.rect)
            return True

        if self.freehand_mode:
            self.mode = "freehand"
            self._freehand_points = [(x, y)]
            self.rect = None
            self.hover_rect = None
            self.area.queue_draw()
            return True

        now = GLib.get_monotonic_time() / 1000.0
        last_time, last_x, last_y = self._last_click
        double = (now - last_time < 320) and abs(x - last_x) < 6 and abs(y - last_y) < 6
        self._last_click = (now, x, y)
        if double and self.rect and self._in_rect(x, y):
            self._finish_accept(self.rect)
            return True

        if self.rect:
            handle = self._handle_at(x, y)
            if handle:
                self.mode = "resizing"
                self.handle = handle
                self._drag_start = (x, y)
                self._rect_start = self._ltrb(self.rect)
                return True
            if self._in_rect(x, y):
                self.mode = "moving"
                self._drag_start = (x, y)
                self._rect_start = self._ltrb(self.rect)
                return True

        # Empezar una nueva seleccion.
        self.mode = "creating"
        self.rect = None
        self.hover_rect = None
        self._drag_start = (x, y)
        return True

    def _on_motion(self, _widget, event):
        x, y = int(event.x), int(event.y)
        self.pointer = (x, y)

        if self.fixed_size:
            self.rect = self._center_rect(x, y, *self.fixed_size)
            self.area.queue_draw()
            return True

        if self.mode == "freehand":
            x = max(0, min(x, self.base.width - 1))
            y = max(0, min(y, self.base.height - 1))
            if not self._freehand_points or abs(x - self._freehand_points[-1][0]) + abs(y - self._freehand_points[-1][1]) >= 1:
                self._freehand_points.append((x, y))
            self.rect = self._points_bbox(self._freehand_points)
            self.area.queue_draw()
            return True

        if self.mode == "creating":
            self.rect = self._normalize(self._drag_start, (x, y))
        elif self.mode == "moving":
            dx = x - self._drag_start[0]
            dy = y - self._drag_start[1]
            left, top, right, bottom = self._rect_start
            self.rect = self._clamp(left + dx, top + dy, right + dx, bottom + dy)
        elif self.mode == "resizing":
            self.rect = self._resize(x, y)
        else:
            self._update_cursor(x, y)
            if self.detect_windows and self.rect is None:
                if self._last_hover is None or abs(x - self._last_hover[0]) + abs(y - self._last_hover[1]) > 6:
                    self._last_hover = (x, y)
                    self.hover_rect = self._window_at(x, y)

        self.area.queue_draw()
        return True

    def _on_release(self, _widget, event):
        if event.button != 1:
            return False
        if self.fixed_size:
            return True
        if self.mode == "freehand":
            self.mode = None
            self._finish_freehand()
            return True
        if self.mode == "creating":
            if not self.rect or self.rect[2] <= 3 or self.rect[3] <= 3:
                self.rect = None
        self.mode = None
        self.handle = None
        self._drag_start = None
        self._rect_start = None
        self.area.queue_draw()
        return True

    def _on_destroy(self, _widget):
        if self.on_cancel:
            callback, self.on_cancel = self.on_cancel, None
            callback()
            self.on_done = None

    # ------------------------------------------------------------------ geometry
    def _center_rect(self, cx, cy, width, height):
        width = max(1, min(int(width), self.base.width))
        height = max(1, min(int(height), self.base.height))
        left = int(cx - width / 2)
        top = int(cy - height / 2)
        left = max(0, min(left, self.base.width - width))
        top = max(0, min(top, self.base.height - height))
        return (left, top, width, height)

    def _clamp_rect(self, x, y, width, height):
        width = max(1, min(int(width), self.base.width))
        height = max(1, min(int(height), self.base.height))
        left = max(0, min(int(x), self.base.width - width))
        top = max(0, min(int(y), self.base.height - height))
        return (left, top, width, height)

    def _points_bbox(self, points):
        if not points:
            return None
        xs = [int(point[0]) for point in points]
        ys = [int(point[1]) for point in points]
        left = max(0, min(xs))
        top = max(0, min(ys))
        right = min(self.base.width - 1, max(xs))
        bottom = min(self.base.height - 1, max(ys))
        if right < left or bottom < top:
            return None
        return (left, top, right - left + 1, bottom - top + 1)

    @staticmethod
    def _ltrb(rect):
        x, y, w, h = rect
        return (x, y, x + w, y + h)

    def _normalize(self, p1, p2):
        left, right = sorted((p1[0], p2[0]))
        top, bottom = sorted((p1[1], p2[1]))
        return self._clamp(left, top, right, bottom)

    def _clamp(self, left, top, right, bottom):
        left = max(0, min(left, self.base.width))
        right = max(0, min(right, self.base.width))
        top = max(0, min(top, self.base.height))
        bottom = max(0, min(bottom, self.base.height))
        return (left, top, max(0, right - left), max(0, bottom - top))

    def _resize(self, x, y):
        left, top, right, bottom = self._rect_start
        if "n" in self.handle:
            top = y
        if "s" in self.handle:
            bottom = y
        if "w" in self.handle:
            left = x
        if "e" in self.handle:
            right = x
        return self._clamp(min(left, right), min(top, bottom), max(left, right), max(top, bottom))

    def _handles(self):
        if not self.rect:
            return {}
        x, y, w, h = self.rect
        return {
            "nw": (x, y), "n": (x + w / 2, y), "ne": (x + w, y),
            "e": (x + w, y + h / 2), "se": (x + w, y + h),
            "s": (x + w / 2, y + h), "sw": (x, y + h), "w": (x, y + h / 2),
        }

    def _handle_at(self, x, y):
        for name in ("nw", "ne", "se", "sw", "n", "s", "e", "w"):
            hx, hy = self._handles()[name]
            if abs(x - hx) <= HANDLE and abs(y - hy) <= HANDLE:
                return name
        return None

    def _in_rect(self, x, y):
        if not self.rect:
            return False
        rx, ry, rw, rh = self.rect
        return rx <= x <= rx + rw and ry <= y <= ry + rh

    def _update_cursor(self, x, y):
        if not self.rect:
            self._set_cursor("crosshair")
            return
        handle = self._handle_at(x, y)
        if handle:
            self._set_cursor(_cursor_name(handle))
        elif self._in_rect(x, y):
            self._set_cursor("move")
        else:
            self._set_cursor("crosshair")

    def _window_at(self, x, y):
        try:
            from . import capture

            d = capture._x11_display()
            root = d.screen().root
            child = root
            while True:
                try:
                    result = child.query_tree().children
                except Exception:
                    break
                found = None
                for candidate in reversed(result):
                    try:
                        cx, cy = capture._root_coords(candidate, root)
                        geom = candidate.get_geometry()
                        if cx <= x < cx + geom.width and cy <= y < cy + geom.height:
                            found = candidate
                            break
                    except Exception:
                        continue
                if found is None:
                    break
                child = found
                try:
                    if child.query_tree().parent.id == root.id:
                        break
                except Exception:
                    break
            cx, cy = capture._root_coords(child, root)
            geom = child.get_geometry()
            return (cx, cy, geom.width, geom.height)
        except Exception:
            return None

    def _complete(self, image):
        self.on_cancel = None
        callback = self.on_done
        self.on_done = None
        self.destroy()
        if callback:
            callback(image)

    def _finish_accept(self, rect):
        image = self.base.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
        self._complete(image)

    def _finish_freehand(self):
        image = extract_freehand(self.base, self._freehand_points)
        if image is None:
            self._freehand_points = []
            self.rect = None
            self.mode = None
            self.area.queue_draw()
            return
        self._complete(image)

    def _finish_cancel(self):
        self.on_done = None
        self.destroy()

    # ------------------------------------------------------------------ drawing
    def _on_draw(self, _widget, cr):
        Gdk.cairo_set_source_pixbuf(cr, self._pixbuf, 0, 0)
        cr.paint()

        if self.freehand_mode and len(self._freehand_points) >= 2:
            self._draw_freehand(cr)
            return False

        rect = self.rect if self.rect else (self.hover_rect if not self.mode else None)
        if rect:
            rx, ry, rw, rh = rect
            cr.set_source_rgba(0, 0, 0, 0.45)
            cr.rectangle(0, 0, self.base.width, self.base.height)
            cr.rectangle(rx, ry, rw, rh)
            cr.set_fill_rule(1)
            cr.fill()
            cr.set_fill_rule(0)

            cr.set_source_rgb(0.11, 0.65, 0.98)
            cr.set_line_width(2)
            cr.rectangle(rx + 0.5, ry + 0.5, rw, rh)
            cr.stroke()

            self._draw_badge(cr, rx, ry, f"{rw} x {rh} px")

            if self.rect and not self.fixed_size:
                self._draw_handles(cr)
            if self.fixed_size:
                self._draw_hint(cr, "Mueve el raton y haz clic para capturar   Esc: cancelar")
            elif self.rect:
                self._draw_hint(cr, "Arrastra para mover/redimensionar   Enter o doble clic: capturar   Esc: cancelar")
        else:
            cr.set_source_rgba(0, 0, 0, 0.25)
            cr.paint()
            if not self.mode:
                self._draw_hint(cr, "Arrastra para seleccionar una region   Esc: cancelar")
        return False

    def _draw_freehand(self, cr):
        points = self._freehand_points
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.rectangle(0, 0, self.base.width, self.base.height)
        cr.move_to(points[0][0], points[0][1])
        for x, y in points[1:]:
            cr.line_to(x, y)
        cr.close_path()
        cr.set_fill_rule(1)
        cr.fill()
        cr.set_fill_rule(0)

        cr.set_source_rgb(0.11, 0.65, 0.98)
        cr.set_line_width(2)
        cr.move_to(points[0][0], points[0][1])
        for x, y in points[1:]:
            cr.line_to(x, y)
        cr.close_path()
        cr.stroke()

        if self.rect:
            rx, ry, rw, rh = self.rect
            self._draw_badge(cr, rx, ry, f"{rw} x {rh} px")
        self._draw_hint(cr, "Dibuja una forma para capturar   Esc: cancelar")

    def _draw_handles(self, cr):
        cr.set_source_rgb(0.11, 0.65, 0.98)
        cr.set_line_width(1)
        for hx, hy in self._handles().values():
            cr.rectangle(hx - HANDLE / 2, hy - HANDLE / 2, HANDLE, HANDLE)
            cr.set_source_rgb(1, 1, 1)
            cr.fill_preserve()
            cr.set_source_rgb(0.11, 0.65, 0.98)
            cr.stroke()

    def _draw_badge(self, cr, x, y, text):
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(13)
        extents = cr.text_extents(text)
        pad = 6
        bw = extents.width + pad * 2
        bh = extents.height + pad
        bx = x
        by = y - bh - 4
        if by < 0:
            by = y + 4
        cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
        cr.rectangle(bx, by, bw, bh)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(bx + pad, by + bh - pad / 1.5)
        cr.show_text(text)

    def _draw_hint(self, cr, text):
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(15)
        extents = cr.text_extents(text)
        x = (self.base.width - extents.width) / 2
        y = 60
        cr.set_source_rgba(0, 0, 0, 0.6)
        cr.rectangle(x - 16, y - extents.height - 10, extents.width + 32, extents.height + 22)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        cr.show_text(text)


def select_region(base_image, on_done, on_cancel=None, detect_windows=True):
    """Crea y muestra el selector de region."""
    return RegionSelector(base_image, on_done, on_cancel, detect_windows)
