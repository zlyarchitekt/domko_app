"""Tests for F2-04: cage position modes (1a/1b/2/3/auto) and program-area fitting."""

from __future__ import annotations

import pytest
from shapely.geometry import Polygon

from services.layout import ApartmentSpec, LayoutInput, generate_layout

RECT_WIDE = Polygon([(0, 0), (40, 0), (40, 10), (0, 10)])  # long edges at y=0/y=10, short at x=0/x=40
SQUARE_20 = Polygon([(0, 0), (20, 0), (20, 20), (0, 20)])
L_SHAPE = Polygon([(0, 0), (20, 0), (20, 8), (8, 8), (8, 20), (0, 20)])


def _generate(footprint, **kwargs):
    apartments = kwargs.pop("apartments", [])
    return generate_layout(LayoutInput(footprint=footprint, apartments=apartments, **kwargs))


def test_convex_footprint_gets_a_cage_in_every_mode():
    """Before F2-04, place_cage=True silently produced zero cages for any
    footprint without a concave vertex — this is the core bug the task fixes."""
    for mode in ("1a", "1b", "2", "3", "auto"):
        layout = _generate(SQUARE_20, place_cage=True, cage_position=mode, cage_size_m=3.0)
        assert layout.cage_polygons, f"mode={mode} produced no cage for a convex footprint"


def test_mode_1a_places_cage_on_longest_edge():
    layout = _generate(RECT_WIDE, place_cage=True, cage_position="1a", cage_size_m=2.0)
    assert layout.cage_polygons
    cage = layout.cage_polygons[0]
    # Longest edges are the horizontal ones (y=0 and y=10); cage should hug one
    # of them flush (dimension-agnostic: the fixed 4.0x5.5 rectangle no longer
    # respects cage_size_m, see spec 2026-07-03 §6, so centroid-distance
    # thresholds tuned for the old cage_size_m=2.0 square no longer apply).
    minx, miny, maxx, maxy = cage.bounds
    assert miny == pytest.approx(0.0, abs=1e-6) or maxy == pytest.approx(10.0, abs=1e-6)


def test_mode_1b_places_cage_on_shortest_edge():
    layout = _generate(RECT_WIDE, place_cage=True, cage_position="1b", cage_size_m=2.0)
    assert layout.cage_polygons
    cage = layout.cage_polygons[0]
    # Shortest edges are the vertical ones (x=0 and x=40); cage should hug one
    # of them flush (see comment in test_mode_1a above re: dimension-agnostic
    # assertion after the cage became a fixed-size rectangle).
    minx, miny, maxx, maxy = cage.bounds
    assert minx == pytest.approx(0.0, abs=1e-6) or maxx == pytest.approx(40.0, abs=1e-6)


def test_mode_2_centers_the_cage():
    layout = _generate(RECT_WIDE, place_cage=True, cage_position="2", cage_size_m=2.0)
    assert layout.cage_polygons
    cage = layout.cage_polygons[0]
    assert cage.centroid.x == pytest.approx(20.0, abs=1.5)
    assert cage.centroid.y == pytest.approx(5.0, abs=1.5)


def test_mode_3_uses_concave_corner_when_available():
    layout = _generate(L_SHAPE, place_cage=True, cage_position="3", cage_size_m=2.5)
    assert layout.cage_polygons
    cage = layout.cage_polygons[0]
    # The reflex corner sits at (8, 8) -- the cage should be anchored AT it (one
    # of the cage's own bbox corners), not merely have its centroid nearby.
    # Centroid-distance thresholds tuned for the old cage_size_m=2.5 square no
    # longer hold now that the cage is a fixed 4.0x5.5 rectangle (spec 2026-07-03
    # §6) whose far corner sits much further from the anchor.
    minx, miny, maxx, maxy = cage.bounds
    bbox_corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    assert any(abs(cx - 8.0) < 1e-6 and abs(cy - 8.0) < 1e-6 for cx, cy in bbox_corners)


def test_invalid_cage_position_mode_raises():
    with pytest.raises(ValueError, match="cage_position"):
        _generate(SQUARE_20, place_cage=True, cage_position="not-a-mode")


def test_oversized_cage_is_rejected_instead_of_producing_empty_zone():
    """A cage_size_m much larger than the footprint must not consume the whole
    zone and leave downstream corridor/apartment-slicing with an empty polygon."""
    tiny = Polygon([(0, 0), (1, 0), (1, 1)])
    layout = generate_layout(
        LayoutInput(footprint=tiny, apartments=[ApartmentSpec(type="1-room", min_area_m2=25, target_count=1)])
    )
    assert layout.cage_polygons == []


def test_double_loaded_corridor_apartments_hit_area_target_exactly():
    """The primary plan.md §4.3 scenario (klatkowiec wzdłużny): a corridor splits
    a simple rectangular footprint into two disconnected strips. Every apartment
    must land on (or very near) its min_area_m2 target."""
    layout = _generate(
        SQUARE_20,
        apartments=[ApartmentSpec(type="1-room", min_area_m2=30, target_count=4)],
        corridor_width_m=1.5,
        place_cage=False,
    )
    assert len(layout.apartments) == 4
    for apt in layout.apartments:
        assert apt.polygon.area == pytest.approx(30.0, rel=0.01)


def test_apartments_are_distributed_on_both_sides_of_corridor():
    """Round-robin fitting (F2-04) must not exhaust one side of a double-loaded
    corridor before touching the other."""
    layout = _generate(
        SQUARE_20,
        apartments=[ApartmentSpec(type="1-room", min_area_m2=30, target_count=4)],
        corridor_width_m=1.5,
        place_cage=False,
    )
    ys = sorted(apt.polygon.centroid.y for apt in layout.apartments)
    # With 4 apartments of ~30 m2 each in a 20x20 square split into two ~9.25m-deep
    # strips, both the bottom strip (y < 10) and top strip (y > 10) must be used.
    assert any(y < 10 for y in ys)
    assert any(y > 10 for y in ys)


def test_mixed_program_areas_are_close_to_targets():
    # place_cage=False isolates "does mixed-type fitting work" from cage
    # placement asymmetrically eating into one side's available depth (a
    # separate, expected interaction verified qualitatively elsewhere).
    layout = _generate(
        SQUARE_20,
        apartments=[
            ApartmentSpec(type="1-room", min_area_m2=30, target_count=2),
            ApartmentSpec(type="2-room", min_area_m2=50, target_count=2),
        ],
        corridor_width_m=1.5,
        place_cage=False,
    )
    by_type = {"1-room": [], "2-room": []}
    for apt in layout.apartments:
        by_type[apt.type].append(apt.polygon.area)
    for area in by_type["1-room"]:
        assert area == pytest.approx(30.0, rel=0.05)
    for area in by_type["2-room"]:
        assert area == pytest.approx(50.0, rel=0.05)
