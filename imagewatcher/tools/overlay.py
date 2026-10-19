"""Overlay de escritorio: dibuja la herramienta sobre toda la pantalla.

Es una ventana *click-through* (los clics pasan al escritorio) y no roba el
foco, de modo que la herramienta se integra con el escritorio sin bloquearlo.
La gestiona el centro de herramientas segun la pestana activa.
"""
import math

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from .. import ui  # noqa: E402
from ..capture import capture_region, virtual_screen_size  # noqa: E402
from ..gtk_util import get_pointer_position  # noqa: E402

# Modos que se dibujan sobre el escritorio (overlay click-through).
OPEN_OVERLAY_MODES = ("magnifier", "ruler", "crosshair", "protractor")


def _enable_transparency(window):
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)
    window.set_app_paintable(True)


class DesktopOverlay(Gtk.Window):
    def __init__(self, mode="crosshair"):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        ui.install_theme()
        self.mode = mode
        # Mira, regla y transportador son interactivos (se usan con clics).
        self.interactive = mode in ("crosshair", "ruler", "protractor")
        self.anchor = None
        self.points = []
        self.dpi = 96
        self._flash = None
        self.pointer = get_pointer_position()
        self._mag = None
        self._mag_half = 10
        self._timer = None
        self._last_pos = None

        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(self.interactive)
        self.set_type_hint(
            Gdk.WindowTypeHint.NORMAL if self.interactive else Gdk.WindowTypeHint.NOTIFICATION
        )
        _enable_transparency(self)

        width, height = virtual_screen_size()
        self.set_default_size(width, height)
        self.move(0, 0)
        self.resize(width, height)

        self.area = Gtk.DrawingArea()
        self.area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("motion-notify-event", self._on_motion)
        self.add(self.area)
        self.connect("key-press-event", self._on_key)

        self.connect("map", lambda *_: self.start())
        self.connect("unmap", lambda *_: self.stop())
        self.show_all()
        if self.interactive:
            GLib.timeout_add(60, self._grab_focus)
        else:
            self.connect("realize", lambda *_: self._make_click_through())
            self._make_click_through()

    def _grab_focus(self):
        try:
            window = self.get_window()
            if window is not None:
                window.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "crosshair"))
                self.grab_focus()
        except Exception:
            pass
        return False

    def _make_click_through(self):
        try:
            import cairo

            window = self.get_window()
            if window is not None:
                window.input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def _on_motion(self, _widget, event):
        self.pointer = (int(event.x), int(event.y))
        self.area.queue_draw()
        return True

    def _on_press(self, _widget, event):
        if not self.interactive:
            return False
        self.pointer = (int(event.x), int(event.y))
        if event.button == 1:
            if self.mode == "crosshair":
                self._crosshair_click()
            elif self.mode == "ruler":
                self._ruler_click()
            elif self.mode == "protractor":
                self._protractor_click()
        elif event.button == 3:
            if self.anchor is not None or self.points:
                self.anchor = None
                self.points = []
            else:
                self.hide()
                self.stop()
        self.area.queue_draw()
        return True

    def _crosshair_click(self):
        if self.anchor is None:
            self.anchor = self.pointer
        else:
            self._copy_size()
            self.hide()
            self.stop()

    def _ruler_click(self):
        if not self.points:
            self.points = [self.pointer]        # origen
        else:
            self._copy_ruler()                   # cierra y copia
            self.hide()
            self.stop()

    def _protractor_click(self):
        if not self.points:
            self.points = [self.pointer]         # vertice
        elif len(self.points) == 1:
            self.points.append(self.pointer)     # primer brazo
        else:
            self._copy_protractor()              # cierra y copia
            self.hide()
            self.stop()

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            self.stop()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.mode == "ruler" and self.points:
                self._copy_ruler()
                self.hide()
                self.stop()
            elif self.mode == "protractor" and len(self.points) >= 2:
                self._copy_protractor()
                self.hide()
                self.stop()
            return True
        return False

    # ---- medidas
    def _ruler_metrics(self):
        if not self.points:
            return None
        x0, y0 = self.points[0]
        x1, y1 = self.pointer
        dx, dy = x1 - x0, y1 - y0
        distance = (dx * dx + dy * dy) ** 0.5
        return x0, y0, x1, y1, dx, dy, distance

    def _protractor_angle(self):
        if not self.points:
            return None
        vx, vy = self.points[0]
        px, py = self.pointer
        if len(self.points) >= 2:
            ax, ay = self.points[1]
            a1 = math.atan2(ay - vy, ax - vx)
            a2 = math.atan2(py - vy, px - vx)
            angle = abs(math.degrees(a1 - a2)) % 360
            if angle > 180:
                angle = 360 - angle
        else:
            angle = math.degrees(math.atan2(vy - py, px - vx)) % 360
        return angle

    def _copy_text(self, text, title):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        self._flash = f"{text}   (copiado)"
        GLib.timeout_add(1400, self._clear_flash)
        try:
            import subprocess
            from shutil import which

            notifier = which("notify-send")
            if notifier:
                subprocess.Popen([notifier, title, text])
        except Exception:
            pass

    def _copy_ruler(self):
        metrics = self._ruler_metrics()
        if not metrics:
            return None
        _x0, _y0, _x1, _y1, dx, dy, distance = metrics
        cm = distance / self.dpi * 2.54
        text = f"{distance:.0f} px  ({dx} x {dy})  {cm:.2f} cm"
        self._copy_text(text, "Distancia copiada")
        return text

    def _copy_protractor(self):
        angle = self._protractor_angle()
        if angle is None:
            return None
        text = f"{angle:.1f} grados"
        self._copy_text(text, "Angulo copiado")
        return text

    def _copy_size(self):
        if self.anchor is None:
            return None
        x0, y0 = self.anchor
        x1, y1 = self.pointer
        width = abs(x1 - x0)
        height = abs(y1 - y0)
        text = f"{width} x {height} px"
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text, -1)
        clipboard.store()
        self._flash = f"Ancho {width} px   Alto {height} px   (copiado)"
        GLib.timeout_add(1400, self._clear_flash)
        try:
            import subprocess
            from shutil import which

            notifier = which("notify-send")
            if notifier:
                subprocess.Popen(
                    [notifier, "Medidas copiadas (px)", f"Ancho {width} px   Alto {height} px"]
                )
        except Exception:
            pass
        return text

    def _clear_flash(self):
        self._flash = None
        self.area.queue_draw()
        return False

    def set_mode(self, mode):
        self.mode = mode
        self.area.queue_draw()

    def start(self):
        if self._timer is None:
            self._last_pos = None
            self._timer = GLib.timeout_add(40, self._tick)

    def stop(self):
        if self._timer is not None:
            GLib.source_remove(self._timer)
            self._timer = None

    def destroy(self):
        self.stop()
        super().destroy()

    def _tick(self):
        try:
            position = get_pointer_position()
            if position == self._last_pos:
                return self._timer is not None
            self._last_pos = position
            self.pointer = position
            if self.mode == "magnifier":
                px, py = position
                cells = self._mag_half * 2 + 1
                self._mag = capture_region(
                    px - self._mag_half, py - self._mag_half, cells, cells
                )
            self.area.queue_draw()
        except Exception:
            pass
        return self._timer is not None

    # -------------------------------------------------------------- dibujo
    def _on_draw(self, _widget, cr):
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        painter = {
            "crosshair": self._draw_crosshair,
            "ruler": self._draw_ruler,
            "protractor": self._draw_protractor,
            "magnifier": self._draw_magnifier,
        }.get(self.mode)
        if painter:
            painter(cr)
        return False

    def _coord_box(self, cr, x, y, text):
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(15)
        extents = cr.text_extents(text)
        cr.set_source_rgba(0, 0, 0, 0.78)
        cr.rectangle(x, y, extents.width + 20, extents.height + 14)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x + 10, y + extents.height + 6)
        cr.show_text(text)

    def _top_hint(self, cr, text):
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(14)
        extents = cr.text_extents(text)
        x = (self.get_allocated_width() - extents.width) / 2
        y = 30
        cr.set_source_rgba(0, 0, 0, 0.68)
        cr.rectangle(x - 14, y - extents.height - 8, extents.width + 28, extents.height + 18)
        cr.fill()
        cr.set_source_rgb(1, 1, 1)
        cr.move_to(x, y)
        cr.show_text(text)

    def _draw_crosshair(self, cr):
        width, height = self.get_allocated_width(), self.get_allocated_height()
        px, py = self.pointer
        cr.set_source_rgba(1, 0.15, 0.15, 0.7)
        cr.set_line_width(1)
        cr.move_to(0, py + 0.5)
        cr.line_to(width, py + 0.5)
        cr.move_to(px + 0.5, 0)
        cr.line_to(px + 0.5, height)
        cr.stroke()
        cr.arc(px, py, 22, 0, 6.2832)
        cr.stroke()

        if self.anchor is not None:
            ax, ay = self.anchor
            x0, x1 = sorted((ax, px))
            y0, y1 = sorted((ay, py))
            cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
            cr.set_line_width(2)
            cr.rectangle(x0 + 0.5, y0 + 0.5, x1 - x0, y1 - y0)
            cr.stroke()
            cr.arc(ax, ay, 5, 0, 6.2832)
            cr.fill()
            self._coord_box(cr, x0, max(0, y0 - 34), f"Ancho {x1 - x0} px   Alto {y1 - y0} px")

        self._coord_box(cr, 20, 20, f"X = {px}   Y = {py}")
        if self._flash:
            self._coord_box(cr, 20, 62, self._flash)
        else:
            self._coord_box(cr, 20, 62, "Clic: fijar esquina / copiar tamano   Esc: cerrar")

    def _draw_ruler(self, cr):
        metrics = self._ruler_metrics()
        if metrics is None:
            self._top_hint(cr, "Clic para fijar el origen de la medida")
            self._coord_box(cr, 20, 20, f"X = {self.pointer[0]}   Y = {self.pointer[1]}")
            return
        x0, y0, x1, y1, dx, dy, distance = metrics

        cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
        cr.set_line_width(2)
        cr.move_to(x0, y0)
        cr.line_to(x1, y1)
        cr.stroke()

        if distance > 1:
            ux, uy = dx / distance, dy / distance
            nx, ny = -uy, ux
            cr.set_line_width(1)
            for t in range(0, int(distance) + 1, 10):
                major = t % 100 == 0
                mid = t % 50 == 0
                tick = 12 if major else (8 if mid else 4)
                bx, by = x0 + ux * t, y0 + uy * t
                cr.move_to(bx - nx * tick, by - ny * tick)
                cr.line_to(bx + nx * tick, by + ny * tick)
                if major:
                    cr.move_to(bx + nx * tick + 3, by + ny * tick)
                    cr.show_text(str(t))
            cr.stroke()

        for ex, ey in ((x0, y0), (x1, y1)):
            cr.arc(ex, ey, 5, 0, 2 * math.pi)
            cr.fill()

        cm = distance / self.dpi * 2.54
        label = f"{distance:.0f} px   {cm:.2f} cm   (dx {dx}, dy {dy})"
        self._coord_box(cr, (x0 + x1) / 2 + 10, (y0 + y1) / 2 - 22, label)
        if self._flash:
            self._top_hint(cr, self._flash)
        else:
            self._top_hint(cr, "Clic: fijar destino y copiar      Esc: cerrar")

    def _draw_protractor(self, cr):
        if not self.points:
            self._top_hint(cr, "Clic para colocar el vertice del angulo")
            self._coord_box(cr, 20, 20, f"X = {self.pointer[0]}   Y = {self.pointer[1]}")
            return

        vx, vy = self.points[0]
        px, py = self.pointer
        radius = 160

        cr.set_source_rgba(0.10, 0.12, 0.16, 0.72)
        cr.arc(vx, vy, radius, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgb(0.9, 0.92, 0.97)
        cr.set_line_width(1.2)
        cr.arc(vx, vy, radius, 0, 2 * math.pi)
        cr.stroke()
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(11)
        for degree in range(0, 360, 5):
            a = math.radians(degree)
            inner = radius - (14 if degree % 10 == 0 else 7)
            cr.move_to(vx + inner * math.cos(a), vy - inner * math.sin(a))
            cr.line_to(vx + radius * math.cos(a), vy - radius * math.sin(a))
            if degree % 30 == 0:
                cr.move_to(vx + (radius - 30) * math.cos(a) - 8, vy - (radius - 30) * math.sin(a) + 4)
                cr.show_text(str(degree))
        cr.stroke()

        if len(self.points) >= 2:
            ax, ay = self.points[1]
            cr.set_source_rgba(1, 0.78, 0.2, 0.95)
            cr.set_line_width(2.5)
            cr.move_to(vx, vy)
            cr.line_to(ax, ay)
            cr.stroke()
            cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
            cr.set_line_width(2.5)
            cr.move_to(vx, vy)
            cr.line_to(px, py)
            cr.stroke()
            cr.set_source_rgb(1, 1, 1)
            cr.arc(ax, ay, 5, 0, 2 * math.pi)
            cr.fill()
            angle = self._protractor_angle()
            self._coord_box(cr, vx + 12, vy - radius - 40, f"{angle:.1f} grados")
            if self._flash:
                self._top_hint(cr, self._flash)
            else:
                self._top_hint(cr, "Clic: copiar el angulo      Esc: cerrar")
        else:
            cr.set_source_rgba(0.11, 0.65, 0.98, 0.95)
            cr.set_line_width(2.5)
            cr.move_to(vx, vy)
            cr.line_to(px, py)
            cr.stroke()
            angle = self._protractor_angle()
            self._coord_box(cr, vx + 12, vy - radius - 40, f"{angle:.1f} grados (referencia)")
            self._top_hint(cr, "Clic para fijar el primer brazo (referencia)")

        cr.set_source_rgb(1, 1, 1)
        cr.arc(vx, vy, 5, 0, 2 * math.pi)
        cr.fill()

    def _draw_magnifier(self, cr):
        cells = self._mag_half * 2 + 1
        half = self._mag_half
        scale = 9
        size = cells * scale
        pad = 10
        box = size + pad * 2
        px, py = self.pointer
        region = self._mag
        if region is None:
            region = Image.new("RGBA", (cells, cells), (30, 30, 30, 255))
        bx = px + 24
        by = py + 24
        if bx + box > self.get_allocated_width():
            bx = px - 24 - box
        if by + box > self.get_allocated_height():
            by = py - 24 - box
        bx = max(4, bx)
        by = max(4, by)
        cr.set_source_rgba(0, 0, 0, 0.4)
        cr.rectangle(bx + 3, by + 3, box, box)
        cr.fill()
        cr.set_source_rgba(0.11, 0.13, 0.17, 0.97)
        cr.rectangle(bx, by, box, box)
        cr.fill()
        for j in range(-half, half + 1):
            for i in range(-half, half + 1):
                sx = max(0, min(region.width - 1, i + half))
                sy = max(0, min(region.height - 1, j + half))
                r, g, b = region.getpixel((sx, sy))[:3]
                cr.set_source_rgb(r / 255, g / 255, b / 255)
                cr.rectangle(bx + pad + (i + half) * scale, by + pad + (j + half) * scale, scale, scale)
                cr.fill()
        cx = bx + pad + half * scale
        cy = by + pad + half * scale
        cr.set_source_rgba(0, 0, 0, 0.8)
        cr.set_line_width(2)
        cr.rectangle(cx - 1, cy - 1, scale + 2, scale + 2)
        cr.stroke()
        cr.set_source_rgb(1, 1, 1)
        cr.set_line_width(1)
        cr.rectangle(cx, cy, scale, scale)
        cr.stroke()
        r, g, b = region.getpixel((half, half))[:3]
        self._coord_box(cr, bx, by + box + 4, f"#{r:02X}{g:02X}{b:02X}   X={px} Y={py}")


def open_overlay(mode="crosshair"):
    """Crea el overlay de escritorio (uso puntual/tests)."""
    return DesktopOverlay(mode)
