from fastapi.testclient import TestClient

from main import app
from services.export_pdf import export_project_pdf

client = TestClient(app)


def _make_payload(footprint: list[list[float]] | None = None):
    """Raw request shape the endpoint accepts — mirrors /export/json and /export/dxf,
    NOT the flat shape export_project_pdf() itself expects (see test below)."""
    return {
        "project_name": "PDF Test",
        "location": {"lat": 52.2297, "lon": 21.0122},
        "footprint": footprint or [[0, 0], [20, 0], [20, 20], [0, 20]],
        "circulation": {"corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True, "cage_size_m": 2.5},
        "apartments": [{"type": "M2", "min_area_m2": 30, "target_count": 4, "width_m": 5, "depth_m": 6}],
        "analysis_date": "2026-03-21",
    }


def test_export_project_pdf_renders_binary_pdf():
    """Unit test of the reportlab renderer itself, given an already-flat report dict."""
    request_data = {
        "project_name": "Testowy Projekt",
        "latitude": 52.2297,
        "longitude": 21.0122,
        "analysis_date": "2026-03-21",
        "required_hours": 3.0,
        "score": 95,
        "footprint_area_m2": 400.0,
        "usable_area_m2": 320.0,
        "circulation_area_m2": 80.0,
        "apartments": [
            {
                "apartment_id": "apt1",
                "type": "M2",
                "area_m2": 45.0,
                "min_width_m": 2.80,
                "passed": True,
            }
        ],
        "facades": [
            {
                "apartment_id": "apt1",
                "orientation": "S",
                "azimuth_deg": 180.0,
                "length_m": 6.0,
                "hours_total": 4.5,
                "meets_wt": True,
            }
        ],
    }

    pdf_bytes = export_project_pdf(request_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes[:4] == b"%PDF"


def test_export_pdf_endpoint_returns_binary_pdf():
    """Endpoint-level test: the raw project payload (mirroring /export/json) must be
    accepted and turned into a real PDF, not passed through unchanged (F6-05)."""
    response = client.post("/api/v1/export/pdf", json=_make_payload())
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 1000
    assert response.content[:4] == b"%PDF"


def test_export_pdf_endpoint_requires_footprint():
    payload = _make_payload()
    payload.pop("footprint")
    response = client.post("/api/v1/export/pdf", json=payload)
    assert response.status_code == 400
