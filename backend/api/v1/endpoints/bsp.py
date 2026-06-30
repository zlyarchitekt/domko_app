import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import Polygon

from services.bsp import bsp_zones, concave_vertices, corner_cage

router = APIRouter()


class PointListRequest(BaseModel):
    points: list[list[float]] = Field(..., min_length=3)


class ConcaveResponse(BaseModel):
    concave: bool
    vertices: list[list[float]]


class ZoneItem(BaseModel):
    name: str
    geometry: dict


class ZonesResponse(BaseModel):
    zones: list[ZoneItem]


class CageResponse(BaseModel):
    corner: list[float]
    cage: dict


@router.post("/concave", response_model=ConcaveResponse)
def bsp_concave(request: PointListRequest):
    try:
        poly = points_to_polygon_coords(request.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    cv = concave_vertices(poly)
    return ConcaveResponse(
        concave=len(cv) > 0,
        vertices=[[idx, x, y] for idx, x, y in cv],
    )


@router.post("/zones", response_model=ZonesResponse)
def bsp_zones_endpoint(request: PointListRequest):
    try:
        poly = points_to_polygon_coords(request.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    zones = bsp_zones(poly)
    return ZonesResponse(
        zones=[ZoneItem(name=z.name, geometry=json.loads(json.dumps(z.polygon.__geo_interface__))) for z in zones]
    )


@router.post("/cage", response_model=CageResponse)
def bsp_cage(request: PointListRequest):
    try:
        poly = points_to_polygon_coords(request.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    cv = concave_vertices(poly)
    if not cv:
        raise HTTPException(status_code=400, detail="Polygon has no concave vertices")
    idx, x, y = cv[0]
    cage = corner_cage(poly, (x, y))
    return CageResponse(
        corner=[x, y],
        cage=json.loads(json.dumps(cage.__geo_interface__)),
    )


def points_to_polygon_coords(points: list[list[float]]) -> Polygon:
    """Helper to convert raw point list to Polygon without depending on Point2D model."""
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)
