
from pydantic import BaseModel


class Point2D(BaseModel):
    x: float
    y: float


class FootprintFromPointsRequest(BaseModel):
    points: list[Point2D]
    close: bool = True


class FootprintValidationError(BaseModel):
    field: str
    message: str


class FootprintFromPointsResponse(BaseModel):
    valid: bool
    closed: bool
    self_intersecting: bool
    errors: list[FootprintValidationError]
    area_m2: float | None = None
    boundary: list[tuple[float, float]] | None = None


class FootprintDimensions(BaseModel):
    width_m: float
    height_m: float


class FootprintImportDxfResponse(BaseModel):
    valid: bool
    errors: list[FootprintValidationError]
    polygon: dict | None = None
    """GeoJSON Polygon (exterior ring only — holes are not supported)."""
    area_m2: float | None = None
    dimensions: FootprintDimensions | None = None
    source_entity_type: str | None = None
    source_layer: str | None = None
    candidate_count: int = 0
