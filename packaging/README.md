# Packaging

Scripts para generar los paquetes del imageWatcher.

| Script | Salida |
| --- | --- |
| `build_deb.sh` | `dist/imagewatcher_<version>_all.deb` |
| `build_appimage.sh` | `dist/imageWatcher-<version>-x86_64.AppImage` |
| `windows/build_exe.ps1` | `dist/imageWatcher.exe` (ver limitacion en `windows/README.md`) |

## Uso

```bash
chmod +x packaging/*.sh
packaging/build_deb.sh
packaging/build_appimage.sh
```

La version se toma automaticamente de `imagewatcher/__init__.py`, asi que basta con
incrementarla ahi antes de empaquetar.

## Dependencias de compilacion

- `.deb`: `dpkg-deb` (paquete `dpkg`, ya presente en Mint).
- AppImage: `curl` y, la primera vez, descarga `appimagetool` a `build/`.
- `.exe`: se compila en Windows con PyInstaller; ver `windows/README.md`.

## Notas

- El `.deb` y el AppImage son **ligeros**: usan el Python+GTK del sistema
  (`python3-gi`, `gir1.2-gtk-3.0`, `python3-pil`, `python3-xlib`, `ffmpeg`),
  declarados como dependencias del paquete.
- El AppImage asume esas dependencias presentes en el sistema (habitual en
  Linux Mint). Si quieres uno 100% autocontenido habria que empaquetar
  CPython + GTK + typelibs con linuxdeploy, lo que multiplica el tamano.
