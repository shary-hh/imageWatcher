"""Grabador de pantalla basado en ffmpeg x11grab."""
import os
import shutil
import subprocess
import time

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk  # noqa: E402

from . import capture, ui  # noqa: E402


def ffmpeg_path():
    return shutil.which("ffmpeg")


def has_encoder(name):
    try:
        out = subprocess.run([ffmpeg_path(), "-hide_banner", "-encoders"],
                             capture_output=True, text=True, timeout=10)
        return name in out.stdout
    except Exception:
        return False


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
        self.start_time = None
        self._timer = None
        self.set_default_size(440, 300)
        self.set_titlebar(ui.header("Grabador de pantalla", "Video con ffmpeg", "media-record"))

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

        grid.attach(Gtk.Label(label="Audio del sistema:", xalign=0), 0, 2, 1, 1)
        self.audio_check = Gtk.CheckButton()
        self.audio_check.set_active(config.get("record_audio", False))
        sink = capture.list_audio_sinks()
        self.audio_check.set_sensitive(bool(sink))
        grid.attach(self.audio_check, 1, 2, 1, 1)

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

        if not ffmpeg_path():
            self.start_btn.set_sensitive(False)
            self.status.set_text("ffmpeg no esta instalado (sudo apt install ffmpeg)")

    def _on_key(self, _widget, event):
        from gi.repository import Gdk

        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _pick_region(self, *_):
        base = capture.capture_screen()
        self.hide()
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

    def _build_command(self):
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

    def _start(self):
        cmd = self._build_command()
        if not cmd:
            self.status.set_text("No se pudo preparar la grabacion")
            return
        try:
            self.process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
        except Exception as exc:
            self.status.set_text(f"Error: {exc}")
            return
        self.start_time = time.time()
        self.start_btn.set_sensitive(False)
        self.stop_btn.set_sensitive(True)
        self.status.set_text(f"Grabando en {self.output_path}")
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(500, self._tick)

    def _tick(self):
        if not self.process:
            self._timer = None
            return False
        elapsed = int(time.time() - self.start_time) if self.start_time else 0
        self.timer_label.set_markup(f"<span size='xx-large'>{elapsed // 60:02d}:{elapsed % 60:02d}</span>")
        return True

    def _stop(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        if self.process:
            try:
                self.process.stdin.write(b"q")
                self.process.stdin.flush()
                self.process.wait(timeout=10)
            except Exception:
                try:
                    self.process.terminate()
                except Exception:
                    pass
            self.process = None
            self.start_btn.set_sensitive(bool(ffmpeg_path()))
            self.stop_btn.set_sensitive(False)
            self.status.set_text(f"Guardado: {self.output_path}")


def open_recorder(config):
    return RecorderWindow(config)
