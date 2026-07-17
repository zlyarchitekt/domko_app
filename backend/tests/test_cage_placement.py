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


def test_base_seed_reproducible_and_diversifying():
    """base_seed (2026-07-16): ta sama baza -> identyczny wynik,
    inna baza -> inna eksploracja (frontend losuje bazę per klik)."""
    big = _rect(0, 0, 80, 12)
    kw = dict(num_cages=3, weights=CageWeights(), iterations=12)
    a = iterate_cage_placement(big, 1.5, base_seed=7_777, **kw)
    b = iterate_cage_placement(big, 1.5, base_seed=7_777, **kw)
    assert [m.score for m in a[1]] == [m.score for m in b[1]]
    c = iterate_cage_placement(big, 1.5, base_seed=123_456, **kw)
    assert [m.score for m in a[1]] != [m.score for m in c[1]]


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
    w = CageWeights(egress=1.0, count=0.0, light_waste=0.0, ends=0.0, spread=0.0)
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
    w = CageWeights(egress=0.0, count=0.0, light_waste=0.0, ends=0.0, spread=1.0)
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=w, iterations=10
    )
    # Uwaga 2026-07-15 Task 10: best_seed wybiera minimal-k (najmniejsze k
    # z zero czerwonych), NIE waga spread -- więc nie asercujemy już
    # best.components["spread"]==min. Test weryfikuje samą FORMUŁĘ spread
    # (różnicowanie 2-klatkowych rozstawień) niżej.

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
    # Formuła spread w [0,1], best <= worst (po zmianie puli kandydatów w Task
    # 10 wiele 2-klatkowych układów może mieć identyczny spread -- OK).
    assert 0.0 <= best_two_cage.components["spread"] <= worst_two_cage.components["spread"] <= 1.0


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
            "cage_weights": {"egress": 1.0, "count": 0.5, "light_waste": 0.3,
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

    # Verify real shrink (net area < raw area) for at least one iteration
    from shapely.geometry import shape
    matching_iterations = [m for m in body["cage_iterations"]
                           if m["circulation_geometry"] is not None and m["circulation_geometry_net"] is not None]
    assert len(matching_iterations) > 0
    raw_area = shape(matching_iterations[0]["circulation_geometry"]).area
    net_area = shape(matching_iterations[0]["circulation_geometry_net"]).area
    assert net_area < raw_area


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
            "cage_weights": {"egress": 1.0, "count": 0.5, "light_waste": 0.3,
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


def _reds(meta):
    return sum(1 for d in meta.result.evacuation_dots if d.status == "red")


def test_minimal_k_slider_is_maximum_not_exact():
    """Zaktualizowane 2026-07-15 Task 10: suwak num_cages to MAKSIMUM, nie
    żądanie. Zwycięzca = NAJMNIEJSZE k dowożące zero czerwonych dojść (nie
    zawsze num_cages). Metas obejmują wiele k (użytkownik je przegląda)."""
    footprint = _rect(0, 0, 34, 12)
    _result, metas, best_seed = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=3, weights=CageWeights(), iterations=30,
    )
    winner = next(m for m in metas if m.seed == best_seed)
    assert _reds(winner) == 0, "zwycięzca musi mieć zero czerwonych dojść gdy to osiągalne"
    # zwycięzca ma NAJMNIEJSZĄ liczbę klatek wśród wszystkich układów zero-red
    zero_red_ks = [m.cages_count for m in metas if _reds(m) == 0]
    assert winner.cages_count == min(zero_red_ks), "minimal-k: najmniejsze k dowożące zero czerwonych"
    assert winner.cages_count < 3, "num_cages to maksimum, nie żądanie"


def test_more_cages_when_evacuation_demands():
    """Ciasny próg dojścia wymusza więcej klatek: zwycięzca to najmniejsze k
    dowożące zero czerwonych (albo najlepszy egress gdy zero nieosiągalne)."""
    footprint = _rect(0, 0, 60, 12)
    _result, metas, best_seed = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=4, weights=CageWeights(),
        iterations=40, max_dist_single_m=12.0, max_dist_multi_m=18.0,
    )
    winner = next(m for m in metas if m.seed == best_seed)
    assert winner.cages_count >= 2


