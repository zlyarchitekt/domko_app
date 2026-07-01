from fastapi import APIRouter

from api.v1.endpoints import (
    bsp,
    export,
    footprint,
    jobs,
    layout,
    optimizer,
    parcels,
    projects,
    solar,
    typology,
    validate,
    variants,
)

api_router = APIRouter()
api_router.include_router(parcels.router, prefix="/parcels", tags=["parcels"])
api_router.include_router(projects.router, prefix="/projects", tags=["projects"])
api_router.include_router(variants.router, prefix="/variants", tags=["variants"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
api_router.include_router(footprint.router, prefix="/footprint", tags=["footprint"])
api_router.include_router(bsp.router, prefix="/bsp", tags=["bsp"])
api_router.include_router(layout.router, prefix="/layout", tags=["layout"])
api_router.include_router(export.router, prefix="/export", tags=["export"])
api_router.include_router(validate.router, prefix="/validate", tags=["validate"])
api_router.include_router(solar.router, prefix="/solar", tags=["solar"])
api_router.include_router(optimizer.router, prefix="/optimizer", tags=["optimizer"])
api_router.include_router(typology.router, prefix="/typology", tags=["typology"])
