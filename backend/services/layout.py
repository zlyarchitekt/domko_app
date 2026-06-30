"""Generowanie układu kondygnacji: korytarz wzdłuż osi, klatka, podział na mieszkania."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union

from services.bsp import Zone, bsp_zones


@dataclass
class ApartmentSpec:
    type: str
    min_area_m2: float
    target_count: int
    width_m: float | None = None
    depth_m: float | None = None


@dataclass
class LayoutInput:
    footprint: Polygon
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    place_cage: bool = True
    cage_size_m: float = 2.5
    apartments: list[ApartmentSpec] = field(default_factory=list)
    local_law: str | None = None


@dataclass
class ApartmentCell:
    id: str
    type: str
    polygon: Polygon


@dataclass
class LayoutResult:
    footprint_area_m2: float
    circulation_area_m2: float
    usable_area_m2: float
    apartments: list[ApartmentCell]
    leftover: Polygon | None
    zones: list[Zone]


def generate_layout(input: LayoutInput) -> LayoutResult:
    """Generuje układ kondygnacji na podstawie obrysu."""
    footprint = input.footprint
    footprint_area = footprint.area

    # 1. Podział BSP na strefy prostokątne
    zones = bsp_zones(footprint)

    apartments: list[ApartmentCell] = []
    circulation_geom = Polygon()
    leftover = Polygon()

    for zone in zones:
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        # 2. Klatka w pierwszym wklęsłym narożniku (opcjonalnie)
        if input.place_cage:
            cv = concave_vertices_in_zone(zone.polygon)
            if cv:
                cage_polygon = _build_cage(zone.polygon, cv[0], input.cage_size_m)
                if cage_polygon.area > 0:
                    circulation_geom = unary_union([circulation_geom, cage_polygon])
                    zone = Zone(name=zone.name, polygon=zone.polygon.difference(cage_polygon))

        # 3. Korytarz wzdłuż osi dłuższego boku strefy
        corridor = _build_corridor(zone.polygon, input.corridor_width_m)
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
        footprint_area_m2=footprint_area,
        circulation_area_m2=circulation_area,
        usable_area_m2=usable_area,
        apartments=apartments,
        leftover=leftover if leftover.area > 1e-6 else None,
        zones=zones,
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


def _build_corridor(polygon: Polygon, width: float) -> Polygon:
    """Buduje korytarz wzdłuż osi dłuższego boku prostokątnego poligonu."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return Polygon()
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        # korytarz poziomy wzdłuż osi X
        mid_y = (miny + maxy) / 2.0
        half = width / 2.0
        corridor = Polygon(
            [(minx, mid_y - half), (maxx, mid_y - half), (maxx, mid_y + half), (minx, mid_y + half)]
        )
    else:
        # korytarz pionowy wzdłuż osi Y
        mid_x = (minx + maxx) / 2.0
        half = width / 2.0
        corridor = Polygon(
            [(mid_x - half, miny), (mid_x + half, miny), (mid_x + half, maxy), (mid_x - half, maxy)]
        )

    return corridor.intersection(polygon)


def _slice_apartments(
    polygon: Polygon, specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Dzieli prostokątną strefę na mieszkania zgodnie z programem."""
    cells: list[ApartmentCell] = []
    if not specs or polygon.area < 1e-6:
        return cells, polygon

    bounds = polygon.bounds
    if len(bounds) != 4:
        return cells, polygon
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    remaining = polygon
    spec_index = 0
    created_total = 0

    while spec_index < len(specs) and remaining.area > 1e-6:
        spec = specs[spec_index]
        for _ in range(spec.target_count):
            if remaining.area < 1e-6:
                break
            target_width = spec.width_m or (spec.min_area_m2 / (spec.depth_m or h))
            target_depth = spec.depth_m or (spec.min_area_m2 / target_width)
            target_width = max(target_width, 2.0)
            target_depth = max(target_depth, 2.0)

            cell_poly, remaining = _cut_cell(remaining, target_width, target_depth, w >= h)
            if cell_poly is None or cell_poly.area < 1e-6:
                continue
            cells.append(
                ApartmentCell(
                    id=str(uuid.uuid4())[:8],
                    type=spec.type,
                    polygon=cell_poly,
                )
            )
            created_total += 1
        spec_index += 1

    return cells, remaining if remaining.area > 1e-6 else None


def _cut_cell(
    polygon: Polygon, width: float, depth: float, horizontal: bool
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
        cut_y = miny + depth
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

    first = geoms[0]
    rest = unary_union(geoms[1:])
    return first, rest
