#!/usr/bin/env bash
# Construye un paquete .deb para Debian/Ubuntu/Linux Mint.
#
# Resultado: dist/imagewatcher_<version>_all.deb
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

log "Empaquetando $APP_NAME $VERSION como .deb"

STAGE="$BUILD_DIR/deb/${PKG_NAME}_${VERSION}_all"
rm -rf "$STAGE"
mkdir -p \
    "$STAGE/DEBIAN" \
    "$STAGE/usr/lib/python3/dist-packages" \
    "$STAGE/usr/bin" \
    "$STAGE/usr/share/applications" \
    "$STAGE/usr/share/icons/hicolor/scalable/apps" \
    "$STAGE/usr/share/doc/$PKG_NAME"

# Paquete Python (launcher usa "python3 -m imagewatcher").
cp -r "$ROOT_DIR/imagewatcher" "$STAGE/usr/lib/python3/dist-packages/"
find "$STAGE/usr/lib/python3/dist-packages" -name '__pycache__' -type d -prune -exec rm -rf {} +

write_launcher "$STAGE/usr/bin/$PKG_NAME"
write_desktop "$STAGE/usr/share/applications/$PKG_NAME.desktop"
cp "$ICON_SVG" "$STAGE/usr/share/icons/hicolor/scalable/apps/$PKG_NAME.svg"
cp "$ROOT_DIR/README.md" "$STAGE/usr/share/doc/$PKG_NAME/README.md" 2>/dev/null || true
[ -f "$ROOT_DIR/LICENSE" ] && cp "$ROOT_DIR/LICENSE" "$STAGE/usr/share/doc/$PKG_NAME/copyright" || true

INSTALLED_SIZE="$(du -sk "$STAGE/usr" | cut -f1)"

cat > "$STAGE/DEBIAN/control" <<EOF
Package: $PKG_NAME
Version: $VERSION
Section: graphics
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-pil, python3-xlib, ffmpeg
Recommends: libnotify-bin
Installed-Size: $INSTALLED_SIZE
Maintainer: imageWatcher contributors <noreply@example.com>
Description: Captura, edicion y grabacion de pantalla (clon libre de PicPick)
 imageWatcher es una suite de captura de pantalla para Linux sobre X11:
 captura de pantalla completa, ventana y region; editor con anotaciones y
 efectos; herramientas de diseno (selector de color, lupa, regla, transportador,
 pizarra); grabacion de pantalla con ffmpeg; atajos globales y bandeja.
EOF

cat > "$STAGE/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/postinst"

cat > "$STAGE/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
exit 0
EOF
chmod 755 "$STAGE/DEBIAN/prerm"

OUT="$DIST_DIR/${PKG_NAME}_${VERSION}_all.deb"
dpkg-deb --build --root-owner-group "$STAGE" "$OUT" >/dev/null

log "Creado: $OUT"
dpkg-deb --info "$OUT" | sed -n '1,20p'
