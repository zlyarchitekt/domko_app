# Optimization Kernel — Three-Stage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Staging note:** Etap 1 (Tasks 1-4) is code-complete and executable now. Etap 2 (Tasks 5-8) is code-complete at algorithm level but its briefs MUST be re-verified against the post-Etap-1 codebase before dispatch. Etap 3 (Tasks 9-11) fixes interfaces and the full NSGA-II core, but assumes solar evaluation exists in-loop — re-verify + refresh line references before dispatch. Between etapy: user acceptance on live app.

**Goal:** Replace the hard-wired `for seed in range(N)` random loops with a pluggable optimization kernel (generator / evaluator / strategy), fix the iterative cage-placement semantics, then upgrade search quality stage-by-stage: random → simulated annealing → multi-objective NSGA-II — the architecture that scales to the roadmap (L/U footprints, slanted walls, solar-in-the-loop, footprint search on a parcel, unit floor-plan generation).

**Architecture:** One new module `backend/services/optimize.py` owns three contracts: `Generator` (random_genome / mutate / build — constraint-correct-by-construction candidates), `Evaluator` (candidate → score, components, hard violations), `SearchStrategy` (decides which genomes to try next under a `Budget`). Existing engines (`iterate_units`, `iterate_cage_placement`) become thin Generator+Evaluator adapters; their public signatures and API surfaces do not change in Etap 1. Strategies are stateless-between-runs and fully seed-deterministic (repro + tests). Frontend keeps its iteration list — in Etap 2 it shows the top-N explored candidates, in Etap 3 the Pareto front.

**Tech Stack:** Python 3.11, Shapely 2.x, FastAPI, pytest. NO new dependencies (NSGA-II hand-rolled, ~150 lines). Frontend: existing Next.js — changes only in Etap 2 (strategy dropdown) and Etap 3 (Pareto tags).

## Global Constraints

- Determinism: identical inputs → identical outputs, always. Every strategy consumes `random.Random(seed)` instances derived from the iteration/generation index; never the global `random` module.
- Etap 1 refactor bar: `iterate_units` and `iterate_cage_placement` keep their EXACT public signatures and return types; existing tests must pass unmodified EXCEPT tests asserting the old cage semantics being fixed here (k=randint, count=k/num_cages) — those are updated with 1-line justifications.
- Hard bans (2026-07-11/13) unchanged and strategy-independent: winner = best hard-valid candidate, fallback best-overall; `hard_violations` reasons flow to both API surfaces.
- Budget unit = number of full candidate evaluations (`Budget.evaluations`), NOT wall-clock. Frontend `ITERATIONS_COUNT` (currently 30) maps 1:1 to evaluations in Etap 1; Etap 2 keeps the same budget but spends it smarter (seed phase + annealing phase).
- The iteration list shown to the user is always: unique candidates, deduplicated by genome, sorted valid-first then score, capped at the request's `iterations` value.
- Dual-surface rule (recurring gotcha): every new API field must land on BOTH `/layout/units` and `/layout/generate` serialization paths (shared `_serialize_unit_iteration` / `_serialize_cage_iteration` helpers).
- Backend verification bar: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` exit 0 (venv python only). Frontend bar: `npx tsc --noEmit` exit 0.
- Git hygiene: stage ONLY files the task names, by name. Never `git add -A` / `git add .`.

---

## ETAP 1 — Kernel + naprawa semantyki klatek (opcja c)

### Task 1: `services/optimize.py` — kernel contracts + RandomSearch

**Files:**
- Create: `backend/services/optimize.py`
- Test: `backend/tests/test_optimize.py` (new)

**Interfaces:**
- Consumes: nothing project-specific (pure module).
- Produces (used by Tasks 2-3 and every later stage):
  - `@dataclass Candidate: genome: Any; payload: Any; score: float; components: dict; hard_valid: bool; hard_violations: list[str]`
  - `@dataclass Budget: evaluations: int`
  - `class Generator(Protocol): random_genome(rng) -> Any; mutate(genome, rng) -> Any; build(genome) -> Any`
  - `class Evaluator(Protocol): __call__(genome, payload) -> tuple[float, dict, list[str]]`
  - `def run_random_search(generator, evaluator, budget) -> list[Candidate]` — candidate i uses `random.Random(i)`; result ordered by evaluation index (stable).
  - `def pick_best(candidates) -> Candidate` — min score among hard-valid, fallback min overall (same rule as `unit_mix.pick_best_iteration`).
  - `def dedupe_and_rank(candidates, limit) -> list[Candidate]` — unique by `genome` (hashable), valid-first then score asc, first `limit`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_optimize.py`)

