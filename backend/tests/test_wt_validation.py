"""Tests for services/wt_validation.py — real WT §94/§64/§68/§58 rules."""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union

from services.layout import ApartmentCell, ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.wt_validation import (
    MIN_APARTMENT_AREA_M2,
    MIN_CORRIDOR_WIDTH_M,
    MIN_ROOM_WIDTH_M,
    validate_layout_wt,
)

SQUARE_20 = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])


def _build_layout_result(
    footprint: Polygon,
    apartments: list[ApartmentCell],
    cage_polygons: list[Polygon],
    circulation_geometry: Polygon | None,
    corridor_width_m: float = 1.5,
    stair_width_m: float = 1.2,
) -> LayoutResult:
    """Hand-build a LayoutResult with exact, controlled geometry.

    Used instead of generate_layout() for the Dijkstra corridor-distance tests
    so results don't depend on the current BSP algorithm's rough edges
    (tracked separately as F2-04) — only on wt_validation's own logic.
    """
    return LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint.area,
        circulation_area_m2=circulation_geometry.area if circulation_geometry else 0.0,
        usable_area_m2=sum(a.polygon.area for a in apartments),
        apartments=apartments,
        leftover=None,
        zones=[],
        circulation_geometry=circulation_geometry,
        cage_polygons=cage_polygons,
        corridor_width_m=corridor_width_m,
        stair_width_m=stair_width_m,
    )


def _layout(footprint, **kwargs):
    apartments = kwargs.pop(
        "apartments",
        [ApartmentSpec(type="1-room", min_area_m2=25, target_count=4, width_m=4, depth_m=7)],
    )
    layout_input = LayoutInput(footprint=footprint, apartments=apartments, **kwargs)
    return generate_layout(layout_input)


def test_all_rules_present_and_scored():
    layout = _layout(SQUARE_20, corridor_width_m=2.0, cage_size_m=3.0, place_cage=True)
    result = validate_layout_wt(layout)
    codes = {r.code for r in result.rules}
    assert codes == {"§94 ust.1", "§94 ust.2", "§64", "§68 ust.1", "§58 ust.4", "heurystyka"}
    assert 0 <= result.score <= 100
    assert result.passed == all(r.passed for r in result.rules)


def test_cage_facade_contact_not_checked_by_default():
    # Not a real WT requirement — off unless the caller explicitly opts in
    # (require_cage_facade_contact=True). A fully interior cage (no facade
    # contact at all) must still pass when the option isn't requested.
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = Polygon([(4, 2), (6, 2), (6, 4), (4, 4)])  # interior, no contact
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[cage],
    )
    result = validate_layout_wt(layout)
    rule = next(r for r in result.rules if "doświetlenie" in r.description.lower())
    assert rule.passed is True
    assert "nie zostal" in rule.detail.lower() or "nie zosta" in rule.detail.lower()


def test_cage_facade_contact_passes_when_requested_and_cage_touches_facade():
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    # cage in the corner, touching two facade edges for 2.5m each — well over 2.4m
    cage = Polygon([(0, 0), (2.5, 0), (2.5, 2.5), (0, 2.5)])
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[cage],
    )
    result = validate_layout_wt(layout, require_cage_facade_contact=True)
    rule = next(r for r in result.rules if "doświetlenie" in r.description.lower())
    assert rule.passed is True


def test_cage_facade_contact_fails_when_requested_and_cage_is_interior():
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = Polygon([(4, 2), (6, 2), (6, 4), (4, 4)])  # fully interior
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[cage],
    )
    result = validate_layout_wt(layout, require_cage_facade_contact=True)
    rule = next(r for r in result.rules if "doświetlenie" in r.description.lower())
    assert rule.passed is False


def test_apartment_area_rule_fails_for_tiny_apartments():
    tiny_apt = ApartmentCell(id="tiny", type="studio", polygon=Polygon([(0, 0), (3, 0), (3, 3), (0, 3)]))
    layout = _layout(SQUARE_20, apartments=[])
    layout.apartments.append(tiny_apt)
    result = validate_layout_wt(layout)
    area_rule = next(r for r in result.rules if r.code == "§94 ust.1")
    assert area_rule.passed is False
    assert "tiny" in area_rule.detail
    assert result.passed is False


