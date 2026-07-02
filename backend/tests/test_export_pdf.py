from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_export_pdf_endpoint_returns_binary_pdf():
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

    response = client.post("/api/v1/export/pdf", json=request_data)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert len(response.content) > 1000  # Expect at least 1KB of PDF binary data
    assert response.content[:4] == b"%PDF"
