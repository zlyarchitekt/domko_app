# Etap 4: Podział na mieszkania — liczba z powierzchni, iteracje, zero resztek, 7 wag — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Liczba mieszkań wyliczana z powierzchni i struktury % (pole input znika), 10 iteracji podziału z deterministycznym seedem, zero resztek, scoring wielokryterialny z 7 wagami (Size m², Unit Mix, Grid lines, Shape aware, Daylight, Squareness, Adjacency — mapowanie z Finch3D zaakceptowane 2026-07-04) i lista iteracji w panelu.

**Architecture:** Nowa funkcja `iterate_units()` w `unit_mix.py` owija istniejący `fit_program_to_rectangles()` (dostaje opcjonalny `rng` do tasowania), po każdej iteracji skleja leftover z sąsiadami i liczy `score = Σ wᵢ·devᵢ / Σ wᵢ` z 7 komponentów. Komponenty `daylight`/`adjacency` wymagają obrysu i geometrii komunikacji — gdy brak w requeście, są pomijane (wypadają z Σwᵢ). Oba endpointy (`/layout/units`, `/layout/generate`) dostają `iterations`/`weights` i zwracają metadane iteracji (dual-surface gotcha).

**Tech Stack:** shapely + stdlib `random` (backend), Next.js (frontend).

**Spec:** `docs/superpowers/specs/2026-07-04-apartment-division-iterations-design.md` (Sekcja 4 = tabela wag)
**Niezależny od** Etapów 2–3 (konsumuje tylko `remainder` + opcjonalnie geometrię komunikacji); może być wdrażany równolegle.

## Global Constraints

- Domyślnie `iterations = 10` (zakres 1–50).
- Wagi (0–1) z defaultami ze specu §4: `size 0.8, mix 0.6, grid 0.3, shape 0.5, daylight 0.7, squareness 0.5, adjacency 1.0`.
- Determinizm: iteracja `i` używa `random.Random(i)`.
- Zero resztek: po `iterate_units()` leftover ZAWSZE None; pole `leftover` w odpowiedziach zostaje (kompat), zawsze null.
- Kara `merged_disjoint`: +0.5 do komponentu `adjacency` danego mieszkania (spec §3/§4).
- Struktura % normalizowana do sumy; wszystkie wiersze 0% → 422.
- Testy backendu: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`. Frontend bez testów automatycznych — typecheck `cd frontend && npx tsc --noEmit`.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001`.

---

### Task 1: unit_mix — rng, merge leftover, scoring 7-komponentowy, iterate_units (TDD)

**Files:**
- Modify: `backend/services/unit_mix.py` (dopisanie funkcji; `fit_program_to_rectangles` dostaje `rng`)
- Modify: `backend/services/layout.py:94-107` (`ApartmentCell` — pole `merged_disjoint`)
- Test: `backend/tests/test_unit_iterations.py` (nowy plik)

**Interfaces:**
- Consumes: `fit_program_to_rectangles`, `rectangle_decompose`, `ApartmentSpec`, `ApartmentCell`, `net_polygon`
- Produces (używane w Tasku 2):
  - `ApartmentCell.merged_disjoint: bool = False`
  - `@dataclass ProgramShare: type: str; percentage: float; area_min_m2: float; area_max_m2: float`
  - `@dataclass UnitWeights: size=0.8; mix=0.6; grid=0.3; shape=0.5; daylight=0.7; squareness=0.5; adjacency=1.0` (wszystkie float)
  - `@dataclass IterationMeta: seed: int; score: float; units_count: int; components: dict[str, float]`
  - `derive_total_units(net_remainder_m2: float, shares: list[ProgramShare]) -> int`
  - `allocate_counts(shares: list[ProgramShare], total_units: int) -> dict[str, int]` (largest-remainder)
  - `iterate_units(remainder, shares, iterations: int = 10, weights: UnitWeights | None = None, footprint: Polygon | None = None, circulation_geometry=None) -> tuple[list[ApartmentCell], list[IterationMeta], int, int]` — (komórki najlepszej, metadane, best_seed, derived_total_units)
  - `fit_program_to_rectangles(rectangles, specs, rng: random.Random | None = None)` — wstecznie zgodne

- [ ] **Step 1: Napisz failing testy**

Utwórz `backend/tests/test_unit_iterations.py`:

