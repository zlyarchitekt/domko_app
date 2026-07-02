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
