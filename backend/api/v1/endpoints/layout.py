import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from services.layout import ApartmentSpec, LayoutInput, generate_layout
from services.wt_validation import validate_layout_wt

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


class WTResult(BaseModel):
    passed: bool
    daylight_min_hours: float | None = None
    noise_max_db: float | None = None
    issues: list[str]


class LayoutGenerateResponse(BaseModel):
    footprint_area_m2: float
    circulation_area_m2: float
    usable_area_m2: float
    apartments: list[ApartmentResult]
    leftover: dict | None = None
    wt_validation: WTResult
    zones: list[dict]


@router.post("/generate", response_model=LayoutGenerateResponse)
def generate_layout_endpoint(request: LayoutGenerateRequest):
    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    circulation = request.circulation
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
        apartments=specs,
        local_law=request.local_law,
    )

    try:
        layout = generate_layout(layout_input)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout generation failed: {exc}")

    wt = validate_layout_wt(layout, request.local_law)

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
            daylight_min_hours=wt.daylight_min_hours,
            noise_max_db=wt.noise_max_db,
            issues=wt.issues,
        ),
        zones=[
            {"name": z.name, "geometry": json.loads(json.dumps(z.polygon.__geo_interface__))}
            for z in layout.zones
        ],
    )


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords: list[tuple[float, float]] = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