```python
"""Testy iteracyjnego podziału na mieszkania (spec 2026-07-04-apartment-
division-iterations §7, scoring 7-wagowy z §4)."""

from shapely.geometry import Polygon

from services.layout import ApartmentCell
from services.unit_mix import (
    ProgramShare,
    UnitWeights,
    _score_iteration,
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
    assert counts["M2"] >= 2 and counts["M3"] >= 2


def test_zero_leftover_guarantee():
    remainder = _rect(0, 0, 24, 10)  # 240 m2
    cells, metas, best_seed, derived_total = iterate_units(remainder, SHARES, iterations=5)
    assert cells
    assert derived_total >= 1
    total_cells_area = sum(c.polygon.area for c in cells)
    assert abs(total_cells_area - remainder.area) < 1e-6
    assert len(metas) == 5
    assert best_seed in {m.seed for m in metas}


def test_determinism_same_seed_same_result():
    remainder = _rect(0, 0, 24, 10)
    cells_a, metas_a, _, _ = iterate_units(remainder, SHARES, iterations=3)
    cells_b, metas_b, _, _ = iterate_units(remainder, SHARES, iterations=3)
    assert [m.score for m in metas_a] == [m.score for m in metas_b]
    assert [c.polygon.wkt for c in cells_a] == [c.polygon.wkt for c in cells_b]


def test_best_seed_has_lowest_score():
    remainder = _rect(0, 0, 30, 11)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=10)
    best = min(metas, key=lambda m: m.score)
    assert best.seed == best_seed


def test_single_weight_score_equals_component():
    remainder = _rect(0, 0, 24, 10)
    only_mix = UnitWeights(size=0, mix=1, grid=0, shape=0, daylight=0, squareness=0, adjacency=0)
    only_size = UnitWeights(size=1, mix=0, grid=0, shape=0, daylight=0, squareness=0, adjacency=0)
    _, metas_mix, _, _ = iterate_units(remainder, SHARES, iterations=3, weights=only_mix)
    _, metas_size, _, _ = iterate_units(remainder, SHARES, iterations=3, weights=only_size)
    assert all(abs(m.score - m.components["mix"]) < 1e-9 for m in metas_mix)
    assert all(abs(m.score - m.components["size"]) < 1e-9 for m in metas_size)


def test_geometric_components_on_crafted_cells():
    # kwadrat 6x6 na siatce: grid=0, shape=0 (prostokąt), squareness=0 (kwadrat)
    square = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 6, 6))
    # 6x15: proporcja 2.5:1 -> squareness = 1.0; poza siatką: wierzchołek 0.3
    long_off = ApartmentCell(id="b", type="M2", polygon=_rect(0.3, 0, 6.3, 15))
    shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=100)]
    w = UnitWeights(size=0, mix=0, grid=1, shape=0, daylight=0, squareness=0, adjacency=0)
    score_sq, comp_sq = _score_iteration([square], shares, w, None, None)
    score_lo, comp_lo = _score_iteration([long_off], shares, w, None, None)
    assert comp_sq["grid"] == 0.0
    assert comp_lo["grid"] > 0.0
    assert comp_sq["squareness"] == 0.0
    assert comp_lo["squareness"] >= 0.99


def test_min_facade_per_type_drives_daylight():
    # komórka 6x6 przy lewej krawędzi obrysu 20x6 dzieli z exterior obrysu
    # lewą (6m), dolną (6m) i górną (6m) krawędź = ~18m styku.
    # Próg 3m -> spełniony (dev 0); próg 25m -> niespełniony (dev 1).
    fp = _rect(0, 0, 20, 6)
    cell = ApartmentCell(id="a", type="M2", polygon=_rect(0, 0, 6, 6))
    w = UnitWeights(size=0, mix=0, grid=0, shape=0, daylight=1, squareness=0, adjacency=0)
    ok_shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=40, min_facade_m=3.0)]
    hi_shares = [ProgramShare(type="M2", percentage=100, area_min_m2=30, area_max_m2=40, min_facade_m=25.0)]
    _, comp_ok = _score_iteration([cell], ok_shares, w, fp, None)
    _, comp_hi = _score_iteration([cell], hi_shares, w, fp, None)
    assert comp_ok["daylight"] == 0.0
    assert comp_hi["daylight"] == 1.0


def test_merged_disjoint_raises_adjacency():
    circulation = _rect(10, 0, 12, 6)
    touching = ApartmentCell(id="a", type="M2", polygon=_rect(6, 0, 10, 6))
    disjoint = ApartmentCell(id="b", type="M2", polygon=_rect(6, 0, 10, 6))
    disjoint.merged_disjoint = True
    shares = [ProgramShare(type="M2", percentage=100, area_min_m2=20, area_max_m2=30)]
    w = UnitWeights(size=0, mix=0, grid=0, shape=0, daylight=0, squareness=0, adjacency=1)
    _, comp_ok = _score_iteration([touching], shares, w, None, circulation)
    _, comp_bad = _score_iteration([disjoint], shares, w, None, circulation)
    assert comp_ok["adjacency"] == 0.0
    assert abs(comp_bad["adjacency"] - 0.5) < 1e-9  # styka się, ale kara za enklawę
```

