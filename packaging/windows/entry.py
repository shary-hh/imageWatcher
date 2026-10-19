"""Punto de entrada para el empaquetado con PyInstaller (Windows)."""
import sys

from imagewatcher.app import main

if __name__ == "__main__":
    sys.exit(main())
