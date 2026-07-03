from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _base_request(centerline_points, corridor_width_m=1.5):
    return {
        "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
        "centerline": [{"points": [list(p1), list(p2)]} for p1, p2 in centerline_points],
        "corridor_width_m": corridor_width_m,
        "cage_geometries": [
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 6], [0, 6], [0, 0]]],
            }
        ],
    }


def test_reshape_endpoint_returns_geometry_and_centerline():
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 3), (30, 3))]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["circulation_geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert body["remainder"]["type"] in ("Polygon", "MultiPolygon")
    assert len(body["centerline"]) == 1
    assert body["centerline"][0]["loading"] in ("single", "double")


def test_reshape_endpoint_flags_exceeds_max_for_long_edited_line():
    # Edited line stretches the single-loaded segment past the 20m threshold.
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 0.75), (30, 0.75))], corridor_width_m=1.5),
    )
    assert response.status_code == 200
    body = response.json()
    assert any(seg["exceeds_max"] for seg in body["centerline"])


def test_reshape_endpoint_rejects_empty_centerline():
    request_body = _base_request([((2, 3), (30, 3))])
    request_body["centerline"] = []
    response = client.post("/api/v1/layout/circulation/reshape", json=request_body)
    assert response.status_code == 422
