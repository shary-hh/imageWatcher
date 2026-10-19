"""Pizarra: lienzo blanco para dibujar y anotar (panel embebible)."""
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

from .. import ui  # noqa: E402


class WhiteboardPanel(Gtk.Box):
    def __init__(self, config=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        ui.apply_dark(self)
        self.config = config
        self.color = (230, 30, 30, 255)
        self.width = 4
        self.eraser = False
        self.strokes = []
        self.current = None

        self.overlay = Gtk.Overlay()
        self.area = Gtk.DrawingArea()
        self.area.set_can_focus(True)
        self.area.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.area.connect("draw", self._on_draw)
        self.area.connect("button-press-event", self._on_press)
        self.area.connect("button-release-event", self._on_release)
        self.area.connect("motion-notify-event", self._on_motion)
        self.overlay.add(self.area)

        bar = self._build_toolbar()
        bar.set_halign(Gtk.Align.CENTER)
        bar.set_valign(Gtk.Align.START)
        bar.set_margin_top(8)
        self.overlay.add_overlay(bar)

        self.pack_start(self.overlay, True, True, 0)

    def start(self):
        self.area.grab_focus()

    def stop(self):
        pass

    def _build_toolbar(self):
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bar.get_style_context().add_class("pill")

        self.color_button = Gtk.ColorButton()
        rgba = Gdk.RGBA()
        rgba.red, rgba.green, rgba.blue, rgba.alpha = 0.9, 0.12, 0.12, 1.0
        self.color_button.set_rgba(rgba)
        self.color_button.set_tooltip_text("Color del trazo")
        self.color_button.connect("color-set", self._on_color)
        bar.pack_start(self.color_button, False, False, 0)

        width_adj = Gtk.Adjustment(value=self.width, lower=1, upper=40, step_increment=1)
        width_spin = Gtk.SpinButton(adjustment=width_adj)
        width_spin.set_tooltip_text("Grosor")
        width_spin.connect("value-changed", lambda s: setattr(self, "width", int(s.get_value())))
        bar.pack_start(width_spin, False, False, 0)

        self.eraser_btn = Gtk.ToggleButton()
        eraser_icon = ui.make_icon("edit-clear", 16)
        self.eraser_btn.add(eraser_icon if eraser_icon is not None else Gtk.Label(label="Borrador"))
        self.eraser_btn.set_tooltip_text("Borrador")
        self.eraser_btn.connect("toggled", lambda b: setattr(self, "eraser", b.get_active()))
        bar.pack_start(self.eraser_btn, False, False, 0)

        bar.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 2)
        bar.pack_start(ui.button(icon_name="user-trash", tooltip="Limpiar",
                                 on_click=lambda *_: self._clear()), False, False, 0)
        bar.pack_start(ui.button(icon_name="document-save", tooltip="Guardar como imagen",
                                 on_click=lambda *_: self._save()), False, False, 0)
        return bar

    def _on_color(self, button):
        rgba = button.get_rgba()
        self.color = (int(rgba.red * 255), int(rgba.green * 255), int(rgba.blue * 255), 255)
        self.eraser_btn.set_active(False)

    def _on_press(self, _widget, event):
        if event.button != 1:
            return False
        self.current = {
            "color": (255, 255, 255, 255) if self.eraser else self.color,
            "width": self.width * (3 if self.eraser else 1),
            "points": [(event.x, event.y)],
        }
        return True

    def _on_motion(self, _widget, event):
        if self.current:
            self.current["points"].append((event.x, event.y))
            self.area.queue_draw()
        return True

    def _on_release(self, _widget, event):
        if self.current and event.button == 1:
            self.strokes.append(self.current)
            self.current = None
            self.area.queue_draw()
        return True

    def _clear(self):
        self.strokes = []
        self.current = None
        self.area.queue_draw()

    def _on_draw(self, _widget, cr):
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        for stroke in self.strokes + ([self.current] if self.current else []):
            color = stroke["color"]
            cr.set_source_rgba(color[0] / 255, color[1] / 255, color[2] / 255, color[3] / 255)
            cr.set_line_width(stroke["width"])
            cr.set_line_cap(1)
            cr.set_line_join(1)
            points = stroke["points"]
            if len(points) == 1:
                points = points + [(points[0][0] + 0.1, points[0][1] + 0.1)]
            cr.move_to(*points[0])
            for point in points[1:]:
                cr.line_to(*point)
            cr.stroke()
        return False

    def _save(self):
        alloc = self.area.get_allocation()
        image = Image.new("RGB", (max(1, alloc.width), max(1, alloc.height)), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        for stroke in self.strokes:
            points = stroke["points"]
            if len(points) < 2:
                continue
            draw.line(points, fill=stroke["color"][:3], width=int(stroke["width"]), joint="curve")
        dialog = Gtk.FileChooserDialog(
            title="Guardar pizarra", transient_for=self.get_toplevel(),
            action=Gtk.FileChooserAction.SAVE,
        )
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Guardar", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name("pizarra.png")
        if self.config is not None:
            try:
                dialog.set_current_folder(str(self.config.ensure_save_dir()))
            except Exception:
                pass
        if dialog.run() == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            if not path.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
                path += ".png"
            try:
                image.save(path)
            except Exception:
                pass
        dialog.destroy()


class WhiteboardWindow(Gtk.Window):
    def __init__(self, config=None):
        super().__init__(title="Pizarra")
        ui.install_theme()
        ui.apply_dark(self)
        self.set_default_size(1000, 700)
        self.panel = WhiteboardPanel(config)
        self.add(self.panel)
        self.connect("key-press-event", self._on_key)
        self.show_all()
        self.present()
        self.fullscreen()
        self.panel.start()

    def _on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False


def open_whiteboard(config=None):
    return WhiteboardWindow(config)
