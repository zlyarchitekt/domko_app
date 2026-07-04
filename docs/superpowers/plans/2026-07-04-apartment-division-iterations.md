# Etap 4: Podział na mieszkania — liczba z powierzchni, iteracje, zero resztek — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Liczba mieszkań wyliczana z powierzchni i struktury % (pole input znika), 10 iteracji podziału z deterministycznym seedem i scoringiem `w·struktura + (1−w)·wielkości`, zero resztek (leftover doklejany do sąsiadów), lista iteracji w panelu + suwak wagi.

**Architecture:** Nowa funkcja `iterate_units()` w `unit_mix.py` owija istniejący `fit_program_to_rectangles()` (dostaje on opcjonalny `rng` do tasowania), po każdej iteracji skleja leftover z sąsiadami (`_merge_leftover_into_cells`) i liczy score. Backend wylicza `derived_total_units` z powierzchni netto remainder i struktury % (largest-remainder dla sztuk per typ). Oba endpointy (`/layout/units`, `/layout/generate`) dostają `iterations`/`weight_w` i zwracają metadane iteracji (dual-surface gotcha).

**Tech Stack:** shapely + stdlib `random` (backend), Next.js (frontend).

**Spec:** `docs/superpowers/specs/2026-07-04-apartment-division-iterations-design.md`
**Niezależny od** Etapów 2–3 (konsumuje tylko `remainder`); może być wdrażany równolegle.

## Global Constraints

- Domyślnie `iterations = 10` (zakres 1–50), `weight_w = 0.5` (0–1).
- Determinizm: iteracja `i` używa `random.Random(i)` — ten sam wynik przy każdym uruchomieniu.
- Zero resztek: po `iterate_units()` leftover ZAWSZE None; pole `leftover` w odpowiedziach zostaje (kompatybilność), zawsze null.
- Kara `merged_disjoint`: +0.5 do składnika `size_dev` danego mieszkania.
- Struktura % normalizowana do sumy (gdy ≠ 100%); wszystkie wiersze 0% → 422.
- Testy backendu: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`. Frontend bez testów automatycznych — typecheck `cd frontend && npx tsc --noEmit`.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001`.

---

### Task 1: unit_mix — rng w fit, merge leftover, scoring, iterate_units (TDD)

**Files:**
- Modify: `backend/services/unit_mix.py` (cały moduł — dopisanie funkcji, `fit_program_to_rectangles` dostaje `rng`)
- Modify: `backend/services/layout.py:94-107` (`ApartmentCell` — pole `merged_disjoint`)
- Test: `backend/tests/test_unit_iterations.py` (nowy plik)

**Interfaces:**
- Consumes: `fit_program_to_rectangles`, `rectangle_decompose`, `ApartmentSpec`, `ApartmentCell`, `net_polygon`
- Produces (używane w Tasku 2):
  - `ApartmentCell.merged_disjoint: bool = False`
  - `@dataclass ProgramShare: type: str; percentage: float; area_min_m2: float; area_max_m2: float`
  - `@dataclass IterationMeta: seed: int; score: float; units_count: int; structure_dev: float; size_dev: float`
  - `derive_total_units(net_remainder_m2: float, shares: list[ProgramShare]) -> int`
  - `allocate_counts(shares: list[ProgramShare], total_units: int) -> dict[str, int]` (largest-remainder, suma = total_units)
  - `iterate_units(remainder, shares: list[ProgramShare], iterations: int, weight_w: float) -> tuple[list[ApartmentCell], list[IterationMeta], int, int]` — zwraca (komórki najlepszej iteracji, metadane wszystkich, best_seed, derived_total_units); leftover zawsze wchłonięty
  - `fit_program_to_rectangles(rectangles, specs, rng: random.Random | None = None)` — wstecznie zgodne (rng=None = dotychczasowe zachowanie)

- [ ] **Step 1: Napisz failing testy**

Utwórz `backend/tests/test_unit_iterations.py`:

