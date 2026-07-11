"""Testy iteracyjnego podziału na mieszkania (spec 2026-07-04-apartment-
division-iterations §7, scoring 7-wagowy z §4)."""

import pytest
from shapely.geometry import Polygon

from services.layout import ApartmentCell
from services.unit_mix import (
    ProgramShare,
    UnitWeights,
    _merge_leftover_into_cells,
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


def test_best_seed_has_lowest_score_among_hard_valid():
    """Od 2026-07-11 zwycięzca = najniższy score wśród iteracji spełniających
    zakazy (hard_valid); dopiero gdy żadna nie spełnia -- najniższy w ogóle.
    Na tym fixturze iteracja o absolutnie najniższym score łamie limit
    proporcji 1:3, więc asercja po samym min(score) byłaby błędna."""
    remainder = _rect(0, 0, 30, 11)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=10)
    valid = [m for m in metas if m.hard_valid]
    pool = valid or metas
    assert min(pool, key=lambda m: m.score).seed == best_seed


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


def test_merge_leftover_disjoint_into_nearest_cell():
    """Leftover bez wspólnej krawędzi z żadną komórką -> merguje do
    najbliższej komórki i ustawia merged_disjoint=True."""
    cells = [
        ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 5, 5)),
        ApartmentCell(id="b", type="M2", polygon=_rect(30, 0, 35, 5)),
    ]
    leftover = _rect(6, 0, 8, 2)  # blisko komórki 'a', daleko od 'b'

    cells_before_a = cells[0].polygon.area
    cells_before_b = cells[1].polygon.area

    _merge_leftover_into_cells(cells, leftover)

    # Komórka 'a' jest bliżej
    nearest_cell = cells[0]
    other_cell = cells[1]

    # Nearest powinno zawierać pełną powierzchnię (stara + leftover)
    assert abs(nearest_cell.polygon.area - (cells_before_a + leftover.area)) < 1e-6
    # Other powinno być bez zmian
    assert abs(other_cell.polygon.area - cells_before_b) < 1e-6
    # Merged disjoint powinno być True
    assert nearest_cell.merged_disjoint is True
    # Net area powinno być przebudowane
    assert nearest_cell.net_area_m2 > 0


def test_merge_leftover_shared_boundary_into_that_cell():
    """Leftover ze wspólną krawędzią z jedną komórką -> merguje do tej
    komórki (nie do najbliższej), merged_disjoint zostaje False."""
    cells = [
        ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 5, 5)),
        ApartmentCell(id="b", type="M2", polygon=_rect(10, 0, 15, 5)),
    ]
    # Leftover przyległ do prawa od komórki 'b'
    leftover = _rect(15, 1, 17, 4)

    cells_before_a = cells[0].polygon.area
    cells_before_b = cells[1].polygon.area

    _merge_leftover_into_cells(cells, leftover)

    cell_a = cells[0]
    cell_b = cells[1]

    # Komórka 'a' powinna być bez zmian (nie jest najbliższa tutaj)
    assert abs(cell_a.polygon.area - cells_before_a) < 1e-6
    # Komórka 'b' powinna zawierać leftover
    assert abs(cell_b.polygon.area - (cells_before_b + leftover.area)) < 1e-6
    # Merged disjoint powinno być False (była wspólna krawędź)
    assert cell_b.merged_disjoint is False


def test_derive_total_units_all_zero_shares_raises():
    """derive_total_units z wszystkimi udziałami procentowymi = 0
    powinien rzucić ValueError."""
    zero_shares = [
        ProgramShare(type="M1", percentage=0, area_min_m2=25, area_max_m2=32),
        ProgramShare(type="M2", percentage=0, area_min_m2=38, area_max_m2=48),
    ]
    with pytest.raises(ValueError, match="wszystkie udziały procentowe są zerowe"):
        derive_total_units(200.0, zero_shares)


def test_allocate_counts_all_zero_shares_raises():
    """allocate_counts z wszystkimi udziałami procentowymi = 0
    powinien rzucić ValueError."""
    zero_shares = [
        ProgramShare(type="M1", percentage=0, area_min_m2=25, area_max_m2=32),
        ProgramShare(type="M2", percentage=0, area_min_m2=38, area_max_m2=48),
    ]
    with pytest.raises(ValueError, match="wszystkie udziały procentowe są zerowe"):
        allocate_counts(zero_shares, total_units=10)


