from shapely.geometry import Polygon

from services.layout import ApartmentSpec
from services.unit_mix import subdivide_units


def test_subdivide_units_exact_fit_horizontal():
    rect = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    specs = [ApartmentSpec(type="M2", min_area_m2=50, target_count=3)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 50.0) < 0.5
        assert c.area_tolerance_exceeded is False


def test_subdivide_units_vertical_zone_correct_area():
    # Regression test for the depth/width _cut_cell bug fixed 2026-07-02 —
    # a zone taller than it is wide must NOT produce square (w x w) cells.
    rect = Polygon([(0, 0), (6, 0), (6, 30), (0, 30)])
    specs = [ApartmentSpec(type="M2", min_area_m2=50, target_count=3)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 50.0) < 0.5


def test_subdivide_units_uses_best_matching_spec_not_fifo():
    # Regression test for the "permanent retirement" bug (audit finding #6):
    # a small leftover part should still be matched against a LATER,
    # smaller spec even if it doesn't fit the FIRST spec in the program.
    small_rect = Polygon([(0, 0), (5, 0), (5, 6), (0, 6)])  # 30 m^2
    specs = [
        ApartmentSpec(type="M4", min_area_m2=80, target_count=1),  # doesn't fit
        ApartmentSpec(type="M1", min_area_m2=28, target_count=1),  # fits well
    ]
    cells, leftover = subdivide_units(small_rect, specs)
    assert len(cells) == 1
    assert cells[0].type == "M1"


def test_subdivide_units_flags_tolerance_exceeded():
    # A rectangle whose only achievable cut deviates from the spec by more
    # than 3% must be flagged, not silently accepted.
    rect = Polygon([(0, 0), (10, 0), (10, 3), (0, 3)])  # 30 m^2, depth=3
    # min_area_m2=50 with depth=3 needs cut_size=16.67, area=50.0 exactly —
    # use a spec that can't land within 3% given MIN_CELL_DIMENSION_M=2.0
    # forcing a floor: request an area smaller than what MIN_CELL_DIMENSION
    # can produce (2.0 * 3 = 6.0 minimum area achievable).
    specs = [ApartmentSpec(type="M0", min_area_m2=3.0, target_count=1)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 1
    assert cells[0].area_tolerance_exceeded is True


def test_subdivide_units_no_specs_returns_all_as_leftover():
    rect = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    cells, leftover = subdivide_units(rect, [])
    assert cells == []
    assert leftover is not None
    assert abs(leftover.area - 100.0) < 1e-6