```python
"""Testy iteracyjnego podziału na mieszkania (spec 2026-07-04-apartment-
division-iterations §7)."""

from shapely.geometry import Polygon

from services.unit_mix import (
    IterationMeta,
    ProgramShare,
    allocate_counts,
    derive_total_units,
    iterate_units,
)

SHARES = [
    ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
    ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
    ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
    ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
]


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_derive_total_units_scales_with_area():
    small = derive_total_units(200.0, SHARES)
    big = derive_total_units(2000.0, SHARES)
    assert small >= 1
    assert big > small
    # avg = 0.1*28.5 + 0.4*43 + 0.4*64 + 0.1*81 = 53.75 -> 2000/53.75 = 37
    assert big == 37


def test_allocate_counts_largest_remainder_sums_to_total():
    counts = allocate_counts(SHARES, 7)
    assert sum(counts.values()) == 7
    # 7*0.4 = 2.8 -> M2 i M3 dostają po ~3 przez largest remainder
    assert counts["M2"] >= 2 and counts["M3"] >= 2


def test_zero_leftover_guarantee():
    remainder = _rect(0, 0, 24, 10)  # 240 m2
    cells, metas, best_seed, derived_total = iterate_units(remainder, SHARES, iterations=5, weight_w=0.5)
    assert cells
    assert derived_total >= 1
    total_cells_area = sum(c.polygon.area for c in cells)
    assert abs(total_cells_area - remainder.area) < 1e-6  # cała powierzchnia przydzielona
    assert len(metas) == 5
    assert best_seed in {m.seed for m in metas}


def test_determinism_same_seed_same_result():
    remainder = _rect(0, 0, 24, 10)
    cells_a, metas_a, _, _ = iterate_units(remainder, SHARES, iterations=3, weight_w=0.5)
    cells_b, metas_b, _, _ = iterate_units(remainder, SHARES, iterations=3, weight_w=0.5)
    assert [m.score for m in metas_a] == [m.score for m in metas_b]
    assert [c.polygon.wkt for c in cells_a] == [c.polygon.wkt for c in cells_b]


def test_best_seed_has_lowest_score():
    remainder = _rect(0, 0, 30, 11)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=10, weight_w=0.5)
    best = min(metas, key=lambda m: m.score)
    assert best.seed == best_seed


def test_weight_extremes_change_scores():
    remainder = _rect(0, 0, 24, 10)
    _, metas_structure, _, _ = iterate_units(remainder, SHARES, iterations=5, weight_w=0.0)
    _, metas_sizes, _, _ = iterate_units(remainder, SHARES, iterations=5, weight_w=1.0)
    # w=0.0 -> score == size_dev; w=1.0 -> score == structure_dev
    assert all(abs(m.score - m.size_dev) < 1e-9 for m in metas_structure)
    assert all(abs(m.score - m.structure_dev) < 1e-9 for m in metas_sizes)
```

UWAGA do konwencji wag: `w` waży STRUKTURĘ (`score = w·structure_dev +
(1−w)·size_dev`), więc `weight_w=1.0` = czysta struktura.

- [ ] **Step 2: Uruchom testy — mają FAILować**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`
Expected: `ImportError: cannot import name 'ProgramShare'`

- [ ] **Step 3: `ApartmentCell.merged_disjoint`**

W `backend/services/layout.py`, dataclass `ApartmentCell` (po `net_area_m2`,
linia 107):

```python
    merged_disjoint: bool = False
    """True gdy zero-leftover merge dokleił do tej komórki część bez wspólnej
    krawędzi (enklawę) -- kara w scoringu, spec 2026-07-04-apartment-division
    -iterations §3."""
```

- [ ] **Step 4: Implementacja w unit_mix.py**

Na górze pliku dodaj importy `import math`, `import random` oraz dataclasses:

```python
from dataclasses import dataclass


@dataclass
class ProgramShare:
    """Wiersz struktury % (spec 2026-07-04-apartment-division-iterations §1).
    Zastępuje parę (min_area_m2, target_count) jako źródło prawdy programu:
    sztuki wynikają z powierzchni budynku, nie z pola usera."""

    type: str
    percentage: float
    area_min_m2: float
    area_max_m2: float


