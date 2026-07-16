"""Spine korytarza (plan 2026-07-15 §B): pozioma komunikacja jako JEDNA
spójna łamana zamiast niezależnych pasków per strefa. Segment na strefę
liczony dotychczasową regułą traktów (_corridor_axis_offset), a potem końce
segmentów sąsiadujących stref są ŁĄCZONE na szwie: koniec segmentu bliższy
szwu jest przesuwany do punktu przecięcia z osią segmentu sąsiada
(staw narożny "L"). Poligon korytarza = unia pasków per segment, przycięta
do obrysu -- z konstrukcji spójna tam, gdzie segmenty się stykają."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from services.circulation import NET_SHRINK_M, _corridor_axis_offset

_SEAM_TOL_M = 0.5
"""Maksymalny dystans strefa-strefa uznawany za wspólny szew."""


@dataclass
class SpineSegment:
    p1: tuple[float, float]
    p2: tuple[float, float]
    zone_index: int

    @property
    def horizontal(self) -> bool:
        return abs(self.p2[1] - self.p1[1]) <= abs(self.p2[0] - self.p1[0])


def _zone_axis_segment(
    zone: Polygon, zone_index: int, cages: list[Polygon], corridor_width_m: float,
    prefer_flush: bool = False,
) -> SpineSegment | None:
    minx, miny, maxx, maxy = zone.bounds
    w, h = maxx - minx, maxy - miny
    grown = corridor_width_m + 2 * NET_SHRINK_M
    half = grown / 2.0
    cages_union = unary_union(cages) if cages else None
    if w >= h:
        if grown >= h:
            return None
        cage_bounds = (cages_union.bounds[1], cages_union.bounds[3]) if cages_union else None
        mid = _corridor_axis_offset(miny, maxy, half, cage_bounds, prefer_flush)
        return SpineSegment(p1=(minx, mid), p2=(maxx, mid), zone_index=zone_index)
    if grown >= w:
        return None
    cage_bounds = (cages_union.bounds[0], cages_union.bounds[2]) if cages_union else None
    mid = _corridor_axis_offset(minx, maxx, half, cage_bounds, prefer_flush)
    return SpineSegment(p1=(mid, miny), p2=(mid, maxy), zone_index=zone_index)


def _connect_at_seam(a: SpineSegment, b: SpineSegment) -> None:
    """Modyfikuje IN PLACE: dosuwa bliższe szwu końce segmentów a i b do
    wspólnego stawu = punkt (x osi pionowego, y osi poziomego). Dla pary
    równoległych segmentów (kolinearne strefy) staw = środek odcinka
    łączącego najbliższe końce."""
    if a.horizontal != b.horizontal:
        hseg, vseg = (a, b) if a.horizontal else (b, a)
        joint = (vseg.p1[0], hseg.p1[1])
    else:
        pairs = [(pa, pb) for pa in (a.p1, a.p2) for pb in (b.p1, b.p2)]
        pa, pb = min(pairs, key=lambda pq: math.dist(pq[0], pq[1]))
        joint = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)

    for seg in (a, b):
        if math.dist(seg.p1, joint) <= math.dist(seg.p2, joint):
            seg.p1 = joint
        else:
            seg.p2 = joint


def build_spine(
    zones: list[Polygon],
    cages_by_zone: dict[int, list[Polygon]],
    corridor_width_m: float,
    prefer_flush: bool = False,
) -> list[SpineSegment]:
    segments: list[SpineSegment] = []
    for i, zone in enumerate(zones):
        if not zone.is_valid or zone.area < 1e-6:
            continue
        seg = _zone_axis_segment(zone, i, cages_by_zone.get(i, []), corridor_width_m, prefer_flush)
        if seg is not None:
            segments.append(seg)

    # łącz każdą parę segmentów, których strefy się stykają (deterministycznie
    # po indeksach rosnąco)
    for ai in range(len(segments)):
        for bi in range(ai + 1, len(segments)):
            za = zones[segments[ai].zone_index]
            zb = zones[segments[bi].zone_index]
            if za.distance(zb) <= _SEAM_TOL_M:
                _connect_at_seam(segments[ai], segments[bi])
    return segments


def spine_polygon(
    segments: list[SpineSegment], corridor_width_m: float, footprint: Polygon
) -> "Polygon | MultiPolygon":
    grown = corridor_width_m + 2 * NET_SHRINK_M
    strips = [
        LineString([s.p1, s.p2]).buffer(grown / 2.0, cap_style="flat", join_style="mitre")
        for s in segments
        if math.dist(s.p1, s.p2) > 1e-9
    ]
    if not strips:
        return Polygon()
    # flat caps zostawiają szczelinę w stawie -- domknij ją kwadratem w stawie
    joints = []
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            for pa in (segments[i].p1, segments[i].p2):
                for pb in (segments[j].p1, segments[j].p2):
                    if math.dist(pa, pb) < 1e-9:
                        joints.append(Point(pa).buffer(grown / 2.0, cap_style="square"))
    return unary_union(strips + joints).intersection(footprint)


def nearest_segment_index(point: tuple[float, float], segments: list[SpineSegment]) -> int:
    p = Point(point)
    return min(
        range(len(segments)),
        key=lambda i: LineString([segments[i].p1, segments[i].p2]).distance(p),
    )
