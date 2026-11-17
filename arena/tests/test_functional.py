"""Arena de funcionamiento: flujos completos y contratos de la aplicacion."""
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from imagewatcher import config as config_module
from imagewatcher.app import Application
from imagewatcher.config import Config
from imagewatcher.editor import UNDO_MAX_BYTES, UNDO_MAX_STEPS, EditorWindow

pytestmark = pytest.mark.func

ROOT = Path(__file__).resolve().parents[2]


class _FakeWindow:
    def __init__(self, visible=True, fail=False):
        self.visible = visible
        self.fail = fail
        self.presented = 0

    def get_visible(self):
        return self.visible

    def present(self):
        if self.fail:
            raise RuntimeError("ventana rota")
        self.presented += 1


def test_present_shows_bar_and_visible_windows():
    """Reabrir la app debe mostrar la barra y recuperar ventanas visibles."""
    calls = []
    editor_visible = _FakeWindow()
    editor_hidden = _FakeWindow(visible=False)
    editor_broken = _FakeWindow(fail=True)
    tool = _FakeWindow()
    welcome = _FakeWindow()

    stub = SimpleNamespace(
        _set_bar_visible=lambda *args, **kwargs: calls.append((args, kwargs)),
        editors=[editor_visible, editor_hidden, editor_broken],
        tool_windows={"recorder": tool},
        _welcome=welcome,
    )
    Application.present(stub)

    assert calls == [((True,), {"force": True})]
    assert editor_visible.presented == 1
    assert editor_hidden.presented == 0
    assert tool.presented == 1
    assert welcome.presented == 1


def test_capture_editor_save_pipeline(tmp_path):
    """Captura simulada -> anotacion -> guardado en disco."""
    image = Image.new("RGBA", (400, 300), (40, 50, 60, 255))
    editor = EditorWindow(image, Config())
    try:
        editor._push_undo()
        editor._raster_line([(10, 10), (300, 200)], 6, (255, 0, 0, 255))
        target = tmp_path / "captura.png"
        editor._write_image(str(target))
    finally:
        editor.destroy()
        editor.release_resources()

    assert target.exists() and target.stat().st_size > 0
    saved = Image.open(target).convert("RGBA")
    assert saved.size == (400, 300)
    red, _green, _blue, _alpha = saved.getpixel((10, 10))
    assert red > 100


def test_desktop_entry_has_required_metadata():
    text = (ROOT / "imagewatcher.desktop").read_text(encoding="utf-8")
    fields = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    assert fields.get("Type") == "Application"
    assert fields.get("Name") == "imageWatcher"
    assert fields.get("Exec")
    assert fields.get("Icon")
    assert fields.get("StartupWMClass") == "imageWatcher"


def test_pyproject_defines_console_script():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        data = tomllib.load(fh)
    entry = data["project"]["scripts"]["imagewatcher"]
    assert entry == "imagewatcher.app:main"


def test_hotkey_undo_limits_are_sane():
    assert 0 < UNDO_MAX_STEPS <= 100
    assert 32 * 1024 * 1024 <= UNDO_MAX_BYTES <= 512 * 1024 * 1024


def test_config_deep_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")

    cfg = Config()
    cfg["delay_seconds"] = 9
    cfg["favorite_tools"] = ["editor", "color_history"]
    cfg.data["hotkeys"]["window"] = "Print"
    cfg["fixed_region_size"] = [800, 600]
    cfg["color_history"] = ["#112233", "#445566"]
    cfg.save()

    loaded = Config()
    assert loaded.data == cfg.data
