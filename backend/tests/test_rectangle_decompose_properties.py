"""Property-based tests for rectangle_decompose — the exact class of bug
(cut_cell depth/width, bsp_zones leaving zones concave) that passed 96/96
example-based tests unnoticed in the 2026-07-02 audit needs property tests,
not more examples."""

from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from services.bsp import concave_vertices, rectangle_decompose


def _l_shaped_polygon(cut_x: float, cut_y: float, width: float, height: float) -> Polygon:
    """Generates an L-shaped rectilinear polygon with a notch of size
    (cut_x, cut_y) removed from the top-right corner of a (width, height) box."""
    return Polygon([
        (0, 0), (width, 0), (width, height - cut_y),
        (width - cut_x, height - cut_y), (width - cut_x, height), (0, height),
    ])


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_preserves_area_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return  # degenerate case, not what this test targets
    parts = rectangle_decompose(poly)
    total = sum(p.area for p in parts)
    assert abs(total - poly.area) < max(1e-3, poly.area * 1e-6)


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_no_overlap_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return
    parts = rectangle_decompose(poly)
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            overlap = parts[i].intersection(parts[j]).area
            assert overlap < max(1e-3, poly.area * 1e-6)


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_eliminates_concavity_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return
    for part in rectangle_decompose(poly):
        assert not concave_vertices(part), (
            f"part still concave for width={width} height={height} "
            f"cut_x={cut_x} cut_y={cut_y}: {list(part.exterior.coords)}"
        )
