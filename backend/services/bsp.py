from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import LineString, Polygon


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
    """Dzieli poligon prostą przechodzącą przez dwa punkty krawędzi (p1, p2)."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    line = LineString([p1, p2])
    intersections = set()
    for i in range(n):
        edge = LineString([coords[i], coords[(i + 1) % n]])
        if edge.intersects(line):
            inter = edge.intersection(line)
            if not inter.is_empty:
                if inter.geom_type == "Point":
                    intersections.add((round(inter.x, 6), round(inter.y, 6)))
                elif inter.geom_type == "MultiPoint":
                    for pt in inter.geoms:
                        intersections.add((round(pt.x, 6), round(pt.y, 6)))
    pts = sorted(intersections)
    if len(pts) < 2:
        raise ValueError("Split line does not intersect polygon boundary in two distinct points")
    cutter = LineString([pts[0], pts[-1]])
    parts = polygon.difference(cutter.buffer(1e-9))
    if parts.geom_type == "Polygon":
        return parts, Polygon()
    geoms = list(parts.geoms)
    if len(geoms) < 2:
        raise ValueError("Split did not produce two polygons")
    return geoms[0], geoms[1]


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