- [ ] **Step 2: Uruchom testy — mają FAILować**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`
Expected: `ImportError: cannot import name 'ProgramShare'`

- [ ] **Step 3: `ApartmentCell.merged_disjoint`**

W `backend/services/layout.py`, dataclass `ApartmentCell` (po `net_area_m2`,
linia 107):

```python
    merged_disjoint: bool = False
    """True gdy zero-leftover merge dokleił do tej komórki część bez wspólnej
    krawędzi (enklawę) -- kara +0.5 w komponencie adjacency scoringu, spec
    2026-07-04-apartment-division-iterations §3."""
```

- [ ] **Step 4: Implementacja w unit_mix.py**

Importy na górze: `import math`, `import random`,
`from dataclasses import dataclass, field, asdict` oraz:

```python
@dataclass
class ProgramShare:
    """Wiersz struktury % (spec §1): sztuki wynikają z powierzchni budynku,
    nie z pola usera."""

    type: str
    percentage: float
    area_min_m2: float
    area_max_m2: float
    min_facade_m: float = 3.0
    """Minimalny styk mieszkania tego typu ze ścianą zewnętrzną (spec §4,
    komponent daylight) -- per typ, pomysł usera ze screena Finch
    'Min facade length'."""


@dataclass
class UnitWeights:
    """7 wag scoringu (spec §4, mapowanie z Finch 'Unit weights')."""

    size: float = 0.8
    mix: float = 0.6
    grid: float = 0.3
    shape: float = 0.5
    daylight: float = 0.7
    squareness: float = 0.5
    adjacency: float = 1.0


@dataclass
class IterationMeta:
    seed: int
    score: float
    units_count: int
    components: dict = field(default_factory=dict)
    """dev per waga: {"size": ..., "mix": ..., ...} -- 0 = idealnie."""
```

`derive_total_units` i `allocate_counts` (spec §1):

```python
def derive_total_units(net_remainder_m2: float, shares: list[ProgramShare]) -> int:
    total_pct = sum(s.percentage for s in shares)
    if total_pct <= 0:
        raise ValueError("Struktura mieszkań: wszystkie udziały procentowe są zerowe")
    avg = sum((s.percentage / total_pct) * (s.area_min_m2 + s.area_max_m2) / 2.0 for s in shares)
    if avg <= 0:
        raise ValueError("Struktura mieszkań: nieprawidłowe przedziały wielkości")
    return max(1, math.floor(net_remainder_m2 / avg))


def allocate_counts(shares: list[ProgramShare], total_units: int) -> dict[str, int]:
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

`fit_program_to_rectangles` — sygnatura (linia 37) dostaje `rng:
random.Random | None = None`, a po zbudowaniu `queue` (linia 46):

```python
    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(rectangles := list(rectangles))
```

(kopia lokalna — lista wywołującego nietknięta; bez rng zachowanie
w 100% dotychczasowe).

Merge resztek (spec §3):

```python
def _merge_leftover_into_cells(cells: list[ApartmentCell], leftover) -> None:
    """Zero resztek: część leftover -> mieszkanie o najdłuższej wspólnej
    krawędzi; bez sąsiada -> najbliższe mieszkanie + merged_disjoint.
    Mutuje cells in-place."""
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

Scoring 7-komponentowy (spec §4). Komponenty per mieszkanie liczone na
SUROWYCH poligonach (`cell.polygon`), 0 = idealnie:

```python
_GRID_M = 0.5
_DAYLIGHT_MIN_CONTACT_M = 3.0
_SQUARENESS_CAP_RATIO = 2.5


