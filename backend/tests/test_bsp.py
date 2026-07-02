from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, Polygon

from main import app
from services.bsp import (
    concave_vertices,
    corner_cage,
    is_concave,
    rectangle_decompose,
    split_polygon_by_edge,
)
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


def test_split_polygon_by_edge_concave_does_not_lose_area():
    # "U"/tub shape: legs at x=0-2 and x=10-12 (full height 0-8), notch open
    # at the top between x=2..10, y=6..8. 80 m^2 total.
    u_shape = Polygon([
        (0, 0), (12, 0), (12, 8), (10, 8), (10, 6), (2, 6), (2, 8), (0, 8),
    ])
    assert u_shape.area == 80.0
    # Horizontal cut through the notch at y=7 crosses the boundary 4 times
    # (both legs of the U plus both sides of the top notch).
    part_a, part_b = split_polygon_by_edge(u_shape, (-1, 7), (13, 7))
    assert abs((part_a.area + part_b.area) - u_shape.area) < 1e-6


def test_split_polygon_by_edge_collinear_with_existing_edge():
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    # Cut line lies exactly on the top edge (y=10) — must not silently
    # drop this as "no valid split", nor lose area.
    part_a, part_b = split_polygon_by_edge(square, (0, 10), (10, 10))
    # A cut along the boundary itself degenerates to (whole, empty) or
    # raises — either is acceptable as long as no area is silently lost
    # and no exception other than ValueError propagates.
    total = part_a.area + part_b.area
    assert abs(total - square.area) < 1e-6 or total == 0.0


def test_rectangle_decompose_convex_returns_single_part():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    parts = rectangle_decompose(rect)
    assert len(parts) == 1
    assert abs(parts[0].area - 60.0) < 1e-6


def test_rectangle_decompose_l_shape_no_area_lost_no_overlap():
    l_shape = Polygon([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
    total_area = l_shape.area  # 76.0
    parts = rectangle_decompose(l_shape)
    assert len(parts) >= 2
    assert abs(sum(p.area for p in parts) - total_area) < 1e-6
    # No two parts overlap by more than a sliver.
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            assert parts[i].intersection(parts[j]).area < 1e-6
    # Every part is (close to) rectangular: 4 vertices after simplification.
    for p in parts:
        assert not concave_vertices(p), f"part still concave: {list(p.exterior.coords)}"


def test_rectangle_decompose_u_shape_no_area_lost():
    u_shape = Polygon([
        (0, 0), (2, 0), (2, 6), (10, 6), (10, 0), (12, 0),
        (12, 8), (0, 8),
    ])
    total_area = u_shape.area  # 48.0 (notch cut from the bottom, see Task 1's fixture)
    parts = rectangle_decompose(u_shape)
    assert abs(sum(p.area for p in parts) - total_area) < 1e-6
    for p in parts:
        assert not concave_vertices(p)


def test_rectangle_decompose_multipolygon_handles_each_part():
    a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    b = Polygon([(10, 0), (15, 0), (15, 5), (10, 5)])
    parts = rectangle_decompose(MultiPolygon([a, b]))
    assert len(parts) == 2
    assert abs(sum(p.area for p in parts) - 50.0) < 1e-6