```python
"""Kernel optymalizacji (plan 2026-07-14, Etap 1) -- kontrakty testowane na
syntetycznym generatorze liczbowym, bez geometrii."""

import random

from services.optimize import Budget, Candidate, dedupe_and_rank, pick_best, run_random_search


class _NumberGenerator:
    """Genome = float z [0, 10); build = identyczność; mutacja = +-0.5."""

    def random_genome(self, rng: random.Random) -> float:
        return rng.uniform(0.0, 10.0)

    def mutate(self, genome: float, rng: random.Random) -> float:
        return genome + rng.uniform(-0.5, 0.5)

    def build(self, genome: float) -> float:
        return genome


def _evaluator(genome: float, payload: float):
    # cel: genome == 3.0; hard-invalid powyżej 8
    score = abs(payload - 3.0)
    violations = ["za duże"] if payload > 8.0 else []
    return score, {"dist": score}, violations


def test_random_search_deterministic_and_budgeted():
    gen = _NumberGenerator()
    a = run_random_search(gen, _evaluator, Budget(evaluations=12))
    b = run_random_search(gen, _evaluator, Budget(evaluations=12))
    assert len(a) == 12
    assert [c.genome for c in a] == [c.genome for c in b]
    assert all(isinstance(c, Candidate) for c in a)
    assert all(c.hard_valid == (not c.hard_violations) for c in a)


def test_pick_best_prefers_hard_valid():
    cands = [
        Candidate(genome=9.0, payload=9.0, score=0.1, components={}, hard_valid=False, hard_violations=["x"]),
        Candidate(genome=4.0, payload=4.0, score=1.0, components={}, hard_valid=True, hard_violations=[]),
    ]
    assert pick_best(cands).genome == 4.0
    # wszystkie invalid -> najniższy score
    all_bad = [
        Candidate(genome=9.0, payload=9.0, score=0.5, components={}, hard_valid=False, hard_violations=["x"]),
        Candidate(genome=8.5, payload=8.5, score=0.2, components={}, hard_valid=False, hard_violations=["x"]),
    ]
    assert pick_best(all_bad).genome == 8.5


def test_dedupe_and_rank():
    mk = lambda g, s, ok: Candidate(genome=g, payload=g, score=s, components={}, hard_valid=ok,
                                    hard_violations=[] if ok else ["x"])
    cands = [mk(1.0, 0.9, True), mk(1.0, 0.9, True), mk(2.0, 0.1, False), mk(3.0, 0.5, True)]
    ranked = dedupe_and_rank(cands, limit=10)
    assert [c.genome for c in ranked] == [3.0, 1.0, 2.0]  # valid-first, potem score; duplikat 1.0 odpada
    assert len(dedupe_and_rank(cands, limit=2)) == 2
```

- [ ] **Step 2: Run to verify RED** — `./.venv/Scripts/python.exe -m pytest tests/test_optimize.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/services/optimize.py`**

```python
"""Kernel optymalizacji (plan 2026-07-14): generator / ewaluator / strategia.

Generator buduje kandydata z genomu i jest poprawny KONSTRUKCYJNIE (np. krajacz
traktowy: mieszkanie zawsze korytarz->elewacja). Ewaluator to czysta funkcja
(genome, payload) -> (score, components, hard_violations). Strategia decyduje,
które genomy próbować w ramach budżetu. Etap 1: RandomSearch (zachowanie 1:1 ze
starą pętlą `for seed in range(N)`); Etap 2 doda SimulatedAnnealing; Etap 3
NSGA-II. Determinizm: wyłącznie random.Random(seed) pochodne od indeksu."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


@dataclass
class Candidate:
    genome: Any
    payload: Any
    score: float
    components: dict = field(default_factory=dict)
    hard_valid: bool = True
    hard_violations: list = field(default_factory=list)


@dataclass
class Budget:
    evaluations: int


class Generator(Protocol):
    def random_genome(self, rng: random.Random) -> Any: ...
    def mutate(self, genome: Any, rng: random.Random) -> Any: ...
    def build(self, genome: Any) -> Any: ...


Evaluator = Callable[[Any, Any], tuple[float, dict, list]]


def evaluate_genome(generator: Generator, evaluator: Evaluator, genome: Any) -> Candidate:
    payload = generator.build(genome)
    score, components, violations = evaluator(genome, payload)
    return Candidate(genome=genome, payload=payload, score=score, components=components,
                     hard_valid=not violations, hard_violations=list(violations))


def run_random_search(generator: Generator, evaluator: Evaluator, budget: Budget) -> list[Candidate]:
    out: list[Candidate] = []
    for i in range(budget.evaluations):
        rng = random.Random(i)
        out.append(evaluate_genome(generator, evaluator, generator.random_genome(rng)))
    return out


def pick_best(candidates: list[Candidate]) -> Candidate:
    valid = [c for c in candidates if c.hard_valid]
    pool = valid or candidates
    return min(pool, key=lambda c: c.score)


def dedupe_and_rank(candidates: list[Candidate], limit: int) -> list[Candidate]:
    seen: set = set()
    unique: list[Candidate] = []
    for c in candidates:
        key = c.genome if isinstance(c.genome, (int, float, str, tuple)) else repr(c.genome)
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda c: (0 if c.hard_valid else 1, c.score))
    return unique[:limit]
```

