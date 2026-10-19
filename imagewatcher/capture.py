"""Backend de captura de pantalla para X11 (Cinnamon / Linux Mint).

Usa Gdk para capturar el framebuffer y Xlib para resolver la ventana activa,
la lista de ventanas y (opcionalmente) el cursor del raton.
"""
import subprocess
import time
from dataclasses import dataclass

import gi

gi.require_version("Gdk", "3.0")

from gi.repository import Gdk
from PIL import Image, ImageChops, ImageStat

from .gtk_util import pixbuf_to_pil


@dataclass
class Geometry:
    x: int
    y: int
    width: int
    height: int

    def as_tuple(self):
        return (self.x, self.y, self.width, self.height)


def virtual_screen_size():
    root = Gdk.get_default_root_window()
    return root.get_width(), root.get_height()


def monitor_geometries():
    """Devuelve la lista de geometrias de monitores (coordenadas globales)."""
    display = Gdk.Display.get_default()
    result = []
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        geom = monitor.get_geometry()
        result.append(Geometry(geom.x, geom.y, geom.width, geom.height))
    return result


def capture_screen():
    """Captura el escritorio completo (todos los monitores) como PIL RGBA."""
    root = Gdk.get_default_root_window()
    width, height = root.get_width(), root.get_height()
    pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, width, height)
    return pixbuf_to_pil(pixbuf)


def capture_region(x, y, width, height, base=None):
    """Captura una region concreta.

    Si ``base`` es una imagen, recorta de ella. Si es ``None``, toma la
    subregion directamente de la pantalla (rapido: sin capturar todo el
    escritorio ni codificar en PNG).
    """
    if width <= 0 or height <= 0:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

    if base is not None:
        left = max(0, x)
        top = max(0, y)
        right = min(base.width, x + width)
        bottom = min(base.height, y + height)
        if right <= left or bottom <= top:
            return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        return base.crop((left, top, right, bottom))

    root = Gdk.get_default_root_window()
    screen_w, screen_h = root.get_width(), root.get_height()
    left = max(0, min(int(x), screen_w - 1))
    top = max(0, min(int(y), screen_h - 1))
    grab_w = max(1, min(width, screen_w - left))
    grab_h = max(1, min(height, screen_h - top))
    pixbuf = Gdk.pixbuf_get_from_window(root, left, top, grab_w, grab_h)
    if pixbuf is None:
        return Image.new("RGBA", (grab_w, grab_h), (0, 0, 0, 0))
    return pixbuf_to_pil(pixbuf)


def capture_window(include_cursor=False):
    """Captura la ventana activa (con decoraciones). None si no se puede resolver."""
    geom = active_window_geometry()
    if geom is None:
        return capture_screen()
    image = capture_region(*geom.as_tuple())
    if include_cursor:
        image = _composite_cursor(image, geom)
    return image


def capture_monitor(index):
    monitors = monitor_geometries()
    if not monitors:
        return capture_screen()
    index = index % len(monitors)
    return capture_region(*monitors[index].as_tuple())


# --------------------------------------------------------------------- scroll
def _mean_abs_diff(image_a, image_b):
    """Diferencia media absoluta entre dos imagenes del mismo tamano."""
    width = min(image_a.width, image_b.width)
    height = min(image_a.height, image_b.height)
    a = image_a.convert("RGB").crop((0, 0, width, height))
    b = image_b.convert("RGB").crop((0, 0, width, height))
    diff = ImageChops.difference(a, b)
    stat = ImageStat.Stat(diff)
    return sum(stat.mean) / len(stat.mean) if stat.mean else 0.0


ROW_SAMPLE_WIDTH = 64
STATIC_ROW_THRESHOLD = 1.5
STATIC_ROW_RUN = 8


def _row_diff_means(previous, current, sample_width=ROW_SAMPLE_WIDTH):
    """Diferencia media por fila entre dos imagenes alineadas arriba."""
    height = min(previous.height, current.height)
    width = min(previous.width, current.width)
    if height <= 0 or width <= 0:
        return []
    sample_width = max(1, min(sample_width, width))
    a = previous.convert("L").crop((0, 0, width, height)).resize((sample_width, height))
    b = current.convert("L").crop((0, 0, width, height)).resize((sample_width, height))
    data = list(ImageChops.difference(a, b).getdata())
    return [
        sum(data[y * sample_width : (y + 1) * sample_width]) / sample_width
        for y in range(height)
    ]


