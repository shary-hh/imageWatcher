"""Pruebas del control de instancia unica (socket + bloqueo)."""
from imagewatcher.single_instance import SingleInstance


def test_second_instance_notifies_first(pump, tmp_path):
    path = tmp_path / "app.sock"
    first = SingleInstance(path)
    called = []
    assert first.acquire() is True
    first.set_callback(lambda action: called.append(action))

    second = SingleInstance(path)
    assert second.acquire(timeout=1.0) is False
    pump(300)
    assert called == ["activate"]

    second.close()
    first.close()


def test_takes_over_stale_socket(tmp_path):
    path = tmp_path / "app.sock"
    path.write_bytes(b"")

    owner = SingleInstance(path)
    assert owner.acquire() is True
    assert owner.is_primary is True
    owner.close()
    assert not path.exists()


def test_lock_released_after_close(tmp_path):
    path = tmp_path / "app.sock"
    first = SingleInstance(path)
    assert first.acquire() is True
    first.close()

    again = SingleInstance(path)
    assert again.acquire() is True
    again.close()
