import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from shapely.geometry import shape as _shape

from services.circulation import CAGE_POSITION_MODES, place_circulation
from services.layout import ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.unit_mix import subdivide_units
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


class LayoutGenerateRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    local_law: str | None = Field(default=None)


class ApartmentResult(BaseModel):
    id: str
    type: str
    area_m2: float
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
        apartments=specs,
        local_law=request.local_law,
    )

    try:
        layout = generate_layout(layout_input)
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
            geometry=json.loads(json.dumps(a.polygon.__geo_interface__)),
        )
        for a in layout.apartments
    ]

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


def _serialize_centerline(segments) -> list["CenterlineSegmentResult"]:
    return [
        CenterlineSegmentResult(
            points=[list(seg.points[0]), list(seg.points[1])],
            loading=seg.loading,
            distance_start_m=seg.distance_start_m,
            distance_end_m=seg.distance_end_m,
            max_distance_m=seg.max_distance_m,
            exceeds_max=seg.exceeds_max,
        )
        for seg in segments
    ]


class CenterlineSegmentResult(BaseModel):
    points: list[list[float]]
    loading: str
    distance_start_m: float
    distance_end_m: float
    max_distance_m: float
    exceeds_max: bool


class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []


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

    result = place_circulation(
        footprint,
        corridor_width_m=circulation.corridor_width_m,
        stair_width_m=circulation.stair_width_m,
        place_cage=circulation.place_cage,
        cage_size_m=circulation.cage_size_m,
        cage_position=circulation.cage_position,
    )

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
    )


class UnitsRequest(BaseModel):
    remainder: dict
    apartments: list[ApartmentProgram] = Field(default_factory=list)


class UnitsResponse(BaseModel):
    apartments: list[ApartmentResult]
    leftover: dict | None = None


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
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
        )
        for c in cells
    ]

    return UnitsResponse(
        apartments=apartments_out,
        leftover=json.loads(json.dumps(leftover.__geo_interface__)) if leftover else None,
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