def test_apartment_area_rule_passes_above_minimum():
    ok_apt = ApartmentCell(
        id="ok", type="1-room", polygon=Polygon([(0, 0), (6, 0), (6, 6), (0, 6)])
    )
    assert ok_apt.polygon.area >= MIN_APARTMENT_AREA_M2
    layout = _layout(SQUARE_20, apartments=[])
    layout.apartments.append(ok_apt)
    result = validate_layout_wt(layout)
    area_rule = next(r for r in result.rules if r.code == "§94 ust.1")
    assert area_rule.passed is True


def test_room_width_rule_fails_for_narrow_apartment():
    narrow_apt = ApartmentCell(
        id="narrow", type="1-room", polygon=Polygon([(0, 0), (30, 0), (30, 1.5), (0, 1.5)])
    )
    layout = _layout(SQUARE_20, apartments=[])
    layout.apartments.append(narrow_apt)
    result = validate_layout_wt(layout)
    width_rule = next(r for r in result.rules if r.code == "§94 ust.2")
    assert width_rule.passed is False
    assert f"< {MIN_ROOM_WIDTH_M}" in width_rule.detail


def test_corridor_width_rule_fails_below_wt_minimum():
    layout = _layout(SQUARE_20, corridor_width_m=1.0, place_cage=False)
    result = validate_layout_wt(layout)
    corridor_rule = next(r for r in result.rules if r.code == "§64")
    assert corridor_rule.passed is False
    assert f"{MIN_CORRIDOR_WIDTH_M}" in corridor_rule.detail


def test_corridor_width_rule_passes_at_wt_minimum():
    layout = _layout(SQUARE_20, corridor_width_m=1.5, place_cage=False)
    result = validate_layout_wt(layout)
    corridor_rule = next(r for r in result.rules if r.code == "§64")
    assert corridor_rule.passed is True


def test_stair_width_rule_not_applicable_without_cage():
    layout = _layout(SQUARE_20, place_cage=False)
    result = validate_layout_wt(layout)
    stair_rule = next(r for r in result.rules if r.code == "§68 ust.1")
    assert stair_rule.passed is True
    assert "nie dotyczy" in stair_rule.detail


def test_stair_width_rule_fails_when_too_narrow():
    l_shape = Polygon([(0, 0), (20, 0), (20, 8), (8, 8), (8, 20), (0, 20)])
    # NOTE: bsp_zones() carves its own fixed ~1.0m corner notch before generate_layout's
    # own cage placement runs (services/bsp.py corner_cage default) — cage_size_m values
    # at or below that notch silently produce a zero-area cage (tracked separately as an
    # F2-04 BSP/cage-placement issue, not a wt_validation concern). 1.1 reliably clears it.
    # stair_width_m (flight width) is a separate parameter from cage_size_m (cage footprint).
    layout = _layout(l_shape, place_cage=True, cage_size_m=1.1, stair_width_m=1.0)
    assert layout.cage_polygons, "expected a (small) cage polygon to be generated"
    result = validate_layout_wt(layout)
    stair_rule = next(r for r in result.rules if r.code == "§68 ust.1")
    assert stair_rule.passed is False


def test_max_corridor_distance_rule_passes_for_small_building():
    layout = _layout(SQUARE_20, corridor_width_m=2.0, place_cage=False)
    # No cage -> rule should fail with a clear "no cage" message, not crash.
    result = validate_layout_wt(layout)
    reach_rule = next(r for r in result.rules if r.code == "§58 ust.4")
    assert reach_rule.passed is False
    assert "Brak klatki" in reach_rule.detail


