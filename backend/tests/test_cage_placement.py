"""Testy iteracyjnego auto-placementu klatek (spec 2026-07-04-cage-
placement-iterations §7)."""

import pytest
from shapely.geometry import Polygon

from services.cage_placement import CageWeights, iterate_cage_placement


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


FOOTPRINT = _rect(0, 0, 40, 12)


def test_determinism():
    a = iterate_cage_placement(FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5)
    b = iterate_cage_placement(FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5)
    assert [m.score for m in a[1]] == [m.score for m in b[1]]
    assert a[2] == b[2]


def test_respects_num_cages_filter():
    result, metas, _ = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=CageWeights(), iterations=10
    )
    assert 1 <= len(result.cage_polygons) <= 2
    assert all(1 <= m.cages_count <= 2 for m in metas)


def test_cages_inside_footprint():
    result, _, _ = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5
    )
    for cage in result.cage_polygons:
        assert FOOTPRINT.buffer(1e-6).contains(cage)


def test_best_seed_lowest_score():
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=10
    )
    assert best_seed == min(metas, key=lambda m: m.score).seed


def test_egress_weight_prefers_fewer_red_dots():
    # długi budynek 80m: 1 klatka nie pokryje limitu 20m -> egress preferuje więcej klatek
    long_fp = _rect(0, 0, 80, 12)
    w = CageWeights(egress=1.0, count=0.0, corners=0.0, ends=0.0, spread=0.0)
    result, metas, best_seed = iterate_cage_placement(
        long_fp, 1.5, num_cages=4, weights=w, iterations=10
    )
    best = next(m for m in metas if m.seed == best_seed)
    assert best.components["egress"] == min(m.components["egress"] for m in metas)


def test_spread_prefers_separated_cages():
    w = CageWeights(egress=0.0, count=0.0, corners=0.0, ends=0.0, spread=1.0)
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=w, iterations=10
    )
    best = next(m for m in metas if m.seed == best_seed)
    assert best.components["spread"] == min(m.components["spread"] for m in metas)


def test_footprint_too_small_raises():
    tiny = _rect(0, 0, 3, 3)  # mniejszy niż klatka 4.2x5.7
    with pytest.raises(ValueError, match="zbyt mały"):
        iterate_cage_placement(tiny, 1.5, num_cages=1, weights=CageWeights(), iterations=3)
