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
    """Spec 2026-07-04 (wall-thickness) §6/§6a -- cage dimensions are now
    CLEAR (w świetle) dimensions from the user, with 20cm of wall added to
    get the axis-to-axis rectangle the placement functions actually build:
    4.0m clear + 0.20m wall = 4.2m axis width, 5.5m + 0.20m = 5.7m axis depth."""
    assert CAGE_WIDTH_M == 4.2
    assert CAGE_DEPTH_M == 5.7


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


def test_place_circulation_centered_cage_gets_centerline_node_at_its_position():
    # Regression: cage_position="2" (środek traktu) places the cage in the
    # MIDDLE of the zone, not at a zone bbox extreme. _corridor_centerline()
    # always spans the full zone length with only 2 endpoint nodes -- without
    # _split_segment_at_cage_positions(), the evacuation graph would have no
    # node within CAGE_ENTRY_TOLERANCE_M of the cage, making it count as 0
    # reachable cages everywhere (all dots red), even though the corridor
    # physically passes right by it.
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (40, 0), (40, 12), (0, 12)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="2",
    )
    assert len(result.cage_polygons) == 1
    cage = result.cage_polygons[0]
    cage_x = cage.centroid.x

    # Centerline must be split so SOME segment endpoint lands at the cage's
    # own x position (not just at x=0/x=40).
    all_x = {p[0] for seg in result.centerline for p in seg.points}
    assert any(abs(x - cage_x) < 1e-6 for x in all_x), (
        f"no centerline node at cage x={cage_x}, only {sorted(all_x)}"
    )

    # And the evacuation dots must actually reach it -- not all-red.
    assert any(d.status != "red" for d in result.evacuation_dots)
    # Dots strictly inside the cage's own footprint are excluded (spec §5),
    # so the nearest sampled dot sits just outside it -- roughly half the
    # cage width from its centroid, not exactly 0. Anything close confirms
    # the node landed at the cage, not still 20m away at a zone extreme.
    dot_near_cage = min(result.evacuation_dots, key=lambda d: abs(d.x - cage_x))
    assert dot_near_cage.distance_m is not None
    assert dot_near_cage.distance_m < 5.0


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
    # mid_y clamped to maxy(6) - half, where half is now derived from the
    # grown (clear + 2*NET_SHRINK_M) width: (1.5 + 0.2) / 2 = 0.85.
    assert abs(y1 - 5.15) < 1e-6 and abs(y2 - 5.15) < 1e-6


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


def test_place_circulation_num_cages_two_zones_gets_two_cages():
    from services.circulation import place_circulation

    # L-shape: rectangle_decompose gives exactly 2 zones (20x10 and 10x10),
    # both large enough for the 4.2x5.7m cage.
    l_shape = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    result = place_circulation(
        l_shape,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=2,
    )
    assert len(result.cage_polygons) == 2
    # No overlap between the two cages.
    assert result.cage_polygons[0].intersection(result.cage_polygons[1]).area < 1e-9


def test_place_circulation_num_cages_defaults_to_one():
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
    assert len(result.cage_polygons) == 1


def test_place_circulation_num_cages_single_zone_places_requested_count():
    """User report 2026-07-11: slider 'Liczba klatek: 3' + klasyczne 'Umieść
    korytarz i klatkę' na prostym prostokącie (= 1 strefa) stawiało zawsze
    1 klatkę. Klasyczny tryb ma honorować num_cages także w obrębie jednej
    strefy (deterministyczne dopełnienie z puli kandydatów), nie tylko
    1 na strefę."""
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (40, 0), (40, 12), (0, 12)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=3,
    )
    assert len(result.cage_polygons) == 3
    # Pairwise disjoint.
    for i in range(len(result.cage_polygons)):
        for j in range(i + 1, len(result.cage_polygons)):
            assert result.cage_polygons[i].intersection(result.cage_polygons[j]).area < 1e-9
    # Corridor touches every cage (single shared corridor per zone).
    assert result.circulation_geometry is not None
    for cage in result.cage_polygons:
        assert result.circulation_geometry.distance(cage) < 1e-6

    # Determinism: classic mode has no rng — identical call, identical result.
    again = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=3,
    )
    assert [c.bounds for c in again.cage_polygons] == [c.bounds for c in result.cage_polygons]


def test_place_circulation_num_cages_exceeds_candidates_caps_silently():
    from services.circulation import place_circulation

    l_shape = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    result = place_circulation(
        l_shape,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=5,
    )
    # Silent cap still holds when candidates run out — but the floor is now
    # "co najmniej 1 na strefę zdolną pomieścić klatkę", nie sztywne 1/strefę
    # (user override 2026-07-11: num_cages honorowany w klasycznym trybie).
    assert 2 <= len(result.cage_polygons) <= 5
    for i in range(len(result.cage_polygons)):
        for j in range(i + 1, len(result.cage_polygons)):
            assert result.cage_polygons[i].intersection(result.cage_polygons[j]).area < 1e-9


