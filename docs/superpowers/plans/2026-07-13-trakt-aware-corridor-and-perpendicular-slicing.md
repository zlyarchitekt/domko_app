# Trakt-Aware Corridor + Perpendicular Trakt Slicing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the "thin strip apartments" failure (user report 2026-07-13, export `domko_export_2026-07-13.json`): the corridor stops leaving dead residual bands (option A), and apartment division cuts ONLY perpendicular to the corridor so every unit spans corridor→facade (option B).

**Architecture:** (A) `_build_corridor` and `_corridor_centerline` currently duplicate the axis-position logic and glue the corridor to the cage centroid, which on a 68×12 footprint left a 2.0 m south band that the slicer filled with 14.25×2 m strips (ratio 7:1). Both functions delegate to one shared pure helper `_corridor_axis_offset` implementing the trakt rule: every band between corridor and zone edge is either ~0 (corridor flush at the facade → single-loaded) or ≥ `MIN_TRAKT_DEPTH_M`; the corridor must still touch its cage(s); legacy clamp is the fallback for zones too shallow for the rule. (B) A new `services/trakt_division.py` slices the remainder per-component with cuts perpendicular to the adjacent corridor part (area-targeted bisection), so cells inherently touch both corridor and facade; `iterate_units` uses it whenever `circulation_geometry` is present and falls back to the legacy `fit_program_to_rectangles` otherwise. Existing zero-leftover merge (`_merge_leftover_into_cells`) absorbs end tails, producing the corner L-wraps seen on the user's reference screenshot.

**Tech Stack:** Python 3.11, Shapely 2.x, FastAPI, pytest. No new dependencies. No frontend changes (geometry flows through existing response fields).

## Global Constraints

- `MIN_TRAKT_DEPTH_M = 4.0` — new module constant in `backend/services/circulation.py`; never hardcode 4.0 elsewhere, import it in tests.
- The corridor MUST still touch every cage of its zone (`_cages_share_valid_corridor` in cage_placement.py relies on `_build_corridor`; evacuation graph relies on corridor↔cage contact). The trakt rule may never win over cage contact — filter trakt candidates by the touch interval, fall back to legacy clamp when empty.
- `_build_corridor` and `_corridor_centerline` MUST produce the identical axis (evacuation dots follow the centerline; a desync paints dots outside the corridor). Single shared helper, plus one test asserting equality.
- Corridor grown width everywhere = `width + 2 * NET_SHRINK_M` (already the case; do not change).
- Hard bans (2026-07-11) unchanged: every unit touches circulation AND facade, MRR aspect ratio ≤ `HARD_MAX_ASPECT_RATIO` (3.0). Task 3's e2e must show ≥1 hard-valid iteration on the user's failing footprint.
- `MIN_CELL_DIMENSION_M` (existing constant in `backend/services/unit_mix.py`) is the minimum cut width in the new slicer too — import, don't redefine.
- `ApartmentCell` lives in `services/layout.py`; importing it at module level from unit_mix/trakt_division creates a cycle — use the established deferred-import-inside-function pattern (see `iterate_units`).
- Behavior-change honesty: Tasks 1 and 3 intentionally change corridor position and cell shapes. Pre-existing tests asserting the OLD corridor position or OLD cell rectangles must be updated to assert the NEW contract (trakt rule / perpendicular cells) — never weakened to presence-only assertions, and every such update must be listed in the task report with a one-line justification.
- Backend verification bar: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` exit 0 (global `python` on PATH lacks deps — always use the venv one).
- Git hygiene: stage ONLY files named by the task, by name. Never `git add -A` / `git add .`.

---

### Task 1: Corridor trakt-aware axis (A) — shared helper + placement rule

**Files:**
- Modify: `backend/services/circulation.py`
  - `_build_corridor` (:177-211)
  - `_corridor_centerline` (:214-247)
  - new constant + new helper directly above `_build_corridor`
- Test: `backend/tests/test_circulation.py` (append; update position-asserting tests that fail)

**Interfaces:**
- Consumes: `NET_SHRINK_M` (already imported in circulation.py).
- Produces: `MIN_TRAKT_DEPTH_M: float = 4.0` (module constant), `_corridor_axis_offset(lo: float, hi: float, half: float, cage_bounds: tuple[float, float] | None) -> float` — pure 1-D position picker used by BOTH `_build_corridor` and `_corridor_centerline`. Task 3's e2e relies on the corridor no longer leaving bands in `(1e-6, MIN_TRAKT_DEPTH_M)`.

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_circulation.py`)