def _moving_top(row_diffs):
    """Primera fila de una racha de filas que cambian entre dos capturas."""
    run = 0
    for y, value in enumerate(row_diffs):
        if value > STATIC_ROW_THRESHOLD:
            run += 1
            if run >= STATIC_ROW_RUN:
                return y - STATIC_ROW_RUN + 1
        else:
            run = 0
    return 0


def _band_detail(image, offset, band_height):
    """Desviacion tipica de una banda: mide si tiene textura o es lisa."""
    band = image.convert("L").crop((0, offset, image.width, offset + band_height))
    stat = ImageStat.Stat(band)
    return stat.stddev[0] if stat.stddev else 0.0


def _choose_band_offset(current, row_diffs, content_top, band_height):
    """Elige una banda movil con textura para que el empalme no sea ambiguo.

    Sobre fondos de un solo color muchas filas coinciden con cualquier
    desplazamiento. Un trozo con texto/imagenes hace unica la coincidencia.
    """
    min_height = min(len(row_diffs), current.height)
    max_offset = min_height - band_height
    if max_offset <= content_top:
        return max(0, max_offset)
    # Reservar sitio para un paso de scroll tipico en la busqueda.
    room = max(64, min_height // 3)
    last_offset = max(content_top, max_offset - room)
    best_offset = content_top
    best_score = -1.0
    offsets = list(range(content_top, last_offset + 1, 8))
    for offset in offsets:
        detail = _band_detail(current, offset, band_height)
        movement = sum(row_diffs[offset : offset + band_height]) / band_height
        score = detail * movement
        if score > best_score:
            best_score = score
            best_offset = offset
    for offset in range(max(content_top, best_offset - 8), min(last_offset, best_offset + 8) + 1):
        detail = _band_detail(current, offset, band_height)
        movement = sum(row_diffs[offset : offset + band_height]) / band_height
        score = detail * movement
        if score > best_score:
            best_score = score
            best_offset = offset
    return best_offset


MATCH_WIDTH = 128
MATCH_GOOD_DIFF = 2.0


def find_vertical_shift(previous, current, band_height=24, min_shift=1, max_shift=None):
    """Busca en que fila de ``previous`` encaja una banda de ``current``.

    La banda se toma del contenido que realmente se desplaza, no de la
    cabecera fija de la ventana. Se compara sobre una version reducida
    horizontalmente y se puede acotar el rango con ``min_shift``/``max_shift``
    para no recorrer toda la imagen acumulada. Devuelve ``(shift, diff)``.
    """
    band_height = min(band_height, current.height)
    width = min(previous.width, current.width)
    if width <= 0 or band_height <= 0:
        return 0, 0.0
    match_width = max(1, min(width, MATCH_WIDTH))
    previous_small = previous.convert("RGB").resize((match_width, previous.height))
    current_small = current.convert("RGB").resize((match_width, current.height))
    row_diffs = _row_diff_means(previous, current)
    content_top = _moving_top(row_diffs)
    content_top = max(0, min(content_top, previous.height - band_height - min_shift))
    if max_shift is None:
        offsets = [content_top]
    else:
        detailed = _choose_band_offset(current_small, row_diffs, content_top, band_height)
        offsets = [detailed]
        if detailed != content_top:
            # Si la banda con textura no acota bien (fondo liso o paso
            # grande), reintentar con la banda mas alta para tener mas rango.
            offsets.append(content_top)

    best_seen = None
    for offset in offsets:
        offset = max(0, min(offset, previous.height - band_height - min_shift))
        band = current_small.crop((0, offset, match_width, offset + band_height))
        max_allowed = previous.height - band_height - offset
        limit = max_allowed if max_shift is None else min(max_shift, max_allowed)
        if limit < min_shift:
            continue
        best_shift = 0
        best_diff = None
        for shift in range(min_shift, limit + 1):
            top = offset + shift
            window = previous_small.crop((0, top, match_width, top + band_height))
            diff = _mean_abs_diff(band, window)
            if best_diff is None or diff < best_diff:
                best_diff, best_shift = diff, shift
        if best_diff is None:
            continue
        if best_seen is None or best_diff < best_seen[1]:
            best_seen = (best_shift, best_diff)
        if best_diff <= MATCH_GOOD_DIFF:
            return best_shift, best_diff
    return best_seen or (0, 0.0)


def stitch_vertical(frames):
    """Une capturas verticales con solape en una sola imagen (Pillow)."""
    frames = [frame.convert("RGBA") for frame in frames if frame is not None]
    if not frames:
        return None
    result = frames[0]
    last_shift = 0
    max_step = max(frame.height for frame in frames)
    for frame in frames[1:]:
        # El desplazamiento total crece de forma monotona y cada frame avanza
        # como mucho una altura de ventana respecto al anterior.
        shift, diff = find_vertical_shift(
            result,
            frame,
            min_shift=last_shift + 1,
            max_shift=last_shift + max_step,
        )
        overlap = result.height - shift
        if overlap < 0:
            overlap = 0
        new_part = frame.crop((0, min(overlap, frame.height), frame.width, frame.height))
        if new_part.height <= 2:
            break
        last_shift = shift
        combined = Image.new(
            "RGBA", (max(result.width, frame.width), result.height + new_part.height), (0, 0, 0, 0)
        )
        combined.alpha_composite(result, (0, 0))
        combined.alpha_composite(new_part, (0, result.height))
        result = combined
    return result


SCROLL_DIFF = 0.4


def _scroll_active_window(times=1, geom=None):
    """Envia rueda de scroll hacia abajo sobre el centro de la ventana.

    XTest entrega la rueda a la ventana que esta bajo el puntero, no a la
    ventana activa. Si el puntero esta sobre la barra de imageWatcher (o
    cualquier otra ventana) el destino no se desplaza y la captura se queda
    con la parte visible. Se mueve el puntero al centro de la ventana y se
    restaura al terminar.
    """
    try:
        from Xlib import X
        from Xlib.ext import xtest

        d = _x11_display()
        root = d.screen().root
        if geom is None:
            geom = active_window_geometry()
        if geom is None or geom.width <= 0 or geom.height <= 0:
            return False
        screen = d.screen()
        target_x = max(0, min(geom.x + geom.width // 2, screen.width_in_pixels - 1))
        target_y = max(0, min(geom.y + geom.height // 2, screen.height_in_pixels - 1))
        pointer = root.query_pointer()
        origin_x, origin_y = pointer.root_x, pointer.root_y
        try:
            root.warp_pointer(target_x, target_y)
            d.sync()
            for _ in range(times):
                xtest.fake_input(d, X.ButtonPress, 5)
                xtest.fake_input(d, X.ButtonRelease, 5)
                d.sync()
        finally:
            try:
                root.warp_pointer(origin_x, origin_y)
                d.sync()
            except Exception:
                pass
        return True
    except Exception:
        return False


def _capture_settled(
    geometry,
    baseline,
    start_timeout=1.0,
    settle_timeout=1.0,
    interval=0.08,
    required_stable=3,
):
    """Captura tras el scroll esperando a que empiece y termine el movimiento.

    Los navegadores hacen scroll suave: al enviar la rueda el contenido puede
    tardar en empezar a moverse. Comparar dos capturas seguidas nada mas
    soltar la rueda devolvia el frame previo (sin scroll) y la captura se
    quedaba con la parte visible. Primero se espera a detectar movimiento y
    despues a que varias capturas seguidas sean estables.
    """
    start = time.monotonic()
    deadline = start + start_timeout + settle_timeout
    frame = baseline
    moved = False
    stable = 0
    while time.monotonic() < deadline:
        time.sleep(interval)
        next_frame = capture_region(*geometry.as_tuple())
        diff = _mean_abs_diff(frame, next_frame)
        if not moved:
            if _mean_abs_diff(baseline, next_frame) >= SCROLL_DIFF:
                moved = True
                stable = 0
            elif time.monotonic() - start >= start_timeout:
                return next_frame
        elif diff < SCROLL_DIFF:
            stable += 1
            if stable >= required_stable:
                return next_frame
        else:
            stable = 0
        frame = next_frame
    return frame


def capture_scrolling_window(max_scrolls=30):
    """Captura una ventana larga desplazandola y empalmando con Pillow."""
    geom = active_window_geometry()
    if geom is None:
        return capture_screen()
    frames = [capture_region(*geom.as_tuple())]
    for _ in range(max_scrolls):
        previous = frames[-1]
        if not _scroll_active_window(1, geom=geom):
            break
        frame = _capture_settled(geom, previous)
        if _mean_abs_diff(previous, frame) < SCROLL_DIFF:
            break
        frames.append(frame)
    return stitch_vertical(frames)



_display_cache = None


def _x11_display():
    """Devuelve una conexion Xlib reutilizada (evita fugas de conexiones)."""
    global _display_cache
    if _display_cache is None:
        from Xlib import display as xdisplay

        _display_cache = xdisplay.Display()
    return _display_cache


def _root_coords(window, root):
    """Coordenadas absolutas de ``window`` respecto a la raiz.

    ``Window.translate_coords`` traduce *desde* el primer argumento *hacia* la
    ventana sobre la que se invoca, por lo que hay que llamarlo en ``root``
    pasando la ventana: al reves devuelve la posicion con signo cambiado.
    """
    coords = root.translate_coords(window, 0, 0)
    return coords.x, coords.y


def active_window_geometry():
    """Geometria (x, y, w, h) de la ventana activa incluyendo marco."""
    try:
        from Xlib import X

        d = _x11_display()
        root = d.screen().root
        atom = d.intern_atom("_NET_ACTIVE_WINDOW")
        prop = root.get_full_property(atom, X.AnyPropertyType)
        if not prop or not prop.value:
            return None
        win_id = prop.value[0]
        if win_id in (0, 1):
            return None
        win = d.create_resource_object("window", win_id)
        x, y = _root_coords(win, root)
        geom = win.get_geometry()
        w, h = geom.width, geom.height
        frame = win.get_full_property(d.intern_atom("_NET_FRAME_EXTENTS"), X.AnyPropertyType)
        if frame and len(frame.value) >= 4:
            left, right, top, bottom = frame.value[:4]
            x -= left
            y -= top
            w += left + right
            h += top + bottom
        return Geometry(x, y, w, h)
    except Exception:
        return None


def list_windows():
    """Lista de ventanas gestionadas por el WM con nombre y geometria."""
    windows = []
    try:
        from Xlib import X

        d = _x11_display()
        root = d.screen().root
        atom = d.intern_atom("_NET_CLIENT_LIST_STACKING")
        prop = root.get_full_property(atom, X.AnyPropertyType)
        if not prop:
            return windows
        for win_id in prop.value:
            try:
                win = d.create_resource_object("window", win_id)
                x, y = _root_coords(win, root)
                geom = win.get_geometry()
                name_prop = win.get_full_property(d.intern_atom("_NET_WM_NAME"), 0)
                title = ""
                if name_prop and name_prop.value:
                    title = name_prop.value
                    if isinstance(title, bytes):
                        title = title.decode("utf-8", "replace")
                windows.append(Geometry(x, y, geom.width, geom.height))
                windows[-1].title = title
            except Exception:
                continue
    except Exception:
        pass
    return windows


def _composite_cursor(image, geom):
    """Compone la imagen real del cursor sobre la captura (best effort)."""
    try:
        from Xlib import X
        from Xlib.ext import xfixes

        d = _x11_display()
        xfixes.display_init(d)
        pointer = d.screen().root.query_pointer()
        cursor = d.xfixes_get_cursor_image()
        cw, ch = cursor.width, cursor.height
        pixels = cursor.cursor_image
        cursor_img = Image.new("RGBA", (cw, ch))
        for j in range(ch):
            row = pixels[j * cw : (j + 1) * cw]
            for i, value in enumerate(row):
                a = (value >> 24) & 0xFF
                r = (value >> 16) & 0xFF
                g = (value >> 8) & 0xFF
                b = value & 0xFF
                cursor_img.putpixel((i, j), (r, g, b, a))
        px = pointer.root_x - cursor.xhot - geom.x
        py = pointer.root_y - cursor.yhot - geom.y
        image.alpha_composite(cursor_img, (px, py))
    except Exception:
        pass
    return image


def copy_image_to_clipboard(image):
    """Copia una imagen PIL al portapapeles."""
    from gi.repository import Gtk

    from .gtk_util import pil_to_pixbuf

    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_image(pil_to_pixbuf(image))
    clipboard.store()


def list_audio_sinks():
    """Lista dispositivos de audio para grabacion (pactl)."""
    try:
        out = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        names = []
        for line in out.stdout.splitlines():
            parts = line.split()
            if len(parts) > 1:
                names.append(parts[1])
        return names
    except Exception:
        return []
