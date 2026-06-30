
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
