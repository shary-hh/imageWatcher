#!/usr/bin/env bash
# Construye e instala el paquete .deb de imageWatcher y reinicia la aplicacion.
#
# Uso:
#   ./install_deb.sh                # compila si hace falta, instala y reinicia
#   ./install_deb.sh --rebuild      # fuerza la compilacion antes de instalar
#   ./install_deb.sh --test         # ejecuta la arena de pruebas antes de instalar
#   ./install_deb.sh --no-restart   # instala sin cerrar/abrir imageWatcher
#
# La instalacion usa sudo, asi que pedira tu contrasena.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cd "$ROOT_DIR" && python3 -c 'from imagewatcher import __version__; print(__version__)')"
DEB="$ROOT_DIR/dist/imagewatcher_${VERSION}_all.deb"

REBUILD=0
RUN_TESTS=0
RESTART=1

show_help() {
    sed -n '2,10p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

for arg in "$@"; do
    case "$arg" in
        --rebuild) REBUILD=1 ;;
        --test) RUN_TESTS=1 ;;
        --no-restart) RESTART=0 ;;
        -h|--help) show_help; exit 0 ;;
        *)
            echo "Opcion desconocida: $arg" >&2
            echo "Usa --help para ver las opciones." >&2
            exit 2
            ;;
    esac
done

if [ "$RUN_TESTS" -eq 1 ]; then
    if python3 -c 'import pytest' >/dev/null 2>&1; then
        echo "==> Ejecutando pruebas..."
        (cd "$ROOT_DIR" && python3 -m pytest arena/tests -q)
    else
        echo "==> pytest no esta instalado; se omiten las pruebas."
        echo "    Instalalo con: sudo apt install python3-pytest"
    fi
fi

if [ "$REBUILD" -eq 1 ] || [ ! -f "$DEB" ]; then
    echo "==> Construyendo imageWatcher $VERSION..."
    "$ROOT_DIR/packaging/build_deb.sh"
fi

echo "==> Instalando $(basename "$DEB") (pedira tu contrasena)..."
sudo apt-get install -y "$DEB"

INSTALLED="$(dpkg-query -W -f='${Version}' imagewatcher 2>/dev/null || echo 'desconocida')"
echo "==> Version instalada: $INSTALLED"

if [ "$RESTART" -eq 1 ]; then
    if pgrep -f 'python3 -m imagewatcher' >/dev/null 2>&1; then
        echo "==> Cerrando imageWatcher..."
        # SIGTERM cierra la app de forma ordenada: guarda la configuracion y
        # finaliza cualquier grabacion en curso.
        pkill -TERM -f 'python3 -m imagewatcher' || true
        for _ in $(seq 1 30); do
            pgrep -f 'python3 -m imagewatcher' >/dev/null 2>&1 || break
            sleep 0.5
        done
    fi
    if command -v imagewatcher >/dev/null 2>&1; then
        echo "==> Iniciando imageWatcher..."
        setsid imagewatcher >/dev/null 2>&1 < /dev/null &
        sleep 1
        pgrep -af 'python3 -m imagewatcher' || echo "Aviso: no arranco; abrelo desde el menu."
    else
        echo "Aviso: no se encontro el comando imagewatcher en PATH."
    fi
fi

echo
echo "Listo: imageWatcher $INSTALLED instalado."
echo "La opcion esta en Preferencias > General:"
echo "  'Incluir el panel (barra de menu) del escritorio'"
