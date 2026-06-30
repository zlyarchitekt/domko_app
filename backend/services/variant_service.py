from uuid import UUID

from models.variant import Variant


def create_variant(project_id: UUID, variant_number: int, buildings, metrics) -> Variant:
    return Variant(project_id=project_id, variant_number=variant_number, buildings=buildings, metrics=metrics)
