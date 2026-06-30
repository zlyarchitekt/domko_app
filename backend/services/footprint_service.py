
from shapely import geometry as geom

from models.footprint import (
    FootprintFromPointsRequest,
    FootprintFromPointsResponse,
    FootprintValidationError,
    Point2D,
)

MAX_POINTS = 10_000
MIN_AREA_M2 = 1e-6


def _validate_request(payload: FootprintFromPointsRequest) -> list[FootprintValidationError]:
    errors: list[FootprintValidationError] = []
    points = payload.points

    if not points:
        errors.append(FootprintValidationError(field="points", message="Point list is empty."))
        return errors

    if len(points) < 3:
        errors.append(
            FootprintValidationError(
                field="points", message=f"At least 3 points are required, got {len(points)}."
            )
        )
        return errors

    if len(points) > MAX_POINTS:
        errors.append(
            FootprintValidationError(
                field="points", message=f"Maximum {MAX_POINTS} points allowed, got {len(points)}."
            )
        )

    # duplicate consecutive points collapse the geometry later; report early
    deduped: list[Point2D] = [points[0]]
    for p in points[1:]:
        if p.x != deduped[-1].x or p.y != deduped[-1].y:
            deduped.append(p)

    if len(deduped) < 3:
        errors.append(
            FootprintValidationError(
                field="points", message="All points are collinear or duplicate; no area."
            )
        )
        return errors

    for i, p in enumerate(points):
        if not _is_finite(p.x) or not _is_finite(p.y):
            errors.append(
                FootprintValidationError(
                    field=f"points[{i}]", message="Coordinates must be finite numbers."
                )
            )

    # detect duplicate points (non-consecutive)
    seen: set = set()
    for i, p in enumerate(points):
        key = (round(p.x, 12), round(p.y, 12))
        if key in seen:
            errors.append(
                FootprintValidationError(
                    field=f"points[{i}]", message="Duplicate point detected."
                )
            )
        seen.add(key)

    return errors


def _is_finite(value: float) -> bool:
    try:
        import math

        return math.isfinite(value)
    except (TypeError, ValueError):
        return False


def _to_coordinates(points: list[Point2D], close: bool) -> list[tuple[float, float]]:
    coords = [(p.x, p.y) for p in points]
    if close and (not coords or coords[0] != coords[-1]):
        coords.append(coords[0])
    return coords


def create_footprint_from_points(
    payload: FootprintFromPointsRequest,
) -> FootprintFromPointsResponse:
    errors = _validate_request(payload)
    if errors:
        return FootprintFromPointsResponse(
            valid=False,
            closed=False,
            self_intersecting=False,
            errors=errors,
        )

    coords = _to_coordinates(payload.points, payload.close)
    closed = len(coords) >= 2 and coords[0] == coords[-1]

    try:
        poly = geom.Polygon(coords)
    except Exception as exc:
        return FootprintFromPointsResponse(
            valid=False,
            closed=closed,
            self_intersecting=False,
            errors=[
                FootprintValidationError(
                    field="points", message=f"Could not build polygon: {exc}"
                )
            ],
        )

    if not poly.is_valid:
        # attempt to explain invalidity
        invalidity_reason = _explain_invalid(poly)
        return FootprintFromPointsResponse(
            valid=False,
            closed=closed,
            self_intersecting=invalidity_reason.get("self_intersecting", False),
            errors=[FootprintValidationError(field="polygon", message=invalidity_reason["msg"])],
        )

    self_intersecting = _has_self_intersection(poly)
    if self_intersecting:
        return FootprintFromPointsResponse(
            valid=False,
            closed=closed,
            self_intersecting=True,
            errors=[
                FootprintValidationError(
                    field="polygon", message="Polygon boundary self-intersects."
                )
            ],
        )

    area = poly.area
    if area < MIN_AREA_M2:
        return FootprintFromPointsResponse(
            valid=False,
            closed=closed,
            self_intersecting=False,
            errors=[
                FootprintValidationError(
                    field="polygon", message=f"Polygon area {area} m2 is too small."
                )
            ],
        )

    boundary = [tuple(coord) for coord in poly.exterior.coords]

    return FootprintFromPointsResponse(
        valid=True,
        closed=closed,
        self_intersecting=False,
        errors=[],
        area_m2=area,
        boundary=boundary,
    )


def _has_self_intersection(poly: geom.Polygon) -> bool:
    """Return True if the polygon exterior ring self-intersects.

    Shapely reports self-intersecting rings as invalid. We additionally check
    the boundary for self-intersections to give a deterministic answer even if
    the geometry happens to be flagged valid after buffering.
    """
    boundary = poly.exterior
    if not boundary.is_simple:
        return True
    # A polygon built from an open but otherwise simple path is not a ring yet,
    # so we close it explicitly for the simplicity check.
    if not boundary.is_ring:
        closed_coords = list(boundary.coords)
        if len(closed_coords) >= 2 and closed_coords[0] != closed_coords[-1]:
            closed_coords.append(closed_coords[0])
        try:
            closed_ring = geom.LineString(closed_coords)
            return not closed_ring.is_simple
        except Exception:
            return False
    return False


def _explain_invalid(poly: geom.Polygon) -> dict:
    """Provide a human-readable reason for invalidity and try to flag self-intersection."""
    boundary = poly.exterior
    if not boundary.is_simple:
        return {"self_intersecting": True, "msg": "Polygon boundary self-intersects."}
    if not boundary.is_ring:
        closed_coords = list(boundary.coords)
        if len(closed_coords) >= 2 and closed_coords[0] != closed_coords[-1]:
            closed_coords.append(closed_coords[0])
        try:
            closed_ring = geom.LineString(closed_coords)
            if not closed_ring.is_simple:
                return {"self_intersecting": True, "msg": "Polygon boundary self-intersects."}
        except Exception:
            pass
    return {"self_intersecting": False, "msg": "Polygon geometry is invalid."}
