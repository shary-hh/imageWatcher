"""Backend de captura de pantalla con soporte X11 y Wayland.

En X11 usa Gdk/Xlib (rapido y con informacion de ventanas). En Wayland usa el
portal de escritorio (xdg-desktop-portal) o herramientas nativas como grim,
gnome-screenshot o spectacle, porque el servidor no expone el framebuffer ni
las ventanas de otros clientes.
"""
import json
import subprocess
import time
from dataclasses import dataclass

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gdk, Gio, GLib  # noqa: E402
from PIL import Image, ImageChops, ImageStat

from . import session
from .gtk_util import get_pointer_position, pixbuf_to_pil


@dataclass
class Geometry:
    x: int
    y: int
    width: int
    height: int
    title: str = ""

    def as_tuple(self):
        return (self.x, self.y, self.width, self.height)


class CaptureCancelled(Exception):
    """El usuario cancelo el selector nativo del portal."""


_wayland_cache = {"time": 0.0, "image": None}
WAYLAND_CACHE_TTL = 0.12


def is_wayland():
    """True si la sesion grafica actual es Wayland."""
    return session.is_wayland()


def monitor_geometries():
    """Devuelve la lista de geometrias de monitores (coordenadas logicas)."""
    display = Gdk.Display.get_default()
    result = []
    if display is None:
        return result
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        geom = monitor.get_geometry()
        result.append(Geometry(geom.x, geom.y, geom.width, geom.height))
    return result


def _monitor_bounds():
    monitors = monitor_geometries()
    if not monitors:
        return 0, 0, 0, 0
    left = min(monitor.x for monitor in monitors)
    top = min(monitor.y for monitor in monitors)
    right = max(monitor.x + monitor.width for monitor in monitors)
    bottom = max(monitor.y + monitor.height for monitor in monitors)
    return left, top, right - left, bottom - top


def monitor_workareas():
    """Area util de cada monitor (sin paneles/barras del escritorio)."""
    display = Gdk.Display.get_default()
    result = []
    if display is None:
        return result
    for index in range(display.get_n_monitors()):
        monitor = display.get_monitor(index)
        if monitor is None:
            continue
        area = monitor.get_workarea()
        result.append(Geometry(area.x, area.y, area.width, area.height))
    return result


def _workarea_bounds():
    """Rectangulo que contiene las areas utiles de todos los monitores."""
    workareas = monitor_workareas()
    if not workareas:
        return None
    left = min(area.x for area in workareas)
    top = min(area.y for area in workareas)
    right = max(area.x + area.width for area in workareas)
    bottom = max(area.y + area.height for area in workareas)
    if right - left <= 0 or bottom - top <= 0:
        return None
    return (left, top, right - left, bottom - top)


def _crop_to_workarea(image):
    """Quita de la captura el panel/barras que el escritorio reserva."""
    box = _workarea_bounds()
    if box is None:
        return image
    left, top, width, height = _logical_to_image(box, image)
    left = max(0, min(left, image.width - 1))
    top = max(0, min(top, image.height - 1))
    right = min(image.width, left + max(1, width))
    bottom = min(image.height, top + max(1, height))
    if right <= left or bottom <= top:
        return image
    return image.crop((left, top, right, bottom))


def virtual_screen_size():
    """Tamano logico del escritorio virtual (todos los monitores)."""
    if is_wayland():
        _left, _top, width, height = _monitor_bounds()
        if width > 0 and height > 0:
            return width, height
    root = Gdk.get_default_root_window()
    if root is None:
        width, height = _monitor_bounds()[2:]
        return max(1, width), max(1, height)
    return root.get_width(), root.get_height()


def _wayland_capture(include_cursor=False, interactive=False):
    """Obtiene una captura completa en Wayland usando portal o herramientas."""
    path = None
    # GNOME Shell permite incluir el cursor sin pasar por el dialogo del portal.
    if include_cursor and session.is_gnome():
        path = session.gnome_shell_screenshot(include_cursor=True)
    if path is None and include_cursor and not interactive:
        path = session.tool_screenshot(include_cursor=True, interactive=False)
    if path is None:
        path = session.portal_screenshot(
            interactive=interactive, timeout=120 if interactive else 60
        )
    if path is False:
        if interactive:
            raise CaptureCancelled()
        path = None
    if not path:
        path = session.tool_screenshot(
            include_cursor=include_cursor,
            interactive=interactive,
            timeout=120 if interactive else 60,
        )
    if not path:
        if interactive:
            raise CaptureCancelled()
        raise RuntimeError(
            "No se pudo capturar la pantalla en Wayland. Instala xdg-desktop-portal "
            "(y xdg-desktop-portal-gnome/kde/wlr) o grim."
        )
    try:
        with Image.open(path) as image:
            return image.convert("RGBA")
    finally:
        session.cleanup_temp(path)


