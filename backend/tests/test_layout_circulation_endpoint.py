from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_circulation_endpoint_returns_geometry_and_remainder():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["circulation_geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert len(body["cage_geometries"]) == 1
    assert body["remainder"]["type"] in ("Polygon", "MultiPolygon")


def test_circulation_endpoint_rejects_short_footprint():
    response = client.post(
        "/api/v1/layout/circulation",
        json={"footprint": [[0, 0], [1, 1]], "circulation": {}},
    )
    assert response.status_code == 422  # pydantic min_length validation


def test_circulation_endpoint_includes_centerline():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["centerline"]) >= 1
    seg = body["centerline"][0]
    assert len(seg["points"]) == 2
    assert seg["loading"] in ("single", "double")
    assert seg["max_distance_m"] in (20.0, 40.0)
    assert isinstance(seg["exceeds_max"], bool)


def test_circulation_endpoint_no_cage_does_not_500():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": False,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["centerline"]) >= 1
    assert body["centerline"][0]["distance_start_m"] is None


def test_circulation_endpoint_respects_num_cages():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
                "num_cages": 2,
            },
        },
    )
    assert response.status_code == 200
    assert len(response.json()["cage_geometries"]) == 2


def test_circulation_endpoint_net_geometry_is_actually_smaller():
    """circulation_geometry_net must be a REAL shrink, not just present --
    Task 1 review of the apartment-colors plan caught a sibling bug where new
    tests only checked field type/presence, never that the polygon actually
    shrank (see .superpowers/sdd/progress.md, Task 1 fix f484e8e)."""
    from shapely.geometry import shape

    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["circulation_geometry"] is not None
    assert body["circulation_geometry_net"] is not None

    raw_area = shape(body["circulation_geometry"]).area
    net_area = shape(body["circulation_geometry_net"]).area
    assert net_area < raw_area


def test_gallery_mode_endpoint_produces_single_loaded_corridor():
    """Task 9: galeriowiec -> korytarz przy jednej z długich elewacji."""
    from shapely.geometry import shape

    body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5,
                        "corridor_mode": "gallery"},
    }
    r = client.post("/api/v1/layout/circulation", json=body)
    assert r.status_code == 200
    corridor = shape(r.json()["circulation_geometry"])
    minx, miny, maxx, maxy = corridor.bounds
    assert miny <= 1e-6 or maxy >= 12 - 1e-6, "galeriowiec: korytarz przy elewacji"


def test_double_mode_endpoint_corridor_centred():
    """Task 9: dwutrakt -> korytarz NIE dotyka długiej elewacji (środkuje)."""
    from shapely.geometry import shape

    body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5,
                        "corridor_mode": "double"},
    }
    r = client.post("/api/v1/layout/circulation", json=body)
    assert r.status_code == 200
    corridor = shape(r.json()["circulation_geometry"])
    # korytarz (bez klatki) odsunięty od obu długich elewacji y=0, y=12
    from shapely.ops import unary_union
    cages = unary_union([shape(c) for c in r.json()["cage_geometries"]])
    corridor_only = corridor.difference(cages)
    cminx, cminy, cmaxx, cmaxy = corridor_only.bounds
    assert cminy > 1e-6 and cmaxy < 12 - 1e-6, "dwutrakt: korytarz nie skleja się z elewacją"
