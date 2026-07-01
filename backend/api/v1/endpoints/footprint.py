from fastapi import APIRouter, File, HTTPException, UploadFile

from models.footprint import (
    FootprintFromPointsRequest,
    FootprintFromPointsResponse,
    FootprintImportDxfResponse,
    FootprintValidationError,
)
from services.dxf_import import import_footprint_from_dxf
from services.footprint_service import create_footprint_from_points

router = APIRouter()

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("/from-points", response_model=FootprintFromPointsResponse)
def footprint_from_points(payload: FootprintFromPointsRequest):
    return create_footprint_from_points(payload)


@router.post("/import-dxf", response_model=FootprintImportDxfResponse)
async def footprint_import_dxf(file: UploadFile = File(...)):
    if file.filename and not file.filename.lower().endswith(".dxf"):
        raise HTTPException(status_code=400, detail="Only .dxf files are accepted.")

    content = await file.read()
    if not content:
        return FootprintImportDxfResponse(
            valid=False,
            errors=[FootprintValidationError(field="file", message="Uploaded file is empty.")],
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="DXF file too large (max 20 MB).")

    result = import_footprint_from_dxf(content)
    return FootprintImportDxfResponse(
        valid=result.valid,
        errors=[FootprintValidationError(field=e.field, message=e.message) for e in result.errors],
        polygon=result.polygon,
        area_m2=result.area_m2,
        dimensions=result.dimensions,
        source_entity_type=result.source_entity_type,
        source_layer=result.source_layer,
        candidate_count=result.candidate_count,
    )
