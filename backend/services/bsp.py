from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, Polygon
from shapely.ops import split as shapely_split
from shapely.ops import unary_union


@dataclass(frozen=True)
class Zone:
    """Jedna strefa BSP: prostokątna komórka opisana przez nazwę i poligon."""

    name: str
    polygon: Polygon


def is_concave(polygon: Polygon) -> bool:
    """Zwraca True, gdy poligon jest wklęsły (ma co najmniej jeden wklęsły wierzchołek)."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    if n < 4:
        return False
    sign = 0
    for i in range(n):
        p0 = coords[(i - 1) % n]
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
        if cross != 0:
            if sign == 0:
                sign = 1 if cross > 0 else -1
            elif (cross > 0 and sign < 0) or (cross < 0 and sign > 0):
                return True
    return False


def concave_vertices(polygon: Polygon) -> list[tuple[int, float, float]]:
    """Zwraca indeksy i współrzędne wierzchołków wklęsłych poligonu."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    result: list[tuple[int, float, float]] = []
    if n < 4:
        return result
    signed_area = sum(
        (coords[i][0] * coords[(i + 1) % n][1] - coords[(i + 1) % n][0] * coords[i][1])
        for i in range(n)
    )
    is_ccw = signed_area > 0
    for i in range(n):
        p0 = coords[(i - 1) % n]
        p1 = coords[i]
        p2 = coords[(i + 1) % n]
        cross = (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0])
        if cross == 0:
            continue
        if is_ccw:
            if cross < 0:
                result.append((i, coords[i][0], coords[i][1]))
        else:
            if cross > 0:
                result.append((i, coords[i][0], coords[i][1]))
    return result


