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
