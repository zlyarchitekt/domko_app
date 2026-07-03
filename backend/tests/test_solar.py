"""Tests for solar access analysis against known suncalc.org values."""

from datetime import date

from shapely.geometry import Polygon

from services.layout import ApartmentCell, LayoutResult
from services.solar_analysis import FacadeAnalysis, _summarize_apartments, analyze_solar_access


def test_solar_analysis_against_suncalc():
    """Verify pvlib-based analysis against approximate suncalc values for Warsaw on Spring Equinox."""
    # A single apartment roughly 10x10m
    p1 = Polygon([(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)])
    apt = ApartmentCell(id="Apt-1", type="M1", polygon=p1)

    # Very simple layout
    layout = LayoutResult(
        footprint=p1,
        footprint_area_m2=100.0,
        circulation_area_m2=0.0,
        usable_area_m2=100.0,
        apartments=[apt],
        leftover=None,
        zones=[],
        circulation_geometry=Polygon(),
        cage_polygons=[],
        corridor_width_m=1.5,
        stair_width_m=1.2,
    )

    # 2026-03-21 is the equinox. Warsaw coordinates.
    # On the equinox, the sun should be up roughly 12 hours.
    # South-facing facade (if azimuth_to_cardinal maps 180 -> S)
    result = analyze_solar_access(layout, latitude=52.2297, longitude=21.0122, analysis_date=date(2026, 3, 21))

    assert len(result.facades) > 0
    total_hours = sum(f.hours_total for f in result.facades)

    # We expect some substantial direct sunlight on the facades.
    # Typically, south receives a large chunk of hours (around 8-10h of direct).
    assert total_hours > 5.0, f"Expected more than 5 hours of total sun, got {total_hours}"


def _facade(apartment_id: str, orientation: str, hours_total: float, required_hours: float) -> FacadeAnalysis:
    return FacadeAnalysis(
        apartment_id=apartment_id,
        apartment_type="M2",
        orientation=orientation,
        azimuth_deg=0.0,
        edge=((0.0, 0.0), (5.0, 0.0)),
        length_m=5.0,
        hours_total=hours_total,
        hours_status={},
        hourly=[],
        meets_wt=hours_total >= required_hours,
        required_hours=required_hours,
    )


def test_facade_edge_excludes_interior_portion_of_collinear_wall():
    """Regression for user report 2026-07-03 (with screenshot + exported JSON):
    solar analysis colored/labeled an INTERIOR apartment edge, not just the
    true exterior facade. Root cause: FacadeAnalysis never exposed the actual
    `edge` coordinates the backend already computes correctly -- the frontend
    had to re-derive "which edge is the facade" by matching azimuth angle
    alone against the apartment's own polygon ring. Real apartment polygons
    routinely carry a redundant collinear vertex along a wall (BSP-split
    artifact, see the real f063c2a2 apartment in the reported JSON: three
    collinear points at x=6 spanning y=-3.12 to 7.12, of which only y=-3.12
    to -2 is actually on the footprint boundary). Any other ring edge sharing
    that same azimuth then wrongly matched the one real facade on the
    frontend, even though it was never selected as a facade here.

    This test builds the same shape: an L-shaped footprint's notch wall
    (x=4, y=4..10) is a true facade, but the apartment's west edge also has a
    collinear vertex at (4,4) continuing DOWN to (4,0) -- a length that is
    NOT on the footprint boundary at all (the footprint continues to x=0 for
    y<4). The backend must select only the true 6m segment as a facade, and
    now must expose its exact coordinates so the frontend can draw exactly
    that segment instead of guessing by azimuth."""
    footprint = Polygon([(0, 0), (10, 0), (10, 10), (4, 10), (4, 4), (0, 4)])
    apartment = Polygon([(4, 0), (10, 0), (10, 10), (4, 10), (4, 4), (4, 0)])
    apt = ApartmentCell(id="apt-notch", type="M2", polygon=apartment)

    layout = LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint.area,
        circulation_area_m2=0.0,
        usable_area_m2=apartment.area,
        apartments=[apt],
        leftover=None,
        zones=[],
        circulation_geometry=Polygon(),
        cage_polygons=[],
        corridor_width_m=1.5,
        stair_width_m=1.2,
    )

    result = analyze_solar_access(layout, latitude=52.2297, longitude=21.0122, analysis_date=date(2026, 3, 21))

    west_facades = [f for f in result.facades if f.orientation == "W"]
    assert len(west_facades) == 1, f"Expected exactly one west facade, got {len(west_facades)}"

    facade = west_facades[0]
    assert facade.length_m == 6.0, f"Facade must be only the true exterior span (6m), got {facade.length_m}m"

    edge_ys = sorted(p[1] for p in facade.edge)
    assert edge_ys == [4.0, 10.0], (
        f"Facade edge must span exactly the exterior notch wall (y=4 to y=10), "
        f"not extend into the interior (y=0 to y=4). Got edge={facade.edge}"
    )


def test_apartment_wt_passed_requires_only_one_passing_facade():
    """WT §13 ust. 1 (plan.md §4.6): passes if AT LEAST ONE facade/room meets
    the required hours -- not every facade. Regression for a bug where
    wt_passed used min_hours (requiring ALL facades to pass) instead of
    max_hours, silently marking a compliant apartment (one passing west
    facade + one failing north facade) as non-compliant in the exported
    JSON/PDF, while the frontend canvas colored it correctly as passing."""
    required = 3.0
    facades = [
        _facade("apt-mixed", "W", 4.25, required),  # passes
        _facade("apt-mixed", "N", 0.0, required),  # fails
    ]
    summary = _summarize_apartments(facades, required)
    assert len(summary) == 1
    assert summary[0]["wt_passed"] is True

    facades_all_fail = [
        _facade("apt-fail", "N", 0.0, required),
    ]
    summary_fail = _summarize_apartments(facades_all_fail, required)
    assert summary_fail[0]["wt_passed"] is False
