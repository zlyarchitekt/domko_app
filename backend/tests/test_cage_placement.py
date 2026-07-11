"""Testy iteracyjnego auto-placementu klatek (spec 2026-07-04-cage-
placement-iterations §7)."""

import json

import pytest
from shapely.geometry import Polygon, box, mapping

from services.cage_placement import CageWeights, assign_cages_to_zones, iterate_cage_placement
from services.circulation import Zone


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def _shape_to_json(geom) -> str:
    return json.dumps(mapping(geom))


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


def test_two_cages_in_one_zone_is_possible():
    # 40x12 to za wąskie na dwie klatki 4.2x5.7 obok siebie bez kolizji w
    # niektórych układach — szerszy fixture daje zachłannemu shuffle więcej
    # szans na dwóch kandydatów w tej samej (jedynej) strefie.
    wide_fp = _rect(0, 0, 60, 12)
    result, metas, _ = iterate_cage_placement(
        wide_fp, 1.5, num_cages=2, weights=CageWeights(), iterations=20
    )
    assert 1 <= len(result.cage_polygons) <= 2
    assert all(1 <= m.cages_count <= 2 for m in metas)
    assert any(m.cages_count == 2 for m in metas), (
        "oczekiwano co najmniej jednej iteracji z 2 klatkami w jednej strefie "
        "teraz gdy _assemble_with_cages przyjmuje dict[int, list[Polygon]]"
    )


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
    # Powyższa asercja jest prawdziwa niezależnie od liczby klatek (score ==
    # egress przy tych wagach, więc to tautologia względem best_seed). Realny
    # test na "egress preferuje więcej klatek" wymaga best.cages_count > 1 --
    # teraz gdy multi-cage-per-zone jest strukturalnie możliwe (Part A/C),
    # zweryfikowano empirycznie (deterministyczne seeds), że 2 klatki bijają
    # 1 klatkę na tym footprint/corridor_width; poniższa asercja jest tego
    # dowodem, nie tautologią.
    assert best.cages_count > 1


def test_spread_prefers_separated_cages():
    w = CageWeights(egress=0.0, count=0.0, corners=0.0, ends=0.0, spread=1.0)
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=w, iterations=10
    )
    best = next(m for m in metas if m.seed == best_seed)
    assert best.components["spread"] == min(m.components["spread"] for m in metas)

    # spread=0.0 dla k=1 to bezwarunkowy dolny próg wzoru (cage_placement.py:
    # "if k <= 1: spread = 0.0", spec §2) -- żadna 2-klatkowa iteracja nie
    # może go pobić (spread >= 0 zawsze), więc globalny "best" ZAWSZE ląduje
    # na k=1, gdy tylko jakikolwiek seed w zakresie wylosuje k=1 (przy
    # num_cages=2 to ~50% szans na seed -- seed=1 losuje k=1 deterministycznie
    # niezależnie od geometrii, sprawdzone empirycznie). To NIE jest luka w
    # naprawie Part C, tylko właściwość wzoru spread nietknięta przez ten task
    # -- podnoszenie `iterations` NIE zmieni tego wyniku (seed=1 zawsze będzie
    # w zakresie i zawsze zwiąże remis na 0.0 najwcześniej ze wszystkich
    # 2-klatkowych wyników, które w praktyce nigdy nie trafiają dokładnie 0.0
    # przez dyskretną siatkę kandydatów co 5m).
    #
    # Zamiast wymuszać best.cages_count>=2 (strukturalnie niemożliwe), test
    # weryfikuje że gałąź k>1 jest w ogóle osiągalna I że formuła spread
    # poprawnie różnicuje jakość 2-klatkowych rozstawień (mniejszy rozrzut od
    # idealnych pozycji -> niższy spread) -- to faktycznie ćwiczy nietrywialną
    # gałąź `else` zamiast tylko k<=1.
    two_cage_metas = [m for m in metas if m.cages_count == 2]
    assert two_cage_metas, "oczekiwano co najmniej jednej iteracji z 2 klatkami w jednej strefie"
    assert any(m.components["spread"] > 0.0 for m in two_cage_metas), (
        "oczekiwano zróżnicowanych (niezerowych) wartości spread wśród wyników 2-klatkowych"
    )
    best_two_cage = min(two_cage_metas, key=lambda m: m.components["spread"])
    worst_two_cage = max(two_cage_metas, key=lambda m: m.components["spread"])
    # Real test: verify spread formula ranks placements correctly (best < worst),
    # not tautology. Different cage positions on discrete grid → different spread values.
    assert best_two_cage.components["spread"] < worst_two_cage.components["spread"], (
        f"spread formuła powinna różnicować 2-klatkowe rozstawienia: "
        f"best={best_two_cage.components['spread']:.4f}, "
        f"worst={worst_two_cage.components['spread']:.4f}"
    )


def test_footprint_too_small_raises():
    tiny = _rect(0, 0, 3, 3)  # mniejszy niż klatka 4.2x5.7
    with pytest.raises(ValueError, match="zbyt mały"):
        iterate_cage_placement(tiny, 1.5, num_cages=1, weights=CageWeights(), iterations=3)


def test_circulation_endpoint_iterative_mode():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 3,
            "cage_iterations": 10,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 1
    assert body["cage_best_seed"] in [m["seed"] for m in body["cage_iterations"]]
    assert body["cage_geometries"]
    assert any(m["circulation_geometry_net"] is not None for m in body["cage_iterations"])


