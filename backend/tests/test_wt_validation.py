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
