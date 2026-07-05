"""Testy grafu ewakuacyjnego (spec 2026-07-04-evacuation-dots §6)."""

from shapely.geometry import Polygon

from services.evacuation import EvacuationDot, compute_evacuation_dots


def _cage(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_single_cage_straight_corridor_green_then_red():
    # klatka przy (0,0); oś od (0,0) do (30,0) -> do 20m zielone, dalej czerwone
    segments = [((0.0, 0.0), (30.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert len(dots) >= 30
    greens = [d for d in dots if d.status == "green"]
    reds = [d for d in dots if d.status == "red"]
    assert greens and reds
    assert all(d.distance_m is not None and d.distance_m < 20.0 for d in greens)
    assert all(d.distance_m is None or d.distance_m >= 20.0 for d in reds)
    assert not [d for d in dots if d.status == "gray"]


def test_two_cages_make_gray():
    # klatki na obu końcach osi 30m -> każdy punkt osiąga 2 klatki, bliższa
    # zawsze <=15m<40m -> wszystko szare (także <20m od klatki: spec §2)
    segments = [((0.0, 0.0), (30.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0), _cage(30.0, -1.0, 32.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert dots
    assert all(d.status == "gray" for d in dots)


def test_two_cages_far_apart_red_in_middle():
    # oś 100m, klatki na końcach: środek ma bliższą ~50m > 40m -> czerwony
    segments = [((0.0, 0.0), (100.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0), _cage(100.0, -1.0, 102.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    mids = [d for d in dots if 45.0 <= d.x <= 55.0]
    assert mids and all(d.status == "red" for d in mids)


def test_branch_distances_via_graph():
    # T: pień (0,0)-(20,0), odgałęzienie w (10,0) do (10,15); klatka przy (0,0).
    # Punkt (10,10) ma odległość 10 (gałąź) + 10 (pień) = 20 -> czerwony (>=20),
    # punkt (10,5) -> 15m -> zielony.
    segments = [((0.0, 0.0), (20.0, 0.0)), ((10.0, 0.0), (10.0, 15.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    near = min(dots, key=lambda d: abs(d.x - 10.0) + abs(d.y - 5.0))
    far = min(dots, key=lambda d: abs(d.x - 10.0) + abs(d.y - 10.0))
    assert near.status == "green"
    assert far.status == "red"


def test_island_without_cage_is_red_with_null_distance():
    segments = [((50.0, 50.0), (60.0, 50.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert dots
    assert all(d.status == "red" and d.distance_m is None for d in dots)


def test_no_cages_all_red():
    segments = [((0.0, 0.0), (10.0, 0.0))]
    dots = compute_evacuation_dots(segments, [])
    assert dots and all(d.status == "red" and d.distance_m is None for d in dots)


def test_place_circulation_returns_dots():
    from shapely.geometry import Polygon as _P
    from services.circulation import place_circulation

    footprint = _P([(0, 0), (30, 0), (30, 12), (0, 12)])
    result = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=1,
    )
    assert result.centerline  # sanity
    assert result.evacuation_dots
    assert {d.status for d in result.evacuation_dots} <= {"green", "gray", "red"}
