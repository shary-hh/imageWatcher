"""Deteccion de la sesion grafica y utilidades compartidas para Wayland.

Wayland no permite capturar la raiz de X11 ni inyectar/registrar eventos
globales como X11. Este modulo centraliza la deteccion de sesion, el acceso al
portal de escritorio (xdg-desktop-portal) y la ejecucion de herramientas
nativas del compositor.
"""
import json
import os
import shutil
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlparse

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
PORTAL_REQUEST = "org.freedesktop.portal.Request"
PORTAL_SCREENSHOT = "org.freedesktop.portal.Screenshot"
PORTAL_GLOBAL_SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"


def is_wayland():
    """True si la sesion grafica es Wayland (aunque haya XWayland)."""
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if session:
        return session == "wayland"
    if os.environ.get("WAYLAND_DISPLAY"):
        return True
    return os.environ.get("GDK_BACKEND", "").lower().startswith("wayland")


def session_name():
    return "wayland" if is_wayland() else "x11"


def desktop_tokens():
    raw = os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get(
        "XDG_SESSION_DESKTOP", ""
    )
    return {token.strip().lower() for token in raw.replace(";", ":").split(":") if token.strip()}


def is_gnome():
    return bool(desktop_tokens() & {"gnome", "ubuntu", "unity"})


def is_kde():
    return bool(desktop_tokens() & {"kde", "plasma"})


def is_cinnamon():
    return any("cinnamon" in token for token in desktop_tokens())


def is_sway():
    return (
        "sway" in desktop_tokens()
        or bool(os.environ.get("SWAYSOCK"))
        or bool(shutil.which("swaymsg"))
    )


