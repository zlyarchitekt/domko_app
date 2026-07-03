from shapely.geometry import Polygon

from services.circulation import CAGE_DEPTH_M, CAGE_WIDTH_M, _place_cage_by_mode


def test_place_cage_auto_convex_uses_bbox_corner():
    rect = Polygon([(0, 0), (20, 0), (20, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "auto", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    assert cage.area > 0
    minx, miny, maxx, maxy = cage.bounds
    assert minx == 0.0 and miny == 0.0  # anchored at the (0,0) corner
    # Rectangle, not square: width along X, depth along Y (spec §4.2).
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6


def test_place_cage_mode_2_centered_rectangle():
    rect = Polygon([(0, 0), (20, 0), (20, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "2", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    cx, cy = cage.centroid.x, cage.centroid.y
    assert abs(cx - 10.0) < 0.5 and abs(cy - 6.0) < 0.5
    minx, miny, maxx, maxy = cage.bounds
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6


def test_place_cage_mode_1a_width_along_edge_depth_inward():
    # Longest edge is the bottom one (30m, horizontal): width runs along it,
    # depth extends inward (up).
    rect = Polygon([(0, 0), (30, 0), (30, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "1a", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    minx, miny, maxx, maxy = cage.bounds
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6
    assert abs(miny - 0.0) < 1e-6  # flush with the facade edge


def test_place_cage_invalid_mode_raises():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    try:
        _place_cage_by_mode(rect, "bogus", CAGE_WIDTH_M, CAGE_DEPTH_M)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_cage_constants_match_spec():
    """Spec 2026-07-03 (staircase-cage-rectangle) §4.1 -- pins the exact
    approved dimensions (400x550cm) so a drive-by edit can't silently shrink
    or grow the cage."""
    assert CAGE_WIDTH_M == 4.0
    assert CAGE_DEPTH_M == 5.5


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


def test_join_centerlines_single_segment():
    from services.circulation import _join_centerlines

    path = _join_centerlines([((0, 0), (10, 0))])
    assert path == [(0, 0), (10, 0)]


def test_join_centerlines_two_segments_already_touching():
    from services.circulation import _join_centerlines

    segs = [((0, 0), (10, 0)), ((10, 0), (10, 10))]
    path = _join_centerlines(segs)
    assert path == [(0, 0), (10, 0), (10, 10)]


def test_join_centerlines_reversed_segment_orientation():
    from services.circulation import _join_centerlines

    # Second segment's endpoints are listed far-then-near relative to path end.
    segs = [((0, 0), (10, 0)), ((10, 10), (10, 0))]
    path = _join_centerlines(segs)
    assert path == [(0, 0), (10, 0), (10, 10)]


def test_join_centerlines_three_segments_picks_nearest_each_step():
    from services.circulation import _join_centerlines

    # Start at (0,0)-(10,0). Nearest next endpoint to (10,0) is (10,0) of
    # the THIRD segment listed (not the second) -- verifies nearest-search,
    # not list order.
    segs = [
        ((0, 0), (10, 0)),
        ((20, 20), (30, 20)),  # far away, should be picked last
        ((10, 0), (10, 10)),   # near, should be picked second
    ]
    path = _join_centerlines(segs)
    assert path[0] == (0, 0)
    assert path[1] == (10, 0)
    assert path[2] == (10, 10)
    assert path[-1] in ((20, 20), (30, 20))


def test_join_centerlines_empty_list():
    from services.circulation import _join_centerlines

    assert _join_centerlines([]) == []


def test_classify_segment_loading_double_when_room_both_sides():
    from services.circulation import _classify_segment_loading

    # Wide zone: corridor in the middle, >= MIN_ROOM_WIDTH_M (2.4) of
    # room depth available on both sides.
    zone = Polygon([(0, 0), (20, 0), (20, 8), (0, 8)])
    segment = ((0, 4), (20, 4))  # horizontal centerline at mid-height
    loading = _classify_segment_loading(zone, segment, corridor_width=1.5)
    assert loading == "double"


def test_classify_segment_loading_single_when_room_one_side_only():
    from services.circulation import _classify_segment_loading

    # Corridor runs along one long edge -- no room depth on the far side.
    zone = Polygon([(0, 0), (20, 0), (20, 3.5), (0, 3.5)])
    segment = ((0, 0.75), (20, 0.75))  # centerline hugging the y=0 edge
    loading = _classify_segment_loading(zone, segment, corridor_width=1.5)
    assert loading == "single"


def test_distances_along_centerline_linear_path_one_cage():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0), (10, 10)]
    cage_points = [(0, 0)]
    distances = _distances_along_centerline(path, cage_points)
    assert distances == [0.0, 10.0, 20.0]


def test_distances_along_centerline_no_cages_returns_inf():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0)]
    distances = _distances_along_centerline(path, [])
    assert distances == [float("inf"), float("inf")]


def test_distances_along_centerline_picks_nearest_cage():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0), (20, 0)]
    cage_points = [(0, 0), (20, 0)]
    distances = _distances_along_centerline(path, cage_points)
    assert distances == [0.0, 10.0, 0.0]


def test_place_circulation_populates_centerline():
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
    assert len(result.centerline) >= 1
    seg = result.centerline[0]
    assert seg.loading in ("single", "double")
    assert seg.max_distance_m in (20.0, 40.0)
    assert isinstance(seg.exceeds_max, bool)


def test_place_circulation_centerline_exceeds_max_on_long_single_loaded_building():
    from services.circulation import place_circulation

    # 50m long, 3m deep -> definitely single-loaded, far end exceeds 20m.
    footprint = Polygon([(0, 0), (50, 0), (50, 3), (0, 3)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.4,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.0,
        cage_position="1a",
    )
    assert any(seg.loading == "single" for seg in result.centerline)
    assert any(seg.exceeds_max for seg in result.centerline)


def test_place_circulation_no_cage_gives_inf_distance_not_crash():
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=False,
        cage_size_m=2.5,
        cage_position="auto",
    )
    assert len(result.centerline) >= 1
    assert all(seg.exceeds_max is False for seg in result.centerline)  # inf never "exceeds" a real building