def _cell_geometry_devs(cell: ApartmentCell) -> tuple[float, float, float]:
    """(grid, shape, squareness) dla jednej komórki."""
    polys = list(cell.polygon.geoms) if hasattr(cell.polygon, "geoms") else [cell.polygon]
    coords = [pt for p in polys for pt in p.exterior.coords[:-1]]
    off = sum(
        1
        for x, y in coords
        if abs(x - round(x / _GRID_M) * _GRID_M) > 1e-6 or abs(y - round(y / _GRID_M) * _GRID_M) > 1e-6
    )
    grid = off / len(coords) if coords else 0.0

    mrr = cell.polygon.minimum_rotated_rectangle
    shape = max(0.0, 1.0 - cell.polygon.area / mrr.area) if mrr.area > 1e-9 else 0.0

    xs = [pt[0] for pt in mrr.exterior.coords[:-1]]
    ys = [pt[1] for pt in mrr.exterior.coords[:-1]]
    import math as _m
    side_a = _m.hypot(xs[1] - xs[0], ys[1] - ys[0])
    side_b = _m.hypot(xs[2] - xs[1], ys[2] - ys[1])
    longer, shorter = max(side_a, side_b), min(side_a, side_b)
    ratio = longer / shorter if shorter > 1e-9 else _SQUARENESS_CAP_RATIO
    squareness = min(1.0, max(0.0, (ratio - 1.0) / (_SQUARENESS_CAP_RATIO - 1.0)))
    return grid, shape, squareness


def _score_iteration(
    cells: list[ApartmentCell],
    shares: list[ProgramShare],
    weights: UnitWeights,
    footprint: Polygon | None,
    circulation_geometry,
) -> tuple[float, dict]:
    """(score, components) -- spec §4. daylight bez footprint i adjacency
    bez circulation_geometry są pomijane (wypadają z sumy wag)."""
    n = len(cells) or 1
    total_pct = sum(s.percentage for s in shares) or 1.0

    mix = sum(
        abs(s.percentage / total_pct - sum(1 for c in cells if c.type == s.type) / n)
        for s in shares
    )

    bounds = {s.type: (s.area_min_m2, s.area_max_m2) for s in shares}
    size_devs = []
    for c in cells:
        lo, hi = bounds.get(c.type, (0.0, float("inf")))
        area = c.polygon.area
        if lo > 0 and area < lo:
            size_devs.append((lo - area) / lo)
        elif hi > 0 and area > hi:
            size_devs.append((area - hi) / hi)
        else:
            size_devs.append(0.0)
    size = sum(size_devs) / n

    geo = [_cell_geometry_devs(c) for c in cells]
    grid = sum(g[0] for g in geo) / n
    shape = sum(g[1] for g in geo) / n
    squareness = sum(g[2] for g in geo) / n

    components = {"size": size, "mix": mix, "grid": grid, "shape": shape, "squareness": squareness}
    active = {
        "size": weights.size, "mix": weights.mix, "grid": weights.grid,
        "shape": weights.shape, "squareness": weights.squareness,
    }

    if footprint is not None:
        edge = footprint.exterior.buffer(0.01)
        facade_min = {s.type: s.min_facade_m for s in shares}
        short_contact = sum(
            1
            for c in cells
            if c.polygon.boundary.intersection(edge).length
            < facade_min.get(c.type, _DAYLIGHT_MIN_CONTACT_M)
        )
        components["daylight"] = short_contact / n
        active["daylight"] = weights.daylight

    if circulation_geometry is not None and not circulation_geometry.is_empty:
        adj_devs = []
        for c in cells:
            base = 0.0 if c.polygon.distance(circulation_geometry) < 0.01 else 1.0
            if c.merged_disjoint:
                base += 0.5
            adj_devs.append(base)
        components["adjacency"] = sum(adj_devs) / n
        active["adjacency"] = weights.adjacency

    total_w = sum(active.values())
    if total_w <= 0:
        return 0.0, components
    score = sum(active[k] * components[k] for k in active) / total_w
    return score, components
