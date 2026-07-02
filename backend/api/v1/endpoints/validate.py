"""Validation endpoints for layouts and apartments."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.apartment_validation import validate_full_layout
from services.layout import ApartmentSpec, LayoutInput, generate_layout
from services.wt_validation import validate_communication

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


class ApartmentCellData(BaseModel):
    id: str
    type: str
    geometry: dict


class LayoutDataInput(BaseModel):
    footprint: list[list[float]]
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = Field(default_factory=list)
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    apartments: list[ApartmentCellData]


class FullLayoutValidateRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    local_law: str | None = Field(default=None)
    max_corridor_distance_m: float | None = Field(default=None, gt=0)
    layout: LayoutDataInput | None = Field(default=None)


class ApartmentValidationItem(BaseModel):
    apartment_id: str
    type: str
    passed: bool
    area_m2: float
    min_width_m: float
    errors: list[str]
    warnings: list[str]


class WTRuleItem(BaseModel):
    code: str
    description: str
    passed: bool
    detail: str


class FullLayoutValidateResponse(BaseModel):
    passed: bool
    score: int
    apartments: list[ApartmentValidationItem]
    wt_rules: list[WTRuleItem]
    communication_all_connected: bool
    communication_issues: list[str]
    errors: list[str]
    warnings: list[str]


@router.post("/full-layout", response_model=FullLayoutValidateResponse)
def validate_full_layout_endpoint(request: FullLayoutValidateRequest):
    from shapely.geometry import Polygon, shape

    from services.layout import ApartmentCell, LayoutResult, _estimate_building_azimuth

    if request.layout is not None:
        try:
            footprint = _points_to_polygon(request.layout.footprint)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid footprint: {exc}")

        apartments: list[ApartmentCell] = []
        for apt in request.layout.apartments:
            try:
                poly = shape(apt.geometry)
                if not isinstance(poly, Polygon):
                    if poly.geom_type == "MultiPolygon" and not poly.is_empty:
                        poly = poly.geoms[0]
                    else:
                        raise ValueError(f"Geometry must be a Polygon, got {poly.geom_type}")
                apartments.append(ApartmentCell(id=apt.id, type=apt.type, polygon=poly))
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid apartment geometry for {apt.id}: {exc}")

        try:
            circulation_geometry = shape(request.layout.circulation_geometry) if request.layout.circulation_geometry else Polygon()
            if not isinstance(circulation_geometry, Polygon) and not hasattr(circulation_geometry, "geoms"):
                circulation_geometry = Polygon()
        except Exception:
            circulation_geometry = Polygon()

        cage_polygons: list[Polygon] = []
        for cage in request.layout.cage_geometries:
            try:
                poly = shape(cage)
                if isinstance(poly, Polygon):
                    cage_polygons.append(poly)
            except Exception:
                pass

        usable_area = sum(a.polygon.area for a in apartments)
        circulation_area = circulation_geometry.area if not circulation_geometry.is_empty else 0.0
        building_azimuth_deg = _estimate_building_azimuth(footprint)

        layout = LayoutResult(
            footprint=footprint,
            footprint_area_m2=footprint.area,
            circulation_area_m2=circulation_area,
            usable_area_m2=usable_area,
            apartments=apartments,
            leftover=None,
            zones=[],
            building_azimuth_deg=building_azimuth_deg,
            circulation_geometry=circulation_geometry if not circulation_geometry.is_empty else None,
            cage_polygons=cage_polygons,
            corridor_width_m=request.layout.corridor_width_m,
            stair_width_m=request.layout.stair_width_m,
        )
    else:
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
    result = validate_full_layout(
        layout,
        spec_by_type,
        local_law=request.local_law,
        max_corridor_distance_m=request.max_corridor_distance_m,
    )

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
        wt_rules=[
            WTRuleItem(code=r.code, description=r.description, passed=r.passed, detail=r.detail)
            for r in result.wt_rules
        ],
        communication_all_connected=result.communication_all_connected,
        communication_issues=result.communication_issues,
        errors=result.aggregated_errors,
        warnings=result.aggregated_warnings,
    )


class CommunicationValidateRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    min_contact_length_m: float = Field(default=1.2, gt=0)
    max_corridor_distance_m: float = Field(default=30.0, gt=0)
    min_cage_spacing_m: float = Field(default=12.0, gt=0)


class CommunicationIssueItem(BaseModel):
    apartment_id: str | None
    error: str


class CommunicationValidateResponse(BaseModel):
    all_connected: bool
    issues: list[CommunicationIssueItem]


@router.post("/communication", response_model=CommunicationValidateResponse)
def validate_communication_endpoint(request: CommunicationValidateRequest):
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
    )

    try:
        layout = generate_layout(layout_input)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Layout generation failed: {exc}")

    result = validate_communication(
        layout,
        min_contact_length_m=request.min_contact_length_m,
        max_corridor_distance_m=request.max_corridor_distance_m,
        min_cage_spacing_m=request.min_cage_spacing_m,
    )

    return CommunicationValidateResponse(
        all_connected=result.all_connected,
        issues=[
            CommunicationIssueItem(apartment_id=i.apartment_id, error=i.error) for i in result.issues
        ],
    )


@router.post("/apartment")
def validate_apartment_endpoint(item: dict):
    # Backwards-compatible single-apartment validation helper.
    # Kept minimal; /full-layout is the preferred aggregate endpoint.
    errors: list[str] = []
    warnings: list[str] = []
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


def _points_to_polygon(points: list[list[float]]):
    from shapely.geometry import Polygon

    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