```python
def _band_depths_horizontal(footprint, corridor):
    """(south_band, north_band) między korytarzem a krawędziami obrysu."""
    fminx, fminy, fmaxx, fmaxy = footprint.bounds
    cminx, cminy, cmaxx, cmaxy = corridor.bounds
    return cminy - fminy, fmaxy - cmaxy


def test_corridor_leaves_no_dead_band_user_footprint_20260713():
    """Repro exportu domko_export_2026-07-13: 68x12, klatka przy południowej
    elewacji -> stary kod zostawiał trakt 2.0 m, który krajacz wypełniał
    paskami 14.25x2 (proporcje 7:1). Nowa zasada: każdy trakt ~0 albo
    >= MIN_TRAKT_DEPTH_M."""
    from services.circulation import MIN_TRAKT_DEPTH_M, place_circulation

    footprint = Polygon([(-32, -2), (36, -2), (36, 10), (-32, 10)])
    result = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    assert result.circulation_geometry is not None
    south, north = _band_depths_horizontal(footprint, result.circulation_geometry)
    for band in (south, north):
        assert band <= 1e-6 or band >= MIN_TRAKT_DEPTH_M - 1e-6, f"martwy trakt {band:.2f} m"
    # korytarz nadal dotyka każdej klatki
    for cage in result.cage_polygons:
        assert result.circulation_geometry.distance(cage) < 1e-6


def test_corridor_axis_offset_prefers_balanced_then_flush():
    from services.circulation import MIN_TRAKT_DEPTH_M, _corridor_axis_offset

    # strefa [0, 12], korytarz half=0.85, klatka przy dole (bounds 0..5.7)
    mid = _corridor_axis_offset(0.0, 12.0, 0.85, (0.0, 5.7))
    south, north = (mid - 0.85) - 0.0, 12.0 - (mid + 0.85)
    assert south >= MIN_TRAKT_DEPTH_M - 1e-9 and north >= MIN_TRAKT_DEPTH_M - 1e-9
    # przedział touch: [0-0.85, 5.7+0.85] -> mid <= 6.55
    assert mid <= 5.7 + 0.85 + 1e-9

    # strefa za płytka na dwa trakty (0..7): jednotrakt przy krawędzi
    mid2 = _corridor_axis_offset(0.0, 7.0, 0.85, (0.0, 5.7))
    band_lo, band_hi = (mid2 - 0.85) - 0.0, 7.0 - (mid2 + 0.85)
    assert min(band_lo, band_hi) <= 1e-6
    assert max(band_lo, band_hi) >= MIN_TRAKT_DEPTH_M - 1e-9

    # strefa zbyt płytka na regułę (0..3): legacy clamp, bez wyjątku
    mid3 = _corridor_axis_offset(0.0, 3.0, 0.85, (0.0, 5.7))
    assert 0.85 <= mid3 <= 3.0 - 0.85 + 1e-9

    # bez klatki, głęboka strefa: środek spełnia regułę
    mid4 = _corridor_axis_offset(0.0, 12.0, 0.85, None)
    assert abs(mid4 - 6.0) < 1e-9


def test_corridor_and_centerline_share_axis():
    from services.circulation import _build_corridor, _corridor_centerline
    from shapely.geometry import box

    zone = Polygon([(0, 0), (40, 0), (40, 12), (0, 12)])
    cage = box(0, 0, 4.2, 5.7)
    corridor = _build_corridor(zone, 1.5, cage)
    line = _corridor_centerline(zone, 1.5, cage)
    assert line is not None
    (x1, y1), (x2, y2) = line
    assert y1 == y2  # korytarz poziomy
    cminy, cmaxy = corridor.bounds[1], corridor.bounds[3]
    assert abs((cminy + cmaxy) / 2.0 - y1) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -k "dead_band or axis_offset or share_axis" -v`
