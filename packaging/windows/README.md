# Empaquetado para Windows (.exe)

Genera `imageWatcher.exe` con PyInstaller:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1
```

Salida: `dist\imageWatcher.exe`

## Importante: limitacion real

Este clon esta escrito contra **X11** (captura con Gdk/Xlib, atajos con
`XGrabKey`, grabacion con `ffmpeg x11grab`). Por eso el `.exe` se **compila**
pero **no es funcional en Windows** salvo que se implemente un backend Windows
(captura via Win32/GDI+, atajos con `RegisterHotKey`, grabacion con `gdigrab`).

El spec y el script se incluyen para dejar el pipeline listo y reproducible.
Para tener un `.exe` que realmente funcione hay que:

1. Abstraer el backend de captura en `imagewatcher/capture.py` (interfaz comun).
2. Anadir `imagewatcher/platform/windows.py` con captura `win32`/`mss` y `RegisterHotKey`.
3. Sustituir `ffmpeg x11grab` por `ffmpeg gdigrab` en `imagewatcher/recorder.py`.

## Requisitos del Python de compilacion

PyGObject no tiene wheels oficiales en PyPI para Windows. Opciones:

- **MSYS2**: instala `mingw-w64-x86_64-python-gobject` y compila con el Python de MSYS2.
- **gvsbuild**: compila GTK3 + PyGObject para el Python nativo de Windows.

Sin `gi` disponible, `PyInstaller` avisa y el `.exe` resultante no arrancara.

## Icono

Si existe `packaging/assets/imagewatcher.ico` se usa como icono del ejecutable.
