# DOMKO_APP 🏡

Monorepo dla aplikacji **DOMKO** — generatora i optymalizatora projektów budowlanych z pełną analizą solarną na bazie PVLib i E2E na Playwrightcie. To kompletne MVP obsługujące drag & drop import DXF z wbudowanym backendem w Pythonie.

## Struktura

- `backend/` — FastAPI (Python 3.11+, Shapely, ezdxf, PvLib, pymoo)
- `frontend/` — Next.js 14 App Router (TypeScript, React, Leaflet, Fabric.js)
- `e2e_tests/` — Testy Playwright
- `docker-compose.yml` — orkiestracja

---

## 🚀 Uruchamianie (Rekomendowane: Docker Compose)

To najprostsza ścieżka by uniknąć problemów z pętlami, portami, i Next.js dev-serverami:

1. Zainstaluj Dockera.
2. Odpal projekt:
   ```bash
   docker-compose up -d --build
   ```
3. Aplikacja ukaże się w przeglądarce pod adresem:
   **http://localhost:3000**
4. (Opcjonalnie) Dokumentacja API Swagger (Backend) będzie widoczna pod:
   **http://localhost:8000/docs**

---

## 🛠 Uruchamianie lokalne (Development)

Jeśli chcesz modyfikować pliki "w locie":

### Backend:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend:
```bash
cd frontend
npm install
npm run dev
```

---

## 🧪 Testy, Analiza Kodu i Performance

Projekt został wyposażony w linter i bogaty system testów pokrywający kluczowe wyliczanie obrysów, wydajność solarną i korytarze.

1. **Linter (Backend)**: Wykonaj `ruff check .` 
2. **Testy jednostkowe & Performance**: `pytest backend/tests/` (zawiera `test_performance.py` badający ramy < 3s analizy)
3. **E2E Playwright**: 
   ```bash
   cd e2e_tests
   npm install
   npx playwright test
   ```

## CI/CD
Workflow automatyczny na `.github/workflows/ci.yml` zapewnia stabilne wsparcie, weryfikując kody przy każdym commicie.

> Implementacja MVP zakończona ze Sprintem 4 (Korytarze, Optymalizacje E2E, Ruff)
