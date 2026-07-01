"""Optimizer endpoint /api/v1/optimizer/run."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from services.layout import ApartmentSpec
from services.optimizer import OptimizerInput, OptimizerVariant, run_optimizer

router = APIRouter()


class ApartmentProgram(BaseModel):
    type: str = Field(..., min_length=1)
    min_area_m2: float = Field(..., gt=0)
    target_count: int = Field(..., ge=0)
    width_m: float | None = Field(None, gt=0)
    depth_m: float | None = Field(None, gt=0)


class OptimizerRunRequest(BaseModel):
    footprint: List[List[float]] = Field(..., min_length=3)
    apartments: List[ApartmentProgram] = Field(default_factory=list)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    analysis_date: str | None = Field(
        default=None, description="ISO date, defaults to spring equinox (03-21)"
    )
    timezone: str = Field(default="Europe/Warsaw")
    required_hours: float = Field(default=3.0, gt=0)
    cage_mode: str = Field(default="auto", pattern="^(auto|single|multiple)$")
    corridor_width_m: float = Field(default=1.5, gt=0)
    stair_width_m: float = Field(default=1.2, gt=0)
    cage_size_m: float = Field(default=2.5, gt=0)
    local_law: str | None = Field(default=None)
    max_variants: int = Field(default=3, ge=1, le=10)


class MetricsModel(BaseModel):
    solar_score: float
    wt_compliance: float
    total_apartments: int
    total_facades: int
    facades_meeting_wt: int
    wt_rules_passed: int
    wt_rules_total: int


class VariantModel(BaseModel):
    rank: int
    config: Dict[str, Any]
    metrics: MetricsModel
    building_azimuth_deg: float | None
    building_orientation: str | None
    apartments: List[Dict[str, Any]]
    solar_summary: Dict[str, Any]
    wt_passed: bool
    wt_issues: List[str]


class OptimizerRunResponse(BaseModel):
    method: str
    footprint_is_concave: bool
    requested_cage_mode: str
    effective_cage_mode: str
    variants: List[VariantModel]


@router.post("/run", response_model=OptimizerRunResponse)
def optimizer_run_endpoint(request: OptimizerRunRequest):
    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    analysis_date = request.analysis_date or date.today().replace(month=3, day=21).isoformat()
    try:
        analysis_date_obj = date.fromisoformat(analysis_date)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid analysis_date: {analysis_date}")

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

    optimizer_input = OptimizerInput(
        footprint=footprint,
        apartments=specs,
        latitude=request.latitude,
        longitude=request.longitude,
        analysis_date=analysis_date_obj,
        timezone=request.timezone,
        required_hours=request.required_hours,
        cage_mode=request.cage_mode,
        corridor_width_m=request.corridor_width_m,
        stair_width_m=request.stair_width_m,
        cage_size_m=request.cage_size_m,
        local_law=request.local_law,
        max_variants=request.max_variants,
    )

    try:
        result = run_optimizer(optimizer_input)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Optimizer failed: {exc}")

    return OptimizerRunResponse(
        method=result.method,
        footprint_is_concave=result.footprint_is_concave,
        requested_cage_mode=result.requested_cage_mode,
        effective_cage_mode=result.effective_cage_mode,
        variants=[_variant_to_model(v) for v in result.variants],
    )


def _variant_to_model(variant: OptimizerVariant) -> VariantModel:
    solar = variant.solar_analysis
    wt = variant.wt_validation
    return VariantModel(
        rank=variant.rank,
        config=variant.config,
        metrics=MetricsModel(
            solar_score=variant.metrics.solar_score,
            wt_compliance=variant.metrics.wt_compliance,
            total_apartments=variant.metrics.total_apartments,
            total_facades=variant.metrics.total_facades,
            facades_meeting_wt=variant.metrics.facades_meeting_wt,
            wt_rules_passed=variant.metrics.wt_rules_passed,
            wt_rules_total=variant.metrics.wt_rules_total,
        ),
        building_azimuth_deg=solar.building_azimuth_deg,
        building_orientation=solar.building_orientation,
        apartments=solar.apartments,
        solar_summary=solar.summary,
        wt_passed=wt.passed,
        wt_issues=wt.issues,
    )


def _points_to_polygon(points: List[List[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