def capture_interactive_region():
    """Captura una region mediante el selector nativo del portal.

    Devuelve una imagen RGBA recortada. Lanza ``CaptureCancelled`` si el
    usuario cancela.
    """
    if not is_wayland():
        return None
    return _wayland_capture(interactive=True)


def region_monitor_index():
    """Indice del monitor bajo el puntero (o el principal) para la vista previa."""
    display = Gdk.Display.get_default()
    if display is None:
        return 0
    count = display.get_n_monitors()
    if count <= 0:
        return 0
    try:
        x, y = get_pointer_position()
    except Exception:
        x = y = None
    if x is not None:
        for index in range(count):
            geom = display.get_monitor(index).get_geometry()
            if geom.x <= x < geom.x + geom.width and geom.y <= y < geom.y + geom.height:
                return index
    primary = display.get_primary_monitor()
    for index in range(count):
        if display.get_monitor(index) == primary:
            return index
    return 0


def region_preview_size():
    """Tamano logico del monitor activo para la vista previa del selector.

    En Wayland no se puede posicionar una ventana sobre todo el escritorio. El
    selector muestra una vista comprimida del escritorio completo en el monitor
    bajo el puntero (o el principal); en X11 se mantiene el tamano real.
    """
    if not is_wayland():
        return None
    display = Gdk.Display.get_default()
    if display is None:
        return None
    index = region_monitor_index()
    monitor = display.get_monitor(index)
    if monitor is None:
        return None
    geom = monitor.get_geometry()
    return (max(1, geom.width), max(1, geom.height))


def _logical_to_image(box, image):
    """Convierte una geometria logica de Gdk a pixeles de la captura."""
    left, top, width, height = _monitor_bounds()
    logical_w = max(1, width)
    logical_h = max(1, height)
    sx = image.width / logical_w
    sy = image.height / logical_h
    x, y, w, h = box
    return (
        int(round((x - left) * sx)),
        int(round((y - top) * sy)),
        max(1, int(round(w * sx))),
        max(1, int(round(h * sy))),
    )


def _crop_logical_box(image, box):
    x, y, width, height = _logical_to_image(box, image)
    left = max(0, min(x, image.width - 1))
    top = max(0, min(y, image.height - 1))
    right = max(left + 1, min(x + width, image.width))
    bottom = max(top + 1, min(y + height, image.height))
    return image.crop((left, top, right, bottom))


def image_to_logical_box(box, image):
    """Inverso de ``_logical_to_image``: pixeles de captura a geometria Gdk."""
    left, top, width, height = _monitor_bounds()
    sx = image.width / max(1, width)
    sy = image.height / max(1, height)
    x, y, w, h = box
    return (
        int(round(left + x / sx)),
        int(round(top + y / sy)),
        max(1, int(round(w / sx))),
        max(1, int(round(h / sy))),
    )


def capture_screen(include_cursor=False, include_panel=True):
    """Captura el escritorio completo (todos los monitores) como PIL RGBA.

    Con ``include_panel=False`` recorta el panel/barras del escritorio usando
    el area util que publica Gdk para cada monitor.
    """
    if is_wayland():
        image = _wayland_capture(include_cursor=include_cursor)
    else:
        root = Gdk.get_default_root_window()
        width, height = root.get_width(), root.get_height()
        pixbuf = Gdk.pixbuf_get_from_window(root, 0, 0, width, height)
        image = pixbuf_to_pil(pixbuf)
        if include_cursor:
            image = _composite_cursor(image, Geometry(0, 0, width, height))
    if not include_panel:
        image = _crop_to_workarea(image)
    return image