def split_polygon_by_edge(
    polygon: Polygon, p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[Polygon, Polygon]:
    """Dzieli poligon prostą przechodzącą przez dwa punkty (p1, p2).

    Rozszerza odcinek p1-p2 do prostej przecinającej cały poligon, następnie
    używa shapely.ops.split — poprawnie obsługuje poligony wklęsłe, w
    których prosta może przeciąć granicę więcej niż dwa razy (każdy
    fragment trafia na właściwą stronę wg położenia względem prostej, żadna
    powierzchnia nie ginie — naprawa buga z audytu 2026-07-02, gdzie
    poprzednia wersja brała tylko dwa skrajne punkty przecięcia i cicho
    odrzucała resztę geometrii przez `polygon.difference(cutter.buffer(eps))`).
    Naprawia też przypadek, gdy linia cięcia jest kolinearna z istniejącą
    krawędzią (poprzednia wersja obsługiwała tylko przecięcia typu
    Point/MultiPoint, cicho ignorując LineString — analog buga solarnego
    naprawionego dziś w services/solar_analysis.py).
    """
    minx, miny, maxx, maxy = polygon.bounds
    diag = math.hypot(maxx - minx, maxy - miny) * 2 + 1.0
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        raise ValueError("Split line points must be distinct")
    ux, uy = dx / length, dy / length
    ext_a = (p1[0] - ux * diag, p1[1] - uy * diag)
    ext_b = (p2[0] + ux * diag, p2[1] + uy * diag)
    cutter = LineString([ext_a, ext_b])

    # Reject lines that don't actually pass through/touch the polygon in
    # their GIVEN (unextended) form — the extended cutter almost always
    # intersects any bounded polygon (it's infinite), so that check alone
    # would silently accept nonsensical split lines drawn nowhere near the
    # footprint (e.g. a UI split-line the user drew off to the side).
    if not LineString([p1, p2]).intersects(polygon):
        raise ValueError("Split line does not intersect polygon boundary in two distinct points")

    try:
        result = shapely_split(polygon, cutter)
    except Exception as exc:
        raise ValueError(f"Could not split polygon: {exc}") from exc

    geoms = [g for g in result.geoms if g.geom_type == "Polygon" and g.area > 1e-9]
    if not geoms:
        raise ValueError("Split line does not intersect polygon boundary in two distinct points")
    if len(geoms) == 1:
        # Cutter didn't actually divide the interior (e.g. collinear with an
        # existing edge, tangent to the boundary) — degenerate but not an
        # error: whole polygon, empty second part, no area lost.
        return geoms[0], Polygon()

    # Normal to the cutting line — used to decide which side each resulting
    # fragment is on (there can be more than one fragment per side for a
    # concave polygon; they get unioned together).
    nx_, ny_ = -uy, ux

    def side(g: Polygon) -> float:
        c = g.centroid
        return (c.x - p1[0]) * nx_ + (c.y - p1[1]) * ny_

    left = [g for g in geoms if side(g) >= 0]
    right = [g for g in geoms if side(g) < 0]
    if not left or not right:
        raise ValueError("Split did not produce two polygons")

    part_a = unary_union(left) if len(left) > 1 else left[0]
    part_b = unary_union(right) if len(right) > 1 else right[0]
    return part_a, part_b


def corner_cage(polygon: Polygon, corner: tuple[float, float], size: float = 1.0) -> Polygon:
    """Generuje kwadratową klatkę w narożniku (przy wierzchołku wklęsłym) o boku `size`.

    Klatka jest orientowana tak, by leżeć wewnątrz poligonu wzdłuż dwóch krawędzi
    przylegających do danego wierzchołka.
    """
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    idx = next(
        (
            i
            for i, p in enumerate(coords)
            if abs(p[0] - corner[0]) < 1e-9 and abs(p[1] - corner[1]) < 1e-9
        ),
        None,
    )
    if idx is None:
        raise ValueError("Corner not found in polygon")
    prev = coords[(idx - 1) % n]
    nxt = coords[(idx + 1) % n]

    def unit(v: tuple[float, float]) -> tuple[float, float]:
        length = (v[0] ** 2 + v[1] ** 2) ** 0.5
        if length == 0:
            return (0.0, 0.0)
        return (v[0] / length, v[1] / length)

    e1 = unit((prev[0] - corner[0], prev[1] - corner[1]))
    e2 = unit((nxt[0] - corner[0], nxt[1] - corner[1]))

    def make_cage(sign: int) -> Polygon:
        return Polygon(
            [
                (corner[0], corner[1]),
                (corner[0] + sign * e1[0] * size, corner[1] + sign * e1[1] * size),
                (
                    corner[0] + sign * (e1[0] + e2[0]) * size,
                    corner[1] + sign * (e1[1] + e2[1]) * size,
                ),
                (corner[0] + sign * e2[0] * size, corner[1] + sign * e2[1] * size),
            ]
        )

    candidates = []
    for sign in (1, -1):
        cage = make_cage(sign)
        if not cage.is_valid or cage.area <= 0:
            continue
        candidates.append((cage, polygon.intersection(cage).area))
    if not candidates:
        raise ValueError("Cannot build a non-degenerate cage for the given corner")
    best_cage = max(candidates, key=lambda item: item[1])[0]

    if not polygon.contains(best_cage):
        best_cage = best_cage.intersection(polygon)
    return best_cage


def bsp_zones(polygon: Polygon, max_zone_area: float | None = None) -> list[Zone]:
    """Rekurencyjnie dzieli poligon na strefy prostokątne; dla wklęsłych najpierw wycina klatkę w narożniku."""
    zones: list[Zone] = []

    def recurse(poly: Polygon, name_prefix: str):
        if max_zone_area is not None and poly.area <= max_zone_area:
            zones.append(Zone(name=name_prefix, polygon=poly))
            return
        cv = concave_vertices(poly)
        if cv:
            idx, x, y = cv[0]
            cage = corner_cage(poly, (x, y))
            if cage.area <= 0:
                zones.append(Zone(name=name_prefix, polygon=poly))
                return
            remainder = poly.difference(cage)
            if remainder.is_empty:
                zones.append(Zone(name=f"{name_prefix}-cage", polygon=cage))
                return
            zones.append(Zone(name=f"{name_prefix}-cage", polygon=cage))
            if remainder.geom_type == "Polygon":
                recurse(remainder, f"{name_prefix}-r")
            else:
                for i, geom in enumerate(remainder.geoms):
                    recurse(geom, f"{name_prefix}-r{i}")
        else:
            zones.append(Zone(name=name_prefix, polygon=poly))

    recurse(polygon, "Z")
    return zones