Expected: FAIL — `ImportError: cannot import name 'MIN_TRAKT_DEPTH_M'` / `_corridor_axis_offset`.

- [ ] **Step 3: Implement the helper and rewire both functions**

In `backend/services/circulation.py`, directly above `_build_corridor` add:

```python
MIN_TRAKT_DEPTH_M = 4.0
"""Minimalna głębokość traktu mieszkalnego między korytarzem a elewacją
(spec 2026-07-13 trakt-aware-corridor §A). Trakt płytszy niż to jest
architektonicznie martwy (pokoje < 2.4 m, proporcje > 1:3) -- korytarz ma
zostawić pas ~0 (jednotrakt) albo >= tej wartości."""


def _corridor_axis_offset(
    lo: float, hi: float, half: float, cage_bounds: tuple[float, float] | None
) -> float:
    """Pozycja osi korytarza na osi poprzecznej strefy [lo, hi].

    Kandydaci (spec §A): (a) oba trakty >= MIN_TRAKT_DEPTH_M, oś możliwie
    blisko klatki; (b)/(c) korytarz przy krawędzi lo/hi (jednotrakt), gdy
    pozostały trakt >= MIN_TRAKT_DEPTH_M. Kandydat odpada, jeśli korytarz
    przestałby dotykać klatki (przedział touch = bounds klatki +- half).
    Brak kandydatów (strefa zbyt płytka) -> dotychczasowy clamp do wnętrza
    strefy, żeby degeneraty zachowywały się jak przed zmianą."""
    center = (lo + hi) / 2.0
    anchor = (cage_bounds[0] + cage_bounds[1]) / 2.0 if cage_bounds is not None else center
    legacy = max(lo + half, min(hi - half, anchor))

    candidates: list[float] = []
    bal_lo, bal_hi = lo + half + MIN_TRAKT_DEPTH_M, hi - half - MIN_TRAKT_DEPTH_M
    if bal_lo <= bal_hi:
        candidates.append(max(bal_lo, min(bal_hi, anchor)))
    if (hi - lo) - 2.0 * half >= MIN_TRAKT_DEPTH_M:
        candidates.append(lo + half)
        candidates.append(hi - half)
    if cage_bounds is not None:
        touch_lo, touch_hi = cage_bounds[0] - half, cage_bounds[1] + half
        candidates = [c for c in candidates if touch_lo <= c <= touch_hi]
    if not candidates:
        return legacy
    return min(candidates, key=lambda c: abs(c - anchor))
```

