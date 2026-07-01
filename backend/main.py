from fastapi import FastAPI

from api.v1.router import api_router

app = FastAPI(title="PZT Generator API", version="0.1.0")
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok"}
