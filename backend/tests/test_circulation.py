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


def test_place_circulation_simple_rectangle():
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
    )
    assert len(result.zones) == 1
    assert result.circulation_geometry is not None
    assert result.circulation_geometry.area > 0
    assert len(result.cage_polygons) == 1
    # circulation_geometry is already the union of cage + corridor (built by
    # progressively unary_union-ing both into it) — cage_polygons is exposed
    # separately for styling/API purposes but is a SUBSET of it, not
    # additional area. remainder + circulation_geometry alone reconstructs
    # the footprint.
    total = result.remainder.area + result.circulation_geometry.area
    assert abs(total - footprint.area) < 1e-3


def test_place_circulation_concave_u_shape_no_area_lost():
    from services.circulation import place_circulation

    u_shape = Polygon([
        (0, 0), (2, 0), (2, 6), (10, 6), (10, 0), (12, 0),
        (12, 8), (0, 8),
    ])
    result = place_circulation(
        u_shape,
        corridor_width_m=1.4,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.0,
        cage_position="auto",
    )
    # circulation_geometry already includes cage area (see comment in the
    # simple-rectangle test above) — don't double-count cage_polygons.
    total = result.remainder.area + result.circulation_geometry.area
    assert abs(total - u_shape.area) < 1e-3
    # This is the regression case for the audit bug: the old bsp_zones()
    # produced a zone that was STILL concave here. Every zone we placed
    # circulation in must now be non-concave.
    from services.bsp import concave_vertices
    for zone in result.zones:
        assert not concave_vertices(zone.polygon), "zone still concave after rectangle_decompose"
