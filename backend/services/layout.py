"""Generowanie układu kondygnacji: korytarz wzdłuż osi, klatka, podział na mieszkania."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union

from services.bsp import Zone, bsp_zones

_CARDINAL_DIRECTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def azimuth_to_cardinal(azimuth_deg: float | None) -> str | None:
    """Convert an azimuth in degrees (0=N, 90=E, 180=S, 270=W) to an 8-point label."""
    if azimuth_deg is None:
        return None
    normalized = azimuth_deg % 360.0
    index = int((normalized + 22.5) // 45.0) % 8
    return _CARDINAL_DIRECTIONS[index]


def sunlight_adjustment_factor(azimuth_deg: float | None) -> float:
    """Rough 0.3..1.0 factor for how favorable an azimuth is for direct sunlight
    in the northern hemisphere (south=180deg best, north=0/360deg worst).

    Used only as a fast surrogate score in services/optimizer.py — not a
    substitute for the real pvlib analysis in services/solar_analysis.py.
    """
    if azimuth_deg is None:
        return 0.5
    cos_val = math.cos(math.radians(azimuth_deg - 180.0))
    return 0.3 + 0.7 * (cos_val + 1.0) / 2.0


def _estimate_building_azimuth(footprint: Polygon) -> float | None:
    """Estimate the building's front-facade azimuth from the longest exterior edge.

    Returns the outward-normal azimuth of the longest edge as a coarse proxy
    for "front facade" orientation (0=N, 90=E, 180=S, 270=W).
    """
    if footprint is None or footprint.is_empty:
        return None
    coords = list(footprint.exterior.coords)[:-1]
    n = len(coords)
    if n < 2:
        return None
    # Bug fixed 2026-07-02: always adding +90 only gives the OUTWARD normal for
    # a counter-clockwise ring. Footprints from hand-drawn points, DXF import,
    # etc. are never normalized to a fixed winding, and the natural top-left ->
    # top-right -> bottom-right -> bottom-left click order most people use is
    # clockwise in this app's Y-up world space — that silently flipped every
    # azimuth/orientation by 180° (see services/solar_analysis.py's matching fix).
    normal_offset = 90.0 if footprint.exterior.is_ccw else -90.0
    best_len = -1.0
    best_azimuth: float | None = None
    for i in range(n):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % n]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length > best_len:
            best_len = length
            edge_az = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
            best_azimuth = (edge_az + normal_offset) % 360.0
    return best_azimuth


@dataclass
class ApartmentSpec:
    type: str
    min_area_m2: float
    target_count: int
    width_m: float | None = None
    depth_m: float | None = None


CAGE_POSITION_MODES = ("1a", "1b", "2", "3", "auto")
"""plan.md §4.3: 1a=elewacja front, 1b=elewacja dziedziniec/tył, 2=środek traktu,
3=narożnik, auto=narożnik wklęsły jeśli istnieje inaczej narożnik obrysu."""


@dataclass
class LayoutInput:
    footprint: Polygon
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    place_cage: bool = True
    cage_size_m: float = 2.5
    cage_position: str = "auto"
    apartments: list[ApartmentSpec] = field(default_factory=list)
    local_law: str | None = None


@dataclass
class ApartmentCell:
    id: str
    type: str
    polygon: Polygon
    area_tolerance_exceeded: bool = False
    """True if this cell's area deviates from its program spec's min_area_m2
    by more than the ±3% tolerance (Finch-inspired, see fit_program_to_
    rectangles in services/unit_mix.py). Default False for cells built by
    paths that don't track this (e.g. manual apartment edits)."""


@dataclass
class LayoutResult:
    footprint: Polygon
    footprint_area_m2: float
    circulation_area_m2: float
    usable_area_m2: float
    apartments: list[ApartmentCell]
    leftover: Polygon | None
    zones: list[Zone]
    building_azimuth_deg: float | None = None
    circulation_geometry: Polygon | None = None
    """Unified corridor+cage geometry, kept for adjacency/Dijkstra checks (F3-01/F3-03)."""
    cage_polygons: list[Polygon] = field(default_factory=list)
    """Individual staircase cage polygons found during generation (may be empty)."""
    corridor_width_m: float = 0.0
    """Corridor width used at generation time — exact by construction, not re-measured."""
    stair_width_m: float = 0.0
    """Stair/cage width parameter used at generation time — exact by construction."""


