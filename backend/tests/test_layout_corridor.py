import pytest
from shapely.geometry import Polygon

from services.layout import ApartmentSpec, LayoutInput, generate_layout


def test_corridor_connects_to_cage_mode_1a():
    """Verify that corridor connects to the cage correctly using new _build_corridor centroid logic."""
    p1 = Polygon([(0, 0), (20, 0), (20, 10), (0, 10), (0, 0)])
    # Mode 1a should place cage on the longest edge (20m length edge)

    input = LayoutInput(
        footprint=p1,
        corridor_width_m=1.5,
        cage_size_m=2.5,
        cage_position="1a",
        apartments=[ApartmentSpec(type="M2", min_area_m2=45.0, target_count=4)]
    )
    result = generate_layout(input)

    assert len(result.cage_polygons) == 1
    cage = result.cage_polygons[0]

    # Corridor and cage should intersect if logic from F2-04 is correct
    corridor_geom = result.circulation_geometry.difference(cage)
    assert cage.intersects(corridor_geom) or cage.touches(corridor_geom), "Corridor does not connect to the cage!"


def test_generate_layout_respects_num_cages():
    p1 = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    input = LayoutInput(
        footprint=p1,
        corridor_width_m=1.5,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=2,
        apartments=[ApartmentSpec(type="M2", min_area_m2=25.0, target_count=2)],
    )
    result = generate_layout(input)
    assert len(result.cage_polygons) == 2


def test_generate_auto_mode_without_cage_iterations_takes_iterative_path():
    """Fix po review Task 7: /generate z corridor_mode=auto i cage_iterations=0
    NIE może cicho spaść do klasycznego double -- gate musi kierować do
    iterate_cage_placement (metas niepuste + modes wypełnione), spójnie z
    gate'em w endpoints/layout.py (/circulation ma już
    `or corridor_mode in ("point","auto")`)."""
    from services.unit_mix import ProgramShare

    fp = Polygon([(0, 0), (23, 0), (23, 13.75), (0, 13.75)])
    input = LayoutInput(
        footprint=fp,
        corridor_mode="auto",
        cage_iterations=0,
        place_cage=True,
        iterations=6,
        program_shares=[
            ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
            ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
            ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
            ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
        ],
    )
    result = generate_layout(input)
    assert result.cage_iteration_metas, "gate powinien pójść przez iterate_cage_placement"
    assert result.circulation_geometry is not None
