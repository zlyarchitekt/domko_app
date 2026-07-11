import json
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon
from shapely.geometry import shape as _shape

from services.circulation import (
    CAGE_POSITION_MODES,
    CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M,
    CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M,
    place_circulation,
)
from services.layout import ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.unit_mix import ProgramShare, UnitWeights, iterate_units, subdivide_units
from services.wall_geometry import exterior_wall_band, interior_wall_bands, net_polygon
from services.wt_validation import WTValidationResult, validate_layout_wt

router = APIRouter()


class ApartmentProgram(BaseModel):
    type: str = Field(..., min_length=1)
    min_area_m2: float = Field(..., gt=0)
    target_count: int = Field(..., ge=0)
    width_m: float | None = Field(None, gt=0)
    depth_m: float | None = Field(None, gt=0)
    percentage: float = Field(default=0.0, ge=0)
    area_min_m2: float = Field(default=0.0, ge=0)
    area_max_m2: float = Field(default=0.0, ge=0)
    min_facade_m: float = Field(default=3.0, ge=0)
    """Min. styk typu ze ścianą zewnętrzną [m] -- komponent daylight."""


class UnitWeightsInput(BaseModel):
    """7 wag scoringu (spec §4) -- defaulty jak services.unit_mix.UnitWeights."""

    size: float = Field(default=0.8, ge=0, le=1)
    mix: float = Field(default=0.6, ge=0, le=1)
    grid: float = Field(default=0.3, ge=0, le=1)
    shape: float = Field(default=0.5, ge=0, le=1)
    daylight: float = Field(default=0.7, ge=0, le=1)
    squareness: float = Field(default=0.5, ge=0, le=1)
    adjacency: float = Field(default=1.0, ge=0, le=1)


class IterationMetaResult(BaseModel):
    seed: int
    score: float
    units_count: int
    components: dict[str, float] = {}
    apartments: list["ApartmentResult"] = []
    wall_bands: list[dict] = []


class CageWeightsInput(BaseModel):
    egress: float = Field(default=1.0, ge=0, le=1)
    count: float = Field(default=0.5, ge=0, le=1)
    corners: float = Field(default=0.3, ge=0, le=1)
    ends: float = Field(default=0.3, ge=0, le=1)
    spread: float = Field(default=0.5, ge=0, le=1)


class CageIterationMetaResult(BaseModel):
    seed: int
    score: float
    cages_count: int
    components: dict[str, float] = {}
    cage_geometries: list[dict] = []
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Jak CirculationResponse.circulation_geometry_net, per iteracja --
    spec 2026-07-06 corridor-net-shrink §1."""
    centerline: list["CenterlineSegmentResult"] = []
    evacuation_dots: list["EvacuationDotResult"] = []
    remainder: dict | None = None
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) TEJ konkretnej
    iteracji -- puste gdy manual_corridors nie podano przy serializacji
    (np. z /layout/generate, który nie ma warnings na top-levelu),
    naprawa Finding 2 (Etap 5 review)."""


class CirculationSpec(BaseModel):
    corridor_width_m: float = Field(default=1.5, gt=0)
    stair_width_m: float = Field(default=1.2, gt=0)
    place_cage: bool = Field(default=True)
    cage_size_m: float = Field(default=2.5, gt=0)
    cage_position: str = Field(
        default="auto",
        description=f"Tryb pozycji klatki wg plan.md §4.3: {CAGE_POSITION_MODES}",
    )
    num_cages: int = Field(default=1, ge=1)
    manual_cages: list[list[list[float]]] = Field(default_factory=list)
    """Ringi ręcznie narysowanych klatek [[x,y],...] bez duplikatu 1. punktu
    (spec 2026-07-04 manual-circulation-drawing §3)."""
    manual_corridors: list[list[list[float]]] = Field(default_factory=list)
    """Łamane osi ręcznie narysowanych korytarzy [[x,y],...]."""
    max_dist_single_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M, gt=0)
    """Edytowalny próg zielonej kropki (heurystyka usera, nie § WT)."""
    max_dist_multi_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M, gt=0)
    """Edytowalny próg szarej kropki (>=2 klatki osiągalne)."""
    cage_iterations: int = Field(default=0, ge=0, le=50)
    """0 = klasyczny auto-placement; >0 = tryb iteracyjny (spec 2026-07-04-
    cage-placement-iterations §4)."""
    cage_weights: CageWeightsInput = Field(default_factory=CageWeightsInput)


class LayoutGenerateRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    local_law: str | None = Field(default=None)
    iterations: int = Field(default=10, ge=1, le=50)
    weights: UnitWeightsInput = Field(default_factory=UnitWeightsInput)