def test_build_corridor_width_is_clear_not_axis():
    from services.circulation import _build_corridor
    from services.wall_geometry import NET_SHRINK_M, net_polygon

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    corridor = _build_corridor(zone, width=1.5)
    minx, miny, maxx, maxy = corridor.bounds
    built_width = maxy - miny
    assert abs(built_width - (1.5 + 2 * NET_SHRINK_M)) < 1e-6

    # After wall subtraction (net_polygon shrinks 0.10m per side), the
    # walkable width should be back to the requested 1.5m clear width.
    net = net_polygon(corridor)
    net_minx, net_miny, net_maxx, net_maxy = net.bounds
    assert abs((net_maxy - net_miny) - 1.5) < 1e-6


def test_corridor_centerline_axis_follows_trakt_rule_not_always_centered():
    """Was test_corridor_centerline_axis_unaffected_by_clear_width_change,
    asserting mid_y == 3.0 (geometric center) -- that encoded the OLD
    cage-agnostic "always center when no cage" rule. This 6m-deep zone with
    a 1.5m corridor (half=0.85) can NOT fit two >= MIN_TRAKT_DEPTH_M traktss
    (needs >= 9.7m), so centering would leave two ~2.15m dead bands exactly
    like the reported bug. Spec 2026-07-13 trakt-aware-corridor §A: the axis
    now moves to an edge so one side is ~0 and the other is a real
    >= MIN_TRAKT_DEPTH_M trakt."""
    from services.circulation import MIN_TRAKT_DEPTH_M, _corridor_centerline
    from services.wall_geometry import NET_SHRINK_M

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    assert y1 == y2
    half = (1.5 + 2 * NET_SHRINK_M) / 2.0
    south, north = y1 - half, 6.0 - (y1 + half)
    for band in (south, north):
        assert band <= 1e-6 or band >= MIN_TRAKT_DEPTH_M - 1e-6, f"martwy trakt {band:.2f} m"


def test_corridor_centerline_none_when_clear_width_plus_walls_too_wide():
    from services.circulation import _corridor_centerline

    # Zone is 6m in the cross-axis; a corridor whose BUILT width (clear +
    # 2*NET_SHRINK_M = 5.8 + 0.2 = 6.0) exactly consumes the whole zone
    # depth must be rejected (existing `if width >= h: return None` guard
    # must compare against the grown width, not the raw clear width).
    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=5.8)
    assert seg is None


def test_reshape_circulation_width_matches_build_corridor():
    from services.circulation import reshape_circulation

    footprint = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    result = reshape_circulation(
        footprint,
        centerline_points=[((0, 3), (20, 3))],
        corridor_width_m=1.5,
        cage_polygons=[],
    )
    minx, miny, maxx, maxy = result.circulation_geometry.bounds
    assert abs((maxy - miny) - (1.5 + 2 * 0.10)) < 1e-6


def _band_depths_horizontal(footprint, corridor):
    """(south_band, north_band) między korytarzem a krawędziami obrysu."""
    fminx, fminy, fmaxx, fmaxy = footprint.bounds
    cminx, cminy, cmaxx, cmaxy = corridor.bounds
    return cminy - fminy, fmaxy - cmaxy


def test_corridor_leaves_no_dead_band_user_footprint_20260713():
    """Repro exportu domko_export_2026-07-13: 68x12, klatka przy południowej
    elewacji -> stary kod zostawiał trakt 2.0 m, który krajacz wypełniał
    paskami 14.25x2 (proporcje 7:1). Nowa zasada: każdy trakt ~0 albo
    >= MIN_TRAKT_DEPTH_M."""
    from services.circulation import MIN_TRAKT_DEPTH_M, place_circulation

    footprint = Polygon([(-32, -2), (36, -2), (36, 10), (-32, 10)])
    result = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    assert result.circulation_geometry is not None
    south, north = _band_depths_horizontal(footprint, result.circulation_geometry)
    for band in (south, north):
        assert band <= 1e-6 or band >= MIN_TRAKT_DEPTH_M - 1e-6, f"martwy trakt {band:.2f} m"
    # korytarz nadal dotyka każdej klatki
    for cage in result.cage_polygons:
        assert result.circulation_geometry.distance(cage) < 1e-6


