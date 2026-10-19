"""Utilidades GTK3 compartidas: versiones, conversion Pixbuf <-> PIL."""
import io

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, Gtk  # noqa: E402
from PIL import Image  # noqa: E402


def pil_to_pixbuf(image):
    """Convierte una imagen PIL (RGBA/RGB) a GdkPixbuf sin perdida."""
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    data = image.tobytes()
    pixbuf = GdkPixbuf.Pixbuf.new_from_data(
        data,
        GdkPixbuf.Colorspace.RGB,
        True,
        8,
        image.width,
        image.height,
        image.width * 4,
    )
    return pixbuf.copy()


def pixbuf_to_pil(pixbuf):
    """Convierte un GdkPixbuf a imagen PIL RGBA (via PNG para robustez)."""
    ok, data = pixbuf.save_to_bufferv("png", [], [])
    if not ok:
        raise RuntimeError("No se pudo convertir el pixbuf")
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def pil_to_bytes(image, fmt="PNG", **kwargs):
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def get_pointer_position():
    """Devuelve (x, y) globales del puntero usando el display por defecto."""
    display = Gdk.Display.get_default()
    try:
        seat = display.get_default_seat()
        _, x, y = seat.get_pointer().get_position()
        return x, y
    except Exception:
        from gi.repository import Gdk as _Gdk

        root = _Gdk.get_default_root_window()
        _, x, y, _ = root.get_pointer()
        return x, y


def set_dark_titlebar(window):
    """Solicita titulo oscuro cuando el WM lo soporta (no critico)."""
    try:
        window.set_titlebar(window.get_titlebar())
    except Exception:
        pass


def add_css(widget, css):
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    context = widget.get_style_context()
    context.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    return provider