def generate_layout(input: LayoutInput) -> LayoutResult:
    """Generuje układ kondygnacji na podstawie obrysu."""
    footprint = input.footprint
    footprint_area = footprint.area

    # 1. Podział BSP na strefy prostokątne
    zones = bsp_zones(footprint)

    apartments: list[ApartmentCell] = []
    circulation_geom = Polygon()
    cage_polygons: list[Polygon] = []
    leftover = Polygon()

    for zone in zones:
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        # 2. Klatka wg trybu pozycji (plan.md §4.3: 1a/1b/2/3/auto).
        # Tylko jedna klatka na budynek (na razie — wiele klatek to zakres
        # optymalizatora/cage_mode, poza tym prostym generatorem), i nigdy w
        # strefie "-cage" wyciętej wewnętrznie przez bsp_zones() — to tylko
        local_cage = None
        # techniczny nibble (stały ~1m, niezależny od cage_size_m) używany do
        # rozbicia wklęsłego obrysu na strefy prostokątne, nie realna klatka.
        if input.place_cage and not cage_polygons and not zone.name.endswith("-cage"):
            cage_polygon = _place_cage_by_mode(zone.polygon, input.cage_position, input.cage_size_m)
            # Odrzuć klatkę, która pochłonęłaby (prawie) całą strefę — zbyt mała
            # strefa względem cage_size_m nie ma miejsca na korytarz/mieszkania,
            # lepiej nie stawiać klatki niż zwrócić pusty/zdegenerowany poligon.
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                circulation_geom = unary_union([circulation_geom, cage_polygon])
                cage_polygons.append(cage_polygon)
                zone = Zone(name=zone.name, polygon=zone.polygon.difference(cage_polygon))
                local_cage = cage_polygon

        # 3. Korytarz wzdłuż osi dłuższego boku strefy
        corridor = _build_corridor(zone.polygon, input.corridor_width_m, local_cage)
        if corridor.area > 0:
            circulation_geom = unary_union([circulation_geom, corridor])
            zone = Zone(name=zone.name, polygon=zone.polygon.difference(corridor))

        # 4. Podział pozostałej strefy na mieszkania
        zone_apartments, zone_leftover = _slice_apartments(
            zone.polygon, input.apartments
        )
        apartments.extend(zone_apartments)
        if zone_leftover and zone_leftover.area > 1e-6:
            leftover = unary_union([leftover, zone_leftover])

    usable_area = sum(a.polygon.area for a in apartments)
    circulation_area = circulation_geom.area if circulation_geom.is_valid else 0.0

    return LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint_area,
        circulation_area_m2=circulation_area,
        usable_area_m2=usable_area,
        apartments=apartments,
        leftover=leftover if leftover.area > 1e-6 else None,
        zones=zones,
        building_azimuth_deg=_estimate_building_azimuth(footprint),
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
    )


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
    # normalna prostopadła do krawędzi, skierowana w stronę środka poligonu
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
    """Buduje korytarz wzdłuż osi dłuższego boku prostokątnego poligonu,
    uwzględniając wyrównanie do pozycji klatki schodowej (F2-04)."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return Polygon()
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        # korytarz poziomy wzdłuż osi X
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
        # korytarz pionowy wzdłuż osi Y
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


MIN_CELL_DIMENSION_M = 2.0


def _polygon_parts(geom: Polygon | None) -> list[Polygon]:
    """Rozbija (Multi)Polygon na listę pojedynczych, niepustych, dodatnio-powierzchniowych części."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom] if geom.area > 1e-6 else []
    if hasattr(geom, "geoms"):
        return [g for g in geom.geoms if g.geom_type == "Polygon" and g.area > 1e-6]
    return []