```

Główna pętla:

```python
def iterate_units(
    remainder: Polygon | MultiPolygon,
    shares: list[ProgramShare],
    iterations: int = 10,
    weights: UnitWeights | None = None,
    footprint: Polygon | None = None,
    circulation_geometry=None,
) -> tuple[list[ApartmentCell], list[IterationMeta], int, int]:
    """Iteracyjny podział (spec §2): seeded przebiegi, zero-leftover merge,
    scoring 7-wagowy, wygrywa najniższy score."""
    weights = weights or UnitWeights()
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
            import uuid as _uuid
            from services.layout import ApartmentCell as _Cell

            whole = remainder if remainder.geom_type == "Polygon" else unary_union(remainder)
            cells = [_Cell(id=str(_uuid.uuid4()), type=shares[0].type, polygon=whole)]
            cells[0].net_area_m2 = net_area
        score, components = _score_iteration(cells, shares, weights, footprint, circulation_geometry)
        metas.append(IterationMeta(seed=seed, score=score, units_count=len(cells), components=components))
        if best is None or score < best[0]:
            best = (score, cells)
    best_seed = min(metas, key=lambda m: m.score).seed
    return best[1], metas, best_seed, total_units
```

- [ ] **Step 5: Uruchom testy — mają przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py tests/test_layout.py -v`
Expected: wszystkie PASS (stare bez regresji — `fit_program_to_rectangles`
bez rng identyczne).

- [ ] **Step 6: Commit**

```bash
git add backend/services/unit_mix.py backend/services/layout.py backend/tests/test_unit_iterations.py
git commit -m "feat: iterate_units - seeded iterations, zero-leftover merge, 7-weight scoring"
```

---

### Task 2: API — oba endpointy z iteracjami, wagami i strukturą %

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (`ApartmentProgram` :18-23, `LayoutGenerateRequest` :38-42, `UnitsRequest` :311-323, `UnitsResponse` :326-332, `LayoutGenerateResponse` :68-84, `subdivide_units_endpoint` :335-405, `generate_layout_endpoint` :87, `layout_result_to_response` :134)
- Modify: `backend/services/layout.py` (`LayoutInput` :81-91, `LayoutResult` :110-127, `generate_layout` :130-)
- Test: `backend/tests/test_unit_iterations.py` (dopisanie)

**Interfaces:**
- Consumes: `iterate_units`, `ProgramShare`, `UnitWeights`, `IterationMeta` (Task 1)
- Produces:
  - `ApartmentProgram` + `percentage: float = 0`, `area_min_m2: float = 0`, `area_max_m2: float = 0` (stare pola zostają — kompat)
  - `UnitsRequest`/`LayoutGenerateRequest` + `iterations: int = 10 (ge=1, le=50)`, `weights: UnitWeightsInput`
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
        "weights": {"size": 1.0, "mix": 1.0, "grid": 0, "shape": 0,
                    "daylight": 0, "squareness": 0, "adjacency": 0},
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
`main.py` — jeśli inny, dostosuj URL.)

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -k endpoint -v`
Expected: FAIL (pola nie istnieją).

- [ ] **Step 2: Modele request/response**

`ApartmentProgram` (linia 18) — dodaj:

```python
    percentage: float = Field(default=0.0, ge=0)
    area_min_m2: float = Field(default=0.0, ge=0)
    area_max_m2: float = Field(default=0.0, ge=0)
    min_facade_m: float = Field(default=3.0, ge=0)
    """Min. styk typu ze ścianą zewnętrzną [m] -- komponent daylight."""
```

Nowe modele (obok pozostałych):

```python
class UnitWeightsInput(BaseModel):
    """7 wag scoringu (spec §4) -- defaulty jak services.unit_mix.UnitWeights."""

    size: float = Field(default=0.8, ge=0, le=1)
    mix: float = Field(default=0.6, ge=0, le=1)
    grid: float = Field(default=0.3, ge=0, le=1)
    shape: float = Field(default=0.5, ge=0, le=1)
    daylight: float = Field(default=0.7, ge=0, le=1)
    squareness: float = Field(default=0.5, ge=0, le=1)
    adjacency: float = Field(default=1.0, ge=0, le=1)


class IterationMetaResult(BaseModel):
    seed: int
    score: float
    units_count: int
    components: dict[str, float] = {}
```

`UnitsRequest` i `LayoutGenerateRequest` — dodaj:

```python
    iterations: int = Field(default=10, ge=1, le=50)
    weights: UnitWeightsInput = Field(default_factory=UnitWeightsInput)
