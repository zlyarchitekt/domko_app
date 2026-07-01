"""Solar access analysis using pvlib sun position and facade-normal dot product."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import List, Tuple

import pandas as pd
from pvlib.location import Location
from shapely.geometry import LineString, Polygon

from services.layout import ApartmentCell, LayoutResult, azimuth_to_cardinal


# Thresholds for hourly sun status (matches frontend legend)
SUN_STATUS_SUNNY = "słoneczne"
SUN_STATUS_PARTIAL = "częściowe"
SUN_STATUS_SHADE = "cień"

# Minimum dot-product (cosine of incidence angle) to count any sun on facade.
# cos(90°) = 0 means sun exactly on horizon; we require the sun to be in the
# forward hemisphere of the facade normal.
MIN_COS_INCIDENCE = 0.0

# Minimum solar elevation above horizon (degrees) to count direct sun.
MIN_SOLAR_ELEVATION_DEG = 0.0


@dataclass
class FacadeSegment:
    """One exterior wall segment derived from a shared apartment-footprint edge."""

    apartment_id: str
    apartment_type: str
    edge: Tuple[Tuple[float, float], Tuple[float, float]]
    length_m: float
    azimuth_deg: float
    """Azimuth of the outward-pointing facade normal (0=N, 90=E, 180=S, 270=W)."""
    orientation: str
    """Cardinal orientation label: N/NE/E/SE/S/SW/W/NW."""


@dataclass
class SunStatusHour:
    """Status for a single 15-minute time step."""

    time_iso: str
    elevation_deg: float
    sun_azimuth_deg: float
    cos_incidence: float
    status: str


@dataclass
class FacadeAnalysis:
    """Solar analysis result for one facade segment."""

    apartment_id: str
    apartment_type: str
    orientation: str
    azimuth_deg: float
    length_m: float
    hours_total: float
    hours_status: dict[str, float]
    hourly: List[SunStatusHour]
    meets_wt: bool
    required_hours: float


@dataclass
class SolarAnalysisResult:
    """Full solar analysis for a layout."""

    latitude: float
    longitude: float
    analysis_date: str
    timezone: str
    required_hours: float
    building_azimuth_deg: float | None
    building_orientation: str | None
    facades: List[FacadeAnalysis]
    apartments: List[dict]
    summary: dict = field(default_factory=dict)


def analyze_solar_access(
    layout: LayoutResult,
    latitude: float,
    longitude: float,
    analysis_date: date | str | None = None,
    timezone: str = "Europe/Warsaw",
    required_hours: float = 3.0,
) -> SolarAnalysisResult:
    """Analyze solar access for every exterior facade of every apartment.

    Args:
        layout: Generated layout with apartments and facade azimuths.
        latitude: Building latitude (decimal degrees).
        longitude: Building longitude (decimal degrees).
        analysis_date: Date for sun-position calculation. Defaults to March 21
            (spring equinox) as required by WT §13.
        timezone: Timezone for local timestamps.
        required_hours: Minimum required hours of direct sun (WT §13 default 3.0).

    Returns:
        SolarAnalysisResult with per-facade hourly status and totals.
    """
    if analysis_date is None:
        analysis_date = date(2021, 3, 21)
    elif isinstance(analysis_date, str):
        analysis_date = date.fromisoformat(analysis_date)

    footprint = layout.footprint_polygon
    if footprint is None or footprint.is_empty:
        raise ValueError("Layout is missing footprint polygon")

    facades = _extract_facade_segments(layout)
    solar_df = _sun_position_timeseries(latitude, longitude, analysis_date, timezone)

    analyzed: List[FacadeAnalysis] = []
    for facade in facades:
        hourly, hours_total, hours_status = _analyze_facade(facade, solar_df)
        meets_wt = hours_total >= required_hours
        analyzed.append(
            FacadeAnalysis(
                apartment_id=facade.apartment_id,
                apartment_type=facade.apartment_type,
                orientation=facade.orientation,
                azimuth_deg=facade.azimuth_deg,
                length_m=facade.length_m,
                hours_total=hours_total,
                hours_status=hours_status,
                hourly=hourly,
                meets_wt=meets_wt,
                required_hours=required_hours,
            )
        )

    apartments_summary = _summarize_apartments(analyzed, required_hours)

    return SolarAnalysisResult(
        latitude=latitude,
        longitude=longitude,
        analysis_date=analysis_date.isoformat(),
        timezone=timezone,
        required_hours=required_hours,
        building_azimuth_deg=layout.building_azimuth_deg,
        building_orientation=azimuth_to_cardinal(layout.building_azimuth_deg),
        facades=analyzed,
        apartments=apartments_summary,
        summary={
            "total_facades": len(analyzed),
            "facades_meeting_wt": sum(1 for f in analyzed if f.meets_wt),
            "facades_below_wt": sum(1 for f in analyzed if not f.meets_wt),
            "total_hours_weighted": round(
                sum(f.hours_total * f.length_m for f in analyzed), 2
            ),
        },
    )


def _extract_facade_segments(layout: LayoutResult) -> List[FacadeSegment]:
    """Extract exterior facade segments for all apartments.

    A facade segment is an edge of an apartment polygon that is collinear and
    overlaps with an edge of the building footprint. We group overlapping
    fragments per apartment so a long shared wall is treated as one segment.
    """
    footprint = layout.footprint_polygon
    if footprint is None or footprint.is_empty:
        return []

    footprint_edges = _polygon_edges(footprint)
    segments: List[FacadeSegment] = []

    for apt in layout.apartments:
        apt_edges = _polygon_edges(apt.polygon)
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
                az = _edge_normal_azimuth(f1, f2, footprint)
                segments.append(
                    FacadeSegment(
                        apartment_id=apt.id,
                        apartment_type=apt.type,
                        edge=(inter.coords[0], inter.coords[-1]),
                        length_m=overlap,
                        azimuth_deg=az,
                        orientation=azimuth_to_cardinal(az) or "?",
                    )
                )

    # Merge adjacent collinear segments belonging to the same apartment.
    return _merge_facade_segments(segments)


def _merge_facade_segments(segments: List[FacadeSegment]) -> List[FacadeSegment]:
    """Merge collinear overlapping fragments per apartment/orientation."""
    if not segments:
        return []

    # Group by apartment + rounded orientation (±22.5° already handled by cardinal).
    groups: dict[Tuple[str, str], List[FacadeSegment]] = {}
    for seg in segments:
        key = (seg.apartment_id, seg.orientation)
        groups.setdefault(key, []).append(seg)

    merged: List[FacadeSegment] = []
    for (apt_id, orientation), group in groups.items():
        # Sort segments along their shared axis and merge contiguous/overlapping ones.
        first = group[0]
        axis = _segment_axis(first.edge)
        sorted_segs = sorted(group, key=lambda s: _project_edge_mid(s.edge, axis))

        chain = [sorted_segs[0]]
        for seg in sorted_segs[1:]:
            last_edge = chain[-1].edge
            if _edges_collinear_and_contiguous(last_edge, seg.edge):
                # Extend the last edge to cover the union of both.
                merged_edge = _merge_two_edges(last_edge, seg.edge)
                chain[-1] = FacadeSegment(
                    apartment_id=chain[-1].apartment_id,
                    apartment_type=chain[-1].apartment_type,
                    edge=merged_edge,
                    length_m=LineString(merged_edge).length,
                    azimuth_deg=chain[-1].azimuth_deg,
                    orientation=chain[-1].orientation,
                )
            else:
                chain.append(seg)

        merged.extend(chain)

    return merged


def _segment_axis(edge: Tuple[Tuple[float, float], Tuple[float, float]]) -> str:
    """Return 'x' if the edge is horizontal-ish, otherwise 'y'."""
    (x1, y1), (x2, y2) = edge
    return "x" if abs(x2 - x1) >= abs(y2 - y1) else "y"


def _project_edge_mid(
    edge: Tuple[Tuple[float, float], Tuple[float, float]], axis: str
) -> float:
    (x1, y1), (x2, y2) = edge
    if axis == "x":
        return (x1 + x2) / 2.0
    return (y1 + y2) / 2.0


def _edges_collinear_and_contiguous(
    a: Tuple[Tuple[float, float], Tuple[float, float]],
    b: Tuple[Tuple[float, float], Tuple[float, float]],
    tol: float = 1e-6,
) -> bool:
    """Return True if two collinear axis-aligned edges touch or overlap."""
    # Check collinearity (axis-aligned simplification).
    ax_min, ax_max = sorted([a[0][0], a[1][0]])
    ay_min, ay_max = sorted([a[0][1], a[1][1]])
    bx_min, bx_max = sorted([b[0][0], b[1][0]])
    by_min, by_max = sorted([b[0][1], b[1][1]])

    same_x = abs(ax_min - bx_min) < tol and abs(ax_max - bx_max) < tol and (ax_max - ax_min) < tol
    same_y = abs(ay_min - by_min) < tol and abs(ay_max - by_max) < tol and (ay_max - ay_min) < tol

    if not (same_x or same_y):
        return False

    # Check overlap/touch along the varying coordinate.
    if same_x:
        return ax_max >= bx_min - tol and bx_max >= ax_min - tol
    else:
        return ay_max >= by_min - tol and by_max >= ay_min - tol


def _merge_two_edges(
    a: Tuple[Tuple[float, float], Tuple[float, float]],
    b: Tuple[Tuple[float, float], Tuple[float, float]],
) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    """Return the bounding edge of two collinear edges."""
    pts = [a[0], a[1], b[0], b[1]]
    axis = _segment_axis(a)
    pts_sorted = sorted(pts, key=lambda p: p[0] if axis == "x" else p[1])
    return (pts_sorted[0], pts_sorted[-1])


def _sun_position_timeseries(
    latitude: float,
    longitude: float,
    analysis_date: date,
    timezone: str,
) -> pd.DataFrame:
    """Build a 15-minute sun-position DataFrame from sunrise to sunset."""
    loc = Location(latitude, longitude, tz=timezone)
    # Use a full day range; pvlib returns sensible values even below horizon.
    start = f"{analysis_date.isoformat()} 04:00"
    end = f"{analysis_date.isoformat()} 22:00"
    times = pd.date_range(start, end, freq="15min", tz=timezone)
    solar_position = loc.get_solarposition(times)
    # Keep only the columns we need and rename for clarity.
    df = solar_position[["apparent_elevation", "azimuth"]].copy()
    df.index = times
    return df


def _analyze_facade(
    facade: FacadeSegment,
    solar_df: pd.DataFrame,
) -> Tuple[List[SunStatusHour], float, dict[str, float]]:
    """Compute hourly status and total sunny hours for a facade segment."""
    normal_az_rad = math.radians(facade.azimuth_deg)
    normal = (math.sin(normal_az_rad), math.cos(normal_az_rad))

    hourly: List[SunStatusHour] = []
    hours_total = 0.0
    hours_status = {
        SUN_STATUS_SUNNY: 0.0,
        SUN_STATUS_PARTIAL: 0.0,
        SUN_STATUS_SHADE: 0.0,
    }

    for ts, row in solar_df.iterrows():
        elevation = float(row["apparent_elevation"])
        sun_azimuth = float(row["azimuth"])
        cos_incidence = _sun_dot_facade_normal(elevation, sun_azimuth, normal)

        status = _status_from_cos(cos_incidence, elevation)
        step_hours = 15.0 / 60.0  # 15 minutes

        if status == SUN_STATUS_SUNNY:
            hours_total += step_hours

        hours_status[status] += step_hours

        hourly.append(
            SunStatusHour(
                time_iso=ts.isoformat(),
                elevation_deg=round(elevation, 2),
                sun_azimuth_deg=round(sun_azimuth, 2),
                cos_incidence=round(cos_incidence, 4),
                status=status,
            )
        )

    return hourly, round(hours_total, 2), hours_status


def _sun_dot_facade_normal(
    sun_elevation_deg: float,
    sun_azimuth_deg: float,
    facade_normal: Tuple[float, float],
) -> float:
    """Dot product of the sun direction unit vector and facade normal.

    The facade normal is a horizontal unit vector (vertical wall).
    The sun vector is a 3-D unit vector. The dot product therefore includes
    the cosine of the solar elevation: a higher sun gives a stronger signal.
    """
    elev_rad = math.radians(sun_elevation_deg)
    az_rad = math.radians(sun_azimuth_deg)

    # Unit sun vector in ENU coordinates.
    sun_vec = (
        math.sin(az_rad) * math.cos(elev_rad),  # east
        math.cos(az_rad) * math.cos(elev_rad),  # north
        math.sin(elev_rad),                     # up
    )

    # Facade normal as 3-D unit vector in the horizontal plane.
    normal_vec = (facade_normal[0], facade_normal[1], 0.0)

    dot = (
        sun_vec[0] * normal_vec[0]
        + sun_vec[1] * normal_vec[1]
        + sun_vec[2] * normal_vec[2]
    )
    return max(-1.0, min(1.0, dot))


def _status_from_cos(cos_incidence: float, elevation_deg: float) -> str:
    """Classify a 15-minute step as sunny / partial / shade.

    - Sun below horizon or behind the wall => shade.
    - Sun in front of the wall with high alignment => sunny.
    - Sun in front but low alignment => partial.
    """
    if elevation_deg <= MIN_SOLAR_ELEVATION_DEG or cos_incidence <= MIN_COS_INCIDENCE:
        return SUN_STATUS_SHADE
    # cos(60°) = 0.5: within ±60° of facade normal => sunny.
    if cos_incidence >= 0.5:
        return SUN_STATUS_SUNNY
    return SUN_STATUS_PARTIAL


def _summarize_apartments(
    facades: List[FacadeAnalysis],
    required_hours: float,
) -> List[dict]:
    """Build per-apartment summary from facade results."""
    by_apt: dict[str, dict] = {}
    for f in facades:
        entry = by_apt.setdefault(
            f.apartment_id,
            {
                "apartment_id": f.apartment_id,
                "apartment_type": f.apartment_type,
                "facades": [],
                "min_hours": float("inf"),
                "max_hours": 0.0,
                "total_length_m": 0.0,
            },
        )
        entry["facades"].append(
            {
                "orientation": f.orientation,
                "azimuth_deg": round(f.azimuth_deg, 1),
                "length_m": round(f.length_m, 2),
                "hours_total": f.hours_total,
                "meets_wt": f.meets_wt,
            }
        )
        entry["min_hours"] = min(entry["min_hours"], f.hours_total)
        entry["max_hours"] = max(entry["max_hours"], f.hours_total)
        entry["total_length_m"] += f.length_m

    result = []
    for entry in by_apt.values():
        entry["min_hours"] = round(entry["min_hours"], 2)
        entry["max_hours"] = round(entry["max_hours"], 2)
        entry["total_length_m"] = round(entry["total_length_m"], 2)
        entry["wt_passed"] = entry["min_hours"] >= required_hours
        result.append(entry)

    return result


def _polygon_edges(polygon: Polygon) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    """Return exterior edges of a polygon as point pairs."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    if n < 2:
        return []
    return [((coords[i][0], coords[i][1]), (coords[(i + 1) % n][0], coords[(i + 1) % n][1])) for i in range(n)]


def _edge_normal_azimuth(
    p1: Tuple[float, float], p2: Tuple[float, float], parent: Polygon
) -> float:
    """Return the outward-pointing normal azimuth for a polygon edge."""
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    edge_az = (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0
    # Exterior ring is CCW; outward normal is +90° from edge direction.
    return (edge_az + 90.0) % 360.0
