#!/usr/bin/env bash
# Construye un paquete RPM (noarch) de imageWatcher.
#
# Si rpmbuild esta instalado lo usa directamente. Si no, construye dentro de
# un contenedor Fedora con Docker (no requiere permisos de root en el host).
#
# Resultado: dist/imagewatcher-<version>-<release>.<dist>.noarch.rpm
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"

SPEC_SRC="$PACKAGING_DIR/rpm/imagewatcher.spec"
RPM_DIR="$BUILD_DIR/rpm"
SRC_STAGE="$RPM_DIR/src"
SRC_TARBALL="$DIST_DIR/imagewatcher-${VERSION}.tar.gz"
RPM_IMAGE="${RPM_BUILD_IMAGE:-fedora:41}"

log "Empaquetando $APP_NAME $VERSION como RPM"

# Fuente reproducible con el codigo y los archivos de empaquetado.
rm -rf "$SRC_STAGE"
mkdir -p "$SRC_STAGE/imagewatcher-$VERSION"
cp -a "$ROOT_DIR/imagewatcher" \
      "$ROOT_DIR/README.md" \
      "$ROOT_DIR/pyproject.toml" \
      "$ROOT_DIR/packaging" \
      "$SRC_STAGE/imagewatcher-$VERSION/"
find "$SRC_STAGE" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SRC_STAGE" -name '*.pyc' -delete
tar -czf "$SRC_TARBALL" -C "$SRC_STAGE" "imagewatcher-$VERSION"

build_with_rpmbuild() {
    local topdir="$RPM_DIR/rpmbuild"
    rm -rf "$topdir"
    mkdir -p "$topdir"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
    sed "s/^Version:.*/Version:        $VERSION/" \
        "$SPEC_SRC" > "$topdir/SPECS/imagewatcher.spec"
    cp "$SRC_TARBALL" "$topdir/SOURCES/"
    rpmbuild -bb --define "_topdir $topdir" "$topdir/SPECS/imagewatcher.spec"
    find "$topdir/RPMS" -name '*.rpm' -exec cp -f {} "$DIST_DIR/" \;
}

build_with_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        warn "No hay rpmbuild ni Docker. Instala rpm-build o Docker para generar el RPM."
        exit 1
    fi
    docker run --rm \
        -e VERSION="$VERSION" \
        -v "$DIST_DIR:/out" \
        -v "$PACKAGING_DIR/rpm:/spec:ro" \
        "$RPM_IMAGE" \
        bash -lc '
            set -euo pipefail
            dnf install -y -q rpm-build python3-devel python3-setuptools \
                python3-wheel pyproject-rpm-macros >/dev/null
            topdir=/tmp/rpmbuild
            mkdir -p "$topdir"/{SOURCES,SPECS,BUILD,BUILDROOT,RPMS,SRPMS}
            sed "s/^Version:.*/Version:        $VERSION/" \
                /spec/imagewatcher.spec > "$topdir/SPECS/imagewatcher.spec"
            cp "/out/imagewatcher-$VERSION.tar.gz" "$topdir/SOURCES/"
            rpmbuild -bb --define "_topdir $topdir" \
                "$topdir/SPECS/imagewatcher.spec"
            cp "$topdir"/RPMS/noarch/*.rpm /out/
        '
}

if command -v rpmbuild >/dev/null 2>&1 && \
   [ -n "$(rpm --eval '%{?fedora}%{?rhel}' 2>/dev/null)" ]; then
    log "Usando rpmbuild local"
    build_with_rpmbuild
else
    log "rpmbuild no esta disponible en un entorno Fedora/RHEL; usando contenedor $RPM_IMAGE"
    build_with_docker
fi

log "Creado(s):"
ls -lh "$DIST_DIR"/*.rpm
