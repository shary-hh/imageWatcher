"""Pruebas del backend de captura."""
import time

import pytest

from imagewatcher import capture
from imagewatcher.gtk_util import pil_to_pixbuf, pixbuf_to_pil


def test_screen_geometry():
    width, height = capture.virtual_screen_size()
    assert width > 0
    assert height > 0


def test_capture_screen_full():
    width, height = capture.virtual_screen_size()
    image = capture.capture_screen()
    assert image.mode == "RGBA"
    assert image.size == (width, height)


def test_monitor_geometries():
    monitors = capture.monitor_geometries()
    assert len(monitors) >= 1
    assert all(monitor.width > 0 and monitor.height > 0 for monitor in monitors)


def test_capture_region_from_base():
    base = capture.capture_screen()
    region = capture.capture_region(10, 10, 120, 80, base=base)
    assert region.size == (120, 80)


def test_capture_region_direct_does_not_recapture_screen():
    """La captura de una subregion debe ser rapida (no capturar toda la pantalla)."""
    capture.capture_region(0, 0, 8, 8)  # calentar
    start = time.perf_counter()
    for _ in range(5):
        region = capture.capture_region(50, 50, 16, 16)
    per_call = (time.perf_counter() - start) / 5
    assert region.size == (16, 16)
    assert per_call < 0.1, f"captura de region demasiado lenta: {per_call*1000:.0f} ms"


def test_capture_window_and_listing():
    image = capture.capture_window(include_cursor=True)
    assert image.width > 0
    capture.active_window_geometry()
    assert isinstance(capture.list_windows(), list)


def test_window_coordinates_are_not_inverted():
    """La geometria de una ventana debe ser su posicion real en la raiz.

    ``translate_coords`` traduce desde su primer argumento hacia la ventana
    receptora; llamarlo en la ventana pasando la raiz devuelve la posicion con
    signo cambiado y la captura acaba tomando una region fuera de la ventana.
    """
    from Xlib import X, display

    xdisplay = display.Display()
    root = xdisplay.screen().root
    win = root.create_window(
        123,
        87,
        40,
        30,
        0,
        xdisplay.screen().root_depth,
        X.InputOutput,
        X.CopyFromParent,
        override_redirect=True,
        background_pixel=xdisplay.screen().white_pixel,
    )
    try:
        xdisplay.sync()
        assert capture._root_coords(win, root) == (123, 87)
    finally:
        win.destroy()
        xdisplay.sync()
        xdisplay.close()


def test_pixbuf_roundtrip():
    base = capture.capture_screen()
    back = pixbuf_to_pil(pil_to_pixbuf(base))
    assert back.size == base.size
    assert back.mode == "RGBA"


@pytest.mark.parametrize("include_cursor", [False, True])
def test_capture_variants(include_cursor):
    image = capture.capture_window(include_cursor=include_cursor)
    assert image.mode == "RGBA"


def _noise_image(width, height, seed=42):
    import random

    from PIL import Image

    random.seed(seed)
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (random.randrange(256), random.randrange(256), random.randrange(256))
            for _ in range(width * height)
        ]
    )
    return image


def test_find_vertical_shift():
    base = _noise_image(120, 600)
    previous = base.crop((0, 0, 120, 300)).convert("RGBA")
    current = base.crop((0, 220, 120, 520)).convert("RGBA")
    shift, _diff = capture.find_vertical_shift(previous, current)
    assert shift == 220


def test_scroll_targets_active_window_center(monkeypatch):
    """La rueda debe enviarse sobre la ventana, no donde este el puntero."""
    from types import SimpleNamespace

    from Xlib.ext import xtest

    warps = []
    events = []
    pointer = SimpleNamespace(root_x=6, root_y=7)
    root = SimpleNamespace(
        query_pointer=lambda: pointer,
        warp_pointer=lambda x, y: warps.append((x, y)),
    )
    screen = SimpleNamespace(root=root, width_in_pixels=1920, height_in_pixels=1080)
    display = SimpleNamespace(screen=lambda: screen, sync=lambda: None)
    monkeypatch.setattr(capture, "_x11_display", lambda: display)
    monkeypatch.setattr(xtest, "fake_input", lambda *args: events.append(args))

    geometry = capture.Geometry(100, 60, 400, 200)
    assert capture._scroll_active_window(1, geometry) is True
    assert warps[0] == (300, 160)
    assert warps[-1] == (6, 7)
    assert len(events) == 2


def test_scroll_stitch_ignores_static_header():
    """Una cabecera fija (p. ej. la barra del navegador) no debe impedir el empalme."""
    from PIL import Image

    base = _noise_image(120, 900)
    header = _noise_image(120, 80, seed=7)
    frame1 = Image.new("RGB", (120, 480))
    frame1.paste(header, (0, 0))
    frame1.paste(base.crop((0, 0, 120, 400)), (0, 80))
    frame2 = Image.new("RGB", (120, 480))
    frame2.paste(header, (0, 0))
    frame2.paste(base.crop((0, 160, 120, 560)), (0, 80))

    shift, _diff = capture.find_vertical_shift(frame1, frame2)
    assert shift == 160
    stitched = capture.stitch_vertical([frame1, frame2])
    assert stitched.height == 640


def test_stitch_vertical_reconstructs_long_window():
    base = _noise_image(120, 600)
    frames = [
        base.crop((0, 0, 120, 300)).convert("RGBA"),
        base.crop((0, 220, 120, 520)).convert("RGBA"),
        base.crop((0, 440, 120, 600)).convert("RGBA"),
    ]
    stitched = capture.stitch_vertical(frames)
    assert stitched.width == 120
    assert 590 <= stitched.height <= 610

