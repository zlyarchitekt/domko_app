"""Helpers for building Shapely polygons from API point input."""

from __future__ import annotations

from shapely.geometry import Polygon

from models.footprint import Point2D


def points_to_polygon(points: list[Point2D]) -> Polygon:
    """Create a Shapely Polygon from a list of points; auto-close the ring if needed."""
    coords: list[tuple[float, float]] = [(p.x, p.y) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def polygon_to_points(polygon: Polygon) -> list[list[float]]:
    """Return exterior ring coordinates as a list of [x, y] lists."""
    return [[float(x), float(y)] for x, y in polygon.exterior.coords]