```

`UnitsResponse` i `LayoutGenerateResponse` — dodaj:

```python
    derived_total_units: int = 0
    net_remainder_m2: float = 0.0
    iterations: list[IterationMetaResult] = []
    best_seed: int = 0
```

- [ ] **Step 3: subdivide_units_endpoint na iterate_units**

W `subdivide_units_endpoint` — footprint i circulation_geometry są dziś
parsowane dopiero w bloku wall_bands (linie 365-376); PRZENIEŚ oba parsy
przed podział (potrzebne do daylight/adjacency), reszta bloku wall_bands
używa już sparsowanych. Zamień budowę specs i wywołanie (linie 345-353):

```python
    shares = [
        ProgramShare(
            type=a.type,
            percentage=a.percentage,
            area_min_m2=a.area_min_m2 or a.min_area_m2,
            area_max_m2=a.area_max_m2 or a.min_area_m2,
            min_facade_m=a.min_facade_m,
        )
        for a in request.apartments
    ]
    weights = UnitWeights(**request.weights.model_dump())
    try:
        cells, iteration_metas, best_seed, derived_total = iterate_units(
            remainder, shares,
            iterations=request.iterations, weights=weights,
            footprint=footprint, circulation_geometry=circulation_geometry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    leftover = None  # iterate_units gwarantuje zero resztek (spec §3)
```

(importy: `from services.unit_mix import ProgramShare, UnitWeights,
iterate_units`; `footprint`/`circulation_geometry` mogą być None — wtedy
daylight/adjacency pomijane, spec §4).

Net remainder do odpowiedzi:

```python
    if hasattr(remainder, "geoms"):
        net_remainder_m2 = sum(net_polygon(p).area for p in remainder.geoms)
    else:
        net_remainder_m2 = net_polygon(remainder).area
```

(import `net_polygon` z `services.wall_geometry`). W `return
UnitsResponse(...)`:

```python
        derived_total_units=derived_total,
        net_remainder_m2=net_remainder_m2,
        iterations=[
            IterationMetaResult(seed=m.seed, score=m.score, units_count=m.units_count, components=m.components)
            for m in iteration_metas
        ],
        best_seed=best_seed,
```

UWAGA: gałąź `wall_bands` odejmująca `leftover` (linie 389-397) przestaje
się wykonywać (leftover zawsze None) — NIE usuwaj jej (mniejszy diff).

- [ ] **Step 4: Ścieżka /generate (dual-surface)**

`services/layout.py`:

`LayoutInput` — dodaj:

```python
    iterations: int = 10
    unit_weights: object = None
    """services.unit_mix.UnitWeights | None."""
    program_shares: list = field(default_factory=list)
    """list[ProgramShare] -- gdy niepuste, generate_layout używa iterate_units."""
```

`LayoutResult` — dodaj:

```python
    iteration_metas: list = field(default_factory=list)
    best_seed: int = 0
    derived_total_units: int = 0
    net_remainder_m2: float = 0.0
```

W `generate_layout` (linia 156) zamień `subdivide_units(...)`:

```python
    if input.program_shares:
        from services.unit_mix import UnitWeights, iterate_units
        from services.wall_geometry import net_polygon as _np

        apartments, iteration_metas, best_seed, derived_total_units = iterate_units(
            circulation.remainder, input.program_shares,
            iterations=input.iterations,
            weights=input.unit_weights or UnitWeights(),
            footprint=footprint,
            circulation_geometry=circulation.circulation_geometry,
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

W `generate_layout_endpoint` — przy budowie `LayoutInput`:

```python
        iterations=request.iterations,
        unit_weights=UnitWeights(**request.weights.model_dump()),
        program_shares=[
            ProgramShare(
                type=a.type, percentage=a.percentage,
                area_min_m2=a.area_min_m2 or a.min_area_m2,
                area_max_m2=a.area_max_m2 or a.min_area_m2,
                min_facade_m=a.min_facade_m,
            )
            for a in request.apartments
            if a.percentage > 0
        ],
```

W `layout_result_to_response` dodaj do konstruktora odpowiedzi:

```python
        derived_total_units=layout.derived_total_units,
        net_remainder_m2=layout.net_remainder_m2,
        iterations=[
            IterationMetaResult(seed=m.seed, score=m.score, units_count=m.units_count, components=m.components)
            for m in layout.iteration_metas
        ],
        best_seed=layout.best_seed,
```

- [ ] **Step 5: Testy + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS (starzy klienci bez nowych pól przechodzą przez
fallbacki `or a.min_area_m2` i defaulty Pydantic).

```bash
git add backend/api/v1/endpoints/layout.py backend/services/layout.py backend/tests/test_unit_iterations.py
git commit -m "feat: iterations and 7-weight scoring through /layout/units and /layout/generate"
```

---

### Task 3: Frontend — panel Program: readonly liczba, 7 suwaków wag, lista iteracji

**Files:**
- Modify: `frontend/app/lib/api.ts` (`ApartmentProgramInput`, `UnitsResponse` :224-228, `LayoutGenerateResponse`, sygnatura `subdivideUnits` :230-)
- Modify: `frontend/app/state/SessionContext.tsx` (stan, `runSubdivideUnits` :538-, `regenerate`, reducer)
- Modify: `frontend/app/components/ProgramSection.tsx` (pole totalUnits :39, suwaki, lista)

**Interfaces:**
- Consumes: pola API z Task 2
- Produces: kompletne UI Etapu 4

- [ ] **Step 1: api.ts**

`ApartmentProgramInput` — dodaj `percentage: number; area_min_m2: number;
area_max_m2: number; min_facade_m: number;`.

Nowe typy:

```ts
export interface UnitWeightsInput {
  size: number;
  mix: number;
  grid: number;
  shape: number;
  daylight: number;
  squareness: number;
  adjacency: number;
}

export interface IterationMeta {
  seed: number;
  score: number;
  units_count: number;
  components?: Record<string, number>;
}
```

Do `UnitsResponse` i `LayoutGenerateResponse` dodaj (OPCJONALNE w TS —
`runSubdivideUnits` konstruuje `LayoutGenerateResponse` ręcznie; odczyt
zawsze z `?? []`/`?? null`):

```ts
  derived_total_units?: number;
  net_remainder_m2?: number;
  iterations?: IterationMeta[];
  best_seed?: number;
```

`subdivideUnits(...)` — dodaj parametry `iterations: number` i `weights:
UnitWeightsInput` przekazywane w body jako `iterations`/`weights`.

- [ ] **Step 2: SessionContext**

Stała + stan (po `totalUnits`):

```ts
export const DEFAULT_UNIT_WEIGHTS: api.UnitWeightsInput = {
  size: 0.8, mix: 0.6, grid: 0.3, shape: 0.5, daylight: 0.7, squareness: 0.5, adjacency: 1.0,
};
```

```ts
  unitWeights: api.UnitWeightsInput;
  lastIterations: api.IterationMeta[];
  derivedTotalUnits: number | null;
  netRemainderM2: number | null;
```

`initialState`: `unitWeights: DEFAULT_UNIT_WEIGHTS, lastIterations: [],
derivedTotalUnits: null, netRemainderM2: null,`.

Akcje:

```ts
  | { type: "SET_UNIT_WEIGHT"; key: keyof api.UnitWeightsInput; value: number }
  | { type: "SET_ITERATION_RESULTS"; iterations: api.IterationMeta[]; derivedTotalUnits: number; netRemainderM2: number }
```

Reducer:

```ts
    case "SET_UNIT_WEIGHT":
      return { ...state, unitWeights: { ...state.unitWeights, [action.key]: action.value } };
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

Callback `setUnitWeight(key, value)` + wpis do interfejsu i `value`
(wzorzec `setTotalUnits`). `SET_TOTAL_UNITS`/`setTotalUnits` ZOSTAJĄ
(nieużywane przez UI — usunięcie odkładamy).

`runSubdivideUnits` (linia 538): `unitsReq` z polami struktury:

```ts
      const unitsReq = state.program.map((row) => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
        percentage: row.percentage,
        area_min_m2: row.area_min_m2,
        area_max_m2: row.area_max_m2,
        min_facade_m: row.min_facade_m,
      }));
