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
        length_m=5.0,
        hours_total=hours_total,
        hours_status={},
        hourly=[],
        meets_wt=hours_total >= required_hours,
        required_hours=required_hours,
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
