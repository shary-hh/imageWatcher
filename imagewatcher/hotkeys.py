"""Atajos de teclado globales: XGrabKey en X11 y portal en Wayland.

Wayland no permite capturar teclas globales directamente. Cuando el escritorio
ofrece `org.freedesktop.portal.GlobalShortcuts`, se registran los atajos ahi;
si no existe (por ejemplo en GNOME sin ese portal), la aplicacion sigue
funcionando sin atajos globales y se informa del motivo.
"""
import logging
import os
import re
import select
import threading
import time

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib  # noqa: E402

from . import session  # noqa: E402

logger = logging.getLogger(__name__)

MODIFIERS = {
    "ctrl": 0x0004,
    "control": 0x0004,
    "shift": 0x0001,
    "alt": 0x0008,
    "mod1": 0x0008,
    "super": 0x0040,
    "win": 0x0040,
    "meta": 0x0040,
    "mod4": 0x0040,
}

PORTAL_MODIFIERS = {
    "ctrl": "CTRL",
    "control": "CTRL",
    "shift": "SHIFT",
    "alt": "ALT",
    "mod1": "ALT",
    "super": "LOGO",
    "win": "LOGO",
    "meta": "LOGO",
    "mod4": "LOGO",
}

KEY_ALIASES = {
    "escape": "Escape",
    "esc": "Escape",
    "return": "Return",
    "enter": "Return",
    "space": "space",
    "tab": "Tab",
    "delete": "Delete",
    "backspace": "BackSpace",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "Page_Up",
    "pagedown": "Page_Down",
    "page_up": "Page_Up",
    "page_down": "Page_Down",
    # La tecla Impr Pant se etiqueta de varias formas segun la distribucion.
    "print": "Print",
    "printscreen": "Print",
    "print_screen": "Print",
    "print screen": "Print",
    "prtsc": "Print",
    "prtscr": "Print",
    "impr": "Print",
    "imprpant": "Print",
    "impr_pant": "Print",
    "impr pant": "Print",
    "imppm": "Print",
    "imp_pm": "Print",
    "imp pm": "Print",
}

ACCELERATOR_MODIFIERS = {
    "ctrl": 0x0004,
    "control": 0x0004,
    "shift": 0x0001,
    "alt": 0x0008,
    "mod1": 0x0008,
    "super": 0x0040,
    "win": 0x0040,
    "meta": 0x0040,
    "mod4": 0x0040,
}

CINNAMON_MEDIA_SCHEMA = "org.cinnamon.desktop.keybindings.media-keys"
CINNAMON_SCREENSHOT_KEYS = (
    "screenshot",
    "window-screenshot",
    "area-screenshot",
    "screenshot-clip",
    "window-screenshot-clip",
    "area-screenshot-clip",
)

IGNORED_MASK = 0x0002 | 0x0010  # LockMask | Mod2Mask


def parse_hotkey(spec):
    """Convierte 'Ctrl+Alt+1' o 'ImpPm' en (mascara_modificadores, tecla)."""
    if not spec:
        return None
    tokens = [token.strip().lower() for token in str(spec).split("+") if token.strip()]
    if not tokens:
        return None
    mods = 0
    for token in tokens[:-1]:
        mods |= MODIFIERS.get(token, 0)
    key_name = KEY_ALIASES.get(tokens[-1], tokens[-1])
    return mods, key_name


def assign_print_key(specs, action):
    """Copia de ``specs`` con Impr Pant asignado a ``action``.

    Quita la tecla sin modificadores de cualquier otra accion: si dos atajos
    comparten la misma combinacion solo se registra uno y el otro queda muerto.
    """
    updated = dict(specs)
    for name, spec in updated.items():
        if name == action or not spec:
            continue
        if parse_hotkey(spec) == (0, "Print"):
            updated[name] = ""
    updated[action] = "Print"
    return updated


def parse_accelerator(spec):
    """Convierte un atajo de Cinnamon ('<Alt>Print') al mismo formato."""
    text = str(spec or "")
    mods = 0
    for name in re.findall(r"<([^>]+)>", text):
        mods |= ACCELERATOR_MODIFIERS.get(name.strip().lower(), 0)
    key = re.sub(r"<[^>]+>", "", text).strip().lower()
    key = KEY_ALIASES.get(key, key)
    return mods, key


def cinnamon_settings():
    """Ajustes de atajos de Cinnamon, o None si no aplica."""
    if session.is_wayland() or not session.is_cinnamon():
        return None
    try:
        source = Gio.SettingsSchemaSource.get_default()
        if source is None or source.lookup(CINNAMON_MEDIA_SCHEMA, True) is None:
            return None
        return Gio.Settings.new(CINNAMON_MEDIA_SCHEMA)
    except Exception:
        return None


