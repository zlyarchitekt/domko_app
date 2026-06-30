from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Parcel(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    name: str
    boundary: Any
    area_m2: float
