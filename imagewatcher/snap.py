"""Lineas de acople (imanes) para selecciones sobre el escritorio.

Combina bordes de pantalla, bordes de ventanas y lineas fuertes de texto/UI
detectadas en una captura. Se usa en el punto de mira y en la captura por
region.
"""
from PIL import Image, ImageFilter

SNAP_DISTANCE = 12
SNAP_EDGE_LINES = 32
SNAP_EDGE_WIDTH = 480


def peak_lines(values, scale, max_lines=SNAP_EDGE_LINES):
    if not values:
        return []
    top = max(values)
    if top <= 0:
        return []
    average = sum(values) / len(values)
    threshold = max(16.0, average * 1.5)
    ranked = sorted(
        ((value, index) for index, value in enumerate(values) if value >= threshold),
        reverse=True,
    )
    chosen = []
    for _value, index in ranked:
        if all(abs(index - other) >= 3 for other in chosen):
            chosen.append(index)
            if len(chosen) >= max_lines:
                break
    return [index * scale for index in chosen]


def detect_screen_lines(image, max_lines=SNAP_EDGE_LINES, sample_width=SNAP_EDGE_WIDTH):
    """Devuelve (lineas_x, lineas_y) de bordes fuertes de la imagen."""
    if image is None:
        return [], []
    width, height = image.size
    if width <= 0 or height <= 0:
        return [], []
    scale = max(1, round(width / sample_width))
    small = image.convert("L").resize(
        (max(1, width // scale), max(1, height // scale))
    )
    edges = small.filter(ImageFilter.FIND_EDGES)
    resample = getattr(Image, "Resampling", Image).BOX
    rows = list(edges.resize((1, edges.height), resample).getdata())
    columns = list(edges.resize((edges.width, 1), resample).getdata())
    return (
        peak_lines(columns, scale, max_lines),
        peak_lines(rows, scale, max_lines),
    )


def build_snap_lines(image, include_windows=True, max_lines=SNAP_EDGE_LINES):
    """Lineas candidatas ordenadas para acoplar una seleccion."""
    xs = set()
    ys = set()
    if image is None:
        return [], []
    width, height = image.size
    xs.update((0, max(0, width - 1)))
    ys.update((0, max(0, height - 1)))
    if include_windows:
        try:
            from .capture import list_windows

            for window in list_windows():
                xs.update((window.x, window.x + window.width - 1))
                ys.update((window.y, window.y + window.height - 1))
        except Exception:
            pass
    try:
        edge_x, edge_y = detect_screen_lines(image, max_lines=max_lines)
        xs.update(edge_x)
        ys.update(edge_y)
    except Exception:
        pass
    return (
        sorted(x for x in xs if 0 <= x < width),
        sorted(y for y in ys if 0 <= y < height),
    )


def snap_value(value, lines, distance=SNAP_DISTANCE):
    best = None
    for line in lines:
        delta = abs(line - value)
        if delta <= distance and (best is None or delta < abs(best - value)):
            best = line
    return value if best is None else best
