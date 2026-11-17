"""Arena de seguridad: aislamiento de ficheros, permisos y ejecucion segura."""
import http.client
import json
import re
import socket
import stat
from pathlib import Path
from types import MethodType, SimpleNamespace

import pytest
from PIL import Image
from urllib.parse import quote

from imagewatcher import app as app_module
from imagewatcher import config as config_module
from imagewatcher import share
from imagewatcher.config import Config, DEFAULTS
from imagewatcher.gtk_util import pixbuf_to_pil
from imagewatcher.share import LocalShare
from imagewatcher.single_instance import SingleInstance

pytestmark = pytest.mark.security

PACKAGE_DIR = Path(__file__).resolve().parents[2] / "imagewatcher"


def _request(port, path, method="GET"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _share_server(tmp_path, name="captura con espacios.txt"):
    target = tmp_path / name
    target.write_text("contenido-privado", encoding="utf-8")
    server = LocalShare(tmp_path)
    server.start(target.name)
    return server


def _iter_keys(data):
    for key, value in data.items():
        yield key
        if isinstance(value, dict):
            yield from _iter_keys(value)


def test_local_share_rejects_traversal_and_directory_listing(tmp_path):
    server = _share_server(tmp_path)
    try:
        port = server.httpd.server_address[1]
        for path in (
            "/",
            "/privado.txt",
            "/.secreto",
            "/../etc/passwd",
            "/..%2f..%2fetc%2fpasswd",
            "/%2e%2e/%2e%2e/etc/passwd",
            "//etc/passwd",
            "/captura%20con%20espacios.txt/../../etc/passwd",
        ):
            status, _body = _request(port, path)
            assert status == 404, f"{path} deberia devolver 404, devolvio {status}"

        status, body = _request(port, "/" + quote("captura con espacios.txt"))
        assert status == 200
        assert body == b"contenido-privado"
    finally:
        server.stop()


def test_local_share_only_serves_exact_name(tmp_path):
    server = _share_server(tmp_path, "captura.txt")
    (tmp_path / "captura.txt.bak").write_text("otro", encoding="utf-8")
    try:
        port = server.httpd.server_address[1]
        assert _request(port, "/captura.txt")[0] == 200
        assert _request(port, "/captura.txt.bak")[0] == 404
        assert _request(port, "/CAPTURA.TXT")[0] == 404
        assert _request(port, "/captura.txt?download=1")[0] == 200
    finally:
        server.stop()


def test_local_share_stops_listening(tmp_path):
    server = _share_server(tmp_path)
    port = server.httpd.server_address[1]
    server.stop()
    assert server.httpd is None

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        with pytest.raises(OSError):
            sock.connect(("127.0.0.1", port))
    finally:
        sock.close()


def test_open_with_external_never_uses_a_shell(monkeypatch, tmp_path):
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(share.subprocess, "Popen", FakePopen)
    dangerous = tmp_path / "captura; rm -rf ~.png"
    share.open_with_external(dangerous)

    assert calls == [((["xdg-open", str(dangerous)],), {})]


def test_notifications_use_argument_lists(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(app_module.subprocess, "Popen", FakePopen)
    stub = SimpleNamespace(notifier="/usr/bin/notify-send")
    app_module.Application._notify(stub, "titulo; touch /tmp/pwned", "$(id)")

    assert calls == [((["/usr/bin/notify-send", "titulo; touch /tmp/pwned", "$(id)"],), {})]


def test_package_has_no_shell_or_eval_patterns():
    patterns = {
        "shell=True": re.compile(r"shell\s*=\s*True"),
        "os.system": re.compile(r"\bos\.system\s*\("),
        "os.popen": re.compile(r"\bos\.popen\s*\("),
        "eval": re.compile(r"\beval\s*\("),
        "exec": re.compile(r"\bexec\s*\("),
        "pickle.loads": re.compile(r"pickle\.loads\s*\("),
        "yaml.load": re.compile(r"yaml\.load\s*\("),
    }
    problems = []
    for path in PACKAGE_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for name, pattern in patterns.items():
            if pattern.search(text):
                problems.append(f"{path.relative_to(PACKAGE_DIR.parent)}: {name}")
    assert not problems, "patrones peligrosos: " + ", ".join(problems)


def test_config_has_no_secret_fields():
    forbidden = re.compile(r"(secret|token|password|passwd|api[_-]?key|credential)", re.I)
    keys = list(_iter_keys(DEFAULTS))
    assert keys
    assert not [key for key in keys if forbidden.search(key)]
    # El JSON de configuracion debe poder serializarse sin tipos opacos.
    json.dumps(DEFAULTS)


def test_config_files_are_not_world_writable(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "config.json")
    cfg = Config()
    cfg.save()

    file_mode = stat.S_IMODE((tmp_path / "config.json").stat().st_mode)
    assert file_mode & 0o077 == 0, (
        f"la configuracion no debe ser accesible por otros: {oct(file_mode)}"
    )
    dir_mode = stat.S_IMODE(tmp_path.stat().st_mode)
    assert dir_mode & 0o002 == 0


def test_auto_save_filename_cannot_escape_save_dir(tmp_path):
    class FakeConfig:
        def ensure_save_dir(self):
            return tmp_path

        def get(self, key, default=None):
            return {"save_format": "png", "jpeg_quality": 90}.get(key, default)

    stub = SimpleNamespace(config=FakeConfig())
    path = app_module.Application._auto_save(stub, Image.new("RGBA", (8, 8)))
    saved = Path(path)
    assert saved.parent == tmp_path
    assert re.fullmatch(r"captura_\d{8}_\d{6}\.png", saved.name)
    assert saved.exists()


def test_autostart_entry_is_confined(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    prefs = SimpleNamespace()
    prefs._autostart_path = MethodType(app_module.PreferencesDialog._autostart_path, prefs)
    prefs._set_autostart = MethodType(app_module.PreferencesDialog._set_autostart, prefs)

    prefs._set_autostart(True)
    path = prefs._autostart_path()
    assert path.parent == tmp_path / "autostart"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in text
    assert "Exec=" in text
    assert "imagewatcher" in text

    prefs._set_autostart(False)
    assert not path.exists()


def test_free_cinnamon_bindings_only_touches_screenshot_keys(monkeypatch):
    from imagewatcher import hotkeys as hotkeys_module

    class FakeSettings:
        def __init__(self):
            self.values = {
                "screenshot": ["Print"],
                "terminal": ["<Control><Alt>t"],
                "screensaver": ["<Control><Alt>l"],
            }
            self.synced = False

        def get_strv(self, key):
            return list(self.values.get(key, []))

        def set_strv(self, key, value):
            self.values[key] = list(value)

        def sync(self):
            self.synced = True

    fake = FakeSettings()
    monkeypatch.setattr(hotkeys_module, "cinnamon_settings", lambda: fake)
    conflicts = hotkeys_module.cinnamon_print_conflicts(["ImpPm"])
    assert conflicts == {"screenshot": ["Print"]}
    assert hotkeys_module.free_cinnamon_bindings(conflicts) is True
    assert fake.values["screenshot"] == []
    assert fake.values["terminal"] == ["<Control><Alt>t"]
    assert fake.values["screensaver"] == ["<Control><Alt>l"]
    assert fake.synced is True


def test_single_instance_socket_is_private(tmp_path):
    socket_path = tmp_path / "app.sock"
    instance = SingleInstance(socket_path)
    try:
        assert instance.acquire() is True
        assert socket_path.exists()
        mode = stat.S_IMODE(socket_path.stat().st_mode)
        assert mode & 0o077 == 0, f"socket accesible por otros: {oct(mode)}"
    finally:
        instance.close()


def test_pixbuf_conversion_rejects_broken_data():
    class BrokenPixbuf:
        def save_to_bufferv(self, *args, **kwargs):
            return False, b""

    with pytest.raises(RuntimeError):
        pixbuf_to_pil(BrokenPixbuf())
