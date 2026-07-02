"""Export endpoints: JSON, PDF, and DXF project snapshots."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from services.export_dxf import build_dxf_input_from_request, export_project_dxf
from services.export_json import ExportJsonInput, build_export_payload_from_request, export_project_json

router = APIRouter()


@router.post("/json")
def export_json(request: dict[str, Any]) -> JSONResponse:
    """Return a full JSON snapshot of the project state.

    The request body must contain:
    - project_id (optional uuid)
    - project_name (optional string)
    - parcel_id (optional uuid)
    - location: {lat, lon, address?, city?}
    - footprint: [[x, y], ...] (at least 3 points)
    - circulation: {corridor_width_m?, stair_width_m?, place_cage?, cage_size_m?}
    - apartments: [{type, min_area_m2, target_count, width_m?, depth_m?}]
    - analysis_date: optional "YYYY-MM-DD"
    - local_law: optional string
    - optimizer_results: optional list of optimizer variants
    """
    try:
        payload = build_export_payload_from_request(request)
        snapshot = export_project_json(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
    return JSONResponse(content=snapshot)


@router.post("/dxf")
def export_dxf(request: dict[str, Any]) -> Response:
    """Return a DXF file of the project layout.

    The request body mirrors the JSON export endpoint. The returned file is a
    binary DXF containing layers:
    - OBRYS: building footprint
    - MIESZKANIA: apartment cells
    - KOMUNIKACJA: circulation area
    - TEKST: labels with apartment id, type, area, and sun hours
    - ELEWACJE: facade segments with orientation attributes
    """
    try:
        payload = build_dxf_input_from_request(request)
        dxf_bytes = export_project_dxf(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc
    filename = f"{payload.project_name or 'project'}.dxf"
    return Response(
        content=dxf_bytes,
        media_type="application/dxf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.post("/pdf")
def export_pdf(request: dict[str, Any]) -> Response:
    """Return a PDF report of the project sun exposure and validation.

    The request body mirrors the JSON export endpoint. Unlike `/json`, the PDF
    renderer (`export_project_pdf`) expects a flat dict (score, footprint_area_m2,
    apartments[].min_width_m/passed, facades[]...) rather than the nested snapshot
    `export_project_json` returns, so this endpoint computes the same snapshot and
    flattens it — see `_build_pdf_report_data`.
    """
    from services.export_pdf import export_project_pdf

    try:
        payload = build_export_payload_from_request(request)
        snapshot = export_project_json(payload)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request: {exc}") from exc

    pdf_data = _build_pdf_report_data(payload, snapshot, request)
    try:
        pdf_bytes = export_project_pdf(pdf_data)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"PDF generation failed: {exc}") from exc

    filename = f"{payload.project_name or 'project'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _apartment_bbox_width(geometry: dict[str, Any]) -> float:
    """Narrower in-plan bounding-box dimension, mirroring apartment_validation._apartment_min_width
    but operating on the already-serialized GeoJSON (no shapely object available here)."""
    coords = geometry["coordinates"][0]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return min(max(xs) - min(xs), max(ys) - min(ys))


def _build_pdf_report_data(
    payload: ExportJsonInput, snapshot: dict[str, Any], raw_request: dict[str, Any]
) -> dict[str, Any]:
    """Flatten the `/export/json` snapshot into the shape `export_project_pdf` expects."""
    from services.apartment_validation import MIN_ROOM_WIDTH_M

    min_area_by_type = {a.type: a.min_area_m2 for a in payload.apartments}

    pdf_apartments = []
    for apt in snapshot["layout"]["apartments"]:
        width = round(_apartment_bbox_width(apt["geometry"]), 2)
        min_area = min_area_by_type.get(apt["type"])
        passed = width >= MIN_ROOM_WIDTH_M and (min_area is None or apt["area_m2"] >= min_area)
        pdf_apartments.append(
            {
                "apartment_id": apt["id"],
                "type": apt["type"],
                "area_m2": apt["area_m2"],
                "min_width_m": width,
                "passed": passed,
            }
        )

    facades = []
    for apt_summary in snapshot.get("solar_analysis", {}).get("apartments", []):
        apartment_id = apt_summary.get("apartment_id") or apt_summary.get("id")
        for f in apt_summary.get("facades", []):
            facades.append({**f, "apartment_id": apartment_id})

    return {
        "project_name": snapshot["project"]["name"],
        "latitude": snapshot["project"]["location"]["lat"],
        "longitude": snapshot["project"]["location"]["lon"],
        "analysis_date": payload.analysis_date.isoformat() if payload.analysis_date else "21 marca (równonoc)",
        "required_hours": raw_request.get("required_hours", 3.0),
        "score": snapshot["wt_validation"]["score"],
        "footprint_area_m2": snapshot["layout"]["footprint_area_m2"],
        "usable_area_m2": snapshot["layout"]["usable_area_m2"],
        "circulation_area_m2": snapshot["layout"]["circulation_area_m2"],
        "apartments": pdf_apartments,
        "facades": facades,
    }