Rewire `_build_corridor` (replace its two branches' mid computation):

```python
    if w >= h:
        half = (width + 2 * NET_SHRINK_M) / 2.0
        cage_bounds = (cage_polygon.bounds[1], cage_polygon.bounds[3]) if cage_polygon else None
        mid_y = _corridor_axis_offset(miny, maxy, half, cage_bounds)
        corridor = Polygon(
            [(minx, mid_y - half), (maxx, mid_y - half), (maxx, mid_y + half), (minx, mid_y + half)]
        )
    else:
        half = (width + 2 * NET_SHRINK_M) / 2.0
        cage_bounds = (cage_polygon.bounds[0], cage_polygon.bounds[2]) if cage_polygon else None
        mid_x = _corridor_axis_offset(minx, maxx, half, cage_bounds)
        corridor = Polygon(
            [(mid_x - half, miny), (mid_x + half, miny), (mid_x + half, maxy), (mid_x - half, maxy)]
        )
```

Rewire `_corridor_centerline` identically (keep its existing `grown_width >= h/w -> None` early exits):

```python
    if w >= h:
        if grown_width >= h:
            return None
        cage_bounds = (cage_polygon.bounds[1], cage_polygon.bounds[3]) if cage_polygon else None
        mid_y = _corridor_axis_offset(miny, maxy, half, cage_bounds)
        return ((minx, mid_y), (maxx, mid_y))
    else:
        if grown_width >= w:
            return None
        cage_bounds = (cage_polygon.bounds[0], cage_polygon.bounds[2]) if cage_polygon else None
        mid_x = _corridor_axis_offset(minx, maxx, half, cage_bounds)
        return ((mid_x, miny), (mid_x, maxy))
```

Note the anchor change: legacy used the cage CENTROID, the helper uses the center of cage bounds — identical for the rectangular cages this codebase produces (constant `CAGE_WIDTH_M × CAGE_DEPTH_M` boxes and their unions).

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -k "dead_band or axis_offset or share_axis" -v`
Expected: PASS.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: some pre-existing tests asserting the OLD corridor position may fail (e.g. concrete-y-coordinate assertions in test_circulation.py / test_evacuation.py / test_cage_placement.py). For each failure: read the test, decide whether it encodes the old cage-glued position (update it to assert the NEW trakt contract — bands ~0 or >= MIN_TRAKT_DEPTH_M, corridor touches cage) or a position-independent invariant (must keep passing unchanged). List every updated test + 1-line justification in your report. Suite must end exit 0.

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: corridor axis is trakt-aware - bands are ~0 or >= MIN_TRAKT_DEPTH_M, cage contact preserved"
```

(Add any other test files you had to update to the `git add` list, by name.)

---

### Task 2: Perpendicular trakt slicer (B) — new module

**Files:**
- Create: `backend/services/trakt_division.py`
- Test: `backend/tests/test_trakt_division.py` (new file)

**Interfaces:**
- Consumes: `MIN_CELL_DIMENSION_M` (import from `services.unit_mix`), `ApartmentSpec` (import from `services.unit_mix`), `ApartmentCell` (deferred import from `services.layout` inside the function — module-level import is a cycle).
- Produces: `slice_trakts(remainder, circulation_geometry, specs: list[ApartmentSpec], rng: random.Random | None) -> tuple[list, Polygon | MultiPolygon | None]` — same return contract as `fit_program_to_rectangles` (cells, leftover), so Task 3 can swap it in.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_trakt_division.py`)

```python
"""Testy podziału traktowego (spec 2026-07-13 §B): cięcia wyłącznie
prostopadle do korytarza, komórka = pełna głębokość traktu."""

import random

from shapely.geometry import Polygon, box

from services.trakt_division import slice_trakts
from services.unit_mix import ApartmentSpec


def _specs(*areas):
    return [ApartmentSpec(type=f"T{i}", min_area_m2=a, target_count=1) for i, a in enumerate(areas)]


def test_rect_trakt_full_depth_cells():
    """Trakt 30x6 nad poziomym korytarzem: 3 komórki po 60 m2 -> szer. 10 m,
    każda dotyka i korytarza (y=0), i elewacji (y=6)."""
    trakt = box(0, 0, 30, 6)
    corridor = box(0, -1.7, 30, 0)
    cells, leftover = slice_trakts(trakt, corridor, _specs(60, 60, 60), rng=None)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 60.0) < 0.5
        assert c.polygon.bounds[1] < 1e-6 and c.polygon.bounds[3] > 6 - 1e-6  # pełna głębokość
        assert c.polygon.distance(corridor) < 1e-6
    assert leftover is None or leftover.area < 0.5


