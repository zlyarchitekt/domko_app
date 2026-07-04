# Etap 2b: Iteracyjny auto-placement klatek ze scoringiem — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przycisk „Rozmieść iteracyjnie": 10 seeded iteracji lokalizacji klatek (1..num_cages sztuk z puli kandydatów), scoring 5 wagami (egress/count/corners/ends/spread), wynik = najlepsza iteracja + lista w panelu. Stary tryb auto zostaje.

**Architecture:** Refactor wydziela z `place_circulation()` funkcję `_assemble_with_cages()` (korytarz+centerline+kropki dla ZADANEGO zestawu klatek). Nowy moduł `cage_placement.py`: pula kandydatów pozycji klatki, seeded losowanie zestawów, scoring, pętla iteracji wołająca `_assemble_with_cages`. Endpoint `/layout/circulation` przełącza się na tryb iteracyjny polem `cage_iterations > 0`; `/generate` analogicznie (dual-surface).

**Tech Stack:** shapely + stdlib `random` (backend), Next.js (frontend).

**Spec:** `docs/superpowers/specs/2026-07-04-cage-placement-iterations-design.md`
**Wymaga:** Etap 3 wdrożony (`compute_evacuation_dots` — komponent `egress`). Jeśli Etap 2 (manuale) wdrożony — jego blok merge musi zostać dostosowany (Task 1 Step 3).

## Global Constraints

- Wagi (0–1) z defaultami ze specu §2: `egress 1.0, count 0.5, corners 0.3, ends 0.3, spread 0.5`.
- Determinizm: iteracja `i` używa `random.Random(i)`; te same wejścia → ten sam wynik.
- `num_cages` = GÓRNY limit (iteracje losują 1..num_cages), nie sztywna liczba.
- Klatka: stałe `CAGE_WIDTH_M = 4.2` × `CAGE_DEPTH_M = 5.7` (`circulation.py:29-30`), obie orientacje.
- Progi dojść: edytowalne `max_dist_single_m`/`max_dist_multi_m` (Etap 3) — wspólne z kropkami.
- Testy backendu: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`. Frontend bez testów — typecheck `cd frontend && npx tsc --noEmit`.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001`.

---

### Task 1: Refactor — wydzielenie _assemble_with_cages z place_circulation

**Files:**
- Modify: `backend/services/circulation.py:427-546`
- Test: istniejąca suita (czysty refactor — zero zmian zachowania)

**Interfaces:**
- Consumes: istniejące wnętrze `place_circulation` (linie 496-546: remainder loop, centerline, distances, dots)
- Produces (używane w Tasku 2):
  - `_assemble_with_cages(footprint: Polygon, zones: list[Zone], local_cages: dict[int, Polygon], corridor_width_m: float, max_dist_single_m: float, max_dist_multi_m: float) -> CirculationResult` — buduje korytarze, centerline, odległości i kropki dla ZADANYCH klatek (klucz dict = indeks strefy)

- [ ] **Step 1: Wydziel funkcję**

Z `place_circulation` przenieś do nowej funkcji modułowej
`_assemble_with_cages` (nad `place_circulation`) DOKŁADNIE blok od
`remainder_parts: list[Polygon] = []` (linia 496) do zbudowania
`centerline` włącznie oraz liczenie kropek (z Etapu 3), kończąc
`return CirculationResult(zones=zones, circulation_geometry=...,
cage_polygons=..., remainder=..., centerline=..., evacuation_dots=...)`.

Wewnątrz: `circulation_geom` startuje jako
`unary_union(list(local_cages.values()))` (lub `Polygon()` gdy pusto),
`cage_polygons = list(local_cages.values())`. Sygnatura jak w
Interfaces.

`place_circulation` po swojej selekcji klatek (pętla `if place_cage:` do
linii 494) kończy się wywołaniem:

```python
    result = _assemble_with_cages(
        footprint, zones, local_cages, corridor_width_m,
        max_dist_single_m, max_dist_multi_m,
    )
```

- [ ] **Step 2: Zachowaj blok manuali (jeśli Etap 2 wdrożony)**

Blok dokładania `manual_cages`/`manual_corridors` (plan Etapu 2, Task 1)
zostaje w `place_circulation` ZA wywołaniem `_assemble_with_cages` i
mutuje pola `result` (`result.cage_polygons.append(...)`,
`result.circulation_geometry = unary_union([...])`,
`result.remainder = result.remainder.difference(...)`,
`result.centerline.append(...)`), po czym przelicza kropki
(`result.evacuation_dots = compute_evacuation_dots(...)` na pełnej
liście segmentów). Jeśli Etap 2 jeszcze nie wdrożony — pomiń ten krok.

