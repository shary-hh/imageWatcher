"""Aplicacion principal: barra de captura, bandeja y orquestacion."""
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from . import __app_id__, __app_name__, __version__, capture, ui
from .config import Config
from .editor import EditorWindow
from .hotkeys import HotkeyManager
from .recorder import open_recorder
from .region import RegionSelector, ask_fixed_size, extract_freehand
from .tools import color_picker, whiteboard
from .tools.overlay import OPEN_OVERLAY_MODES, DesktopOverlay

logger = logging.getLogger(__name__)


class CaptureBar(Gtk.Window):
    def __init__(self, app):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.app = app
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(False)
        self.set_resizable(False)
        self.set_title(__app_name__)

        outer = Gtk.EventBox()
        outer.get_style_context().add_class("imagewatcher-bar")
        self.add(outer)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
        box.set_margin_start(6)
        box.set_margin_end(6)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        outer.add(box)

        box.pack_start(self._brand(), False, False, 4)
        box.pack_start(self._separator(), False, False, 0)

        # Acciones principales, grandes y claras
        for label, kind, callback, tooltip in [
            ("Pantalla", "display", lambda *_: app.do_capture("fullscreen"),
             "Capturar toda la pantalla  (Ctrl+Alt+1)"),
            ("Ventana", "window", lambda *_: app.do_capture("window"),
             "Capturar la ventana activa  (Ctrl+Alt+3)"),
            ("Region", "region", lambda *_: app.do_capture("region"),
             "Seleccionar una region con el raton  (Ctrl+Alt+2)"),
            ("Grabar", "record", lambda *_: app.open_tool("recorder"),
             "Grabar video de la pantalla"),
        ]:
            box.pack_start(ui.glyph_tile(kind, label, tooltip, callback), False, False, 0)

        box.pack_start(self._separator(), False, False, 0)
        box.pack_start(self._more_button(), False, False, 0)

        box.pack_start(self._separator(), False, False, 0)
        box.pack_start(ui.button(icon_name="window-close", tooltip="Ocultar en la bandeja",
                                 on_click=lambda *_: self.hide()), False, False, 0)

        outer.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        outer.connect("button-press-event", self._on_press)
        self.connect("delete-event", lambda *args: (self.hide(), True)[1])

        self.show_all()
        self._place()

    def _brand(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_start(6)
        box.set_margin_end(8)
        image = ui.make_icon("applications-graphics", 26)
        if image is not None:
            box.pack_start(image, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        texts.set_valign(Gtk.Align.CENTER)
        name = Gtk.Label(label="imageWatcher", xalign=0)
        name.get_style_context().add_class("brand")
        sub = Gtk.Label(label="Captura y edicion", xalign=0)
        sub.get_style_context().add_class("brand-sub")
        texts.pack_start(name, False, False, 0)
        texts.pack_start(sub, False, False, 0)
        box.pack_start(texts, False, False, 0)
        return box

    def _separator(self):
        return Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)

    def _more_button(self):
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        image = ui.glyph_image("more", 22)
        if image is not None:
            content.pack_start(image, False, False, 0)
        caption = Gtk.Label(label="Mas")
        caption.get_style_context().add_class("tile-label")
        content.pack_start(caption, False, False, 0)
        button = Gtk.MenuButton()
        button.add(content)
        button.set_tooltip_text("Mas acciones")

        menu = Gtk.Menu()
        items = [
            ("Editor de imagenes", "pen", lambda *_: self.app.open_editor_blank()),
            ("Herramientas de diseno", "color", lambda *_: self.app.open_tools_menu()),
            ("sep", None, None),
            ("Repetir ultima captura", "undo", lambda *_: self.app.do_capture("repeat")),
            ("Region fija", "region", lambda *_: self.app.do_capture("fixed")),
            ("Captura freehand", "pen", lambda *_: self.app.do_capture("freehand")),
            ("Ventana con desplazamiento", "window", lambda *_: self.app.do_capture("scrolling")),
            ("Captura con retardo", "clock", lambda *_: self.app.do_capture("delayed")),
            ("sep", None, None),
            ("Preferencias", "settings", lambda *_: self.app.open_preferences()),
        ]
        for label, kind, callback in items:
            if label == "sep":
                menu.append(Gtk.SeparatorMenuItem())
                continue
            menu.append(ui.menu_item(label, kind, callback))
        menu.show_all()
        button.set_popup(menu)
        return button

    def _place(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        width = self.get_preferred_width()[1]
        self.move(geom.x + max(0, (geom.width - width) // 2), geom.y + 12)

    def _on_press(self, _widget, event):
        if event.button == 3:
            self.app.open_tools_menu()
            return True
        if event.button == 1:
            try:
                self.begin_move_drag(event.button, int(event.x_root), int(event.y_root), event.time)
            except Exception:
                pass
            return False
        return False


class Application:
    def __init__(self):
        ui.install_theme()
        ui.set_app_identity()
        self.config = Config()
        self.hotkeys = HotkeyManager()
        self.editors = []
        self.tool_windows = {}
        self._overlays = {}
        self._last_color = None
        self._escape_grabber = HotkeyManager()
        self._escape_active = False
        self.last_capture = None
        self.notifier = shutil_which("notify-send")
        self.bar = CaptureBar(self)
        self._tray = None
        self._build_tray()
        self._start_hotkeys()

    # -------------------------------------------------------------- tray
    def _build_tray(self):
        self._indicator = None
        self._tray = None
        if self._build_indicator():
            return
        self._build_status_icon()

    def _build_indicator(self):
        try:
            gi.require_version("AyatanaAppIndicator3", "0.1")
            from gi.repository import AyatanaAppIndicator3 as AppIndicator
        except Exception:
            return False
        try:
            indicator = AppIndicator.Indicator.new(
                __app_id__,
                "accessories-screenshot",
                AppIndicator.IndicatorCategory.APPLICATION_STATUS,
            )
            indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
            indicator.set_title(__app_name__)
            self._tray_menu = self._build_menu()
            indicator.set_menu(self._tray_menu)
            self._indicator = indicator
            return True
        except Exception:
            self._indicator = None
            return False

    def _build_status_icon(self):
        try:
            icon = Gtk.StatusIcon()
            icon.set_from_icon_name("accessories-screenshot")
            icon.set_tooltip_text(f"{__app_name__} {__version__}")
            icon.connect("activate", lambda *_: self.bar.present())
            icon.connect("popup-menu", self._show_tray_menu)
            self._tray = icon
        except Exception:
            self._tray = None

    def _show_tray_menu(self, icon, button, activate_time):
        menu = self._build_menu()
        menu.popup(
            None,
            None,
            Gtk.StatusIcon.position_menu,
            icon,
            button,
            activate_time,
        )

    def _build_menu(self):
        menu = Gtk.Menu()
        entries = [
            ("Mostrar barra de captura", lambda *_: self.bar.present()),
            ("sep", None),
            ("Capturar pantalla completa", lambda *_: self.do_capture("fullscreen")),
            ("Capturar ventana activa", lambda *_: self.do_capture("window")),
            ("Capturar ventana con desplazamiento", lambda *_: self.do_capture("scrolling")),
            ("Capturar region", lambda *_: self.do_capture("region")),
            ("Capturar region fija", lambda *_: self.do_capture("fixed")),
            ("Captura freehand", lambda *_: self.do_capture("freehand")),
            ("Repetir ultima captura", lambda *_: self.do_capture("repeat")),
            ("Captura con retardo", lambda *_: self.do_capture("delayed")),
            ("sep", None),
            ("Editor de imagenes", lambda *_: self.open_editor_blank()),
            ("Grabador de pantalla", lambda *_: self.open_tool("recorder")),
            ("sep", None),
        ]
        for label, callback in entries:
            if label == "sep":
                menu.append(Gtk.SeparatorMenuItem())
                continue
            item = Gtk.MenuItem(label=label)
            item.connect("activate", callback)
            menu.append(item)
        tools = Gtk.MenuItem(label="Herramientas de diseno")
        submenu = Gtk.Menu()
        for label, callback in [
            ("Selector de color", lambda *_: self.open_tool("color")),
            ("Lupa", lambda *_: self.open_tool("magnifier")),
            ("Regla de pixeles", lambda *_: self.open_tool("ruler")),
            ("Punto de mira", lambda *_: self.open_tool("crosshair")),
            ("Transportador", lambda *_: self.open_tool("protractor")),
            ("Pizarra", lambda *_: self.open_tool("whiteboard")),
        ]:
            sub = Gtk.MenuItem(label=label)
            sub.connect("activate", callback)
            submenu.append(sub)
        tools.set_submenu(submenu)
        menu.append(tools)
        menu.append(self._color_history_menu())
        menu.append(self._color_format_menu())
        hide_overlays = Gtk.MenuItem(label="Ocultar superposiciones")
        hide_overlays.connect("activate", lambda *_: self._hide_overlays())
        menu.append(hide_overlays)
        menu.append(Gtk.SeparatorMenuItem())
        prefs = Gtk.MenuItem(label="Preferencias...")
        prefs.connect("activate", lambda *_: self.open_preferences())
        menu.append(prefs)
        about = Gtk.MenuItem(label="Acerca de")
        about.connect("activate", lambda *_: self._about())
        menu.append(about)
        menu.append(Gtk.SeparatorMenuItem())
        quit_item = Gtk.MenuItem(label="Salir")
        quit_item.connect("activate", lambda *_: self.quit())
        menu.append(quit_item)
        menu.show_all()
        return menu

    # -------------------------------------------------------------- hotkeys
    def _start_hotkeys(self):
        self.hotkeys.set_callbacks(
            {
                "fullscreen": lambda: self.do_capture("fullscreen"),
                "window": lambda: self.do_capture("window"),
                "region": lambda: self.do_capture("region"),
                "fixed": lambda: self.do_capture("fixed"),
                "freehand": lambda: self.do_capture("freehand"),
                "repeat": lambda: self.do_capture("repeat"),
            }
        )
        if self.config.get("hotkeys_enabled", True):
            self.hotkeys.start(self.config.get("hotkeys", {}))
            for failure in self.hotkeys.failures:
                logger.warning("%s", failure)

    # -------------------------------------------------------------- capture
    def _set_bar_visible(self, visible):
        if visible:
            self.bar.show_all()
            self.bar.present()
        else:
            self.bar.hide()

    def do_capture(self, mode):
        self._set_bar_visible(False)
        GLib.timeout_add(220, self._dispatch_capture, mode)

    def _dispatch_capture(self, mode):
        if mode == "delayed":
            delay = max(1, int(self.config.get("delay_seconds", 3)))
            self._notify("imageWatcher", f"Captura en {delay} segundos...")
            GLib.timeout_add_seconds(delay, self._do_capture, "fullscreen")
            return False
        if mode == "repeat" and self.last_capture:
            self._do_capture(
                self.last_capture["mode"],
                self.last_capture.get("rect"),
                self.last_capture.get("points"),
            )
            return False
        self._do_capture(mode)
        return False

    def _do_capture(self, mode, rect=None, points=None):
        try:
            if mode == "freehand" and points:
                image = extract_freehand(capture.capture_screen(), points)
                if image is None:
                    self._notify("Captura freehand", "El trazo era demasiado pequeno")
                    self._set_bar_visible(True)
                    return False
                self.last_capture = {"mode": "freehand", "rect": rect, "points": list(points)}
                self._finish_capture(image)
                return False
            if mode == "region" and rect is None:
                base = capture.capture_screen()
                selector = RegionSelector(base, self._finish_capture, on_cancel=self._on_capture_cancelled)

                original_accept = selector._finish_accept

                def accept(r):
                    self.last_capture = {"mode": "region", "rect": r}
                    original_accept(r)

                selector._finish_accept = accept
                return False
            if mode == "fixed" and rect is None:
                parent = self.bar if self.bar.get_visible() else None
                size = ask_fixed_size(parent, tuple(self.config.get("fixed_region_size", (360, 360))))
                if not size:
                    self._on_capture_cancelled()
                    return False
                self.config["fixed_region_size"] = list(size)
                self.config.save()
                base = capture.capture_screen()
                selector = RegionSelector(
                    base, self._finish_capture,
                    on_cancel=self._on_capture_cancelled,
                    fixed_size=size,
                )

                original_accept = selector._finish_accept

                def accept(r):
                    self.last_capture = {"mode": "fixed", "rect": r}
                    original_accept(r)

                selector._finish_accept = accept
                return False
            if mode == "freehand" and points is None:
                base = capture.capture_screen()
                selector = RegionSelector(
                    base, self._finish_capture,
                    on_cancel=self._on_capture_cancelled,
                    freehand=True,
                )

                original_freehand = selector._finish_freehand

                def finish_freehand():
                    pts = list(selector._freehand_points)
                    bbox = selector._points_bbox(pts)
                    if len(pts) >= 3 and bbox:
                        self.last_capture = {"mode": "freehand", "rect": bbox, "points": pts}
                    original_freehand()

                selector._finish_freehand = finish_freehand
                return False
            if mode == "window":
                image = capture.capture_window(include_cursor=self.config.get("capture_cursor", False))
                self.last_capture = {"mode": "window"}
            elif mode == "scrolling":
                image = capture.capture_scrolling_window()
                self.last_capture = {"mode": "scrolling"}
            elif mode == "monitor":
                image = capture.capture_monitor(0)
                self.last_capture = {"mode": "monitor"}
            elif mode in ("region", "fixed") and rect:
                base = capture.capture_screen()
                image = base.crop((rect[0], rect[1], rect[0] + rect[2], rect[1] + rect[3]))
            else:
                image = capture.capture_screen()
                self.last_capture = {"mode": "fullscreen"}
            self._finish_capture(image)
        except Exception as exc:
            self._notify("Error de captura", str(exc))
            self._set_bar_visible(True)
        return False

    def _on_capture_cancelled(self):
        self._set_bar_visible(True)

    def _finish_capture(self, image):
        if self.config.get("copy_to_clipboard", True):
            try:
                capture.copy_image_to_clipboard(image)
            except Exception:
                pass
        path = None
        if self.config.get("auto_save", False):
            try:
                path = self._auto_save(image)
            except Exception:
                path = None
        if self.config.get("open_editor", True):
            self._open_editor(image)
            self._set_bar_visible(True)
        else:
            if path:
                self._notify("Captura guardada", os.path.basename(path))
            else:
                self._notify("Captura", "Imagen copiada al portapapeles")
            self._set_bar_visible(True)

    def _auto_save(self, image):
        directory = self.config.ensure_save_dir()
        fmt = self.config.get("save_format", "png")
        filename = time.strftime("captura_%Y%m%d_%H%M%S") + f".{fmt}"
        path = os.path.join(str(directory), filename)
        if fmt in ("jpg", "jpeg"):
            from PIL import Image

            background = Image.new("RGB", image.size, (255, 255, 255))
            background.paste(image, mask=image.getchannel("A"))
            background.save(path, quality=self.config.get("jpeg_quality", 90))
        else:
            image.save(path)
        return path

    # -------------------------------------------------------------- editor
    def _open_editor(self, image):
        editor = EditorWindow(image, self.config, capture_callback=lambda: self.do_capture("region"))
        editor.connect("destroy", lambda *_: self._forget_editor(editor))
        self.editors.append(editor)
        editor.present()

    def _forget_editor(self, editor):
        if editor in self.editors:
            self.editors.remove(editor)

    def open_editor_blank(self):
        from PIL import Image

        self._open_editor(Image.new("RGBA", (1000, 650), (255, 255, 255, 255)))

    # -------------------------------------------------------------- tools
    def open_tool(self, name):
        if name == "recorder":
            existing = self.tool_windows.get("recorder")
            if existing is not None:
                try:
                    if existing.get_visible():
                        existing.present()
                        return existing
                except Exception:
                    pass
            window = open_recorder(self.config)
            window.connect("destroy", lambda *_: self.tool_windows.pop("recorder", None))
            self.tool_windows["recorder"] = window
            return window
        if name in ("color", "palette"):
            return color_picker.open_color_picker(
                on_pick=self._remember_color,
                color_format=self.config.get("color_format", "hex"),
                history=self.config.get("color_history", []),
            )
        if name == "whiteboard":
            return whiteboard.open_whiteboard(self.config)
        if name in OPEN_OVERLAY_MODES:
            return self._toggle_overlay(name)
        return None

    # -------------------------------------------------------- overlays (mouse)
    def _toggle_overlay(self, mode):
        overlay = self._overlays.get(mode)
        if overlay is not None and overlay.get_visible():
            overlay.hide()
            overlay.stop()
            self._sync_escape_grab()
            return overlay
        for other, widget in self._overlays.items():
            if other != mode and widget.get_visible():
                widget.hide()
                widget.stop()
        if overlay is None:
            overlay = DesktopOverlay(mode)
            overlay.connect("hide", lambda *_: self._sync_escape_grab())
            self._overlays[mode] = overlay
        else:
            overlay.set_mode(mode)
            overlay.show_all()
            overlay._make_click_through()
            overlay.start()
        self._sync_escape_grab()
        return overlay

    def _hide_overlays(self):
        for widget in self._overlays.values():
            if widget.get_visible():
                widget.hide()
            widget.stop()
        self._sync_escape_grab()

    def _sync_escape_grab(self):
        """Graba Escape mientras haya superposiciones para cerrarlas."""
        any_visible = any(w.get_visible() for w in self._overlays.values())
        if any_visible and not self._escape_active:
            self._escape_grabber.set_callbacks({"escape": self._hide_overlays})
            self._escape_grabber.start({"escape": "Escape"})
            self._escape_active = True
        elif not any_visible and self._escape_active:
            self._escape_grabber.stop()
            self._escape_active = False

    def open_tools_menu(self):
        """Muestra el menu de herramientas en la posicion del mouse."""
        menu = Gtk.Menu()
        entries = [
            ("Selector de color (lupa)", "color", lambda: self.open_tool("color")),
            ("Lupa", "zoom-in", lambda: self.open_tool("magnifier")),
            ("Regla de pixeles", "ruler", lambda: self.open_tool("ruler")),
            ("Punto de mira", "crosshair", lambda: self.open_tool("crosshair")),
            ("Transportador", "protractor", lambda: self.open_tool("protractor")),
            ("Pizarra", "pen", lambda: self.open_tool("whiteboard")),
        ]
        for label, kind, callback in entries:
            menu.append(ui.menu_item(label, kind, lambda *_, cb=callback: cb()))

        menu.append(self._color_history_menu())
        menu.append(self._color_format_menu())

        menu.append(Gtk.SeparatorMenuItem())
        hide_item = Gtk.MenuItem(label="Ocultar superposiciones")
        hide_item.connect("activate", lambda *_: self._hide_overlays())
        menu.append(hide_item)
        menu.show_all()
        try:
            _, x, y = Gdk.Display.get_default().get_default_seat().get_pointer().get_position()
            menu.popup(
                None, None,
                lambda *args: (int(x), int(y), True),
                None, 0, Gtk.get_current_event_time(),
            )
        except Exception:
            menu.popup_at_pointer(None)
        return menu

    def _color_format_menu(self):
        item = Gtk.MenuItem(label="Formato de color")
        submenu = Gtk.Menu()
        current = str(self.config.get("color_format", "hex")).lower()
        group = None
        for fmt in ("hex", "rgb", "hsl", "hsv", "html", "c++", "delphi"):
            radio = Gtk.RadioMenuItem(label=fmt.upper())
            if group is None:
                group = radio
            else:
                radio.join_group(group)
            if fmt == current:
                radio.set_active(True)
            radio.connect("toggled", self._on_color_format, fmt)
            submenu.append(radio)
        item.set_submenu(submenu)
        return item

    def _on_color_format(self, widget, fmt):
        if widget.get_active():
            self.config["color_format"] = fmt
            self.config.save()
            if self._last_color is not None:
                value = color_picker.format_color(self._last_color, fmt)
                clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                clipboard.set_text(value, -1)
                clipboard.store()
                logger.info("Color recopiado en formato %s: %s", fmt.upper(), value)
            self._refresh_tray_menu()

    def _remember_color(self, rgb):
        self._last_color = rgb
        hexv = color_picker.format_color(rgb, "hex")
        history = [hexv] + [h for h in self.config.get("color_history", []) if h != hexv]
        self.config["color_history"] = history[:16]
        self.config.save()
        self._refresh_tray_menu()

    def _refresh_tray_menu(self):
        """Reconstruye el menu de la bandeja (historial/formato al dia)."""
        if self._indicator is not None:
            try:
                self._tray_menu = self._build_menu()
                self._indicator.set_menu(self._tray_menu)
            except Exception:
                pass

    def _swatch_pixbuf(self, hexv, size=16):
        from gi.repository import GdkPixbuf

        r, g, b = color_picker._hex_to_rgb(hexv) or (0, 0, 0)
        data = bytes([r, g, b]) * (size * size)
        pixbuf = GdkPixbuf.Pixbuf.new_from_data(
            data, GdkPixbuf.Colorspace.RGB, False, 8, size, size, size * 3
        )
        return pixbuf.copy()

    def _copy_color_hex(self, hexv):
        rgb = color_picker._hex_to_rgb(hexv)
        if rgb is None:
            return
        value = color_picker.format_color(rgb, self.config.get("color_format", "hex"))
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(value, -1)
        clipboard.store()
        self._last_color = rgb
        logger.info("Color del historial copiado: %s", value)

    def _clear_color_history(self):
        self.config["color_history"] = []
        self.config.save()
        self._refresh_tray_menu()

    def _color_history_menu(self):
        item = Gtk.MenuItem(label="Historial de colores")
        submenu = Gtk.Menu()
        history = self.config.get("color_history", [])
        if not history:
            empty = Gtk.MenuItem(label="(vacio)")
            empty.set_sensitive(False)
            submenu.append(empty)
        else:
            for hexv in history:
                entry = Gtk.MenuItem()
                row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
                row.pack_start(Gtk.Image.new_from_pixbuf(self._swatch_pixbuf(hexv)), False, False, 0)
                row.pack_start(Gtk.Label(label=hexv, xalign=0), False, False, 0)
                entry.add(row)
                entry.connect("activate", lambda *_, h=hexv: self._copy_color_hex(h))
                submenu.append(entry)
            submenu.append(Gtk.SeparatorMenuItem())
            clear = Gtk.MenuItem(label="Limpiar historial")
            clear.connect("activate", lambda *_: self._clear_color_history())
            submenu.append(clear)
        item.set_submenu(submenu)
        return item

    # -------------------------------------------------------------- prefs
    def open_preferences(self):
        PreferencesDialog(self)

    def apply_hotkeys(self):
        self.hotkeys.stop()
        self._start_hotkeys()

    # -------------------------------------------------------------- utils
    def _notify(self, title, body):
        if self.notifier:
            try:
                subprocess.Popen([self.notifier, title, body])
                return
            except Exception:
                pass
        print(f"[{title}] {body}")

    def _about(self):
        dialog = Gtk.AboutDialog()
        dialog.set_program_name(__app_name__)
        dialog.set_version(__version__)
        dialog.set_comments("Clon libre inspirado en PicPick para Linux Mint.")
        dialog.run()
        dialog.destroy()

    def quit(self):
        self.config.save()
        self.hotkeys.stop()
        self._escape_grabber.stop()
        Gtk.main_quit()


def shutil_which(name):
    from shutil import which

    return which(name)


class PreferencesDialog(Gtk.Dialog):
    def __init__(self, app):
        super().__init__(title="Preferencias", transient_for=app.bar, modal=True)
        ui.apply_dark(self)
        self.app = app
        self.config = app.config
        self.set_default_size(520, 460)
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Guardar", Gtk.ResponseType.OK)

        notebook = Gtk.Notebook()
        self.get_content_area().add(notebook)

        notebook.append_page(self._general_page(), Gtk.Label(label="General"))
        notebook.append_page(self._save_page(), Gtk.Label(label="Guardado"))
        notebook.append_page(self._hotkeys_page(), Gtk.Label(label="Atajos"))
        notebook.append_page(self._record_page(), Gtk.Label(label="Grabacion"))

        self.show_all()
        if self.run() == Gtk.ResponseType.OK:
            self._apply()
        self.destroy()

    def _general_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_border_width(8)

        self.open_editor_check = Gtk.CheckButton(label="Abrir el editor tras capturar")
        self.open_editor_check.set_active(self.config.get("open_editor", True))
        box.pack_start(self.open_editor_check, False, False, 0)

        self.clipboard_check = Gtk.CheckButton(label="Copiar siempre al portapapeles")
        self.clipboard_check.set_active(self.config.get("copy_to_clipboard", True))
        box.pack_start(self.clipboard_check, False, False, 0)

        self.cursor_check = Gtk.CheckButton(label="Incluir el cursor del raton")
        self.cursor_check.set_active(self.config.get("capture_cursor", False))
        box.pack_start(self.cursor_check, False, False, 0)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Label(label="Segundos de retardo:"), False, False, 0)
        adj = Gtk.Adjustment(value=self.config.get("delay_seconds", 3), lower=1, upper=60, step_increment=1)
        self.delay_spin = Gtk.SpinButton(adjustment=adj)
        row.pack_start(self.delay_spin, False, False, 0)
        box.pack_start(row, False, False, 0)

        fixed_size = self.config.get("fixed_region_size", [360, 360])
        fixed_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fixed_row.pack_start(Gtk.Label(label="Region fija (ancho x alto):"), False, False, 0)
        self.fixed_width_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.fixed_width_spin.set_value(max(1, int(fixed_size[0])))
        fixed_row.pack_start(self.fixed_width_spin, False, False, 0)
        fixed_row.pack_start(Gtk.Label(label="x"), False, False, 0)
        self.fixed_height_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.fixed_height_spin.set_value(max(1, int(fixed_size[1])))
        fixed_row.pack_start(self.fixed_height_spin, False, False, 0)
        box.pack_start(fixed_row, False, False, 0)

        self.autostart_check = Gtk.CheckButton(label="Iniciar al entrar en sesion")
        self.autostart_check.set_active(self._autostart_enabled())
        box.pack_start(self.autostart_check, False, False, 0)
        return box

    def _save_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_border_width(8)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.dir_button = Gtk.FileChooserButton(title="Carpeta de guardado", action=Gtk.FileChooserAction.SELECT_FOLDER)
        current = Path(self.config.get("save_dir")).expanduser()
        current.mkdir(parents=True, exist_ok=True)
        self.dir_button.set_filename(str(current))
        row.pack_start(Gtk.Label(label="Carpeta:"), False, False, 0)
        row.pack_start(self.dir_button, True, True, 0)
        box.pack_start(row, False, False, 0)

        fmt_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fmt_row.pack_start(Gtk.Label(label="Formato:"), False, False, 0)
        self.format_combo = Gtk.ComboBoxText()
        for fmt in ("png", "jpg", "bmp", "gif", "pdf"):
            self.format_combo.append_text(fmt)
        self.format_combo.set_active(["png", "jpg", "bmp", "gif", "pdf"].index(self.config.get("save_format", "png")) if self.config.get("save_format", "png") in ("png", "jpg", "bmp", "gif", "pdf") else 0)
        fmt_row.pack_start(self.format_combo, False, False, 0)
        fmt_row.pack_start(Gtk.Label(label="Calidad JPG:"), False, False, 8)
        adj = Gtk.Adjustment(value=self.config.get("jpeg_quality", 90), lower=1, upper=100, step_increment=1)
        self.quality_spin = Gtk.SpinButton(adjustment=adj)
        fmt_row.pack_start(self.quality_spin, False, False, 0)
        box.pack_start(fmt_row, False, False, 0)

        self.autosave_check = Gtk.CheckButton(label="Guardar automaticamente al capturar")
        self.autosave_check.set_active(self.config.get("auto_save", False))
        box.pack_start(self.autosave_check, False, False, 0)
        return box

    def _hotkeys_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_border_width(8)

        self.hotkeys_check = Gtk.CheckButton(label="Activar atajos globales")
        self.hotkeys_check.set_active(self.config.get("hotkeys_enabled", True))
        box.pack_start(self.hotkeys_check, False, False, 0)

        box.pack_start(
            Gtk.Label(
                label=(
                    "Formato: modificadores + tecla, p.ej. 'Ctrl+Alt+1' o 'Print'.\n"
                    "Si un atajo falla, desactiva el que use Cinnamon en Preferencias del sistema."
                ),
                xalign=0,
            ),
            False,
            False,
            0,
        )

        self.hotkey_entries = {}
        labels = {
            "fullscreen": "Pantalla completa",
            "window": "Ventana activa",
            "region": "Region",
            "fixed": "Region fija",
            "freehand": "Freehand",
            "repeat": "Repetir ultima",
        }
        grid = Gtk.Grid(column_spacing=10, row_spacing=6)
        for row, (key, label) in enumerate(labels.items()):
            grid.attach(Gtk.Label(label=label + ":", xalign=0), 0, row, 1, 1)
            entry = Gtk.Entry()
            entry.set_text(self.config.get("hotkeys", {}).get(key, ""))
            grid.attach(entry, 1, row, 1, 1)
            self.hotkey_entries[key] = entry
        box.pack_start(grid, False, False, 0)
        return box

    def _record_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_start(12)
        box.set_margin_end(12)
        box.set_margin_top(12)
        box.set_border_width(8)
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.pack_start(Gtk.Label(label="FPS de grabacion:"), False, False, 0)
        adj = Gtk.Adjustment(value=self.config.get("record_fps", 25), lower=5, upper=60, step_increment=1)
        self.fps_spin = Gtk.SpinButton(adjustment=adj)
        row.pack_start(self.fps_spin, False, False, 0)
        box.pack_start(row, False, False, 0)
        self.audio_check = Gtk.CheckButton(label="Grabar audio del sistema")
        self.audio_check.set_active(self.config.get("record_audio", False))
        box.pack_start(self.audio_check, False, False, 0)
        return box

    def _apply(self):
        self.config["open_editor"] = self.open_editor_check.get_active()
        self.config["copy_to_clipboard"] = self.clipboard_check.get_active()
        self.config["capture_cursor"] = self.cursor_check.get_active()
        self.config["delay_seconds"] = int(self.delay_spin.get_value())
        self.config["fixed_region_size"] = [
            int(self.fixed_width_spin.get_value()),
            int(self.fixed_height_spin.get_value()),
        ]
        self.config["save_dir"] = self.dir_button.get_filename()
        self.config["save_format"] = self.format_combo.get_active_text() or "png"
        self.config["jpeg_quality"] = int(self.quality_spin.get_value())
        self.config["auto_save"] = self.autosave_check.get_active()
        self.config["hotkeys_enabled"] = self.hotkeys_check.get_active()
        for key, entry in self.hotkey_entries.items():
            self.config.data["hotkeys"][key] = entry.get_text().strip()
        self.config["record_fps"] = int(self.fps_spin.get_value())
        self.config["record_audio"] = self.audio_check.get_active()
        self.config.save()
        self._set_autostart(self.autostart_check.get_active())
        self.app.apply_hotkeys()

    def _autostart_path(self):
        return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / f"{__app_id__}.desktop"

    def _autostart_enabled(self):
        return self._autostart_path().exists()

    def _set_autostart(self, enabled):
        path = self._autostart_path()
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            project = Path(__file__).resolve().parent.parent
            path.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                f"Name={__app_name__}\n"
                f"Exec={sys.executable} -m imagewatcher\n"
                f"Path={project}\n"
                "X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
        elif path.exists():
            path.unlink()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if not os.environ.get("DISPLAY"):
        logger.error("Se requiere un servidor X11 (DISPLAY no definido).")
        return 1
    app = Application()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