def test_units_endpoint_returns_iterations_and_no_leftover():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    remainder = Polygon([(0, 0), (24, 0), (24, 10), (0, 10)]).__geo_interface__
    payload = {
        "remainder": dict(remainder),
        "apartments": [
            {"type": "M2", "percentage": 50, "area_min_m2": 38, "area_max_m2": 48,
             "min_area_m2": 43, "target_count": 0},
            {"type": "M3", "percentage": 50, "area_min_m2": 58, "area_max_m2": 70,
             "min_area_m2": 64, "target_count": 0},
        ],
        "iterations": 5,
        "weights": {"size": 1.0, "mix": 1.0, "grid": 0, "shape": 0,
                    "daylight": 0, "squareness": 0, "adjacency": 0},
    }
    res = client.post("/api/v1/layout/units", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["leftover"] is None
    assert body["derived_total_units"] >= 1
    assert len(body["iterations"]) == 5
    assert body["best_seed"] in [m["seed"] for m in body["iterations"]]


def test_units_endpoint_classic_fallback_for_legacy_payload():
    """Regression: /layout/units must still serve pre-Etap-4 callers whose
    apartments carry no `percentage` at all (old min_area_m2/target_count
    contract) -- subdivide_units_endpoint's `if shares:` gate (built by
    filtering request.apartments to a.percentage > 0) must fall through to
    the classic subdivide_units() path instead of raising derive_total_units's
    422 "wszystkie udziały procentowe są zerowe" (percentage defaults to 0.0
    on ApartmentProgram, so an all-legacy payload produces an empty `shares`
    list, not a bad one). This locks in that the gate itself -- not just the
    new-engine path exercised by test_units_endpoint_returns_iterations_and_
    no_leftover above -- is protected by a test."""
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    remainder = Polygon([(0, 0), (30, 0), (30, 4), (0, 4)]).__geo_interface__
    payload = {
        "remainder": dict(remainder),
        "apartments": [
            # Old shape: no `percentage` key at all -- defaults to 0.0, so
            # this apartment is filtered out of `shares` and the gate is
            # False. target_count=2 * min_area_m2=40 = 80 m2 leaves 40 m2
            # of the 120 m2 remainder un-programmed, so leftover is real
            # (not None) -- this is the classic path's actual behavior,
            # distinct from the new engine's zero-leftover guarantee.
            {"type": "M2", "min_area_m2": 40, "target_count": 2},
        ],
    }
    res = client.post("/api/v1/layout/units", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    # Classic fallback ran (not the new iterative engine):
    assert body["derived_total_units"] == 0
    assert body["iterations"] == []
    assert body["best_seed"] == 0
    # subdivide_units() actually produced a real leftover here -- "leftover
    # is always None" is a guarantee of the new engine only (spec §3), not
    # a universal property of /layout/units.
    assert body["leftover"] is not None
    assert len(body["apartments"]) == 2


def test_iterate_units_metas_carry_full_cells():
    remainder = _rect(0, 0, 24, 10)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=5)
    for m in metas:
        assert m.cells is not None
        assert len(m.cells) == m.units_count
        total_area = sum(c.polygon.area for c in m.cells)
        assert abs(total_area - remainder.area) < 1e-6  # zero-leftover per iteracja


def test_units_endpoint_iterations_carry_geometry_and_walls():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    remainder = Polygon([(0, 0), (24, 0), (24, 10), (0, 10)]).__geo_interface__
    payload = {
        "remainder": dict(remainder),
        "footprint": [[0, 0], [24, 0], [24, 10], [0, 10]],
        "apartments": [
            {"type": "M2", "percentage": 50, "area_min_m2": 38, "area_max_m2": 48,
             "min_area_m2": 43, "target_count": 0},
            {"type": "M3", "percentage": 50, "area_min_m2": 58, "area_max_m2": 70,
             "min_area_m2": 64, "target_count": 0},
        ],
        "iterations": 5,
    }
    res = client.post("/api/v1/layout/units", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["iterations"]) == 5
    for it in body["iterations"]:
        assert len(it["apartments"]) == it["units_count"]
        assert len(it["wall_bands"]) > 0


def test_generate_endpoint_classic_fallback_for_legacy_payload():
    """Same gate/branch-selection regression as the /layout/units test above,
    but for /layout/generate's mirrored `if input.program_shares: ... else:
    ...` gate in services.layout.generate_layout -- no existing test asserted
    derived_total_units/iterations for this endpoint's classic branch
    (test_layout.py's and test_cage_placement.py's old-style-apartments
    /generate calls only check apartments/zones/cage_iterations, never these
    fields)."""
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [20, 0], [20, 20], [0, 20]],
        "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
        "apartments": [
            # Old shape again: no `percentage` -- program_shares ends up
            # empty, so generate_layout() takes its classic subdivide_units
            # branch (services/layout.py else-branch).
            {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7},
        ],
    }
    res = client.post("/api/v1/layout/generate", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["derived_total_units"] == 0
    assert body["iterations"] == []
    assert body["best_seed"] == 0
    assert len(body["apartments"]) > 0


# --- ZAKAZ: mieszkanie musi dotykać komunikacji ORAZ elewacji (2026-07-11) ---


def test_meets_hard_constraints_detects_interior_cell():
    from services.unit_mix import meets_hard_constraints

    footprint = _rect(0, 0, 10, 10)
    circulation = _rect(4, 0, 6, 10)
    touching = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 4, 10))  # dotyka obu
    interior = ApartmentCell(id="b", type="M2", polygon=_rect(1, 1, 3, 3))  # nie dotyka niczego

    assert meets_hard_constraints([touching], footprint, circulation) is True
    assert meets_hard_constraints([touching, interior], footprint, circulation) is False


