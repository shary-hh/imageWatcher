"""Pruebas del selector de region editable (mover / redimensionar)."""
from PIL import Image

from imagewatcher.region import RegionSelector, extract_freehand


class _Mouse:
    def __init__(self, x, y, button=1):
        self.x, self.y, self.button = x, y, button


def _selector(pump):
    selector = RegionSelector(Image.new("RGBA", (800, 600), (0, 0, 0, 255)), lambda img: None)
    pump(120)
    # Los imanes dependen del escritorio real; se desactivan salvo en sus tests.
    selector._snap_x = []
    selector._snap_y = []
    return selector


def test_region_moves_selection(pump):
    selector = _selector(pump)
    try:
        selector.rect = (100, 100, 200, 150)
        selector.mode = "moving"
        selector._drag_start = (100, 100)
        selector._rect_start = selector._ltrb(selector.rect)
        selector._on_motion(None, _Mouse(160, 130))
        assert selector.rect == (160, 130, 200, 150)
    finally:
        selector.destroy()


def test_region_resizes_from_corner(pump):
    selector = _selector(pump)
    try:
        selector.rect = (100, 100, 200, 150)
        selector.mode = "resizing"
        selector.handle = "se"
        selector._rect_start = selector._ltrb(selector.rect)
        selector._on_motion(None, _Mouse(500, 500))
        assert selector.rect == (100, 100, 400, 400)
    finally:
        selector.destroy()


def test_region_snaps_new_selection_and_edges(pump):
    selector = _selector(pump)
    try:
        selector._snap_x = [100, 400]
        selector._snap_y = [200]
        selector._on_press(None, _Mouse(105, 195))
        assert selector.mode == "creating"
        assert selector._drag_start == (100, 200)
        selector._on_motion(None, _Mouse(395, 305))
        assert selector.rect == (100, 200, 300, 105)
    finally:
        selector.destroy()


def test_region_snaps_moved_rect_edges(pump):
    selector = _selector(pump)
    try:
        selector._snap_x = [400]
        selector._snap_y = []
        selector.rect = (300, 50, 90, 100)
        selector.mode = "moving"
        selector._drag_start = (300, 50)
        selector._rect_start = selector._ltrb(selector.rect)
        selector._on_motion(None, _Mouse(305, 55))
        assert selector.rect == (310, 55, 90, 100)
    finally:
        selector.destroy()


def test_region_lasso_toggle(pump):
    from types import SimpleNamespace

    from gi.repository import Gdk

    selector = _selector(pump)
    try:
        assert selector.freehand_mode is False
        assert selector._on_key(None, SimpleNamespace(keyval=Gdk.KEY_l)) is True
        assert selector.freehand_mode is True
        assert selector._on_key(None, SimpleNamespace(keyval=Gdk.KEY_L)) is True
        assert selector.freehand_mode is False
    finally:
        selector.destroy()


def test_region_can_disable_magnets(pump):
    from types import SimpleNamespace

    from gi.repository import Gdk

    selector = RegionSelector(
        Image.new("RGBA", (800, 600), (0, 0, 0, 255)),
        lambda image: None,
        snap_enabled=False,
    )
    pump(120)
    try:
        assert selector.snap_enabled is False
        assert selector._snap_x == [] and selector._snap_y == []
        selector._snap_x = [100]
        selector._snap_y = [200]
        assert selector._snap_point((105, 195)) == (105, 195)
        assert selector._on_key(None, SimpleNamespace(keyval=Gdk.KEY_m)) is True
        assert selector.snap_enabled is True
        assert selector._snap_point((105, 195)) == (100, 200)
    finally:
        selector.destroy()


def test_region_handle_detection(pump):
    selector = _selector(pump)
    try:
        selector.rect = (100, 100, 200, 150)
        assert selector._handle_at(100, 100) == "nw"
        assert selector._handle_at(300, 250) == "se"
        assert selector._handle_at(200, 100) == "n"
        assert selector._handle_at(150, 175) is None
        assert selector._in_rect(150, 175) is True
    finally:
        selector.destroy()


def test_fixed_region_centers_and_accepts_on_click(pump):
    captured = {}

    def done(image):
        captured["image"] = image

    selector = RegionSelector(
        Image.new("RGBA", (800, 600), (10, 20, 30, 255)),
        done,
        fixed_size=(200, 100),
    )
    pump(120)
    try:
        assert selector.rect is not None
        assert selector.rect[2:] == (200, 100)
        selector._on_press(None, _Mouse(400, 300))
        assert captured["image"].size == (200, 100)
        assert selector.rect == (300, 250, 200, 100)
    finally:
        selector.destroy()


def test_fixed_region_clamps_to_screen_edges(pump):
    selector = RegionSelector(
        Image.new("RGBA", (800, 600), (0, 0, 0, 255)),
        lambda image: None,
        fixed_size=(200, 100),
    )
    pump(120)
    try:
        assert selector._center_rect(0, 0, 200, 100) == (0, 0, 200, 100)
        assert selector._center_rect(799, 599, 200, 100) == (600, 500, 200, 100)
    finally:
        selector.destroy()


def test_freehand_extracts_polygon_with_transparency():
    base = Image.new("RGBA", (400, 300), (255, 0, 0, 255))
    points = [(100, 100), (200, 100), (150, 200)]
    image = extract_freehand(base, points)
    assert image.size == (101, 101)
    assert image.mode == "RGBA"
    assert image.getpixel((50, 10))[3] == 255
    assert image.getpixel((1, 90))[3] == 0


def test_freehand_selector_captures_on_release(pump):
    captured = {}

    def done(image):
        captured["image"] = image

    selector = RegionSelector(
        Image.new("RGBA", (400, 300), (0, 255, 0, 255)),
        done,
        freehand=True,
    )
    pump(120)
    try:
        selector.mode = "freehand"
        selector._freehand_points = [(100, 100), (200, 100), (150, 200)]
        selector._on_release(None, _Mouse(150, 200))
        assert captured["image"].size == (101, 101)
        assert captured["image"].getpixel((50, 10))[3] == 255
        assert captured["image"].getpixel((1, 90))[3] == 0
    finally:
        selector.destroy()
