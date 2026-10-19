#!/usr/bin/env bash
# Arena de pruebas (sandbox): ejecuta pytest en un servidor X virtual.
#
# Uso:
#   arena/run_arena.sh                 # Xvfb si hace falta + pytest
#   DISPLAY=:0 arena/run_arena.sh -v   # usa tu sesion y pasa args a pytest
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

XVFB_PID=""
cleanup() {
    if [ -n "$XVFB_PID" ]; then
        kill "$XVFB_PID" 2>/dev/null || true
        wait "$XVFB_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

need_display=1
if [ -n "${DISPLAY:-}" ]; then
    if command -v xdpyinfo >/dev/null 2>&1; then
        xdpyinfo >/dev/null 2>&1 && need_display=0
    else
        need_display=0
    fi
fi

if [ "$need_display" = 1 ]; then
    if command -v Xvfb >/dev/null 2>&1; then
        export DISPLAY=":99"
        Xvfb "$DISPLAY" -screen 0 1600x900x24 -nolisten tcp >"/tmp/imagewatcher-arena-xvfb.log" 2>&1 &
        XVFB_PID=$!
        sleep 1.5
        echo "==> Arena con Xvfb en $DISPLAY"
    else
        echo "!! No hay DISPLAY ni Xvfb. Instala xvfb: sudo apt install xvfb" >&2
        exit 2
    fi
else
    echo "==> Arena usando el DISPLAY actual: $DISPLAY"
fi

export PYTHONPATH="$ROOT:${PYTHONPATH:-}"

if ! python3 -c "import pytest" >/dev/null 2>&1; then
    echo "==> pytest no encontrado; instalando en el usuario..."
    if ! python3 -m pip install --user --break-system-packages -q -r requirements-dev.txt; then
        echo "!! No se pudo instalar pytest. Prueba: sudo apt install python3-pytest" >&2
        exit 3
    fi
fi

echo "==> Python: $(python3 --version)  -  pytest: $(python3 -m pytest --version 2>/dev/null | head -1)"
echo

python3 -m pytest "$@"
STATUS=$?

echo
if [ "$STATUS" = 0 ]; then
    echo -e "\033[1;32mARENA OK\033[0m"
else
    echo -e "\033[1;31mARENA CON FALLOS ($STATUS)\033[0m"
fi
exit $STATUS