@dataclass
class IterationMeta:
    seed: int
    score: float
    units_count: int
    structure_dev: float
    size_dev: float
```

Funkcje wyliczeń:

```python
def derive_total_units(net_remainder_m2: float, shares: list[ProgramShare]) -> int:
    """totalUnits z powierzchni i struktury (spec §1). Udziały normalizowane
    do sumy -- struktura 50/50 działa tak samo jak 25/25."""
    total_pct = sum(s.percentage for s in shares)
    if total_pct <= 0:
        raise ValueError("Struktura mieszkań: wszystkie udziały procentowe są zerowe")
    avg = sum(
        (s.percentage / total_pct) * (s.area_min_m2 + s.area_max_m2) / 2.0 for s in shares
    )
    if avg <= 0:
        raise ValueError("Struktura mieszkań: nieprawidłowe przedziały wielkości")
    return max(1, math.floor(net_remainder_m2 / avg))


def allocate_counts(shares: list[ProgramShare], total_units: int) -> dict[str, int]:
    """Largest-remainder: suma sztuk == total_units, bez dryfu zaokrągleń
    (spec §1)."""
    total_pct = sum(s.percentage for s in shares)
    if total_pct <= 0:
        raise ValueError("Struktura mieszkań: wszystkie udziały procentowe są zerowe")
    raw = [(s, total_units * s.percentage / total_pct) for s in shares]
    counts = {s.type: math.floor(r) for s, r in raw}
    deficit = total_units - sum(counts.values())
    by_frac = sorted(raw, key=lambda sr: sr[1] - math.floor(sr[1]), reverse=True)
    for s, _ in by_frac[:deficit]:
        counts[s.type] += 1
    return counts
```

`fit_program_to_rectangles` — sygnatura (linia 37) dostaje parametr:

```python
def fit_program_to_rectangles(
    rectangles: list[Polygon], specs: list[ApartmentSpec], rng: random.Random | None = None
) -> tuple[list[ApartmentCell], Polygon | None]:
```

a zaraz po zbudowaniu `queue` (linia 46, `queue.extend(...)`) dodaj:

```python
    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(rectangles := list(rectangles))
```

(UWAGA: `rectangles :=` tworzy przetasowaną KOPIĘ lokalną — oryginalna lista
wywołującego nietknięta; bez rng zachowanie w 100% dotychczasowe.)

Merge resztek:

```python
def _merge_leftover_into_cells(cells: list[ApartmentCell], leftover) -> None:
    """Zero resztek (spec §3): każda część leftover doklejana do mieszkania
    o najdłuższej wspólnej krawędzi; części bez sąsiada -- do najbliższego
    mieszkania z flagą merged_disjoint. Mutuje cells in-place."""
    if leftover is None or leftover.is_empty or not cells:
        return
    parts = list(leftover.geoms) if hasattr(leftover, "geoms") else [leftover]
    for part in parts:
        if part.is_empty or part.area < 1e-9:
            continue
        best_i, best_shared = -1, 0.0
        for i, cell in enumerate(cells):
            shared = cell.polygon.boundary.intersection(part.boundary).length
            if shared > best_shared:
                best_i, best_shared = i, shared
        if best_i >= 0 and best_shared > 1e-6:
            cells[best_i].polygon = unary_union([cells[best_i].polygon, part])
        else:
            nearest = min(range(len(cells)), key=lambda i: cells[i].polygon.distance(part))
            cells[nearest].polygon = unary_union([cells[nearest].polygon, part])
            cells[nearest].merged_disjoint = True
    for cell in cells:
        cell.net_area_m2 = net_polygon(cell.polygon).area