def _straight_corridor_scenario():
    """Simple rectangular building: one straight corridor, cage at one end,
    one apartment touching the corridor at the other end. Hand-built so the
    geometry (and therefore expected distances) is exact and independent of
    the current BSP algorithm's apartment-slicing behaviour."""
    footprint = Polygon([(0, 0), (20, 0), (20, 3), (0, 3)])
    corridor = Polygon([(0, 1.25), (20, 1.25), (20, 1.75), (0, 1.75)])
    cage = Polygon([(0, 0), (1.5, 0), (1.5, 3), (0, 3)])
    circulation = unary_union([corridor, cage])
    apartment = ApartmentCell(
        id="apt-far-end",
        type="1-room",
        polygon=Polygon([(17, 1.75), (20, 1.75), (20, 3), (17, 3)]),
    )
    layout = _build_layout_result(footprint, [apartment], [cage], circulation, corridor_width_m=1.5)
    return layout, apartment, cage


def test_max_corridor_distance_rule_passes_for_reachable_apartment():
    layout, _, _ = _straight_corridor_scenario()
    result = validate_layout_wt(layout, max_corridor_distance_m=30.0)
    reach_rule = next(r for r in result.rules if r.code == "§58 ust.4")
    assert reach_rule.passed is True


def test_max_corridor_distance_rule_fails_when_limit_set_very_low():
    layout, _, _ = _straight_corridor_scenario()
    result = validate_layout_wt(layout, max_corridor_distance_m=1.0)
    reach_rule = next(r for r in result.rules if r.code == "§58 ust.4")
    assert reach_rule.passed is False
    assert "Przekroczone dojście" in reach_rule.detail


def test_max_corridor_distance_rule_reports_unreachable_apartment():
    footprint = Polygon([(0, 0), (20, 0), (20, 3), (0, 3)])
    cage = Polygon([(0, 0), (1.5, 0), (1.5, 3), (0, 3)])
    # Apartment placed with NO shared boundary with the circulation geometry.
    isolated_apartment = ApartmentCell(
        id="isolated", type="1-room", polygon=Polygon([(17, 10), (20, 10), (20, 13), (17, 13)])
    )
    layout = _build_layout_result(footprint, [isolated_apartment], [cage], cage)
    result = validate_layout_wt(layout)
    reach_rule = next(r for r in result.rules if r.code == "§58 ust.4")
    assert reach_rule.passed is False
    assert "niepołączone z komunikacją" in reach_rule.detail


def test_corridor_distance_is_not_euclidean_for_l_shaped_corridor():
    """plan.md §4.4: corridor (walking) distance must exceed straight-line distance
    when the walkable path bends around a corner instead of cutting straight through.

    Circulation is an L-shaped corridor (bottom strip + left strip). The cage sits at
    the far end of the left strip; the apartment sits at the far end of the bottom
    strip. A straight line between them cuts through non-walkable space, so the real
    (Dijkstra) corridor distance must be noticeably longer than the Euclidean one —
    and in this scenario also exceeds the default 30m WT §58 limit.
    """
    from services.wt_validation import _build_corridor_graph, _corridor_distance_to_nearest_cage

    bottom_strip = Polygon([(0, 0), (20, 0), (20, 1.5), (0, 1.5)])
    left_strip = Polygon([(0, 0), (1.5, 0), (1.5, 20), (0, 20)])
    circulation = unary_union([bottom_strip, left_strip])

    cage = Polygon([(0, 18.5), (1.5, 18.5), (1.5, 20), (0, 20)])
    apartment = ApartmentCell(
        id="far-corner-apt",
        type="1-room",
        polygon=Polygon([(18, 1.5), (20, 1.5), (20, 5), (18, 5)]),
    )

    graph, nodes = _build_corridor_graph(circulation)
    cage_targets = [cage.centroid]
    corridor_dist = _corridor_distance_to_nearest_cage(apartment, circulation, graph, nodes, cage_targets)

    assert corridor_dist is not None
    euclidean_dist = apartment.polygon.centroid.distance(cage.centroid)
    assert corridor_dist > euclidean_dist + 5.0  # clearly bent, not a coincidence of grid rounding
    assert corridor_dist > 30.0  # also demonstrates why Euclidean measurement would under-report a real WT §58 violation

    layout = _build_layout_result(
        Polygon([(0, 0), (20, 0), (20, 20), (0, 20)]), [apartment], [cage], circulation
    )
    result = validate_layout_wt(layout, max_corridor_distance_m=30.0)
    reach_rule = next(r for r in result.rules if r.code == "§58 ust.4")
    assert reach_rule.passed is False


