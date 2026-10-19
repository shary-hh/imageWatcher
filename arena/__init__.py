"""Arena de pruebas (sandbox) para el imageWatcher.

Ejecuta la suite con pytest (ver conftest.py y pytest.ini en la raiz):

    python3 -m pytest
    ./arena/run_arena.sh          # levanta Xvfb si hace falta

Con Docker:

    docker build -f arena/Dockerfile -t imagewatcher-arena .
    docker run --rm imagewatcher-arena
"""
