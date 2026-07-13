"""Testy doradcy struktury mieszkań (user 2026-07-11)."""

from fastapi.testclient import TestClient
from main import app
from services.program_advisor import MAX_PROPOSALS, suggest_program
from services.unit_mix import ProgramShare

SHARES = [
    ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
    ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
    ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
    ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
]


def test_suggest_program_baseline_matches_engine_arithmetic():
    baseline, _ = suggest_program(SHARES, 1000.0)
    assert baseline is not None
    # ta sama para derive_total_units/allocate_counts co silnik podziału
    from services.unit_mix import allocate_counts, derive_total_units

    total = derive_total_units(1000.0, SHARES)
    assert baseline.total_units == total
    assert baseline.counts == allocate_counts(SHARES, total)
    assert 0.0 < baseline.utilization <= 1.5


def test_suggest_program_proposals_strictly_better_and_sorted():
    baseline, proposals = suggest_program(SHARES, 437.0)  # celowo "niewygodna" powierzchnia
    assert baseline is not None
    assert len(proposals) <= MAX_PROPOSALS
    for p in proposals:
        assert p.score < baseline.score
        assert sum(p.percentages.values()) == sum(s.percentage for s in SHARES)
        assert all(v >= 0 for v in p.percentages.values())
        assert p.reason
    assert [p.score for p in proposals] == sorted(p.score for p in proposals)


def test_suggest_program_zero_percentages_unevaluable():
    zero = [ProgramShare(type="M1", percentage=0, area_min_m2=25, area_max_m2=32)]
    baseline, proposals = suggest_program(zero, 500.0)
    assert baseline is None and proposals == []


def test_suggest_endpoint_dual_shape():
    client = TestClient(app)
    body = {
        "net_area_m2": 437.0,
        "apartments": [
            {"type": "M1", "min_area_m2": 28.5, "target_count": 1, "percentage": 10, "area_min_m2": 25, "area_max_m2": 32},
            {"type": "M2", "min_area_m2": 43.0, "target_count": 4, "percentage": 40, "area_min_m2": 38, "area_max_m2": 48},
            {"type": "M3", "min_area_m2": 64.0, "target_count": 4, "percentage": 40, "area_min_m2": 58, "area_max_m2": 70},
            {"type": "M4", "min_area_m2": 81.0, "target_count": 1, "percentage": 10, "area_min_m2": 72, "area_max_m2": 90},
        ],
    }
    r = client.post("/api/v1/layout/program/suggest", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["baseline"]["total_units"] >= 1
    assert isinstance(data["proposals"], list)
    for p in data["proposals"]:
        assert set(p["percentages"].keys()) == {"M1", "M2", "M3", "M4"}
        assert p["reason"]

    # wszystkie udziały zerowe -> 422 po polsku
    for a in body["apartments"]:
        a["percentage"] = 0
    r2 = client.post("/api/v1/layout/program/suggest", json=body)
    assert r2.status_code == 422
