"""Solar access analysis endpoint."""

from __future__ import annotations

from datetime import date
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from api.v1.endpoints.validate import LayoutDataInput
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
    footprint: list[list[float]] = Field(..., min_length=3)
    circulation: CirculationSpec = Field(default_factory=CirculationSpec)
    apartments: list[ApartmentProgram] = Field(default_factory=list)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    analysis_date: str | None = Field(default=None, description="ISO date, defaults to spring equinox (03-21)")
    timezone: str = Field(default="Europe/Warsaw")
    required_hours: float = Field(default=3.0, gt=0)
    layout: LayoutDataInput | None = Field(default=None)


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
    edge: list[list[float]]
    length_m: float
    hours_total: float
    hours_status: dict[str, float]
    hourly: list[SunStatusHourModel]
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
    facades: list[FacadeAnalysisModel]
    apartments: list[dict]
    summary: dict


@router.post("/analyze", response_model=SolarAnalyzeResponse)
def analyze_solar_endpoint(request: SolarAnalyzeRequest):
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
                edge=[list(f.edge[0]), list(f.edge[1])],
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


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
