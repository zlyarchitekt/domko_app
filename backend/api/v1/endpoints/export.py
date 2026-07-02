"""Export endpoints: JSON, PDF, and DXF project snapshots."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, Response

from services.export_dxf import build_dxf_input_from_request, export_project_dxf
from services.export_json import build_export_payload_from_request, export_project_json

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

    The request body mirrors the JSON export endpoint.
    """
    from services.export_pdf import export_project_pdf
    try:
        pdf_bytes = export_project_pdf(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request or PDF generation failed: {exc}") from exc
    filename = f"{request.get('project_name', 'project')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
