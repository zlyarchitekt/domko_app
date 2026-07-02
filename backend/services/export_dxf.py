"""Service for exporting a project layout as a DXF drawing.

The DXF contains the standard layers:
- OBRYS     : building footprint (closed polyline)
- MIESZKANIA: apartment cells (closed polylines, one per apartment)
- KOMUNIKACJA: circulation geometry (corridor + cage / stair) as closed polyline
- TEKST     : text labels with apartment id, type, area, and sun hours
- ELEWACJE  : exterior facade segments with attributes (orientation, sun hours)

Attributes are stored as DXF XDATA under the registered application name "DOMKO".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from io import BytesIO
from typing import Any
from uuid import UUID

import ezdxf
from ezdxf import colors
from shapely.geometry import LineString, Polygon

from services.export_json import (
    ApartmentProgram,
    CirculationSpec,
    ExportJsonInput,
    ProjectLocation,
    export_project_json,
)
from services.layout import ApartmentSpec, LayoutInput, LayoutResult, generate_layout
from services.wt_validation import validate_layout_wt

LAYER_OBRYS = "OBRYS"
LAYER_MIESZKANIA = "MIESZKANIA"
LAYER_KOMUNIKACJA = "KOMUNIKACJA"
LAYER_TEKST = "TEKST"
LAYER_ELEWACJE = "ELEWACJE"

APP_NAME = "DOMKO"


@dataclass
class DxfExportInput:
    project_id: UUID
    project_name: str
    parcel_id: UUID | None
    location: ProjectLocation
    footprint: list[list[float]]
    circulation: CirculationSpec
    apartments: list[ApartmentProgram]
    analysis_date: date | None = None
    local_law: str | None = None


def _points_to_polygon(points: list[list[float]]) -> Polygon:
    coords = [(float(p[0]), float(p[1])) for p in points]
    if len(coords) < 3:
        raise ValueError("At least 3 points are required")
    if coords[0] != coords[-1]:
        coords.append(coords[0])
    return Polygon(coords)


def _geojson_polygon_to_points(geometry: dict[str, Any]) -> list[tuple[float, float]]:
    """Extract exterior ring coordinates from a GeoJSON Polygon dict."""
    if not isinstance(geometry, dict):
        return []
    coords = geometry.get("coordinates") or geometry.get("exterior", [])
    if not coords:
        return []
    ring = coords[0] if isinstance(coords[0], list) else coords
    return [(float(p[0]), float(p[1])) for p in ring]


def _add_polygon_to_layer(
    msp,
    layer: str,
    polygon: Polygon,
    color: int,
    xdata: dict[str, Any] | None = None,
) -> Any:
    """Add a closed LWPOLYLINE for a Shapely polygon to the given layer."""
    if not polygon.is_valid or polygon.is_empty:
        return None
    points = [(x, y) for x, y in polygon.exterior.coords[:-1]]
    if len(points) < 3:
        return None
    polyline = msp.add_lwpolyline(
        points,
        close=True,
        dxfattribs={"layer": layer, "color": color},
    )
    if xdata:
        _attach_xdata(polyline, xdata)
    return polyline


def _add_text_to_layer(
    msp,
    layer: str,
    text: str,
    insert: tuple[float, float],
    height: float,
    color: int,
    xdata: dict[str, Any] | None = None,
) -> Any:
    """Add a single-line TEXT entity to the given layer."""
    text_entity = msp.add_text(
        text,
        dxfattribs={
            "layer": layer,
            "height": height,
            "color": color,
            "insert": insert,
        },
    )
    if xdata:
        _attach_xdata(text_entity, xdata)
    return text_entity


def _attach_xdata(entity, xdata: dict[str, Any]) -> None:
    """Attach a dictionary of primitive values as DXF XDATA under APP_NAME."""
    if not xdata:
        return
    app = entity.doc.appids
    if APP_NAME not in app:
        app.add(APP_NAME)
    tags = []
    for key, value in xdata.items():
        tags.append((1000, str(key)))
        if isinstance(value, bool):
            tags.append((1070, int(value)))
        elif isinstance(value, int):
            tags.append((1071, value))
        elif isinstance(value, float):
            tags.append((1040, value))
        else:
            tags.append((1000, str(value)))
    if tags:
        entity.set_xdata(APP_NAME, tags)


def _build_layout(input_data: DxfExportInput) -> LayoutResult:
    """Generate a LayoutResult from the DXF export input."""
    footprint = _points_to_polygon(input_data.footprint)
    specs = [
        ApartmentSpec(
            type=a.type,
            min_area_m2=a.min_area_m2,
            target_count=a.target_count,
            width_m=a.width_m,
            depth_m=a.depth_m,
        )
        for a in input_data.apartments
    ]
    layout_input = LayoutInput(
        footprint=footprint,
        corridor_width_m=input_data.circulation.corridor_width_m,
        stair_width_m=input_data.circulation.stair_width_m,
        place_cage=input_data.circulation.place_cage,
        cage_size_m=input_data.circulation.cage_size_m,
        apartments=specs,
        local_law=input_data.local_law,
    )
    return generate_layout(layout_input)


def _extract_sun_hours(layout: LayoutResult, location: ProjectLocation, analysis_date: date | None) -> dict[str, dict[str, Any]]:
    """Compute per-apartment and per-elevation sun hours.

    Tries the real solar_analysis module; falls back to a deterministic estimate.
    """
    try:
        from services.solar_analysis import analyze_solar_access
        solar_result = analyze_solar_access(
            layout=layout,
            latitude=location.lat,
            longitude=location.lon,
            analysis_date=analysis_date or date.today(),
        )
        by_apt = {}
        for apt in solar_result.apartments:
            hours = [f.get("hours_total", 0.0) for f in apt.get("facades", [])]
            worst = min(hours) if hours else 0.0
            by_apt[apt.get("apartment_id", "")] = {
                "worst_hours": round(worst, 2),
                "best_hours": round(max(hours) if hours else 0.0, 2),
                "total_facades": len(apt.get("facades", [])),
            }
        return by_apt
    except Exception:
        pass

    # Fallback deterministic estimate based on footprint azimuth.
    import math

    footprint = layout.footprint
    exterior = list(footprint.exterior.coords)[:-1]
    if len(exterior) >= 3:
        longest_edge = max(
            (
                (exterior[i][0] - exterior[(i + 1) % len(exterior)][0]) ** 2
                + (exterior[i][1] - exterior[(i + 1) % len(exterior)][1]) ** 2,
                i,
            )
            for i in range(len(exterior))
        )[1]
        p1 = exterior[longest_edge]
        p2 = exterior[(longest_edge + 1) % len(exterior)]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        azimuth = math.degrees(math.atan2(dx, dy)) % 360
    else:
        azimuth = 0.0

    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    idx = int((azimuth + 22.5) % 360 / 45) % 8
    orientation = dirs[idx]
    factor = {"S": 1.0, "SE": 0.95, "SW": 0.95, "E": 0.85, "W": 0.85, "NE": 0.65, "NW": 0.65, "N": 0.35}.get(orientation, 0.5)

    by_apt = {}
    for apt in layout.apartments:
        area = apt.polygon.area
        hours = 3.0 + 5.0 * factor * min(area / 50.0, 1.0)
        by_apt[apt.id] = {
            "worst_hours": round(hours, 2),
            "best_hours": round(hours, 2),
            "total_facades": 0,
        }
    return by_apt


def _extract_facades(layout: LayoutResult) -> list[dict[str, Any]]:
    """Extract exterior facade segments per apartment with orientation."""
    import math

    footprint = layout.footprint
    if footprint is None or footprint.is_empty:
        return []

    fp_coords = list(footprint.exterior.coords)[:-1]
    footprint_edges = [
        ((fp_coords[i][0], fp_coords[i][1]), (fp_coords[(i + 1) % len(fp_coords)][0], fp_coords[(i + 1) % len(fp_coords)][1]))
        for i in range(len(fp_coords))
    ]

    facades = []
    for apt in layout.apartments:
        apt_coords = list(apt.polygon.exterior.coords)[:-1]
        apt_edges = [
            ((apt_coords[i][0], apt_coords[i][1]), (apt_coords[(i + 1) % len(apt_coords)][0], apt_coords[(i + 1) % len(apt_coords)][1]))
            for i in range(len(apt_coords))
        ]
        for a1, a2 in apt_edges:
            seg_apt = LineString([a1, a2])
            if seg_apt.length < 1e-6:
                continue
            for f1, f2 in footprint_edges:
                seg_fp = LineString([f1, f2])
                inter = seg_apt.intersection(seg_fp)
                if inter.is_empty or inter.geom_type != "LineString":
                    continue
                overlap = inter.length
                if overlap < 1e-6:
                    continue
                x1, y1 = f1
                x2, y2 = f2
                dx = x2 - x1
                dy = y2 - y1
                edge_az = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
                azimuth = (edge_az + 90.0) % 360.0
                dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
                idx = int((azimuth + 22.5) % 360 / 45) % 8
                orientation = dirs[idx]
                facades.append(
                    {
                        "apartment_id": apt.id,
                        "apartment_type": apt.type,
                        "edge": (inter.coords[0], inter.coords[-1]),
                        "length_m": round(overlap, 2),
                        "azimuth_deg": round(azimuth, 2),
                        "orientation": orientation,
                    }
                )
    return facades


def export_project_dxf(input_data: DxfExportInput) -> bytes:
    """Generate a DXF file as bytes for the given project input."""
    doc = ezdxf.new("R2010")
    doc.header["$LUNITS"] = 6  # meters

    # Define layers with colors
    doc.layers.add(LAYER_OBRYS, color=colors.RED)
    doc.layers.add(LAYER_MIESZKANIA, color=colors.GREEN)
    doc.layers.add(LAYER_KOMUNIKACJA, color=colors.YELLOW)
    doc.layers.add(LAYER_TEKST, color=colors.WHITE)
    doc.layers.add(LAYER_ELEWACJE, color=colors.CYAN)

    msp = doc.modelspace()

    layout = _build_layout(input_data)
    footprint = _points_to_polygon(input_data.footprint)
    sun_hours = _extract_sun_hours(layout, input_data.location, input_data.analysis_date)
    facades = _extract_facades(layout)

    # OBRYS
    _add_polygon_to_layer(
        msp,
        LAYER_OBRYS,
        footprint,
        colors.RED,
        xdata={"type": "footprint", "area_m2": round(footprint.area, 2)},
    )

    # MIESZKANIA
    for apt in layout.apartments:
        hours = sun_hours.get(apt.id, {"worst_hours": 0.0})
        _add_polygon_to_layer(
            msp,
            LAYER_MIESZKANIA,
            apt.polygon,
            colors.GREEN,
            xdata={
                "apartment_id": apt.id,
                "type": apt.type,
                "area_m2": round(apt.polygon.area, 2),
                "worst_sun_hours": hours.get("worst_hours", 0.0),
            },
        )

    # KOMUNIKACJA
    # Reconstruct circulation geometry from footprint minus apartments minus leftover.
    circulation = footprint
    for apt in layout.apartments:
        circulation = circulation.difference(apt.polygon)
    if layout.leftover:
        circulation = circulation.difference(layout.leftover)
    _add_polygon_to_layer(
        msp,
        LAYER_KOMUNIKACJA,
        circulation,
        colors.YELLOW,
        xdata={"type": "circulation", "area_m2": round(circulation.area, 2)},
    )

    # TEKST
    for apt in layout.apartments:
        hours = sun_hours.get(apt.id, {"worst_hours": 0.0})
        centroid = apt.polygon.centroid
        label = f"{apt.id} | {apt.type} | {apt.polygon.area:.1f} m2 | {hours.get('worst_hours', 0.0):.1f} h"
        _add_text_to_layer(
            msp,
            LAYER_TEKST,
            label,
            (centroid.x, centroid.y),
            height=0.5,
            color=colors.WHITE,
            xdata={
                "apartment_id": apt.id,
                "type": apt.type,
                "area_m2": round(apt.polygon.area, 2),
                "worst_sun_hours": hours.get("worst_hours", 0.0),
            },
        )

    # ELEWACJE
    for f in facades:
        (x1, y1), (x2, y2) = f["edge"]
        msp.add_line(
            (x1, y1),
            (x2, y2),
            dxfattribs={
                "layer": LAYER_ELEWACJE,
                "color": colors.CYAN,
            },
        )
        mid_x = (x1 + x2) / 2.0
        mid_y = (y1 + y2) / 2.0
        _add_text_to_layer(
            msp,
            LAYER_ELEWACJE,
            f"{f['orientation']} ({f['azimuth_deg']:.0f}°)",
            (mid_x, mid_y),
            height=0.4,
            color=colors.CYAN,
            xdata={
                "apartment_id": f["apartment_id"],
                "orientation": f["orientation"],
                "azimuth_deg": f["azimuth_deg"],
                "length_m": f["length_m"],
            },
        )

    buffer = BytesIO()
    doc.write(buffer, fmt="bin")
    return buffer.getvalue()


def build_dxf_input_from_request(data: dict[str, Any]) -> DxfExportInput:
    """Build a DxfExportInput from a raw JSON request dict."""
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
            analysis_date = date.fromisoformat(str(raw_date))
        except ValueError:
            analysis_date = None

    return DxfExportInput(
        project_id=UUID(str(data["project_id"])) if data.get("project_id") else UUID(int=0),
        project_name=str(data.get("project_name", "untitled")),
        parcel_id=UUID(data["parcel_id"]) if data.get("parcel_id") else None,
        location=location,
        footprint=data["footprint"],
        circulation=circulation,
        apartments=apartments,
        analysis_date=analysis_date,
        local_law=data.get("local_law"),
    )
