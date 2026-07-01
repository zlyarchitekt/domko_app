"""Tests for /api/v1/validate/* endpoints (apartment, full-layout, communication)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SQUARE_20 = [[0, 0], [20, 0], [20, 20], [0, 20]]
L_SHAPE = [[0, 0], [20, 0], [20, 8], [8, 8], [8, 20], [0, 20]]

APARTMENTS = [{"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}]


def test_validate_apartment_flags_small_area_and_narrow_width():
    response = client.post(
        "/api/v1/validate/apartment", json={"area_m2": 20, "min_area_m2": 25, "min_width_m": 2.0}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["errors"]) == 2


def test_validate_apartment_passes_for_conforming_apartment():
    response = client.post(
        "/api/v1/validate/apartment", json={"area_m2": 30, "min_area_m2": 25, "min_width_m": 3.0}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["errors"] == []


def test_validate_full_layout_returns_wt_rules_and_communication():
    response = client.post(
        "/api/v1/validate/full-layout",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
            "apartments": APARTMENTS,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["score"], int)
    assert 0 <= data["score"] <= 100
    assert len(data["wt_rules"]) == 6
    assert {r["code"] for r in data["wt_rules"]} == {
        "§94 ust.1",
        "§94 ust.2",
        "§64",
        "§68 ust.1",
        "§58 ust.4",
        "heurystyka",
    }
    assert "communication_all_connected" in data
    assert isinstance(data["communication_issues"], list)


def test_validate_full_layout_respects_max_corridor_distance_override():
    response = client.post(
        "/api/v1/validate/full-layout",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": True},
            "apartments": APARTMENTS,
            "max_corridor_distance_m": 0.1,
        },
    )
    assert response.status_code == 200
    data = response.json()
    reach_rule = next(r for r in data["wt_rules"] if r["code"] == "§58 ust.4")
    assert reach_rule["passed"] is False


def test_validate_communication_endpoint_reports_missing_cage():
    response = client.post(
        "/api/v1/validate/communication",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "place_cage": False},
            "apartments": APARTMENTS,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["all_connected"] is False
    assert any("klatki" in issue["error"].lower() for issue in data["issues"])


def test_validate_communication_endpoint_no_apartments_is_connected():
    response = client.post(
        "/api/v1/validate/communication",
        json={"footprint": SQUARE_20, "apartments": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["all_connected"] is True
    assert data["issues"] == []


def test_validate_communication_endpoint_l_shape_smoke():
    response = client.post(
        "/api/v1/validate/communication",
        json={
            "footprint": L_SHAPE,
            "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5},
            "apartments": [
                {"type": "1-room", "min_area_m2": 25, "target_count": 2, "width_m": 5, "depth_m": 7}
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "all_connected" in data
    assert isinstance(data["issues"], list)
