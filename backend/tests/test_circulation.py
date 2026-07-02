from shapely.geometry import Polygon

from services.circulation import _place_cage_by_mode


def test_place_cage_auto_convex_uses_bbox_corner():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = _place_cage_by_mode(rect, "auto", 2.0)
    assert cage is not None
    assert cage.area > 0
    minx, miny, maxx, maxy = cage.bounds
    assert minx == 0.0 and miny == 0.0  # anchored at the (0,0) corner


def test_place_cage_mode_2_centered():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = _place_cage_by_mode(rect, "2", 2.0)
    assert cage is not None
    cx, cy = cage.centroid.x, cage.centroid.y
    assert abs(cx - 5.0) < 0.5 and abs(cy - 3.0) < 0.5


def test_place_cage_invalid_mode_raises():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    try:
        _place_cage_by_mode(rect, "bogus", 2.0)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