def test_notched_trakt_stepped_cells():
    """Trakt z wcięciem (klatka) -> komórki schodkowe, pole trzyma cel."""
    trakt = Polygon([(0, 0), (20, 0), (20, 6), (12, 6), (12, 4), (8, 4), (8, 6), (0, 6)])
    corridor = box(0, -1.7, 20, 0)
    cells, leftover = slice_trakts(trakt, corridor, _specs(50, 54), rng=None)
    assert len(cells) == 2
    for c, target in zip(cells, (50.0, 54.0)):
        assert abs(c.polygon.area - target) < 1.0
        assert c.polygon.distance(corridor) < 1e-6


def test_component_not_touching_corridor_becomes_leftover():
    far = box(100, 100, 110, 106)
    corridor = box(0, -1.7, 30, 0)
    cells, leftover = slice_trakts(far, corridor, _specs(60), rng=None)
    assert cells == []
    assert leftover is not None and abs(leftover.area - 60.0) < 1e-6


def test_deterministic_for_same_seed():
    trakt = box(0, 0, 30, 6)
    corridor = box(0, -1.7, 30, 0)
    a, _ = slice_trakts(trakt, corridor, _specs(60, 45, 70), rng=random.Random(3))
    b, _ = slice_trakts(trakt, corridor, _specs(60, 45, 70), rng=random.Random(3))
    assert [c.polygon.bounds for c in a] == [c.polygon.bounds for c in b]


def test_vertical_corridor_slices_horizontally():
    """Korytarz pionowy -> cięcia poziome (y), komórki na pełną szerokość traktu."""
    trakt = box(0, 0, 6, 30)
    corridor = box(-1.7, 0, 0, 30)
    cells, _ = slice_trakts(trakt, corridor, _specs(60, 60, 60), rng=None)
    assert len(cells) == 3
    for c in cells:
        assert c.polygon.bounds[0] < 1e-6 and c.polygon.bounds[2] > 6 - 1e-6  # pełna szerokość
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_trakt_division.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.trakt_division'`.

- [ ] **Step 3: Implement the module**

Create `backend/services/trakt_division.py`:

```python
"""Podział traktowy mieszkań (spec 2026-07-13 §B, user report "cienkie
prostokątne mieszkania"): komórki powstają WYŁĄCZNIE cięciami prostopadłymi
do przyległego korytarza, więc każda z definicji rozciąga się od korytarza
do elewacji. Zamiennik fit_program_to_rectangles dla przebiegów, które znają
geometrię komunikacji; resztki końcowe domyka istniejący zero-leftover merge
w iterate_units (_merge_leftover_into_cells) -- stąd naturalne "L" w
narożnikach."""

import random
import uuid

from shapely.geometry import MultiPolygon, Polygon, box
from shapely.ops import unary_union

from services.unit_mix import MIN_CELL_DIMENSION_M, ApartmentSpec

_TOUCH_TOL_M = 0.05
"""Maks. odległość komponent-korytarz uznawana za styk (ściany działowe
w tym silniku są liniami osiowymi, geometrie stykają się na 0)."""

_AREA_TOL_M2 = 0.01
_BISECT_ITERS = 48


def _polygons(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]


def _clip_area(component: Polygon, horizontal: bool, lo: float, hi: float) -> float:
    minx, miny, maxx, maxy = component.bounds
    clip = (
        box(lo, miny - 1.0, hi, maxy + 1.0) if horizontal else box(minx - 1.0, lo, maxx + 1.0, hi)
    )
    return component.intersection(clip).area


def _clip(component: Polygon, horizontal: bool, lo: float, hi: float):
    minx, miny, maxx, maxy = component.bounds
    clip = (
        box(lo, miny - 1.0, hi, maxy + 1.0) if horizontal else box(minx - 1.0, lo, maxx + 1.0, hi)
    )
    return component.intersection(clip)


def slice_trakts(remainder, circulation_geometry, specs: list[ApartmentSpec], rng: random.Random | None):
    """(cells, leftover) -- kontrakt zwrotu jak fit_program_to_rectangles.

    Komponenty remainder to naturalne trakty (korytarz już je rozciął).
    Dla komponentu przylegającego do poziomego korytarza tniemy pionowo
    (kursor po x), do pionowego -- poziomo. Pole komórki trafia w cel
    bisekcją granicy (radzi sobie z wcięciami klatek: komórka wychodzi
    schodkowa, jak na referencyjnym rzucie usera). Komponenty bez styku
    z korytarzem w całości idą do leftover."""
    from services.layout import ApartmentCell  # deferred: cykl layout->unit_mix

    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)
    components = _polygons(remainder)
    corridor_parts = _polygons(circulation_geometry)
    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(components)

    cells: list = []
    leftover_parts: list[Polygon] = []

    for component in components:
        part = next((p for p in corridor_parts if component.distance(p) < _TOUCH_TOL_M), None)
        if part is None or not queue:
            leftover_parts.append(component)
            continue
        pminx, pminy, pmaxx, pmaxy = part.bounds
        horizontal = (pmaxx - pminx) >= (pmaxy - pminy)

        minx, miny, maxx, maxy = component.bounds
        cursor = minx if horizontal else miny
        end = maxx if horizontal else maxy
        remaining_area = component.area

        while queue and remaining_area > _AREA_TOL_M2:
            spec = queue[0]
            target = spec.min_area_m2
            if remaining_area < target * 0.6:
                break
            if remaining_area <= target:
                hi = end
            else:
                lo_b, hi_b = cursor, end
                for _ in range(_BISECT_ITERS):
                    mid = (lo_b + hi_b) / 2.0
                    if _clip_area(component, horizontal, cursor, mid) < target:
                        lo_b = mid
                    else:
                        hi_b = mid
                hi = hi_b
            if hi - cursor < MIN_CELL_DIMENSION_M:
                hi = min(cursor + MIN_CELL_DIMENSION_M, end)
            piece = _clip(component, horizontal, cursor, hi)
            piece_polys = _polygons(piece)
            if not piece_polys:
                break
            main = max(piece_polys, key=lambda p: p.area)
            for extra in piece_polys:
                if extra is not main:
                    leftover_parts.append(extra)
            if main.area < target * 0.5 and hi < end - 1e-9:
                # wcięcie zjadło pole -- poszerz o brakującą powierzchnię raz
                hi2 = min(end, hi + (target - main.area) / max(1e-6, (pmaxy - pminy) if horizontal else (pmaxx - pminx)))
                piece2 = _clip(component, horizontal, cursor, hi2)
                polys2 = _polygons(piece2)
                if polys2:
                    main = max(polys2, key=lambda p: p.area)
                    hi = hi2
            queue.pop(0)
            cells.append(ApartmentCell(id=str(uuid.uuid4()), type=spec.type, polygon=main))
            cursor = hi
            tail = _clip(component, horizontal, cursor, end)
            remaining_area = tail.area

        tail = _clip(component, horizontal, cursor, end)
        for t in _polygons(tail):
            if t.area > _AREA_TOL_M2:
                leftover_parts.append(t)

    leftover = unary_union([p for p in leftover_parts if p.area > _AREA_TOL_M2]) if leftover_parts else None
    if leftover is not None and (leftover.is_empty or leftover.area <= _AREA_TOL_M2):
        leftover = None
    return cells, leftover
```

- [ ] **Step 4: Run the module tests**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_trakt_division.py -v`
Expected: PASS (5/5). If `test_notched_trakt_stepped_cells` misses tolerance, inspect whether the notch-widening branch fired; adjust the widening denominator to the COMPONENT depth (`maxy - miny` / `maxx - minx`), not the corridor part's — then re-run. Do not loosen the test tolerance beyond 1.0 m².

- [ ] **Step 5: Run the full suite (no regressions expected — nothing imports the new module yet)**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add backend/services/trakt_division.py backend/tests/test_trakt_division.py
git commit -m "feat: perpendicular trakt slicer - cells span corridor-to-facade by construction"
```