class ApartmentResult(BaseModel):
    id: str
    type: str
    area_m2: float
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian -- spec 2026-07-04 wall-thickness §5.2."""
    geometry: dict
    net_geometry: dict | None = None
    """Poligon netto (w świetle ścian) do wypełnienia strefy mieszkania na
    froncie -- spec 2026-07-06 apartment-type-colors §3.2. None gdy netto
    puste (komórka zbyt mała) lub nie jest prostym Polygonem; front spada
    wtedy na `geometry` (surowy, na osiach)."""


class WTRuleResult(BaseModel):
    code: str
    description: str
    passed: bool
    detail: str


class WTResult(BaseModel):
    passed: bool
    score: int
    rules: list[WTRuleResult]
    issues: list[str]


class EvacuationDotResult(BaseModel):
    x: float
    y: float
    status: str
    distance_m: float | None = None


class CenterlineSegmentResult(BaseModel):
    points: list[list[float]]
    loading: str
    distance_start_m: float | None
    distance_end_m: float | None
    max_distance_m: float
    exceeds_max: bool


class LayoutGenerateResponse(BaseModel):
    footprint_area_m2: float
    circulation_area_m2: float
    usable_area_m2: float
    apartments: list[ApartmentResult]
    leftover: dict | None = None
    wt_validation: WTResult
    zones: list[dict]
    circulation_parts: list[dict] = []
    """Corridor+cage geometry, decomposed into individual Polygon parts (may be
    a MultiPolygon internally — e.g. both sides of a double-loaded corridor),
    for frontend rendering (F2-07)."""
    circulation_parts_net: list[dict] = []
    """circulation_parts w świetle ścian (net_polygon na całej geometrii przed
    dekompozycją) -- spec 2026-07-06 corridor-net-shrink §1. Front: gdy
    niepusta, renderuje TĘ listę zamiast circulation_parts."""
    cage_geometries: list[dict] = []
    """Individual staircase cage polygons (may be empty), for frontend rendering (F2-07)."""
    wall_bands: list[dict] = []
    """Pasy ścian (zewnętrzne + wewnętrzne), GeoJSON, do narysowania na
    płótnie -- spec 2026-07-04 wall-thickness §5.2."""
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots
    (dual-surface: musi być na wszystkich trzech odpowiedziach)."""
    cage_iterations: list[CageIterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego (puste w trybie klasycznym)
    -- spec 2026-07-04-cage-placement-iterations §4 (dual-surface z
    /layout/circulation's CirculationResponse)."""
    cage_best_seed: int = 0
    """Seed zwycięskiej iteracji trybu iteracyjnego (0 w trybie klasycznym)."""
    derived_total_units: int = 0
    """Liczba mieszkań wyliczona ze struktury % i powierzchni netto
    (spec 2026-07-04-apartment-division-iterations §1, dual-surface z
    /layout/units)."""
    net_remainder_m2: float = 0.0
    """Powierzchnia netto pozostałości po komunikacji, wejście do
    derive_total_units (spec §1)."""
    iterations: list[IterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego podziału na mieszkania
    (puste, gdy request nie podał program_shares -- klasyczny subdivide_units),
    spec §4 (dual-surface z /layout/units)."""
    best_seed: int = 0
    """Seed zwycięskiej iteracji trybu iteracyjnego podziału na mieszkania
    (0 w trybie klasycznym)."""


@router.post("/generate", response_model=LayoutGenerateResponse)
def generate_layout_endpoint(request: LayoutGenerateRequest):
    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    circulation = request.circulation
    if circulation.cage_position not in CAGE_POSITION_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cage_position '{circulation.cage_position}'. Valid: {CAGE_POSITION_MODES}",
        )

    specs = [
        ApartmentSpec(
            type=a.type,
            min_area_m2=a.min_area_m2,
            target_count=a.target_count,
            width_m=a.width_m,
            depth_m=a.depth_m,
        )
        for a in request.apartments
    ]

    from services.cage_placement import CageWeights

    layout_input = LayoutInput(
        footprint=footprint,
        corridor_width_m=circulation.corridor_width_m,
        stair_width_m=circulation.stair_width_m,
        place_cage=circulation.place_cage,
        cage_size_m=circulation.cage_size_m,
        cage_position=circulation.cage_position,
        num_cages=circulation.num_cages,
        manual_cages=[[(p[0], p[1]) for p in ring] for ring in circulation.manual_cages],
        manual_corridors=[[(p[0], p[1]) for p in path] for path in circulation.manual_corridors],
        apartments=specs,
        local_law=request.local_law,
        max_dist_single_m=circulation.max_dist_single_m,
        max_dist_multi_m=circulation.max_dist_multi_m,
        cage_iterations=circulation.cage_iterations,
        cage_weights=(
            CageWeights(**circulation.cage_weights.model_dump())
            if circulation.cage_iterations > 0
            else None
        ),
        iterations=request.iterations,
        unit_weights=UnitWeights(**request.weights.model_dump()),
        program_shares=[
            ProgramShare(
                type=a.type, percentage=a.percentage,
                area_min_m2=a.area_min_m2 or a.min_area_m2,
                area_max_m2=a.area_max_m2 or a.min_area_m2,
                min_facade_m=a.min_facade_m,
            )
            for a in request.apartments
            if a.percentage > 0
        ],
    )

    try:
        layout = generate_layout(layout_input)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout generation failed: {exc}")

    wt = validate_layout_wt(layout, request.local_law)

    return layout_result_to_response(layout, wt)


def layout_result_to_response(layout: LayoutResult, wt: WTValidationResult) -> LayoutGenerateResponse:
    """Serialize a `LayoutResult` (+ its WT validation) into the API response shape.

    Shared with `api/v1/endpoints/optimizer.py` so each optimizer variant's `layout`
    (which is a full `LayoutResult`, same as a plain `/layout/generate` call) can be
    exposed in the exact shape the frontend already knows how to render — otherwise
    "apply this variant" has no geometry to hand to the canvas.
    """
    apartments_out = [
        ApartmentResult(
            id=a.id,
            type=a.type,
            area_m2=a.polygon.area,
            net_area_m2=a.net_area_m2,
            geometry=json.loads(json.dumps(a.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(a.polygon),
        )
        for a in layout.apartments
    ]

    wall_cells = [a.polygon for a in layout.apartments]
    if layout.circulation_geometry is not None:
        wall_cells.append(layout.circulation_geometry)
    wall_bands_out = _compute_wall_bands(layout.footprint, wall_cells, layout.leftover)

    return LayoutGenerateResponse(
        footprint_area_m2=layout.footprint_area_m2,
        circulation_area_m2=layout.circulation_area_m2,
        usable_area_m2=layout.usable_area_m2,
        apartments=apartments_out,
        leftover=json.loads(json.dumps(layout.leftover.__geo_interface__)) if layout.leftover else None,
        wt_validation=WTResult(
            passed=wt.passed,
            score=wt.score,
            rules=[
                WTRuleResult(code=r.code, description=r.description, passed=r.passed, detail=r.detail)
                for r in wt.rules
            ],
            issues=wt.issues,
        ),
        zones=[
            {"name": z.name, "geometry": json.loads(json.dumps(z.polygon.__geo_interface__))}
            for z in layout.zones
        ],
        circulation_parts=_decompose_to_polygons(layout.circulation_geometry),
        circulation_parts_net=(
            _decompose_to_polygons(net_polygon(layout.circulation_geometry))
            if layout.circulation_geometry is not None else []
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in layout.cage_polygons],
        wall_bands=wall_bands_out,
        evacuation_dots=_serialize_dots(layout.evacuation_dots),
        cage_iterations=[_serialize_cage_iteration(m) for m in layout.cage_iteration_metas],
        cage_best_seed=layout.cage_best_seed,
        derived_total_units=layout.derived_total_units,
        net_remainder_m2=layout.net_remainder_m2,
        iterations=[
            _serialize_unit_iteration(m, layout.footprint, layout.circulation_geometry)
            for m in layout.iteration_metas
        ],
        best_seed=layout.best_seed,
    )


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords: list[tuple[float, float]] = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def _decompose_to_polygons(geom: Polygon | None) -> list[dict]:
    """Split a (Multi)Polygon into a JSON-serializable list of Polygon geo-interfaces."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [json.loads(json.dumps(geom.__geo_interface__))]
    if hasattr(geom, "geoms"):
        return [
            json.loads(json.dumps(part.__geo_interface__))
            for part in geom.geoms
            if part.geom_type == "Polygon"
        ]
    return []


def _compute_wall_bands(
    footprint: Polygon, wall_cells: list[Polygon], leftover: Polygon | None
) -> list[dict]:
    """Pasy ścian (zewn.+wewn.) dla danego zestawu komórek -- wspólne dla
    /layout/generate, /layout/units (wynik główny) i /layout/units (wynik
    każdej iteracji, Task 2). `wall_cells` to apartments+circulation_geometry
    (jeśli istnieje), BEZ leftover (patrz interior_wall_bands docstring).

    Jeśli `leftover` jest podany (niepusty), jest odejmowany z powrotem od
    interior_wall_bands jako RAW polygon (nie net_polygon(leftover)) --
    interior_wall_bands() traktuje "niepokryte żadną realną komórką" jako
    "ściana", a leftover to legalnie nieprzydzielona przestrzeń, nie ściana
    (spec 2026-07-04-wall-thickness-design.md §3: "bez ściany dookoła").
    Odjęcie surowego leftover jest bezpieczne, bo leftover jest zawsze
    rozłączny z każdą realną komórką (silnik kafelkuje przestrzeń bez luk) --
    nie może więc wymazać prawdziwej ściany międzykomórkowej (patrz commit
    10341e3 i test_wall_bands_excludes_thin_leftover_sliver)."""
    wall_geoms = [exterior_wall_band(footprint)]
    if wall_cells:
        interior_bands = interior_wall_bands(footprint, wall_cells)
        if leftover is not None and not leftover.is_empty:
            interior_bands = interior_bands.difference(leftover)
        wall_geoms.append(interior_bands)
    return [g for geom in wall_geoms for g in _decompose_to_polygons(geom)]


def _finite_or_none(x: float) -> float | None:
    """Odległości wzdłuż centerline są float('inf') gdy nie ma klatki
    schodowej (patrz services.circulation._distances_along_centerline) --
    Starlette's default JSONResponse używa allow_nan=False i rzuca 500 przy
    próbie serializacji Infinity. None jest bezpieczne: frontend czyta tylko
    `exceeds_max` do kolorowania, nie te pola bezpośrednio (final-review
    Finding 1, 2026-07-03)."""
    return x if math.isfinite(x) else None


def _serialize_centerline(segments) -> list["CenterlineSegmentResult"]:
    return [
        CenterlineSegmentResult(
            points=[list(seg.points[0]), list(seg.points[1])],
            loading=seg.loading,
            distance_start_m=_finite_or_none(seg.distance_start_m),
            distance_end_m=_finite_or_none(seg.distance_end_m),
            max_distance_m=seg.max_distance_m,
            exceeds_max=seg.exceeds_max,
        )
        for seg in segments
    ]


def _serialize_dots(dots) -> list["EvacuationDotResult"]:
    return [
        EvacuationDotResult(
            x=d.x, y=d.y, status=d.status,
            distance_m=_finite_or_none(d.distance_m) if d.distance_m is not None else None,
        )
        for d in dots
    ]


def _compute_manual_corridor_warnings(manual_corridors, cage_polygons) -> list[str]:
    """Miękkie ostrzeżenia gdy ręcznie narysowany korytarz nie styka się z
    żadną klatką -- wydzielone z `place_circulation_endpoint` (Finding 2,
    Etap 5 review) żeby dało się policzyć je PER ITERACJA cage_iterations,
    a nie tylko raz przeciwko zwycięskiemu `result.cage_polygons`."""
    warnings: list[str] = []
    for i, path in enumerate(manual_corridors):
        if len(path) < 2:
            continue
        axis = LineString([(p[0], p[1]) for p in path])
        touches_any = any(axis.distance(c) <= 0.25 for c in cage_polygons)
        if not touches_any:
            warnings.append(f"Korytarz {i + 1} nie styka się z żadną klatką")
    return warnings


def _serialize_cage_iteration(m, manual_corridors: list | None = None) -> "CageIterationMetaResult":
    return CageIterationMetaResult(
        seed=m.seed, score=m.score, cages_count=m.cages_count, components=m.components,
        cage_geometries=(
            [json.loads(json.dumps(c.__geo_interface__)) for c in m.result.cage_polygons]
            if m.result is not None else []
        ),
        circulation_geometry=(
            json.loads(json.dumps(m.result.circulation_geometry.__geo_interface__))
            if m.result is not None and m.result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(m.result.circulation_geometry)
            if m.result is not None and m.result.circulation_geometry is not None else None
        ),
        centerline=_serialize_centerline(m.result.centerline) if m.result is not None else [],
        evacuation_dots=_serialize_dots(m.result.evacuation_dots) if m.result is not None else [],
        remainder=(
            json.loads(json.dumps(m.result.remainder.__geo_interface__))
            if m.result is not None else None
        ),
        warnings=(
            _compute_manual_corridor_warnings(manual_corridors, m.result.cage_polygons)
            if manual_corridors is not None and m.result is not None else []
        ),
    )


def _net_geometry_json(polygon: Polygon) -> dict | None:
    """GeoJSON poligonu netto (w świetle ścian) -- spec 2026-07-06
    apartment-type-colors §3.2. None gdy netto puste albo nie jest prostym
    Polygonem (ringToPoints na froncie czyta coordinates[0], więc
    MultiPolygon odpada -> front spada na geometrię surową)."""
    net = net_polygon(polygon)
    if net.is_empty or net.geom_type != "Polygon":
        return None
    return json.loads(json.dumps(net.__geo_interface__))


def _serialize_unit_iteration(m, footprint: Polygon | None, circulation_geometry) -> "IterationMetaResult":
    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area, net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(c.polygon),
        )
        for c in m.cells
    ]
    wall_bands_out: list[dict] = []
    if footprint is not None:
        wall_cells = [c.polygon for c in m.cells]
        if circulation_geometry is not None:
            wall_cells.append(circulation_geometry)
        # iterate_units gwarantuje zero resztek (spec Etap 4 §3) -- leftover
        # zawsze None dla każdej iteracji tego silnika, nie tylko najlepszej.
        wall_bands_out = _compute_wall_bands(footprint, wall_cells, None)
    return IterationMetaResult(
        seed=m.seed, score=m.score, units_count=m.units_count, components=m.components,
        apartments=apartments_out, wall_bands=wall_bands_out,
    )


class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Poligon korytarza+klatki w świetle ścian (wall_geometry.net_polygon) --
    spec 2026-07-06 corridor-net-shrink §1. None gdy netto puste albo nie jest
    prostym Polygonem; front spada wtedy na `circulation_geometry` (surowy)."""
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) -- spec §4."""
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""
    cage_iterations: list[CageIterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego (puste w trybie klasycznym,
    cage_iterations=0) -- spec 2026-07-04-cage-placement-iterations §4."""
    cage_best_seed: int = 0
    """Seed zwycięskiej iteracji (0 w trybie klasycznym)."""


@router.post("/circulation", response_model=CirculationResponse)
def place_circulation_endpoint(request: LayoutGenerateRequest):
    """Etap 1 osobno (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md)."""
    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    circulation = request.circulation
    if circulation.cage_position not in CAGE_POSITION_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cage_position '{circulation.cage_position}'. Valid: {CAGE_POSITION_MODES}",
        )

    manual_cages = [[(p[0], p[1]) for p in ring] for ring in circulation.manual_cages]
    manual_corridors = [[(p[0], p[1]) for p in path] for path in circulation.manual_corridors]

    cage_iteration_metas: list = []
    cage_best_seed = 0
    if circulation.cage_iterations > 0 and circulation.place_cage:
        from services.cage_placement import CageWeights, iterate_cage_placement
        from services.circulation import _merge_manual_elements

        try:
            result, cage_iteration_metas, cage_best_seed = iterate_cage_placement(
                footprint,
                corridor_width_m=circulation.corridor_width_m,
                num_cages=circulation.num_cages,
                weights=CageWeights(**circulation.cage_weights.model_dump()),
                iterations=circulation.cage_iterations,
                max_dist_single_m=circulation.max_dist_single_m,
                max_dist_multi_m=circulation.max_dist_multi_m,
            )
            result = _merge_manual_elements(
                result, footprint, circulation.corridor_width_m,
                manual_cages, manual_corridors,
                circulation.max_dist_single_m, circulation.max_dist_multi_m,
            )
            # Finding 1 (Etap 5 review): the winning iteration's `.result` IS
            # `result` (same object, aliased -- see iterate_cage_placement's
            # `best = (score, result)` / `metas.append(..., result=result)`),
            # so it's already merged above. Every OTHER iteration's `.result`
            # is a distinct CirculationResult from its own seed and never got
            # manual elements merged in -- without this, clicking a
            # non-winning cage iteration silently drops manually-drawn
            # cages/corridors from its serialized geometry.
            for m in cage_iteration_metas:
                if m.result is result:
                    continue
                if m.result is not None:
                    m.result = _merge_manual_elements(
                        m.result, footprint, circulation.corridor_width_m,
                        manual_cages, manual_corridors,
                        circulation.max_dist_single_m, circulation.max_dist_multi_m,
                    )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    else:
        try:
            result = place_circulation(
                footprint,
                corridor_width_m=circulation.corridor_width_m,
                stair_width_m=circulation.stair_width_m,
                place_cage=circulation.place_cage,
                cage_size_m=circulation.cage_size_m,
                cage_position=circulation.cage_position,
                num_cages=circulation.num_cages,
                manual_cages=manual_cages,
                manual_corridors=manual_corridors,
                max_dist_single_m=circulation.max_dist_single_m,
                max_dist_multi_m=circulation.max_dist_multi_m,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    warnings = _compute_manual_corridor_warnings(circulation.manual_corridors, result.cage_polygons)

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        warnings=warnings,
        evacuation_dots=_serialize_dots(result.evacuation_dots),
        cage_iterations=[
            _serialize_cage_iteration(m, circulation.manual_corridors) for m in cage_iteration_metas
        ],
        cage_best_seed=cage_best_seed,
    )


class UnitsRequest(BaseModel):
    remainder: dict
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    footprint: list[list[float]] | None = None
    """Opcjonalny -- bez niego endpoint dzieli remainder tak jak wcześniej,
    ale nie może policzyć wall_bands (potrzebuje pełnego obrysu, nie tylko
    pozostałej po komunikacji części). Podawany przez frontend od naprawy
    braku wall_bands w przepływie Etap 1/2 (2026-07-04)."""
    circulation_geometry: dict | None = None
    """Geometria korytarza+klatki z /layout/circulation -- wliczana do
    wall_cells tak samo jak layout.circulation_geometry w
    layout_result_to_response(), żeby ściana między mieszkaniem a
    korytarzem/klatką też się narysowała."""
    iterations: int = Field(default=10, ge=1, le=50)
    weights: UnitWeightsInput = Field(default_factory=UnitWeightsInput)


class UnitsResponse(BaseModel):
    apartments: list[ApartmentResult]
    leftover: dict | None = None
    wall_bands: list[dict] = []
    """Pasy ścian (zewn.+wewn.), GeoJSON -- patrz UnitsRequest.footprint.
    Puste, gdy request nie podał footprint (nie da się policzyć bez pełnego
    obrysu)."""
    derived_total_units: int = 0
    """Liczba mieszkań wyliczona ze struktury % i powierzchni netto remainder
    (spec 2026-07-04-apartment-division-iterations §1)."""
    net_remainder_m2: float = 0.0
    """Powierzchnia netto pozostałości po komunikacji, wejście do
    derive_total_units (spec §1)."""
    iterations: list[IterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego podziału na mieszkania,
    spec §4 (dual-surface z /layout/generate)."""
    best_seed: int = 0
    """Seed zwycięskiej iteracji trybu iteracyjnego."""


@router.post("/units", response_model=UnitsResponse)
def subdivide_units_endpoint(request: UnitsRequest):
    """Etap 2 osobno (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md)."""
    try:
        remainder = _shape(request.remainder)
        if remainder.is_empty or not remainder.is_valid:
            raise ValueError("remainder geometry is empty or invalid")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid remainder geometry: {exc}")

    # Footprint/circulation_geometry parsed up-front now (used to be parsed
    # lazily inside the wall_bands block below) -- iterate_units() needs both
    # for its daylight (footprint) and adjacency (circulation_geometry)
    # scoring components (spec 2026-07-04-apartment-division-iterations §4).
    footprint = None
    if request.footprint is not None:
        try:
            footprint = _points_to_polygon(request.footprint)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    circulation_geometry = None
    if request.circulation_geometry is not None:
        try:
            circulation_geometry = _shape(request.circulation_geometry)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid circulation_geometry: {exc}")

    # Same gate as generate_layout_endpoint's `program_shares` (dual-surface):
    # only opt into the %-structure iterative engine when at least one
    # apartment actually carries a percentage -- otherwise fall back to the
    # classic target_count-based subdivide_units(), so callers still using
    # the pre-Etap-4 contract (min_area_m2 + target_count, no percentage)
    # keep getting 200s instead of a "wszystkie udziały procentowe są
    # zerowe" 422 from derive_total_units (percentage defaults to 0.0).
    shares = [
        ProgramShare(
            type=a.type,
            percentage=a.percentage,
            area_min_m2=a.area_min_m2 or a.min_area_m2,
            area_max_m2=a.area_max_m2 or a.min_area_m2,
            min_facade_m=a.min_facade_m,
        )
        for a in request.apartments
        if a.percentage > 0
    ]

    if shares:
        weights = UnitWeights(**request.weights.model_dump())
        try:
            cells, iteration_metas, best_seed, derived_total = iterate_units(
                remainder, shares,
                iterations=request.iterations, weights=weights,
                footprint=footprint, circulation_geometry=circulation_geometry,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        leftover = None  # iterate_units gwarantuje zero resztek (spec §3)
    else:
        specs = [
            ApartmentSpec(
                type=a.type, min_area_m2=a.min_area_m2, target_count=a.target_count,
                width_m=a.width_m, depth_m=a.depth_m,
            )
            for a in request.apartments
        ]
        cells, leftover = subdivide_units(remainder, specs)
        iteration_metas, best_seed, derived_total = [], 0, 0

    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area,
            net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(c.polygon),
        )
        for c in cells
    ]

    wall_bands_out: list[dict] = []
    if footprint is not None:
        # wall_cells is every real cell that should get a net-shrunk
        # footprint carved out of the wall envelope -- apartments plus
        # circulation/cage geometry. leftover is None whenever the
        # %-structure iterate_units path ran above (zero-remainder
        # guarantee, spec §3); it's only ever real for the classic
        # subdivide_units fallback below.
        wall_cells = [c.polygon for c in cells]
        if circulation_geometry is not None:
            wall_cells.append(circulation_geometry)
        wall_bands_out = _compute_wall_bands(footprint, wall_cells, leftover)

    if hasattr(remainder, "geoms"):
        net_remainder_m2 = sum(net_polygon(p).area for p in remainder.geoms)
    else:
        net_remainder_m2 = net_polygon(remainder).area

    iterations_out = (
        [_serialize_unit_iteration(m, footprint, circulation_geometry) for m in iteration_metas]
        if shares else []
    )

    return UnitsResponse(
        apartments=apartments_out,
        leftover=json.loads(json.dumps(leftover.__geo_interface__)) if leftover else None,
        wall_bands=wall_bands_out,
        derived_total_units=derived_total,
        net_remainder_m2=net_remainder_m2,
        iterations=iterations_out,
        best_seed=best_seed,
    )


class SplitRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    split_line: list[list[float]] = Field(..., min_length=2, max_length=2)


class SplitResponse(BaseModel):
    polygons: list[dict]
    areas: list[float]


@router.post("/split", response_model=SplitResponse)
def split_polygon_endpoint(request: SplitRequest):
    """Dzieli obrys linią na dwa poligony (plan.md §3.7, F2-06).

    Cienka warstwa HTTP nad `services.bsp.split_polygon_by_edge` — logika
    dzielenia i przypadki brzegowe (linia nie przecina obrysu w dwóch
    punktach) są już przetestowane w `test_bsp.py`.
    """
    from services.bsp import split_polygon_by_edge

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    p1 = (float(request.split_line[0][0]), float(request.split_line[0][1]))
    p2 = (float(request.split_line[1][0]), float(request.split_line[1][1]))

    try:
        part_a, part_b = split_polygon_by_edge(footprint, p1, p2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    parts = [p for p in (part_a, part_b) if p is not None and not p.is_empty and p.area > 1e-6]
    if not parts:
        raise HTTPException(status_code=400, detail="Split produced no valid polygons.")

    return SplitResponse(
        polygons=[json.loads(json.dumps(p.__geo_interface__)) for p in parts],
        areas=[round(p.area, 6) for p in parts],
    )


class ReshapeSegmentInput(BaseModel):
    points: list[list[float]] = Field(..., min_length=2, max_length=2)


class ReshapeCirculationRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    centerline: list[ReshapeSegmentInput] = Field(..., min_length=1)
    corridor_width_m: float = Field(..., gt=0)
    cage_geometries: list[dict] = Field(default_factory=list)
    max_dist_single_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M, gt=0)
    """Edytowalny próg zielonej kropki (heurystyka usera, nie § WT)."""
    max_dist_multi_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M, gt=0)
    """Edytowalny próg szarej kropki (>=2 klatki osiągalne)."""


