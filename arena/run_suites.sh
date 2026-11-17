#!/usr/bin/env bash
# Arena por categorias: funcionamiento, estabilidad y seguridad.
#
# Uso:
#   arena/run_suites.sh                 # todas las categorias
#   arena/run_suites.sh funcionamiento
#   arena/run_suites.sh estabilidad
#   arena/run_suites.sh seguridad
#
# Cualquier argumento extra se pasa a pytest.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRUPO="${1:-todo}"

case "$GRUPO" in
    func|funcionamiento|funcional)
        shift
        MARCA="func"
        ;;
    stability|estabilidad|estable)
        shift
        MARCA="stability"
        ;;
    security|seguridad)
        shift
        MARCA="security"
        ;;
    todo|all)
        shift
        MARCA="func or stability or security"
        ;;
    *)
        MARCA="func or stability or security"
        ;;
esac

echo "==> Arena: $MARCA"
exec "$HERE/run_arena.sh" -m "$MARCA" -v "$@"
