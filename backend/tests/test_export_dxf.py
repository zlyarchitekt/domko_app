"""Tests for /api/v1/export/dxf service and endpoint."""

from __future__ import annotations

import os
import tempfile

import ezdxf
from fastapi.testclient import TestClient

from main import app
from services.export_dxf import (
    APP_NAME,
    LAYER_ELEWACJE,
    LAYER_KOMUNIKACJA,
    LAYER_MIESZKANIA,
    LAYER_OBRYS,
    LAYER_TEKST,
    build_dxf_input_from_request,
    export_project_dxf,
)

client = TestClient(app)


def _make_payload(footprint: list[list[float]] | None = None):
    return {
        "project_id": "11111111-1111-1111-1111-111111111111",
        "project_name": "DXF Test",
        "parcel_id": "22222222-2222-2222-2222-222222222222",
        "location": {"lat": 52.23, "lon": 21.03, "address": "Warszawa", "city": "Warszawa"},
        "footprint": footprint or [[0, 0], [20, 0], [20, 20], [0, 20]],
        "circulation": {"corridor_width_m": 2.0, "stair_width_m": 1.2, "place_cage": False, "cage_size_m": 3.0},
        "apartments": [
            {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
        ],
        "analysis_date": "2026-03-21",
        "local_law": "warszawa",
    }


def _load_dxf(dxf_bytes: bytes):
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(dxf_bytes)
        tmp_name = tmp.name
    try:
        return ezdxf.readfile(tmp_name)
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def test_service_returns_bytes():
    inp = build_dxf_input_from_request(_make_payload())
    dxf_bytes = export_project_dxf(inp)
    assert isinstance(dxf_bytes, bytes)
    assert len(dxf_bytes) > 1000


def test_dxf_has_required_layers():
    inp = build_dxf_input_from_request(_make_payload())
    doc = _load_dxf(export_project_dxf(inp))

    layer_names = {layer.dxf.name for layer in doc.layers}
    for layer in [LAYER_OBRYS, LAYER_MIESZKANIA, LAYER_KOMUNIKACJA, LAYER_TEKST, LAYER_ELEWACJE]:
        assert layer in layer_names, f"Missing layer {layer}"

    msp = doc.modelspace()
    assert len(msp.query(f"LWPOLYLINE[layer=='{LAYER_OBRYS}']")) == 1
    assert len(msp.query(f"LWPOLYLINE[layer=='{LAYER_MIESZKANIA}']")) >= 1
    assert len(msp.query(f"LWPOLYLINE[layer=='{LAYER_KOMUNIKACJA}']")) == 1
    assert len(msp.query(f"TEXT[layer=='{LAYER_TEKST}']")) >= 1
    assert len(msp.query(f"LINE[layer=='{LAYER_ELEWACJE}']")) >= 1
    assert len(msp.query(f"TEXT[layer=='{LAYER_ELEWACJE}']")) >= 1


def test_dxf_apartments_have_xdata_sun_hours():
    doc = _load_dxf(export_project_dxf(build_dxf_input_from_request(_make_payload())))
    msp = doc.modelspace()
    apartments = list(msp.query(f"LWPOLYLINE[layer=='{LAYER_MIESZKANIA}']"))
    assert apartments
    for apt in apartments:
        tags = list(apt.get_xdata(APP_NAME))
        keys = [str(t.value) for t in tags[::2]]
        assert "worst_sun_hours" in keys
        assert "area_m2" in keys


def test_dxf_footprint_xdata():
    doc = _load_dxf(export_project_dxf(build_dxf_input_from_request(_make_payload())))
    msp = doc.modelspace()
    outline = msp.query(f"LWPOLYLINE[layer=='{LAYER_OBRYS}']")[0]
    tags = list(outline.get_xdata(APP_NAME))
    assert any(str(t.value) == "type" for t in tags)


def test_dxf_endpoint_status():
    response = client.post("/api/v1/export/dxf", json=_make_payload())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/dxf"
    assert response.headers["content-disposition"].startswith("attachment")
    assert len(response.content) > 1000


def test_dxf_endpoint_requires_footprint():
    payload = _make_payload()
    payload.pop("footprint")
    response = client.post("/api/v1/export/dxf", json=payload)
    assert response.status_code == 400


def test_dxf_endpoint_rejects_small_footprint():
    payload = _make_payload(footprint=[[0, 0], [1, 0], [1, 1]])
    response = client.post("/api/v1/export/dxf", json=payload)
    assert response.status_code == 200


def test_dxf_text_labels_include_sun_hours():
    doc = _load_dxf(export_project_dxf(build_dxf_input_from_request(_make_payload())))
    msp = doc.modelspace()
    texts = list(msp.query(f"TEXT[layer=='{LAYER_TEKST}']"))
    assert texts
    assert any("h" in t.dxf.text for t in texts)