- [ ] **Step 3: Regresja**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS — identyczne zachowanie (czysty refactor).

- [ ] **Step 4: Commit**

```bash
git add backend/services/circulation.py
git commit -m "refactor: extract _assemble_with_cages from place_circulation"
```

---

### Task 2: Moduł cage_placement.py — kandydaci, scoring, iteracje (TDD)

**Files:**
- Create: `backend/services/cage_placement.py`
- Test: `backend/tests/test_cage_placement.py` (nowy plik)

**Interfaces:**
- Consumes: `_assemble_with_cages`, `Zone`, `rectangle_decompose`, `CAGE_WIDTH_M`, `CAGE_DEPTH_M`, `compute_evacuation_dots` (pośrednio przez assembly)
- Produces (używane w Tasku 3):
  - `@dataclass CageWeights: egress=1.0; count=0.5; corners=0.3; ends=0.3; spread=0.5`
  - `@dataclass CageIterationMeta: seed: int; score: float; cages_count: int; components: dict`
  - `iterate_cage_placement(footprint: Polygon, corridor_width_m: float, num_cages: int, weights: CageWeights, iterations: int = 10, max_dist_single_m: float = 20.0, max_dist_multi_m: float = 40.0) -> tuple[CirculationResult, list[CageIterationMeta], int]` — (wynik najlepszej, metadane, best_seed); ValueError gdy zero kandydatów

- [ ] **Step 1: Napisz failing testy**

Utwórz `backend/tests/test_cage_placement.py`:

```python
"""Testy iteracyjnego auto-placementu klatek (spec 2026-07-04-cage-
placement-iterations §7)."""

import pytest
from shapely.geometry import Polygon

from services.cage_placement import CageWeights, iterate_cage_placement


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


FOOTPRINT = _rect(0, 0, 40, 12)


def test_determinism():
    a = iterate_cage_placement(FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5)
    b = iterate_cage_placement(FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5)
    assert [m.score for m in a[1]] == [m.score for m in b[1]]
    assert a[2] == b[2]


def test_respects_num_cages_filter():
    result, metas, _ = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=CageWeights(), iterations=10
    )
    assert 1 <= len(result.cage_polygons) <= 2
    assert all(1 <= m.cages_count <= 2 for m in metas)


def test_cages_inside_footprint():
    result, _, _ = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=5
    )
    for cage in result.cage_polygons:
        assert FOOTPRINT.buffer(1e-6).contains(cage)


def test_best_seed_lowest_score():
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=3, weights=CageWeights(), iterations=10
    )
    assert best_seed == min(metas, key=lambda m: m.score).seed


def test_egress_weight_prefers_fewer_red_dots():
    # długi budynek 80m: 1 klatka nie pokryje limitu 20m -> egress preferuje więcej klatek
    long_fp = _rect(0, 0, 80, 12)
    w = CageWeights(egress=1.0, count=0.0, corners=0.0, ends=0.0, spread=0.0)
    result, metas, best_seed = iterate_cage_placement(
        long_fp, 1.5, num_cages=4, weights=w, iterations=10
    )
    best = next(m for m in metas if m.seed == best_seed)
    assert best.components["egress"] == min(m.components["egress"] for m in metas)


def test_spread_prefers_separated_cages():
    w = CageWeights(egress=0.0, count=0.0, corners=0.0, ends=0.0, spread=1.0)
    _, metas, best_seed = iterate_cage_placement(
        FOOTPRINT, 1.5, num_cages=2, weights=w, iterations=10
    )
    best = next(m for m in metas if m.seed == best_seed)
    assert best.components["spread"] == min(m.components["spread"] for m in metas)


def test_footprint_too_small_raises():
    tiny = _rect(0, 0, 3, 3)  # mniejszy niż klatka 4.2x5.7
    with pytest.raises(ValueError, match="zbyt mały"):
        iterate_cage_placement(tiny, 1.5, num_cages=1, weights=CageWeights(), iterations=3)
```

- [ ] **Step 2: Uruchom testy — mają FAILować**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: `ModuleNotFoundError: No module named 'services.cage_placement'`

- [ ] **Step 3: Implementacja `backend/services/cage_placement.py`**

