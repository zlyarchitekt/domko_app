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
    # 8 rules (2026-07-15: +trakt-depth heurystyka): 5 unique codes below,
    # "heurystyka" now shared by 4 rules -- circulation_utilization,
    # cage_facade_contact, room_width, trakt_depth -- none real WT paragraphs
    # (spec 2026-07-04 wall-thickness §9). CODE set stays 5 unique values.
    assert len(data["wt_rules"]) == 8
    assert {r["code"] for r in data["wt_rules"]} == {
        "§94 ust.1",
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


def test_validate_full_layout_with_explicit_geometry():
    footprint = [[0, 0], [10, 0], [10, 10], [0, 10]]
    apt_geom = {
        "type": "Polygon",
        "coordinates": [[[0, 0], [5, 0], [5, 10], [0, 10], [0, 0]]]
    }
    circulation_geom = {
        "type": "Polygon",
        "coordinates": [[[5, 0], [10, 0], [10, 10], [5, 10], [5, 0]]]
    }

    response = client.post(
        "/api/v1/validate/full-layout",
        json={
            "footprint": footprint,
            "apartments": [{"type": "M2", "min_area_m2": 45, "target_count": 1}],
            "layout": {
                "footprint": footprint,
                "circulation_geometry": circulation_geom,
                "cage_geometries": [],
                "corridor_width_m": 5.0,
                "stair_width_m": 1.2,
                "apartments": [
                    {
                        "id": "apt1",
                        "type": "M2",
                        "geometry": apt_geom
                    }
                ]
            }
        }
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["score"], int)
    assert len(data["apartments"]) == 1
    assert data["apartments"][0]["apartment_id"] == "apt1"
    assert data["apartments"][0]["area_m2"] == 50.0


def test_validate_apartment_warns_on_narrow_facade_frontage():
    from shapely.geometry import Polygon

    from services.apartment_validation import validate_apartment
    from services.layout import ApartmentCell

    # 3m wide x 20m deep — facade frontage well under 3.6m
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (3, 0), (3, 20), (0, 20)]))
    result = validate_apartment(apt, min_area_m2=None)
    assert any("front" in w.lower() or "elewacj" in w.lower() for w in result.warnings)


def test_validate_apartment_warns_on_excessive_aspect_ratio():
    from shapely.geometry import Polygon

    from services.apartment_validation import validate_apartment
    from services.layout import ApartmentCell

    # 4m wide x 15m deep -> ratio 3.75:1, over the 2.5:1 threshold
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (4, 0), (4, 15), (0, 15)]))
    result = validate_apartment(apt, min_area_m2=None)
    assert any("stosun" in w.lower() or "aspect" in w.lower() for w in result.warnings)


def test_validate_apartment_no_warning_for_well_proportioned_unit():
    from shapely.geometry import Polygon

    from services.apartment_validation import validate_apartment
    from services.layout import ApartmentCell

    # 5m x 9m, area 45, aspect ratio 1.8:1, frontage 5m — all within bounds.
    # min_area_m2=None sidesteps the unrelated pre-existing "blisko minimum"
    # warning (fires whenever area is within 5% of min_area_m2 — would
    # trigger here at exactly 0% deviation and has nothing to do with the
    # facade-frontage/aspect-ratio checks this test targets).
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (5, 0), (5, 9), (0, 9)]))
    result = validate_apartment(apt, min_area_m2=None)
    assert result.warnings == []

