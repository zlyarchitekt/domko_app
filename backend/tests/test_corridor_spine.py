"""Spine korytarza (plan 2026-07-15 §B): segmenty stref połączone na szwach
w jedną spójną komunikację -- fix dla L/U, gdzie osobne paski per strefa
potrafiły się nie stykać."""

from shapely.geometry import Polygon, box

from services.bsp import rectangle_decompose
from services.corridor_spine import build_spine, nearest_segment_index, spine_polygon


def _zones(footprint):
    return rectangle_decompose(footprint)


def test_rectangle_spine_is_single_segment():
    fp = box(0, 0, 40, 12)
    segments = build_spine(_zones(fp), {}, corridor_width_m=1.5)
    assert len(segments) == 1
    (x1, y1), (x2, y2) = segments[0].p1, segments[0].p2
    assert y1 == y2  # poziomy, wzdłuż dłuższej osi
    assert abs(x2 - x1) == 40.0


def test_l_shape_spine_is_connected():
    """L 30x20 z ramionami 8 m: 2 strefy -> 2 segmenty, których końce
    SPOTYKAJĄ SIĘ w jednym punkcie (staw narożny), a poligon korytarza
    jest jednym spójnym komponentem."""
    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    zones = _zones(l_shape)
    assert len(zones) == 2
    segments = build_spine(zones, {}, corridor_width_m=1.5)
    assert len(segments) == 2
    endpoints = [segments[0].p1, segments[0].p2, segments[1].p1, segments[1].p2]
    # dokładnie jedna para końców pokrywa się (wspólny staw)
    shared = [
        (a, b) for ai, a in enumerate(endpoints) for b in endpoints[ai + 1:]
        if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
    ]
    assert len(shared) == 1, endpoints

    poly = spine_polygon(segments, 1.5, l_shape)
    assert poly.geom_type == "Polygon", "korytarz L musi być jednym spójnym poligonem"
    assert poly.area > 0
    assert l_shape.buffer(1e-6).contains(poly)


def test_u_shape_spine_connected_three_segments():
    u_shape = Polygon([
        (0, 0), (36, 0), (36, 20), (28, 20), (28, 8), (8, 8), (8, 20), (0, 20),
    ])
    zones = _zones(u_shape)
    segments = build_spine(zones, {}, corridor_width_m=1.5)
    assert len(segments) == len(zones)
    poly = spine_polygon(segments, 1.5, u_shape)
    assert poly.geom_type == "Polygon", "korytarz U musi być spójny"


def test_spine_respects_cage_anchor():
    """Klatka przy południowej krawędzi prostokąta przyciąga oś (w granicach
    reguły traktów) -- identycznie jak _corridor_axis_offset."""
    fp = box(0, 0, 40, 12)
    cage = box(0, 0, 4.2, 5.7)
    segments = build_spine(_zones(fp), {0: [cage]}, corridor_width_m=1.5)
    y = segments[0].p1[1]
    from services.circulation import MIN_TRAKT_DEPTH_M, NET_SHRINK_M
    half = (1.5 + 2 * NET_SHRINK_M) / 2.0
    south, north = (y - half) - 0.0, 12.0 - (y + half)
    for band in (south, north):
        assert band <= 1e-6 or band >= MIN_TRAKT_DEPTH_M - 1e-6


def test_nearest_segment_index():
    fp = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    segments = build_spine(_zones(fp), {}, corridor_width_m=1.5)
    horizontal = 0 if abs(segments[0].p1[1] - segments[0].p2[1]) < 1e-6 else 1
    vertical = 1 - horizontal
    assert nearest_segment_index((20.0, 4.0), segments) == horizontal
    assert nearest_segment_index((4.0, 15.0), segments) == vertical
