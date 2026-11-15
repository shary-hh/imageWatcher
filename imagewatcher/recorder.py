"""Grabador de pantalla: ffmpeg/x11grab en X11 y wf-recorder/GNOME en Wayland."""
import os
import re
import shutil
import signal
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402

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


class RecorderWindow(Gtk.Window):
    def __init__(self, config):
        super().__init__(title="Grabador de pantalla")
        ui.install_theme()
        ui.apply_dark(self)
        self.config = config
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

        grid.attach(Gtk.Label(label="Audio del sistema:", xalign=0), 0, 3, 1, 1)
        self.audio_check = Gtk.CheckButton()
        self.audio_check.set_active(config.get("record_audio", False))
        sink = capture.list_audio_sinks()
        self.audio_check.set_sensitive(
            bool(sink) and self.backend in ("x11", "wf-recorder")
        )
        grid.attach(self.audio_check, 1, 3, 1, 1)

        self.timer_label = Gtk.Label(label="00:00")
        self.timer_label.set_markup("<span size='xx-large'>00:00</span>")
        root.pack_start(self.timer_label, False, False, 4)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.start_btn = Gtk.Button(label="Iniciar grabacion")
        self.start_btn.connect("clicked", lambda *_: self._start())
        buttons.pack_start(self.start_btn, True, True, 0)
        self.stop_btn = Gtk.Button(label="Detener")
        self.stop_btn.set_sensitive(False)
        self.stop_btn.connect("clicked", lambda *_: self._stop())
        buttons.pack_start(self.stop_btn, True, True, 0)
        root.pack_start(buttons, False, False, 0)

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
        fps = int(self.fps_spin.get_value())
        self.output_path = self._output_path(".mp4")
        if self.backend != "wf-recorder":
            return None
        cmd = [
            shutil.which("wf-recorder"),
            "-f", self.output_path,
            "-r", str(fps),
            "--pixel-format", "yuv420p",
        ]
        if self.region_geometry:
            x, y, width, height = self.region_geometry
            cmd += ["-g", f"{x},{y} {width}x{height}"]
        if self.audio_check.get_active():
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
        fps = int(self.fps_spin.get_value())
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

        directory = self.config.ensure_save_dir()
        self.output_path = os.path.join(
            str(directory), time.strftime("grabacion_%Y%m%d_%H%M%S") + ".mp4"
        )

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
        if self.audio_check.get_active():
            sinks = capture.list_audio_sinks()
            if sinks:
                monitor = sinks[0]
                if not monitor.endswith(".monitor"):
                    monitor = monitor + ".monitor"
                cmd += ["-f", "pulse", "-i", monitor, "-c:a", "aac", "-b:a", "160k"]
        cmd += ["-r", str(fps)] + vcodec + [self.output_path]
        return cmd

    def _can_start(self):
        return self.backend is not None and (
            self.backend != "x11" or bool(ffmpeg_path())
        )

    def _on_countdown_changed(self, spin):
        self.config["record_countdown"] = int(spin.get_value())
        try:
            self.config.save()
        except Exception:
            pass

    def _show_countdown(self):
        remaining = self._countdown_remaining
        self.timer_label.set_markup(
            f"<span size='xx-large'>{remaining}</span>"
        )
        self.status.set_text(f"La grabacion empieza en {remaining} s...")

    def _begin_countdown(self, seconds):
        self._countdown_remaining = int(seconds)
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self._show_countdown()
        self._countdown_timer = GLib.timeout_add(1000, self._countdown_tick)

    def _countdown_tick(self):
        if self._countdown_remaining > 0:
            self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer = None
            self.timer_label.set_markup(
                "<span size='xx-large'>00:00</span>"
            )
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
        self.timer_label.set_markup("<span size='xx-large'>00:00</span>")
        self.start_btn.set_sensitive(self._can_start())
        self.stop_btn.set_sensitive(False)

    def _start(self):
        if self._countdown_timer is not None:
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
            return
        try:
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        except Exception as exc:
            self.status.set_text(f"Error: {exc}")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            return
        self._stop_signal = self.backend == "wf-recorder"
        self.start_time = time.time()
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.status.set_text(f"Grabando en {self.output_path}")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._tick)

    def _start_gnome(self):
        fps = int(self.fps_spin.get_value())
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
            return
        if not success:
            self.status.set_text("GNOME Shell rechazo la grabacion.")
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            return
        self._gnome_bus = bus
        self._gnome_screencast = True
        self.output_path = filename
        self.start_time = time.time()
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.status.set_text(f"Grabando en {self.output_path}")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._tick)

    def _tick(self):
        if not self.process and not self._gnome_screencast:
            self._timer = None
            return False
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        self.timer_label.set_markup(f"<span size='xx-large'>{elapsed // 60:02d}:{elapsed % 60:02d}</span>")
        return True

    def _stop(self):
        if self._countdown_timer is not None:
            self._cancel_countdown()
            self.status.set_text("Grabacion cancelada")
            return
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
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
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.status.set_text(f"Guardado: {self.output_path}")
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
            self.start_btn.set_sensitive(self._can_start())
            self.stop_btn.set_sensitive(False)
            self.status.set_text(f"Guardado: {self.output_path}")


def open_recorder(config):
    return RecorderWindow(config)
