from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Project(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    parcel_id: UUID
    name: str
    parameters: Any
