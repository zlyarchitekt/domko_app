# Domko App

Monorepo dla aplikacji Domko — generatora projektów zagospodarowania terenu.

## Struktura

- `backend/` — FastAPI (Python)
- `frontend/` — Next.js 14 (TypeScript)
- `.github/workflows/ci.yml` — GitHub Actions CI

## CI

Workflow uruchamia się na każdym push/PR do `main`:

- `lint-backend` — `ruff check .`
- `test-backend` — `pytest`
- `lint-frontend` — `next lint` (ESLint)
