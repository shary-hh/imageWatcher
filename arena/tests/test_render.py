"""Prueba de renderizado del editor (composicion correcta en el canvas)."""
import cairo
import gi
import pytest

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gtk  # noqa: E402
from PIL import Image  # noqa: E402

from imagewatcher.config import Config  # noqa: E402
from imagewatcher.editor import EditorWindow  # noqa: E402


def _find_menu_button(widget):
    if isinstance(widget, Gtk.MenuButton):
        return widget
    if isinstance(widget, Gtk.Container):
        for child in widget.get_children():
            found = _find_menu_button(child)
            if found is not None:
                return found
    return None


def test_editor_menu_labels_stay_light_over_the_dark_menu(pump):
    """El texto del menu no debe heredar el color oscuro de la cabecera."""
    editor = EditorWindow(Image.new("RGBA", (320, 240), (0, 128, 255, 255)), Config())
    try:
        editor.show_all()
        pump(100)
        button = _find_menu_button(editor)
        assert button is not None
        menu = button.get_popup()
        menu.popup_at_widget(
            button, Gdk.Gravity.SOUTH_WEST, Gdk.Gravity.NORTH_WEST, None
        )
        pump(200)
        background = menu.get_style_context().get_background_color(
            Gtk.StateFlags.NORMAL
        )
        background_luma = background.red + background.green + background.blue
        for item in menu.get_children():
            label = item.get_child()
            if label is None:
                continue
            foreground = label.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            foreground_luma = foreground.red + foreground.green + foreground.blue
            assert foreground_luma > background_luma + 0.8
        menu.popdown()
    finally:
        editor.destroy()


def test_editor_draws_image_at_correct_position(pump):
    editor = EditorWindow(Image.new("RGBA", (400, 300), (0, 128, 255, 255)), Config())
    try:
        editor.show_all()
        pump(400)
        allocation = editor.canvas.get_allocation()
        assert allocation.width > 0

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, allocation.width, allocation.height)
        context = cairo.Context(surface)
        editor._on_draw(editor.canvas, context)

        cx = int(editor.offset[0] + editor.image.width * editor.scale / 2)
        cy = int(editor.offset[1] + editor.image.height * editor.scale / 2)
        data = surface.get_data()
        stride = surface.get_stride()
        index = cy * stride + cx * 4
        blue, green, red = data[index], data[index + 1], data[index + 2]
        assert (red, green, blue) == (0, 128, 255)
    finally:
        editor.destroy()


def test_tray_menu_uses_theme_icon_names():
    """El menu de bandeja se exporta por DBusMenu: necesita iconos nombrados."""
    from imagewatcher import ui

    item = ui.menu_item("Pantalla completa", "display", tray=True)
    assert isinstance(item, Gtk.ImageMenuItem)
    image = item.get_image()
    assert image is not None
    icon_name = image.get_icon_name()
    assert icon_name


def test_pil_to_pixbuf_copies_pixels_into_the_pixbuf():
    from imagewatcher.gtk_util import pil_to_pixbuf

    image = Image.new("RGBA", (8, 8), (10, 20, 30, 255))
    pixbuf = pil_to_pixbuf(image)
    del image

    import gc

    gc.collect()
    assert pixbuf.get_width() == 8
    assert bytes(pixbuf.get_pixels()[:4]) == bytes((10, 20, 30, 255))


def test_trim_memory_does_not_fail():
    from imagewatcher.memory import trim_memory

    trim_memory()
