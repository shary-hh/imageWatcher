"""Pruebas del modulo de compartir (URL local)."""
import urllib.request

from imagewatcher.share import LocalShare


def test_local_share_serves_file(tmp_path):
    target = tmp_path / "captura.txt"
    target.write_text("contenido-de-prueba", encoding="utf-8")

    server = LocalShare(tmp_path)
    url = server.start("captura.txt")
    try:
        assert "captura.txt" in url
        with urllib.request.urlopen(url, timeout=5) as response:
            assert response.read() == b"contenido-de-prueba"
    finally:
        server.stop()