def is_hyprland():
    return (
        "hyprland" in desktop_tokens()
        or bool(os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"))
        or bool(shutil.which("hyprctl"))
    )


def is_wlroots():
    return bool(
        desktop_tokens()
        & {"sway", "hyprland", "river", "wayfire", "labwc", "niri", "wlroots"}
    )


def which(name):
    return shutil.which(name)


def run_command(args, timeout=15, text=True):
    """Ejecuta un comando sin lanzar excepciones. Devuelve CompletedProcess o None."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=text,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None


def command_output(args, timeout=15):
    result = run_command(args, timeout=timeout)
    if result is None or result.returncode != 0:
        return None
    return result.stdout


def _bus_call_method(
    bus,
    interface,
    method,
    params,
    reply_type=None,
    timeout=15000,
    bus_name=PORTAL_BUS,
    path=PORTAL_PATH,
):
    try:
        return bus.call_sync(
            bus_name,
            path,
            interface,
            method,
            params,
            reply_type,
            Gio.DBusCallFlags.NONE,
            timeout,
            None,
        )
    except Exception:
        return None


def portal_version(interface):
    """Version del portal indicado, o 0 si no esta disponible."""
    bus = None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception:
        return 0
    reply = _bus_call_method(
        bus,
        "org.freedesktop.DBus.Properties",
        "Get",
        GLib.Variant("(ss)", (interface, "version")),
    )
    if reply is None:
        return 0
    try:
        return int(reply.unpack()[0])
    except Exception:
        try:
            return int(reply.unpack())
        except Exception:
            return 0


def _request_path(bus, token):
    unique = (bus.get_unique_name() or "").lstrip(":") or "0"
    unique = unique.replace(".", "_")
    return f"{PORTAL_PATH}/request/{unique}/{token}"


def _uri_to_path(uri):
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme in ("", "file"):
        return unquote(parsed.path if parsed.scheme else uri)
    return None


def portal_screenshot(interactive=False, timeout=30):
    """Pide una captura al portal de escritorio.

    Devuelve la ruta del archivo creado por el portal, ``False`` si el usuario
    cancela (o el portal responde con error) y ``None`` si el portal no esta
    disponible o se agota el tiempo. El llamador es responsable de borrar el
    archivo cuando termine de leerlo.
    """
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception:
        return None

    token = f"imagewatcher_{os.getpid()}_{time.time_ns()}"
    request_path = _request_path(bus, token)
    state = {"done": False, "uri": None, "accepted": None}
    loop = GLib.MainLoop()

    def on_response(_connection, _sender, _path, _interface, _signal, params, _data=None):
        if state["done"]:
            return
        state["done"] = True
        try:
            response, results = params.unpack()
        except Exception:
            response, results = 1, {}
        state["accepted"] = response == 0
        if response == 0 and isinstance(results, dict):
            state["uri"] = results.get("uri")
        if loop.is_running():
            loop.quit()

    subscription = bus.signal_subscribe(
        PORTAL_BUS,
        PORTAL_REQUEST,
        "Response",
        request_path,
        None,
        Gio.DBusSignalFlags.NONE,
        on_response,
    )
    options = {
        "handle_token": GLib.Variant("s", token),
        "interactive": GLib.Variant("b", bool(interactive)),
        "modal": GLib.Variant("b", False),
    }
    params = GLib.Variant("(sa{sv})", ("", options))
    reply = _bus_call_method(
        bus,
        PORTAL_SCREENSHOT,
        "Screenshot",
        params,
        GLib.VariantType.new("(o)"),
        timeout=timeout * 1000,
    )
    if reply is None:
        bus.signal_unsubscribe(subscription)
        return None

    if not state["done"]:
        def _timeout():
            if not state["done"]:
                state["done"] = True
                if loop.is_running():
                    loop.quit()
            return False

        timeout_id = GLib.timeout_add_seconds(timeout, _timeout)
        try:
            loop.run()
        finally:
            try:
                GLib.source_remove(timeout_id)
            except Exception:
                pass
    bus.signal_unsubscribe(subscription)
    if not state["done"] or state["accepted"] is None:
        return None
    if not state["accepted"]:
        return False
    return _uri_to_path(state["uri"])


def _temp_png_path():
    fd, path = tempfile.mkstemp(prefix="imagewatcher_", suffix=".png")
    os.close(fd)
    try:
        os.unlink(path)
    except OSError:
        pass
    return path


def gnome_shell_screenshot(include_cursor=False, timeout=20):
    """Captura con la API de GNOME Shell (soporta cursor sin portal)."""
    path = _temp_png_path()
    bus = None
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    except Exception:
        return None
    reply = _bus_call_method(
        bus,
        "org.gnome.Shell.Screenshot",
        "Screenshot",
        GLib.Variant("(bbs)", (bool(include_cursor), False, path)),
        GLib.VariantType.new("(bs)"),
        timeout=timeout * 1000,
        bus_name="org.gnome.Shell",
        path="/org/gnome/Shell/Screenshot",
    )
    if reply is None:
        return None
    try:
        success, _filename = reply.unpack()
    except Exception:
        return None
    return path if success and os.path.exists(path) else None


def tool_screenshot(include_cursor=False, interactive=False, timeout=60):
    """Captura usando herramientas nativas de Wayland, en orden de preferencia.

    Devuelve una ruta a un archivo temporal PNG o ``None``.
    """
    temp = _temp_png_path()

    def clear_temp():
        try:
            if os.path.exists(temp):
                os.unlink(temp)
        except OSError:
            pass

    def try_gnome():
        if not (is_gnome() and which("gnome-screenshot")):
            return None
        clear_temp()
        args = ["gnome-screenshot", "-f", temp]
        if include_cursor:
            args.insert(1, "-p")
        if interactive:
            args.insert(1, "-a")
        run_command(args, timeout=timeout)
        return temp if os.path.exists(temp) else False

    def try_grim():
        if not which("grim"):
            return None
        if interactive and not which("slurp"):
            return None
        clear_temp()
        args = ["grim"]
        if include_cursor:
            args.append("-c")
        if interactive:
            geometry = command_output(["slurp"], timeout=timeout)
            if not geometry:
                return False
            args += ["-g", geometry.strip()]
        args.append(temp)
        run_command(args, timeout=timeout)
        return temp if os.path.exists(temp) else False

    def try_spectacle():
        if not which("spectacle"):
            return None
        clear_temp()
        args = ["spectacle", "-b", "-n"]
        args.append("-r" if interactive else "-f")
        args += ["-o", temp]
        if include_cursor:
            args.insert(2, "-p")
        run_command(args, timeout=timeout)
        return temp if os.path.exists(temp) else False

    def try_flameshot():
        if not which("flameshot"):
            return None
        clear_temp()
        args = ["flameshot", "gui"] if interactive else ["flameshot", "full", "-p", temp]
        run_command(args, timeout=timeout)
        return temp if os.path.exists(temp) else False

    tools = [try_gnome]
    if is_kde():
        tools += [try_spectacle, try_grim]
    else:
        tools += [try_grim, try_spectacle]
    tools.append(try_flameshot)

    for tool in tools:
        result = tool()
        if result:
            return result
        if result is False:
            if interactive:
                clear_temp()
                return None
            continue

    try:
        if os.path.exists(temp):
            os.unlink(temp)
    except Exception:
        pass
    return None


def cleanup_temp(path):
    if not path:
        return
    try:
        os.unlink(path)
    except Exception:
        pass


def json_command(args, timeout=10):
    output = command_output(args, timeout=timeout)
    if not output:
        return None
    try:
        return json.loads(output)
    except Exception:
        return None
