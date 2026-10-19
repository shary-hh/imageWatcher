"""Prueba de renderizado del editor (composicion correcta en el canvas)."""
import cairo
import pytest
from PIL import Image

from imagewatcher.config import Config
from imagewatcher.editor import EditorWindow


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
