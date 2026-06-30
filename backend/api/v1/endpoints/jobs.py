from uuid import UUID

from fastapi import APIRouter

router = APIRouter()


@router.get("/{job_id}")
def get_job(job_id: UUID):
    return {"job_id": job_id, "status": "pending"}
