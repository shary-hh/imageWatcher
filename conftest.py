"""Configuracion global de pytest para imageWatcher.

Anade el proyecto al sys.path y expone fixtures para GTK y para procesar el
bucle de eventos. Si no hay servidor grafico, se saltan los tests.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS = os.path.join(ROOT, "arena", "tests")
for _path in (ROOT, TESTS):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def gtk_environment():
    """Inicializa GTK una vez; salta los tests si no hay DISPLAY."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gtk

    if not Gtk.init_check([]):
        pytest.skip("No hay servidor grafico disponible (DISPLAY)", allow_module_level=False)
    return Gtk


@pytest.fixture
def pump():
    """Ejecuta el bucle principal de GLib durante N milisegundos."""
    from gi.repository import GLib

    def _pump(milliseconds=150):
        loop = GLib.MainLoop()
        GLib.timeout_add(milliseconds, loop.quit)
        loop.run()

    return _pump