def _wayland_cached_screen(ttl=WAYLAND_CACHE_TTL):
    """Captura compartida para lupas/reglas que consultan muchas veces por segundo."""
    now = time.monotonic()
    image = _wayland_cache["image"]
    if image is not None and now - _wayland_cache["time"] < ttl:
        return image
    image = capture_screen()
    _wayland_cache["image"] = image
    _wayland_cache["time"] = now
    return image


def capture_region(x, y, width, height, base=None):
    """Captura una region concreta.

    Si ``base`` es una imagen, recorta de ella. Si es ``None``, toma la
    subregion directamente de la pantalla en X11 o recorta de una captura
    completa en Wayland (donde no existe captura de subregiones).
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

    if is_wayland():
        image = _wayland_cached_screen()
        x, y, width, height = _logical_to_image((x, y, width, height), image)
        return capture_region(x, y, width, height, base=image)

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
        return capture_screen(include_cursor=include_cursor)
    if is_wayland():
        image = capture_screen(include_cursor=include_cursor)
        return _crop_logical_box(image, geom.as_tuple())
    image = capture_region(*geom.as_tuple())
    if include_cursor:
        image = _composite_cursor(image, geom)
    return image


def capture_monitor(index, include_panel=True):
    monitors = monitor_geometries()
    if not monitors:
        return capture_screen(include_panel=include_panel)
    index = index % len(monitors)
    box = monitors[index]
    if not include_panel:
        workareas = monitor_workareas()
        if len(workareas) == len(monitors) and workareas[index].width > 0:
            box = workareas[index]
    if is_wayland():
        # Se recorta de la captura completa sin recortar para que el mapeo de
        # coordenadas siga usando los limites de los monitores.
        image = capture_screen()
        return _crop_logical_box(image, box.as_tuple())
    return capture_region(*box.as_tuple())


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
    room = max(64, min_height // 5)
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


def find_vertical_shift(
    previous,
    current,
    band_height=64,
    min_shift=1,
    max_shift=None,
    motion_reference=None,
):
    """Busca en que fila de ``previous`` encaja una banda de ``current``.

    La banda se toma del contenido que realmente se desplaza, no de la
    cabecera fija de la ventana. ``motion_reference`` permite detectar ese
    contenido comparando con el frame anterior en lugar de con la imagen
    acumulada (asi una cabecera que cambia de estilo al hacer scroll no se
    confunde con contenido movil). Se compara sobre una version reducida
    horizontalmente y se puede acotar el rango con ``min_shift``/``max_shift``.
    Devuelve ``(shift, diff)``.
    """
    band_height = min(band_height, current.height)
    width = min(previous.width, current.width)
    if width <= 0 or band_height <= 0:
        return 0, 0.0
    match_width = max(1, min(width, MATCH_WIDTH))
    previous_small = previous.convert("RGB").resize((match_width, previous.height))
    current_small = current.convert("RGB").resize((match_width, current.height))
    motion_source = previous if motion_reference is None else motion_reference
    row_diffs = _row_diff_means(motion_source, current)
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


BOTTOM_GUARD = 200

FIXED_TOP_MAX_RATIO = 0.5
FIXED_TOP_MAX_HEIGHT = 400
FIXED_TOP_MIN_HEIGHT = 12
CONTENT_ROW_RUN = 48


def _scrolling_fixed_top(frames, max_pairs=3):
    """Altura de la franja fija superior (pestanas/barra del navegador).

    Compara cada fila del frame actual con la fila que ocupaba el mismo
    contenido ``step`` filas mas arriba en el frame anterior. El contenido
    coincide (sube al hacer scroll) y la cabecera fija no, asi que la primera
    racha de filas coincidentes marca donde empieza la pagina.

    Devuelve 0 si no se detecta una franja fija clara. Se usan solo los
    primeros frames para no repetir el coste de alineacion en capturas largas.
    """
    if len(frames) < 2:
        return 0
    pairs = []
    for previous, current in zip(frames, frames[1:]):
        step, _diff = find_vertical_shift(
            previous, current, min_shift=1, max_shift=previous.height
        )
        if step <= 2 or step >= previous.height - STATIC_ROW_RUN:
            continue
        pairs.append((previous, current, step))
        if len(pairs) >= max_pairs:
            break
    if not pairs:
        return 0

    limit = min(
        int(frames[0].height * FIXED_TOP_MAX_RATIO),
        FIXED_TOP_MAX_HEIGHT,
        min(previous.height - step for previous, _current, step in pairs),
        min(current.height for _previous, current, _step in pairs),
    )
    if limit <= CONTENT_ROW_RUN:
        return 0

    rows_by_pair = []
    for previous, current, step in pairs:
        width = min(previous.width, current.width)
        # previous[step + y] es el contenido que ahora ocupa current[y].
        old_content = previous.crop((0, step, width, step + limit))
        new_content = current.crop((0, 0, width, limit))
        rows_by_pair.append(_row_diff_means(old_content, new_content))

    count = min(len(rows) for rows in rows_by_pair)
    scores = []
    for y in range(count):
        values = sorted(rows[y] for rows in rows_by_pair)
        scores.append(values[len(values) // 2])

    run = 0
    for y, score in enumerate(scores):
        if score <= STATIC_ROW_THRESHOLD:
            run += 1
            if run >= CONTENT_ROW_RUN:
                top = y - CONTENT_ROW_RUN + 1
                return top if top >= FIXED_TOP_MIN_HEIGHT else 0
        else:
            run = 0
    return 0


def _append_vertical(result, part):
    if part.height <= 0:
        return result
    combined = Image.new(
        "RGBA", (max(result.width, part.width), result.height + part.height), (0, 0, 0, 0)
    )
    combined.alpha_composite(result, (0, 0))
    combined.alpha_composite(part, (0, result.height))
    return combined


def stitch_vertical(frames):
    """Une capturas verticales con solape en una sola imagen (Pillow)."""
    frames = [frame.convert("RGBA") for frame in frames if frame is not None]
    if not frames:
        return None
    first = frames[0]
    if len(frames) == 1:
        return first
    result = None
    previous_frame = first
    total_shift = 0
    for frame in frames[1:]:
        # Comparar solo con el frame anterior (mucho solape) evita acumular
        # errores y que una animacion congelada en la imagen acumulada
        # contamine las alineaciones siguientes.
        step, diff = find_vertical_shift(
            previous_frame,
            frame,
            min_shift=1,
            max_shift=previous_frame.height,
        )
        if step <= 2:
            previous_frame = frame
            continue
        # No tomar el borde inferior de cada frame: ahi suelen vivir botones
        # fijos ("volver arriba", chat...). Ese contenido se recupera del
        # frame siguiente, donde ya ha subido y no esta tapado. El margen no
        # puede superar el solape disponible con el frame siguiente.
        guard = min(BOTTOM_GUARD, max(0, frame.height - step - 4))
        if result is None:
            first_guard = min(BOTTOM_GUARD, max(0, first.height - step - 4))
            result = first.crop(
                (0, 0, first.width, first.height - first_guard)
            )
        total_shift += step
        start = max(0, result.height - total_shift)
        end = frame.height - guard
        if end > start:
            result = _append_vertical(result, frame.crop((0, start, frame.width, end)))
        previous_frame = frame
    if result is None:
        return first
    # El ultimo trozo (incluido el borde inferior) se toma una sola vez.
    last = frames[-1]
    start = max(0, result.height - total_shift)
    if start < last.height:
        result = _append_vertical(result, last.crop((0, start, last.width, last.height)))
    return result


SCROLL_DIFF = 0.4


def _wayland_scroll_active_window(times=1, geom=None):
    """Intenta desplazar la ventana activa con ydotool/wlrctl en Wayland."""
    if geom is None:
        geom = active_window_geometry()
    if geom is None or geom.width <= 0 or geom.height <= 0:
        return False
    target_x = geom.x + geom.width // 2
    target_y = geom.y + geom.height // 2

    if session.which("ydotool"):
        moved = session.run_command(
            ["ydotool", "mousemove", "--absolute", "-x", str(target_x), "-y", str(target_y)],
            timeout=5,
        )
        if moved is not None and moved.returncode == 0:
            for _ in range(times):
                session.run_command(
                    ["ydotool", "mousemove", "--wheel", "-y", "120"], timeout=5
                )
            return True

    if session.which("wlrctl"):
        result = session.run_command(
            ["wlrctl", "pointer", "move", str(target_x), str(target_y)], timeout=5
        )
        if result is not None and result.returncode == 0:
            for _ in range(times):
                session.run_command(["wlrctl", "pointer", "scroll", "0", "120"], timeout=5)
            return True
    return False


def _scroll_active_window(times=1, geom=None):
    """Envia rueda de scroll hacia abajo sobre el centro de la ventana.

    XTest entrega la rueda a la ventana que esta bajo el puntero, no a la
    ventana activa. Si el puntero esta sobre la barra de imageWatcher (o
    cualquier otra ventana) el destino no se desplaza y la captura se queda
    con la parte visible. Se mueve el puntero al centro de la ventana y se
    restaura al terminar.

    En Wayland se usa ydotool o wlrctl si estan instalados; sin ellos el
    desplazamiento no es posible porque no hay inyeccion global estandar.
    """
    if is_wayland():
        return _wayland_scroll_active_window(times, geom)
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


def capture_scrolling_window(max_scrolls=100, trim_header=True):
    """Captura una ventana larga desplazandola y empalmando con Pillow.

    ``max_scrolls`` es solo un limite de seguridad: el bucle termina antes al
    llegar al final de la pagina (cuando la rueda ya no la desplaza).

    Con ``trim_header`` se recorta la franja fija superior (pestanas y barra
    de direcciones del navegador, por ejemplo) del resultado final.
    """
    geom = active_window_geometry()
    if geom is None:
        return capture_screen()
    frames = [capture_region(*geom.as_tuple())]
    stalls = 0
    for _ in range(max_scrolls):
        previous = frames[-1]
        if not _scroll_active_window(1, geom=geom):
            break
        frame = _capture_settled(geom, previous)
        step, _diff = find_vertical_shift(
            previous, frame, min_shift=1, max_shift=geom.height
        )
        if _mean_abs_diff(previous, frame) < SCROLL_DIFF or step <= 2:
            # Puede ser el final de la pagina o una carga/animacion temporal.
            # Reintentar antes de darla por terminada.
            stalls += 1
            if stalls >= 3:
                break
            time.sleep(0.15)
            continue
        stalls = 0
        frames.append(frame)
    result = stitch_vertical(frames)
    if trim_header and result is not None:
        top = _scrolling_fixed_top(frames)
        if 0 < top < result.height:
            result = result.crop((0, top, result.width, result.height))
    return result



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


def _x11_active_window_geometry():
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


def _geometry_from_rect(rect, title=""):
    try:
        x, y, width, height = (int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3]))
    except Exception:
        return None
    if width <= 0 or height <= 0:
        return None
    geometry = Geometry(x, y, width, height)
    geometry.title = title
    return geometry


def _sway_tree():
    return session.json_command(["swaymsg", "-t", "get_tree", "-r"], timeout=5)


def _sway_windows(tree, focused_only=False):
    result = []

    def walk(node):
        if not isinstance(node, dict):
            return
        if node.get("type") in ("con", "floating_con") and node.get("pid"):
            if not focused_only or node.get("focused"):
                rect = node.get("rect") or {}
                geometry = _geometry_from_rect(
                    (
                        rect.get("x", 0),
                        rect.get("y", 0),
                        rect.get("width", 0),
                        rect.get("height", 0),
                    ),
                    node.get("name") or node.get("app_id") or "",
                )
                if geometry is not None:
                    result.append(geometry)
        for key in ("nodes", "floating_nodes"):
            for child in node.get(key, []) or []:
                walk(child)

    walk(tree)
    return result


def _hyprland_windows(focused_only=False):
    data = session.json_command(["hyprctl", "clients", "-j"], timeout=5)
    if not isinstance(data, list):
        return []
    result = []
    for item in data:
        if item.get("hidden") or item.get("mapped") is False:
            continue
        if focused_only and not item.get("focused"):
            continue
        at = item.get("at") or [0, 0]
        size = item.get("size") or [0, 0]
        geometry = _geometry_from_rect(
            (at[0], at[1], size[0], size[1]),
            item.get("title") or item.get("class") or "",
        )
        if geometry is not None:
            result.append(geometry)
    return result


def _gnome_windows(focused_only=False):
    """Intenta leer ventanas de GNOME Shell. Eval suele estar deshabilitado."""
    script = (
        "JSON.stringify(global.get_window_actors().map(a=>a.meta_window)"
        ".filter(w=>!w.is_skip_taskbar()).map(w=>{"
        "let r=w.get_frame_rect();"
        "return {x:r.x,y:r.y,width:r.width,height:r.height,"
        "title:w.get_title(),focused:w.has_focus()};}))"
    )
    bus = None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        reply = bus.call_sync(
            "org.gnome.Shell",
            "/org/gnome/Shell",
            "org.gnome.Shell",
            "Eval",
            GLib.Variant("(s)", (script,)),
            GLib.VariantType.new("(bs)"),
            Gio.DBusCallFlags.NONE,
            5000,
            None,
        )
        success, payload = reply.unpack()
        if not success:
            return []
        data = json.loads(payload)
    except Exception:
        return []
    result = []
    for item in data or []:
        if focused_only and not item.get("focused"):
            continue
        geometry = _geometry_from_rect(
            (item.get("x", 0), item.get("y", 0), item.get("width", 0), item.get("height", 0)),
            item.get("title") or "",
        )
        if geometry is not None:
            result.append(geometry)
    return result


def _kdotool_geometry(output):
    values = {}
    for line in (output or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip()
    return _geometry_from_rect(
        (
            values.get("x", 0),
            values.get("y", 0),
            values.get("width", 0),
            values.get("height", 0),
        )
    )


def _kdotool_windows(focused_only=False):
    """Soporte opcional para KDE mediante kdotool."""
    if not session.which("kdotool"):
        return []
    if focused_only:
        geometry = _kdotool_geometry(
            session.command_output(
                ["kdotool", "getactivewindow", "getwindowgeometry", "--shell"],
                timeout=5,
            )
        )
        return [geometry] if geometry is not None else []
    ids = session.command_output(
        ["kdotool", "search", "--onlyvisible", "--name", ""], timeout=5
    )
    result = []
    for window_id in (ids or "").split():
        geometry = _kdotool_geometry(
            session.command_output(
                ["kdotool", "getwindowgeometry", "--shell", window_id], timeout=5
            )
        )
        if geometry is not None:
            result.append(geometry)
    return result


def _wayland_windows(focused_only=False):
    if session.is_sway():
        tree = _sway_tree()
        if tree is not None:
            return _sway_windows(tree, focused_only=focused_only)
    if session.is_hyprland():
        windows = _hyprland_windows(focused_only=focused_only)
        if windows:
            return windows
    if session.is_gnome():
        windows = _gnome_windows(focused_only=focused_only)
        if windows:
            return windows
    if session.is_kde():
        windows = _kdotool_windows(focused_only=focused_only)
        if windows:
            return windows
    return []


def active_window_geometry():
    """Geometria (x, y, w, h) de la ventana activa incluyendo marco."""
    if is_wayland():
        windows = _wayland_windows(focused_only=True)
        return windows[0] if windows else None
    return _x11_active_window_geometry()


def list_windows():
    """Lista de ventanas con nombre y geometria (puede estar vacia en Wayland)."""
    if is_wayland():
        return _wayland_windows(focused_only=False)

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


def window_at(x, y):
    """Ventana (x, y, w, h) bajo un punto, de la mas alta a la mas baja."""
    if is_wayland():
        for window in reversed(list_windows()):
            if (
                window.x <= x < window.x + window.width
                and window.y <= y < window.y + window.height
            ):
                return window.as_tuple()
        return None
    try:
        from Xlib import X

        d = _x11_display()
        root = d.screen().root
        child = root
        while True:
            try:
                result = child.query_tree().children
            except Exception:
                break
            found = None
            for candidate in reversed(result):
                try:
                    cx, cy = _root_coords(candidate, root)
                    geom = candidate.get_geometry()
                    if cx <= x < cx + geom.width and cy <= y < cy + geom.height:
                        found = candidate
                        break
                except Exception:
                    continue
            if found is None:
                break
            child = found
            try:
                if child.query_tree().parent.id == root.id:
                    break
            except Exception:
                break
        cx, cy = _root_coords(child, root)
        geom = child.get_geometry()
        return (cx, cy, geom.width, geom.height)
    except Exception:
        return None


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
