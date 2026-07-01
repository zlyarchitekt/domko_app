"""Typology preset listing and auto-detection endpoints (F2-13/F2-14)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from services.typology_presets import TYPOLOGY_PRESETS, suggest_typology

router = APIRouter()


class PointListRequest(BaseModel):
    points: list[list[float]] = Field(..., min_length=3)


class TypologyPresetItem(BaseModel):
    key: str
    label: str
    staircase_position: str
    corridor_width_m: float
    staircase_dims_m: tuple[float, float]
    double_loaded: bool
    takt_m: tuple[float, float]
    staircase_spacing_m: tuple[float, float] | None
    max_arm_length_m: float | None
    staircase_per_apt: float | None
    apts_per_staircase: tuple[int, int] | None


class TypologyPresetsResponse(BaseModel):
    presets: list[TypologyPresetItem]


class TypologySuggestResponse(BaseModel):
    typology: str
    bbox_ratio: float
    concave_vertex_count: int
    rationale: str
    suggested_cage_count: int
    alternative: str | None


@router.get("/presets", response_model=TypologyPresetsResponse)
def list_typology_presets():
    return TypologyPresetsResponse(
        presets=[
            TypologyPresetItem(
                key=p.key,
                label=p.label,
                staircase_position=p.staircase_position,
                corridor_width_m=p.corridor_width_m,
                staircase_dims_m=p.staircase_dims_m,
                double_loaded=p.double_loaded,
                takt_m=p.takt_m,
                staircase_spacing_m=p.staircase_spacing_m,
                max_arm_length_m=p.max_arm_length_m,
                staircase_per_apt=p.staircase_per_apt,
                apts_per_staircase=p.apts_per_staircase,
            )
            for p in TYPOLOGY_PRESETS.values()
        ]
    )


@router.post("/suggest", response_model=TypologySuggestResponse)
def suggest_typology_endpoint(request: PointListRequest):
    try:
        polygon = _points_to_polygon(request.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    suggestion = suggest_typology(polygon)
    return TypologySuggestResponse(
        typology=suggestion.typology,
        bbox_ratio=suggestion.bbox_ratio,
        concave_vertex_count=suggestion.concave_vertex_count,
        rationale=suggestion.rationale,
        suggested_cage_count=suggestion.suggested_cage_count,
        alternative=suggestion.alternative,
    )


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
