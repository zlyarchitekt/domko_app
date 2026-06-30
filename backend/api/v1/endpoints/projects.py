from uuid import UUID

from fastapi import APIRouter

from models.project import Project

router = APIRouter()


@router.post("/", response_model=Project)
def create_project(project: Project):
    return project


@router.get("/", response_model=list[Project])
def list_projects():
    return []


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: UUID):
    return Project(parcel_id=project_id, name="example", parameters={})


@router.put("/{project_id}", response_model=Project)
def update_project(project_id: UUID, project: Project):
    return project


@router.post("/{project_id}/generate")
def generate_project(project_id: UUID):
    return {"project_id": project_id, "job_id": "placeholder"}


@router.get("/{project_id}/status")
def project_status(project_id: UUID):
    return {"project_id": project_id, "status": "idle"}
