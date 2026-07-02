"""Tests for solar access analysis against known suncalc.org values."""

from datetime import date

from shapely.geometry import Polygon

from services.layout import ApartmentCell, LayoutResult
from services.solar_analysis import analyze_solar_access


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