```python
"""Iteracyjny auto-placement klatek schodowych (spec 2026-07-04-cage-
placement-iterations). 10 seeded iteracji, scoring 5 wagami, wygrywa
najniższy score. Czyste funkcje + reużycie _assemble_with_cages."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from services.bsp import rectangle_decompose
from services.circulation import (
    CAGE_DEPTH_M,
    CAGE_WIDTH_M,
    CirculationResult,
    Zone,
    _assemble_with_cages,
)

CANDIDATE_EDGE_STEP_M = 5.0


@dataclass
class CageWeights:
    """5 wag scoringu lokalizacji klatek (spec §2, mapowanie z Finch)."""

    egress: float = 1.0
    count: float = 0.5
    corners: float = 0.3
    ends: float = 0.3
    spread: float = 0.5


@dataclass
class CageIterationMeta:
    seed: int
    score: float
    cages_count: int
    components: dict = field(default_factory=dict)


def _candidate_cages(footprint: Polygon, zones: list[Zone]) -> list[tuple[int, Polygon]]:
    """Pula kandydatów: (indeks_strefy, prostokąt klatki). Kotwice: narożniki
    bbox strefy, środki krawędzi bbox; obie orientacje klatki; tylko
    kandydaci w całości wewnątrz obrysu (spec §3.1)."""
    fp = footprint.buffer(1e-9)
    candidates: list[tuple[int, Polygon]] = []
    for zi, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        minx, miny, maxx, maxy = zone.polygon.bounds
        anchors = [
            (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
            ((minx + maxx) / 2, miny), ((minx + maxx) / 2, maxy),
            (minx, (miny + maxy) / 2), (maxx, (miny + maxy) / 2),
        ]
        # dodatkowe kotwice co ~5m wzdłuż dolnej/górnej krawędzi strefy
        x = minx + CANDIDATE_EDGE_STEP_M
        while x < maxx - 1e-6:
            anchors.append((x, miny))
            anchors.append((x, maxy))
            x += CANDIDATE_EDGE_STEP_M
        for ax, ay in anchors:
            for w, d in ((CAGE_WIDTH_M, CAGE_DEPTH_M), (CAGE_DEPTH_M, CAGE_WIDTH_M)):
                # prostokąt dosunięty do kotwicy w stronę wnętrza bbox strefy
                x0 = ax if ax + w <= maxx + 1e-6 else ax - w
                y0 = ay if ay + d <= maxy + 1e-6 else ay - d
                cage = box(x0, y0, x0 + w, y0 + d)
                if fp.contains(cage):
                    candidates.append((zi, cage))
    # deduplikacja po zaokrąglonych bounds
    seen: set = set()
    unique: list[tuple[int, Polygon]] = []
    for zi, cage in candidates:
        key = tuple(round(v, 3) for v in cage.bounds)
        if key not in seen:
            seen.add(key)
            unique.append((zi, cage))
    return unique


def _score_placement(
    result: CirculationResult, footprint: Polygon, num_cages: int, weights: CageWeights
) -> tuple[float, dict]:
    cages = result.cage_polygons
    k = len(cages)
    dots = result.evacuation_dots
    egress = (sum(1 for d in dots if d.status == "red") / len(dots)) if dots else 1.0
    count = k / num_cages if num_cages > 0 else 0.0

    minx, miny, maxx, maxy = footprint.bounds
    diag_half = math.hypot(maxx - minx, maxy - miny) / 2.0 or 1.0
    corner_pts = list(footprint.exterior.coords[:-1])
    corners_devs = []
    for c in cages:
        cx, cy = c.centroid.x, c.centroid.y
        d = min(math.hypot(cx - px, cy - py) for px, py in corner_pts)
        corners_devs.append(min(1.0, d / diag_half))
    corners = sum(corners_devs) / k if k else 1.0

    horizontal = (maxx - minx) >= (maxy - miny)
    axis_len = (maxx - minx) if horizontal else (maxy - miny)
    axis_len = axis_len or 1.0
    ts = sorted(
        ((c.centroid.x - minx) / axis_len if horizontal else (c.centroid.y - miny) / axis_len)
        for c in cages
    )
    ends = sum(min(t, 1.0 - t) * 2.0 for t in ts) / k if k else 1.0

    if k <= 1:
        spread = 0.0  # spec §2: 0 dla 1 klatki
    else:
        ideal = [(i + 0.5) / k for i in range(k)]
        spread = min(1.0, sum(abs(t - i) for t, i in zip(ts, ideal)) / k * 2.0)

    components = {"egress": egress, "count": count, "corners": corners, "ends": ends, "spread": spread}
    active = {"egress": weights.egress, "count": weights.count, "corners": weights.corners,
              "ends": weights.ends, "spread": weights.spread}
    total_w = sum(active.values())
    if total_w <= 0:
        return 0.0, components
    return sum(active[key] * components[key] for key in active) / total_w, components


def iterate_cage_placement(
    footprint: Polygon,
    corridor_width_m: float,
    num_cages: int,
    weights: CageWeights,
    iterations: int = 10,
    max_dist_single_m: float = 20.0,
    max_dist_multi_m: float = 40.0,
) -> tuple[CirculationResult, list[CageIterationMeta], int]:
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    candidates = _candidate_cages(footprint, zones)
    if not candidates:
        raise ValueError("Obrys zbyt mały na klatkę schodową")

    best: tuple[float, CirculationResult] | None = None
    metas: list[CageIterationMeta] = []
    for seed in range(iterations):
        rng = random.Random(seed)
        k = rng.randint(1, max(1, num_cages))
        pool = list(candidates)
        rng.shuffle(pool)
        # zachłannie bierz niekolidujące, max 1 klatka na strefę
        # (_assemble_with_cages dostaje dict {indeks_strefy: klatka})
        local_cages: dict[int, Polygon] = {}
        for zi, cage in pool:
            if len(local_cages) >= k:
                break
            if zi in local_cages:
                continue
            if any(cage.intersects(existing) for existing in local_cages.values()):
                continue
            local_cages[zi] = cage
        if not local_cages:
            continue
        result = _assemble_with_cages(
            footprint, zones, local_cages, corridor_width_m,
            max_dist_single_m, max_dist_multi_m,
        )
        score, components = _score_placement(result, footprint, num_cages, weights)
        metas.append(CageIterationMeta(seed=seed, score=score,
                                       cages_count=len(result.cage_polygons),
                                       components=components))
        if best is None or score < best[0]:
            best = (score, result)
    if best is None:
        raise ValueError("Obrys zbyt mały na klatkę schodową")
    best_seed = min(metas, key=lambda m: m.score).seed
    return best[1], metas, best_seed
```

