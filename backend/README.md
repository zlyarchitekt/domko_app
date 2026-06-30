# Backend PZT Generator

FastAPI backend dla automatycznego generatora projektów zagospodarowania terenu.

## Struktura

- `models/` — modele Pydantic i schematy danych
- `services/` — logika biznesowa (parsery, solver, renderer)
- `api/` — routery FastAPI (`/api/v1/...`)
- `tests/` — testy jednostkowe i integracyjne
- `core/` — konfiguracja i ustawienia aplikacji
- `db/` — połączenie z bazą danych i migracje
- `tasks/` — zadania asynchroniczne (Celery)

## Uruchomienie

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## Testy

```bash
pytest
```
