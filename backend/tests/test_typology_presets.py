"""Tests for services/typology_presets.py (F2-13 presets, F2-14 auto-detect heuristic)."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from services.typology_presets import (
    ALL_TYPOLOGIES,
    GALERIOWIEC,
    KLATKOWIEC_NAROZNY,
    KLATKOWIEC_WZDLUZNY,
    PUNKTOWIEC,
    SZEREGOWIEC,
    TYPOLOGY_PRESETS,
    get_preset,
    suggest_typology,
    to_layout_defaults,
)


def test_all_five_presets_exist():
    assert set(TYPOLOGY_PRESETS.keys()) == set(ALL_TYPOLOGIES)
    assert len(ALL_TYPOLOGIES) == 5


def test_get_preset_returns_expected_values():
    preset = get_preset(KLATKOWIEC_WZDLUZNY)
    assert preset.staircase_position == "elewacja"
    assert preset.corridor_width_m == 1.5
    assert preset.double_loaded is True


def test_get_preset_rejects_unknown_key():
    with pytest.raises(ValueError, match="nonexistent"):
        get_preset("nonexistent")


def test_to_layout_defaults_maps_corridor_and_cage():
    preset = get_preset(PUNKTOWIEC)
    defaults = to_layout_defaults(preset)
    assert defaults["corridor_width_m"] == 1.5
    assert defaults["cage_size_m"] == 3.5
    assert defaults["place_cage"] is True


def test_to_layout_defaults_szeregowiec_has_no_shared_cage():
    preset = get_preset(SZEREGOWIEC)
    defaults = to_layout_defaults(preset)
    assert defaults["place_cage"] is False


def test_suggest_typology_wide_rectangle_is_punktowiec():
    square = Polygon([(0, 0), (16, 0), (16, 14), (0, 14)])  # ratio ~1.14
    suggestion = suggest_typology(square)
    assert suggestion.typology == PUNKTOWIEC
    assert suggestion.concave_vertex_count == 0


def test_suggest_typology_narrow_rectangle_is_klatkowiec_wzdluzny():
    rect = Polygon([(0, 0), (40, 0), (40, 16), (0, 16)])  # ratio 2.5
    suggestion = suggest_typology(rect)
    assert suggestion.typology == KLATKOWIEC_WZDLUZNY


def test_suggest_typology_very_narrow_rectangle_is_szeregowiec_with_galeriowiec_alternative():
    rect = Polygon([(0, 0), (60, 0), (60, 10), (0, 10)])  # ratio 6.0
    suggestion = suggest_typology(rect)
    assert suggestion.typology == SZEREGOWIEC
    assert suggestion.alternative == GALERIOWIEC


def test_suggest_typology_l_shape_is_klatkowiec_narozny_single_cage():
    l_shape = Polygon([(0, 0), (20, 0), (20, 8), (8, 8), (8, 20), (0, 20)])
    suggestion = suggest_typology(l_shape)
    assert suggestion.typology == KLATKOWIEC_NAROZNY
    assert suggestion.concave_vertex_count == 1
    assert suggestion.suggested_cage_count == 1


def test_suggest_typology_u_shape_is_klatkowiec_narozny_double_cage():
    u_shape = Polygon(
        [
            (0, 0), (30, 0), (30, 20), (20, 20), (20, 10), (10, 10), (10, 20), (0, 20),
        ]
    )
    suggestion = suggest_typology(u_shape)
    assert suggestion.concave_vertex_count >= 2
    assert suggestion.typology == KLATKOWIEC_NAROZNY
    assert suggestion.suggested_cage_count == 2


def test_typology_presets_endpoint_lists_all_presets():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.get("/api/v1/typology/presets")
    assert response.status_code == 200
    data = response.json()
    assert len(data["presets"]) == 5


def test_typology_suggest_endpoint_returns_rationale():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/typology/suggest",
        json={"points": [[0, 0], [40, 0], [40, 16], [0, 16]]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["typology"] == KLATKOWIEC_WZDLUZNY
    assert "rationale" in data and data["rationale"]
