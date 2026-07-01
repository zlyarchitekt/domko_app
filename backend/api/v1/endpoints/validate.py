"""Validation endpoints for layouts and apartments."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.layout import generate_layout, LayoutInput, ApartmentSpec
from services.apartment_validation import (
    validate_full_layout,
    FullLayoutValidationResult,
    ApartmentValidationResult,
)

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


class FullLayoutValidateRequest(BaseModel):
    footprint: List[List[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: List[ApartmentProgram] = Field(default_factory=list)
    local_law: str | None = Field(default=None)


class ApartmentValidationItem(BaseModel):
    apartment_id: str
    type: str
    passed: bool
    area_m2: float
    min_width_m: float
    errors: List[str]
    warnings: List[str]


class FullLayoutValidateResponse(BaseModel):
    passed: bool
    score: int
    apartments: List[ApartmentValidationItem]
    errors: List[str]
    warnings: List[str]


@router.post("/full-layout", response_model=FullLayoutValidateResponse)
def validate_full_layout_endpoint(request: FullLayoutValidateRequest):
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

    spec_by_type = {a.type: a.min_area_m2 for a in request.apartments}
    result = validate_full_layout(layout, spec_by_type)

    return FullLayoutValidateResponse(
        passed=result.passed,
        score=result.score,
        apartments=[
            ApartmentValidationItem(
                apartment_id=a.apartment_id,
                type=a.type,
                passed=a.passed,
                area_m2=a.area_m2,
                min_width_m=a.min_width_m,
                errors=a.errors,
                warnings=a.warnings,
            )
            for a in result.apartment_results
        ],
        errors=result.aggregated_errors,
        warnings=result.aggregated_warnings,
    )


@router.post("/apartment")
def validate_apartment_endpoint(item: dict):
    # Backwards-compatible single-apartment validation helper.
    # Kept minimal; /full-layout is the preferred aggregate endpoint.
    errors: List[str] = []
    warnings: List[str] = []
    area = float(item.get("area_m2", 0))
    min_area = float(item.get("min_area_m2", 0))
    min_width = float(item.get("min_width_m", 0))

    if min_area > 0 and area < min_area:
        errors.append(f"Powierzchnia {area:.2f} m2 < {min_area:.2f} m2.")
    elif min_area > 0 and abs(area - min_area) < 0.05:
        warnings.append(f"Powierzchnia równa minimum ({area:.2f} m2).")

    if min_width > 0 and min_width < 2.4:
        errors.append(f"Szerokość {min_width:.2f} m < 2.4 m.")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def _points_to_polygon(points: List[List[float]]):
    from shapely.geometry import Polygon

    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
