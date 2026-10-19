#!/usr/bin/env bash
# Helpers compartidos por los scripts de empaquetado.
# Se hace "source" desde build_deb.sh y build_appimage.sh.
set -euo pipefail

PACKAGING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PACKAGING_DIR/.." && pwd)"
cd "$ROOT_DIR"

PKG_NAME="imagewatcher"
APP_NAME="imageWatcher"
VERSION="$(python3 -c 'import imagewatcher; print(imagewatcher.__version__)')"
ARCH="$(dpkg --print-architecture 2>/dev/null || echo amd64)"

DIST_DIR="$ROOT_DIR/dist"
BUILD_DIR="$ROOT_DIR/build"
ICON_SVG="$PACKAGING_DIR/assets/imagewatcher.svg"

mkdir -p "$DIST_DIR" "$BUILD_DIR"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }

write_launcher() {
    local dest="$1"
    cat > "$dest" <<'EOF'
#!/usr/bin/env bash
exec python3 -m imagewatcher "$@"
EOF
    chmod 755 "$dest"
}

write_desktop() {
    local dest="$1"
    cat > "$dest" <<EOF
[Desktop Entry]
Type=Application
Name=$APP_NAME
Comment=Captura, edita y comparte la pantalla
Exec=$PKG_NAME
Icon=$PKG_NAME
Terminal=false
Categories=Graphics;
Keywords=captura;screenshot;editor;pantalla;
EOF
}
