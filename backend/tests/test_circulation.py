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


def test_corridor_centerline_horizontal_zone():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (20, 0), (20, 4), (0, 4)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    assert abs(y1 - 2.0) < 1e-6 and abs(y2 - 2.0) < 1e-6  # centered on mid_y
    assert {round(x1), round(x2)} == {0, 20}


def test_corridor_centerline_vertical_zone():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (4, 0), (4, 20), (0, 20)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    assert abs(x1 - 2.0) < 1e-6 and abs(x2 - 2.0) < 1e-6  # centered on mid_x
    assert {round(y1), round(y2)} == {0, 20}


def test_corridor_centerline_aligns_to_cage():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    # centroid.y = 5.8 -- deliberately close to maxy(6) so the clamp
    # (mid_y <= maxy - half) actually engages instead of just passing
    # cage_y through unclamped.
    cage = Polygon([(0, 5.6), (2, 5.6), (2, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=1.5, cage_polygon=cage)
    assert seg is not None
    (_, y1), (_, y2) = seg
    assert abs(y1 - 5.25) < 1e-6 and abs(y2 - 5.25) < 1e-6  # mid_y clamped to maxy(6) - half(0.75)


def test_corridor_centerline_none_when_too_narrow():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (1.0, 0), (1.0, 20), (0, 20)])  # width 1.0m < corridor 1.5m
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is None