def cinnamon_print_conflicts(specs):
    """Atajos de captura de Cinnamon que chocan con los ``specs`` pedidos.

    Devuelve ``{clave_de_ajuste: [atajos_en_conflicto]}``. Solo se tienen en
    cuenta las teclas de captura de pantalla de Cinnamon, que son las que
    impiden registrar ImpPm/Print en imageWatcher.
    """
    settings = cinnamon_settings()
    if settings is None:
        return {}
    wanted = {parse_hotkey(spec) for spec in specs if spec}
    wanted.discard(None)
    if not wanted:
        return {}
    conflicts = {}
    for key in CINNAMON_SCREENSHOT_KEYS:
        try:
            accels = settings.get_strv(key)
        except Exception:
            continue
        matches = [accel for accel in accels if parse_accelerator(accel) in wanted]
        if matches:
            conflicts[key] = matches
    return conflicts


def free_cinnamon_bindings(conflicts):
    """Quita de Cinnamon los atajos indicados por ``conflicts``."""
    settings = cinnamon_settings()
    if settings is None or not conflicts:
        return False
    changed = False
    for key, accels in conflicts.items():
        try:
            current = settings.get_strv(key)
        except Exception:
            continue
        remaining = [accel for accel in current if accel not in accels]
        if remaining != current:
            try:
                settings.set_strv(key, remaining)
                changed = True
            except Exception:
                pass
    if changed:
        try:
            settings.sync()
        except Exception:
            pass
    return changed


