from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_units_endpoint_fits_program_to_remainder():
    response = client.post(
        "/api/v1/layout/units",
        json={
            "remainder": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [30, 0], [30, 4], [0, 4], [0, 0]]],
            },
            "apartments": [{"type": "M2", "min_area_m2": 40, "target_count": 3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["apartments"]) == 3
    for apt in body["apartments"]:
        assert abs(apt["area_m2"] - 40.0) < 1.0


def test_units_endpoint_rejects_invalid_geometry():
    response = client.post(
        "/api/v1/layout/units",
        json={"remainder": {"type": "Polygon", "coordinates": []}, "apartments": []},
    )
    assert response.status_code == 400


def test_units_endpoint_exposes_real_net_area_m2():
    """Regression: /layout/units must pass through the real net_area_m2 that
    subdivide_units()/fit_program_to_rectangles() already compute on each
    ApartmentCell -- the endpoint handler previously omitted it from the
    ApartmentResult constructor, so it serialized as the model's 0.0 default
    (final whole-branch review finding, wall-thickness spec)."""
    response = client.post(
        "/api/v1/layout/units",
        json={
            "remainder": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [30, 0], [30, 4], [0, 4], [0, 0]]],
            },
            "apartments": [{"type": "M2", "min_area_m2": 40, "target_count": 3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["apartments"]) >= 1
    for apt in body["apartments"]:
        assert apt["net_area_m2"] > 0
        assert apt["net_area_m2"] < apt["area_m2"]


def test_units_endpoint_exposes_wall_bands():
    """Regression: the two-step Etap-1/2 flow (POST /layout/circulation then
    POST /layout/units) is the only flow currently used to test cage/corridor
    placement, but /layout/units never computed wall_bands -- UnitsRequest had
    no footprint/circulation_geometry inputs to compute them from, and
    UnitsResponse had no field for them at all. The frontend then hardcoded
    wall_bands: [] when assembling its layoutResult from this flow's response,
    so wall thickness silently never rendered on canvas for this path, even
    though /layout/generate's wall_geometry engine has been correct all along.

    This test drives a real /layout/circulation call first (so
    circulation_geometry/remainder are realistic, not hand-built), then feeds
    footprint + circulation_geometry + apartments into /layout/units and
    checks wall_bands comes back non-empty with valid GeoJSON polygons."""
    footprint = [[0, 0], [30, 0], [30, 6], [0, 6]]
    circ_response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": footprint,
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert circ_response.status_code == 200
    circ_body = circ_response.json()

    response = client.post(
        "/api/v1/layout/units",
        json={
            "footprint": footprint,
            "circulation_geometry": circ_body["circulation_geometry"],
            "remainder": circ_body["remainder"],
            "apartments": [{"type": "M2", "min_area_m2": 40, "target_count": 3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["wall_bands"]) > 0

    from shapely.geometry import shape as shapely_shape

    footprint_poly = shapely_shape(
        {"type": "Polygon", "coordinates": [footprint + [footprint[0]]]}
    )
    total_wall_area = 0.0
    for band in body["wall_bands"]:
        assert band["type"] in ("Polygon", "MultiPolygon")
        total_wall_area += shapely_shape(band).area

    # Sane, non-degenerate range: wall material exists (not ~0) but obviously
    # can't exceed the footprint it's carved from.
    assert 0 < total_wall_area < footprint_poly.area