def test_corridor_axis_offset_double_mode_never_flush():
    """Zaktualizowane 2026-07-15 (Task 9): w dwutrakcie (prefer_flush=False)
    korytarz NIGDY nie skleja się z elewacją -- oba pasy muszą mieć legalną
    głębokość ([4,7] lub >=10), inaczej legacy clamp. Stary test zakładał
    flush w płytkiej strefie w dwutrakcie -- to teraz zabronione."""
    from services.circulation import MIN_TRAKT_DEPTH_M, _corridor_axis_offset, _band_depth_ok

    # strefa [0, 12], half=0.85, klatka przy dole: oba pasy legalne, oś blisko klatki
    mid = _corridor_axis_offset(0.0, 12.0, 0.85, (0.0, 5.7))
    south, north = (mid - 0.85) - 0.0, 12.0 - (mid + 0.85)
    assert _band_depth_ok(south) and _band_depth_ok(north)
    assert south > 1e-6 and north > 1e-6, "dwutrakt: żaden pas nie skleja się z elewacją"
    assert mid <= 5.7 + 0.85 + 1e-9  # touch klatki

    # strefa za płytka na dwa legalne pasy (0..7) w dwutrakcie -> legacy clamp
    mid2 = _corridor_axis_offset(0.0, 7.0, 0.85, (0.0, 5.7))
    assert 0.85 <= mid2 <= 7.0 - 0.85 + 1e-9

    # strefa zbyt płytka na regułę (0..3): legacy clamp, bez wyjątku
    mid3 = _corridor_axis_offset(0.0, 3.0, 0.85, (0.0, 5.7))
    assert 0.85 <= mid3 <= 3.0 - 0.85 + 1e-9

    # bez klatki, głęboka strefa: oś blisko środka (skan po siatce 0.1 m nie
    # trafia dokładnie w 6.0), oba pasy legalne
    mid4 = _corridor_axis_offset(0.0, 12.0, 0.85, None)
    assert abs(mid4 - 6.0) <= 0.1 + 1e-9
    assert _band_depth_ok((mid4 - 0.85) - 0.0) and _band_depth_ok(12.0 - (mid4 + 0.85))


def test_corridor_axis_offset_prefer_flush():
    from services.circulation import MIN_TRAKT_DEPTH_M, _corridor_axis_offset

    # strefa [0,12], half 0.85, bez klatki: galeriowiec wybiera krawędź
    # (jednotrakt >= MIN), nie środek
    mid = _corridor_axis_offset(0.0, 12.0, 0.85, None, prefer_flush=True)
    band_lo, band_hi = (mid - 0.85) - 0.0, 12.0 - (mid + 0.85)
    assert min(band_lo, band_hi) <= 1e-6
    assert max(band_lo, band_hi) >= MIN_TRAKT_DEPTH_M - 1e-9


def test_corridor_and_centerline_share_axis():
    from services.circulation import _build_corridor, _corridor_centerline
    from shapely.geometry import box

    zone = Polygon([(0, 0), (40, 0), (40, 12), (0, 12)])
    cage = box(0, 0, 4.2, 5.7)
    corridor = _build_corridor(zone, 1.5, cage)
    line = _corridor_centerline(zone, 1.5, cage)
    assert line is not None
    (x1, y1), (x2, y2) = line
    assert y1 == y2  # korytarz poziomy
    cminy, cmaxy = corridor.bounds[1], corridor.bounds[3]
    assert abs((cminy + cmaxy) / 2.0 - y1) < 1e-9


def test_l_shape_corridor_is_connected_and_reaches_both_wings():
    """Plan 2026-07-15 §B: na L korytarz to JEDEN spójny poligon łączący oba
    skrzydła (stare paski per strefa umiały się nie stykać), a centerline
    podąża za spine (wspólny staw)."""
    from shapely.ops import unary_union
    from services.circulation import place_circulation

    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    result = place_circulation(
        l_shape, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    # CAŁA komunikacja (korytarz + klatki jako spinacze) jest jednym spójnym
    # systemem -- klatka stojąca NA korytarzu może rozbić sam pas korytarza na
    # 2 widoczne kawałki, ale oba dotykają klatki, więc suma jest spójna.
    assert result.circulation_geometry.geom_type == "Polygon", (
        f"komunikacja na L musi być spójna, jest {result.circulation_geometry.geom_type}"
    )
    # a sam korytarz (bez klatek) dotyka każdej klatki
    corridor_only = result.circulation_geometry.difference(unary_union(result.cage_polygons))
    for cage in result.cage_polygons:
        assert corridor_only.distance(cage) < 1e-6, "korytarz musi dotykać każdej klatki"
    assert len(result.spine_segments) >= 2
    assert result.evacuation_dots
    assert any(d.status != "red" for d in result.evacuation_dots)
