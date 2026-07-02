from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.router import api_router

app = FastAPI(title="PZT Generator API", version="0.1.0")

# Dev CORS: frontend (Next.js, localhost:3000) calls this API directly from the
# browser (F2-15) — no reverse proxy exists yet (F0-04, Docker Compose still
# missing), so the API must allow the browser origin directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok"}