```

Scoring:

```python
def _score_iteration(
    cells: list[ApartmentCell], shares: list[ProgramShare], weight_w: float
) -> tuple[float, float, float]:
    """Zwraca (score, structure_dev, size_dev) -- spec §4. Mniejszy lepszy."""
    total_pct = sum(s.percentage for s in shares) or 1.0
    n = len(cells) or 1
    structure_dev = sum(
        abs(s.percentage / total_pct - sum(1 for c in cells if c.type == s.type) / n)
        for s in shares
    )
    bounds = {s.type: (s.area_min_m2, s.area_max_m2) for s in shares}
    devs = []
    for c in cells:
        lo, hi = bounds.get(c.type, (0.0, float("inf")))
        area = c.polygon.area
        dev = 0.0
        if lo > 0 and area < lo:
            dev = (lo - area) / lo
        elif hi > 0 and area > hi:
            dev = (area - hi) / hi
        if c.merged_disjoint:
            dev += 0.5
        devs.append(dev)
    size_dev = sum(devs) / len(devs) if devs else 0.0
    score = weight_w * structure_dev + (1.0 - weight_w) * size_dev
    return score, structure_dev, size_dev
```

Główna pętla:

```python
def iterate_units(
    remainder: Polygon | MultiPolygon,
    shares: list[ProgramShare],
    iterations: int = 10,
    weight_w: float = 0.5,
) -> tuple[list[ApartmentCell], list[IterationMeta], int, int]:
    """Iteracyjny podział (spec §2): `iterations` przebiegów z deterministycznym
    seedem, zero-leftover merge po każdym, wygrywa najniższy score."""
    net_remainder = net_polygon(remainder) if remainder.geom_type == "Polygon" else remainder
    # totalUnits liczone z powierzchni netto remainder (spec §1); dla
    # MultiPolygon sumujemy netto części.
    if hasattr(remainder, "geoms"):
        net_area = sum(net_polygon(p).area for p in remainder.geoms)
    else:
        net_area = net_polygon(remainder).area
    total_units = derive_total_units(net_area, shares)
    counts = allocate_counts(shares, total_units)
    specs = [
        ApartmentSpec(
            type=s.type,
            min_area_m2=(s.area_min_m2 + s.area_max_m2) / 2.0,
            target_count=counts[s.type],
        )
        for s in shares
        if counts[s.type] > 0
    ]

    rectangles = rectangle_decompose(remainder)
    best: tuple[float, list[ApartmentCell]] | None = None
    metas: list[IterationMeta] = []
    for seed in range(iterations):
        rng = random.Random(seed)
        cells, leftover = fit_program_to_rectangles(list(rectangles), specs, rng=rng)
        _merge_leftover_into_cells(cells, leftover)
        if not cells:
            # remainder za mały na jakikolwiek program: jedno mieszkanie z całości
            from services.layout import ApartmentCell as _Cell
            import uuid as _uuid
            cells = [_Cell(id=str(_uuid.uuid4()), type=shares[0].type, polygon=remainder
                           if remainder.geom_type == "Polygon" else unary_union(remainder))]
            cells[0].net_area_m2 = net_area
        score, structure_dev, size_dev = _score_iteration(cells, shares, weight_w)
        metas.append(IterationMeta(seed=seed, score=score, units_count=len(cells),
                                   structure_dev=structure_dev, size_dev=size_dev))
        if best is None or score < best[0]:
            best = (score, cells)
    best_seed = min(metas, key=lambda m: m.score).seed
    return best[1], metas, best_seed, total_units
```

- [ ] **Step 5: Uruchom testy — mają przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py tests/test_layout.py -v`
Expected: wszystkie PASS (w tym stare — `fit_program_to_rectangles` bez rng
zachowuje się identycznie).

- [ ] **Step 6: Commit**

```bash
git add backend/services/unit_mix.py backend/services/layout.py backend/tests/test_unit_iterations.py
git commit -m "feat: iterate_units - seeded iterations, zero-leftover merge, structure/size scoring"
```

---

