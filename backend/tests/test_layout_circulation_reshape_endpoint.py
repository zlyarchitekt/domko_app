from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _base_request(centerline_points, corridor_width_m=1.5):
    return {
        "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
        "centerline": [{"points": [list(p1), list(p2)]} for p1, p2 in centerline_points],
        "corridor_width_m": corridor_width_m,
        "cage_geometries": [
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 6], [0, 6], [0, 0]]],
            }
        ],
    }


def test_reshape_endpoint_returns_geometry_and_centerline():
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 3), (30, 3))]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["circulation_geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert body["remainder"]["type"] in ("Polygon", "MultiPolygon")
    assert len(body["centerline"]) == 1
    assert body["centerline"][0]["loading"] in ("single", "double")


def test_reshape_endpoint_flags_exceeds_max_for_long_edited_line():
    # Edited line stretches the single-loaded segment past the 20m threshold.
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 0.75), (30, 0.75))], corridor_width_m=1.5),
    )
    assert response.status_code == 200
    body = response.json()
    assert any(seg["exceeds_max"] for seg in body["centerline"])


def test_reshape_endpoint_rejects_empty_centerline():
    request_body = _base_request([((2, 3), (30, 3))])
    request_body["centerline"] = []
    response = client.post("/api/v1/layout/circulation/reshape", json=request_body)
    assert response.status_code == 422


def test_reshape_endpoint_no_cage_does_not_500():
    request_body = _base_request([((2, 3), (30, 3))])
    request_body["cage_geometries"] = []
    response = client.post("/api/v1/layout/circulation/reshape", json=request_body)
    assert response.status_code == 200
    body = response.json()
    assert len(body["centerline"]) == 1
    assert body["centerline"][0]["distance_start_m"] is None
    assert body["centerline"][0]["distance_end_m"] is None


def test_reshape_endpoint_l_shaped_corridor_reports_whole_path_arc_distance():
    # Two contiguous segments forming a straight-but-multi-leg corridor. Cage
    # sits near (0, 0), behind the corridor's own start at x=2. Old per-segment
    # code called _distances_along_centerline() separately for each segment,
    # so LineString.project() clamped the cage projection onto THAT segment's
    # own two endpoints (arc position 0, since the cage lies behind both
    # segments' own start) -- the far endpoint of the second segment would
    # report only that segment's own length (~18m: 38-20), instead of the true
    # whole-path arc distance measured from the actual nearest point on the
    # FULL path (~36m: (20-2) + (38-20)).
    request_body = {
        "footprint": [[0, 0], [40, 0], [40, 6], [0, 6]],
        "centerline": [
            {"points": [[2, 0.75], [20, 0.75]]},
            {"points": [[20, 0.75], [38, 0.75]]},
        ],
        "corridor_width_m": 1.5,
        "cage_geometries": [
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 1.5], [0, 1.5], [0, 0]]],
            }
        ],
    }
    response = client.post("/api/v1/layout/circulation/reshape", json=request_body)
    assert response.status_code == 200
    body = response.json()
    centerline = body["centerline"]
    assert len(centerline) == 2

    far_segment = centerline[1]
    far_distance = far_segment["distance_end_m"]
    assert far_distance is not None
    # True whole-path arc distance from cage centroid (1, 0.75) to (38, 0.75)
    # is ~37m. The old per-segment-clamped bug would report ~18m (the far
    # segment's own length). Assert we are near the correct whole-path value,
    # well above what the clamped bug would have produced.
    assert far_distance > 30.0
