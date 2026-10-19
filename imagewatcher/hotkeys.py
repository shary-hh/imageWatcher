"""Atajos de teclado globales usando XGrabKey (X11)."""
import logging
import threading
import time

from gi.repository import GLib

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

IGNORED_MASK = 0x0002 | 0x0010  # LockMask | Mod2Mask


class HotkeyManager:
    """Registra atajos globales y los despacha en el hilo de GTK."""

    def __init__(self):
        self._thread = None
        self._running = False
        self._display = None
        self._bindings = {}
        self._callbacks = {}
        self.failures = []

    def _parse(self, spec):
        tokens = [token.strip().lower() for token in spec.split("+") if token.strip()]
        if not tokens:
            return None
        mods = 0
        key_name = tokens[-1]
        for token in tokens[:-1]:
            if token in MODIFIERS:
                mods |= MODIFIERS[token]
        return mods, key_name

    def start(self, hotkeys):
        self.stop()
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
                time.sleep(0.04)
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
