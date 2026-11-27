#!/usr/bin/env bash
# Construye un paquete Flatpak (bundle .flatpak) de imageWatcher.
#
# Usa el runtime org.gnome.Platform (que ya incluye Python 3, PyGObject, GTK3
# y ffmpeg) y empaqueta solo Pillow y python-xlib como dependencias Python.
#
# Resultado: dist/imageWatcher-<version>-x86_64.flatpak
#
# No necesita flatpak-builder ni SDK: arma el AppDir con flatpak build-finish
# y lo exporta con build-export/build-bundle.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

APP_ID="io.github.shary_hh.imagewatcher"
RUNTIME_VERSION="${FLATPAK_RUNTIME_VERSION:-50}"
PYTHON_VERSION="3.13"
FP_DIR="$BUILD_DIR/flatpak"
APPDIR="$FP_DIR/app"
REPO="$FP_DIR/repo"
WHEEL_DIR="$FP_DIR/wheels"
SITE_PACKAGES="$APPDIR/files/lib/python$PYTHON_VERSION/site-packages"

# Ruedas fijadas para que el paquete sea reproducible.
PILLOW_URL="https://files.pythonhosted.org/packages/ef/fe/f5cdaa2d1c4086e757430f368c271a58ee29cfe7378e7ae7b9d964015c25/pillow-13.0.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PILLOW_SHA="5f56499c1a74d2b862beb0c33b8016f99d095858455df9d21583bbbc1c15b582"
PILLOW_FILE="pillow-13.0.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
XLIB_URL="https://files.pythonhosted.org/packages/fc/b8/ff33610932e0ee81ae7f1269c890f697d56ff74b9f5b2ee5d9b7fa2c5355/python_xlib-0.33-py2.py3-none-any.whl"
XLIB_SHA="c3534038d42e0df2f1392a1b30a15a4ff5fdc2b86cfa94f072bf11b10a164398"
XLIB_FILE="python_xlib-0.33-py2.py3-none-any.whl"
SIX_URL="https://files.pythonhosted.org/packages/b7/ce/149a00dd41f10bc29e5921b496af8b574d8413afcd5e30dfa0ed46c2cc5e/six-1.17.0-py2.py3-none-any.whl"
SIX_SHA="4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"
SIX_FILE="six-1.17.0-py2.py3-none-any.whl"

if ! command -v flatpak >/dev/null 2>&1; then
    warn "flatpak no esta instalado."
    exit 1
fi
if ! flatpak info "org.gnome.Platform/x86_64/$RUNTIME_VERSION" >/dev/null 2>&1; then
    warn "Falta el runtime org.gnome.Platform $RUNTIME_VERSION."
    warn "Instalalo con: flatpak install --user flathub org.gnome.Platform//$RUNTIME_VERSION"
    exit 1
fi

log "Empaquetando $APP_NAME $VERSION como Flatpak"

rm -rf "$FP_DIR"
mkdir -p "$WHEEL_DIR" "$SITE_PACKAGES" \
    "$APPDIR/files/bin" \
    "$APPDIR/files/share/applications" \
    "$APPDIR/files/share/icons/hicolor/scalable/apps" \
    "$APPDIR/files/share/metainfo" \
    "$APPDIR/files/share/doc/$PKG_NAME"

download_wheel() {
    local url="$1" expected="$2" filename="$3"
    local target="$WHEEL_DIR/$filename"
    if [ -f "$target" ] && echo "$expected  $target" | sha256sum -c - >/dev/null 2>&1; then
        return
    fi
    log "Descargando $filename"
    curl -fL --retry 3 -o "$target" "$url"
    echo "$expected  $target" | sha256sum -c -
}

download_wheel "$PILLOW_URL" "$PILLOW_SHA" "$PILLOW_FILE"
download_wheel "$XLIB_URL" "$XLIB_SHA" "$XLIB_FILE"
download_wheel "$SIX_URL" "$SIX_SHA" "$SIX_FILE"

python3 - "$WHEEL_DIR" "$SITE_PACKAGES" <<'PY'
import glob
import os
import sys
import zipfile

wheel_dir, destination = sys.argv[1], sys.argv[2]
os.makedirs(destination, exist_ok=True)
for path in sorted(glob.glob(os.path.join(wheel_dir, "*.whl"))):
    with zipfile.ZipFile(path) as wheel:
        wheel.extractall(destination)
PY

# Codigo de la aplicacion.
cp -r "$ROOT_DIR/imagewatcher" "$SITE_PACKAGES/"
find "$SITE_PACKAGES" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SITE_PACKAGES" -name '*.pyc' -delete

cat > "$APPDIR/files/bin/$PKG_NAME" <<EOF
#!/bin/sh
export PYTHONPATH="/app/lib/python$PYTHON_VERSION/site-packages\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m imagewatcher "\$@"
EOF
chmod 755 "$APPDIR/files/bin/$PKG_NAME"

cp "$PACKAGING_DIR/assets/imagewatcher.svg" \
    "$APPDIR/files/share/icons/hicolor/scalable/apps/$APP_ID.svg"
cp "$PACKAGING_DIR/flatpak/$APP_ID.desktop" \
    "$APPDIR/files/share/applications/$APP_ID.desktop"
cp "$PACKAGING_DIR/flatpak/$APP_ID.metainfo.xml" \
    "$APPDIR/files/share/metainfo/$APP_ID.metainfo.xml"
cp "$ROOT_DIR/README.md" "$APPDIR/files/share/doc/$PKG_NAME/README.md"

cat > "$APPDIR/metadata" <<EOF
[Application]
name=$APP_ID
runtime=org.gnome.Platform/x86_64/$RUNTIME_VERSION
sdk=org.gnome.Sdk/x86_64/$RUNTIME_VERSION
command=$PKG_NAME
EOF

flatpak build-finish "$APPDIR" \
    --command="$PKG_NAME" \
    --share=ipc \
    --socket=x11 \
    --socket=wayland \
    --socket=pulseaudio \
    --device=dri \
    --filesystem=xdg-pictures \
    --filesystem=xdg-download \
    --filesystem=xdg-config/imagewatcher:create \
    --filesystem=xdg-config/autostart:create \
    --talk-name=org.freedesktop.Notifications \
    --talk-name=org.freedesktop.portal.Desktop \
    --talk-name=org.kde.StatusNotifierWatcher \
    --talk-name=org.gnome.Shell.Screenshot \
    --talk-name=org.gnome.Shell.Screencast

flatpak build-export "$REPO" "$APPDIR" master

OUT="$DIST_DIR/imageWatcher-${VERSION}-x86_64.flatpak"
flatpak build-bundle "$REPO" "$OUT" "$APP_ID" master

log "Creado: $OUT"
ls -lh "$OUT"
