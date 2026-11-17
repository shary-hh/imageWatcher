"""Arena de estabilidad: ciclos prolongados, recursos y recuperacion."""
import gc
import time
from urllib.request import urlopen

import pytest
from PIL import Image

from imagewatcher import capture, config as config_module, session
from imagewatcher.config import Config
from imagewatcher.editor import EditorWindow
from imagewatcher.gtk_util import pil_to_pixbuf, pixbuf_to_pil
from imagewatcher.hotkeys import HotkeyManager, parse_accelerator, parse_hotkey
from imagewatcher.memory import trim_memory
from imagewatcher.share import LocalShare
from imagewatcher.single_instance import SingleInstance

pytestmark = pytest.mark.stability


def _rss_mb():
    """RSS del proceso actual en MB; None si no hay /proc."""
    try:
        with open("/proc/self/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024
    except OSError:
        return None
    return None


def _new_editor(size=(640, 360)):
    return EditorWindow(Image.new("RGBA", size, (30, 40, 50, 255)), Config())


def _close_editor(editor, pump):
    editor.destroy()
    pump(20)
    editor.release_resources()
    del editor
    gc.collect()
    trim_memory()
    pump(20)


def test_editor_cycles_keep_memory_bounded(pump):
    """Abrir/cerrar editores no debe hacer crecer la memoria sin limite."""
    if _rss_mb() is None:
        pytest.skip("RSS no disponible en este sistema")

    def _cycle():
        editor = _new_editor()
        editor.hide()
        for _ in range(5):
            editor._push_undo()
            editor._refresh_pixbuf()
        _close_editor(editor, pump)

    _cycle()  # calentar fuentes, iconos y caches de GTK
    baseline = _rss_mb()
    for _ in range(8):
        _cycle()
    pump(100)
    growth = _rss_mb() - baseline
    assert growth < 180, f"crecimiento de memoria tras 8 ciclos: {growth:.0f} MB"


def test_undo_history_bounded_under_stress(pump):
    editor = _new_editor((320, 240))
    try:
        for _ in range(300):
            editor._push_undo()
        assert len(editor.undo_stack) <= 40
        total = sum(step.width * step.height * 4 for step in editor.undo_stack)
        assert total <= 200 * 1024 * 1024

        for _ in range(60):
            editor._undo()
        assert editor.undo_stack == []
        assert len(editor.redo_stack) <= 40

        for _ in range(60):
            editor._redo()
        assert editor.redo_stack == []
        assert len(editor.undo_stack) <= 40
    finally:
        editor.destroy()
        editor.release_resources()


def test_editor_release_resources_is_idempotent():
    editor = _new_editor((64, 64))
    editor.destroy()
    editor.release_resources()
    editor.release_resources()
    assert editor.image is None
    assert editor.undo_stack == []


def test_hotkey_manager_start_stop_cycles():
    if session.is_wayland():
        pytest.skip("Los atajos Wayland dependen del portal del escritorio")
    for _ in range(8):
        manager = HotkeyManager()
        manager.start({"fullscreen": "Ctrl+Alt+Shift+F9"})
        assert manager._thread is not None
        manager.stop()
        assert manager._thread is None
        assert manager._display is None


def test_single_instance_repeated_cycles(tmp_path):
    socket_path = tmp_path / "app.sock"
    for _ in range(20):
        instance = SingleInstance(socket_path)
        assert instance.acquire(timeout=0.2) is True
        assert instance.is_primary is True
        instance.close()
        assert not socket_path.exists()


def test_local_share_start_stop_cycles(tmp_path):
    target = tmp_path / "captura.txt"
    target.write_text("contenido", encoding="utf-8")
    for _ in range(6):
        server = LocalShare(tmp_path)
        url = server.start(target.name)
        thread = server.thread
        with urlopen(url, timeout=5) as response:
            assert response.read() == b"contenido"
        server.stop()
        assert thread is not None and not thread.is_alive()


def test_capture_and_pixbuf_cycles():
    if capture.is_wayland():
        pytest.skip("La captura Wayland abre el portal del escritorio")
    start = time.perf_counter()
    for _ in range(10):
        image = capture.capture_region(0, 0, 64, 48)
        back = pixbuf_to_pil(pil_to_pixbuf(image))
        assert back.size == (64, 48)
        assert back.mode == "RGBA"
    assert time.perf_counter() - start < 15


def test_config_recovers_from_corrupt_json(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    (tmp_path / "config.json").write_text("{ esto no es json", encoding="utf-8")

    cfg = Config()
    assert cfg.get("save_format") == "png"
    assert cfg.get("hotkeys_enabled") is True

    cfg["save_format"] = "jpg"
    cfg.save()
    assert Config().get("save_format") == "jpg"


def test_config_many_save_load_cycles(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    cfg = Config()
    for index in range(50):
        cfg["delay_seconds"] = index % 10 + 1
        cfg.save()
        assert Config().get("delay_seconds") == index % 10 + 1


@pytest.mark.parametrize("size", [(1, 1), (3, 5), (17, 9), (64, 64)])
def test_pixbuf_roundtrip_odd_sizes(size):
    image = Image.new("RGBA", size, (11, 22, 33, 255))
    back = pixbuf_to_pil(pil_to_pixbuf(image))
    assert back.size == size
    assert back.getpixel((0, 0)) == (11, 22, 33, 255)


def test_trim_memory_can_run_repeatedly():
    for _ in range(30):
        trim_memory()


def test_hotkey_parser_survives_extreme_input():
    assert parse_hotkey("+" * 5000) is None
    mods, key = parse_hotkey("x" * 5000)
    assert mods == 0 and len(key) == 5000
    mods, key = parse_accelerator("<" * 5000)
    assert mods == 0 and key
