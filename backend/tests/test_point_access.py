"""Testy trybu klatkowego (plan 2026-07-16, referencje
docs/references/typologia-klatkowa.md)."""

from shapely.geometry import Polygon

from services.point_access import (
    HALL_DEPTH_M,
    anchor_candidates,
    build_point_core,
    core_polygon,
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
