# Packaging

Scripts para generar los paquetes del imageWatcher.

| Script | Salida |
| --- | --- |
| `build_deb.sh` | `dist/imagewatcher_<version>_all.deb` |
| `build_appimage.sh` | `dist/imageWatcher-<version>-x86_64.AppImage` |
| `build_flatpak.sh` | `dist/imageWatcher-<version>-x86_64.flatpak` |
| `build_rpm.sh` | `dist/imagewatcher-<version>-1.<dist>.noarch.rpm` |
| `windows/build_exe.ps1` | `dist/imageWatcher.exe` (ver limitacion en `windows/README.md`) |

## Uso

```bash
chmod +x packaging/*.sh
packaging/build_deb.sh
packaging/build_appimage.sh
packaging/build_flatpak.sh
packaging/build_rpm.sh
```

La version se toma automaticamente de `imagewatcher/__init__.py`, asi que basta con
incrementarla ahi antes de empaquetar.

## Dependencias de compilacion

- `.deb`: `dpkg-deb` (paquete `dpkg`, ya presente en Mint).
- AppImage: `curl` y, la primera vez, descarga `appimagetool` a `build/`.
- Flatpak: `flatpak` y el runtime `org.gnome.Platform//50` (incluye Python 3,
  PyGObject, GTK3 y ffmpeg). No necesita `flatpak-builder` ni SDK: el script
  arma el AppDir y usa `flatpak build-finish`, `build-export` y `build-bundle`.
  Descarga ruedas fijadas de Pillow, python-xlib y six.
- RPM: `rpmbuild` o Docker (el script usa `fedora:41` si no hay `rpmbuild`).
  En Fedora instala `rpm-build`, `python3-devel`, `python3-setuptools`,
  `python3-wheel` y `pyproject-rpm-macros`.
- `.exe`: se compila en Windows con PyInstaller; ver `windows/README.md`.

## Notas

- El `.deb` y el AppImage son **ligeros**: usan el Python+GTK del sistema
  (`python3-gi`, `gir1.2-gtk-3.0`, `python3-pil`, `python3-xlib`, `ffmpeg`),
  declarados como dependencias del paquete. En Wayland se recomienda ademas
  `xdg-desktop-portal` (+ backend del escritorio) y, en wlroots,
  `grim`/`slurp`/`wf-recorder`.
- El Flatpak usa el runtime `org.gnome.Platform//50` e incluye Pillow,
  python-xlib y six dentro del paquete. `ffmpeg` y GTK3 ya vienen en el runtime.
  En Wayland, la grabacion con `wf-recorder` no esta disponible dentro del
  sandbox (no se empaqueta); en GNOME se usa la API de GNOME Shell y en X11
  funciona `ffmpeg`.
- El RPM es `noarch` y declara las dependencias de Fedora (`python3-gobject`,
  `python3-pillow`, `python3-xlib`, `gtk3` y `ffmpeg` o `ffmpeg-free`).
  `build_rpm.sh` puede construirlo en un contenedor Fedora si no hay
  `rpmbuild` en el host.
- El AppImage asume esas dependencias presentes en el sistema (habitual en
  Linux Mint). Si quieres uno 100% autocontenido habria que empaquetar
  CPython + GTK + typelibs con linuxdeploy, lo que multiplica el tamano.
