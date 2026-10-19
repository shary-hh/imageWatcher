"""Pruebas del modulo de compartir (URL local)."""
import urllib.error
import urllib.request

import pytest

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


def test_local_share_does_not_expose_other_files(tmp_path):
    target = tmp_path / "captura.txt"
    target.write_text("contenido-de-prueba", encoding="utf-8")
    other = tmp_path / "privado.txt"
    other.write_text("no-debe-compartirse", encoding="utf-8")

    server = LocalShare(tmp_path)
    url = server.start("captura.txt")
    try:
        other_url = url.rsplit("/", 1)[0] + "/privado.txt"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(other_url, timeout=5)
        assert exc.value.code == 404
    finally:
        server.stop()
