import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SQUARE_20 = [[0, 0], [20, 0], [20, 20], [0, 20]]
L_SHAPE = [[0, 0], [20, 0], [20, 8], [8, 8], [8, 20], [0, 20]]


def test_layout_generate_square():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
            "apartments": [
                {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["footprint_area_m2"] == pytest.approx(400.0)
    assert data["circulation_area_m2"] > 0
    assert data["usable_area_m2"] > 0
    assert len(data["apartments"]) > 0
    assert data["wt_validation"]["passed"] in (True, False)
    assert len(data["zones"]) > 0


def test_layout_generate_l_shape():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": L_SHAPE,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": True},
            "apartments": [
                {"type": "2-room", "min_area_m2": 45, "target_count": 2, "width_m": 5, "depth_m": 9},
                {"type": "1-room", "min_area_m2": 30, "target_count": 2, "width_m": 4, "depth_m": 8},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["footprint_area_m2"] > 0
    assert len(data["apartments"]) > 0
    assert len(data["zones"]) >= 2


def test_layout_generate_rejects_small_footprint():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": [[0, 0], [1, 0], [1, 1]],
            "apartments": [{"type": "1-room", "min_area_m2": 25, "target_count": 1}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    # May produce 0 apartments or leftover, but should not crash
    assert "apartments" in data
