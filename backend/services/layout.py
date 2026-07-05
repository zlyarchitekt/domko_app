"""Generowanie układu kondygnacji: korytarz wzdłuż osi, klatka, podział na mieszkania."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Polygon
from shapely.ops import split, unary_union

from services.bsp import Zone

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


@dataclass
class LayoutInput:
    footprint: Polygon
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    place_cage: bool = True
    cage_size_m: float = 2.5
    cage_position: str = "auto"
    num_cages: int = 1
    manual_cages: list[list[tuple[float, float]]] = field(default_factory=list)
    manual_corridors: list[list[tuple[float, float]]] = field(default_factory=list)
    apartments: list[ApartmentSpec] = field(default_factory=list)
    local_law: str | None = None
    max_dist_single_m: float = 20.0
    """Edytowalny próg zielonej kropki ewakuacyjnej (spec 2026-07-04-
    evacuation-dots) -- passthrough do place_circulation()."""
    max_dist_multi_m: float = 40.0
    """Edytowalny próg szarej kropki ewakuacyjnej (>=2 klatki osiągalne)."""


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
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian (wall_geometry.net_polygon(polygon).area)
    -- spec 2026-07-04 wall-thickness §5.1. Domyślnie 0.0 dla ścieżek, które
    jej nie liczą (np. ręczna edycja mieszkania przed ponownym przeliczeniem)."""


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
    evacuation_dots: list = field(default_factory=list)
    """Passthrough z CirculationResult -- /layout/generate serializuje kropki
    tak samo jak /layout/circulation (dual-surface gotcha)."""


def generate_layout(input: LayoutInput) -> LayoutResult:
    """Generuje układ kondygnacji na podstawie obrysu.

    Wrapper nad dwoma jawnymi etapami (docs/superpowers/specs/2026-07-02-
    layout-engine-redesign-design.md): place_circulation (klatka+korytarz
    per prawie-prostokątna strefa) potem subdivide_units (dopasowanie
    programu do pozostałości). Zachowany dla optimizer.py i /layout/generate
    — oba etapy są też dostępne osobno (services.circulation.place_circulation,
    services.unit_mix.subdivide_units) dla nowych endpointów /layout/circulation
    i /layout/units."""
    from services.circulation import place_circulation
    from services.unit_mix import subdivide_units

    footprint = input.footprint
    footprint_area = footprint.area

    circulation = place_circulation(
        footprint,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
        place_cage=input.place_cage,
        cage_size_m=input.cage_size_m,
        cage_position=input.cage_position,
        num_cages=input.num_cages,
        manual_cages=input.manual_cages,
        manual_corridors=input.manual_corridors,
        max_dist_single_m=input.max_dist_single_m,
        max_dist_multi_m=input.max_dist_multi_m,
    )

    apartments, leftover = subdivide_units(circulation.remainder, input.apartments)

    usable_area = sum(a.polygon.area for a in apartments)
    circulation_area = (
        circulation.circulation_geometry.area if circulation.circulation_geometry is not None else 0.0
    )

    return LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint_area,
        circulation_area_m2=circulation_area,
        usable_area_m2=usable_area,
        apartments=apartments,
        leftover=leftover,
        zones=circulation.zones,
        building_azimuth_deg=_estimate_building_azimuth(footprint),
        circulation_geometry=circulation.circulation_geometry,
        cage_polygons=circulation.cage_polygons,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
        evacuation_dots=circulation.evacuation_dots,
    )


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
