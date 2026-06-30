from uuid import UUID

from fastapi import APIRouter

from models.variant import Variant

router = APIRouter()


@router.get("/{variant_id}", response_model=Variant)
def get_variant(variant_id: UUID):
    return Variant(project_id=variant_id, variant_number=1, buildings=[], metrics={})


@router.get("/{variant_id}/preview")
def preview_variant(variant_id: UUID):
    return {"variant_id": variant_id, "preview_url": ""}


@router.put("/{variant_id}", response_model=Variant)
def update_variant(variant_id: UUID, variant: Variant):
    return variant


@router.post("/{variant_id}/export")
def export_variant(variant_id: UUID):
    return {"variant_id": variant_id, "file_url": ""}
