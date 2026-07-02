from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.router import api_router

app = FastAPI(title="PZT Generator API", version="0.1.0")

# Dev CORS: frontend (Next.js, localhost:3000) calls this API directly from the
# browser (F2-15) — no reverse proxy exists yet (F0-04, Docker Compose still
# missing), so the API must allow the browser origin directly.
#
# allow_credentials=False is deliberate: the frontend never sends cookies/auth
# (grep confirms no `credentials: 'include'` anywhere), and per the Fetch spec a
# server cannot combine a wildcard allow_origins with allow_credentials=True —
# Starlette will still emit the literal `*`, which some browsers silently reject
# at the preflight-validation stage (visible as the OPTIONS succeeding in server
# logs while the browser never sends the real request).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/health")
def health_check():
    return {"status": "ok"}
