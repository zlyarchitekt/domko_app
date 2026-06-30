from uuid import UUID

from fastapi import APIRouter

from models.parcel import Parcel

router = APIRouter()


@router.post("/", response_model=Parcel)
def upload_parcel(parcel: Parcel):
    return parcel


@router.get("/", response_model=list[Parcel])
def list_parcels():
    return []


@router.get("/{parcel_id}", response_model=Parcel)
def get_parcel(parcel_id: UUID):
    return Parcel(name="example", boundary=None, area_m2=0.0)


@router.delete("/{parcel_id}")
def delete_parcel(parcel_id: UUID):
    return {"deleted": parcel_id}


@router.get("/{parcel_id}/neighbors")
def get_neighbors(parcel_id: UUID):
    return {"parcel_id": parcel_id, "neighbors": []}