UWAGA — ograniczenie „max 1 klatka na strefę" wynika z kontraktu
`_assemble_with_cages` (dict indeksowany strefą, jak w dzisiejszym
`place_circulation`). Przy małej liczbie stref ogranicza k — cichy cap,
spójny z istniejącym zachowaniem num_cages (spec 2026-07-04-cage-corridor
-placement-quality §3.1).

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/cage_placement.py backend/tests/test_cage_placement.py
git commit -m "feat: iterative cage placement - candidate pool, 5-weight scoring, seeded iterations"
```

---

### Task 3: API — tryb iteracyjny w obu ścieżkach

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (`CirculationSpec` :26-36, `CirculationResponse` :267-271, `place_circulation_endpoint` :274-308, `generate_layout_endpoint`/`layout_result_to_response`)
- Modify: `backend/services/layout.py` (`LayoutInput`, `LayoutResult`, `generate_layout`)
- Test: `backend/tests/test_cage_placement.py` (dopisanie)

**Interfaces:**
- Consumes: `iterate_cage_placement`, `CageWeights`, `CageIterationMeta` (Task 2)
- Produces:
  - `CirculationSpec.cage_iterations: int = 0 (ge=0, le=50)` — 0 = tryb klasyczny
  - `CirculationSpec.cage_weights: CageWeightsInput`
  - odpowiedzi (`CirculationResponse` + `LayoutGenerateResponse`): `cage_iterations: list[CageIterationMetaResult]`, `cage_best_seed: int`

- [ ] **Step 1: Failing test endpointu**

Dopisz do `backend/tests/test_cage_placement.py`:

```python
def test_circulation_endpoint_iterative_mode():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 3,
            "cage_iterations": 10,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 1
    assert body["cage_best_seed"] in [m["seed"] for m in body["cage_iterations"]]
    assert body["cage_geometries"]
```

(Prefiks `/api/v1` zweryfikuj jak w pozostałych planach.)

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -k endpoint -v`
Expected: FAIL.

- [ ] **Step 2: Modele + endpoint /circulation**

`layout.py` (endpoints) — nowe modele:

```python
class CageWeightsInput(BaseModel):
    egress: float = Field(default=1.0, ge=0, le=1)
    count: float = Field(default=0.5, ge=0, le=1)
    corners: float = Field(default=0.3, ge=0, le=1)
    ends: float = Field(default=0.3, ge=0, le=1)
    spread: float = Field(default=0.5, ge=0, le=1)


class CageIterationMetaResult(BaseModel):
    seed: int
    score: float
    cages_count: int
    components: dict[str, float] = {}
```

`CirculationSpec` — dodaj:

```python
    cage_iterations: int = Field(default=0, ge=0, le=50)
    """0 = klasyczny auto-placement; >0 = tryb iteracyjny (spec §4)."""
    cage_weights: CageWeightsInput = Field(default_factory=CageWeightsInput)
```

`CirculationResponse` — dodaj:

```python
    cage_iterations: list[CageIterationMetaResult] = []
    cage_best_seed: int = 0
```

`place_circulation_endpoint` — po walidacji `cage_position`, gałąź:

```python
    cage_iteration_metas: list = []
    cage_best_seed = 0
    if circulation.cage_iterations > 0:
        from services.cage_placement import CageWeights, iterate_cage_placement

        try:
            result, cage_iteration_metas, cage_best_seed = iterate_cage_placement(
                footprint,
                corridor_width_m=circulation.corridor_width_m,
                num_cages=circulation.num_cages,
                weights=CageWeights(**circulation.cage_weights.model_dump()),
                iterations=circulation.cage_iterations,
                max_dist_single_m=circulation.max_dist_single_m,
                max_dist_multi_m=circulation.max_dist_multi_m,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        # manuale (Etap 2) dokładane do result tak samo jak w trybie
        # klasycznym -- przenieś/reużyj blok merge z place_circulation,
        # wołając go na result (patrz Task 1 Step 2 tego planu).
    else:
        result = place_circulation(...)  # istniejące wywołanie bez zmian
```

W konstruktorze odpowiedzi:

```python
        cage_iterations=[
            CageIterationMetaResult(seed=m.seed, score=m.score,
                                    cages_count=m.cages_count, components=m.components)
            for m in cage_iteration_metas
        ],
        cage_best_seed=cage_best_seed,
```

- [ ] **Step 3: Ścieżka /generate (dual-surface)**

`services/layout.py`: `LayoutInput` + `cage_iterations: int = 0` i
`cage_weights: object = None`; `LayoutResult` + `cage_iteration_metas:
list = field(default_factory=list)` i `cage_best_seed: int = 0`.
W `generate_layout`: gdy `input.cage_iterations > 0` — komunikacja przez
`iterate_cage_placement` (parametry jak wyżej) zamiast `place_circulation`;
metadane do `LayoutResult`. `generate_layout_endpoint` mapuje pola z
`request.circulation`; `layout_result_to_response` serializuje
`cage_iterations`/`cage_best_seed` do `LayoutGenerateResponse` (dodaj oba
pola do modelu odpowiedzi, defaulty `[]`/`0`).

- [ ] **Step 4: Testy + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS.

```bash
git add backend/api/v1/endpoints/layout.py backend/services/layout.py backend/tests/test_cage_placement.py
git commit -m "feat: iterative cage placement mode through /layout/circulation and /generate"
```

---

### Task 4: Frontend — przycisk, 5 suwaków, lista iteracji

**Files:**
- Modify: `frontend/app/lib/api.ts` (`CirculationSpecInput`, `CirculationResponse`)
- Modify: `frontend/app/state/SessionContext.tsx` (initialCirculation, stan wag)
- Modify: `frontend/app/components/CirculationSection.tsx`

**Interfaces:**
- Consumes: pola API z Task 3, `runPlaceCirculation(overrides)` (Etap 2) lub bez overrides
- Produces: kompletne UI Etapu 2b

- [ ] **Step 1: api.ts**

```ts
export interface CageWeightsInput {
  egress: number;
  count: number;
  corners: number;
  ends: number;
  spread: number;
}

export interface CageIterationMeta {
  seed: number;
  score: number;
  cages_count: number;
  components?: Record<string, number>;
}
```

`CirculationSpecInput` — dodaj `cage_iterations: number; cage_weights:
CageWeightsInput;`. `CirculationResponse` — dodaj `cage_iterations?:
CageIterationMeta[]; cage_best_seed?: number;` (opcjonalne w TS).

- [ ] **Step 2: SessionContext**

`initialCirculation` — dodaj:

