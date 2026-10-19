#!/usr/bin/env bash
# Instalador para Linux Mint / Ubuntu (X11).
# Instala dependencias del sistema, crea el lanzador y la entrada de menu.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPS_DIR="$HOME/.local/share/applications"
BIN_DIR="$HOME/.local/bin"
DESKTOP="$APPS_DIR/imagewatcher.desktop"

echo "==> Instalando dependencias del sistema..."
sudo apt update
sudo apt install -y \
    python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
    python3-pil python3-xlib ffmpeg libnotify-bin

echo "==> Creando lanzador en $BIN_DIR/imagewatcher"
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/imagewatcher" <<EOF
#!/usr/bin/env bash
cd "$DIR"
exec python3 -m imagewatcher "\$@"
EOF
chmod +x "$BIN_DIR/imagewatcher"

echo "==> Creando entrada de menu..."
mkdir -p "$APPS_DIR"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=imageWatcher
Comment=Captura, edita y comparte la pantalla
Exec=$BIN_DIR/imagewatcher
Path=$DIR
Icon=accessories-screenshot
Terminal=false
Categories=Utility;Graphics;
Keywords=captura;screenshot;editor;
EOF
chmod +x "$DESKTOP"

echo
echo "Instalado. Ejecuta 'imagewatcher' o buscalo como \"imageWatcher\" en el menu."
echo "Si $BIN_DIR no esta en tu PATH, anadelo a ~/.profile."