### Task 2: API — oba endpointy z iteracjami i strukturą %

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (`ApartmentProgram` :18-23, `LayoutGenerateRequest` :38-42, `UnitsRequest` :311-323, `UnitsResponse` :326-332, `LayoutGenerateResponse` :68-84, `subdivide_units_endpoint` :335-405, `generate_layout_endpoint` :87, `layout_result_to_response` :134)
- Modify: `backend/services/layout.py` (`LayoutInput` :81-91, `LayoutResult` :110-127, `generate_layout` :130-)
- Test: `backend/tests/test_unit_iterations.py` (dopisanie)

**Interfaces:**
- Consumes: `iterate_units`, `ProgramShare`, `IterationMeta` (Task 1)
- Produces:
  - `ApartmentProgram` + pola: `percentage: float = 0`, `area_min_m2: float = 0`, `area_max_m2: float = 0` (stare pola zostają — kompat)
  - `UnitsRequest`/`LayoutGenerateRequest` + `iterations: int = 10 (ge=1, le=50)`, `weight_w: float = 0.5 (ge=0, le=1)`
  - odpowiedzi (OBIE): `derived_total_units: int`, `net_remainder_m2: float`, `iterations: list[IterationMetaResult]`, `best_seed: int`; `leftover` zawsze `None`

- [ ] **Step 1: Failing test endpointu**

Dopisz do `backend/tests/test_unit_iterations.py`:

```python
def test_units_endpoint_returns_iterations_and_no_leftover():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    remainder = Polygon([(0, 0), (24, 0), (24, 10), (0, 10)]).__geo_interface__
    payload = {
        "remainder": dict(remainder),
        "apartments": [
            {"type": "M2", "percentage": 50, "area_min_m2": 38, "area_max_m2": 48,
             "min_area_m2": 43, "target_count": 0},
            {"type": "M3", "percentage": 50, "area_min_m2": 58, "area_max_m2": 70,
             "min_area_m2": 64, "target_count": 0},
        ],
        "iterations": 5,
        "weight_w": 0.5,
    }
    res = client.post("/api/v1/layout/units", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["leftover"] is None
    assert body["derived_total_units"] >= 1
    assert len(body["iterations"]) == 5
    assert body["best_seed"] in [m["seed"] for m in body["iterations"]]
```

(Prefiks ścieżki `/api/v1` zweryfikuj w `backend/api/v1/router.py` /
`main.py` — jeśli inny, dostosuj URL w teście.)

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -k endpoint -v`
Expected: FAIL (pola nie istnieją).

- [ ] **Step 2: Modele request/response**

`ApartmentProgram` (linia 18) — dodaj pola struktury:

```python
    percentage: float = Field(default=0.0, ge=0)
    area_min_m2: float = Field(default=0.0, ge=0)
    area_max_m2: float = Field(default=0.0, ge=0)
```

`UnitsRequest` i `LayoutGenerateRequest` — dodaj:

```python
    iterations: int = Field(default=10, ge=1, le=50)
    weight_w: float = Field(default=0.5, ge=0.0, le=1.0)
```

Wspólny model metadanych (obok innych modeli):

```python
class IterationMetaResult(BaseModel):
    seed: int
    score: float
    units_count: int
    structure_dev: float
    size_dev: float
```

`UnitsResponse` i `LayoutGenerateResponse` — dodaj:

```python
    derived_total_units: int = 0
    net_remainder_m2: float = 0.0
    iterations: list[IterationMetaResult] = []
    best_seed: int = 0
