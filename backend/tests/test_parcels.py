from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_list_parcels():
    response = client.get("/api/v1/parcels/")
    assert response.status_code == 200
    assert response.json() == []
