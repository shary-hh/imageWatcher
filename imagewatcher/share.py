"""Utilidades para compartir: URL local (HTTP), programa externo, impresion.

El equivalente Linux a "subir y obtener un enlace" de PicPick es levantar un
servidor HTTP local que sirve el archivo en la red local.
"""
import functools
import http.server
import socket
import subprocess
import threading


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # silenciar el log
        pass


class LocalShare:
    """Sirve un archivo por HTTP en la red local y devuelve su URL."""

    def __init__(self, directory):
        self.directory = str(directory)
        self.httpd = None
        self.thread = None
        self.url = None

    def start(self, filename):
        handler = functools.partial(_QuietHandler, directory=self.directory)
        self.httpd = http.server.ThreadingHTTPServer(("0.0.0.0", 0), handler)
        port = self.httpd.server_address[1]
        self.url = f"http://{self._lan_ip()}:{port}/{filename}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self.url

    def stop(self):
        if self.httpd is not None:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
            self.thread = None

    @staticmethod
    def _lan_ip():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            return ip
        except Exception:
            return "127.0.0.1"


def open_with_external(path):
    """Abre un archivo con la aplicacion predeterminada del escritorio."""
    return subprocess.Popen(["xdg-open", str(path)])