```

- [ ] **Step 3: subdivide_units_endpoint na iterate_units**

W `subdivide_units_endpoint` (linia 345-353) zamień budowę specs i wywołanie:

```python
    shares = [
        ProgramShare(
            type=a.type,
            percentage=a.percentage,
            area_min_m2=a.area_min_m2 or a.min_area_m2,
            area_max_m2=a.area_max_m2 or a.min_area_m2,
        )
        for a in request.apartments
    ]
    try:
        cells, iteration_metas, best_seed, derived_total = iterate_units(
            remainder, shares, iterations=request.iterations, weight_w=request.weight_w
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    leftover = None  # iterate_units gwarantuje zero resztek (spec §3)
```

(importy: `from services.unit_mix import ProgramShare, iterate_units`;
`or a.min_area_m2` = fallback dla starych klientów bez pól przedziału).

Dalej w tym endpoincie: net remainder do odpowiedzi —

```python
    if hasattr(remainder, "geoms"):
        net_remainder_m2 = sum(net_polygon(p).area for p in remainder.geoms)
    else:
        net_remainder_m2 = net_polygon(remainder).area
```

(import `net_polygon` z `services.wall_geometry` już jest pośrednio — dodaj
jawny). W `return UnitsResponse(...)` dodaj:

```python
        derived_total_units=derived_total,
        net_remainder_m2=net_remainder_m2,
        iterations=[IterationMetaResult(**vars(m)) for m in iteration_metas],
        best_seed=best_seed,
```

UWAGA: blok `wall_bands` w tym endpoincie odejmował `leftover` od
`interior_bands` (linie 389-397) — po zmianie `leftover` jest zawsze None,
więc ta gałąź po prostu przestaje się wykonywać; NIE usuwaj jej (zero
ryzyka, mniejszy diff).

- [ ] **Step 4: Ścieżka /generate (dual-surface)**

`services/layout.py`:

`LayoutInput` — dodaj:

```python
    iterations: int = 10
    weight_w: float = 0.5
    program_shares: list = field(default_factory=list)
    """list[ProgramShare] -- gdy niepuste, generate_layout używa iterate_units
    zamiast subdivide_units (spec 2026-07-04-apartment-division-iterations)."""
```

`LayoutResult` — dodaj:

```python
    iteration_metas: list = field(default_factory=list)
    best_seed: int = 0
    derived_total_units: int = 0
    net_remainder_m2: float = 0.0
```

W `generate_layout` (linia 156) zamień `subdivide_units(...)` na:

```python
    if input.program_shares:
        from services.unit_mix import iterate_units
        from services.wall_geometry import net_polygon as _np

        apartments, iteration_metas, best_seed, derived_total_units = iterate_units(
            circulation.remainder, input.program_shares,
            iterations=input.iterations, weight_w=input.weight_w,
        )
        leftover = None
        rem = circulation.remainder
        net_remainder_m2 = (
            sum(_np(p).area for p in rem.geoms) if hasattr(rem, "geoms") else _np(rem).area
        )
    else:
        apartments, leftover = subdivide_units(circulation.remainder, input.apartments)
        iteration_metas, best_seed, derived_total_units, net_remainder_m2 = [], 0, 0, 0.0
```

i przekaż nowe pola do `LayoutResult(...)`.

W `generate_layout_endpoint` — przy budowie `LayoutInput` dodaj:

```python
        iterations=request.iterations,
        weight_w=request.weight_w,
        program_shares=[
            ProgramShare(
                type=a.type, percentage=a.percentage,
                area_min_m2=a.area_min_m2 or a.min_area_m2,
                area_max_m2=a.area_max_m2 or a.min_area_m2,
            )
            for a in request.apartments
            if a.percentage > 0
        ],
```

W `layout_result_to_response` dodaj do konstruktora odpowiedzi:

```python
        derived_total_units=layout.derived_total_units,
        net_remainder_m2=layout.net_remainder_m2,
        iterations=[IterationMetaResult(**vars(m)) for m in layout.iteration_metas],
        best_seed=layout.best_seed,
```

- [ ] **Step 5: Testy + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS (stare testy /units z klientami bez nowych pól
przechodzą przez fallbacki `or a.min_area_m2` i defaulty Pydantic).

```bash
git add backend/api/v1/endpoints/layout.py backend/services/layout.py backend/tests/test_unit_iterations.py
git commit -m "feat: iterations/weight_w through /layout/units and /layout/generate, derived unit count"
```

---

### Task 3: Frontend — panel Program bez pola liczby, suwak wagi, lista iteracji

**Files:**
- Modify: `frontend/app/lib/api.ts` (`ApartmentProgramInput`, `UnitsResponse` :224-228, `LayoutGenerateResponse`, sygnatura `subdivideUnits` :230-)
- Modify: `frontend/app/state/SessionContext.tsx` (stan, `runSubdivideUnits` :538-, `regenerate`, reducer)
- Modify: `frontend/app/components/ProgramSection.tsx` (pole totalUnits :39, wiersze, stopka)

**Interfaces:**
- Consumes: pola API z Task 2
- Produces: kompletne UI Etapu 4

- [ ] **Step 1: api.ts**

`ApartmentProgramInput` — dodaj `percentage: number; area_min_m2: number;
area_max_m2: number;` (obok istniejących pól).

Nowy typ + pola odpowiedzi:

```ts
export interface IterationMeta {
  seed: number;
  score: number;
  units_count: number;
  structure_dev: number;
  size_dev: number;
}
```

Do `UnitsResponse` i `LayoutGenerateResponse` dodaj (OPCJONALNE w TS —
`runSubdivideUnits` konstruuje `LayoutGenerateResponse` ręcznie i wymagane
pola wymusiłyby dopisywanie ich w każdym takim miejscu; odczyt zawsze
z `?? []`/`?? null`):

```ts
  derived_total_units?: number;
  net_remainder_m2?: number;
  iterations?: IterationMeta[];
  best_seed?: number;
```

`subdivideUnits(...)` — dodaj parametry `iterations: number` i `weightW:
number` przekazywane w body jako `iterations`/`weight_w`.

- [ ] **Step 2: SessionContext**

Stan (po `totalUnits`):

```ts
  weightW: number;               // suwak struktura(1)↔wielkości(0), default 0.5
  lastIterations: api.IterationMeta[];
  derivedTotalUnits: number | null;
  netRemainderM2: number | null;
```

`initialState`: `weightW: 0.5, lastIterations: [], derivedTotalUnits: null,
netRemainderM2: null,`.

Akcje:

```ts
  | { type: "SET_WEIGHT_W"; weightW: number }
  | { type: "SET_ITERATION_RESULTS"; iterations: api.IterationMeta[]; derivedTotalUnits: number; netRemainderM2: number }
```

Reducer:

```ts
    case "SET_WEIGHT_W":
      return { ...state, weightW: action.weightW };
    case "SET_ITERATION_RESULTS":
      return {
        ...state,
        lastIterations: action.iterations,
        derivedTotalUnits: action.derivedTotalUnits,
        netRemainderM2: action.netRemainderM2,
        // liczba pochodna zasila dotychczasowy mechanizm ≈sztuk w wierszach
        totalUnits: action.derivedTotalUnits,
        program: recomputeDerivedProgram(state.program, action.derivedTotalUnits),
      };
```

Callback `setWeightW` + wpis do interfejsu i `value` (wzorzec
`setTotalUnits`). `SET_TOTAL_UNITS` i `setTotalUnits` ZOSTAJĄ w kodzie
(nieużywane przez UI po tym etapie — usunięcie odkładamy, mniejszy diff).

`runSubdivideUnits` (linia 538): w `unitsReq` dodaj pola struktury:

```ts
      const unitsReq = state.program.map((row) => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
        percentage: row.percentage,
        area_min_m2: row.area_min_m2,
        area_max_m2: row.area_max_m2,
      }));
