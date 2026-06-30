import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from main import app
from services.bsp import bsp_zones, concave_vertices, corner_cage, is_concave
from services.polygon_input import points_to_polygon

client = TestClient(app)

SQUARE = [[0, 0], [10, 0], [10, 10], [0, 10]]
L_SHAPE = [[0, 0], [10, 0], [10, 5], [5, 5], [5, 10], [0, 10]]
U_SHAPE = [[0, 0], [10, 0], [10, 2], [2, 2], [2, 8], [10, 8], [10, 10], [0, 10]]


def test_square_is_convex():
    poly = Polygon(SQUARE)
    assert is_concave(poly) is False
    assert concave_vertices(poly) == []


def test_l_shape_is_concave():
    poly = Polygon(L_SHAPE)
    assert is_concave(poly) is True
    cv = concave_vertices(poly)
    assert len(cv) == 1
    assert cv[0] == (3, 5.0, 5.0)


def test_u_shape_three_concave():
    poly = Polygon(U_SHAPE)
    assert is_concave(poly) is True
    cv = concave_vertices(poly)
    assert len(cv) == 2


def test_bsp_zones_for_l_shape():
    poly = Polygon(L_SHAPE)
    zones = bsp_zones(poly)
    names = [z.name for z in zones]
    assert "Z-cage" in names
    total = sum(z.polygon.area for z in zones)
    assert total == pytest.approx(poly.area)


def test_corner_cage_l_shape():
    poly = Polygon(L_SHAPE)
    cage = corner_cage(poly, (5.0, 5.0))
    assert cage.area > 0
    assert poly.contains(cage)


def test_polygon_from_points_closes_ring():
    from models.footprint import Point2D
    pts = [Point2D(x=0.0, y=0.0), Point2D(x=10.0, y=0.0), Point2D(x=10.0, y=10.0)]
    poly = points_to_polygon(pts)
    assert poly.is_valid
    assert len(poly.exterior.coords) == 4


def test_bsp_concave_endpoint():
    response = client.post("/api/v1/bsp/concave", json={"points": L_SHAPE})
    assert response.status_code == 200
    data = response.json()
    assert data["concave"] is True


def test_bsp_zones_endpoint():
    response = client.post("/api/v1/bsp/zones", json={"points": L_SHAPE})
    assert response.status_code == 200
    data = response.json()
    assert len(data["zones"]) >= 2


def test_bsp_cage_endpoint():
    response = client.post("/api/v1/bsp/cage", json={"points": L_SHAPE})
    assert response.status_code == 200
    data = response.json()
    assert data["corner"] == [5.0, 5.0]
    assert data["cage"]["type"] == "Polygon"
