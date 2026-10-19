"""Pruebas del editor de imagenes."""
import os

import pytest
from PIL import Image

from imagewatcher.config import Config
from imagewatcher.editor import EditorWindow


@pytest.fixture
def editor():
    window = EditorWindow(Image.new("RGBA", (320, 240), (0, 128, 255, 255)), Config())
    yield window
    window.destroy()


def test_annotations_and_undo(editor, pump):
    editor._push_undo()
    editor._raster_line([(5, 5), (100, 100)], 4, (255, 0, 0, 255))
    editor._push_undo()
    editor._raster_arrow((10, 10), (150, 150), 3, (0, 255, 0, 255))
    editor._push_undo()
    editor._raster_rect((20, 20), (120, 90), 2, (255, 255, 0, 255))
    editor._push_undo()
    editor._raster_ellipse((30, 30), (140, 100), 2, (255, 0, 255, 255))
    editor._push_undo()
    editor._raster_alpha_line([(1, 1), (200, 1)], 10, (255, 255, 0, 90))
    editor._push_undo()
    editor._raster_region_effect((0, 0), (60, 60), "blur")
    editor._push_undo()
    editor._raster_region_effect((0, 0), (60, 60), "pixelate")
    assert len(editor.undo_stack) >= 7
    editor._undo()
    editor._redo()


@pytest.mark.parametrize(
    "effect",
    [
        "grayscale",
        "invert",
        "blur",
        "sharpen",
        "pixelate",
        "rotate_cw",
        "rotate_ccw",
        "rotate_180",
        "flip_h",
        "flip_v",
    ],
)
def test_effects(editor, pump, effect):
    editor._apply_effect(effect)
    assert editor.image.width > 0


@pytest.mark.parametrize("name", ["out.png", "out.jpg", "out.bmp", "out.gif", "out.pdf"])
def test_save_formats(editor, tmp_path, name):
    path = os.path.join(tmp_path, name)
    editor._write_image(path)
    assert os.path.exists(path)
    assert os.path.getsize(path) > 0


def test_resize_and_crop(editor):
    editor._set_image(editor.image.resize((160, 120)), refresh_original=True)
    assert editor.image.size == (160, 120)
    editor._pending_crop = (10, 10, 50, 40)
    editor._crop_to_selection()
    assert editor.image.size == (50, 40)


def test_copy_to_clipboard(editor):
    editor._copy_clipboard()


def test_mouse_wheel_zooms(editor, pump):
    from types import SimpleNamespace

    from gi.repository import Gdk

    editor._set_zoom(1.0)
    up = SimpleNamespace(direction=Gdk.ScrollDirection.UP)
    assert editor._on_scroll(editor.canvas, up) is True
    assert editor.scale > 1.0

    down = SimpleNamespace(direction=Gdk.ScrollDirection.DOWN)
    assert editor._on_scroll(editor.canvas, down) is True
    assert editor.scale < 1.0

    smooth = SimpleNamespace(
        direction=Gdk.ScrollDirection.SMOOTH,
        get_scroll_deltas=lambda: (False, 0.0, -0.5),
    )
    before = editor.scale
    assert editor._on_scroll(editor.canvas, smooth) is True
    assert editor.scale > before


def test_ctrl_plus_minus_zoom(editor):
    from types import SimpleNamespace

    from gi.repository import Gdk

    def key(keyval):
        return SimpleNamespace(state=Gdk.ModifierType.CONTROL_MASK, keyval=keyval)

    editor._set_zoom(1.0)
    assert editor._on_key(editor, key(Gdk.KEY_plus)) is True
    assert editor.scale > 1.0
    assert editor._on_key(editor, key(Gdk.KEY_minus)) is True
    assert editor.scale < 1.25
    before = editor.scale
    assert editor._on_key(editor, key(Gdk.KEY_equal)) is True
    assert editor.scale > before


def test_new_brush_tools(editor):
    editor._push_undo()
    editor._raster_airbrush([(10, 10), (30, 30)], 8, (255, 0, 0, 255))
    editor._push_undo()
    editor._raster_calligraphy([(5, 5), (60, 60), (120, 20)], 8, (0, 0, 255, 255))
    editor._push_undo()
    editor._raster_callout((10, 10), (120, 80), 3, (0, 0, 0, 255))
    editor._push_undo()
    editor._raster_retouch([(20, 20), (40, 40)], 20)
    editor._push_undo()
    editor._commit_cursor_stamp(50, 50)
    assert editor.image.size == (320, 240)


def test_lasso_selection_crops_to_polygon(editor):
    editor._pending_lasso = [(10, 10), (80, 10), (80, 60), (10, 60)]
    editor._crop_to_selection()
    assert editor.image.size == (71, 51)


def test_channel_balance():
    from imagewatcher.editor import channel_balance

    image = Image.new("RGBA", (10, 10), (100, 100, 100, 255))
    out = channel_balance(image, 20, 0, -20)
    assert out.getpixel((0, 0))[:3] == (100 + int(20 * 2.55), 100, 100 - int(20 * 2.55))


def test_drop_shadow_grows_canvas():
    from imagewatcher.editor import add_drop_shadow

    image = Image.new("RGBA", (20, 20), (255, 0, 0, 255))
    shadow = add_drop_shadow(image, offset=5, blur=3, opacity=60)
    assert shadow.size == (30, 30)

