#!/usr/bin/env bash
# Construye un AppImage "ligero" que usa el Python+GTK del sistema.
#
# Resultado: dist/imageWatcher-<version>-x86_64.AppImage
#
# Nota: se apoya en las dependencias del sistema (python3-gi, gir1.2-gtk-3.0,
# python3-pil, python3-xlib, ffmpeg) para no duplicar GTK ni Python. Es el
# enfoque habitual para apps PyGObject y mantiene el AppImage en pocos cientos de KB.
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "Empaquetando $APP_NAME $VERSION como AppImage"

APPDIR="$BUILD_DIR/AppDir"
rm -rf "$APPDIR"
mkdir -p \
    "$APPDIR/usr/lib/$PKG_NAME" \
    "$APPDIR/usr/share/applications" \
    "$APPDIR/usr/share/icons/hicolor/scalable/apps"

cp -r "$ROOT_DIR/imagewatcher" "$APPDIR/usr/lib/$PKG_NAME/"
find "$APPDIR/usr/lib/$PKG_NAME" -name '__pycache__' -type d -prune -exec rm -rf {} +

cp "$ICON_SVG" "$APPDIR/$PKG_NAME.svg"
cp "$ICON_SVG" "$APPDIR/usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"
write_desktop "$APPDIR/$PKG_NAME.desktop"
cp "$APPDIR/$PKG_NAME.desktop" "$APPDIR/usr/share/applications/$PKG_NAME.desktop"

cat > "$APPDIR/AppRun" <<EOF
#!/usr/bin/env bash
HERE="\$(cd "\$(dirname "\$(readlink -f "\${BASH_SOURCE[0]}")")" && pwd)"
export PYTHONPATH="\$HERE/usr/lib/$PKG_NAME:\${PYTHONPATH:-}"
export PICPPICK_APPIMAGE=1
exec python3 -m imagewatcher "\$@"
EOF
chmod 755 "$APPDIR/AppRun"

TOOL="$BUILD_DIR/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
    log "Descargando appimagetool..."
    if ! curl -fL -o "$TOOL" \
        "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"; then
        warn "No se pudo descargar appimagetool. AppDir listo en: $APPDIR"
        warn "Instálalo manualmente y ejecuta: ARCH=x86_64 appimagetool \"$APPDIR\""
        exit 1
    fi
    chmod +x "$TOOL"
fi

OUT="$DIST_DIR/${APP_NAME// /-}-${VERSION}-x86_64.AppImage"
export ARCH=x86_64

run_tool() {
    "$TOOL" "$@"
}

log "Generando AppImage..."
if ! run_tool "$APPDIR" "$OUT" 2>/tmp/imagewatcher-appimagetool.log; then
    warn "appimagetool fallo (posible falta de FUSE); reintentando con extraccion..."
    APPIMAGE_EXTRACT_AND_RUN=1 run_tool "$APPDIR" "$OUT"
fi
chmod +x "$OUT"
log "Creado: $OUT"
