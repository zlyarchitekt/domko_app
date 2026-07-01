"""Tests for POST /api/v1/layout/split (F2-06)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SQUARE_20 = [[0, 0], [20, 0], [20, 20], [0, 20]]


def test_split_square_in_half():
    response = client.post(
        "/api/v1/layout/split",
        json={"footprint": SQUARE_20, "split_line": [[10, -1], [10, 21]]},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["polygons"]) == 2
    assert sum(data["areas"]) == pytest.approx(400.0, rel=0.01)
    assert data["areas"][0] == pytest.approx(200.0, rel=0.01)
    assert data["areas"][1] == pytest.approx(200.0, rel=0.01)


def test_split_off_center():
    response = client.post(
        "/api/v1/layout/split",
        json={"footprint": SQUARE_20, "split_line": [[5, -1], [5, 21]]},
    )
    assert response.status_code == 200
    data = response.json()
    assert sorted(round(a, 1) for a in data["areas"]) == [100.0, 300.0]


def test_split_line_not_crossing_polygon_rejected():
    response = client.post(
        "/api/v1/layout/split",
        json={"footprint": SQUARE_20, "split_line": [[30, 30], [40, 40]]},
    )
    assert response.status_code == 400


def test_split_rejects_invalid_footprint():
    response = client.post(
        "/api/v1/layout/split",
        json={"footprint": [[0, 0], [1, 1]], "split_line": [[0, 0], [1, 1]]},
    )
    assert response.status_code == 422  # Pydantic min_length=3 on footprint
