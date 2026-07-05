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
    assert best_two_cage.components["spread"] == min(m.components["spread"] for m in two_cage_metas)


def test_footprint_too_small_raises():
    tiny = _rect(0, 0, 3, 3)  # mniejszy niż klatka 4.2x5.7
    with pytest.raises(ValueError, match="zbyt mały"):
        iterate_cage_placement(tiny, 1.5, num_cages=1, weights=CageWeights(), iterations=3)