---

### Task 3: Wire slicer into iterate_units + end-to-end on the failing footprint

**Files:**
- Modify: `backend/services/unit_mix.py` (`iterate_units`, the `fit_program_to_rectangles` call)
- Test: `backend/tests/test_unit_iterations.py` (append e2e; update tests whose cell-shape expectations legitimately change), `backend/tests/test_layout.py` (endpoint-level e2e)

**Interfaces:**
- Consumes: `slice_trakts` (Task 2), `hard_constraint_violations` (existing).
- Produces: `iterate_units` transparently uses trakt slicing when `circulation_geometry` is present; API surfaces unchanged.

- [ ] **Step 1: Write the failing e2e test** (append to `backend/tests/test_unit_iterations.py`)

```python
def test_user_footprint_20260713_yields_hard_valid_layout():
    """Repro exportu domko_export_2026-07-13 (68x12): po fixie A (korytarz
    trakt-aware) + B (cięcia prostopadłe) przynajmniej jedna iteracja musi
    spełniać wszystkie zakazy, a zwycięzca ma zero naruszeń."""
    from services.circulation import place_circulation
    from services.unit_mix import ProgramShare, iterate_units

    footprint = Polygon([(-32, -2), (36, -2), (36, 10), (-32, 10)])
    circ = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    shares = [
        ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
        ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
        ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
        ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
    ]
    cells, metas, best_seed, _ = iterate_units(
        circ.remainder, shares, iterations=10,
        footprint=footprint, circulation_geometry=circ.circulation_geometry,
    )
    assert any(m.hard_valid for m in metas), [m.hard_violations for m in metas]
    winner = next(m for m in metas if m.seed == best_seed)
    assert winner.hard_valid, winner.hard_violations
    # każda komórka zwycięzcy: styk z korytarzem i elewacją
    edge = footprint.exterior.buffer(0.01)
    for c in cells:
        assert c.polygon.distance(circ.circulation_geometry) < 0.01
        assert c.polygon.boundary.intersection(edge).length > 0
```

- [ ] **Step 2: Run it to verify it fails on current main**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -k user_footprint_20260713 -v`
Expected: FAIL (before wiring, legacy BSP still slices; if Task 1 alone already makes it pass, note that in the report and continue — the wiring below is still required for the perpendicular guarantee).

- [ ] **Step 3: Wire the slicer into `iterate_units`**

In `backend/services/unit_mix.py`, find in `iterate_units`:

```python
    rectangles = rectangle_decompose(remainder)
```

and the loop line:

```python
        cells, leftover = fit_program_to_rectangles(list(rectangles), specs, rng=rng)
```

Replace with (lazy legacy decompose, trakt path when circulation known):

```python
    use_trakts = circulation_geometry is not None and not circulation_geometry.is_empty
    rectangles = [] if use_trakts else rectangle_decompose(remainder)
```

```python
        if use_trakts:
            from services.trakt_division import slice_trakts

            cells, leftover = slice_trakts(remainder, circulation_geometry, specs, rng=rng)
        else:
            cells, leftover = fit_program_to_rectangles(list(rectangles), specs, rng=rng)
```

(`subdivide_units` — the classic non-iterative fallback — stays on the legacy path untouched.)

- [ ] **Step 4: Run the e2e test, then the full suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -k user_footprint_20260713 -v`
Expected: PASS.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: tests that fed `circulation_geometry` into `iterate_units` and asserted legacy cell shapes/counts may fail — update each to the new contract (cells full-trakt, counts may differ by ±1 from merge) with a 1-line justification in the report; suite ends exit 0.

- [ ] **Step 5: Endpoint-level dual-surface check** (append to `backend/tests/test_layout.py`)

