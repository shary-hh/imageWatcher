"""Grabador de pantalla: ffmpeg/x11grab en X11 y wf-recorder/GNOME en Wayland."""
import os
import re
import shutil
import signal
import subprocess
import threading
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

from . import capture, session, ui  # noqa: E402


def ffmpeg_path():
    return shutil.which("ffmpeg")


def has_encoder(name):
    try:
        out = subprocess.run([ffmpeg_path(), "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=10)
        return name in out.stdout
    except Exception:
        return False


def _detect_backend():
    if not capture.is_wayland():
        return "x11"
    if session.is_gnome():
        return "gnome"
    if session.is_kde():
        return None
    if shutil.which("wf-recorder"):
        return "wf-recorder"
    return None


GIF_MAX_FPS = 15
GIF_MAX_WIDTH = 960


def _ffmpeg_error(result):
    lines = (result.stderr or "").strip().splitlines()
    return lines[-1] if lines else f"ffmpeg termino con codigo {result.returncode}"


def video_to_gif(video_path, gif_path, fps=GIF_MAX_FPS):
    """Convierte un video a GIF con una paleta optimizada (dos pasadas)."""
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg no esta instalado")
    fps = max(1, min(int(fps), GIF_MAX_FPS))
    palette = gif_path + ".palette.png"
    filters = f"fps={fps},scale='min({GIF_MAX_WIDTH},iw)':-1:flags=lanczos"
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-i", video_path,
             "-vf", f"{filters},palettegen=stats_mode=diff", palette],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(_ffmpeg_error(result))
        result = subprocess.run(
            [ffmpeg, "-y", "-i", video_path, "-i", palette,
             "-lavfi",
             f"{filters}[x];[x][1:v]paletteuse=dither=sierra2_4a:diff_mode=rectangle",
             "-loop", "0", gif_path],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            try:
                os.remove(gif_path)
            except OSError:
                pass
            raise RuntimeError(_ffmpeg_error(result))
    finally:
        try:
            os.remove(palette)
        except OSError:
            pass


class CountdownOverlay(Gtk.Window):
    """Cuenta regresiva a pantalla completa, sin bloquear el escritorio."""

    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        ui.install_theme()
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_can_focus(False)
        self.set_type_hint(
            Gdk.WindowTypeHint.OVERLAY
            if hasattr(Gdk.WindowTypeHint, "OVERLAY")
            else Gdk.WindowTypeHint.DOCK
        )
        self.get_style_context().add_class("countdown-window")
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)
        self.set_app_paintable(True)

        overlay = Gtk.Overlay()
        background = Gtk.DrawingArea()
        background.connect("draw", self._draw_background)
        overlay.add(background)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        self.number = Gtk.Label(label="")
        self.number.get_style_context().add_class("countdown-number")
        content.pack_start(self.number, False, False, 0)
        hint = Gtk.Label(label="La grabacion comienza en breve")
        hint.get_style_context().add_class("countdown-hint")
        content.pack_start(hint, False, False, 0)
        overlay.add_overlay(content)
        self.add(overlay)

        width, height = capture.virtual_screen_size()
        self.set_default_size(width, height)
        self.move(0, 0)
        self.resize(width, height)
        self.connect("realize", lambda *_: self._click_through())
        self._click_through()
        self.show_all()
        if capture.is_wayland():
            try:
                self.fullscreen_on_monitor(
                    self.get_screen(), capture.region_monitor_index()
                )
            except Exception:
                self.fullscreen()
        else:
            # El gestor de ventanas es quien garantiza la pantalla completa.
            self.fullscreen()
        self.present()

    def _draw_background(self, _widget, cr):
        cr.set_source_rgba(0.02, 0.03, 0.05, 0.82)
        cr.paint()
        return False

    def _click_through(self):
        """Deja pasar los clics: el aviso es solo visual."""
        try:
            import cairo

            window = self.get_window()
            if window is not None:
                window.input_shape_combine_region(cairo.Region(), 0, 0)
        except Exception:
            pass

    def set_remaining(self, seconds):
        self.number.set_text(str(max(0, int(seconds))))


class RecorderWindow(Gtk.Window):
    def __init__(self, config, countdown_overlay=True):
        super().__init__(title="Grabador de pantalla")
        ui.install_theme()
        ui.apply_dark(self)
        self.config = config
        self.countdown_overlay_enabled = bool(countdown_overlay)
        self.process = None
        self.output_path = None
        self.region = None
        self.region_offset = (0, 0)
        self.region_geometry = None
        self.backend = _detect_backend()
        self._stop_signal = False
        self._gnome_screencast = False
        self._gnome_bus = None
        self.start_time = None
        self._timer = None
        self._countdown_timer = None
        self._countdown_remaining = 0
        self._countdown_overlay = None
        self._temp_path = None
        self._converting = False
        self._audio_available = False
        self.set_default_size(440, 300)
        subtitle = {
            "x11": "Video con ffmpeg",
            "wf-recorder": "Video con wf-recorder",
            "gnome": "Video con GNOME Shell",
        }.get(self.backend, "Grabacion no disponible")
        self.set_titlebar(ui.header("Grabador de pantalla", subtitle, "media-record"))

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_start(14)
        root.set_margin_end(14)
        root.set_margin_top(14)
        root.set_margin_bottom(14)
        self.add(root)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        root.pack_start(grid, False, False, 0)

        grid.attach(Gtk.Label(label="Area:", xalign=0), 0, 0, 1, 1)
        self.area_label = Gtk.Label(label="Pantalla completa", xalign=0)
        grid.attach(self.area_label, 1, 0, 1, 1)
        pick = Gtk.Button(label="Seleccionar region...")
        pick.connect("clicked", self._pick_region)
        grid.attach(pick, 2, 0, 1, 1)

        grid.attach(Gtk.Label(label="FPS:", xalign=0), 0, 1, 1, 1)
        fps_adj = Gtk.Adjustment(value=config.get("record_fps", 25), lower=5, upper=60, step_increment=1)
        self.fps_spin = Gtk.SpinButton(adjustment=fps_adj)
        grid.attach(self.fps_spin, 1, 1, 1, 1)

        grid.attach(Gtk.Label(label="Cuenta regresiva (s):", xalign=0), 0, 2, 1, 1)
        countdown_adj = Gtk.Adjustment(
            value=config.get("record_countdown", 3), lower=0, upper=30, step_increment=1
        )
        self.countdown_spin = Gtk.SpinButton(adjustment=countdown_adj)
        self.countdown_spin.set_tooltip_text(
            "Segundos de espera antes de empezar a grabar. 0 desactiva la cuenta."
        )
        self.countdown_spin.connect("value-changed", self._on_countdown_changed)
        grid.attach(self.countdown_spin, 1, 2, 1, 1)

        grid.attach(Gtk.Label(label="Formato:", xalign=0), 0, 3, 1, 1)
        self.format_combo = Gtk.ComboBoxText()
        self.format_combo.append("mp4", "MP4 (video)")
        self.format_combo.append("gif", "GIF (animacion)")
        active_format = config.get("record_format", "mp4")
        self.format_combo.set_active_id(
            active_format if active_format in ("mp4", "gif") else "mp4"
        )
        self.format_combo.set_tooltip_text(
            "GIF no incluye audio y se graba a un maximo de 15 FPS."
        )
        self.format_combo.connect("changed", self._on_format_changed)
        grid.attach(self.format_combo, 1, 3, 2, 1)

        grid.attach(Gtk.Label(label="Audio del sistema:", xalign=0), 0, 4, 1, 1)
        self.audio_check = Gtk.CheckButton()
        self.audio_check.set_active(config.get("record_audio", False))
        sink = capture.list_audio_sinks()
        self._audio_available = bool(sink) and self.backend in ("x11", "wf-recorder")
        grid.attach(self.audio_check, 1, 4, 1, 1)
        self._update_audio_state()

        self.timer_label = Gtk.Label(label="00:00")
        self.timer_label.set_xalign(0.5)
        self.timer_label.set_justify(Gtk.Justification.CENTER)
        self._set_timer_text("00:00")
        root.pack_start(self.timer_label, True, True, 4)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.start_btn = Gtk.Button(label="Iniciar grabacion")
        self.start_btn.set_tooltip_text("Iniciar grabacion (Ctrl+R)")
        self.start_btn.connect("clicked", lambda *_: self._start())
        buttons.pack_start(self.start_btn, True, True, 0)
        self.stop_btn = Gtk.Button(label="Detener")
        self.stop_btn.set_tooltip_text("Detener grabacion (Ctrl+R)")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda *_: self._stop())
        buttons.pack_start(self.stop_btn, True, True, 0)
        root.pack_start(buttons, False, False, 0)

        hotkey = (config.get("hotkeys") or {}).get("record_toggle", "")
        if hotkey:
            hint = Gtk.Label(
                label=f"Atajo global: {hotkey} para iniciar o detener",
                xalign=0,
            )
            hint.get_style_context().add_class("dim")
            root.pack_start(hint, False, False, 0)

        self.status = Gtk.Label(label="Listo", xalign=0)
        root.pack_start(self.status, False, False, 0)

        self.connect("destroy", lambda *_: self._stop())
        self.connect("key-press-event", self._on_key)
        self.show_all()

        if self.backend is None:
            self.start_btn.set_sensitive(False)
            if capture.is_wayland() and session.is_kde():
                self.status.set_text(
                    "KDE Wayland: la grabacion integrada no esta disponible."
                )
            elif capture.is_wayland():
                self.status.set_text(
                    "Wayland: instala wf-recorder (wlroots) o usa GNOME Shell."
                )
            else:
                self.status.set_text("No hay un backend de grabacion disponible.")
        elif self.backend == "x11" and not ffmpeg_path():
            self.start_btn.set_sensitive(False)
            self.status.set_text("ffmpeg no esta instalado (sudo apt install ffmpeg)")

    def _on_key(self, _widget, event):
        from gi.repository import Gdk

        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        if (
            event.keyval in (Gdk.KEY_r, Gdk.KEY_R)
            and event.state & Gdk.ModifierType.CONTROL_MASK
        ):
            self.toggle_recording()
            return True
        return False

    def _pick_region(self, *_):
        if capture.is_wayland():
            self._pick_region_wayland()
            return
        try:
            self.hide()
            base = capture.capture_screen()
        except Exception as exc:
            self.show()
            self.status.set_text(f"No se pudo capturar la pantalla: {exc}")
            return
        from .region import RegionSelector

        holder = {}

        def finished(image):
            self.region = image
            self.region_offset = holder.get("rect", (0, 0, image.width, image.height))[:2]
            self.area_label.set_text(f"Region {image.width}x{image.height}")
            self.show()

        selector = RegionSelector(base, finished, on_cancel=self.show, detect_windows=False)

        original_accept = selector._finish_accept

        def accept(rect):
            holder["rect"] = rect
            original_accept(rect)

        selector._finish_accept = accept

    def _pick_region_wayland(self):
        if self.backend is None:
            self.status.set_text("No hay un backend de grabacion disponible.")
            return
        if self.backend == "gnome":
            self.status.set_text(
                "GNOME Wayland solo permite grabar la pantalla completa desde aqui."
            )
            return
        if shutil.which("slurp"):
            self.hide()
            output = session.command_output(["slurp"], timeout=120)
            if not output:
                self.show()
                return
            match = re.search(r"(-?\d+),(-?\d+)\s+(\d+)x(\d+)", output.strip())
            if match is None:
                self.show()
                self.status.set_text("No se pudo interpretar la region de slurp.")
                return
            x, y, width, height = (int(value) for value in match.groups())
            self.region_geometry = (x, y, width, height)
            self.area_label.set_text(f"Region {width}x{height}")
            self.show()
            return

        try:
            self.hide()
            base = capture.capture_screen()
        except Exception as exc:
            self.show()
            self.status.set_text(f"No se pudo capturar la pantalla: {exc}")
            return
        from .region import RegionSelector

        holder = {}

        def finished(image):
            self.region = image
            rect = holder.get("rect")
            if rect:
                self.region_geometry = capture.image_to_logical_box(rect, base)
            else:
                self.region_geometry = capture.image_to_logical_box(
                    (0, 0, base.width, base.height), base
                )
            self.area_label.set_text(f"Region {image.width}x{image.height}")
            self.show()

        selector = RegionSelector(
            base,
            finished,
            on_cancel=self.show,
            detect_windows=False,
            preview_size=capture.region_preview_size(),
        )
        original_accept = selector._finish_accept

        def accept(rect):
            holder["rect"] = selector.rect_to_source(rect)
            original_accept(rect)

        selector._finish_accept = accept

    def _output_path(self, extension=".mp4"):
        directory = self.config.ensure_save_dir()
        return os.path.join(
            str(directory), time.strftime("grabacion_%Y%m%d_%H%M%S") + extension
        )

    def _build_command_wayland(self):
        fps = self._target_fps()
        self._prepare_output()
        if self.backend != "wf-recorder":
            return None
        target = self._temp_path or self.output_path
        cmd = [
            shutil.which("wf-recorder"),
            "-f", target,
            "-r", str(fps),
            "--pixel-format", "yuv420p",
        ]
        if self.region_geometry:
            x, y, width, height = self.region_geometry
            cmd += ["-g", f"{x},{y} {width}x{height}"]
        if self.audio_check.get_active() and not self._is_gif():
            sinks = capture.list_audio_sinks()
            if sinks:
                monitor = sinks[0]
                if not monitor.endswith(".monitor"):
                    monitor = monitor + ".monitor"
                cmd += [f"--audio={monitor}"]
        return cmd

    def _build_command(self):
        if capture.is_wayland():
            return self._build_command_wayland()
        display = os.environ.get("DISPLAY", ":0.0")
        fps = self._target_fps()
        monitors = capture.monitor_geometries()
        if self.region is not None:
            width, height = self.region.width, self.region.height
            ox, oy = self.region_offset
            grab_input = f"{display}+{int(ox)},{int(oy)}"
            size = f"{width}x{height}"
        else:
            if not monitors:
                return None
            mon = monitors[0]
            size = f"{mon.width}x{mon.height}"
            grab_input = f"{display}+{mon.x},{mon.y}"

        self._prepare_output()
        target = self._temp_path or self.output_path

        if has_encoder("libx264"):
            vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
        else:
            vcodec = ["-c:v", "mpeg4", "-qscale:v", "5"]

        cmd = [
            ffmpeg_path(),
            "-y",
            "-f", "x11grab",
            "-framerate", str(fps),
            "-video_size", size,
            "-i", grab_input,
        ]
        if self.audio_check.get_active() and not self._is_gif():
            sinks = capture.list_audio_sinks()
            if sinks:
                monitor = sinks[0]
                if not monitor.endswith(".monitor"):
                    monitor = monitor + ".monitor"
                cmd += ["-f", "pulse", "-i", monitor, "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-r", str(fps)] + vcodec + [target]
        return cmd

    def _can_start(self):
        if self.backend is None:
            return False
        if not ffmpeg_path() and (self.backend == "x11" or self._is_gif()):
            return False
        return True

    def _is_gif(self):
        return self.format_combo.get_active_id() == "gif"

    def _update_audio_state(self):
        if not hasattr(self, "audio_check"):
            return
        gif = self._is_gif()
        self.audio_check.set_sensitive(self._audio_available and not gif)
        self.audio_check.set_tooltip_text(
            "GIF no incluye audio" if gif else "Grabar el audio del sistema"
        )
        self.fps_spin.set_tooltip_text(
            f"GIF se graba a un maximo de {GIF_MAX_FPS} FPS." if gif else ""
        )

    def _on_format_changed(self, _combo):
        self.config["record_format"] = self.format_combo.get_active_id() or "mp4"
        self._update_audio_state()
        try:
            self.config.save()
        except Exception:
            pass

    def _prepare_output(self):
        """Elige la ruta final y, para GIF, el video temporal que se convierte."""
        self._temp_path = None
        if self._is_gif():
            self.output_path = self._output_path(".gif")
            self._temp_path = self._output_path(".mp4")
        else:
            self.output_path = self._output_path(".mp4")

    def _target_fps(self):
        fps = int(self.fps_spin.get_value())
        return min(fps, GIF_MAX_FPS) if self._is_gif() else fps

    def _on_countdown_changed(self, spin):
        self.config["record_countdown"] = int(spin.get_value())
        try:
            self.config.save()
        except Exception:
            pass

    def _set_timer_text(self, text, countdown=False):
        """Actualiza el reloj. La cuenta regresiva se muestra grande y centrada."""
        size = "72pt" if countdown else "28pt"
        weight = " weight='bold'" if countdown else ""
        self.timer_label.set_markup(
            f"<span font_family='monospace' font_size='{size}'{weight}>{text}</span>"
        )

    def is_busy(self):
        """True si hay una grabacion, una cuenta o una conversion en curso."""
        return (
            self._countdown_timer is not None
            or self.process is not None
            or self._gnome_screencast
            or self._converting
        )

    def toggle_recording(self):
        """Inicia o detiene la grabacion (atajo global y Ctrl+R)."""
        if self._converting:
            self.present()
            self.status.set_text("Generando GIF...")
            return
        if self.is_busy():
            self._stop()
            self.present()
            return
        if not self._can_start():
            self.present()
            self.status.set_text("No se puede iniciar la grabacion")
            return
        # Al grabar desde un atajo, la ventana no debe salir en el video.
        self.hide()
        self._start()
        if not self.is_busy():
            # No se pudo iniciar (backend o ffmpeg): muestra el motivo.
            self.present()

    def _show_countdown_overlay(self):
        if not self.countdown_overlay_enabled:
            return
        if self._countdown_overlay is None:
            self._countdown_overlay = CountdownOverlay()
        self._countdown_overlay.set_remaining(self._countdown_remaining)

    def _hide_countdown_overlay(self):
        if self._countdown_overlay is not None:
            self._countdown_overlay.destroy()
            self._countdown_overlay = None

    def _show_countdown(self):
        remaining = self._countdown_remaining
        self._set_timer_text(str(remaining), countdown=True)
        self._show_countdown_overlay()
        self.status.set_text(f"La grabacion empieza en {remaining} s...")

    def _begin_countdown(self, seconds):
        self._countdown_remaining = int(seconds)
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.format_combo.set_sensitive(False)
        # La ventana no debe duplicar la cuenta ni salir luego en el video.
        self.hide()
        self._show_countdown()
        self._countdown_timer = GLib.timeout_add(1000, self._countdown_tick)

    def _countdown_tick(self):
        if self._countdown_remaining > 0:
            self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer = None
            self._hide_countdown_overlay()
            self._set_timer_text("00:00")
            self._start_recording()
            return False
        self._show_countdown()
        return True

    def _cancel_countdown(self):
        if self._countdown_timer is not None:
            try:
                GLib.source_remove(self._countdown_timer)
            except Exception:
                pass
            self._countdown_timer = None
        self._countdown_remaining = 0
        self._hide_countdown_overlay()
        self._set_timer_text("00:00")
        self.start_btn.set_sensitive(self._can_start())
        self.stop_btn.set_sensitive(False)
        self.format_combo.set_sensitive(True)

    def _start(self):
        if self._countdown_timer is not None or self._converting:
            return
        if not self._can_start():
            self.status.set_text("No se puede iniciar la grabacion")
            return
        self._save_countdown()
        seconds = int(self.countdown_spin.get_value())
        if seconds > 0:
            self._begin_countdown(seconds)
        else:
            self._start_recording()

    def _save_countdown(self):
        self._on_countdown_changed(self.countdown_spin)

    def _start_recording(self):
        if self.backend == "gnome":
            self._start_gnome()
            return
        cmd = self._build_command()
        if not cmd:
            self.status.set_text("No se pudo preparar la grabacion")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.format_combo.set_sensitive(True)
            return
        try:
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        except Exception as exc:
            self.status.set_text(f"Error: {exc}")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.format_combo.set_sensitive(True)
            return
        self._stop_signal = self.backend == "wf-recorder"
        self.start_time = time.time()
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.format_combo.set_sensitive(False)
        self.status.set_text(f"Grabando en {self.output_path}")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._tick)

    def _start_gnome(self):
        fps = self._target_fps()
        gif = self._is_gif()
        self._temp_path = None
        if gif:
            self.output_path = self._output_path(".gif")
        template = self._output_path(".webm")
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            reply = bus.call_sync(
                "org.gnome.Shell",
                "/org/gnome/Shell/Screencast",
                "org.gnome.Shell.Screencast",
                "Screencast",
                GLib.Variant(
                    "(sa{sv})",
                    (
                        template,
                        {
                            "framerate": GLib.Variant("i", fps),
                            "draw-cursor": GLib.Variant("b", True),
                        },
                    ),
                ),
                GLib.VariantType.new("(bs)"),
                Gio.DBusCallFlags.NONE,
                10000,
                None,
            )
            success, filename = reply.unpack()
        except Exception as exc:
            self.status.set_text(f"Error: {exc}")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.format_combo.set_sensitive(True)
            return
        if not success:
            self.status.set_text("GNOME Shell rechazo la grabacion.")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.format_combo.set_sensitive(True)
            return
        self._gnome_bus = bus
        self._gnome_screencast = True
        if gif:
            self._temp_path = filename
        else:
            self.output_path = filename
        self.start_time = time.time()
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.format_combo.set_sensitive(False)
        self.status.set_text(f"Grabando en {self.output_path}")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._tick)

    def _tick(self):
        if not self.process and not self._gnome_screencast:
            self._timer = None
            return False
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        self._set_timer_text(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
        return True

    def _stop(self):
        if self._countdown_timer is not None:
            self._cancel_countdown()
            self.status.set_text("Grabacion cancelada")
            return
        if self._converting:
            return
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        stopped = False
        if self._gnome_screencast:
            try:
                self._gnome_bus.call_sync(
                    "org.gnome.Shell",
                    "/org/gnome/Shell/Screencast",
                    "org.gnome.Shell.Screencast",
                    "StopScreencast",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    5000,
                    None,
                )
            except Exception:
                pass
            self._gnome_screencast = False
            self._gnome_bus = None
            stopped = True
        if self.process:
            try:
                if self._stop_signal:
                    self.process.send_signal(signal.SIGINT)
                else:
                    self.process.stdin.write(b"q")
                    self.process.stdin.flush()
                self.process.wait(timeout=10)
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            self.process = None
            stopped = True
        if not stopped:
            return
        self.start_btn.set_sensitive(self._can_start())
        self.stop_btn.set_sensitive(False)
        self.format_combo.set_sensitive(True)
        temp = self._temp_path
        self._temp_path = None
        if temp:
            self._start_gif_conversion(temp)
        else:
            self.status.set_text(f"Guardado: {self.output_path}")

    def _start_gif_conversion(self, video_path):
        """Convierte el video temporal a GIF sin bloquear la interfaz."""
        self._converting = True
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(False)
        self.format_combo.set_sensitive(False)
        self.status.set_text("Generando GIF...")
        self.status.set_tooltip_text("")
        fps = self._target_fps()
        gif_path = self.output_path

        def work():
            try:
                video_to_gif(video_path, gif_path, fps)
            except Exception as exc:
                GLib.idle_add(self._gif_finished, False, str(exc), video_path)
                return
            try:
                os.remove(video_path)
            except OSError:
                pass
            GLib.idle_add(self._gif_finished, True, gif_path, None)

        threading.Thread(target=work, daemon=True).start()

    def _gif_finished(self, success, detail, temp_path):
        self._converting = False
        self.start_btn.set_sensitive(self._can_start())
        self.stop_btn.set_sensitive(False)
        self.format_combo.set_sensitive(True)
        if success:
            self.status.set_text(f"Guardado: {detail}")
        else:
            self.status.set_text(f"Error al crear el GIF: {detail}")
            if temp_path:
                self.status.set_tooltip_text(f"Video temporal: {temp_path}")
        return False


def open_recorder(config):
    return RecorderWindow(config)
