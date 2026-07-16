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


def test_place_circulation_threshold_override_changes_classification():
    from shapely.geometry import Polygon as _P
    from services.circulation import place_circulation

    footprint = _P([(0, 0), (30, 0), (30, 12), (0, 12)])
    tight = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=1,
        max_dist_single_m=1.0, max_dist_multi_m=1.0,
    )
    loose = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=1,
        max_dist_single_m=100.0, max_dist_multi_m=100.0,
    )
    tight_reds = sum(1 for d in tight.evacuation_dots if d.status == "red")
    loose_reds = sum(1 for d in loose.evacuation_dots if d.status == "red")
    assert tight_reds > loose_reds
    assert loose_reds == 0


def test_circulation_endpoint_serializes_evacuation_dots():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [30, 0], [30, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 1,
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert "evacuation_dots" in body
    assert len(body["evacuation_dots"]) > 0
    dot = body["evacuation_dots"][0]
    assert set(dot.keys()) >= {"x", "y", "status", "distance_m"}
    assert dot["status"] in {"green", "gray", "red"}


def test_gray_requires_direction_disjoint_routes_unit():
    """Plan 2026-07-15 Task 7: korytarz 0-60, klatki x=15 i x=45.
    x=5: obie w prawo -> green (10 m <= 20). x=30: c1 w lewo, c2 w prawo ->
    gray. x=5 przy progu single=8 -> red."""
    from shapely.geometry import box

    # segmenty rozcięte w pozycjach klatek (jak _split_segment_at_cage_positions
    # w pipeline), żeby graf miał węzeł-wejście przy każdej klatce
    segments = [((0.0, 6.0), (15.0, 6.0)), ((15.0, 6.0), (45.0, 6.0)), ((45.0, 6.0), (60.0, 6.0))]
    cages = [box(12.9, 3.15, 17.1, 8.85), box(42.9, 3.15, 47.1, 8.85)]

    dots = compute_evacuation_dots(segments, cages, green_max_m=20.0, gray_max_m=40.0)

    def at(x):
        return min(dots, key=lambda d: abs(d.x - x))

    assert at(5.0).status == "green"
    assert at(30.0).status == "gray"

    dots_tight = compute_evacuation_dots(segments, cages, green_max_m=8.0, gray_max_m=40.0)
    tight_at_5 = min(dots_tight, key=lambda d: abs(d.x - 5.0))
    assert tight_at_5.status == "red"


def test_dead_end_stub_is_one_directional_even_with_two_cages():
    """Kropka na lewo od LEWEJ klatki: obie klatki osiągalne tylko w prawo
    (tym samym korytarzem) -> dojście JEDNOSTRONNE, nigdy gray."""
    from shapely.geometry import box

    # korytarz 0-60; klatki blisko siebie po prawej (x=40, x=50), martwy
    # odcinek 0-40 na lewo od lewej klatki. Segmenty rozcięte w pozycjach klatek.
    segments = [((0.0, 6.0), (40.0, 6.0)), ((40.0, 6.0), (50.0, 6.0)), ((50.0, 6.0), (60.0, 6.0))]
    cages = [box(37.9, 3.15, 42.1, 8.85), box(47.9, 3.15, 52.1, 8.85)]

    dots = compute_evacuation_dots(segments, cages, green_max_m=20.0, gray_max_m=40.0)
    stub = [d for d in dots if d.x < 35.0]
    assert stub, "fixture ma mieć kropki na martwym odcinku"
    assert all(d.status != "gray" for d in stub), (
        "kropki za skrajną klatką nie mogą być dwustronne (drogi się pokrywają)"
    )
    between = [d for d in dots if 43.0 < d.x < 47.0]
    assert between and any(d.status == "gray" for d in between)
