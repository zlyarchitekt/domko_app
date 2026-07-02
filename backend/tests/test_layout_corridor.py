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