class HotkeyManager:
    """Registra atajos globales y los despacha en el hilo de GTK."""

    def __init__(self):
        self._thread = None
        self._running = False
        self._display = None
        self._bindings = {}
        self._callbacks = {}
        self.failures = []
        self._bus = None
        self._portal_session = None
        self._portal_subscriptions = []
        self._portal_actions = {}

    def _parse(self, spec):
        return parse_hotkey(spec)

    def _portal_trigger(self, spec):
        tokens = [token.strip().lower() for token in spec.split("+") if token.strip()]
        if not tokens:
            return None
        mods = []
        for token in tokens[:-1]:
            modifier = PORTAL_MODIFIERS.get(token)
            if modifier and modifier not in mods:
                mods.append(modifier)
        key = KEY_ALIASES.get(tokens[-1])
        if key is None:
            key = tokens[-1].upper() if len(tokens[-1]) == 1 else tokens[-1].capitalize()
        return "+".join(mods + [key])

    def _portal_request(self, interface, method, make_params, timeout=60):
        """Llama a un metodo del portal que devuelve un request handle."""
        if self._bus is None:
            return None
        token = f"imagewatcher_{os.getpid()}_{time.time_ns()}"
        request_path = f"{session.PORTAL_PATH}/request/"
        unique = (self._bus.get_unique_name() or "").lstrip(":") or "0"
        request_path += unique.replace(".", "_") + "/" + token
        state = {"done": False, "result": None}
        loop = GLib.MainLoop()

        def on_response(_conn, _sender, _path, _iface, _signal, params, _data=None):
            if state["done"]:
                return
            state["done"] = True
            try:
                state["result"] = params.unpack()
            except Exception:
                state["result"] = (1, {})
            if loop.is_running():
                loop.quit()

        subscription = self._bus.signal_subscribe(
            session.PORTAL_BUS,
            session.PORTAL_REQUEST,
            "Response",
            request_path,
            None,
            Gio.DBusSignalFlags.NONE,
            on_response,
        )
        try:
            params = make_params(token)
            reply = self._bus.call_sync(
                session.PORTAL_BUS,
                session.PORTAL_PATH,
                interface,
                method,
                params,
                GLib.VariantType.new("(o)"),
                Gio.DBusCallFlags.NONE,
                timeout * 1000,
                None,
            )
        except Exception:
            reply = None
        if reply is None:
            self._bus.signal_unsubscribe(subscription)
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
        self._bus.signal_unsubscribe(subscription)
        result = state.get("result")
        if not result:
            return None
        try:
            response, values = result
        except Exception:
            return None
        if response != 0:
            return False
        return values if isinstance(values, dict) else {}

    def _start_wayland(self, hotkeys):
        if session.portal_version(session.PORTAL_GLOBAL_SHORTCUTS) <= 0:
            self.failures.append(
                "Wayland: el portal GlobalShortcuts no esta disponible. "
                "Configura los atajos desde el escritorio."
            )
            return
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except Exception as exc:
            self.failures.append(f"No se pudo abrir D-Bus: {exc}")
            return
        result = self._portal_request(
            session.PORTAL_GLOBAL_SHORTCUTS,
            "CreateSession",
            lambda token: GLib.Variant(
                "(a{sv})",
                (
                    {
                        "handle_token": GLib.Variant("s", token),
                        "session_handle_token": GLib.Variant(
                            "s", f"imagewatcher_{os.getpid()}"
                        ),
                    },
                ),
            ),
            timeout=30,
        )
        if result is None or result is False:
            self.failures.append(
                "Wayland: no se pudo crear una sesion de atajos globales."
            )
            self._close_portal()
            return
        session_handle = result.get("session_handle") if isinstance(result, dict) else None
        if not session_handle:
            self.failures.append("Wayland: el portal no devolvio la sesion de atajos.")
            self._close_portal()
            return
        session_handle = str(session_handle)

        shortcuts = []
        for action, spec in hotkeys.items():
            trigger = self._portal_trigger(spec)
            if not trigger:
                continue
            shortcuts.append(
                (
                    action,
                    {
                        "description": GLib.Variant("s", action),
                        "preferred_trigger": GLib.Variant("s", trigger),
                    },
                )
            )
        if not shortcuts:
            self._portal_session = session_handle
            self._close_portal()
            return

        result = self._portal_request(
            session.PORTAL_GLOBAL_SHORTCUTS,
            "BindShortcuts",
            lambda token: GLib.Variant(
                "(oa(sa{sv})sa{sv})",
                (
                    session_handle,
                    shortcuts,
                    "",
                    {"handle_token": GLib.Variant("s", token)},
                ),
            ),
            timeout=120,
        )
        if result is None or result is False:
            self.failures.append(
                "Wayland: el escritorio rechazo o no pudo registrar los atajos."
            )
            self._portal_session = session_handle
            self._close_portal()
            return

        self._portal_session = session_handle
        self._portal_actions = {action: action for action, _spec in hotkeys.items()}

        def on_activated(_conn, _sender, _path, _iface, _signal, params, _data=None):
            try:
                values = params.unpack()
                _session_handle, shortcut_id = values[0], values[1]
            except Exception:
                return
            action = self._portal_actions.get(shortcut_id)
            callback = self._callbacks.get(action) if action else None
            if callback:
                GLib.idle_add(callback)

        self._portal_subscriptions.append(
            self._bus.signal_subscribe(
                session.PORTAL_BUS,
                session.PORTAL_GLOBAL_SHORTCUTS,
                "Activated",
                None,
                None,
                Gio.DBusSignalFlags.NONE,
                on_activated,
            )
        )
        self._running = True

    def _close_portal(self):
        for subscription in self._portal_subscriptions:
            try:
                self._bus.signal_unsubscribe(subscription)
            except Exception:
                pass
        self._portal_subscriptions = []
        if self._portal_session and self._bus is not None:
            try:
                self._bus.call_sync(
                    session.PORTAL_BUS,
                    self._portal_session,
                    "org.freedesktop.portal.Session",
                    "Close",
                    None,
                    None,
                    Gio.DBusCallFlags.NONE,
                    3000,
                    None,
                )
            except Exception:
                pass
        self._portal_session = None
        self._bus = None
        self._running = False
        self._portal_actions = {}

    def start(self, hotkeys):
        self.stop()
        self.failures = []
        if session.is_wayland():
            self._start_wayland(hotkeys)
            return
        from Xlib import X, XK, display as xdisplay, error as xerror

        try:
            self._display = xdisplay.Display()
        except Exception as exc:
            self.failures.append(f"No se pudo abrir X11: {exc}")
            return
        self._display.set_error_handler(self._on_x_error)
        root = self._display.screen().root
        self._bindings = {}
        self.failures = []
        for action, spec in hotkeys.items():
            parsed = self._parse(spec)
            if not parsed:
                continue
            mods, key_name = parsed
            keysym = XK.string_to_keysym(key_name)
            if keysym == 0:
                try:
                    keysym = XK.string_to_keysym(key_name.capitalize())
                except Exception:
                    keysym = 0
            if keysym == 0:
                self.failures.append(f"Tecla desconocida: {key_name}")
                continue
            keycode = self._display.keysym_to_keycode(keysym)
            if keycode == 0:
                self.failures.append(f"Sin keycode para: {key_name}")
                continue

            conflict = False
            for index, extra in enumerate((0, 0x0002, 0x0010, 0x0012)):
                catcher = xerror.CatchError(xerror.BadAccess)
                try:
                    root.grab_key(
                        keycode, mods | extra, True,
                        X.GrabModeAsync, X.GrabModeAsync, onerror=catcher,
                    )
                    self._display.sync()
                except Exception:
                    pass
                if catcher.get_error():
                    if index == 0:
                        conflict = True
                        break
                    # Solo fallan las variantes con BloqueoMayus/Num; no es critico.
            if conflict:
                self.failures.append(
                    f"El atajo '{spec}' ya esta en uso por otra aplicacion"
                )
            else:
                self._bindings[(keycode, mods)] = action

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    @staticmethod
    def _on_x_error(err, _request):
        from Xlib import error as xerror

        if isinstance(err, xerror.BadAccess):
            return
        logger.warning("Error X inesperado en atajos: %s", err)

    def _loop(self):
        from Xlib import X

        while self._running and self._display is not None:
            try:
                while self._display.pending_events():
                    event = self._display.next_event()
                    if event.type == X.KeyPress:
                        self._handle(event)
                # Bloquea hasta que llegue actividad a X11: sin sondeo.
                select.select([self._display.fileno()], [], [], 0.5)
            except Exception:
                break

    def _handle(self, event):
        keycode = event.detail
        state = event.state & ~IGNORED_MASK
        action = self._bindings.get((keycode, state))
        if action:
            callback = self._callbacks.get(action)
            if callback:
                GLib.idle_add(callback)

    def set_callbacks(self, callbacks):
        self._callbacks = callbacks

    def stop(self):
        if self._bus is not None or self._portal_session is not None:
            self._close_portal()
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._display is not None:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None