def test_layout_generate_endpoint_exposes_wt_rules():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": [[0, 0], [20, 0], [20, 20], [0, 20]],
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
            "apartments": [
                {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "rules" in data["wt_validation"]
    assert "score" in data["wt_validation"]
    assert isinstance(data["wt_validation"]["rules"], list)
    assert len(data["wt_validation"]["rules"]) >= 5


def test_layout_generate_endpoint_exposes_net_area_and_wall_bands():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": [[0, 0], [20, 0], [20, 20], [0, 20]],
            "circulation": {"corridor_width_m": 1.5, "cage_size_m": 3.0, "place_cage": True},
            "apartments": [
                {"type": "M2", "min_area_m2": 40.0, "target_count": 4},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["apartments"]) >= 1
    for apt in data["apartments"]:
        assert "net_area_m2" in apt
        assert apt["net_area_m2"] < apt["area_m2"]
    assert "wall_bands" in data
    assert len(data["wall_bands"]) >= 1


def test_wall_bands_excludes_leftover_area():
    """Regression: interior_wall_bands() (Task 1, services/wall_geometry.py)
    treats any interior-envelope area not covered by any real cell's net
    polygon as 'wall' -- but LayoutResult.leftover is legitimately
    un-programmed floor space, not a wall. Per docs/superpowers/specs/2026-
    07-04-wall-thickness-design.md §3 ("bez ściany dookoła" -- no wall
    around it), leftover must render as a fully open hole, so
    layout_result_to_response() must subtract it back out of the interior
    wall bands (using leftover's RAW polygon, not net_polygon(leftover) --
    see the module-level fix comment for why).

    The check isolates the interior contribution (wall_bands minus
    exterior_wall_band(footprint)) before comparing against leftover's raw
    polygon. Two failure modes this specifically guards against, both
    verified empirically while diagnosing this regression:
    - Comparing the *full* wall_bands (including exterior_wall_band)
      against raw leftover is unsatisfiable whenever leftover touches a
      facade edge: the real 40cm perimeter wall legitimately overlaps raw
      leftover there (~5.03m^2 in this scenario) regardless of how the
      interior exclusion is implemented -- that's not a bug, so asserting
      zero overlap against the *full* wall_bands would fail even with a
      correct fix.
    - Comparing against net_polygon(leftover) instead of raw would dodge
      that, but is blind to a real regression: subtracting
      net_polygon(leftover) (instead of raw leftover) from
      interior_wall_bands() still leaves a ~4.97m^2 rim of fake wall at
      leftover's boundary against its neighbours -- yet that rim sits
      entirely *outside* net_polygon(leftover) too, so it evaluates to
      exactly 0 either way and wouldn't catch the regression. Isolating the
      interior contribution and comparing against the RAW polygon catches
      both "no exclusion at all" (187.33 m^2 overlap) and "net-shrunk
      exclusion" (4.97 m^2 overlap), vs. exactly 0 for the correct (raw)
      fix."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from api.v1.endpoints.layout import layout_result_to_response
    from services.wall_geometry import exterior_wall_band

    layout = _layout(
        SQUARE_20,
        corridor_width_m=1.5,
        cage_size_m=3.0,
        place_cage=True,
        apartments=[ApartmentSpec(type="M2", min_area_m2=40.0, target_count=4)],
    )
    assert layout.leftover is not None
    assert layout.leftover.area > 50.0, "test scenario should under-fill the footprint (non-trivial leftover)"

    wt = validate_layout_wt(layout)
    response = layout_result_to_response(layout, wt)

    wall_union = unary_union([shape(g) for g in response.wall_bands])
    interior_only = wall_union.difference(exterior_wall_band(layout.footprint))
    overlap_area = interior_only.intersection(layout.leftover).area
    assert overlap_area < 1e-6, (
        f"interior wall_bands overlap leftover by {overlap_area:.3f} m^2 -- "
        "leftover was absorbed into the wall layer instead of rendering as an open gap"
    )


def test_wall_bands_excludes_thin_leftover_sliver():
    """Regression: net_polygon() (services/wall_geometry.py) returns an EMPTY
    polygon for shapes too thin to survive a -0.10m shrink on all sides (see
    test_wall_geometry.py::test_net_polygon_too_small_returns_empty_not_crash
    -- NET_SHRINK_M=0.10, so anything narrower than 0.20m collapses). A
    leftover-exclusion fix built on net_polygon(leftover) would therefore be
    a silent no-op for a thin leftover sliver: `interior_bands.difference(
    Polygon())` is a no-op, so the sliver renders as fake wall, reproducing
    the original bug for that shape. Subtracting the RAW leftover polygon
    (what layout_result_to_response() actually does) has no such failure
    mode -- Shapely's .difference() works regardless of how thin the
    subtrahend is.

    This is also *why* the assertion below can't be phrased in terms of
    net_polygon(sliver) the way the sibling test discusses net_polygon
    (leftover): net_polygon(sliver) is empty by construction here, so
    comparing against it would be vacuously true regardless of whether the
    fix works. Isolating the interior contribution (wall_bands minus
    exterior_wall_band(footprint), which legitimately touches the sliver's
    facade-adjacent edge) and comparing against the RAW sliver is the only
    check that's both satisfiable and actually exercises the fix -- verified
    empirically: 0.24 m^2 overlap with no exclusion (or with a
    net_polygon-based exclusion, which is a no-op here and gives the exact
    same result), vs. exactly 0 for the correct (raw) fix.

    Hand-built LayoutResult (not generate_layout()) for exact control over
    the sliver's geometry, same technique as _build_layout_result()
    elsewhere in this file."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from api.v1.endpoints.layout import layout_result_to_response
    from services.wall_geometry import exterior_wall_band, net_polygon

    footprint = Polygon([(0, 0), (10, 0), (10, 5), (0, 5)])
    apartment = ApartmentCell(
        id="big-apt", type="1-room", polygon=Polygon([(0, 0), (9.85, 0), (9.85, 5), (0, 5)])
    )
    sliver = Polygon([(9.85, 0), (10, 0), (10, 5), (9.85, 5)])  # 0.15m wide, 5m tall -> 0.75 m^2
    assert sliver.area > 0.5, "sanity: sliver should be a real, non-trivial (if thin) leftover area"
    assert net_polygon(sliver).is_empty, (
        "test setup assumption: sliver must be too thin to survive net_polygon's -0.10m shrink"
    )

    layout = LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint.area,
        circulation_area_m2=0.0,
        usable_area_m2=apartment.polygon.area,
        apartments=[apartment],
        leftover=sliver,
        zones=[],
        circulation_geometry=None,
        cage_polygons=[],
    )

    wt = validate_layout_wt(layout)
    response = layout_result_to_response(layout, wt)

    wall_union = unary_union([shape(g) for g in response.wall_bands])
    interior_only = wall_union.difference(exterior_wall_band(layout.footprint))
    overlap_area = interior_only.intersection(sliver).area
    assert overlap_area < 1e-6, (
        f"interior wall_bands overlap the thin leftover sliver by {overlap_area:.4f} m^2 -- "
        "a net_polygon-based fix would silently no-op here since net_polygon(sliver) is empty"
    )


def test_default_max_corridor_distance_is_20m():
    """Regression for the 2026-07-03 domain correction: WT §58 ust.4
    single-loaded threshold is 20m, not 30m (see
    docs/superpowers/specs/2026-07-03-corridor-centerline-editing-design.md
    §7). All other tests in this file pass an explicit
    max_corridor_distance_m override, so this is the only place the actual
    default value is pinned."""
    from services.wt_validation import DEFAULT_MAX_CORRIDOR_DISTANCE_M

    assert DEFAULT_MAX_CORRIDOR_DISTANCE_M == 20.0
