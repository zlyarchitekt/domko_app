from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _place_iterative(num_cages=2, iterations=10):
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": num_cages,
            "cage_iterations": iterations,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3, "ends": 0.3, "spread": 0.5},
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    return res.json()


def test_add_manual_cage_onto_current_result_does_not_recompute_placement():
    base = _place_iterative()
    non_best = next(m for m in base["cage_iterations"] if m["seed"] != base["cage_best_seed"])

    request_body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation_geometry": non_best["circulation_geometry"],
        "cage_geometries": non_best["cage_geometries"],
        "remainder": non_best["remainder"],
        "centerline": non_best["centerline"],
        "corridor_width_m": 1.5,
        "manual_cage": [[18, 9], [22, 9], [22, 11.5], [18, 11.5]],
        "max_dist_single_m": 20.0,
        "max_dist_multi_m": 40.0,
    }
    res = client.post("/api/v1/layout/circulation/add-manual", json=request_body)
    assert res.status_code == 200, res.text
    body = res.json()

    # The non-best iteration's own auto-placed cages must all survive
    # untouched -- this is the regression this endpoint exists to prevent
    # (drawing a manual cage used to silently re-run auto/iterative placement
    # from scratch via /layout/circulation, discarding whichever non-best
    # iteration or manually-dragged cage the user had active).
    assert len(body["cage_geometries"]) == non_best["cages_count"] + 1


def test_add_manual_corridor_onto_current_result():
    base = _place_iterative(num_cages=1, iterations=1)
    winner = base["cage_iterations"][0]

    request_body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation_geometry": winner["circulation_geometry"],
        "cage_geometries": winner["cage_geometries"],
        "remainder": winner["remainder"],
        "centerline": winner["centerline"],
        "corridor_width_m": 1.5,
        "manual_corridor": [[20, 1], [20, 10]],
        "max_dist_single_m": 20.0,
        "max_dist_multi_m": 40.0,
    }
    res = client.post("/api/v1/layout/circulation/add-manual", json=request_body)
    assert res.status_code == 200, res.text
    body = res.json()

    # Original centerline segment(s) survive, plus at least one new segment
    # from the manual corridor path.
    assert len(body["centerline"]) > len(winner["centerline"])


def test_add_manual_cage_outside_footprint_rejected():
    base = _place_iterative(num_cages=1, iterations=1)
    winner = base["cage_iterations"][0]

    request_body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation_geometry": winner["circulation_geometry"],
        "cage_geometries": winner["cage_geometries"],
        "remainder": winner["remainder"],
        "centerline": winner["centerline"],
        "corridor_width_m": 1.5,
        "manual_cage": [[38, 10], [45, 10], [45, 16], [38, 16]],
        "max_dist_single_m": 20.0,
        "max_dist_multi_m": 40.0,
    }
    res = client.post("/api/v1/layout/circulation/add-manual", json=request_body)
    assert res.status_code == 422
