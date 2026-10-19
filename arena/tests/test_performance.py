"""Tests de rendimiento (presupuestos) para evitar regresiones de fluidez."""
import time

import cairo
import pytest

from imagewatcher import capture
from imagewatcher.tools.overlay import open_overlay


def test_capture_region_is_fast():
    """Una subregion no debe capturar toda la pantalla (presupuesto 60 ms)."""
    capture.capture_region(0, 0, 8, 8)  # calentar
    start = time.perf_counter()
    for _ in range(10):
        capture.capture_region(100, 100, 16, 16)
    per_call = (time.perf_counter() - start) / 10
    assert per_call < 0.06, f"capture_region lenta: {per_call*1000:.0f} ms"


@pytest.mark.parametrize("mode", ["crosshair", "ruler", "protractor", "magnifier"])
def test_overlay_draw_budget(pump, mode):
    overlay = open_overlay(mode)
    try:
        pump(150)
        allocation = overlay.get_allocation()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, allocation.width, allocation.height)
        context = cairo.Context(surface)
        overlay._on_draw(overlay.area, context)
        start = time.perf_counter()
        for _ in range(5):
            overlay._on_draw(overlay.area, context)
        per_frame = (time.perf_counter() - start) / 5
        assert per_frame < 0.02, f"draw {mode} lento: {per_frame*1000:.1f} ms"
    finally:
        overlay.destroy()
        pump(50)


def test_idle_tick_does_not_capture(monkeypatch):
    """Si el puntero no se mueve, el tick no debe capturar ni repintar."""
    from imagewatcher.tools import magnifier

    panel = magnifier.MagnifierPanel()
    calls = {"captures": 0, "draws": 0}

    def fake_capture(*args, **kwargs):
        calls["captures"] += 1
        return capture.capture_screen()

    monkeypatch.setattr(magnifier, "capture_region", fake_capture)
    monkeypatch.setattr(magnifier, "get_pointer_position", lambda: (50, 50))
    panel.area.queue_draw = lambda *a, **k: calls.__setitem__("draws", calls["draws"] + 1)

    panel._tick()  # primer tick: detecta posicion
    panel._tick()  # segundo tick: misma posicion -> sin trabajo
    panel._tick()
    assert calls["captures"] == 1
    assert calls["draws"] == 1
