from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_units_endpoint_fits_program_to_remainder():
    response = client.post(
        "/api/v1/layout/units",
        json={
            "remainder": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [30, 0], [30, 4], [0, 4], [0, 0]]],
            },
            "apartments": [{"type": "M2", "min_area_m2": 40, "target_count": 3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["apartments"]) == 3
    for apt in body["apartments"]:
        assert abs(apt["area_m2"] - 40.0) < 1.0


def test_units_endpoint_rejects_invalid_geometry():
    response = client.post(
        "/api/v1/layout/units",
        json={"remainder": {"type": "Polygon", "coordinates": []}, "apartments": []},
    )
    assert response.status_code == 400
