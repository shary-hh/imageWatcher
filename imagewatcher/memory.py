"""Ayudas para devolver memoria al sistema tras cerrar ventanas grandes."""
import ctypes
import gc

try:
    _malloc_trim = ctypes.CDLL("libc.so.6").malloc_trim
except Exception:
    # No es glibc (musl, macOS...) o no esta disponible.
    _malloc_trim = None


def trim_memory():
    """Recolecta ciclos de Python y libera las arenas libres de glibc.

    Pillow y GTK crean imagenes grandes que Python y el asignador de la libc
    pueden retener aunque ya no se usen. Llamar a esta funcion al cerrar un
    editor o una herramienta devuelve esa memoria al sistema.
    """
    gc.collect()
    if _malloc_trim is not None:
        try:
            _malloc_trim(0)
        except Exception:
            pass