def _slice_apartments(
    polygon: Polygon, specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Dzieli strefę (także rozłączną — np. obie strony korytarza dwustronnego)
    na mieszkania zgodnie z programem (sekwencyjna gilotyna per część).

    Dwa usprawnienia względem poprzedniej wersji (F2-04):
    1. **Rozłączne części.** Korytarz najczęściej dzieli strefę na dwie
       rozłączne części (`MultiPolygon`) — front i tył. Poprzednia wersja
       liczyła głębokość cięcia z bounding-boxa całej `MultiPolygon` (czyli
       łącznie z przerwą na korytarz!), co dawało kompletnie błędne
       powierzchnie. Tu każda część jest cięta osobno, z własną, prawdziwą
       głębokością, na przemian (round-robin) między częściami — program
       jest sprawiedliwie rozłożony na obie strony, zamiast wyczerpać jedną
       stronę przed drugą.
    2. **Dopasowanie do programu.** Wymiar cięcia jest wyprowadzany wyłącznie
       z `min_area_m2 / rzeczywista_głębokość_części` — `min_area_m2` jest
       rozstrzygający, bo to jest program, który mamy dopasować.
       `width_m`/`depth_m` (opcjonalne podpowiedzi z `ApartmentSpec`) NIE są
       tu używane: w tym 1D-gilotynowym modelu cięcia (jeden wymiar na raz)
       nie da się jednocześnie wymusić i szerokości, i głębokości bez
       złamania dopasowania powierzchni — gdy oba są podane i się nie
       zgadzają z rzeczywistą geometrią strefy, priorytet ma trafienie w
       `min_area_m2`. Pełne poszanowanie jawnego `width_m` (np. z presetu
       typologii — takt_m) wymagałoby prawdziwego 2D-podziału na wiele
       rzędów, co jest kolejnym krokiem poza zakresem tego zadania.
    """
    cells: list[ApartmentCell] = []
    parts = _polygon_parts(polygon)
    if not specs or not parts:
        leftover = polygon if polygon is not None and not polygon.is_empty and polygon.area > 1e-6 else None
        return cells, leftover

    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)

    remaining_parts: list[Polygon] = parts
    retired: list[Polygon] = []
    idx = 0

    while queue and remaining_parts:
        idx %= len(remaining_parts)
        part = remaining_parts[idx]
        spec = queue[0]

        bounds = part.bounds
        if len(bounds) != 4:
            retired.append(remaining_parts.pop(idx))
            continue
        minx, miny, maxx, maxy = bounds
        w = maxx - minx
        h = maxy - miny
        horizontal = w >= h
        available_depth = h if horizontal else w
        if available_depth < 1e-6:
            retired.append(remaining_parts.pop(idx))
            continue

        # min_area_m2 jest rozstrzygający (to jest program, który mamy dopasować) —
        # width_m/depth_m to tylko opcjonalne podpowiedzi z API, nie są tu użyte,
        # bo w tym 1D-gilotynowym modelu nadpisanie szerokości ponad wymóg
        # powierzchni psułoby dopasowanie (patrz docstring funkcji).
        fitted_size = spec.min_area_m2 / available_depth
        cut_size = max(fitted_size, MIN_CELL_DIMENSION_M)

        cell_poly, rest = _cut_cell(part, cut_size, horizontal)
        if cell_poly is None or cell_poly.area < 1e-6:
            # Ta część nie mieści już kolejnej komórki — wycofaj z rotacji.
            retired.append(remaining_parts.pop(idx))
            continue

        cells.append(ApartmentCell(id=str(uuid.uuid4())[:8], type=spec.type, polygon=cell_poly))
        queue.pop(0)

        rest_parts = _polygon_parts(rest)
        if rest_parts:
            remaining_parts[idx] = rest_parts[0]
            remaining_parts.extend(rest_parts[1:])
            idx += 1
        else:
            remaining_parts.pop(idx)

    leftover_geoms = retired + [p for p in remaining_parts if p.area > 1e-6]
    leftover = unary_union(leftover_geoms) if leftover_geoms else None
    return cells, leftover if leftover is not None and not leftover.is_empty and leftover.area > 1e-6 else None


def _cut_cell(
    polygon: Polygon, width: float, horizontal: bool
) -> tuple[Polygon | None, Polygon]:
    """Wycina jedno mieszkanie z poligonu wzdłuż wybranej osi."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return None, polygon
    minx, miny, maxx, maxy = bounds

    if horizontal:
        cut_x = minx + width
        if cut_x >= maxx:
            return None, polygon
        cutter = LineString([(cut_x, miny - 1), (cut_x, maxy + 1)])
    else:
        # Bug fixed 2026-07-02: this used `depth` (the perpendicular span, i.e.
        # the zone's own width) instead of `width` (the computed slice
        # thickness `cut_size`) for the vertical-cut position. Every apartment
        # sliced from a taller-than-wide zone came out as a `w x w` square
        # instead of `w x cut_size`, silently ignoring min_area_m2 — verified:
        # a 6x30m zone with a 50m2 spec produced 36.0m2 (=6x6) cells, while the
        # horizontal (w>=h) branch, which already used `width` correctly, gave
        # the correct 50.0m2 for the same spec on a 30x6m zone.
        cut_y = miny + width
        if cut_y >= maxy:
            return None, polygon
        cutter = LineString([(minx - 1, cut_y), (maxx + 1, cut_y)])

    try:
        split_result = split(polygon, cutter)
    except Exception:
        return None, polygon

    geoms = [g for g in split_result.geoms if g.area > 1e-6]
    if len(geoms) < 2:
        return None, polygon

    # shapely.split() nie gwarantuje kolejności części — wybierz jawnie wg
    # pozycji centroidu względem linii cięcia, żeby `first` zawsze był nowo
    # wyciętą komórką (od strony minx/miny), a nie przypadkowo większą resztą.
    if horizontal:
        near = [g for g in geoms if g.centroid.x <= cut_x]
        far = [g for g in geoms if g.centroid.x > cut_x]
    else:
        near = [g for g in geoms if g.centroid.y <= cut_y]
        far = [g for g in geoms if g.centroid.y > cut_y]

    if not near or not far:
        return None, polygon

    first = unary_union(near) if len(near) > 1 else near[0]
    rest = unary_union(far) if len(far) > 1 else far[0]
    return first, rest