```

wywołanie `api.subdivideUnits(..., 10, state.weightW)` — stała `10`
(bez osobnego pola w stanie; YAGNI). Po otrzymaniu `unitsRes` dodaj dispatch:

```ts
      dispatch({
        type: "SET_ITERATION_RESULTS",
        iterations: unitsRes.iterations ?? [],
        derivedTotalUnits: unitsRes.derived_total_units ?? 0,
        netRemainderM2: unitsRes.net_remainder_m2 ?? 0,
      });
```

W ręcznie budowanym `layoutResult` w tym samym callbacku (linie ~553-566)
dopisz nowe pola z odpowiedzi, żeby ścieżka dwustopniowa niosła te same
dane co /generate:

```ts
        derived_total_units: unitsRes.derived_total_units,
        net_remainder_m2: unitsRes.net_remainder_m2,
        iterations: unitsRes.iterations,
        best_seed: unitsRes.best_seed,
```

Analogicznie w `regenerate` (ścieżka /generate): request dostaje
`iterations: 10, weight_w: state.weightW` oraz pola struktury w
`apartments`; po odpowiedzi ten sam dispatch `SET_ITERATION_RESULTS`
z pól `LayoutGenerateResponse`. Dodaj `state.weightW` do zależności obu
useCallbacków.

- [ ] **Step 3: ProgramSection**

- USUŃ label/input „liczba mieszkań" (blok z `value={state.totalUnits}`,
  linia ~39) wraz z `setTotalUnits` z destrukturyzacji.
- W jego miejsce readonly:

```tsx
      <div className="flex items-center justify-between text-xs text-zinc-400">
        Liczba mieszkań (z powierzchni)
        <span className="font-mono text-zinc-200 light:text-zinc-800">
          {state.derivedTotalUnits !== null
            ? `≈ ${state.derivedTotalUnits}${state.netRemainderM2 !== null ? ` (${state.netRemainderM2.toFixed(0)} m² netto)` : ""}`
            : "—"}
        </span>
      </div>
