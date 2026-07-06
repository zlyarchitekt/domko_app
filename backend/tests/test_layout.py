import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

SQUARE_20 = [[0, 0], [20, 0], [20, 20], [0, 20]]
L_SHAPE = [[0, 0], [20, 0], [20, 8], [8, 8], [8, 20], [0, 20]]


def test_layout_generate_square():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
            "apartments": [
                {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["footprint_area_m2"] == pytest.approx(400.0)
    assert data["circulation_area_m2"] > 0
    assert data["usable_area_m2"] > 0
    assert len(data["apartments"]) > 0
    assert data["wt_validation"]["passed"] in (True, False)
    assert len(data["zones"]) > 0


def test_layout_generate_l_shape():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": L_SHAPE,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": True},
            "apartments": [
                {"type": "2-room", "min_area_m2": 45, "target_count": 2, "width_m": 5, "depth_m": 9},
                {"type": "1-room", "min_area_m2": 30, "target_count": 2, "width_m": 4, "depth_m": 8},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["footprint_area_m2"] > 0
    assert len(data["apartments"]) > 0
    assert len(data["zones"]) >= 2


def test_layout_generate_rejects_small_footprint():
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": [[0, 0], [1, 0], [1, 1]],
            "apartments": [{"type": "1-room", "min_area_m2": 25, "target_count": 1}],
        },
    )
    assert response.status_code == 200
    data = response.json()
    # May produce 0 apartments or leftover, but should not crash
    assert "apartments" in data


from services.circulation import place_circulation as _pc


def _square(x0, y0, x1, y1):
    from shapely.geometry import Polygon
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_manual_cage_merged_into_result():
    footprint = _square(0, 0, 30, 12)
    manual_cage = [(1.0, 1.0), (5.0, 1.0), (5.0, 6.0), (1.0, 6.0)]
    result = _pc(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
        manual_cages=[manual_cage], manual_corridors=[],
    )
    assert len(result.cage_polygons) == 1
    assert abs(result.cage_polygons[0].area - 20.0) < 1e-6
    # remainder nie zawiera wnętrza klatki
    from shapely.geometry import Point
    assert not result.remainder.buffer(-1e-9).contains(Point(3.0, 3.5))


def test_manual_corridor_buffered_and_in_centerline():
    # NOTE: deviation from the plan's literal test. place_circulation() always
    # auto-places a corridor per zone regardless of `place_cage` (that flag
    # only gates the *cage*, see _build_corridor callsite) — for a single
    # 30x12 rectangle footprint this puts the auto-corridor at the exact same
    # y-center/width as the brief's manual path, making the manual band a
    # strict subset of the auto band (confirmed: area came back as 51.0, the
    # full auto-corridor, not 44.2). Use a taller footprint + a path placed
    # away from the auto-corridor's centerline so the two bands don't
    # overlap, and assert on the *delta* vs an auto-only run -- this isolates
    # the manual-corridor buffer math the test is actually meant to check.
    footprint = _square(0, 0, 30, 20)
    path = [(2.0, 2.0), (28.0, 2.0)]
    auto_only = _pc(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
        manual_cages=[], manual_corridors=[],
    )
    result = _pc(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
        manual_cages=[], manual_corridors=[path],
    )
    assert result.circulation_geometry is not None
    added_area = result.circulation_geometry.area - auto_only.circulation_geometry.area
    # pas: długość 26m x (1.5 + 2*0.10) szerokości, dodany PONAD auto-korytarz
    assert abs(added_area - 26.0 * 1.7) < 0.5
    manual_segs = [s for s in result.centerline if s.points == ((2.0, 2.0), (28.0, 2.0))]
    assert len(manual_segs) == 1


def test_manual_cage_outside_footprint_raises():
    import pytest as _pytest
    footprint = _square(0, 0, 10, 10)
    outside = [(8.0, 8.0), (14.0, 8.0), (14.0, 12.0), (8.0, 12.0)]
    with _pytest.raises(ValueError, match="wykracza poza obrys"):
        _pc(
            footprint, corridor_width_m=1.5, stair_width_m=1.2,
            place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
            manual_cages=[outside], manual_corridors=[],
        )


def test_generate_apartments_carry_net_geometry():
    """Verify that apartments in /layout/generate response include net_geometry field."""
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": SQUARE_20,
            "circulation": {"corridor_width_m": 2.0, "cage_size_m": 3.0, "place_cage": False},
            "apartments": [
                {"type": "1-room", "min_area_m2": 25, "target_count": 4, "width_m": 4, "depth_m": 7}
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["apartments"]) > 0
    for apt in data["apartments"]:
        assert "net_geometry" in apt
        assert apt["net_geometry"] is not None, "normalnie wymiarowane mieszkanie powinno mieć netto"
        # netto to GeoJSON Polygon
        assert apt["net_geometry"]["type"] == "Polygon"
        assert "coordinates" in apt["net_geometry"]
        # netto rzeczywiście skurczone względem surowej geometrii (nie tylko
        # obecność klucza/typu) -- porównanie pól przez shapely
        from shapely.geometry import shape as shapely_shape
        raw_poly = shapely_shape(apt["geometry"])
        net_poly = shapely_shape(apt["net_geometry"])
        assert net_poly.area < raw_poly.area


def test_net_geometry_json_none_for_tiny_cell():
    from api.v1.endpoints.layout import _net_geometry_json
    from services.wall_geometry import NET_SHRINK_M
    from shapely.geometry import box, shape as shapely_shape

    # 15x15cm -- za małe, żeby przetrwać skurczenie o 10cm z każdej strony
    assert _net_geometry_json(box(0, 0, 0.15, 0.15)) is None
    # normalny prostokąt -> dict GeoJSON, faktycznie skurczony o NET_SHRINK_M
    # z każdej strony (nie tylko poprawny typ GeoJSON)
    raw_box = box(0, 0, 5, 4)
    net = _net_geometry_json(raw_box)
    assert net is not None and net["type"] == "Polygon"
    net_shape = shapely_shape(net)
    expected_area = (5 - 2 * NET_SHRINK_M) * (4 - 2 * NET_SHRINK_M)
    assert net_shape.area == pytest.approx(expected_area, abs=1e-6)
    assert net_shape.area < raw_box.area - 0.1