```

Typ `ProgramRow` (SessionContext) dostaje pole `min_facade_m: number`;
w `initialState` i w `ADD_PROGRAM_ROW` nowe wiersze dostają
`min_facade_m: 3.0` (dopisz do każdego literału wiersza obok
`area_max_m2`).

```ts
```

wywołanie `api.subdivideUnits(..., 10, state.unitWeights)`. Po `unitsRes`:

```ts
      dispatch({
        type: "SET_ITERATION_RESULTS",
        iterations: unitsRes.iterations ?? [],
        derivedTotalUnits: unitsRes.derived_total_units ?? 0,
        netRemainderM2: unitsRes.net_remainder_m2 ?? 0,
      });
```

W ręcznie budowanym `layoutResult` (linie ~553-566) dopisz:

```ts
        derived_total_units: unitsRes.derived_total_units,
        net_remainder_m2: unitsRes.net_remainder_m2,
        iterations: unitsRes.iterations,
        best_seed: unitsRes.best_seed,
```

Analogicznie `regenerate` (/generate): request dostaje `iterations: 10,
weights: state.unitWeights` + pola struktury w `apartments`; po odpowiedzi
ten sam dispatch `SET_ITERATION_RESULTS`. `state.unitWeights` do zależności
obu useCallbacków.

- [ ] **Step 3: ProgramSection**

- USUŃ label/input „liczba mieszkań" (blok z `value={state.totalUnits}`,
  linia ~39) wraz z `setTotalUnits` z destrukturyzacji; dodaj
  `setUnitWeight` do destrukturyzacji.
- W każdym wierszu struktury (obok pól area_min/area_max) dodaj pole
  „Min. styk z elewacją [m]" (screen Finch „Min facade length"):

```tsx
              <input
                type="number"
                step={0.5}
                min={0}
                value={row.min_facade_m}
                onChange={(e) => updateProgramRow(row.id, { min_facade_m: Number(e.target.value) })}
                title="Minimalny styk mieszkań tego typu ze ścianą zewnętrzną (komponent Daylight)"
                className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
              />
