"""Solar access analysis endpoint."""

from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from services.layout import ApartmentSpec, LayoutInput, generate_layout
from services.solar_analysis import SolarAnalysisResult, analyze_solar_access

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


class SolarAnalyzeRequest(BaseModel):
    footprint: List[List[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: List[ApartmentProgram] = Field(default_factory=list)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    analysis_date: str | None = Field(default=None, description="ISO date, defaults to spring equinox (03-21)")
    timezone: str = Field(default="Europe/Warsaw")
    required_hours: float = Field(default=3.0, gt=0)


class SunStatusHourModel(BaseModel):
    time_iso: str
    elevation_deg: float
    sun_azimuth_deg: float
    cos_incidence: float
    status: str


class FacadeAnalysisModel(BaseModel):
    apartment_id: str
    apartment_type: str
    orientation: str
    azimuth_deg: float
    length_m: float
    hours_total: float
    hours_status: dict[str, float]
    hourly: List[SunStatusHourModel]
    meets_wt: bool
    required_hours: float


class SolarAnalyzeResponse(BaseModel):
    latitude: float
    longitude: float
    analysis_date: str
    timezone: str
    required_hours: float
    building_azimuth_deg: float | None
    building_orientation: str | None
    facades: List[FacadeAnalysisModel]
    apartments: List[dict]
    summary: dict


@router.post("/analyze", response_model=SolarAnalyzeResponse)
def analyze_solar_endpoint(request: SolarAnalyzeRequest):
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

    analysis_date = request.analysis_date or date.today().replace(month=3, day=21).isoformat()

    try:
        result = analyze_solar_access(
            layout,
            latitude=request.latitude,
            longitude=request.longitude,
            analysis_date=analysis_date,
            timezone=request.timezone,
            required_hours=request.required_hours,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Solar analysis failed: {exc}")

    return SolarAnalyzeResponse(
        latitude=result.latitude,
        longitude=result.longitude,
        analysis_date=result.analysis_date,
        timezone=result.timezone,
        required_hours=result.required_hours,
        building_azimuth_deg=result.building_azimuth_deg,
        building_orientation=result.building_orientation,
        facades=[
            FacadeAnalysisModel(
                apartment_id=f.apartment_id,
                apartment_type=f.apartment_type,
                orientation=f.orientation,
                azimuth_deg=f.azimuth_deg,
                length_m=f.length_m,
                hours_total=f.hours_total,
                hours_status=f.hours_status,
                hourly=[
                    SunStatusHourModel(
                        time_iso=h.time_iso,
                        elevation_deg=h.elevation_deg,
                        sun_azimuth_deg=h.sun_azimuth_deg,
                        cos_incidence=h.cos_incidence,
                        status=h.status,
                    )
                    for h in f.hourly
                ],
                meets_wt=f.meets_wt,
                required_hours=f.required_hours,
            )
            for f in result.facades
        ],
        apartments=result.apartments,
        summary=result.summary,
    )


def _points_to_polygon(points: List[List[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