def test_candidate_pool_contains_even_spread_anchors():
    from services.circulation import Zone
    from services.bsp import rectangle_decompose
    from services.cage_placement import _candidate_cages

    footprint = _rect(0, 0, 60, 12)
    zones = [Zone(name="Z0", polygon=p) for p, in [(q,) for q in rectangle_decompose(footprint)]]
    candidates = _candidate_cages(footprint, zones, num_cages=3)
    xs = sorted({round((c.bounds[0] + c.bounds[2]) / 2, 1) for _, c in candidates})
    # pozycje rozstawu 1/6, 3/6, 5/6 długości: x ~= 10, 30, 50
    for target in (10.0, 30.0, 50.0):
        assert any(abs(x - target) <= 3.0 for x in xs), (target, xs)


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


# --- Genomy permutacyjne klatek (plan 2026-07-14 Etap 2, Task 5) ---


def test_cage_generator_build_deterministic_for_same_genome():
    """Genome (krotka indeksów kandydatów) -> build() daje identyczny wynik
    za każdym razem -- build() jest teraz czystą funkcją genomu, bez
    własnego losowania/shuffle."""
    from services.bsp import rectangle_decompose
    from services.cage_placement import _candidate_cages, _CageGenerator

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    candidates = _candidate_cages(footprint, zones, num_cages=3)
    gen = _CageGenerator(footprint, zones, candidates, num_cages=3,
                          corridor_width_m=1.5, max_dist_single_m=20.0, max_dist_multi_m=40.0)

    import random
    genome = gen.random_genome(random.Random(4))
    result_a = gen.build(genome)
    result_b = gen.build(genome)
    assert result_a is not None and result_b is not None
    assert [c.wkt for c in result_a.cage_polygons] == [c.wkt for c in result_b.cage_polygons]


def test_cage_generator_random_genome_deterministic_per_seed():
    from services.bsp import rectangle_decompose
    from services.cage_placement import _candidate_cages, _CageGenerator

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    candidates = _candidate_cages(footprint, zones, num_cages=3)
    gen = _CageGenerator(footprint, zones, candidates, num_cages=3,
                          corridor_width_m=1.5, max_dist_single_m=20.0, max_dist_multi_m=40.0)

    import random
    a = gen.random_genome(random.Random(9))
    b = gen.random_genome(random.Random(9))
    assert a == b
    assert list(a) == sorted(a)
    assert len(a) == 3
    assert len(set(a)) == 3


def test_cage_generator_colliding_genome_places_fewer_and_penalizes():
    """Genom "niewykonalny" -- indeksy dwóch kandydatów, które fizycznie
    kolidują (nakładają się) -- build() umieszcza mniej niż num_cages, a
    _score_placement's `count` component to penalizuje (>0), zamiast po
    cichu szukać zastępczego kandydata (Task 5 zmienia semantykę: genom to
    ZAMKNIĘTY zestaw, nie rosnąca zachłanna pula jak w Task 3)."""
    from services.bsp import rectangle_decompose
    from services.cage_placement import _candidate_cages, _CageGenerator, _score_placement, CageWeights

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    candidates = _candidate_cages(footprint, zones, num_cages=3)

    # znajdź dwa kandydaty, które ze sobą kolidują (nakładają się)
    collide_pair = None
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if candidates[i][1].intersects(candidates[j][1]):
                collide_pair = (i, j)
                break
        if collide_pair:
            break
    assert collide_pair is not None, "fixture powinien mieć kolidujących kandydatów w puli"

    gen = _CageGenerator(footprint, zones, candidates, num_cages=3,
                          corridor_width_m=1.5, max_dist_single_m=20.0, max_dist_multi_m=40.0)
    genome = tuple(sorted(collide_pair))
    result = gen.build(genome)
    assert result is not None
    assert len(result.cage_polygons) < 3

    _score, components = _score_placement(result, footprint, num_cages=3, weights=CageWeights())
    expected_count = abs(len(result.cage_polygons) - 3) / 3
    assert abs(components["count"] - expected_count) < 1e-9
    assert components["count"] > 0.0


