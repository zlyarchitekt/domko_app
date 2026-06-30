from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Variant(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    variant_number: int
    buildings: Any
    metrics: Any