```
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

- Sekcja 7 suwaków wag (pod wierszami struktury; etykiety PL ze specu §4):

```tsx
      <div className="space-y-1.5 pt-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Wagi układu</div>
        {(
          [
            ["size", "Wielkość m²"],
            ["mix", "Struktura mieszkań"],
            ["grid", "Siatka 0.5m"],
            ["shape", "Prostokątność"],
            ["daylight", "Dostęp do elewacji"],
            ["squareness", "Proporcje boków"],
            ["adjacency", "Dostęp do komunikacji"],
          ] as [keyof api.UnitWeightsInput, string][]
        ).map(([key, label]) => (
          <label key={key} className="flex items-center justify-between text-xs text-zinc-400">
            <span>{label} ({state.unitWeights[key].toFixed(2)})</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={state.unitWeights[key]}
              onChange={(e) => setUnitWeight(key, Number(e.target.value))}
              className="ml-2 w-24 accent-accent-500"
            />
          </label>
        ))}
      </div>
```

- Lista iteracji (na końcu sekcji):

```tsx
      {state.lastIterations.length > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje ({state.lastIterations.length})
          </div>
          {state.lastIterations.map((m) => {
            const isBest = state.lastIterations.every((o) => m.score <= o.score);
            return (
              <div
                key={m.seed}
                className={`flex items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] ${
                  isBest ? "bg-accent-500/15 text-accent-400" : "text-zinc-500"
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

- [ ] **Step 4: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/ProgramSection.tsx
git commit -m "feat: derived unit count, 7 weight sliders, iteration list in Program panel"
```

---

### Task 4: Weryfikacja ręczna (spec §7)

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1–3
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. Mały obrys (~12×10m) → kilka mieszkań; duży (~40×15m) → kilkanaście+.
2. Pole „liczba mieszkań" zniknęło; readonly „≈ N mieszkań (M m² netto)".
3. Po podziale lista 10 iteracji ze score; najlepsza podświetlona; canvas
   pokazuje najlepszą.
4. Skrajne wagi: `adjacency=1` reszta 0 vs `size=1` reszta 0 → inne
   zwycięskie układy/score.
4b. Podbij „Min. styk z elewacją" jednego typu do 8m przy `daylight=1` →
   mieszkania tego typu lądują przy elewacji z długim stykiem / score
   rośnie gdy się nie da.
5. Zero dziur: mieszkania + komunikacja + ściany pokrywają cały obrys.
6. Dwa uruchomienia z tymi samymi danymi → identyczne wyniki (determinizm).
7. Ścieżka „Generuj układ" (/generate) daje te same nowe pola co
   dwustopniowa.
8. Regresja: WT-walidacja, eksport, wall_bands.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
