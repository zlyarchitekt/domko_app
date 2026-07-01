"""Service for exporting the full project state as JSON.

The service is intentionally stateless and accepts all data required to
reconstruct the project snapshot. It delegates layout generation to the
existing `services.layout` module and produces a deterministic JSON-serializable
payload. Missing upstream modules (optimizer, solar analysis) are handled as
tolerant fallbacks so the export never crashes on an incomplete project.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from shapely.geometry import Polygon

from services.layout import ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.wt_validation import validate_layout_wt


@dataclass
class ProjectLocation:
    lat: float
    lon: float
    address: str | None = None
    city: str | None = None


@dataclass
class ApartmentProgram:
    type: str
    min_area_m2: float
    target_count: int
    width_m: float | None = None
    depth_m: float | None = None


@dataclass
class CirculationSpec:
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    place_cage: bool = True
    cage_size_m: float = 2.5


@dataclass
class ExportJsonInput:
    project_id: UUID
    project_name: str
    parcel_id: UUID | None
    location: ProjectLocation
    footprint: list[list[float]]
    circulation: CirculationSpec
    apartments: list[ApartmentProgram]
    analysis_date: date | None = None
    local_law: str | None = None
    optimizer_results: list[dict[str, Any]] | None = None


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def _geojson(obj: Polygon) -> dict[str, Any]:
    """Return a GeoJSON-style dict for a Shapely geometry."""
    return json.loads(json.dumps(obj.__geo_interface__))


def _safe_solar_analysis(footprint: Polygon, layout: LayoutResult, location: ProjectLocation, analysis_date: date | None) -> dict[str, Any]:
    """Return a simplified solar analysis summary.

    If the real solar analysis module is unavailable, we still produce a
    deterministic placeholder with elevation data derived from the footprint.
    """
    try:
        from services.solar_analysis import analyze_solar_access
        result = analyze_solar_access(
            layout=layout,
            latitude=location.lat,
            longitude=location.lon,
            analysis_date=analysis_date or date.today(),
        )
        return {
            "building_azimuth_deg": result.building_azimuth_deg,
            "building_orientation": result.building_orientation,
            "apartments": result.apartments,
            "elevation_hours": {},
            "source": "solar_analysis",
        }
    except Exception:
        pass

    # Fallback: derive a deterministic solar score from the footprint azimuth.
    exterior = list(footprint.exterior.coords)[:-1]
    longest_edge = max(
        ((exterior[i][0] - exterior[(i + 1) % len(exterior)][0]) ** 2
         + (exterior[i][1] - exterior[(i + 1) % len(exterior)][1]) ** 2,
         i)
        for i in range(len(exterior))
    )[1]
    p1 = exterior[longest_edge]
    p2 = exterior[(longest_edge + 1) % len(exterior)]
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    azimuth = math.degrees(math.atan2(dx, dy)) % 360

    orientation = _azimuth_to_orientation(azimuth)
    factor = {"S": 1.0, "SE": 0.95, "SW": 0.95, "E": 0.85, "W": 0.85, "NE": 0.65, "NW": 0.65, "N": 0.35}.get(orientation, 0.5)

    apartment_hours = []
    for apt in layout.apartments:
        area = apt.polygon.area
        hours = 3.0 + 5.0 * factor * min(area / 50.0, 1.0)
        apartment_hours.append({
            "id": apt.id,
            "type": apt.type,
            "area_m2": round(area, 6),
            "sun_hours": round(hours, 2),
        })

    return {
        "building_azimuth_deg": round(azimuth, 2),
        "building_orientation": orientation,
        "apartments": apartment_hours,
        "elevation_hours": {
            "south": round(7.0 * factor, 2),
            "east": round(5.0 * factor, 2),
            "west": round(5.0 * factor, 2),
            "north": round(3.0 * factor, 2),
        },
        "source": "fallback",
    }


def _azimuth_to_orientation(azimuth: float) -> str:
    """Map azimuth to 8-point compass orientation."""
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((azimuth + 22.5) % 360 / 45) % 8
    return dirs[idx]


def _collect_apartments(layout: LayoutResult) -> list[dict[str, Any]]:
    return [
        {
            "id": a.id,
            "type": a.type,
            "area_m2": round(a.polygon.area, 6),
            "geometry": _geojson(a.polygon),
        }
        for a in layout.apartments
    ]


def _collect_zones(layout: LayoutResult) -> list[dict[str, Any]]:
    return [
        {
            "name": z.name,
            "area_m2": round(z.polygon.area, 6),
            "geometry": _geojson(z.polygon),
        }
        for z in layout.zones
    ]


def _collect_optimizer_results(optimizer_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if optimizer_results is None:
        return []
    return [
        {
            "rank": i + 1,
            "variant_number": v.get("variant_number", i + 1),
            "solar_score": v.get("solar_score"),
            "wt_compliance": v.get("wt_compliance"),
            "buildings": v.get("buildings"),
            "metrics": v.get("metrics"),
        }
        for i, v in enumerate(optimizer_results)
    ]


def export_project_json(payload: ExportJsonInput) -> dict[str, Any]:
    """Build a full, deterministic JSON snapshot of a project.

    The returned structure is intended to be consumed by downstream tools and the
    frontend. It is JSON-serializable and contains:
    - project metadata
    - footprint geometry
    - generated apartments and circulation zones
    - simplified solar analysis
    - WT validation
    - optimizer results (if provided)
    """
    footprint = _points_to_polygon(payload.footprint)
    footprint_geojson = _geojson(footprint)
    footprint_area = footprint.area

    specs = [
        ApartmentSpec(
            type=a.type,
            min_area_m2=a.min_area_m2,
            target_count=a.target_count,
            width_m=a.width_m,
            depth_m=a.depth_m,
        )
        for a in payload.apartments
    ]

    layout_input = LayoutInput(
        footprint=footprint,
        corridor_width_m=payload.circulation.corridor_width_m,
        stair_width_m=payload.circulation.stair_width_m,
        place_cage=payload.circulation.place_cage,
        cage_size_m=payload.circulation.cage_size_m,
        apartments=specs,
        local_law=payload.local_law,
    )
    layout = generate_layout(layout_input)
    wt = validate_layout_wt(layout, payload.local_law)

    solar = _safe_solar_analysis(footprint, layout, payload.location, payload.analysis_date)

    apartments = _collect_apartments(layout)
    zones = _collect_zones(layout)

    result = {
        "project": {
            "id": str(payload.project_id),
            "name": payload.project_name,
            "parcel_id": str(payload.parcel_id) if payload.parcel_id else None,
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "location": {
                "lat": payload.location.lat,
                "lon": payload.location.lon,
                "address": payload.location.address,
                "city": payload.location.city,
            },
        },
        "footprint": {
            "area_m2": round(footprint_area, 6),
            "geometry": footprint_geojson,
        },
        "layout": {
            "footprint_area_m2": round(layout.footprint_area_m2, 6),
            "circulation_area_m2": round(layout.circulation_area_m2, 6),
            "usable_area_m2": round(layout.usable_area_m2, 6),
            "apartments": apartments,
            "zones": zones,
            "leftover_geometry": _geojson(layout.leftover) if layout.leftover else None,
        },
        "solar_analysis": solar,
        "wt_validation": {
            "passed": wt.passed,
            "daylight_min_hours": wt.daylight_min_hours,
            "noise_max_db": wt.noise_max_db,
            "issues": wt.issues,
            "local_law": payload.local_law,
        },
        "optimizer_results": _collect_optimizer_results(payload.optimizer_results),
    }

    return result


def build_export_payload_from_request(data: dict[str, Any]) -> ExportJsonInput:
    """Convert a raw request dict into an ExportJsonInput.

    This helper allows the endpoint to accept a flexible JSON body without
    needing to declare every optional upstream field in a Pydantic model.
    """
    raw_location = data.get("location") or {}
    location = ProjectLocation(
        lat=float(raw_location.get("lat", 0.0)),
        lon=float(raw_location.get("lon", 0.0)),
        address=raw_location.get("address"),
        city=raw_location.get("city"),
    )

    raw_circulation = data.get("circulation") or {}
    circulation = CirculationSpec(
        corridor_width_m=float(raw_circulation.get("corridor_width_m", 1.5)),
        stair_width_m=float(raw_circulation.get("stair_width_m", 1.2)),
        place_cage=bool(raw_circulation.get("place_cage", True)),
        cage_size_m=float(raw_circulation.get("cage_size_m", 2.5)),
    )

    apartments = []
    for a in data.get("apartments", []):
        apartments.append(
            ApartmentProgram(
                type=str(a["type"]),
                min_area_m2=float(a["min_area_m2"]),
                target_count=int(a["target_count"]),
                width_m=float(a["width_m"]) if a.get("width_m") is not None else None,
                depth_m=float(a["depth_m"]) if a.get("depth_m") is not None else None,
            )
        )

    raw_date = data.get("analysis_date")
    analysis_date = None
    if raw_date:
        try:
            analysis_date = datetime.strptime(str(raw_date), "%Y-%m-%d").date()
        except ValueError:
            analysis_date = None

    return ExportJsonInput(
        project_id=UUID(data.get("project_id", uuid4())),
        project_name=str(data.get("project_name", "untitled")),
        parcel_id=UUID(data["parcel_id"]) if data.get("parcel_id") else None,
        location=location,
        footprint=data["footprint"],
        circulation=circulation,
        apartments=apartments,
        analysis_date=analysis_date,
        local_law=data.get("local_law"),
        optimizer_results=data.get("optimizer_results"),
    )
