# -*- mode: python ; coding: utf-8 -*-
# Spec de PyInstaller para generar imageWatcher.exe en Windows.
#
# Requiere PyGObject + GTK3 instalados en el interprete de Windows
# (MSYS2/gvsbuild). Ver packaging/windows/README.md.
import os

spec_dir = os.path.dirname(os.path.abspath(SPEC))
project_root = os.path.abspath(os.path.join(spec_dir, "..", ".."))
icon_path = os.path.join(spec_dir, "..", "assets", "imagewatcher.ico")

hiddenimports = [
    "imagewatcher",
    "imagewatcher.app",
    "imagewatcher.capture",
    "imagewatcher.region",
    "imagewatcher.editor",
    "imagewatcher.recorder",
    "imagewatcher.hotkeys",
    "imagewatcher.config",
    "imagewatcher.gtk_util",
    "imagewatcher.tools.color_picker",
    "imagewatcher.tools.magnifier",
    "imagewatcher.tools.ruler",
    "imagewatcher.tools.crosshair",
    "imagewatcher.tools.protractor",
    "imagewatcher.tools.whiteboard",
    "gi",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.GdkPixbuf",
    "gi.repository.GLib",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageFilter",
    "PIL.ImageEnhance",
    "PIL.ImageOps",
    "Xlib",
    "Xlib.display",
]

try:
    from PyInstaller.utils.hooks import collect_data_files, collect_submodules

    hiddenimports += collect_submodules("gi")
    hiddenimports += collect_submodules("PIL")
    datas = collect_data_files("gi")
except Exception:
    datas = []

a = Analysis(
    [os.path.join(spec_dir, "entry.py")],
    pathex=[project_root],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="imageWatcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
)