```python
def test_generate_endpoint_user_footprint_20260713_winner_hard_valid(client):
    """Dual-surface: /generate na obrysie z exportu 2026-07-13 zwraca
    zwycięzcę bez naruszeń zakazów."""
    body = {
        "footprint": [[-32, -2], [36, -2], [36, 10], [-32, 10]],
        "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5},
        "apartments": [
            {"type": "M1", "min_area_m2": 28.5, "target_count": 1, "percentage": 10, "area_min_m2": 25, "area_max_m2": 32},
            {"type": "M2", "min_area_m2": 43.0, "target_count": 4, "percentage": 40, "area_min_m2": 38, "area_max_m2": 48},
            {"type": "M3", "min_area_m2": 64.0, "target_count": 4, "percentage": 40, "area_min_m2": 58, "area_max_m2": 70},
            {"type": "M4", "min_area_m2": 81.0, "target_count": 1, "percentage": 10, "area_min_m2": 72, "area_max_m2": 90},
        ],
    }
    response = client.post("/api/v1/layout/generate", json=body)
    assert response.status_code == 200
    data = response.json()
    iters = data["iterations"]
    assert iters and any(m["hard_valid"] for m in iters)
    best = min((m for m in iters if m["hard_valid"]), key=lambda m: m["score"])
    assert best["hard_violations"] == []
```

(If this file's existing `/generate` tests use a different fixture convention than `client`, match the neighboring test's convention instead of inventing a new one.)

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout.py -k 20260713 -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/services/unit_mix.py backend/tests/test_unit_iterations.py backend/tests/test_layout.py
git commit -m "feat: iterate_units slices perpendicular trakts when circulation is known"
```

(Add any other updated test files by name.)

---

### Task 4: Verification on live servers + handoff

**Files:** none (verification task)

- [ ] **Step 1: Full backend suite + frontend typecheck**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` — expected exit 0.
Run: `cd frontend && npx tsc --noEmit` — expected exit 0 (no frontend changes in this plan; this guards accidental drift).

- [ ] **Step 2: Live smoke on the user's exact failing footprint**

Ensure a fresh backend serves on :8000 (kill stale/orphaned uvicorn workers first — check `Get-CimInstance Win32_Process` for spawn children of dead parents, see gotcha memory), then:

```bash
curl -s -X POST http://localhost:8000/api/v1/layout/generate -H "Content-Type: application/json" -d '{"footprint": [[-32,-2],[36,-2],[36,10],[-32,10]], "circulation": {"corridor_width_m": 1.5, "place_cage": true, "cage_size_m": 2.5}, "apartments": [{"type":"M1","min_area_m2":28.5,"target_count":1,"percentage":10,"area_min_m2":25,"area_max_m2":32},{"type":"M2","min_area_m2":43,"target_count":4,"percentage":40,"area_min_m2":38,"area_max_m2":48},{"type":"M3","min_area_m2":64,"target_count":4,"percentage":40,"area_min_m2":58,"area_max_m2":70},{"type":"M4","min_area_m2":81,"target_count":1,"percentage":10,"area_min_m2":72,"area_max_m2":90}]}'
```

Verify in the response: at least one iteration `hard_valid: true`; the corridor bbox leaves no band in (0, 4.0) m against footprint edges; no apartment with MRR ratio > 3 among the winner's cells.

- [ ] **Step 3: Hand the user a UI checklist**

1. Narysuj/wgraj obrys ~68×12, Umieść korytarz i klatkę → korytarz NIE zostawia pasa ~2 m przy elewacji (albo dosunięty do elewacji, albo oba trakty ≥ 4 m).
2. Podziel na mieszkania → mieszkania od korytarza do elewacji, brak poziomych pasków wzdłuż korytarza; narożne mogą być "L".
3. Lista iteracji: większość bez ⚠; zwycięzca bez ⚠.
4. Kropki ewakuacyjne leżą na osi korytarza (sync osi po zmianie).
5. Regresja: przesuwanie klatek (snap 0.1 m), edycja osi korytarza, eksport DXF/PDF.
