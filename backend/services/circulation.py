"""Etap 1 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
umieszczenie klatki schodowej i korytarza w każdej strefie zwróconej przez
services.bsp.rectangle_decompose(). Klatka i korytarz przeniesione z
layout.py bez zmian logiki — nigdy nie były zepsute, zepsute były strefy,
które dostawały na wejściu (patrz spec §1a)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from services.bsp import Zone, rectangle_decompose

CAGE_POSITION_MODES = ("1a", "1b", "2", "3", "auto")
"""plan.md §4.3: 1a=elewacja front, 1b=elewacja dziedziniec/tył, 2=środek traktu,
3=narożnik, auto=narożnik wklęsły jeśli istnieje inaczej narożnik obrysu."""

CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0
CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M = 40.0
"""Progi kolorowania linii środkowej korytarza (spec §7) -- świadomie
osobne od wt_validation.py's DEFAULT_MAX_CORRIDOR_DISTANCE_M (inny moduł,
inny punkt cyklu życia layoutu; duplikacja dwóch float jest tańsza niż
sprzężenie Etapu 1 z walidacją post-Etap-2)."""


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


def _place_cage_by_mode(
    polygon: Polygon,
    mode: str,
    size: float,
    preferred_corner: tuple[float, float] | None = None,
) -> Polygon | None:
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
        return _corner_cage_convex(polygon, size, preferred=preferred_corner)

    if mode == "2":
        return _centered_cage(polygon, size)

    # "1a" / "1b"
    return _edge_cage(polygon, size, longest=(mode == "1a"))


def _corner_cage_convex(
    polygon: Polygon, size: float, preferred: tuple[float, float] | None = None
) -> Polygon | None:
    """Klatka w narożniku bounding-boxa — dla stref bez własnego wierzchołka wklęsłego.

    Domyślnie narożnik (minx,miny). Jeśli `preferred` pokrywa się z jednym z
    czterech narożników bbox (patrz `place_circulation`'s `_find_preferred_
    corner` — strefa po `rectangle_decompose` traci swój wklęsły wierzchołek,
    ale ten wierzchołek staje się zwykłym narożnikiem JEDNEJ z sąsiadujących
    prostokątnych stref), użyj go zamiast (minx,miny) — przywraca sens trybu
    "3"/"auto" (klatka schowana w narożniku wewnętrznym) po dekompozycji."""
    minx, miny, maxx, maxy = polygon.bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    ax, ay = corners[0]
    if preferred is not None:
        for cx, cy in corners:
            if abs(cx - preferred[0]) < 1e-6 and abs(cy - preferred[1]) < 1e-6:
                ax, ay = cx, cy
                break
    sx = size if ax == minx else -size
    sy = size if ay == miny else -size
    candidate = Polygon([(ax, ay), (ax + sx, ay), (ax + sx, ay + sy), (ax, ay + sy)])
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


def _corridor_centerline(
    polygon: Polygon, width: float, cage_polygon: Polygon | None = None
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Oś korytarza strefy jako 2-punktowy odcinek — ta sama oś, ten sam
    warunek wyrównania do klatki co _build_corridor(), tylko zwrócona jako
    linia zamiast wypełnionego prostokąta (spec §3.1). None gdy korytarz
    o zadanej szerokości nie mieści się w strefie."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return None
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny
    half = width / 2.0

    if w >= h:
        if width >= h:
            return None
        if cage_polygon:
            cage_y = cage_polygon.centroid.y
            mid_y = max(miny + half, min(maxy - half, cage_y))
        else:
            mid_y = (miny + maxy) / 2.0
        return ((minx, mid_y), (maxx, mid_y))
    else:
        if width >= w:
            return None
        if cage_polygon:
            cage_x = cage_polygon.centroid.x
            mid_x = max(minx + half, min(maxx - half, cage_x))
        else:
            mid_x = (minx + maxx) / 2.0
        return ((mid_x, miny), (mid_x, maxy))


def _join_centerlines(
    segments: list[tuple[tuple[float, float], tuple[float, float]]]
) -> list[tuple[float, float]]:
    """Łączy odcinki centerline sąsiednich stref w jedną łamaną (spec §3.2).
    Zachłanny nearest-neighbor: zaczyna od pierwszego segmentu, za każdym
    razem dołącza segment, którego bliższy koniec leży najbliżej ostatniego
    punktu ścieżki. NIE straight-skeleton (odrzucone jako zbyt kruche dla
    wklęsłych kształtów w tej sesji) -- niepotrzebne tu, bo rectangle_
    decompose() już daje prawie-prostokątne strefy."""
    if not segments:
        return []

    remaining = list(segments[1:])
    path: list[tuple[float, float]] = [segments[0][0], segments[0][1]]

    while remaining:
        last = path[-1]
        best_idx = None
        best_dist = None
        best_reversed = False
        for i, (p1, p2) in enumerate(remaining):
            d1 = math.hypot(p1[0] - last[0], p1[1] - last[1])
            d2 = math.hypot(p2[0] - last[0], p2[1] - last[1])
            if best_dist is None or d1 < best_dist:
                best_dist, best_idx, best_reversed = d1, i, False
            if d2 < best_dist:
                best_dist, best_idx, best_reversed = d2, i, True
        p1, p2 = remaining.pop(best_idx)
        if best_reversed:
            path.append(p1)
        else:
            path.append(p2)

    return path


def _classify_segment_loading(
    zone_polygon: Polygon, segment: tuple[tuple[float, float], tuple[float, float]], corridor_width: float
) -> str:
    """"single" albo "double" (spec §3.3) -- geometryczne, NIE zależne od
    danych Etapu 2 (mieszkania jeszcze nie istnieją, gdy place_circulation()
    działa). Sonduje obie strony odcinka na głębokość MIN_ROOM_WIDTH_M
    (wt_validation.py) poza pasem korytarza."""
    from services.wt_validation import MIN_ROOM_WIDTH_M

    (x1, y1), (x2, y2) = segment
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return "single"
    ux, uy = dx / length, dy / length
    normal_x, normal_y = -uy, ux

    half_corridor = corridor_width / 2.0
    depth = MIN_ROOM_WIDTH_M
    sides_with_room = 0
    for sign in (1.0, -1.0):
        near = (
            x1 + normal_x * half_corridor * sign,
            y1 + normal_y * half_corridor * sign,
        )
        far = (
            near[0] + normal_x * depth * sign,
            near[1] + normal_y * depth * sign,
        )
        far2 = (
            x2 + normal_x * (half_corridor + depth) * sign,
            y2 + normal_y * (half_corridor + depth) * sign,
        )
        near2 = (
            x2 + normal_x * half_corridor * sign,
            y2 + normal_y * half_corridor * sign,
        )
        probe = Polygon([near, far, far2, near2])
        if not probe.is_valid or probe.area < 1e-9:
            continue
        clipped = probe.intersection(zone_polygon)
        if clipped.area > probe.area * 0.9:
            sides_with_room += 1

    return "double" if sides_with_room >= 2 else "single"


def _distances_along_centerline(
    path: list[tuple[float, float]], cage_points: list[tuple[float, float]]
) -> list[float]:
    """Odległość (długość łuku wzdłuż `path`) każdego wierzchołka `path` do
    najbliższego punktu w `cage_points`, rzutowanego na najbliższy punkt na
    `path` (spec §3.4). float('inf') dla wszystkich gdy `cage_points` puste."""
    if len(path) < 2:
        return [float("inf")] * len(path)

    cumulative = [0.0]
    for i in range(1, len(path)):
        p1, p2 = path[i - 1], path[i]
        cumulative.append(cumulative[-1] + math.hypot(p2[0] - p1[0], p2[1] - p1[1]))

    if not cage_points:
        return [float("inf")] * len(path)

    line = LineString(path)
    cage_arc_positions = [line.project(Point(cp)) for cp in cage_points]

    result = []
    for i, point in enumerate(path):
        vertex_arc = cumulative[i]
        result.append(min(abs(vertex_arc - cage_arc) for cage_arc in cage_arc_positions))
    return result


def _find_matching_corner(
    zone_polygon: Polygon, candidates: list[tuple[float, float]]
) -> tuple[float, float] | None:
    """Zwraca pierwszy narożnik bbox strefy pokrywający się z jednym z
    `candidates` (wklęsłych wierzchołków oryginalnego obrysu), albo None."""
    if not candidates:
        return None
    minx, miny, maxx, maxy = zone_polygon.bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    for corner in corners:
        for cand in candidates:
            if abs(corner[0] - cand[0]) < 1e-6 and abs(corner[1] - cand[1]) < 1e-6:
                return corner
    return None


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
    centerline: list[CorridorCenterlineSegment] = field(default_factory=list)


@dataclass
class CorridorCenterlineSegment:
    """Jeden odcinek połączonej linii środkowej korytarza (spec §3.5)."""

    points: tuple[tuple[float, float], tuple[float, float]]
    loading: str  # "single" | "double"
    distance_start_m: float
    distance_end_m: float
    max_distance_m: float
    exceeds_max: bool


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

    # rectangle_decompose() rozwiązuje każdy wklęsły wierzchołek OBRYSU na
    # rzecz dwóch sąsiadujących prostokątnych stref — żadna pojedyncza strefa
    # nie ma już wierzchołka wklęsłego, więc _place_cage_by_mode's "3"/"auto"
    # (klatka w narożniku wklęsłym) nigdy by go nie znalazło. Wykrywamy
    # wklęsłe wierzchołki oryginalnego obrysu raz i dla każdej strefy
    # sprawdzamy, czy jeden z jej 4 narożników bbox się z którymś pokrywa —
    # jeśli tak, to jest to dokładnie ten sam punkt, tylko teraz jako zwykły
    # narożnik strefy (patrz _corner_cage_convex).
    original_concave = [(x, y) for _, x, y in concave_vertices_in_zone(footprint)]

    # Tylko jedna klatka na budynek (jak dawne generate_layout() — wiele
    # klatek to zakres optymalizatora/cage_mode, nie tego prostego
    # generatora, patrz services/optimizer.py's effective_cage_mode). Kolejność
    # prób: jeśli tryb "3"/"auto", najpierw strefy, których narożnik bbox
    # pokrywa się z oryginalnym wklęsłym wierzchołkiem (przywraca sens trybu
    # po rectangle_decompose), potem zwykła kolejność stref.
    cage_zone_order = list(range(len(zones)))
    if place_cage and cage_position in ("3", "auto") and original_concave:
        matching = [
            i for i in cage_zone_order if _find_matching_corner(zones[i].polygon, original_concave) is not None
        ]
        if matching:
            remaining = [i for i in cage_zone_order if i not in matching]
            cage_zone_order = matching + remaining

    local_cages: dict[int, Polygon] = {}
    circulation_geom = Polygon()
    cage_polygons: list[Polygon] = []

    if place_cage:
        for i in cage_zone_order:
            zone = zones[i]
            if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
                continue
            preferred_corner = _find_matching_corner(zone.polygon, original_concave)
            cage_polygon = _place_cage_by_mode(
                zone.polygon, cage_position, cage_size_m, preferred_corner=preferred_corner
            )
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                circulation_geom = unary_union([circulation_geom, cage_polygon])
                cage_polygons.append(cage_polygon)
                local_cages[i] = cage_polygon
                break

    remainder_parts: list[Polygon] = []

    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        local_cage = local_cages.get(i)
        zone_remaining = zone.polygon.difference(local_cage) if local_cage is not None else zone.polygon

        corridor = _build_corridor(zone_remaining, corridor_width_m, local_cage)
        if corridor.area > 0:
            circulation_geom = unary_union([circulation_geom, corridor])
            zone_remaining = zone_remaining.difference(corridor)

        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)

    remainder = unary_union(remainder_parts) if remainder_parts else Polygon()

    raw_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        local_cage = local_cages.get(i)
        seg = _corridor_centerline(zone.polygon, corridor_width_m, local_cage)
        if seg is not None:
            raw_segments.append(seg)

    centerline_path = _join_centerlines(raw_segments)
    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]
    arc_distances = _distances_along_centerline(centerline_path, cage_points)

    centerline: list[CorridorCenterlineSegment] = []
    for i in range(len(centerline_path) - 1):
        p1, p2 = centerline_path[i], centerline_path[i + 1]
        midpoint = Point((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        containing_zone = next(
            (z.polygon for z in zones if z.polygon.buffer(1e-6).contains(midpoint)),
            footprint,
        )
        loading = _classify_segment_loading(containing_zone, (p1, p2), corridor_width_m)
        max_dist = (
            CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M
            if loading == "double"
            else CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M
        )
        d_start, d_end = arc_distances[i], arc_distances[i + 1]
        centerline.append(
            CorridorCenterlineSegment(
                points=(p1, p2),
                loading=loading,
                distance_start_m=d_start,
                distance_end_m=d_end,
                max_distance_m=max_dist,
                exceeds_max=bool(max(d_start, d_end) > max_dist) if math.isfinite(max(d_start, d_end)) else False,
            )
        )

    return CirculationResult(
        zones=zones,
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
    )


def reshape_circulation(
    footprint: Polygon,
    centerline_points: list[tuple[tuple[float, float], tuple[float, float]]],
    corridor_width_m: float,
    cage_polygons: list[Polygon],
) -> CirculationResult:
    """Przelicza geometrię korytarza + klasyfikację/odległości segmentów po
    edycji linii środkowej przez użytkownika (spec §3.6). Buduje geometrię
    jako bufor (cap_style="flat") wokół każdego edytowanego odcinka, zamiast
    ponownie dzielić footprint na strefy -- edytowana linia już nie jest
    przywiązana do rectangle_decompose()'s stref."""
    half = corridor_width_m / 2.0
    buffered_parts = [
        LineString([p1, p2]).buffer(half, cap_style="flat")
        for p1, p2 in centerline_points
    ]
    circulation_geom = unary_union(buffered_parts).intersection(footprint)
    circulation_geom = unary_union([circulation_geom] + cage_polygons)

    remainder = footprint.difference(circulation_geom)

    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]

    centerline: list[CorridorCenterlineSegment] = []
    for p1, p2 in centerline_points:
        arc_distances = _distances_along_centerline([p1, p2], cage_points)
        loading = _classify_segment_loading(footprint, (p1, p2), corridor_width_m)
        max_dist = (
            CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M
            if loading == "double"
            else CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M
        )
        d_start, d_end = arc_distances[0], arc_distances[1]
        centerline.append(
            CorridorCenterlineSegment(
                points=(p1, p2),
                loading=loading,
                distance_start_m=d_start,
                distance_end_m=d_end,
                max_distance_m=max_dist,
                exceeds_max=(max(d_start, d_end) > max_dist) if math.isfinite(max(d_start, d_end)) else False,
            )
        )

    return CirculationResult(
        zones=[],
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
    )
