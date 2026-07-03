from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Polygon
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


def rectangle_decompose(poly: Polygon | MultiPolygon) -> list[Polygon]:
    """Dzieli (możliwie wklęsły) poligon na listę prawie-prostokątnych części.

    Rekurencyjnie tnie przez każdy wierzchołek wklęsły — przedłużając jedną
    z dwóch sąsiadujących krawędzi przez ten wierzchołek w głąb poligonu —
    aż nie zostaną żadne wierzchołki wklęsłe. Zastępuje `bsp_zones()`'s
    fikcyjną obsługę wklęsłości (stały nibble 1x1m w narożniku, który
    często zostawiał resztę wciąż wklęsłą — patrz audyt 2026-07-02).

    Poligony wypukłe, ale nie ściśle prostokątne (np. skośny czworobok po
    ekstremalnej edycji wierzchołka), zostają jedną nie-prostokątną częścią
    — udokumentowane ograniczenie, patrz spec §10.
    """
    if hasattr(poly, "geoms"):
        result: list[Polygon] = []
        for part in poly.geoms:
            if part.geom_type == "Polygon" and part.area > 1e-9:
                result.extend(rectangle_decompose(part))
        return result

    if poly.is_empty or poly.area < 1e-9:
        return []

    cv = concave_vertices(poly)
    if not cv:
        return [poly]

    idx, x, y = cv[0]
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)
    prev_pt = coords[(idx - 1) % n]
    curr_pt = (x, y)
    next_pt = coords[(idx + 1) % n]

    minx, miny, maxx, maxy = poly.bounds
    diag = math.hypot(maxx - minx, maxy - miny) * 2 + 1.0

    candidates: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for anchor in (prev_pt, next_pt):
        edx, edy = curr_pt[0] - anchor[0], curr_pt[1] - anchor[1]
        elen = math.hypot(edx, edy)
        if elen < 1e-9:
            continue
        ux, uy = edx / elen, edy / elen
        far = (curr_pt[0] + ux * diag, curr_pt[1] + uy * diag)
        candidates.append((curr_pt, far))

    for p1, p2 in candidates:
        try:
            part_a, part_b = split_polygon_by_edge(poly, p1, p2)
        except ValueError:
            continue
        if part_a.area < 1e-9 or part_b.area < 1e-9:
            continue
        return rectangle_decompose(part_a) + rectangle_decompose(part_b)

    # Neither candidate cut produced a valid two-way split (degenerate
    # geometry) — return as a single (still-concave) zone rather than loop
    # forever. Downstream code (fit_program_to_rectangles) falls back to
    # bounding-box sizing for non-rectangular parts, same as today.
    return [poly]


def corner_cage(
    polygon: Polygon,
    corner: tuple[float, float],
    width: float = 1.0,
    depth: float = 1.0,
) -> Polygon:
    """Generuje prostokątną klatkę w narożniku (przy wierzchołku wklęsłym).

    Rozpiętość wzdłuż każdej z dwóch krawędzi przylegających do narożnika:
    `width` gdy krawędź jest bardziej pozioma (|dx| >= |dy|), `depth` gdy
    bardziej pionowa — spec 2026-07-03 (staircase-cage-rectangle) §4.2,
    reguła deterministyczna dla prostokąta zamiast dawnego kwadratu o boku
    `size`. Klatka jest orientowana tak, by leżeć wewnątrz poligonu wzdłuż
    dwóch krawędzi przylegających do danego wierzchołka.
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

    def extent(e: tuple[float, float]) -> float:
        return width if abs(e[0]) >= abs(e[1]) else depth

    e1 = unit((prev[0] - corner[0], prev[1] - corner[1]))
    e2 = unit((nxt[0] - corner[0], nxt[1] - corner[1]))
    s1 = extent(e1)
    s2 = extent(e2)

    def make_cage(sign: int) -> Polygon:
        return Polygon(
            [
                (corner[0], corner[1]),
                (corner[0] + sign * e1[0] * s1, corner[1] + sign * e1[1] * s1),
                (
                    corner[0] + sign * (e1[0] * s1 + e2[0] * s2),
                    corner[1] + sign * (e1[1] * s1 + e2[1] * s2),
                ),
                (corner[0] + sign * e2[0] * s2, corner[1] + sign * e2[1] * s2),
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


