import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


SQUARE = [
    {"x": 0.0, "y": 0.0},
    {"x": 10.0, "y": 0.0},
    {"x": 10.0, "y": 10.0},
    {"x": 0.0, "y": 10.0},
]

SELF_INTERSECTING = [
    {"x": 0.0, "y": 0.0},
    {"x": 10.0, "y": 10.0},
    {"x": 10.0, "y": 0.0},
    {"x": 0.0, "y": 10.0},
]


def test_valid_square_closed():
    response = client.post("/api/v1/footprint/from-points", json={"points": SQUARE, "close": True})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["closed"] is True
    assert data["self_intersecting"] is False
    assert data["errors"] == []
    assert data["area_m2"] == pytest.approx(100.0)
    assert data["boundary"] == [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]


def test_valid_square_open():
    response = client.post("/api/v1/footprint/from-points", json={"points": SQUARE, "close": False})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    # We always close the ring internally for validation/area but report whether
    # the caller supplied a closed ring.
    assert data["closed"] is False
    assert data["area_m2"] == pytest.approx(100.0)


def test_too_few_points():
    response = client.post(
        "/api/v1/footprint/from-points", json={"points": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(e["field"] == "points" for e in data["errors"])


def test_self_intersection_detected():
    response = client.post(
        "/api/v1/footprint/from-points", json={"points": SELF_INTERSECTING, "close": True}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["self_intersecting"] is True
    assert any("self-intersects" in e["message"].lower() for e in data["errors"])


def test_empty_points():
    response = client.post("/api/v1/footprint/from-points", json={"points": []})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert data["closed"] is False


def test_nan_rejected():
    response = client.post(
        "/api/v1/footprint/from-points",
        json={"points": [{"x": 0, "y": 0}, {"x": None, "y": 1}, {"x": 1, "y": 1}]},
    )
    assert response.status_code == 422


def test_duplicate_point_rejected():
    duplicate = [
        {"x": 0.0, "y": 0.0},
        {"x": 10.0, "y": 0.0},
        {"x": 10.0, "y": 10.0},
        {"x": 0.0, "y": 0.0},  # duplicate
    ]
    response = client.post("/api/v1/footprint/from-points", json={"points": duplicate})
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any("duplicate" in e["message"].lower() for e in data["errors"])