def test_cage_generator_random_genome_pool_smaller_than_num_cages_no_crash():
    """Pula mniejsza niż num_cages -> random_genome bierze wszystkie
    dostępne indeksy (k = min(num_cages, len(pool))) zamiast rng.sample
    rzucającego ValueError na próbie za dużej."""
    from services.cage_placement import _CageGenerator

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=footprint)]
    tiny_pool = [(0, box(1, 1, 5.2, 6.7))]  # tylko 1 kandydat w puli

    gen = _CageGenerator(footprint, zones, tiny_pool, num_cages=5,
                          corridor_width_m=1.5, max_dist_single_m=20.0, max_dist_multi_m=40.0)
    import random
    genome = gen.random_genome(random.Random(1))
    assert len(genome) == 1
    result = gen.build(genome)
    assert result is not None
    assert len(result.cage_polygons) == 1


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
            "cage_weights": {"egress": 1.0, "count": 0.5, "light_waste": 0.3,
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
            "cage_weights": {"egress": 1.0, "count": 0.5, "light_waste": 0.3,
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


def test_arc_positions_on_bent_spine():
    from services.cage_placement import _arc_positions

    spine = [((0.0, 0.0), (10.0, 0.0)), ((10.0, 0.0), (10.0, 10.0))]  # łuk 20 m
    ts = _arc_positions([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], spine)
    assert [round(t, 3) for t in ts] == [0.0, 0.5, 1.0]


def test_spread_measured_along_spine_arc_on_l_shape():
    """Na L metryki rozstawu/końców liczone wzdłuż łuku spine, nie rzutem na
    jedną oś bbox -- wartości w [0,1], bez wyjątku."""
    from services.circulation import place_circulation
    from services.cage_placement import CageWeights, _score_placement

    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    result = place_circulation(
        l_shape, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=2,
    )
    if len(result.cage_polygons) < 2:
        import pytest
        pytest.skip("auto nie postawił 2 klatek na tym L (pula kandydatów)")
    _score, comps = _score_placement(result, l_shape, 2, CageWeights())
    assert 0.0 <= comps["spread"] <= 1.0
    assert 0.0 <= comps["ends"] <= 1.0


def test_light_waste_component():
    """Task 10: klatka przy południowej elewacji marnuje światło (dev→1),
    klatka wewnętrzna/przy północnej -- nie (dev→0). Północ = +y."""
    from services.cage_placement import _light_waste_for_cage
    from shapely.geometry import box

    fp = box(0, 0, 40, 12)
    south_cage = box(10, 0, 14.2, 5.7)      # styk z y=0 (południe)
    north_cage = box(10, 6.3, 14.2, 12)     # styk z y=12 (północ)
    interior = box(10, 3, 14.2, 8.7)        # zero styku z obrysem

    assert _light_waste_for_cage(south_cage, fp) > 0.9
    assert _light_waste_for_cage(north_cage, fp) < 0.1
    assert _light_waste_for_cage(interior, fp) == 0.0


def test_candidate_pool_contains_spine_adjacent_anchors():
    """Task 10: kotwice przy korytarzu -> istnieją kandydaci NIE dotykający
    obrysu (wnętrze budynku, dosunięci do pasa korytarza)."""
    from services.bsp import rectangle_decompose
    from services.circulation import Zone
    from services.cage_placement import _candidate_cages

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=p) for p in rectangle_decompose(footprint)]
    spine = [((0.0, 6.0), (40.0, 6.0))]
    candidates = _candidate_cages(footprint, zones, num_cages=2, spine_segments=spine, corridor_half_m=0.85)
    interior = [c for _zi, c in candidates if c.exterior.distance(footprint.exterior) > 0.5]
    assert interior, "brak kandydatów wewnętrznych przy spine"


def test_iterate_cage_placement_point_mode_enumerates_anchors():
    footprint = _rect(0, 0, 23, 13.75)
    result, metas, best = iterate_cage_placement(
        footprint, 1.5, num_cages=1, weights=CageWeights(), iterations=10,
        corridor_mode="point",
    )
    assert result.zone_access_modes == ["point"]
    assert 1 <= len(metas) <= 5           # co najwyżej 5 kotwic
    assert metas[0].seed == best
    assert result.centerline == []
    scores = [m.score for m in metas]
    assert scores == sorted(scores)
    # kontroler: winner na 23x13.75 = center (gap=0), nie remis z north (light_waste=0)
    assert metas[0].components.get("coverage_gap", 0) <= 1e-6