```

- Suwak wagi (pod wierszami struktury):

```tsx
      <label className="flex items-center justify-between text-xs text-zinc-400">
        {/* spec §"Suwak": LEWO = trzymaj strukturę %, PRAWO = trzymaj
            wielkości. Pozycja suwaka s mapuje się na weight_w = 1 - s,
            bo w waży strukturę (score = w·struktura + (1-w)·wielkości). */}
        <span>struktura ↔ wielkości (w={state.weightW.toFixed(2)})</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={1 - state.weightW}
          onChange={(e) => setWeightW(1 - Number(e.target.value))}
          className="ml-2 w-24 accent-accent-500"
        />
      </label>
```

- Lista iteracji (na końcu sekcji):

```tsx
      {state.lastIterations.length > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje ({state.lastIterations.length})
          </div>
          {state.lastIterations.map((m) => {
            const isBest = m.seed === (state.layoutResult?.best_seed ?? -1) ||
              state.lastIterations.every((o) => m.score <= o.score);
            return (
              <div
                key={m.seed}
                className={`flex items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] ${
                  isBest
                    ? "bg-accent-500/15 text-accent-400"
                    : "text-zinc-500"
                }`}
              >
                <span>#{m.seed}</span>
                <span>{m.units_count} szt.</span>
                <span>score {m.score.toFixed(3)}</span>
              </div>
            );
          })}
        </div>
      )}
```

(Wybór najlepszej: najniższy score — bez zależności od kanału odpowiedzi.)

- [ ] **Step 4: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/ProgramSection.tsx
git commit -m "feat: derived unit count display, weight slider, iteration list in Program panel"
```

---

### Task 4: Weryfikacja ręczna (spec §7)

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1–3
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. Mały obrys (~12×10m) → komunikacja → podział: kilka mieszkań. Duży
   (~40×15m): kilkanaście+. Liczba skaluje się z powierzchnią.
2. Pole „liczba mieszkań" zniknęło; readonly „≈ N mieszkań (M m² netto)".
3. Po podziale lista 10 iteracji ze score; najlepsza podświetlona; canvas
   pokazuje najlepszą.
4. Suwak 0 vs 1 → inne układy/score (przy tej samej geometrii).
5. Zero dziur: mieszkania + komunikacja + ściany pokrywają cały obrys
   (leftover null, brak nieprzydzielonych szarych pól).
6. Dwa uruchomienia z tymi samymi danymi → identyczne wyniki (determinizm).
7. Ścieżka „Generuj układ" (/generate) daje te same nowe pola co dwustopniowa.
8. Regresja: WT-walidacja, eksport, wall_bands.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
