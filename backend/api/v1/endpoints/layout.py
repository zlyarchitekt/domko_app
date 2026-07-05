import json
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import LineString, Polygon
from shapely.geometry import shape as _shape

from services.circulation import CAGE_POSITION_MODES, place_circulation
from services.layout import ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.unit_mix import subdivide_units
from services.wall_geometry import exterior_wall_band, interior_wall_bands
from services.wt_validation import WTValidationResult, validate_layout_wt

router = APIRouter()


class ApartmentProgram(BaseModel):
    type: str = Field(..., min_length=1)
    min_area_m2: float = Field(..., gt=0)
    target_count: int = Field(..., ge=0)
    width_m: float | None = Field(None, gt=0)
    depth_m: float | None = Field(None, gt=0)


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


class LayoutGenerateRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    local_law: str | None = Field(default=None)


class ApartmentResult(BaseModel):
    id: str
    type: str
    area_m2: float
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian -- spec 2026-07-04 wall-thickness §5.2."""
    geometry: dict


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
    cage_geometries: list[dict] = []
    """Individual staircase cage polygons (may be empty), for frontend rendering (F2-07)."""
    wall_bands: list[dict] = []
    """Pasy ścian (zewnętrzne + wewnętrzne), GeoJSON, do narysowania na
    płótnie -- spec 2026-07-04 wall-thickness §5.2."""


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
        )
        for a in layout.apartments
    ]

    wall_cells = [a.polygon for a in layout.apartments]
    if layout.circulation_geometry is not None:
        wall_cells.append(layout.circulation_geometry)
    wall_geoms = [exterior_wall_band(layout.footprint)]
    if wall_cells:
        interior_bands = interior_wall_bands(layout.footprint, wall_cells)
        if layout.leftover is not None and not layout.leftover.is_empty:
            # interior_wall_bands() infers "wall" from "not covered by any real
            # cell's net polygon" -- LayoutResult.leftover satisfies that same
            # condition without being a wall (it's legitimately un-programmed
            # floor space). Subtract the RAW leftover polygon (not a net-shrunk
            # version) back out here so it renders as a fully open hole with no
            # wall contour at all -- spec docs/superpowers/specs/2026-07-04-
            # wall-thickness-design.md §3: "bez ściany dookoła" (no wall around
            # it). Raw, not net_polygon(leftover), is correct: leftover is
            # constructed disjoint from every real cell (core engine tiles space
            # with zero gap), so `.difference(leftover)` can never erase a
            # genuine inter-cell wall -- there's nothing to protect by shrinking
            # the subtrahend first. Net-shrinking it first would instead leave a
            # rim of fake wall exactly at leftover's boundary against a real
            # neighbour (contradicting "no wall around it"), and degenerates to
            # a silent no-op for any leftover sliver narrower than
            # 2*NET_SHRINK_M=0.20m (net_polygon() returns empty for shapes that
            # can't survive the shrink -- see test_wall_bands_excludes_thin_
            # leftover_sliver). wall_geometry.py itself stays unaware of
            # "leftover" -- that's a LayoutResult-level concept, not a generic
            # geometry-helper concern -- so the exclusion lives here, at the
            # integration point.
            interior_bands = interior_bands.difference(layout.leftover)
        wall_geoms.append(interior_bands)
    wall_bands_out = [g for geom in wall_geoms for g in _decompose_to_polygons(geom)]

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
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in layout.cage_polygons],
        wall_bands=wall_bands_out,
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


class CenterlineSegmentResult(BaseModel):
    points: list[list[float]]
    loading: str
    distance_start_m: float | None
    distance_end_m: float | None
    max_distance_m: float
    exceeds_max: bool


class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) -- spec §4."""


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

    try:
        result = place_circulation(
            footprint,
            corridor_width_m=circulation.corridor_width_m,
            stair_width_m=circulation.stair_width_m,
            place_cage=circulation.place_cage,
            cage_size_m=circulation.cage_size_m,
            cage_position=circulation.cage_position,
            num_cages=circulation.num_cages,
            manual_cages=[[(p[0], p[1]) for p in ring] for ring in circulation.manual_cages],
            manual_corridors=[[(p[0], p[1]) for p in path] for path in circulation.manual_corridors],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    warnings: list[str] = []
    for i, path in enumerate(circulation.manual_corridors):
        if len(path) < 2:
            continue
        axis = LineString([(p[0], p[1]) for p in path])
        touches_any = any(axis.distance(c) <= 0.25 for c in result.cage_polygons)
        if not touches_any:
            warnings.append(f"Korytarz {i + 1} nie styka się z żadną klatką")

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        warnings=warnings,
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


class UnitsResponse(BaseModel):
    apartments: list[ApartmentResult]
    leftover: dict | None = None
    wall_bands: list[dict] = []
    """Pasy ścian (zewn.+wewn.), GeoJSON -- patrz UnitsRequest.footprint.
    Puste, gdy request nie podał footprint (nie da się policzyć bez pełnego
    obrysu)."""


@router.post("/units", response_model=UnitsResponse)
def subdivide_units_endpoint(request: UnitsRequest):
    """Etap 2 osobno (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md)."""
    try:
        remainder = _shape(request.remainder)
        if remainder.is_empty or not remainder.is_valid:
            raise ValueError("remainder geometry is empty or invalid")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid remainder geometry: {exc}")

    specs = [
        ApartmentSpec(
            type=a.type, min_area_m2=a.min_area_m2, target_count=a.target_count,
            width_m=a.width_m, depth_m=a.depth_m,
        )
        for a in request.apartments
    ]

    cells, leftover = subdivide_units(remainder, specs)

    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area,
            net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
        )
        for c in cells
    ]

    wall_bands_out: list[dict] = []
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

        # Same pattern as layout_result_to_response() (shared with
        # /layout/generate and the optimizer endpoints): wall_cells is every
        # real cell that should get a net-shrunk footprint carved out of the
        # wall envelope -- apartments plus circulation/cage geometry.
        wall_cells = [c.polygon for c in cells]
        if circulation_geometry is not None:
            wall_cells.append(circulation_geometry)

        wall_geoms = [exterior_wall_band(footprint)]
        if wall_cells:
            interior_bands = interior_wall_bands(footprint, wall_cells)
            if leftover is not None and not leftover.is_empty:
                # Subtract the RAW leftover polygon here too -- not
                # net_polygon(leftover) -- exactly the fix from Wall Task 4
                # (commit 10341e3, "revert leftover exclusion to subtract raw
                # polygon, not net-shrunk, avoids thin-sliver regression").
                # leftover is subdivide_units()'s own un-programmed slice,
                # constructed disjoint from every real cell, so raw
                # subtraction can never erase a genuine inter-cell wall.
                interior_bands = interior_bands.difference(leftover)
            wall_geoms.append(interior_bands)
        wall_bands_out = [g for geom in wall_geoms for g in _decompose_to_polygons(geom)]

    return UnitsResponse(
        apartments=apartments_out,
        leftover=json.loads(json.dumps(leftover.__geo_interface__)) if leftover else None,
        wall_bands=wall_bands_out,
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


class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []


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

    result = reshape_circulation(footprint, centerline_points, request.corridor_width_m, cage_polygons)

    return ReshapeCirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
    )
