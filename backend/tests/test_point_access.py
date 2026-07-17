"""Testy trybu klatkowego (plan 2026-07-16, referencje
docs/references/typologia-klatkowa.md)."""

import random

from shapely.geometry import Polygon

from services.layout import ApartmentSpec
from services.point_access import (
    HALL_DEPTH_M,
    anchor_candidates,
    build_point_core,
    core_polygon,
    point_zone_components,
    slice_point_zone,
)


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_build_point_core_north_flush_hall_inside():
    zone = _rect(0, 0, 23, 13.75)  # wzorzec 3 z referencji
    core = build_point_core(zone, "north")
    assert core is not None
    cage, hall = core
    # klatka dosunięta do północnej krawędzi, wyśrodkowana w x
    assert abs(cage.bounds[3] - 13.75) < 1e-6
    assert abs((cage.bounds[0] + cage.bounds[2]) / 2 - 11.5) < 1e-6
    # hol przylega od południa (wnętrza), głębokość HALL_DEPTH_M
    assert abs(hall.bounds[3] - cage.bounds[1]) < 1e-6
    assert abs((hall.bounds[3] - hall.bounds[1]) - HALL_DEPTH_M) < 1e-6
    # całość w strefie
    assert core_polygon(cage, hall).within(zone.buffer(1e-6))


def test_build_point_core_center_no_facade_contact():
    zone = _rect(0, 0, 17, 20)  # wzorzec 2: punktowiec, trzon bez okien
    core = build_point_core(zone, "center")
    assert core is not None
    cage, hall = core
    assert core_polygon(cage, hall).distance(zone.exterior) > 0.5


def test_build_point_core_none_when_zone_too_small():
    assert build_point_core(_rect(0, 0, 5, 5), "north") is None


def test_anchor_candidates_prefer_north_and_center():
    zone = _rect(0, 0, 23, 13.75)
    cands = anchor_candidates(zone)
    assert set(cands) <= {"north", "south", "east", "west", "center"}
    # north i center mają light_waste 0 -> przed south
    assert cands.index("north") < cands.index("south")
    assert cands.index("center") < cands.index("south")


def test_point_zone_components_all_touch_core():
    zone = _rect(0, 0, 23, 13.75)
    cage, hall = build_point_core(zone, "center")
    core = core_polygon(cage, hall)
    comps = point_zone_components(zone, core)
    assert len(comps) >= 3
    for poly, _horiz in comps:
        assert poly.distance(core) < 0.06


def test_slice_point_zone_units_touch_core_and_facade():
    """Wzorzec 5 z referencji: 5 mieszkań wiatraczkiem, każde dotyka trzonu."""
    zone = _rect(0, 0, 23, 13.75)
    cage, hall = build_point_core(zone, "center")
    core = core_polygon(cage, hall)
    specs = [
        ApartmentSpec(type="2Pd", min_area_m2=55, target_count=2),
        ApartmentSpec(type="2Pm", min_area_m2=45, target_count=2),
        ApartmentSpec(type="P1", min_area_m2=33, target_count=1),
    ]
    cells, leftover = slice_point_zone(zone, core, specs, rng=random.Random(1))
    assert 3 <= len(cells) <= 6
    for c in cells:
        assert c.polygon.distance(core) < 0.06, "mieszkanie bez styku z trzonem"
        assert c.polygon.exterior.intersection(zone.exterior).length > 1.0 or \
            c.polygon.boundary.intersection(zone.exterior).length > 1.0
    # pustka co najwyżej marginalna
    left_area = 0.0 if leftover is None or leftover.is_empty else leftover.area
    assert left_area / (zone.area - core.area) < 0.10
