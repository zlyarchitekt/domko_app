from uuid import UUID

from models.project import Project


def create_project(parcel_id: UUID, name: str, parameters) -> Project:
    return Project(parcel_id=parcel_id, name=name, parameters=parameters)
