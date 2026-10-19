"""Pantalla de bienvenida con instrucciones basicas de uso."""
import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from . import __app_name__, __version__, ui

SECTIONS = [
    (
        "Captura",
        "display",
        [
            "Pantalla: captura todos los monitores.",
            "Ventana: captura la ventana activa.",
            "Region: arrastra para seleccionar; Enter confirma y Esc cancela.",
            "Grabar: graba video de pantalla con ffmpeg.",
        ],
    ),
    (
        "Atajos de teclado",
        "clock",
        [
            "Ctrl+Alt+1 Pantalla - Ctrl+Alt+2 Region - Ctrl+Alt+3 Ventana",
            "Ctrl+Alt+4 Repetir - Ctrl+Alt+5 Region fija - Ctrl+Alt+6 Freehand",
            "Esc cancela la seleccion o cierra las superposiciones.",
        ],
    ),
    (
        "Herramientas de diseno",
        "color",
        [
            "Clic derecho sobre la barra para abrir el menu de herramientas.",
            "Selector de color, lupa, regla, punto de mira, transportador y pizarra.",
            "Las medidas se muestran sobre el escritorio sin bloquear el raton.",
        ],
    ),
    (
        "Editor y compartir",
        "pen",
        [
            "El editor se abre tras cada captura (configurable en Preferencias).",
            "Guarda en PNG, JPG, BMP, GIF o PDF y copia al portapapeles.",
            "Comparte con un programa externo o con una URL de tu red local.",
        ],
    ),
]


class WelcomeWindow(Gtk.Window):
    """Ventana de bienvenida no modal, con la guia rapida de uso."""

    def __init__(self, app):
        super().__init__(title=f"Bienvenido a {__app_name__}")
        self.app = app
        self.set_default_size(780, 600)
        self.set_transient_for(app.bar)
        self.set_destroy_with_parent(True)
        ui.apply_dark(self)
        self.set_titlebar(
            ui.header(
                f"Bienvenido a {__app_name__}",
                "Guia rapida de uso",
                "applications-graphics",
            )
        )
        self.connect("delete-event", self._on_close)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        outer.set_margin_start(26)
        outer.set_margin_end(26)
        outer.set_margin_top(20)
        outer.set_margin_bottom(20)
        self.add(outer)

        outer.pack_start(self._hero(), False, False, 0)
        outer.pack_start(self._sections(), True, True, 0)
        outer.pack_start(self._footer(), False, False, 0)
        self.show_all()

    def _hero(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        image = ui.make_icon("applications-graphics", 64)
        if image is not None:
            box.pack_start(image, False, False, 0)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        texts.set_valign(Gtk.Align.CENTER)
        title = Gtk.Label(label=__app_name__, xalign=0)
        title.get_style_context().add_class("welcome-title")
        subtitle = Gtk.Label(
            label=f"Captura, edita y comparte tu pantalla - version {__version__}",
            xalign=0,
        )
        subtitle.get_style_context().add_class("welcome-subtitle")
        texts.pack_start(title, False, False, 0)
        texts.pack_start(subtitle, False, False, 0)
        box.pack_start(texts, False, False, 0)
        return box

    def _sections(self):
        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_column_homogeneous(True)
        for index, (title, icon, lines) in enumerate(SECTIONS):
            grid.attach(self._card(title, icon, lines), index % 2, index // 2, 1, 1)
        return grid

    def _card(self, title, icon, lines):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        card.get_style_context().add_class("welcome-card")
        card.set_hexpand(True)

        head = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        image = ui.make_icon(icon, 20)
        if image is not None:
            head.pack_start(image, False, False, 0)
        label = Gtk.Label(label=title, xalign=0)
        label.get_style_context().add_class("welcome-card-title")
        head.pack_start(label, False, False, 0)
        card.pack_start(head, False, False, 0)

        for line in lines:
            text = Gtk.Label(label=line, xalign=0)
            text.set_line_wrap(True)
            text.set_max_width_chars(44)
            text.get_style_context().add_class("welcome-text")
            card.pack_start(text, False, False, 0)
        return card

    def _footer(self):
        footer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.show_on_start = Gtk.CheckButton(label="Mostrar esta guia al iniciar")
        self.show_on_start.set_active(bool(self.app.config.get("show_welcome", True)))
        footer.pack_start(self.show_on_start, False, False, 0)

        start = Gtk.Button(label="Empezar")
        start.get_style_context().add_class("suggested-action")
        start.connect("clicked", self._on_start)
        footer.pack_end(start, False, False, 0)
        return footer

    def _remember(self):
        self.app.config["show_welcome"] = self.show_on_start.get_active()
        self.app.config.save()

    def _on_start(self, *_):
        self._remember()
        self.destroy()

    def _on_close(self, *_):
        self._remember()
        return False