def test_iterate_cage_placement_metas_carry_full_result():
    footprint = _rect(0, 0, 40, 12)
    _, metas, best_seed = iterate_cage_placement(
        footprint, 1.5, num_cages=2, weights=CageWeights(), iterations=5
    )
    for m in metas:
        assert m.result is not None
        assert isinstance(m.result.cage_polygons, list)
        # liczba klatek w wyniku zgadza się z policzoną wcześniej cages_count
        assert len(m.result.cage_polygons) == m.cages_count
    best = next(m for m in metas if m.seed == best_seed)
    assert len(best.result.centerline) >= 1


def test_generate_endpoint_iterative_mode():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 3,
            "cage_iterations": 10,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
        },
        "apartments": [
            {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
        ],
    }
    res = client.post("/api/v1/layout/generate", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 1
    assert body["cage_best_seed"] in [m["seed"] for m in body["cage_iterations"]]
    assert body["cage_geometries"]


def test_assign_cages_to_zones_matches_containing_bbox():
    # Prostokąt 40x12: rectangle_decompose zwraca 1 strefę = cały footprint.
    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=footprint)]
    cage_a = box(2, 2, 6.2, 7.7)
    cage_b = box(30, 2, 34.2, 7.7)
    result = assign_cages_to_zones([cage_a, cage_b], zones)
    assert result == {0: [cage_a, cage_b]}


def test_assign_cages_to_zones_multi_zone():
    left = _rect(0, 0, 8, 12)
    right = _rect(8, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=left), Zone(name="Z1", polygon=right)]
    cage_left = box(1, 2, 5.2, 7.7)
    cage_right = box(30, 2, 34.2, 7.7)
    result = assign_cages_to_zones([cage_left, cage_right], zones)
    assert result == {0: [cage_left], 1: [cage_right]}


def test_move_cage_endpoint_recomputes_zone_corridor():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    footprint = [[0, 0], [40, 0], [40, 12], [0, 12]]
    cage = box(2, 2, 6.2, 7.7)
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(cage))],
        "corridor_width_m": 1.5,
        "max_dist_single_m": 20.0,
        "max_dist_multi_m": 40.0,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_geometries"]) == 1
    assert body["circulation_geometry"] is not None
    assert len(body["centerline"]) >= 1


def test_move_cage_endpoint_rejects_cage_outside_footprint():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    footprint = [[0, 0], [40, 0], [40, 12], [0, 12]]
    cage = box(38, 10, 45, 16)  # wystaje poza obrys
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(cage))],
        "corridor_width_m": 1.5,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 422


def test_move_cage_endpoint_rejects_colliding_cages():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    footprint = [[0, 0], [40, 0], [40, 12], [0, 12]]
    cage_a = box(2, 2, 6.2, 7.7)
    cage_b = box(4, 3, 8.2, 8.7)  # overlaps cage_a
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(cage_a)), json.loads(_shape_to_json(cage_b))],
        "corridor_width_m": 1.5,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 422


def test_move_cage_endpoint_rejects_cage_straddling_zone_boundary():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    # L-shape: rectangle_decompose splits this into 2 zones at the y=8 seam.
    footprint = [[0, 0], [40, 0], [40, 8], [24, 8], [24, 12], [0, 12]]
    straddling_cage = box(5, 6, 9, 10)  # crosses the y=8 zone boundary
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(straddling_cage))],
        "corridor_width_m": 1.5,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 422


def test_circulation_endpoint_iterations_carry_geometry():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 2,
            "cage_iterations": 5,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 1
    for it in body["cage_iterations"]:
        assert "cage_geometries" in it
        assert isinstance(it["cage_geometries"], list)
        assert len(it["cage_geometries"]) == it["cages_count"]
        assert it["remainder"] is not None


def test_manual_cage_merged_into_every_iteration_not_just_winner():
    """Finding 1 (Etap 5 review, `/layout/circulation` endpoint fix): a
    manually-drawn cage must be merged into EVERY cage iteration's result,
    not just the winning one -- `_merge_manual_elements` mutates its
    `result` argument in place, and the winning iteration's `.result` is the
    SAME object as the loop-local `result` variable (aliased), so only that
    one got merged before this fix. Every other (non-winning) iteration's
    `.result` is a distinct `CirculationResult` from its own seed and
    silently kept missing the manual cage."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    manual_cage_ring = [[35.0, 9.5], [38.0, 9.5], [38.0, 11.5], [35.0, 11.5]]
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 2,
            "cage_iterations": 8,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
            "manual_cages": [manual_cage_ring],
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 2, "need at least one non-winning iteration to test"

    best_seed = body["cage_best_seed"]
    non_winning = [it for it in body["cage_iterations"] if it["seed"] != best_seed]
    assert non_winning, "expected at least one non-winning iteration"

    manual_cage_area = Polygon(manual_cage_ring).area
    for it in non_winning:
        # cages_count only ever counts AUTO-placed cages (computed inside
        # iterate_cage_placement before any manual merge happens) -- so
        # len(cage_geometries) == cages_count + 1 proves the manual cage
        # made it into THIS iteration's serialized geometry too.
        assert len(it["cage_geometries"]) == it["cages_count"] + 1, (
            f"seed={it['seed']}: manual cage missing from non-winning iteration's "
            f"cage_geometries (got {len(it['cage_geometries'])}, expected "
            f"{it['cages_count'] + 1})"
        )
        areas = [Polygon(g["coordinates"][0]).area for g in it["cage_geometries"]]
        assert any(abs(a - manual_cage_area) < 1e-6 for a in areas), (
            f"seed={it['seed']}: no cage_geometries entry matches the manual cage's area"
        )