def test_meets_hard_constraints_each_condition_independent():
    from services.unit_mix import meets_hard_constraints

    footprint = _rect(0, 0, 10, 10)
    circulation = _rect(4, 4, 6, 6)  # wyspa w środku
    facade_only = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 2, 2))  # elewacja tak, komunikacja nie
    circ_only = ApartmentCell(id="b", type="M2", polygon=_rect(4, 2, 6, 4))  # komunikacja tak, elewacja nie

    assert meets_hard_constraints([facade_only], footprint, circulation) is False
    assert meets_hard_constraints([circ_only], footprint, circulation) is False
    # bez podanej geometrii dany warunek jest pomijany (jak w _score_iteration)
    assert meets_hard_constraints([facade_only], footprint, None) is True
    assert meets_hard_constraints([circ_only], None, circulation) is True


def test_pick_best_iteration_prefers_hard_valid_over_lower_score():
    from services.unit_mix import IterationMeta, pick_best_iteration

    invalid_better = IterationMeta(seed=0, score=0.1, units_count=5, hard_valid=False)
    valid_worse = IterationMeta(seed=1, score=0.4, units_count=5, hard_valid=True)
    assert pick_best_iteration([invalid_better, valid_worse]).seed == 1

    # żadna ważna -> najniższy score w ogóle (fallback zamiast pustego wyniku)
    all_invalid = [
        IterationMeta(seed=0, score=0.3, units_count=5, hard_valid=False),
        IterationMeta(seed=1, score=0.2, units_count=5, hard_valid=False),
    ]
    assert pick_best_iteration(all_invalid).seed == 1


def test_iterate_units_metas_carry_hard_valid_and_winner_is_valid():
    remainder = _rect(0, 0, 30, 10)
    footprint = _rect(0, 0, 30, 12)
    circulation = _rect(0, 10, 30, 12)  # korytarz wzdłuż górnej krawędzi remainder
    cells, metas, best_seed, _total = iterate_units(
        remainder, SHARES, iterations=5, footprint=footprint, circulation_geometry=circulation
    )
    assert all(isinstance(m.hard_valid, bool) for m in metas)
    winner = next(m for m in metas if m.seed == best_seed)
    if any(m.hard_valid for m in metas):
        assert winner.hard_valid is True


def test_hard_constraint_violations_aspect_ratio():
    from services.unit_mix import HARD_MAX_ASPECT_RATIO, hard_constraint_violations

    footprint = _rect(0, 0, 30, 10)
    circulation = _rect(0, 0, 30, 2)
    ok = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 9, 3))  # 3:1 dokładnie na limicie
    too_long = ApartmentCell(id="b", type="M2", polygon=_rect(9, 0, 22, 3))  # 13x3 > 1:3

    assert hard_constraint_violations([ok], footprint, circulation) == []
    v = hard_constraint_violations([ok, too_long], footprint, circulation)
    assert len(v) == 1 and "proporcje" in v[0] and f"1:{HARD_MAX_ASPECT_RATIO:g}" in v[0]


def test_hard_constraint_violations_lshape_uses_bounding_rectangle():
    """Kształt L o rozpiętościach 12x3 (bbox) -> ratio 4 > 3, mimo że każde
    ramię z osobna jest przysadziste — user: 'patrz na maksymalne rozpiętości
    tak jakbyś wpisywał kształt w prostokąt'."""
    from services.unit_mix import hard_constraint_violations

    lshape = Polygon([(0, 0), (12, 0), (12, 1.5), (1.5, 1.5), (1.5, 3), (0, 3)])
    cell = ApartmentCell(id="a", type="M2", polygon=lshape)
    v = hard_constraint_violations([cell], None, None)
    assert len(v) == 1 and "proporcje" in v[0]


def test_iterate_units_metas_carry_violation_reasons():
    remainder = _rect(0, 0, 30, 10)
    footprint = _rect(0, 0, 30, 12)
    circulation = _rect(0, 10, 30, 12)
    _cells, metas, _seed, _total = iterate_units(
        remainder, SHARES, iterations=3, footprint=footprint, circulation_geometry=circulation
    )
    for m in metas:
        assert m.hard_valid == (m.hard_violations == [])
