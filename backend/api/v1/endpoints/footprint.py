from fastapi import APIRouter

from models.footprint import FootprintFromPointsRequest, FootprintFromPointsResponse
from services.footprint_service import create_footprint_from_points

router = APIRouter()


@router.post("/from-points", response_model=FootprintFromPointsResponse)
def footprint_from_points(payload: FootprintFromPointsRequest):
    return create_footprint_from_points(payload)
