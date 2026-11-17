"""Control de instancia unica para imageWatcher.

Al abrir la aplicacion otra vez (desde el menu, el escritorio o el
lanzador) no se crea un proceso nuevo: se avisa a la instancia que ya
esta corriendo para que muestre su barra de captura.

Se usa un socket Unix en XDG_RUNTIME_DIR y un fichero de bloqueo con
flock. El bloqueo evita que dos procesos que arrancan a la vez se
consideren ambos principales.
"""
import fcntl
import logging
import os
import socket
import tempfile
import time
from pathlib import Path

from gi.repository import GLib

from . import __app_id__

logger = logging.getLogger(__name__)


def default_socket_path():
    """Ruta del socket de la sesion actual (por usuario)."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    base = Path(runtime) if runtime else Path(tempfile.gettempdir())
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path(tempfile.gettempdir())
    return base / f"{__app_id__}-{os.getuid()}.sock"


class SingleInstance:
    """Toma el control de la primera instancia o avisa a la existente."""

    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_socket_path()
        self._lock_fd = None
        self._server = None
        self._channel = None
        self._watch_id = None
        self._callback = None
        self._pending = None
        self._primary = False

    @property
    def is_primary(self):
        return self._primary

    def set_callback(self, callback):
        """Funcion que se ejecuta cuando otra instancia pide mostrarse."""
        self._callback = callback
        pending, self._pending = self._pending, None
        if pending is not None:
            self._run_callback(pending)

    def acquire(self, command=b"activate\n", timeout=2.0):
        """Devuelve True si somos la instancia principal.

        Si ya hay una instancia viva le envia ``command`` y devuelve False.
        """
        if not self._lock():
            self._notify_existing(command, timeout)
            return False
        self._start_server()
        self._primary = True
        return True

    # ------------------------------------------------------------ locking
    def _lock(self):
        lock_path = self.path.with_suffix(".lock")
        try:
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        except OSError:
            logger.warning("No se pudo abrir el bloqueo %s", lock_path)
            return True
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(lock_fd)
            return False
        self._lock_fd = lock_fd
        return True

    def _notify_existing(self, command, timeout):
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(min(0.5, remaining))
            try:
                sock.connect(str(self.path))
                sock.sendall(command)
                return True
            except OSError:
                time.sleep(0.05)
            finally:
                try:
                    sock.close()
                except OSError:
                    pass
        logger.info("Otra instancia esta arrancando; no se abre una nueva.")
        return False

    # ------------------------------------------------------------- server
    def _start_server(self):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(self.path))
            os.chmod(str(self.path), 0o600)
            server.listen(5)
            server.setblocking(False)
        except OSError:
            server.close()
            raise
        self._server = server
        self._channel = GLib.IOChannel.unix_new(server.fileno())
        self._channel.set_close_on_unref(False)
        self._watch_id = GLib.io_add_watch(
            self._channel,
            GLib.PRIORITY_DEFAULT,
            GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
            self._on_connection,
        )

    def _on_connection(self, _channel, _condition):
        while True:
            try:
                conn, _addr = self._server.accept()
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            try:
                conn.settimeout(0.5)
                raw = conn.recv(64)
            except OSError:
                raw = b""
            finally:
                try:
                    conn.close()
                except OSError:
                    pass
            self._dispatch(raw.strip() or b"activate")
        return True

    def _dispatch(self, command):
        action = command.decode("utf-8", "ignore").strip().lower() or "activate"
        if self._callback is None:
            self._pending = action
            return
        self._run_callback(action)

    def _run_callback(self, action):
        try:
            self._callback(action)
        except Exception:
            logger.exception("Fallo atendiendo la orden %r", action)

    # ------------------------------------------------------------ cleanup
    def close(self):
        if self._watch_id is not None:
            try:
                GLib.source_remove(self._watch_id)
            except Exception:
                pass
            self._watch_id = None
        if self._channel is not None:
            try:
                self._channel.shutdown(False)
            except Exception:
                pass
            self._channel = None
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
            self._server = None
        try:
            self.path.unlink()
        except OSError:
            pass
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        self._primary = False
