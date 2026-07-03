from shapely.geometry import Polygon

from services.wall_geometry import (
    NET_SHRINK_M,
    WALL_EXTERIOR_THICKNESS_M,
    WALL_INTERIOR_THICKNESS_M,
    exterior_wall_band,
    interior_wall_bands,
    net_polygon,
)


def test_constants_match_spec():
    """Spec 2026-07-04 (wall-thickness) §4 -- pins the exact approved values."""
    assert WALL_EXTERIOR_THICKNESS_M == 0.40
    assert WALL_INTERIOR_THICKNESS_M == 0.20
    assert NET_SHRINK_M == 0.10


def test_net_polygon_shrinks_uniformly_by_10cm():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    net = net_polygon(rect)
    minx, miny, maxx, maxy = net.bounds
    assert abs(minx - 0.10) < 1e-9
    assert abs(miny - 0.10) < 1e-9
    assert abs(maxx - 9.90) < 1e-9
    assert abs(maxy - 5.90) < 1e-9


def test_net_polygon_too_small_returns_empty_not_crash():
    tiny = Polygon([(0, 0), (0.15, 0), (0.15, 0.15), (0, 0.15)])
    net = net_polygon(tiny)
    assert net.is_empty


def test_exterior_wall_band_area_matches_perimeter_times_thickness():
    # 10x6 rectangle: perimeter 32m. Band = footprint.buffer(0.30) - footprint.buffer(-0.10),
    # i.e. a ring of outer width 0.30 and inner width 0.10 around all 4 sides plus
    # 4 corner squares (mitred join) -- for a rectangle the exact area is:
    # (10+0.6)*(6+0.6) - (10-0.2)*(6-0.2) computed directly below, not approximated.
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    band = exterior_wall_band(footprint)
    expected_area = (10 + 0.6) * (6 + 0.6) - (10 - 0.2) * (6 - 0.2)
    assert abs(band.area - expected_area) < 1e-6


def test_interior_wall_bands_between_two_adjacent_rectangles():
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cell_a = Polygon([(0, 0), (5, 0), (5, 6), (0, 6)])
    cell_b = Polygon([(5, 0), (10, 0), (10, 6), (5, 6)])
    bands = interior_wall_bands(footprint, [cell_a, cell_b])
    # The gap between the two cells' net polygons is exactly 0.20m wide (0.10
    # eaten from each side of the shared axis at x=5), spanning the shared
    # net-height (6 - 2*0.10 = 5.8m, since the top/bottom are footprint/exterior
    # edges shrunk by net_polygon the same way as the exterior envelope below).
    minx, miny, maxx, maxy = bands.bounds
    assert abs((maxx - minx) - 0.20) < 1e-6
    assert abs(minx - 4.90) < 1e-6
    assert abs(maxx - 5.10) < 1e-6


def test_interior_wall_bands_disconnected_returns_multipolygon():
    """With 3+ cells the residual wall frame can be topologically
    disconnected -- Shapely's difference() then returns a MultiPolygon,
    not a Polygon. Three cells side by side tile the whole footprint,
    leaving two separated 0.20m gaps (around x=10 and x=20) that are far
    enough apart (10.10 < 19.90) to never touch each other."""
    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    cell_a = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cell_b = Polygon([(10, 0), (20, 0), (20, 6), (10, 6)])
    cell_c = Polygon([(20, 0), (30, 0), (30, 6), (20, 6)])
    bands = interior_wall_bands(footprint, [cell_a, cell_b, cell_c])

    assert bands.geom_type == "MultiPolygon"
    parts = list(bands.geoms)
    assert len(parts) >= 2

    parts_by_x = sorted(parts, key=lambda p: p.bounds[0])
    first, second = parts_by_x[0], parts_by_x[1]

    fminx, fminy, fmaxx, fmaxy = first.bounds
    assert abs(fminx - 9.90) < 1e-6
    assert abs(fmaxx - 10.10) < 1e-6
    assert abs(fminy - 0.10) < 1e-6
    assert abs(fmaxy - 5.90) < 1e-6

    sminx, sminy, smaxx, smaxy = second.bounds
    assert abs(sminx - 19.90) < 1e-6
    assert abs(smaxx - 20.10) < 1e-6
    assert abs(sminy - 0.10) < 1e-6
    assert abs(smaxy - 5.90) < 1e-6
