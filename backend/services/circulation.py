"""Etap 1 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
umieszczenie klatki schodowej i korytarza w każdej strefie zwróconej przez
services.bsp.rectangle_decompose(). Klatka i korytarz przeniesione z
layout.py bez zmian logiki — nigdy nie były zepsute, zepsute były strefy,
które dostawały na wejściu (patrz spec §1a)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon
from shapely.ops import unary_union

from services.bsp import Zone, rectangle_decompose

CAGE_POSITION_MODES = ("1a", "1b", "2", "3", "auto")
"""plan.md §4.3: 1a=elewacja front, 1b=elewacja dziedziniec/tył, 2=środek traktu,
3=narożnik, auto=narożnik wklęsły jeśli istnieje inaczej narożnik obrysu."""


def concave_vertices_in_zone(polygon: Polygon) -> list[tuple[int, float, float]]:
    """Wykrywa wierzchołki wklęsłe w pojedynczej strefie."""
    from services.bsp import concave_vertices

    return concave_vertices(polygon)


def _build_cage(
    polygon: Polygon, corner_data: tuple[int, float, float], size: float
) -> Polygon:
    """Buduje kwadratową klatkę w narożniku."""
    from services.bsp import corner_cage

    idx, x, y = corner_data
    return corner_cage(polygon, (x, y), size)


def _place_cage_by_mode(polygon: Polygon, mode: str, size: float) -> Polygon | None:
    """Umieszcza klatkę wg trybu z plan.md §4.3.

    - "3"/"auto": narożnik wklęsły jeśli istnieje (jak dotychczas), inaczej
      narożnik bounding-boxa (naprawia przypadek obrysu wypukłego, który
      wcześniej nigdy nie dostawał klatki mimo `place_cage=True`).
    - "2": środek strefy (typowe dla punktowca).
    - "1a": wzdłuż najdłuższej krawędzi zewnętrznej (elewacja frontowa).
    - "1b": wzdłuż najkrótszej krawędzi zewnętrznej — uproszczony zamiennik
      "krawędzi od dziedzińca" (wykrywanie krawędzi wewnętrznej/dziedzińca
      wymagałoby modelu sąsiednich budynków, poza zakresem tego MVP).
    """
    if polygon.is_empty or polygon.area < 1e-6:
        return None

    if mode not in CAGE_POSITION_MODES:
        raise ValueError(f"Unknown cage_position mode '{mode}'. Valid: {CAGE_POSITION_MODES}")

    if mode in ("3", "auto"):
        cv = concave_vertices_in_zone(polygon)
        if cv:
            try:
                cage = _build_cage(polygon, cv[0], size)
            except ValueError:
                return None
            return cage if cage.area > 1e-6 else None
        return _corner_cage_convex(polygon, size)

    if mode == "2":
        return _centered_cage(polygon, size)

    # "1a" / "1b"
    return _edge_cage(polygon, size, longest=(mode == "1a"))


def _corner_cage_convex(polygon: Polygon, size: float) -> Polygon | None:
    """Klatka w narożniku bounding-boxa — dla obrysów wypukłych bez wierzchołka wklęsłego."""
    minx, miny, maxx, maxy = polygon.bounds
    candidate = Polygon(
        [(minx, miny), (minx + size, miny), (minx + size, miny + size), (minx, miny + size)]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _centered_cage(polygon: Polygon, size: float) -> Polygon | None:
    """Klatka wyśrodkowana w strefie (tryb 2 — punktowiec)."""
    center = polygon.centroid
    half = size / 2.0
    candidate = Polygon(
        [
            (center.x - half, center.y - half),
            (center.x + half, center.y - half),
            (center.x + half, center.y + half),
            (center.x - half, center.y + half),
        ]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _edge_cage(polygon: Polygon, size: float, longest: bool) -> Polygon | None:
    """Klatka wzdłuż najdłuższej (tryb 1a) lub najkrótszej (tryb 1b) krawędzi, skierowana do wnętrza."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    if n < 2:
        return None

    edges = []
    for i in range(n):
        p1, p2 = coords[i], coords[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        edges.append((length, p1, p2))
    edges.sort(key=lambda e: e[0], reverse=longest)
    _, p1, p2 = edges[0]

    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    edge_len = math.hypot(dx, dy)
    if edge_len < 1e-9:
        return None
    ux, uy = dx / edge_len, dy / edge_len

    mid_x, mid_y = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    normal_x, normal_y = -uy, ux
    centroid = polygon.centroid
    if normal_x * (centroid.x - mid_x) + normal_y * (centroid.y - mid_y) < 0:
        normal_x, normal_y = -normal_x, -normal_y

    half = size / 2.0
    p_a = (mid_x - ux * half, mid_y - uy * half)
    p_b = (mid_x + ux * half, mid_y + uy * half)
    p_c = (p_b[0] + normal_x * size, p_b[1] + normal_y * size)
    p_d = (p_a[0] + normal_x * size, p_a[1] + normal_y * size)

    candidate = Polygon([p_a, p_b, p_c, p_d])
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _build_corridor(polygon: Polygon, width: float, cage_polygon: Polygon | None = None) -> Polygon:
    """Buduje korytarz wzdłuż osi dłuższego boku prostokątnej (po
    rectangle_decompose) strefy, uwzględniając wyrównanie do pozycji klatki
    schodowej (F2-04). Przeniesiona bez zmian logiki z layout.py — działa
    poprawnie teraz, bo strefa jest już prawie-prostokątna (patrz spec §1a:
    to nigdy nie było zepsute, tylko strefy, które dostawała na wejściu)."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return Polygon()
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        half = width / 2.0
        if cage_polygon:
            cage_y = cage_polygon.centroid.y
            mid_y = max(miny + half, min(maxy - half, cage_y))
        else:
            mid_y = (miny + maxy) / 2.0
        corridor = Polygon(
            [(minx, mid_y - half), (maxx, mid_y - half), (maxx, mid_y + half), (minx, mid_y + half)]
        )
    else:
        half = width / 2.0
        if cage_polygon:
            cage_x = cage_polygon.centroid.x
            mid_x = max(minx + half, min(maxx - half, cage_x))
        else:
            mid_x = (minx + maxx) / 2.0
        corridor = Polygon(
            [(mid_x - half, miny), (mid_x + half, miny), (mid_x + half, maxy), (mid_x - half, maxy)]
        )

    return corridor.intersection(polygon)


@dataclass
class CirculationResult:
    """Wynik Etapu 1: strefy (po rectangle_decompose), zunifikowana
    geometria komunikacji, klatki, i pozostałość na mieszkania (Etap 2)."""

    zones: list[Zone]
    circulation_geometry: Polygon | None
    cage_polygons: list[Polygon] = field(default_factory=list)
    remainder: Polygon = field(default_factory=Polygon)
    """Może być MultiPolygon w praktyce mimo adnotacji typu (patrz spec §9) —
    konsumenci muszą sprawdzać hasattr(geom, "geoms")."""


def place_circulation(
    footprint: Polygon,
    corridor_width_m: float,
    stair_width_m: float,
    place_cage: bool,
    cage_size_m: float,
    cage_position: str,
) -> CirculationResult:
    """Etap 1: dzieli obrys na prawie-prostokątne strefy (rectangle_decompose),
    umieszcza klatkę i korytarz w każdej, zwraca zunifikowany wynik."""
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]

    circulation_geom = Polygon()
    cage_polygons: list[Polygon] = []
    remainder_parts: list[Polygon] = []

    for zone in zones:
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        local_cage: Polygon | None = None
        if place_cage:
            cage_polygon = _place_cage_by_mode(zone.polygon, cage_position, cage_size_m)
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                circulation_geom = unary_union([circulation_geom, cage_polygon])
                cage_polygons.append(cage_polygon)
                zone_remaining = zone.polygon.difference(cage_polygon)
                local_cage = cage_polygon
            else:
                zone_remaining = zone.polygon
        else:
            zone_remaining = zone.polygon

        corridor = _build_corridor(zone_remaining, corridor_width_m, local_cage)
        if corridor.area > 0:
            circulation_geom = unary_union([circulation_geom, corridor])
            zone_remaining = zone_remaining.difference(corridor)

        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)

    remainder = unary_union(remainder_parts) if remainder_parts else Polygon()

    return CirculationResult(
        zones=zones,
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
    )
