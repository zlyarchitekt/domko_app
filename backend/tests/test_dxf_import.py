"""Tests for POST /api/v1/footprint/import-dxf (services/dxf_import.py)."""

from __future__ import annotations

from io import BytesIO

import ezdxf
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _dxf_bytes(build) -> bytes:
    """Build a DXF document via `build(msp)` and return it as bytes."""
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    build(msp)
    buffer = BytesIO()
    doc.write(buffer, fmt="bin")
    return buffer.getvalue()


def _upload(dxf_bytes: bytes, filename: str = "footprint.dxf"):
    return client.post(
        "/api/v1/footprint/import-dxf",
        files={"file": (filename, dxf_bytes, "application/dxf")},
    )


def test_import_rectangle_lwpolyline():
    def build(msp):
        msp.add_lwpolyline(
            [(0, 0), (20, 0), (20, 10), (0, 10)], close=True, dxfattribs={"layer": "OBRYS"}
        )

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["valid"] is True
    assert data["area_m2"] == pytest.approx(200.0)
    assert data["dimensions"] == {"width_m": 20.0, "height_m": 10.0}
    assert data["source_entity_type"] == "LWPOLYLINE"
    assert data["polygon"]["type"] == "Polygon"
    assert len(data["polygon"]["coordinates"][0]) == 5  # closed ring


def test_import_l_shape():
    def build(msp):
        msp.add_lwpolyline(
            [(0, 0), (20, 0), (20, 8), (8, 8), (8, 20), (0, 20)],
            close=True,
            dxfattribs={"layer": "OBRYS"},
        )

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["valid"] is True
    assert data["area_m2"] == pytest.approx(20 * 8 + 8 * 12)


def test_import_concave_polygon_old_style_polyline():
    def build(msp):
        # Old-style POLYLINE entity (as opposed to LWPOLYLINE).
        polyline = msp.add_polyline2d([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
        polyline.close(True)

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["valid"] is True
    assert data["source_entity_type"] == "POLYLINE"
    assert data["area_m2"] == pytest.approx(10 * 4 + 4 * 6)


def test_import_picks_largest_entity_across_multiple_layers():
    def build(msp):
        # Small dimension/detail polyline on one layer...
        msp.add_lwpolyline([(0, 0), (2, 0), (2, 2), (0, 2)], close=True, dxfattribs={"layer": "DETAIL"})
        # ...and the real building outline on another, much bigger.
        msp.add_lwpolyline(
            [(0, 0), (30, 0), (30, 15), (0, 15)], close=True, dxfattribs={"layer": "OBRYS"}
        )

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["valid"] is True
    assert data["area_m2"] == pytest.approx(30 * 15)
    assert data["source_layer"] == "OBRYS"
    assert data["candidate_count"] == 2


def test_import_hatch_boundary():
    def build(msp):
        hatch = msp.add_hatch(dxfattribs={"layer": "OBRYS"})
        hatch.paths.add_polyline_path(
            [(0, 0), (12, 0), (12, 6), (0, 6)], is_closed=True
        )

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["valid"] is True
    assert data["source_entity_type"] == "HATCH"
    assert data["area_m2"] == pytest.approx(12 * 6)


def test_import_rejects_file_with_no_closed_entities():
    def build(msp):
        msp.add_line((0, 0), (10, 0), dxfattribs={"layer": "OBRYS"})

    response = _upload(_dxf_bytes(build))
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert any(e["field"] == "file" for e in data["errors"])


def test_import_rejects_non_dxf_extension():
    response = _upload(b"not a dxf file", filename="footprint.txt")
    assert response.status_code == 400


def test_import_rejects_corrupt_dxf():
    response = _upload(b"this is not valid DXF content at all", filename="footprint.dxf")
    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