```ts
  cage_iterations: 0,
  cage_weights: { egress: 1.0, count: 0.5, corners: 0.3, ends: 0.3, spread: 0.5 },
```

Tryb iteracyjny NIE wymaga nowego callbacku: przycisk ustawia
`setCirculation({ cage_iterations: 10 })` i woła `runPlaceCirculation()`?
NIE — stale closure. Zamiast tego `runPlaceCirculation` dostaje (obok
overrides z Etapu 2) opcjonalny parametr `circulationOverride?:
Partial<api.CirculationSpecInput>` scalany do wysyłanego spec:

```ts
        const result = await api.placeCirculation(footprintToPoints(state.footprint), {
          ...state.circulation,
          ...(overrides?.circulationOverride ?? {}),
          manual_cages: ...,   // jak w Etapie 2
          manual_corridors: ...,
        });
```

(Jeśli Etap 2 nie jest wdrożony — dodaj sam parametr `circulationOverride`
analogicznie.)

- [ ] **Step 3: Panel Komunikacja**

Przycisk (obok „Umieść korytarz i klatkę"):

```tsx
        <button
          onClick={() => void runPlaceCirculation({ circulationOverride: { cage_iterations: 10 } })}
          disabled={!state.footprint || state.isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-500 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-accent-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
          title="10 iteracji lokalizacji klatek, wygrywa najlepszy score wg wag"
        >
          {state.isLoading ? "Iteruję..." : "Rozmieść iteracyjnie"}
        </button>
```

Sekcja suwaków (zwijana `<details>` — panel jest gęsty):

```tsx
      <details className="pt-1">
        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Wagi klatek
        </summary>
        <div className="space-y-1.5 pt-1.5">
          {(
            [
              ["egress", "Minimalizuj złe dojścia"],
              ["count", "Minimalizuj liczbę klatek"],
              ["corners", "Klatki w narożnikach"],
              ["ends", "Klatki na końcach"],
              ["spread", "Równomierne rozmieszczenie"],
            ] as [keyof api.CageWeightsInput, string][]
          ).map(([key, label]) => (
            <label key={key} className="flex items-center justify-between text-xs text-zinc-400">
              <span>{label} ({state.circulation.cage_weights[key].toFixed(2)})</span>
              <input
                type="range" min={0} max={1} step={0.05}
                value={state.circulation.cage_weights[key]}
                onChange={(e) =>
                  setCirculation({
                    cage_weights: { ...state.circulation.cage_weights, [key]: Number(e.target.value) },
                  })
                }
                className="ml-2 w-24 accent-accent-500"
              />
            </label>
          ))}
        </div>
      </details>
```

Lista iteracji (pod przyciskami, ten sam wzorzec co lista mieszkań
z Etapu 4):

```tsx
      {(state.circulationResult?.cage_iterations?.length ?? 0) > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje klatek ({state.circulationResult!.cage_iterations!.length})
          </div>
          {state.circulationResult!.cage_iterations!.map((m) => (
            <div
              key={m.seed}
              className={`flex items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] ${
                m.seed === (state.circulationResult!.cage_best_seed ?? -1)
                  ? "bg-accent-500/15 text-accent-400"
                  : "text-zinc-500"
              }`}
            >
              <span>#{m.seed}</span>
              <span>{m.cages_count} klatek</span>
              <span>score {m.score.toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}
```

- [ ] **Step 4: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: iterative cage placement button, weight sliders, iteration list"
```

---

### Task 5: Weryfikacja ręczna (spec §7)

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1–4 (+ Etapy 2 i 3 wdrożone)
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. Prostokąt 40×12, num_cages=3 → „Rozmieść iteracyjnie" → lista 10
   iteracji, najlepsza podświetlona, klatki w sensownych miejscach.
2. `egress=1` reszta 0 → wynik z minimalną liczbą czerwonych kropek.
3. `corners=1` reszta 0 → klatki w narożnikach; `ends=1` → na końcach;
   `spread=1` (num_cages≥2) → rozsunięte.
4. Zmiana progów dojść (Etap 3) + ponowne „Rozmieść iteracyjnie" → inny
   zwycięzca, spójny z kropkami.
5. Stary przycisk „Umieść korytarz i klatkę" działa jak dotychczas
   (`cage_iterations` w spec pozostaje 0).
6. Manuale (Etap 2) przeżywają rozmieszczenie iteracyjne.
7. Obrys 3×3m → czerwony błąd 422 „Obrys zbyt mały...".

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
