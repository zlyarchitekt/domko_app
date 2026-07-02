import pytest
from shapely.geometry import Polygon
from services.solar_analysis import analyze_solar_access
from services.layout import ApartmentCell, LayoutResult

def _mock_layout() -> LayoutResult:
    p1 = Polygon([(0, 0), (20, 0), (20, 20), (0, 20), (0, 0)])
    apt = ApartmentCell(id="Apt-1", type="M1", polygon=p1)
    return LayoutResult(
        footprint=p1,
        footprint_area_m2=400.0,
        circulation_area_m2=0.0,
        usable_area_m2=400.0,
        apartments=[apt],
        leftover=None,
        zones=[],
        building_azimuth_deg=0.0,
        circulation_geometry=Polygon(),
        cage_polygons=[],
        corridor_width_m=1.5,
        stair_width_m=1.2,
    )

def test_solar_analysis_performance():
    """
    Test performance of solar analysis. Must run well under 3 seconds per F7-04 constraints.
    """
    layout = _mock_layout()
    import time
    start_time = time.perf_counter()
    # Execute function
    result = analyze_solar_access(
        layout,
        52.2297,
        21.0122,
        "2026-03-21",
        "Europe/Warsaw",
        1.5,
        None
    )
    duration = time.perf_counter() - start_time
    
    assert result.building_orientation is not None
    assert duration < 3.0, f"Solar analysis took too long: {duration:.2f}s"
