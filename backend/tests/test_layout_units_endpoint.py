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


def test_units_endpoint_exposes_real_net_area_m2():
    """Regression: /layout/units must pass through the real net_area_m2 that
    subdivide_units()/fit_program_to_rectangles() already compute on each
    ApartmentCell -- the endpoint handler previously omitted it from the
    ApartmentResult constructor, so it serialized as the model's 0.0 default
    (final whole-branch review finding, wall-thickness spec)."""
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
    assert len(body["apartments"]) >= 1
    for apt in body["apartments"]:
        assert apt["net_area_m2"] > 0
        assert apt["net_area_m2"] < apt["area_m2"]