class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Jak CirculationResponse.circulation_geometry_net -- spec 2026-07-06
    corridor-net-shrink §1."""
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""


@router.post("/circulation/reshape", response_model=ReshapeCirculationResponse)
def reshape_circulation_endpoint(request: ReshapeCirculationRequest):
    """Przelicza korytarz po edycji linii środkowej przez użytkownika (F2-04-bis)."""
    from services.circulation import reshape_circulation

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    centerline_points = [
        ((seg.points[0][0], seg.points[0][1]), (seg.points[1][0], seg.points[1][1]))
        for seg in request.centerline
    ]
    try:
        cage_polygons = [_shape(g) for g in request.cage_geometries]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid cage geometry: {exc}")

    result = reshape_circulation(
        footprint,
        centerline_points,
        request.corridor_width_m,
        cage_polygons,
        max_dist_single_m=request.max_dist_single_m,
        max_dist_multi_m=request.max_dist_multi_m,
    )

    return ReshapeCirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None
            else None
        ),
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )


class MoveCageRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    cage_geometries: list[dict] = Field(..., min_length=1)
    """Aktualne wielokąty WSZYSTKICH klatek, z tą przesuniętą już podmienioną
    na nową pozycję (frontend wysyła cały zestaw, nie tylko jedną)."""
    corridor_width_m: float = Field(default=1.5, gt=0)
    max_dist_single_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M, gt=0)
    max_dist_multi_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M, gt=0)


@router.post("/circulation/move-cage", response_model=CirculationResponse)
def move_cage_endpoint(request: MoveCageRequest):
    """Przelicza korytarz po przesunięciu jednej lub więcej klatek (spec
    2026-07-05-circulation-iteration-selection-and-drag §2). Różni się od
    /circulation/reshape (który kształtuje oś bez stref) -- tu klatki
    wracają do zestawu stref (rectangle_decompose) i _assemble_with_cages
    przelicza korytarz per strefa, tak jak przy pierwszym umieszczeniu."""
    from services.bsp import rectangle_decompose
    from services.cage_placement import assign_cages_to_zones
    from services.circulation import Zone, _assemble_with_cages

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        cages = [_shape(g) for g in request.cage_geometries]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid cage geometry: {exc}")

    fp_buffered = footprint.buffer(1e-6)
    for i, cage in enumerate(cages):
        if not fp_buffered.contains(cage):
            raise HTTPException(status_code=422, detail=f"Klatka {i + 1} poza obrysem")
    for i, a in enumerate(cages):
        for j, b in enumerate(cages[i + 1:], start=i + 1):
            if a.intersects(b):
                raise HTTPException(
                    status_code=422, detail=f"Klatka {i + 1} koliduje z klatką {j + 1}"
                )

    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    local_cages = assign_cages_to_zones(cages, zones)

    if sum(len(v) for v in local_cages.values()) != len(cages):
        raise HTTPException(
            status_code=422,
            detail="Klatka nie mieści się w całości w żadnej strefie (obrys wklęsły dzieli ją na dwie części)",
        )

    result = _assemble_with_cages(
        footprint, zones, local_cages, request.corridor_width_m,
        request.max_dist_single_m, request.max_dist_multi_m,
    )

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )


class CenterlineSegmentInput(BaseModel):
    points: list[list[float]] = Field(..., min_length=2, max_length=2)
    loading: str
    distance_start_m: float | None = None
    distance_end_m: float | None = None
    max_distance_m: float
    exceeds_max: bool


class AddManualElementRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentInput] = []
    corridor_width_m: float = Field(default=1.5, gt=0)
    manual_cage: list[list[float]] | None = None
    """Ring [[x,y],...] nowej ręcznej klatki, bez duplikatu 1. punktu."""
    manual_corridor: list[list[float]] | None = None
    """Łamana [[x,y],...] osi nowego ręcznego korytarza."""
    max_dist_single_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M, gt=0)
    max_dist_multi_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M, gt=0)


@router.post("/circulation/add-manual", response_model=CirculationResponse)
def add_manual_element_endpoint(request: AddManualElementRequest):
    """Dokłada JEDNĄ nową ręczną klatkę lub korytarz do AKTUALNIE wyświetlanego
    wyniku (jakikolwiek by nie był -- domyślny auto, wybrana z listy iteracja,
    czy ręcznie przesunięta klatka), bez ponownego przeliczania auto/iteracyjnego
    umieszczenia od zera (spec 2026-07-06-apartment-type-colors nie dotyczy --
    to fix zgłoszony osobno: rysowanie ręcznej klatki wcześniej wołało
    place_circulation/iterate_cage_placement od nowa przez /layout/circulation,
    co bezpowrotnie gubiło wybraną nie-najlepszą iterację lub przeciągniętą
    klatkę -- ten endpoint tylko dokleja nowy element, resztę zostawia
    nietkniętą, jak /circulation/move-cage nie rusza nic poza jedną strefą."""
    from services.circulation import CirculationResult, CorridorCenterlineSegment, _merge_manual_elements

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        circulation_geometry = (
            _shape(request.circulation_geometry) if request.circulation_geometry is not None else Polygon()
        )
        cage_polygons = [_shape(g) for g in request.cage_geometries]
        remainder = _shape(request.remainder)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid geometry: {exc}")

    centerline = [
        CorridorCenterlineSegment(
            points=((seg.points[0][0], seg.points[0][1]), (seg.points[1][0], seg.points[1][1])),
            loading=seg.loading,
            distance_start_m=seg.distance_start_m if seg.distance_start_m is not None else float("inf"),
            distance_end_m=seg.distance_end_m if seg.distance_end_m is not None else float("inf"),
            max_distance_m=seg.max_distance_m,
            exceeds_max=seg.exceeds_max,
        )
        for seg in request.centerline
    ]

    base_result = CirculationResult(
        zones=[],
        circulation_geometry=circulation_geometry,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
        evacuation_dots=[],
    )

    manual_cages = [request.manual_cage] if request.manual_cage else []
    manual_corridors = [request.manual_corridor] if request.manual_corridor else []

    try:
        result = _merge_manual_elements(
            base_result, footprint, request.corridor_width_m,
            manual_cages, manual_corridors,
            request.max_dist_single_m, request.max_dist_multi_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )


class EvacuationRecomputeRequest(BaseModel):
    centerline: list[dict]
    """[{points: [[x,y],[x,y]]}] -- aktualna oś z frontendu (auto+manual+reshape)."""
    cage_geometries: list[dict] = Field(default_factory=list)
    max_dist_single_m: float = Field(default=20.0, gt=0)
    max_dist_multi_m: float = Field(default=40.0, gt=0)


class EvacuationRecomputeResponse(BaseModel):
    evacuation_dots: list[EvacuationDotResult] = []


@router.post("/evacuation", response_model=EvacuationRecomputeResponse)
def recompute_evacuation_endpoint(request: EvacuationRecomputeRequest):
    """PRZELICZ (spec 2026-07-04-evacuation-dots §3): przemalowuje kropki
    po zmianie progów BEZ ruszania geometrii -- ręcznie przesunięta oś
    zostaje dokładnie tam, gdzie user ją zostawił."""
    from services.evacuation import compute_evacuation_dots

    try:
        segments = [
            ((seg["points"][0][0], seg["points"][0][1]), (seg["points"][1][0], seg["points"][1][1]))
            for seg in request.centerline
        ]
        cages = [_shape(g) for g in request.cage_geometries]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid evacuation payload: {exc}")

    dots = compute_evacuation_dots(
        segments, cages,
        green_max_m=request.max_dist_single_m, gray_max_m=request.max_dist_multi_m,
    )
    return EvacuationRecomputeResponse(evacuation_dots=_serialize_dots(dots))
