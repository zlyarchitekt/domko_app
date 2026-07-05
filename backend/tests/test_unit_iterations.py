"""Testy iteracyjnego podziału na mieszkania (spec 2026-07-04-apartment-
division-iterations §7, scoring 7-wagowy z §4)."""

from shapely.geometry import Polygon

from services.layout import ApartmentCell
from services.unit_mix import (
    ProgramShare,
    UnitWeights,
    _score_iteration,
    allocate_counts,
    derive_total_units,
    iterate_units,
)

SHARES = [
    ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
    ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
    ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
    ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
]


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_derive_total_units_scales_with_area():
    small = derive_total_units(200.0, SHARES)
    big = derive_total_units(2000.0, SHARES)
    assert small >= 1
    assert big > small
    # avg = 0.1*28.5 + 0.4*43 + 0.4*64 + 0.1*81 = 53.75 -> 2000/53.75 = 37
    assert big == 37


def test_allocate_counts_largest_remainder_sums_to_total():
    counts = allocate_counts(SHARES, 7)
    assert sum(counts.values()) == 7
    assert counts["M2"] >= 2 and counts["M3"] >= 2


def test_zero_leftover_guarantee():
    remainder = _rect(0, 0, 24, 10)  # 240 m2
    cells, metas, best_seed, derived_total = iterate_units(remainder, SHARES, iterations=5)
    assert cells
    assert derived_total >= 1
    total_cells_area = sum(c.polygon.area for c in cells)
    assert abs(total_cells_area - remainder.area) < 1e-6
    assert len(metas) == 5
    assert best_seed in {m.seed for m in metas}


def test_determinism_same_seed_same_result():
    remainder = _rect(0, 0, 24, 10)
    cells_a, metas_a, _, _ = iterate_units(remainder, SHARES, iterations=3)
    cells_b, metas_b, _, _ = iterate_units(remainder, SHARES, iterations=3)
    assert [m.score for m in metas_a] == [m.score for m in metas_b]
    assert [c.polygon.wkt for c in cells_a] == [c.polygon.wkt for c in cells_b]


def test_best_seed_has_lowest_score():
    remainder = _rect(0, 0, 30, 11)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=10)
    best = min(metas, key=lambda m: m.score)
    assert best.seed == best_seed


def test_single_weight_score_equals_component():
    remainder = _rect(0, 0, 24, 10)
    only_mix = UnitWeights(size=0, mix=1, grid=0, shape=0, daylight=0, squareness=0, adjacency=0)
    only_size = UnitWeights(size=1, mix=0, grid=0, shape=0, daylight=0, squareness=0, adjacency=0)
    _, metas_mix, _, _ = iterate_units(remainder, SHARES, iterations=3, weights=only_mix)
    _, metas_size, _, _ = iterate_units(remainder, SHARES, iterations=3, weights=only_size)
    assert all(abs(m.score - m.components["mix"]) < 1e-9 for m in metas_mix)
    assert all(abs(m.score - m.components["size"]) < 1e-9 for m in metas_size)


def test_geometric_components_on_crafted_cells():
    # kwadrat 6x6 na siatce: grid=0, shape=0 (prostokąt), squareness=0 (kwadrat)
    square = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 6, 6))
    # 6x15: proporcja 2.5:1 -> squareness = 1.0; poza siatką: wierzchołek 0.3
    long_off = ApartmentCell(id="b", type="M2", polygon=_rect(0.3, 0, 6.3, 15))
    shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=100)]
    w = UnitWeights(size=0, mix=0, grid=1, shape=0, daylight=0, squareness=0, adjacency=0)
    score_sq, comp_sq = _score_iteration([square], shares, w, None, None)
    score_lo, comp_lo = _score_iteration([long_off], shares, w, None, None)
    assert comp_sq["grid"] == 0.0
    assert comp_lo["grid"] > 0.0
    assert comp_sq["squareness"] == 0.0
    assert comp_lo["squareness"] >= 0.99


def test_min_facade_per_type_drives_daylight():
    # komórka 6x6 przy lewej krawędzi obrysu 20x6 dzieli z exterior obrysu
    # lewą (6m), dolną (6m) i górną (6m) krawędź = ~18m styku.
    # Próg 3m -> spełniony (dev 0); próg 25m -> niespełniony (dev 1).
    fp = _rect(0, 0, 20, 6)
    cell = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 6, 6))
    w = UnitWeights(size=0, mix=0, grid=0, shape=0, daylight=1, squareness=0, adjacency=0)
    ok_shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=40, min_facade_m=3.0)]
    hi_shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=40, min_facade_m=25.0)]
    _, comp_ok = _score_iteration([cell], ok_shares, w, fp, None)
    _, comp_hi = _score_iteration([cell], hi_shares, w, fp, None)
    assert comp_ok["daylight"] == 0.0
    assert comp_hi["daylight"] == 1.0


def test_merged_disjoint_raises_adjacency():
    circulation = _rect(10, 0, 12, 6)
    touching = ApartmentCell(id="a", type="M2", polygon=_rect(6, 0, 10, 6))
    disjoint = ApartmentCell(id="b", type="M2", polygon=_rect(6, 0, 10, 6))
    disjoint.merged_disjoint = True
    shares = [ProgramShare(type="M2", percentage=100, area_min_m2=20, area_max_m2=30)]
    w = UnitWeights(size=0, mix=0, grid=0, shape=0, daylight=0, squareness=0, adjacency=1)
    _, comp_ok = _score_iteration([touching], shares, w, None, circulation)
    _, comp_bad = _score_iteration([disjoint], shares, w, None, circulation)
    assert comp_ok["adjacency"] == 0.0
    assert abs(comp_bad["adjacency"] - 0.5) < 1e-9  # styka się, ale kara za enklawę