- [ ] **Step 4: GREEN + full suite** — module tests pass; full suite exit 0 (nothing imports the kernel yet).

- [ ] **Step 5: Commit** — `git add backend/services/optimize.py backend/tests/test_optimize.py && git commit -m "feat: optimization kernel - generator/evaluator/strategy contracts + RandomSearch"`

---

### Task 2: `iterate_units` na kernelu (refaktor 1:1)

**Files:**
- Modify: `backend/services/unit_mix.py` (`iterate_units` body only)
- Test: `backend/tests/test_unit_iterations.py` (NO changes expected — that's the regression bar)

**Interfaces:**
- Consumes: Task 1 kernel; existing `slice_trakts`, `fit_program_to_rectangles`, `_score_iteration`, `hard_constraint_violations`.
- Produces: unchanged `iterate_units` signature `(remainder, shares, iterations, weights, footprint, circulation_geometry) -> (cells, metas, best_seed, total_units)`; internal `_UnitsGenerator` class reused by Etap 2.

- [ ] **Step 1: Implement the adapter inside unit_mix.py** (no new test first — the bar is the EXISTING suite, byte-identical metas)

Genome (Etap 1) = the seed int itself; `build` runs the current per-seed body. This makes the refactor provably 1:1: same seed → same rng → same cells.

```python
class _UnitsGenerator:
    """Adapter silnika mieszkań do kernela (plan 2026-07-14 Etap 1).
    Genome = seed (int); build odtwarza dokładnie stare per-seed zachowanie,
    więc refaktor jest 1:1. Etap 2 podmieni genome na permutacje."""

    def __init__(self, remainder, specs, rectangles, use_trakts, circulation_geometry, net_area, shares):
        self.remainder = remainder
        self.specs = specs
        self.rectangles = rectangles
        self.use_trakts = use_trakts
        self.circulation_geometry = circulation_geometry
        self.net_area = net_area
        self.shares = shares

    def random_genome(self, rng: random.Random):
        # seed wyprowadzamy z PIERWSZEGO losowania rng, żeby kolejne wywołania
        # kernela (Random(0), Random(1), ...) mapowały się na seedy 0,1,2...
        return rng._seed if hasattr(rng, "_seed") else None  # placeholder, patrz build-by-index niżej

    def mutate(self, genome, rng):
        return genome  # Etap 1: brak mutacji (RandomSearch nie mutuje)

    def build(self, genome: int):
        rng = random.Random(genome)
        if self.use_trakts:
            from services.trakt_division import slice_trakts
            cells, leftover = slice_trakts(self.remainder, self.circulation_geometry, self.specs, rng=rng)
        else:
            cells, leftover = fit_program_to_rectangles(list(self.rectangles), self.specs, rng=rng)
        _merge_leftover_into_cells(cells, leftover)
        if not cells:
            import uuid as _uuid
            from services.layout import ApartmentCell as _Cell
            whole = self.remainder if self.remainder.geom_type == "Polygon" else unary_union(self.remainder)
            cells = [_Cell(id=str(_uuid.uuid4()), type=self.shares[0].type, polygon=whole)]
            cells[0].net_area_m2 = self.net_area
        return cells
```

IMPORTANT implementation detail: `random.Random` does not expose its seed. Solve it by making the SEED the genome directly — in `iterate_units` call `evaluate_genome(gen, evaluator, seed)` in a loop over `range(iterations)` instead of `run_random_search` (the kernel helper `evaluate_genome` is the shared piece; `run_random_search` stays for generators whose genomes are self-contained). Update `random_genome` to raise `NotImplementedError("Etap 1: seed-genomes are enumerated, not drawn")` and drop the placeholder above.

`iterate_units` body becomes:

```python
    gen = _UnitsGenerator(remainder, specs, rectangles, use_trakts, circulation_geometry, net_area, shares)

    def _evaluator(genome, cells):
        score, components = _score_iteration(cells, shares, weights, footprint, circulation_geometry)
        violations = hard_constraint_violations(cells, footprint, circulation_geometry)
        return score, components, violations

    from services.optimize import evaluate_genome

    candidates = [evaluate_genome(gen, _evaluator, seed) for seed in range(iterations)]
    metas = [
        IterationMeta(seed=c.genome, score=c.score, units_count=len(c.payload),
                      components=c.components, cells=list(c.payload),
                      hard_valid=c.hard_valid, hard_violations=list(c.hard_violations))
        for c in candidates
    ]
    winner = pick_best_iteration(metas)
    return winner.cells, metas, winner.seed, total_units
```

- [ ] **Step 2: Full suite — the regression bar** — `./.venv/Scripts/python.exe -m pytest -q` exit 0 with ZERO test modifications. If any unit-iteration test fails, the refactor is not 1:1 — fix the adapter, not the test.

- [ ] **Step 3: Commit** — `git add backend/services/unit_mix.py && git commit -m "refactor: iterate_units runs on the optimization kernel (behavior-identical)"`

---

### Task 3: `iterate_cage_placement` na kernelu + naprawa semantyki (opcja c)

**Files:**
- Modify: `backend/services/cage_placement.py` (`iterate_cage_placement`, `_score_placement`, `_candidate_cages`)
- Test: `backend/tests/test_cage_placement.py` (update old-semantics tests with justifications), `backend/tests/test_circulation.py` (only if position assertions trip)

**Interfaces:**
- Consumes: Task 1 kernel.
- Produces: unchanged signature `iterate_cage_placement(footprint, corridor_width_m, num_cages, weights, iterations, max_dist_single_m, max_dist_multi_m) -> (best_result, metas, best_seed)`; internal `_CageGenerator` reused by Etap 2.

Three semantic fixes (user report 2026-07-13 "nie wygląda to dobrze"):
1. `k = rng.randint(1, num_cages)` → **k = num_cages zawsze** (suwak to żądanie, nie górna granica losowania).
2. `count = k / num_cages` (karze za więcej klatek) → **`count = abs(placed - num_cages) / num_cages`** (kara za niedowiezienie żądanej liczby, 0 = dowiezione).
3. `_candidate_cages` dostaje dodatkowe deterministyczne kotwice rozstawu: dla każdej strefy i dla k = num_cages pozycje `(i + 0.5) / k` wzdłuż dłuższej osi strefy (obie orientacje klatki, przy obu krawędziach poprzecznych) — losowanie ma sensowne pozycje w puli zamiast czystego chaosu; `spread` wreszcie ma z czego wybierać.

- [ ] **Step 1: Write failing tests** (append to `backend/tests/test_cage_placement.py`)

```python
def test_iterative_placement_delivers_requested_cage_count():
    """Fix 2026-07-14 (opcja c): suwak num_cages to żądanie -- każda iteracja
    próbuje umieścić DOKŁADNIE num_cages klatek; mniej tylko gdy pula
    kandydatów fizycznie nie pozwala (i wtedy komponent count > 0)."""
    footprint = _rect(0, 0, 40, 12)
    result, metas, best_seed = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=3, weights=CageWeights(), iterations=10,
    )
    assert all(m.cages_count == 3 for m in metas), [m.cages_count for m in metas]
    assert len(result.cage_polygons) == 3


def test_count_component_penalizes_shortfall_not_more_cages():
    footprint = _rect(0, 0, 40, 12)
    _result, metas, _ = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=3, weights=CageWeights(), iterations=5,
    )
    for m in metas:
        expected = abs(m.cages_count - 3) / 3
        assert abs(m.components["count"] - expected) < 1e-9


def test_candidate_pool_contains_even_spread_anchors():
    from services.circulation import Zone
    from services.bsp import rectangle_decompose
    from services.cage_placement import _candidate_cages

    footprint = _rect(0, 0, 60, 12)
    zones = [Zone(name="Z0", polygon=p) for p, in [(q,) for q in rectangle_decompose(footprint)]]
    candidates = _candidate_cages(footprint, zones, num_cages=3)
    xs = sorted({round((c.bounds[0] + c.bounds[2]) / 2, 1) for _, c in candidates})
    # pozycje rozstawu 1/6, 3/6, 5/6 długości: x ~= 10, 30, 50
    for target in (10.0, 30.0, 50.0):
        assert any(abs(x - target) <= 3.0 for x in xs), (target, xs)
```

(`_candidate_cages` gains an optional `num_cages: int = 1` parameter — existing call sites without it keep the old pool plus nothing new for num_cages=1, so classic placement's deterministic fill is unaffected.)

- [ ] **Step 2: RED** — the three tests fail on current semantics.

- [ ] **Step 3: Implement**

In `_score_placement` replace:

```python
    count = k / num_cages if num_cages > 0 else 0.0
```
with:
```python
    # Fix 2026-07-14: kara za NIEDOWIEZIENIE żądanej liczby klatek
    # (0 = umieszczono dokładnie num_cages), nie za "posiadanie klatek".
    count = abs(k - num_cages) / num_cages if num_cages > 0 else 0.0
```

In `_candidate_cages(footprint, zones)` → `_candidate_cages(footprint, zones, num_cages: int = 1)`; after the existing per-zone anchors block, add:

```python
        # Kotwice rozstawu (plan 2026-07-14 Etap 1): (i+0.5)/k długości strefy
        # wzdłuż dłuższej osi, przy obu krawędziach poprzecznych -- pozycje,
        # które wybrałby projektant przy k klatkach; RandomSearch/SA losują
        # wokół sensownych punktów zamiast czystego chaosu.
        if num_cages > 1:
            horizontal = (maxx - minx) >= (maxy - miny)
            for i_k in range(num_cages):
                t = (i_k + 0.5) / num_cages
                if horizontal:
                    anchors.append((minx + t * (maxx - minx), miny))
                    anchors.append((minx + t * (maxx - minx), maxy))
                else:
                    anchors.append((minx, miny + t * (maxy - miny)))
                    anchors.append((maxx, miny + t * (maxy - miny)))
```

(Note: append BEFORE the `for ax, ay in anchors:` loop — inspect the current function body first; anchors list is built per-zone.)

In `iterate_cage_placement`: genome = seed (jak Task 2), `build(seed)`:

```python
        rng = random.Random(seed)
        k = num_cages                      # było: rng.randint(1, max(1, num_cages))
        pool = list(candidates)
        rng.shuffle(pool)
        # ... reszta zachłannego brania bez zmian ...
```
plus adapter `_CageGenerator` + `evaluate_genome` loop analogicznie do Task 2 (build zwraca `CirculationResult | None`; None gdy `local_cages` puste → kandydat ze score inf i naruszeniem `"nie udało się umieścić klatek"` zamiast `continue`, żeby budżet się zgadzał; `pick_best` ignoruje je naturalnie, a serializacja pomija metas z `result=None` tak jak dziś).

- [ ] **Step 4: GREEN + full suite; update old-semantics tests** — expected failures to UPDATE (with 1-line justifications in report): any test asserting `cages_count` varies across seeds or `count == k/num_cages`. Suite exit 0.

- [ ] **Step 5: Commit** — `git add backend/services/cage_placement.py backend/tests/test_cage_placement.py && git commit -m "feat: cage iterations on kernel - k=num_cages, count penalizes shortfall, even-spread anchors"`

---

### Task 4: Weryfikacja Etapu 1 (żywe serwery)

**Files:** none.

- [ ] Full suite + tsc (no frontend changes in Etap 1).
- [ ] Fresh backend :8000 (kill orphaned uvicorn workers — gotcha memory), smoke: 40×12 rect, `cage_iterations: 30, num_cages: 3` → EVERY iteration in response has `cages_count == 3`; positions differ between iterations; units on 68×12 (user footprint) still ≥1 hard-valid winner.
- [ ] User checklist: "Rozmieść iteracyjnie" z suwakiem 3 → 3 klatki w każdej iteracji, rozstawione (nie stłoczone w naróżniku); lista iteracji różni się pozycjami.

---

## ETAP 2 — Local search / symulowane wyżarzanie

**Prerekwizyt:** Etap 1 zmergowany i zaakceptowany na żywej apce. Briefs re-verified against current code (line numbers WILL have drifted).

### Task 5: Genomy permutacyjne + mutacje w generatorach

**Files:**
- Modify: `backend/services/unit_mix.py` (`_UnitsGenerator`), `backend/services/cage_placement.py` (`_CageGenerator`)
- Test: `backend/tests/test_unit_iterations.py`, `backend/tests/test_cage_placement.py` (append)

**Interfaces:**
- Produces: genomes become self-contained hashable tuples (not seeds):
  - units: `genome = ("perm", tuple[int, ...])` — permutacja indeksów kolejki specyfikacji (queue z target_count rozwiniętym) + `tuple[int, ...]` kolejność komponentów; build deterministycznie tnie wg tej permutacji (slice_trakts/fit dostają PRZETASOWANĄ listę i `rng=None`).
  - cages: `genome = tuple[int, ...]` — posortowana krotka indeksów wybranych kandydatów z puli (dokładnie `num_cages` sztuk); build składa te konkretne klatki (kolizje/korytarz-share sprawdzane w build; niewykonalny genom → payload None → naruszenie jak w Task 3).
- `mutate(genome, rng)`: units — swap dwóch pozycji permutacji (albo, p=0.3, swap kolejności dwóch komponentów); cages — podmień jeden indeks na losowy spoza genomu (bez kolizji sprawdza build).
- `random_genome(rng)`: units — `rng.shuffle` permutacji; cages — `rng.sample(range(len(pool)), num_cages)`.

Backward-compat wymóg: seed-owe wyniki Etapu 1 NIE muszą być bitowo zachowane w Etapie 2 (to zmiana zachowania per plan), ale determinizm i kontrakty API tak. Testy asertujące konkretne geometrie per seed → aktualizacja z uzasadnieniem.

- [ ] Tests: permutation genome round-trip (same genome → same cells), mutate zmienia dokładnie jedną parę, random_genome deterministyczne per seed, cages genome infeasible → hard_violations niepuste.
- [ ] Implement + suite + commit (`feat: permutation genomes with mutation for units and cages generators`).

### Task 6: Strategia SimulatedAnnealing w kernelu

**Files:**
- Modify: `backend/services/optimize.py`
- Test: `backend/tests/test_optimize.py` (append)

**Interfaces:**
- Produces: `def run_simulated_annealing(generator, evaluator, budget, seed_candidates=None, restarts=3) -> list[Candidate]` — zwraca WSZYSTKIE ewaluowane kandydaty (historia; dedupe robi caller).

Complete core (hand-rolled, no deps):

```python
def run_simulated_annealing(generator, evaluator, budget, seed_candidates=None, restarts=3):
    """SA z restartami: budżet dzielony po równo między restarty; każdy restart
    startuje z kolejnego najlepszego seed-kandydata (albo losowego genomu).
    Temperatura: T0 = max(1e-6, 0.25 * score startu), wykładniczo do ~T0/100.
    Akceptacja: lepszy zawsze; gorszy z p = exp(-delta/T). Kandydat łamiący
    zakazy dostaje score + 1.0 kary do porównań SA (ale w historii zostaje
    z prawdziwym score) -- SA szuka w stronę ważnych, nie przez nie."""
    history: list[Candidate] = []
    seeds = list(seed_candidates or [])
    per_restart = max(1, budget.evaluations // max(1, restarts))
    for r in range(restarts):
        rng = random.Random(10_000 + r)
        if r < len(seeds):
            current = seeds[r]
        else:
            current = evaluate_genome(generator, evaluator, generator.random_genome(rng))
            history.append(current)
        def eff(c: Candidate) -> float:
            return c.score + (0.0 if c.hard_valid else 1.0)
        t = max(1e-6, 0.25 * eff(current))
        cooling = (0.01) ** (1.0 / max(1, per_restart))
        for _ in range(per_restart):
            neighbor = evaluate_genome(generator, evaluator, generator.mutate(current.genome, rng))
            history.append(neighbor)
            delta = eff(neighbor) - eff(current)
            if delta <= 0 or rng.random() < math.exp(-delta / t):
                current = neighbor
            t *= cooling
    return history
```

- [ ] Tests na `_NumberGenerator`: SA z budżetem 60 znajduje wynik lepszy niż RandomSearch z tym samym budżetem (statystycznie pewne na tej funkcji — assert `pick_best(sa).score <= pick_best(rs).score`); determinizm powtórnego wywołania; historia ma długość ≈ budżet.
- [ ] Commit (`feat: simulated-annealing strategy with restarts in the optimization kernel`).

### Task 7: Silniki na SA (hybryda: random seed phase → annealing)

**Files:**
- Modify: `backend/services/unit_mix.py`, `backend/services/cage_placement.py`
- Test: istniejące pliki testów obu silników (append e2e)

Przebieg per silnik: `n_seed = max(5, iterations // 3)` RandomSearch → top-3 valid-first jako starty → `run_simulated_annealing` z resztą budżetu → `dedupe_and_rank(all_history, limit=iterations)` do listy metas → `pick_best`. `best_seed`/`seed` pola API: nadawaj metas kolejne numery 0..N-1 wg rankingu (genome nie jest już seedem; pole `seed` zostaje jako stabilny identyfikator wiersza listy — frontendowi to wystarcza, SELECT_*_ITERATION działa po tym id).

- [ ] e2e: na 68×12 SA-winner score <= RandomSearch-winner score (ten sam budżet 30); wszystkie API pola obecne na obu powierzchniach; suite + tsc.
- [ ] Commit (`feat: units and cage engines run hybrid random+annealing search`).

### Task 8: Frontend — wybór strategii + weryfikacja Etapu 2

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (request field `strategy: Literal["random","anneal"] = "anneal"` na CirculationSpec i LayoutGenerateRequest/units request), `frontend/app/lib/api.ts`, `frontend/app/components/ProgramSection.tsx` (mały select przy WAGI UKŁADU), `frontend/app/components/CirculationSection.tsx` (analogicznie przy WAGI KLATEK)
- [ ] Dual-surface: pole przechodzi przez OBIE ścieżki (/units i /generate). Default "anneal"; "random" zostaje do debugowania/porównań.
- [ ] Weryfikacja na żywo + checklist dla usera (jakość układów wizualnie lepsza/równa, czasy akceptowalne — budżet ten sam, więc czas ~identyczny jak Etap 1).

---

## ETAP 3 — Wielokryterialnie (NSGA-II) + solar w pętli

**Prerekwizyt:** solar evaluator per-komórka dostępny jako tania funkcja (istniejący `services/solar.py` policzy godziny nasłonecznienia elewacji; w pętli wystarczy: dla każdej komórki suma `hours × długość styku` po jej odcinkach elewacyjnych — BEZ pełnego ray-tracingu). Briefs refresh przed dispatch.

### Task 9: NSGA-II core w kernelu

**Files:**
- Modify: `backend/services/optimize.py`
- Test: `backend/tests/test_optimize.py` (append)

**Interfaces:**
- `Candidate.objectives: tuple[float, ...] = ()` (nowe pole; minimalizowane).
- `def run_nsga2(generator, evaluator_multi, budget, population=24) -> list[Candidate]` gdzie `evaluator_multi(genome, payload) -> tuple[objectives: tuple[float,...], components: dict, violations: list]`.
- Zwraca finalną populację; front Pareto = `pareto_front(candidates)`.

Complete core (fast non-dominated sort + crowding + turniej + mutacja jako operator wariacji; crossover pominięty świadomie — mutate wystarcza przy genomach permutacyjnych, crossover permutacji to osobna nauka, YAGNI dopóki front nie jest za ubogi):

```python
def _dominates(a: Candidate, b: Candidate) -> bool:
    if a.hard_valid != b.hard_valid:
        return a.hard_valid
    return all(x <= y for x, y in zip(a.objectives, b.objectives)) and any(
        x < y for x, y in zip(a.objectives, b.objectives)
    )


def pareto_front(candidates: list[Candidate]) -> list[Candidate]:
    return [c for c in candidates if not any(_dominates(o, c) for o in candidates if o is not c)]


def _crowding(front: list[Candidate]) -> dict[int, float]:
    n = len(front)
    dist = {id(c): 0.0 for c in front}
    if n <= 2:
        return {k: float("inf") for k in dist}
    n_obj = len(front[0].objectives)
    for m in range(n_obj):
        ordered = sorted(front, key=lambda c: c.objectives[m])
        dist[id(ordered[0])] = dist[id(ordered[-1])] = float("inf")
        span = ordered[-1].objectives[m] - ordered[0].objectives[m] or 1.0
        for i in range(1, n - 1):
            dist[id(ordered[i])] += (ordered[i + 1].objectives[m] - ordered[i - 1].objectives[m]) / span
    return dist


def run_nsga2(generator, evaluator_multi, budget, population: int = 24):
    def _eval(genome) -> Candidate:
        payload = generator.build(genome)
        objectives, components, violations = evaluator_multi(genome, payload)
        return Candidate(genome=genome, payload=payload, score=sum(objectives), components=components,
                         hard_valid=not violations, hard_violations=list(violations),
                         objectives=tuple(objectives))

    rng = random.Random(42)
    pop = [_eval(generator.random_genome(random.Random(i))) for i in range(population)]
    evals = population
    gen_idx = 0
    while evals + population <= budget.evaluations:
        gen_idx += 1
        rng_g = random.Random(1000 + gen_idx)
        # turniej binarny po (front-rank przybliżony dominacją, crowding)
        def better(a: Candidate, b: Candidate) -> Candidate:
            if _dominates(a, b):
                return a
            if _dominates(b, a):
                return b
            return a if rng_g.random() < 0.5 else b
        offspring = []
        for _ in range(population):
            p1, p2 = rng_g.sample(pop, 2)
            parent = better(p1, p2)
            offspring.append(_eval(generator.mutate(parent.genome, rng_g)))
        evals += population
        merged = pop + offspring
        # selekcja: kolejne fronty + crowding do rozmiaru population
        next_pop: list[Candidate] = []
        rest = list(merged)
        while rest and len(next_pop) < population:
            front = pareto_front(rest)
            if len(next_pop) + len(front) <= population:
                next_pop.extend(front)
            else:
                cd = _crowding(front)
                front.sort(key=lambda c: -cd[id(c)])
                next_pop.extend(front[: population - len(next_pop)])
            rest = [c for c in rest if c not in front]
        pop = next_pop
    return pop
```

- [ ] Tests: 2-celowa funkcja syntetyczna (min (g-2)², min (g-8)² na `_NumberGenerator`) — front zawiera punkty rozpięte między 2 a 8; determinizm; `pareto_front` poprawny na ręcznych kandydatach; invalid nigdy nie dominuje valid.
- [ ] Commit (`feat: hand-rolled NSGA-II with crowding distance in the optimization kernel`).

### Task 10: Solar objective per komórka + evaluator wielokryterialny mieszkań

**Files:**
- Create: `backend/services/solar_objective.py` (tania funkcja: cells + footprint + elevation_hours → suma niedoboru godzin per komórka)
- Modify: `backend/services/unit_mix.py` (nowa funkcja `iterate_units_multi(...)` obok istniejącej — NIE podmieniaj single-objective, obie ścieżki żyją równolegle; API wybiera)
- Test: nowe + istniejące

**Interfaces:** objectives (wszystkie minimalizowane): `(program_fit, geometry_quality, solar_deficit)` gdzie program_fit = ważona suma size+mix (obecne komponenty), geometry_quality = grid+shape+squareness+adjacency+daylight (obecne), solar_deficit = Σ max(0, wymagane_h − dostępne_h)/n z solar_objective. Wagi suwaków dalej działają WEWNĄTRZ każdej wiązki; między wiązkami — Pareto.

- [ ] Implementacja + testy (deficyt 0 gdy elevation_hours puste; deterministyczność; front niepusty na 68×12).
- [ ] Commit.

### Task 11: API + frontend Pareto + weryfikacja Etapu 3

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (strategy: `"pareto"` trzecia opcja; `IterationMetaResult.objectives: list[float] = []`, `is_pareto: bool = False` — dual-surface przez wspólny serializer), `frontend/app/lib/api.ts`, `frontend/app/components/IterationsSidebar.tsx` (wiersze frontu z tagiem ★P i mini-wartościami celów w tooltipie; sortowanie: front najpierw, potem reszta valid-first/score)
- [ ] Weryfikacja żywa: strategy=pareto na 68×12 z solar → lista pokazuje front (≥3 różne kompromisy), wybór wiersza renderuje układ; regresja strategy=anneal/random.
- [ ] Checklist dla usera + wpis w ledger.

---

## Mapa przyszłych rozszerzeń (poza tym planem, dla kontekstu decyzji)

- **L/U-kształty:** zmiana WYŁĄCZNIE w generatorach (korytarz jako graf odcinków; trakty per odcinek; cięcia prostopadłe do lokalnego odcinka). Kernel/strategie bez zmian.
- **Skośne ściany:** trakt slicing w lokalnym układzie współrzędnych odcinka korytarza (wektor kierunku + normalna zamiast osi x/y); `box`-clipy zastępuje clip równoległobokiem. Kernel bez zmian.
- **Szukanie obrysu na działce:** zewnętrzny `Generator` (genom = parametry obrysu), evaluator = CAŁY pipeline (circulation+units+solar) z małym budżetem wewnętrznym; kernel obsługuje zagnieżdżenie naturalnie (evaluator wywołuje kernel). Wymaga cache wyników i coarse-to-fine budżetów — projekt na osobny plan.
- **Generowanie rzutów mieszkań:** nowy generator niższego poziomu (pokoje w komórce), te same kontrakty.
