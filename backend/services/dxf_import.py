"""Import a building footprint from an uploaded DXF file.

Reads closed LWPOLYLINE / POLYLINE entities (and simple polyline-boundary
HATCH entities) from the DXF modelspace, converts the largest one by area to
a Shapely Polygon, and returns it as GeoJSON plus basic dimensions.

Limitations (documented, not silently ignored): HATCH boundaries made of
arc/spline edges are not supported (only polyline-type boundary paths); holes
in HATCH boundaries are ignored (only the exterior ring is used) — the MVP
scope in plan.md only requires the outer building footprint.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field

import ezdxf
from ezdxf.lldxf.const import DXFStructureError
from shapely import geometry as geom

MIN_AREA_M2 = 1e-6
SUPPORTED_ENTITY_TYPES = ("LWPOLYLINE", "POLYLINE", "HATCH")


@dataclass
class DxfImportError:
    field: str
    message: str


@dataclass
class DxfImportResult:
    valid: bool
    errors: list[DxfImportError] = field(default_factory=list)
    polygon: dict | None = None
    """GeoJSON Polygon (exterior ring only)."""
    area_m2: float | None = None
    dimensions: dict | None = None
    """{"width_m": float, "height_m": float} — axis-aligned bounding box size."""
    source_entity_type: str | None = None
    source_layer: str | None = None
    candidate_count: int = 0
    """How many closed candidate entities were found in the file (for diagnostics)."""


def _entity_points_lwpolyline(entity) -> list[tuple[float, float]] | None:
    if not entity.closed:
        return None
    points = [(p[0], p[1]) for p in entity.get_points("xy")]
    return points if len(points) >= 3 else None


def _entity_points_polyline(entity) -> list[tuple[float, float]] | None:
    is_closed = bool(getattr(entity, "is_closed", False))
    if not is_closed:
        return None
    points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
    return points if len(points) >= 3 else None


def _entity_points_hatch(entity) -> list[tuple[float, float]] | None:
    """Extract the largest polyline-type boundary path of a HATCH as points.

    Only PolylinePath boundaries are supported (the common case when a HATCH
    is created by picking a closed polyline). Edge-type paths built from
    arcs/splines are skipped.
    """
    best_points: list[tuple[float, float]] | None = None
    best_area = 0.0
    try:
        paths = entity.paths
    except AttributeError:
        return None
    for path in paths:
        vertices = getattr(path, "vertices", None)
        if not vertices:
            continue
        points = [(v[0], v[1]) for v in vertices]
        if len(points) < 3:
            continue
        try:
            candidate_area = geom.Polygon(points).area
        except Exception:
            continue
        if candidate_area > best_area:
            best_area = candidate_area
            best_points = points
    return best_points


def _extract_candidates(doc) -> list[tuple[list[tuple[float, float]], str, str]]:
    """Return (points, entity_type, layer) for every closed candidate entity."""
    msp = doc.modelspace()
    candidates: list[tuple[list[tuple[float, float]], str, str]] = []

    extractors = {
        "LWPOLYLINE": _entity_points_lwpolyline,
        "POLYLINE": _entity_points_polyline,
        "HATCH": _entity_points_hatch,
    }

    for entity in msp:
        dxftype = entity.dxftype()
        extractor = extractors.get(dxftype)
        if extractor is None:
            continue
        points = extractor(entity)
        if points is None:
            continue
        layer = entity.dxf.layer if entity.dxf.hasattr("layer") else "0"
        candidates.append((points, dxftype, layer))

    return candidates


def _bounding_dimensions(polygon: geom.Polygon) -> dict[str, float]:
    minx, miny, maxx, maxy = polygon.bounds
    return {"width_m": round(maxx - minx, 4), "height_m": round(maxy - miny, 4)}


def import_footprint_from_dxf(file_bytes: bytes) -> DxfImportResult:
    """Parse DXF bytes and return the largest closed polygon as GeoJSON."""
    tmp = tempfile.NamedTemporaryFile(suffix=".dxf", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        with open(tmp_path, "wb") as f:
            f.write(file_bytes)
        try:
            doc = ezdxf.readfile(tmp_path)
        except (DXFStructureError, OSError, UnicodeDecodeError) as exc:
            return DxfImportResult(
                valid=False,
                errors=[DxfImportError(field="file", message=f"Could not parse DXF file: {exc}")],
            )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    candidates = _extract_candidates(doc)
    if not candidates:
        return DxfImportResult(
            valid=False,
            errors=[
                DxfImportError(
                    field="file",
                    message=(
                        "No closed LWPOLYLINE, POLYLINE, or HATCH boundary found in the "
                        "DXF modelspace."
                    ),
                )
            ],
            candidate_count=0,
        )

    # Pick the largest candidate by area — the building outline is typically
    # the biggest closed shape in an architectural DXF (dimension lines,
    # hatches for individual rooms, etc. are smaller).
    best_polygon: geom.Polygon | None = None
    best_area = -1.0
    best_type = ""
    best_layer = ""

    for points, dxftype, layer in candidates:
        coords = list(points)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        try:
            poly = geom.Polygon(coords)
        except Exception:
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.area > best_area:
            best_area = poly.area
            best_polygon = poly
            best_type = dxftype
            best_layer = layer

    if best_polygon is None or best_area < MIN_AREA_M2:
        return DxfImportResult(
            valid=False,
            errors=[
                DxfImportError(
                    field="file",
                    message="Found closed entities but none produced a valid polygon with non-zero area.",
                )
            ],
            candidate_count=len(candidates),
        )

    if not best_polygon.exterior.is_simple:
        return DxfImportResult(
            valid=False,
            errors=[DxfImportError(field="polygon", message="Largest closed entity self-intersects.")],
            candidate_count=len(candidates),
        )

    geojson_polygon = {
        "type": "Polygon",
        "coordinates": [[[round(x, 6), round(y, 6)] for x, y in best_polygon.exterior.coords]],
    }

    return DxfImportResult(
        valid=True,
        errors=[],
        polygon=geojson_polygon,
        area_m2=round(best_polygon.area, 4),
        dimensions=_bounding_dimensions(best_polygon),
        source_entity_type=best_type,
        source_layer=best_layer,
        candidate_count=len(candidates),
    )
