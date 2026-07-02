# Layout Engine Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `bsp_zones()`'s broken concave-footprint handling with a real rectangle-decomposition algorithm, split `generate_layout()` into two explicit stages (circulation placement, then unit-mix subdivision), and add three Finch-inspired validation rules — without changing `LayoutResult`'s shape or breaking the optimizer/solar/WT/export/frontend consumers that already work.

**Architecture:** See `docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md` for the full design and rationale (including the corrected corridor approach — corridor geometry itself was never broken, only zone decomposition was). Two new backend modules (`circulation.py`, `unit_mix.py`), `layout.py`'s `generate_layout()` becomes a thin wrapper, `bsp.py` gets a real `rectangle_decompose()` and a fixed `split_polygon_by_edge()`.

**Tech Stack:** Python 3.11, FastAPI, Shapely 2.x, pytest, hypothesis (new dev dependency), Next.js/TypeScript, react-konva.

## Global Constraints

- `LayoutResult`, `ApartmentCell`, `Zone` dataclass fields stay backward-compatible — only additive changes (`ApartmentCell.area_tolerance_exceeded: bool = False`).
- `circulation_geometry` may now be `Polygon` or `MultiPolygon` in practice — any code reading it must handle both (check `hasattr(geom, "geoms")`), never assume `Polygon`.
- Backend venv: always `backend/.venv/Scripts/python.exe -m pytest` / `-m ruff check .` — the global `python` on PATH lacks project dependencies.
- Every backend task ends with `cd backend && ./.venv/Scripts/python.exe -m pytest -q` passing in full (not just the new test) and `./.venv/Scripts/python.exe -m ruff check .` clean.
- Frontend tasks end with `cd frontend && npx tsc --noEmit` clean.
- New Finch-inspired validation rules (facade frontage, aspect ratio) are **warnings**, not hard failures — same two-tier pattern as existing `MIN_CONTACT_LENGTH_M` (warning) vs `MIN_DOOR_CONTACT_LENGTH_M` (hard error) in `wt_validation.py`. The cage-facade contact rule is a **hard error** (real WT §68 lighting/smoke-extraction requirement, not just a Finch heuristic).
- Snap/units stay in meters (floats) — the Finch integer-cm proposal was discussed but not adopted for this task (out of scope, noted in spec §10).

---

## Phase 1 — `bsp.py`: fix `split_polygon_by_edge`, add `rectangle_decompose`

### Task 1: Fix `split_polygon_by_edge` (concave multi-intersection + collinear bugs)

**Files:**
- Modify: `backend/services/bsp.py`
- Test: `backend/tests/test_bsp.py`

**Interfaces:**
- Produces: `split_polygon_by_edge(polygon: Polygon, p1: tuple[float, float], p2: tuple[float, float]) -> tuple[Polygon, Polygon]` — same signature as today, raises `ValueError` on failure (unchanged contract for the existing `/layout/split` endpoint).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_bsp.py`:

```python
def test_split_polygon_by_edge_concave_does_not_lose_area():
    # U-shape, 84 m^2 total (matches the shape from the 2026-07-02 audit)
    u_shape = Polygon([
        (0, 0), (2, 0), (2, 6), (10, 6), (10, 0), (12, 0),
        (12, 8), (0, 8),
    ])
    assert u_shape.area == 84.0
    # Horizontal cut through the slot at y=7 crosses the boundary 4 times
    # (both arms of the U plus both sides of the slot notch).
    part_a, part_b = split_polygon_by_edge(u_shape, (-1, 7), (13, 7))
    assert abs((part_a.area + part_b.area) - u_shape.area) < 1e-6


def test_split_polygon_by_edge_collinear_with_existing_edge():
    square = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    # Cut line lies exactly on the top edge (y=10) — must not silently
    # drop this as "no valid split", nor lose area.
    part_a, part_b = split_polygon_by_edge(square, (0, 10), (10, 10))
    # A cut along the boundary itself degenerates to (whole, empty) or
    # raises — either is acceptable as long as no area is silently lost
    # and no exception other than ValueError propagates.
    total = part_a.area + part_b.area
    assert abs(total - square.area) < 1e-6 or total == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_bsp.py -k "concave_does_not_lose_area or collinear_with_existing_edge" -v`
Expected: `test_split_polygon_by_edge_concave_does_not_lose_area` FAILS (today's implementation returns `part_a.area + part_b.area == 68.0`, not `84.0` — verified during audit).

- [ ] **Step 3: Replace `split_polygon_by_edge` with a `shapely.ops.split`-based implementation**

In `backend/services/bsp.py`, add imports at the top (after existing `from shapely.geometry import LineString, Polygon`):

```python
import math

from shapely.ops import split as shapely_split
from shapely.ops import unary_union
```

Replace the existing `split_polygon_by_edge` function body entirely:

```python
def split_polygon_by_edge(
    polygon: Polygon, p1: tuple[float, float], p2: tuple[float, float]
) -> tuple[Polygon, Polygon]:
    """Dzieli poligon prostą przechodzącą przez dwa punkty (p1, p2).

    Rozszerza odcinek p1-p2 do prostej przecinającej cały poligon, następnie
    używa shapely.ops.split — poprawnie obsługuje poligony wklęsłe, w
    których prosta może przeciąć granicę więcej niż dwa razy (każdy
    fragment trafia na właściwą stronę wg położenia względem prostej, żadna
    powierzchnia nie ginie — naprawa buga z audytu 2026-07-02, gdzie
    poprzednia wersja brała tylko dwa skrajne punkty przecięcia i cicho
    odrzucała resztę geometrii przez `polygon.difference(cutter.buffer(eps))`).
    Naprawia też przypadek, gdy linia cięcia jest kolinearna z istniejącą
    krawędzią (poprzednia wersja obsługiwała tylko przecięcia typu
    Point/MultiPoint, cicho ignorując LineString — analog buga solarnego
    naprawionego dziś w services/solar_analysis.py).
    """
    minx, miny, maxx, maxy = polygon.bounds
    diag = math.hypot(maxx - minx, maxy - miny) * 2 + 1.0
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        raise ValueError("Split line points must be distinct")
    ux, uy = dx / length, dy / length
    ext_a = (p1[0] - ux * diag, p1[1] - uy * diag)
    ext_b = (p2[0] + ux * diag, p2[1] + uy * diag)
    cutter = LineString([ext_a, ext_b])

    if not cutter.intersects(polygon):
        raise ValueError("Split line does not intersect polygon boundary in two distinct points")

    try:
        result = shapely_split(polygon, cutter)
    except Exception as exc:
        raise ValueError(f"Could not split polygon: {exc}") from exc

    geoms = [g for g in result.geoms if g.geom_type == "Polygon" and g.area > 1e-9]
    if len(geoms) < 2:
        raise ValueError("Split line does not intersect polygon boundary in two distinct points")

    # Normal to the cutting line — used to decide which side each resulting
    # fragment is on (there can be more than one fragment per side for a
    # concave polygon; they get unioned together).
    nx_, ny_ = -uy, ux

    def side(g: Polygon) -> float:
        c = g.centroid
        return (c.x - p1[0]) * nx_ + (c.y - p1[1]) * ny_

    left = [g for g in geoms if side(g) >= 0]
    right = [g for g in geoms if side(g) < 0]
    if not left or not right:
        raise ValueError("Split did not produce two polygons")

    part_a = unary_union(left) if len(left) > 1 else left[0]
    part_b = unary_union(right) if len(right) > 1 else right[0]
    return part_a, part_b
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_bsp.py -v`
Expected: all pass, including the two new tests and all pre-existing `split_polygon_by_edge`/`test_layout_split.py` tests (regression check — run `-v` and read every line, don't just check exit code).

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 96/96 pass (full suite regression).

- [ ] **Step 5: Commit**

```bash
git add backend/services/bsp.py backend/tests/test_bsp.py
git commit -m "fix: split_polygon_by_edge loses area for concave/collinear splits

Rewrite using shapely.ops.split() with a line extended across the whole
polygon, grouping resulting fragments by side-of-line instead of picking
two extreme intersection points and discarding the rest via
difference(cutter.buffer(eps)). Fixes both the >2-intersection area-loss
bug and the collinear-with-existing-edge case (previously silently
ignored, same root cause class as the solar_analysis.py facade bug fixed
earlier today)."
```

### Task 2: Add `rectangle_decompose()`

**Files:**
- Modify: `backend/services/bsp.py`
- Test: `backend/tests/test_bsp.py`

**Interfaces:**
- Consumes: `concave_vertices(polygon: Polygon) -> list[tuple[int, float, float]]` (existing), `split_polygon_by_edge` (Task 1).
- Produces: `rectangle_decompose(poly: Polygon | MultiPolygon) -> list[Polygon]` — new public function, used by both `circulation.py` (Phase 3) and `unit_mix.py` (Phase 4).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_bsp.py`:

```python
from shapely.geometry import MultiPolygon


def test_rectangle_decompose_convex_returns_single_part():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    parts = rectangle_decompose(rect)
    assert len(parts) == 1
    assert abs(parts[0].area - 60.0) < 1e-6


def test_rectangle_decompose_l_shape_no_area_lost_no_overlap():
    l_shape = Polygon([(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)])
    total_area = l_shape.area  # 76.0
    parts = rectangle_decompose(l_shape)
    assert len(parts) >= 2
    assert abs(sum(p.area for p in parts) - total_area) < 1e-6
    # No two parts overlap by more than a sliver.
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            assert parts[i].intersection(parts[j]).area < 1e-6
    # Every part is (close to) rectangular: 4 vertices after simplification.
    for p in parts:
        assert not concave_vertices(p), f"part still concave: {list(p.exterior.coords)}"


def test_rectangle_decompose_u_shape_no_area_lost():
    u_shape = Polygon([
        (0, 0), (2, 0), (2, 6), (10, 6), (10, 0), (12, 0),
        (12, 8), (0, 8),
    ])
    total_area = u_shape.area  # 84.0
    parts = rectangle_decompose(u_shape)
    assert abs(sum(p.area for p in parts) - total_area) < 1e-6
    for p in parts:
        assert not concave_vertices(p)


def test_rectangle_decompose_multipolygon_handles_each_part():
    a = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    b = Polygon([(10, 0), (15, 0), (15, 5), (10, 5)])
    parts = rectangle_decompose(MultiPolygon([a, b]))
    assert len(parts) == 2
    assert abs(sum(p.area for p in parts) - 50.0) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_bsp.py -k rectangle_decompose -v`
Expected: FAIL with `NameError: name 'rectangle_decompose' is not defined`.

- [ ] **Step 3: Implement `rectangle_decompose`**

Add to `backend/services/bsp.py`, after `split_polygon_by_edge`:

```python
def rectangle_decompose(poly: Polygon | MultiPolygon) -> list[Polygon]:
    """Dzieli (możliwie wklęsły) poligon na listę prawie-prostokątnych części.

    Rekurencyjnie tnie przez każdy wierzchołek wklęsły — przedłużając jedną
    z dwóch sąsiadujących krawędzi przez ten wierzchołek w głąb poligonu —
    aż nie zostaną żadne wierzchołki wklęsłe. Zastępuje `bsp_zones()`'s
    fikcyjną obsługę wklęsłości (stały nibble 1x1m w narożniku, który
    często zostawiał resztę wciąż wklęsłą — patrz audyt 2026-07-02).

    Poligony wypukłe, ale nie ściśle prostokątne (np. skośny czworobok po
    ekstremalnej edycji wierzchołka), zostają jedną nie-prostokątną częścią
    — udokumentowane ograniczenie, patrz spec §10.
    """
    if hasattr(poly, "geoms"):
        result: list[Polygon] = []
        for part in poly.geoms:
            if part.geom_type == "Polygon" and part.area > 1e-9:
                result.extend(rectangle_decompose(part))
        return result

    if poly.is_empty or poly.area < 1e-9:
        return []

    cv = concave_vertices(poly)
    if not cv:
        return [poly]

    idx, x, y = cv[0]
    coords = list(poly.exterior.coords)[:-1]
    n = len(coords)
    prev_pt = coords[(idx - 1) % n]
    curr_pt = (x, y)
    next_pt = coords[(idx + 1) % n]

    minx, miny, maxx, maxy = poly.bounds
    diag = math.hypot(maxx - minx, maxy - miny) * 2 + 1.0

    candidates: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for anchor in (prev_pt, next_pt):
        edx, edy = curr_pt[0] - anchor[0], curr_pt[1] - anchor[1]
        elen = math.hypot(edx, edy)
        if elen < 1e-9:
            continue
        ux, uy = edx / elen, edy / elen
        far = (curr_pt[0] + ux * diag, curr_pt[1] + uy * diag)
        candidates.append((curr_pt, far))

    for p1, p2 in candidates:
        try:
            part_a, part_b = split_polygon_by_edge(poly, p1, p2)
        except ValueError:
            continue
        if part_a.area < 1e-9 or part_b.area < 1e-9:
            continue
        return rectangle_decompose(part_a) + rectangle_decompose(part_b)

    # Neither candidate cut produced a valid two-way split (degenerate
    # geometry) — return as a single (still-concave) zone rather than loop
    # forever. Downstream code (fit_program_to_rectangles) falls back to
    # bounding-box sizing for non-rectangular parts, same as today.
    return [poly]
```

Add `MultiPolygon` to the shapely import at the top of `bsp.py`:

```python
from shapely.geometry import LineString, MultiPolygon, Polygon
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_bsp.py -v`
Expected: all pass.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: 96/96 pass, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/services/bsp.py backend/tests/test_bsp.py
git commit -m "feat: add rectangle_decompose() — real concave-footprint decomposition

Cuts recursively through each reflex vertex (extending an adjacent edge
into the polygon) until no concave vertices remain, using the now-fixed
split_polygon_by_edge. Replaces bsp_zones()'s fixed-size corner nibble,
which frequently left the remainder still concave for real (non-toy)
footprints — the root cause behind today's facade-matching and cut_cell
bugs. Used by both circulation.py and unit_mix.py in later phases."
```

---

## Phase 2 — `ApartmentCell` gains `area_tolerance_exceeded`

### Task 3: Add the field

**Files:**
- Modify: `backend/services/layout.py`

**Interfaces:**
- Produces: `ApartmentCell.area_tolerance_exceeded: bool` (default `False`) — consumed by `unit_mix.py` (Phase 4) and `apartment_validation.py` (Phase 7).

- [ ] **Step 1: Add the field**

In `backend/services/layout.py`, find:

```python
@dataclass
class ApartmentCell:
    id: str
    type: str
    polygon: Polygon
```

Replace with:

```python
@dataclass
class ApartmentCell:
    id: str
    type: str
    polygon: Polygon
    area_tolerance_exceeded: bool = False
    """True if this cell's area deviates from its program spec's min_area_m2
    by more than the ±3% tolerance (Finch-inspired, see fit_program_to_
    rectangles in services/unit_mix.py). Default False for cells built by
    paths that don't track this (e.g. manual apartment edits)."""
```

- [ ] **Step 2: Run full suite to confirm no breakage**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: 96/96 pass (dataclass default means every existing `ApartmentCell(...)` call site still works unchanged).

- [ ] **Step 3: Commit**

```bash
git add backend/services/layout.py
git commit -m "feat: add ApartmentCell.area_tolerance_exceeded field

Additive, defaults to False — no existing call site needs updating.
Populated by fit_program_to_rectangles (Phase 4), consumed by a new
validation rule (Phase 7)."
```

---

## Phase 3 — `circulation.py`: cage placement + corridor, moved and orchestrated

### Task 4: Create `circulation.py`, move cage-placement functions

**Files:**
- Create: `backend/services/circulation.py`
- Modify: `backend/services/layout.py` (remove moved functions, re-export nothing — callers updated in Task 5/7)
- Test: `backend/tests/test_circulation.py` (new file)

**Interfaces:**
- Consumes: `concave_vertices` (bsp.py), `corner_cage` (bsp.py).
- Produces: `CAGE_POSITION_MODES`, `_place_cage_by_mode(polygon, mode, size) -> Polygon | None` (moved verbatim from `layout.py`, same behavior).

- [ ] **Step 1: Write a regression test pinning today's cage-placement behavior**

Create `backend/tests/test_circulation.py`:

```python
from shapely.geometry import Polygon

from services.circulation import _place_cage_by_mode


def test_place_cage_auto_convex_uses_bbox_corner():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = _place_cage_by_mode(rect, "auto", 2.0)
    assert cage is not None
    assert cage.area > 0
    minx, miny, maxx, maxy = cage.bounds
    assert minx == 0.0 and miny == 0.0  # anchored at the (0,0) corner


def test_place_cage_mode_2_centered():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cage = _place_cage_by_mode(rect, "2", 2.0)
    assert cage is not None
    cx, cy = cage.centroid.x, cage.centroid.y
    assert abs(cx - 5.0) < 0.5 and abs(cy - 3.0) < 0.5


def test_place_cage_invalid_mode_raises():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    try:
        _place_cage_by_mode(rect, "bogus", 2.0)
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.circulation'`.

- [ ] **Step 3: Create `circulation.py`, move the cage functions**

In `backend/services/layout.py`, locate and **cut** (remove from this file) these five items in full: `CAGE_POSITION_MODES` constant, `concave_vertices_in_zone()`, `_build_cage()`, `_place_cage_by_mode()`, `_corner_cage_convex()`, `_centered_cage()`, `_edge_cage()`.

Create `backend/services/circulation.py`:

```python
"""Etap 1 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
umieszczenie klatki schodowej i korytarza w każdej strefie zwróconej przez
services.bsp.rectangle_decompose(). Klatka i korytarz przeniesione z
layout.py bez zmian logiki — nigdy nie były zepsute, zepsute były strefy,
które dostawały na wejściu (patrz spec §1a)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import Polygon

CAGE_POSITION_MODES = ("1a", "1b", "2", "3", "auto")
"""plan.md §4.3: 1a=elewacja front, 1b=elewacja dziedziniec/tył, 2=środek traktu,
3=narożnik, auto=narożnik wklęsły jeśli istnieje inaczej narożnik obrysu."""


def concave_vertices_in_zone(polygon: Polygon) -> list[tuple[int, float, float]]:
    """Wykrywa wierzchołki wklęsłe w pojedynczej strefie."""
    from services.bsp import concave_vertices

    return concave_vertices(polygon)


def _build_cage(
    polygon: Polygon, corner_data: tuple[int, float, float], size: float
) -> Polygon:
    """Buduje kwadratową klatkę w narożniku."""
    from services.bsp import corner_cage

    idx, x, y = corner_data
    return corner_cage(polygon, (x, y), size)


def _place_cage_by_mode(polygon: Polygon, mode: str, size: float) -> Polygon | None:
    """Umieszcza klatkę wg trybu z plan.md §4.3.

    - "3"/"auto": narożnik wklęsły jeśli istnieje (jak dotychczas), inaczej
      narożnik bounding-boxa (naprawia przypadek obrysu wypukłego, który
      wcześniej nigdy nie dostawał klatki mimo `place_cage=True`).
    - "2": środek strefy (typowe dla punktowca).
    - "1a": wzdłuż najdłuższej krawędzi zewnętrznej (elewacja frontowa).
    - "1b": wzdłuż najkrótszej krawędzi zewnętrznej — uproszczony zamiennik
      "krawędzi od dziedzińca" (wykrywanie krawędzi wewnętrznej/dziedzińca
      wymagałoby modelu sąsiednich budynków, poza zakresem tego MVP).
    """
    if polygon.is_empty or polygon.area < 1e-6:
        return None

    if mode not in CAGE_POSITION_MODES:
        raise ValueError(f"Unknown cage_position mode '{mode}'. Valid: {CAGE_POSITION_MODES}")

    if mode in ("3", "auto"):
        cv = concave_vertices_in_zone(polygon)
        if cv:
            try:
                cage = _build_cage(polygon, cv[0], size)
            except ValueError:
                return None
            return cage if cage.area > 1e-6 else None
        return _corner_cage_convex(polygon, size)

    if mode == "2":
        return _centered_cage(polygon, size)

    # "1a" / "1b"
    return _edge_cage(polygon, size, longest=(mode == "1a"))


def _corner_cage_convex(polygon: Polygon, size: float) -> Polygon | None:
    """Klatka w narożniku bounding-boxa — dla obrysów wypukłych bez wierzchołka wklęsłego."""
    minx, miny, maxx, maxy = polygon.bounds
    candidate = Polygon(
        [(minx, miny), (minx + size, miny), (minx + size, miny + size), (minx, miny + size)]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _centered_cage(polygon: Polygon, size: float) -> Polygon | None:
    """Klatka wyśrodkowana w strefie (tryb 2 — punktowiec)."""
    center = polygon.centroid
    half = size / 2.0
    candidate = Polygon(
        [
            (center.x - half, center.y - half),
            (center.x + half, center.y - half),
            (center.x + half, center.y + half),
            (center.x - half, center.y + half),
        ]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _edge_cage(polygon: Polygon, size: float, longest: bool) -> Polygon | None:
    """Klatka wzdłuż najdłuższej (tryb 1a) lub najkrótszej (tryb 1b) krawędzi, skierowana do wnętrza."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    if n < 2:
        return None

    edges = []
    for i in range(n):
        p1, p2 = coords[i], coords[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        edges.append((length, p1, p2))
    edges.sort(key=lambda e: e[0], reverse=longest)
    _, p1, p2 = edges[0]

    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    edge_len = math.hypot(dx, dy)
    if edge_len < 1e-9:
        return None
    ux, uy = dx / edge_len, dy / edge_len

    mid_x, mid_y = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    normal_x, normal_y = -uy, ux
    centroid = polygon.centroid
    if normal_x * (centroid.x - mid_x) + normal_y * (centroid.y - mid_y) < 0:
        normal_x, normal_y = -normal_x, -normal_y

    half = size / 2.0
    p_a = (mid_x - ux * half, mid_y - uy * half)
    p_b = (mid_x + ux * half, mid_y + uy * half)
    p_c = (p_b[0] + normal_x * size, p_b[1] + normal_y * size)
    p_d = (p_a[0] + normal_x * size, p_a[1] + normal_y * size)

    candidate = Polygon([p_a, p_b, p_c, p_d])
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -v`
Expected: all 3 pass.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: **failures expected** in `test_layout.py`/`test_cage_modes_and_fitting.py` — they still import `_place_cage_by_mode` etc. from `services.layout`. This is fine; Task 5 finishes the move by updating `generate_layout()` and Task 7 updates those test imports. Note the failing test names now (`pytest -q 2>&1 | tail -30`) so Task 7's regression check can confirm they're fixed, not newly broken.

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py backend/services/layout.py
git commit -m "refactor: move cage-placement functions to new circulation.py

_place_cage_by_mode + _edge_cage/_centered_cage/_corner_cage_convex/
concave_vertices_in_zone/_build_cage moved verbatim from layout.py — no
logic changes, this is purely relocating code that was never broken (only
the zones it received were, see spec §1a). layout.py's generate_layout()
and existing tests importing these from services.layout are updated in the
next two tasks — expect test_layout.py/test_cage_modes_and_fitting.py
failures until then."
```

### Task 5: Add corridor placement + `place_circulation()` orchestration

**Files:**
- Modify: `backend/services/circulation.py`
- Modify: `backend/services/layout.py` (remove `_build_corridor`)
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: `rectangle_decompose` (bsp.py, Task 2), `Zone` (bsp.py, existing), `_place_cage_by_mode` (Task 4).
- Produces: `CirculationResult` dataclass (`zones`, `circulation_geometry`, `cage_polygons`, `remainder`), `place_circulation(footprint, corridor_width_m, stair_width_m, place_cage, cage_size_m, cage_position) -> CirculationResult` — consumed by `layout.py`'s `generate_layout()` in Task 7 and the new `/layout/circulation` endpoint in Task 12.

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_circulation.py`:

```python
from shapely.geometry import Polygon

from services.circulation import place_circulation


def test_place_circulation_simple_rectangle():
    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
    )
    assert len(result.zones) == 1
    assert result.circulation_geometry is not None
    assert result.circulation_geometry.area > 0
    assert len(result.cage_polygons) == 1
    # remainder + corridor + cage should reconstruct (close to) the footprint
    total = (
        result.remainder.area
        + result.circulation_geometry.area
        + sum(c.area for c in result.cage_polygons)
    )
    assert abs(total - footprint.area) < 1e-3


def test_place_circulation_concave_u_shape_no_area_lost():
    u_shape = Polygon([
        (0, 0), (2, 0), (2, 6), (10, 6), (10, 0), (12, 0),
        (12, 8), (0, 8),
    ])
    result = place_circulation(
        u_shape,
        corridor_width_m=1.4,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.0,
        cage_position="auto",
    )
    total = (
        result.remainder.area
        + result.circulation_geometry.area
        + sum(c.area for c in result.cage_polygons)
    )
    assert abs(total - u_shape.area) < 1e-3
    # This is the regression case for the audit bug: the old bsp_zones()
    # produced a zone that was STILL concave here. Every zone we placed
    # circulation in must now be non-concave.
    from services.bsp import concave_vertices
    for zone in result.zones:
        assert not concave_vertices(zone.polygon), "zone still concave after rectangle_decompose"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -k place_circulation -v`
Expected: FAIL with `ImportError: cannot import name 'place_circulation'`.

- [ ] **Step 3: Implement corridor placement + orchestration**

In `backend/services/layout.py`, **cut** `_build_corridor()` in full (remove from this file — moved below).

Add to `backend/services/circulation.py` (imports section gets `from shapely.ops import unary_union` added, and a `Zone` import):

```python
from shapely.ops import unary_union

from services.bsp import Zone, rectangle_decompose
```

Append to the end of `circulation.py`:

```python
def _build_corridor(polygon: Polygon, width: float, cage_polygon: Polygon | None = None) -> Polygon:
    """Buduje korytarz wzdłuż osi dłuższego boku prostokątnej (po
    rectangle_decompose) strefy, uwzględniając wyrównanie do pozycji klatki
    schodowej (F2-04). Przeniesiona bez zmian logiki z layout.py — działa
    poprawnie teraz, bo strefa jest już prawie-prostokątna (patrz spec §1a:
    to nigdy nie było zepsute, tylko strefy, które dostawała na wejściu)."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return Polygon()
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        half = width / 2.0
        if cage_polygon:
            cage_y = cage_polygon.centroid.y
            mid_y = max(miny + half, min(maxy - half, cage_y))
        else:
            mid_y = (miny + maxy) / 2.0
        corridor = Polygon(
            [(minx, mid_y - half), (maxx, mid_y - half), (maxx, mid_y + half), (minx, mid_y + half)]
        )
    else:
        half = width / 2.0
        if cage_polygon:
            cage_x = cage_polygon.centroid.x
            mid_x = max(minx + half, min(maxx - half, cage_x))
        else:
            mid_x = (minx + maxx) / 2.0
        corridor = Polygon(
            [(mid_x - half, miny), (mid_x + half, miny), (mid_x + half, maxy), (mid_x - half, maxy)]
        )

    return corridor.intersection(polygon)


@dataclass
class CirculationResult:
    """Wynik Etapu 1: strefy (po rectangle_decompose), zunifikowana
    geometria komunikacji, klatki, i pozostałość na mieszkania (Etap 2)."""

    zones: list[Zone]
    circulation_geometry: Polygon | None
    cage_polygons: list[Polygon] = field(default_factory=list)
    remainder: Polygon = field(default_factory=Polygon)
    """Może być MultiPolygon w praktyce mimo adnotacji typu (patrz spec §9) —
    konsumenci muszą sprawdzać hasattr(geom, "geoms")."""


def place_circulation(
    footprint: Polygon,
    corridor_width_m: float,
    stair_width_m: float,
    place_cage: bool,
    cage_size_m: float,
    cage_position: str,
) -> CirculationResult:
    """Etap 1: dzieli obrys na prawie-prostokątne strefy (rectangle_decompose),
    umieszcza klatkę i korytarz w każdej, zwraca zunifikowany wynik."""
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]

    circulation_geom = Polygon()
    cage_polygons: list[Polygon] = []
    remainder_parts: list[Polygon] = []

    for zone in zones:
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        local_cage: Polygon | None = None
        if place_cage:
            cage_polygon = _place_cage_by_mode(zone.polygon, cage_position, cage_size_m)
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                circulation_geom = unary_union([circulation_geom, cage_polygon])
                cage_polygons.append(cage_polygon)
                zone_remaining = zone.polygon.difference(cage_polygon)
                local_cage = cage_polygon
            else:
                zone_remaining = zone.polygon
        else:
            zone_remaining = zone.polygon

        corridor = _build_corridor(zone_remaining, corridor_width_m, local_cage)
        if corridor.area > 0:
            circulation_geom = unary_union([circulation_geom, corridor])
            zone_remaining = zone_remaining.difference(corridor)

        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)

    remainder = unary_union(remainder_parts) if remainder_parts else Polygon()

    return CirculationResult(
        zones=zones,
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -v`
Expected: all 5 pass (2 from Task 4 + 3 new).

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/services/layout.py
git commit -m "feat: place_circulation() orchestrates rectangle_decompose + cage + corridor

Etap 1 of the redesign: decompose the (possibly concave) footprint into
near-rectangular zones first, then place cage and corridor per zone using
the existing (unmodified) logic. _build_corridor moved verbatim from
layout.py. Regression-tested against the U-shape case from the 2026-07-02
audit that previously left a zone still concave."
```

---

## Phase 4 — `unit_mix.py`: knapsack-style program fitting

### Task 6: Create `unit_mix.py` with `fit_program_to_rectangles()`

**Files:**
- Create: `backend/services/unit_mix.py`
- Modify: `backend/services/layout.py` (remove `_slice_apartments`, keep `_cut_cell`/`_polygon_parts`/`MIN_CELL_DIMENSION_M` — they're reused)
- Test: `backend/tests/test_unit_mix.py` (new file)

**Interfaces:**
- Consumes: `ApartmentSpec`, `ApartmentCell`, `MIN_CELL_DIMENSION_M`, `_cut_cell`, `_polygon_parts` (all `layout.py`, existing/Task 3), `rectangle_decompose` (bsp.py, Task 2).
- Produces: `subdivide_units(remainder, specs) -> tuple[list[ApartmentCell], Polygon | None]` — consumed by `layout.py`'s `generate_layout()` in Task 7 and the new `/layout/units` endpoint in Task 13.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_unit_mix.py`:

```python
from shapely.geometry import Polygon

from services.layout import ApartmentSpec
from services.unit_mix import subdivide_units


def test_subdivide_units_exact_fit_horizontal():
    rect = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    specs = [ApartmentSpec(type="M2", min_area_m2=50, target_count=3)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 50.0) < 0.5
        assert c.area_tolerance_exceeded is False


def test_subdivide_units_vertical_zone_correct_area():
    # Regression test for the depth/width _cut_cell bug fixed 2026-07-02 —
    # a zone taller than it is wide must NOT produce square (w x w) cells.
    rect = Polygon([(0, 0), (6, 0), (6, 30), (0, 30)])
    specs = [ApartmentSpec(type="M2", min_area_m2=50, target_count=3)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 50.0) < 0.5


def test_subdivide_units_uses_best_matching_spec_not_fifo():
    # Regression test for the "permanent retirement" bug (audit finding #6):
    # a small leftover part should still be matched against a LATER,
    # smaller spec even if it doesn't fit the FIRST spec in the program.
    small_rect = Polygon([(0, 0), (5, 0), (5, 6), (0, 6)])  # 30 m^2
    specs = [
        ApartmentSpec(type="M4", min_area_m2=80, target_count=1),  # doesn't fit
        ApartmentSpec(type="M1", min_area_m2=28, target_count=1),  # fits well
    ]
    cells, leftover = subdivide_units(small_rect, specs)
    assert len(cells) == 1
    assert cells[0].type == "M1"


def test_subdivide_units_flags_tolerance_exceeded():
    # A rectangle whose only achievable cut deviates from the spec by more
    # than 3% must be flagged, not silently accepted.
    rect = Polygon([(0, 0), (10, 0), (10, 3), (0, 3)])  # 30 m^2, depth=3
    # min_area_m2=50 with depth=3 needs cut_size=16.67, area=50.0 exactly —
    # use a spec that can't land within 3% given MIN_CELL_DIMENSION_M=2.0
    # forcing a floor: request an area smaller than what MIN_CELL_DIMENSION
    # can produce (2.0 * 3 = 6.0 minimum area achievable).
    specs = [ApartmentSpec(type="M0", min_area_m2=3.0, target_count=1)]
    cells, leftover = subdivide_units(rect, specs)
    assert len(cells) == 1
    assert cells[0].area_tolerance_exceeded is True


def test_subdivide_units_no_specs_returns_all_as_leftover():
    rect = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])
    cells, leftover = subdivide_units(rect, [])
    assert cells == []
    assert leftover is not None
    assert abs(leftover.area - 100.0) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_unit_mix.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.unit_mix'`.

- [ ] **Step 3: Implement `unit_mix.py`**

In `backend/services/layout.py`, **cut** `_slice_apartments()` in full (removed — replaced below). **Keep** `_cut_cell()`, `_polygon_parts()`, and `MIN_CELL_DIMENSION_M` — they stay in `layout.py` and are imported by `unit_mix.py`.

Create `backend/services/unit_mix.py`:

```python
"""Etap 2 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
dopasowanie programu mieszkań do przestrzeni pozostałej po komunikacji.
Zastępuje services.layout._slice_apartments (sekwencyjne FIFO, trwałe
odrzucanie części — audyt 2026-07-02, znalezisko #6). Reużywa
services.layout._cut_cell (naprawiony 2026-07-02, bug depth/width) do
samego cięcia — zmienia się tylko WYBÓR, którą specyfikację i który
prostokąt ciąć, nie mechanika cięcia."""

from __future__ import annotations

import uuid

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from services.bsp import rectangle_decompose
from services.layout import (
    MIN_CELL_DIMENSION_M,
    ApartmentCell,
    ApartmentSpec,
    _cut_cell,
    _polygon_parts,
)

AREA_TOLERANCE = 0.03
"""±3% (Finch §B.2, adaptowane) — patrz spec §5. Powyżej tej tolerancji
komórka jest wciąż tworzona (najlepsze dostępne dopasowanie), ale oznaczona
ApartmentCell.area_tolerance_exceeded=True zamiast cichego zaakceptowania
dowolnego odchylenia."""


def fit_program_to_rectangles(
    rectangles: list[Polygon], specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Zachłanne dopasowanie: dla każdego prostokąta wybiera specyfikację
    programu dającą najmniejsze odchylenie procentowe od min_area_m2 —
    próbuje WSZYSTKIE pozostałe specyfikacje, nie tylko czoło kolejki FIFO
    jak dawne _slice_apartments (audyt 2026-07-02, znalezisko #6)."""
    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)

    if not queue or not rectangles:
        leftover_geoms = [r for r in rectangles if r.area > 1e-6]
        leftover = unary_union(leftover_geoms) if leftover_geoms else None
        return [], (
            leftover if leftover is not None and not leftover.is_empty and leftover.area > 1e-6 else None
        )

    cells: list[ApartmentCell] = []
    remaining_rects: list[Polygon] = list(rectangles)
    unused_specs: list[ApartmentSpec] = list(queue)
    leftover_parts: list[Polygon] = []
    idx = 0

    while remaining_rects:
        idx %= len(remaining_rects)
        rect = remaining_rects[idx]
        bounds = rect.bounds
        if len(bounds) != 4:
            leftover_parts.append(remaining_rects.pop(idx))
            continue
        minx, miny, maxx, maxy = bounds
        w, h = maxx - minx, maxy - miny
        horizontal = w >= h
        available_depth = h if horizontal else w

        if available_depth < 1e-6 or not unused_specs:
            leftover_parts.append(remaining_rects.pop(idx))
            continue

        best_i: int | None = None
        best_deviation = float("inf")
        for i, spec in enumerate(unused_specs):
            fitted = spec.min_area_m2 / available_depth
            cut_size = max(fitted, MIN_CELL_DIMENSION_M)
            projected_area = cut_size * available_depth
            deviation = abs(projected_area - spec.min_area_m2) / spec.min_area_m2
            if deviation < best_deviation:
                best_deviation = deviation
                best_i = i

        assert best_i is not None
        spec = unused_specs[best_i]
        fitted = spec.min_area_m2 / available_depth
        cut_size = max(fitted, MIN_CELL_DIMENSION_M)

        cell_poly, rest = _cut_cell(rect, cut_size, horizontal)
        if cell_poly is None or cell_poly.area < 1e-6:
            leftover_parts.append(remaining_rects.pop(idx))
            continue

        cells.append(
            ApartmentCell(
                id=str(uuid.uuid4())[:8],
                type=spec.type,
                polygon=cell_poly,
                area_tolerance_exceeded=best_deviation > AREA_TOLERANCE,
            )
        )
        unused_specs.pop(best_i)

        rest_parts = _polygon_parts(rest)
        if rest_parts:
            remaining_rects[idx] = rest_parts[0]
            remaining_rects.extend(rest_parts[1:])
            idx += 1
        else:
            remaining_rects.pop(idx)

    leftover_geoms = leftover_parts + [p for p in remaining_rects if p.area > 1e-6]
    leftover = unary_union(leftover_geoms) if leftover_geoms else None
    return cells, (
        leftover if leftover is not None and not leftover.is_empty and leftover.area > 1e-6 else None
    )


def subdivide_units(
    remainder: Polygon | MultiPolygon, specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Etap 2 pełny: dekompozycja `remainder` (może być wklęsła/wieloczęściowa)
    na prostokąty, potem dopasowanie programu."""
    rectangles = rectangle_decompose(remainder)
    return fit_program_to_rectangles(rectangles, specs)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_unit_mix.py -v`
Expected: all 5 pass. If `test_subdivide_units_flags_tolerance_exceeded` fails because the deviation happens to land under 3%, adjust the spec's `min_area_m2` down (e.g. to `1.0`) until `best_deviation > AREA_TOLERANCE` is true for that geometry — verify by adding a `print(best_deviation)` temporarily if needed, then remove it.

- [ ] **Step 5: Commit**

```bash
git add backend/services/unit_mix.py backend/services/layout.py backend/tests/test_unit_mix.py
git commit -m "feat: add unit_mix.py — knapsack-style program fitting, replaces FIFO

fit_program_to_rectangles tries every remaining spec against every
rectangle and picks the smallest-deviation match, instead of only ever
checking the FIFO queue head (which permanently retired parts that didn't
fit the CURRENT head even if a later, smaller spec would fit — audit
finding #6). Flags cells exceeding +/-3% tolerance instead of silently
accepting any deviation. Reuses the already-fixed _cut_cell for the actual
cut. subdivide_units() composes this with rectangle_decompose for the full
Etap 2."
```

---

## Phase 5 — `layout.py`: rewire `generate_layout()` as a thin wrapper

### Task 7: Rewrite `generate_layout()`, remove `bsp_zones` call, fix test imports

**Files:**
- Modify: `backend/services/layout.py`
- Modify: `backend/services/bsp.py` (remove `bsp_zones`)
- Modify: `backend/tests/test_layout.py`, `backend/tests/test_cage_modes_and_fitting.py`, `backend/tests/test_layout_corridor.py` (fix imports broken by Tasks 4/6)

**Interfaces:**
- Consumes: `place_circulation` (circulation.py, Task 5), `subdivide_units` (unit_mix.py, Task 6).
- Produces: `generate_layout(input: LayoutInput) -> LayoutResult` — same signature and return shape as today (verified by full regression suite).

- [ ] **Step 1: Find and update broken test imports**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | grep -E "ERROR|ImportError|ModuleNotFoundError"`

For every test file reporting `ImportError`/`ModuleNotFoundError` referencing `_place_cage_by_mode`, `_edge_cage`, `_centered_cage`, `_corner_cage_convex`, `CAGE_POSITION_MODES`, or `_build_corridor` from `services.layout` — change the import to `from services.circulation import ...` (same names, new module). For imports of `_slice_apartments` — change call sites to use `from services.unit_mix import subdivide_units` and adapt the call (`subdivide_units(polygon, specs)` returns the same `(cells, leftover)` tuple shape `_slice_apartments` did).

- [ ] **Step 2: Rewrite `generate_layout()`**

In `backend/services/layout.py`, replace the entire body of `generate_layout()`:

```python
def generate_layout(input: LayoutInput) -> LayoutResult:
    """Generuje układ kondygnacji na podstawie obrysu.

    Wrapper nad dwoma jawnymi etapami (docs/superpowers/specs/2026-07-02-
    layout-engine-redesign-design.md): place_circulation (klatka+korytarz
    per prawie-prostokątna strefa) potem subdivide_units (dopasowanie
    programu do pozostałości). Zachowany dla optimizer.py i /layout/generate
    — oba etapy są też dostępne osobno (services.circulation.place_circulation,
    services.unit_mix.subdivide_units) dla nowych endpointów /layout/circulation
    i /layout/units."""
    from services.circulation import place_circulation
    from services.unit_mix import subdivide_units

    footprint = input.footprint
    footprint_area = footprint.area

    circulation = place_circulation(
        footprint,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
        place_cage=input.place_cage,
        cage_size_m=input.cage_size_m,
        cage_position=input.cage_position,
    )

    apartments, leftover = subdivide_units(circulation.remainder, input.apartments)

    usable_area = sum(a.polygon.area for a in apartments)
    circulation_area = (
        circulation.circulation_geometry.area if circulation.circulation_geometry is not None else 0.0
    )

    return LayoutResult(
        footprint=footprint,
        footprint_area_m2=footprint_area,
        circulation_area_m2=circulation_area,
        usable_area_m2=usable_area,
        apartments=apartments,
        leftover=leftover,
        zones=circulation.zones,
        building_azimuth_deg=_estimate_building_azimuth(footprint),
        circulation_geometry=circulation.circulation_geometry,
        cage_polygons=circulation.cage_polygons,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
    )
```

Remove the now-unused `from services.bsp import Zone, bsp_zones` import at the top of `layout.py` (replace with `from services.bsp import Zone` — `Zone` is still needed for the `LayoutResult.zones` type).

- [ ] **Step 3: Remove `bsp_zones()` from `bsp.py`**

In `backend/services/bsp.py`, delete the entire `bsp_zones()` function (now superseded by `rectangle_decompose()` + `circulation.py`'s per-zone loop). Keep `is_concave`, `concave_vertices`, `split_polygon_by_edge`, `corner_cage`, `rectangle_decompose`, and the `Zone` dataclass.

- [ ] **Step 4: Run full regression suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q -v 2>&1 | tail -60`

Expected: every test passes. Read the full output, not just the summary line — this is the highest-risk step in the whole plan (it's the point where the old and new engines must agree on behavior for every existing fixture). If any test fails:
- If it's a fixture that happened to depend on `bsp_zones()`'s specific (buggy) zone-numbering or the old `_slice_apartments` FIFO order, update the assertion to match the new (correct) behavior, and add a one-line comment explaining why the expected value changed.
- If it's a genuine regression (area mismatch, crash), STOP and re-examine — do not paper over it, this is exactly the class of bug the whole redesign exists to eliminate.

Run: `cd backend && ./.venv/Scripts/python.exe -m ruff check .`
Expected: clean (check for now-unused imports in `layout.py`/`bsp.py` after the moves — `ruff` will flag them).

- [ ] **Step 5: Commit**

```bash
git add backend/services/layout.py backend/services/bsp.py backend/tests/
git commit -m "refactor: generate_layout() becomes a thin wrapper over the two new stages

Replaces the bsp_zones()-based single-pass algorithm with
place_circulation() + subdivide_units(). LayoutResult's shape is
unchanged — optimizer.py, solar_analysis.py, wt_validation.py, exports,
and the frontend all keep working against the same contract. bsp_zones()
removed (superseded by rectangle_decompose()). Full test suite passing
confirms behavioral parity (or documents where behavior intentionally
improved, e.g. concave footprints that previously silently produced wrong
geometry now produce correct geometry)."
```

---

## Phase 6 — New validation rules (Finch-inspired, adopted per user decision)

### Task 8: Facade frontage + aspect ratio warnings

**Files:**
- Modify: `backend/services/apartment_validation.py`
- Test: `backend/tests/test_validate.py`

**Interfaces:**
- Produces: `MIN_FACADE_FRONTAGE_M = 3.6`, `MAX_APARTMENT_ASPECT_RATIO = 2.5` constants; `ApartmentValidationResult` gains `warnings` entries (existing field, no new field needed — these are additional warning strings, same pattern as the existing "blisko minimum" warning).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_validate.py` (check the existing import block at the top of that file for `validate_apartment`/`ApartmentCell` and match it):

```python
def test_validate_apartment_warns_on_narrow_facade_frontage():
    from services.layout import ApartmentCell
    from services.apartment_validation import validate_apartment
    from shapely.geometry import Polygon

    # 3m wide x 20m deep — facade frontage well under 3.6m
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (3, 0), (3, 20), (0, 20)]))
    result = validate_apartment(apt, min_area_m2=None)
    assert any("front" in w.lower() or "elewacj" in w.lower() for w in result.warnings)


def test_validate_apartment_warns_on_excessive_aspect_ratio():
    from services.layout import ApartmentCell
    from services.apartment_validation import validate_apartment
    from shapely.geometry import Polygon

    # 4m wide x 15m deep -> ratio 3.75:1, over the 2.5:1 threshold
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (4, 0), (4, 15), (0, 15)]))
    result = validate_apartment(apt, min_area_m2=None)
    assert any("stosun" in w.lower() or "aspect" in w.lower() for w in result.warnings)


def test_validate_apartment_no_warning_for_well_proportioned_unit():
    from services.layout import ApartmentCell
    from services.apartment_validation import validate_apartment
    from shapely.geometry import Polygon

    # 5m x 9m, area 45, aspect ratio 1.8:1, frontage 5m — all within bounds
    apt = ApartmentCell(id="a1", type="M2", polygon=Polygon([(0, 0), (5, 0), (5, 9), (0, 9)]))
    result = validate_apartment(apt, min_area_m2=45)
    assert result.warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_validate.py -k "frontage or aspect_ratio or well_proportioned" -v`
Expected: FAIL (no such warnings emitted yet).

- [ ] **Step 3: Implement the two new rules**

In `backend/services/apartment_validation.py`, add constants near `MIN_ROOM_WIDTH_M`:

```python
MIN_FACADE_FRONTAGE_M = 3.6
"""Finch §B.2 (adaptowane, nie polskie WT) — min. długość elewacji frontowej
apartamentu, zapobiega bardzo wąskim mieszkaniom. Ostrzeżenie, nie błąd
twardy — to heurystyka jakościowa, nie przepis prawa budowlanego."""

MAX_APARTMENT_ASPECT_RATIO = 2.5
"""Finch §B.2 — max. stosunek głębokości do szerokości mieszkania.
Ostrzeżenie, ta sama logika co wyżej."""
```

Add a helper next to `_apartment_min_width`:

```python
def _apartment_aspect_ratio(apt: ApartmentCell) -> float:
    minx, miny, maxx, maxy = apt.polygon.bounds
    w, h = maxx - minx, maxy - miny
    short, long_ = min(w, h), max(w, h)
    return long_ / short if short > 1e-9 else float("inf")
```

`_apartment_min_width` already gives the "frontage" proxy (shorter bbox dimension) — for now (this module operates on bbox, not on which edge is actually the facade; a precise "facade frontage" would need the footprint boundary, out of scope for this task per YAGNI) use the SAME bbox-based approximation consistently: treat `_apartment_min_width(apt)` as the frontage proxy too (this mirrors how `_apartment_min_width` is already documented as an approximation of "the narrower in-plan dimension", used for both §94 ust.2 and now this Finch-inspired check).

In `validate_apartment()`, after the existing width check (`if width < MIN_ROOM_WIDTH_M: ...`), add:

```python
    if width < MIN_FACADE_FRONTAGE_M:
        warnings.append(
            f"{apt.id}: szerokość frontu {width:.2f} m < zalecane {MIN_FACADE_FRONTAGE_M} m "
            f"(ryzyko zbyt wąskiego mieszkania, heurystyka nie-WT)."
        )

    ratio = _apartment_aspect_ratio(apt)
    if ratio > MAX_APARTMENT_ASPECT_RATIO:
        warnings.append(
            f"{apt.id}: stosunek głębokość:szerokość {ratio:.2f}:1 > zalecane "
            f"{MAX_APARTMENT_ASPECT_RATIO}:1 (heurystyka nie-WT)."
        )
```

Note: `MIN_FACADE_FRONTAGE_M` (3.6) is above `MIN_ROOM_WIDTH_M` (2.4), so this warning will fire for any apartment already failing the §94 ust.2 hard error — that's fine, both fire (an apartment can have multiple issues).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_validate.py -v`
Expected: all pass, including pre-existing tests in this file (check none now unexpectedly gain warnings — if an existing fixture is narrower than 3.6m or has ratio > 2.5, its test may need its assertion updated to expect the new warning; read the failures if any).

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: full suite passes.

- [ ] **Step 5: Commit**

```bash
git add backend/services/apartment_validation.py backend/tests/test_validate.py
git commit -m "feat: add facade-frontage and aspect-ratio warnings (Finch-inspired)

MIN_FACADE_FRONTAGE_M (3.6m) and MAX_APARTMENT_ASPECT_RATIO (2.5:1),
adapted from ANALIZA_FINCH3D/specyfikacja_systemowa_finch3d.md §B.2. Both
are warnings, not hard errors -- same two-tier pattern as the existing
MIN_CONTACT_LENGTH_M (warning) vs MIN_DOOR_CONTACT_LENGTH_M (hard error) in
wt_validation.py, since these are quality heuristics, not Polish WT law."
```

### Task 9: Cage-to-facade contact hard rule

**Files:**
- Modify: `backend/services/wt_validation.py`
- Test: `backend/tests/test_wt_validation.py`

**Interfaces:**
- Produces: new `WTRule` with `code="§68 ust.1-doswietlenie"`, added to `validate_layout_wt()`'s rule list.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_wt_validation.py` (match the existing import/fixture style in that file):

```python
def test_cage_facade_contact_rule_passes_when_cage_touches_facade():
    from shapely.geometry import Polygon
    from services.layout import LayoutResult

    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    # cage in the corner, touching two facade edges for 2.5m each — well over 2.4m
    cage = Polygon([(0, 0), (2.5, 0), (2.5, 2.5), (0, 2.5)])
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[cage],
    )
    result = validate_layout_wt(layout)
    rule = next(r for r in result.rules if r.code == "§68 ust.1-doswietlenie")
    assert rule.passed is True


def test_cage_facade_contact_rule_fails_when_cage_is_interior():
    from shapely.geometry import Polygon
    from services.layout import LayoutResult

    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    # cage fully interior, no contact with the footprint boundary at all
    cage = Polygon([(4, 2), (6, 2), (6, 4), (4, 4)])
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[cage],
    )
    result = validate_layout_wt(layout)
    rule = next(r for r in result.rules if r.code == "§68 ust.1-doswietlenie")
    assert rule.passed is False


def test_cage_facade_contact_rule_not_applicable_without_cage():
    from shapely.geometry import Polygon
    from services.layout import LayoutResult

    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    layout = LayoutResult(
        footprint=footprint, footprint_area_m2=60, circulation_area_m2=0,
        usable_area_m2=0, apartments=[], leftover=None, zones=[],
        cage_polygons=[],
    )
    result = validate_layout_wt(layout)
    rule = next(r for r in result.rules if r.code == "§68 ust.1-doswietlenie")
    assert rule.passed is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_wt_validation.py -k cage_facade -v`
Expected: FAIL with `StopIteration` (no rule with that code exists yet).

- [ ] **Step 3: Implement the rule**

In `backend/services/wt_validation.py`, add a constant near `MIN_STAIR_WIDTH_M`:

```python
MIN_CAGE_FACADE_CONTACT_M = 2.4
"""Finch §A.2 (240cm) — min. styk klatki schodowej z elewacją zewnętrzną,
dla naturalnego doświetlenia i strefy oddymiania. Adaptowane jako realny
polski wymóg pokrewny WT §68 (nie tylko heurystyka Finch) — stąd twardy
błąd, nie ostrzeżenie."""
```

Add a new rule function next to `_rule_stair_width`:

```python
def _rule_cage_facade_contact(layout: LayoutResult) -> WTRule:
    """§68 ust.1 (doświetlenie/oddymianie) — klatka schodowa musi stykać się
    z elewacją zewnętrzną na min. MIN_CAGE_FACADE_CONTACT_M."""
    if not layout.cage_polygons:
        return WTRule(
            code="§68 ust.1-doswietlenie",
            description="Min. styk klatki z elewacją (doświetlenie/oddymianie)",
            passed=True,
            detail="Brak klatki schodowej w układzie — reguła nie dotyczy.",
        )
    failing: list[str] = []
    for i, cage in enumerate(layout.cage_polygons):
        contact = cage.boundary.intersection(layout.footprint.boundary)
        length = 0.0 if contact.is_empty else contact.length
        if length < MIN_CAGE_FACADE_CONTACT_M:
            failing.append(f"klatka #{i + 1}: styk {length:.2f} m < {MIN_CAGE_FACADE_CONTACT_M} m")
    passed = not failing
    detail = (
        f"Wszystkie klatki stykają się z elewacją na min. {MIN_CAGE_FACADE_CONTACT_M} m."
        if passed
        else "Niewystarczający styk z elewacją: " + "; ".join(failing)
    )
    return WTRule(
        code="§68 ust.1-doswietlenie",
        description="Min. styk klatki z elewacją (doświetlenie/oddymianie)",
        passed=passed,
        detail=detail,
    )
```

In `validate_layout_wt()`, add the new rule to the `rules` list (after `rules.append(_rule_stair_width(layout))`):

```python
    rules.append(_rule_cage_facade_contact(layout))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_wt_validation.py -v`
Expected: all pass, including pre-existing tests (check whether any existing fixture has a cage with <2.4m facade contact — if so its `score`/`passed` assertions may need updating to account for the new rule; the score is `passed_count/len(rules)*100` so adding a rule shifts every score fixture by `1/N`).

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: full suite passes — **pay special attention** to any test asserting an exact `score` value anywhere in the suite (`test_validate.py`, `test_optimizer_constraints.py`), since adding a rule changes the denominator. Update expected scores as needed.

- [ ] **Step 5: Commit**

```bash
git add backend/services/wt_validation.py backend/tests/test_wt_validation.py
git commit -m "feat: add cage-to-facade contact hard rule (WT §68 lighting/smoke extraction)

MIN_CAGE_FACADE_CONTACT_M = 2.4m, adapted from ANALIZA_FINCH3D's Finch
analysis §A.2 but treated as a hard error (not a Finch-only heuristic) —
it maps to a real Polish WT requirement for stair-shaft natural lighting
and smoke extraction. Adding a rule shifts every existing score
denominator by 1/N; fixture assertions updated accordingly."
```

---

## Phase 7 — New API endpoints

### Task 10: `POST /layout/circulation`

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Test: `backend/tests/test_layout_circulation_endpoint.py` (new file)

**Interfaces:**
- Produces: `POST /api/v1/layout/circulation` — request: `{footprint, circulation}` (same `CirculationSpec` shape as today's `LayoutGenerateRequest.circulation`), response: `{circulation_geometry, cage_geometries, remainder}` (GeoJSON, `remainder` may be a `MultiPolygon` GeoJSON).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_layout_circulation_endpoint.py`:

```python
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_circulation_endpoint_returns_geometry_and_remainder():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["circulation_geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert len(body["cage_geometries"]) == 1
    assert body["remainder"]["type"] in ("Polygon", "MultiPolygon")


def test_circulation_endpoint_rejects_short_footprint():
    response = client.post(
        "/api/v1/layout/circulation",
        json={"footprint": [[0, 0], [1, 1]], "circulation": {}},
    )
    assert response.status_code == 422  # pydantic min_length validation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist).

- [ ] **Step 3: Add the endpoint**

In `backend/api/v1/endpoints/layout.py`, add near the top (after existing imports):

```python
import json as _json

from services.circulation import place_circulation
```

Add a new response model near `SplitResponse`:

```python
class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
```

Add the endpoint (place it before `/split`, after `/generate`):

```python
@router.post("/circulation", response_model=CirculationResponse)
def place_circulation_endpoint(request: LayoutGenerateRequest):
    """Etap 1 osobno (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md)."""
    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    circulation = request.circulation
    if circulation.cage_position not in CAGE_POSITION_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid cage_position '{circulation.cage_position}'. Valid: {CAGE_POSITION_MODES}",
        )

    result = place_circulation(
        footprint,
        corridor_width_m=circulation.corridor_width_m,
        stair_width_m=circulation.stair_width_m,
        place_cage=circulation.place_cage,
        cage_size_m=circulation.cage_size_m,
        cage_position=circulation.cage_position,
    )

    return CirculationResponse(
        circulation_geometry=(
            _json.loads(_json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[_json.loads(_json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=_json.loads(_json.dumps(result.remainder.__geo_interface__)),
    )
```

Add `CAGE_POSITION_MODES` to the import from `services.circulation` (change the earlier import line to `from services.circulation import CAGE_POSITION_MODES, place_circulation`), and remove it from wherever `layout.py` currently imports it from `services.layout` if still present (check — `CAGE_POSITION_MODES` moved to `circulation.py` in Task 4).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py -v`
Expected: both pass.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: full suite passes, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_layout_circulation_endpoint.py
git commit -m "feat: add POST /api/v1/layout/circulation endpoint (Etap 1 standalone)

Returns circulation_geometry, cage_geometries, and remainder as GeoJSON —
remainder may be a MultiPolygon. Frontend uses this for the new two-step
UX (Phase 9)."
```

### Task 11: `POST /layout/units`

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Test: `backend/tests/test_layout_units_endpoint.py` (new file)

**Interfaces:**
- Produces: `POST /api/v1/layout/units` — request: `{remainder: GeoJSON, apartments: [ApartmentProgram, ...]}`, response: `{apartments: [ApartmentResult, ...], leftover: GeoJSON | null}` (reuses the existing `ApartmentResult` model from `/layout/generate`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_layout_units_endpoint.py`:

```python
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_units_endpoint_fits_program_to_remainder():
    response = client.post(
        "/api/v1/layout/units",
        json={
            "remainder": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [30, 0], [30, 4], [0, 4], [0, 0]]],
            },
            "apartments": [{"type": "M2", "min_area_m2": 40, "target_count": 3}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["apartments"]) == 3
    for apt in body["apartments"]:
        assert abs(apt["area_m2"] - 40.0) < 1.0


def test_units_endpoint_rejects_invalid_geometry():
    response = client.post(
        "/api/v1/layout/units",
        json={"remainder": {"type": "Polygon", "coordinates": []}, "apartments": []},
    )
    assert response.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout_units_endpoint.py -v`
Expected: FAIL with 404.

- [ ] **Step 3: Add the endpoint**

In `backend/api/v1/endpoints/layout.py`, add:

```python
from shapely.geometry import shape as _shape

from services.unit_mix import subdivide_units


class UnitsRequest(BaseModel):
    remainder: dict
    apartments: list[ApartmentProgram] = Field(default_factory=list)


class UnitsResponse(BaseModel):
    apartments: list[ApartmentResult]
    leftover: dict | None = None


@router.post("/units", response_model=UnitsResponse)
def subdivide_units_endpoint(request: UnitsRequest):
    """Etap 2 osobno (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md)."""
    try:
        remainder = _shape(request.remainder)
        if remainder.is_empty or not remainder.is_valid:
            raise ValueError("remainder geometry is empty or invalid")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid remainder geometry: {exc}")

    specs = [
        ApartmentSpec(
            type=a.type, min_area_m2=a.min_area_m2, target_count=a.target_count,
            width_m=a.width_m, depth_m=a.depth_m,
        )
        for a in request.apartments
    ]

    cells, leftover = subdivide_units(remainder, specs)

    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area,
            geometry=_json.loads(_json.dumps(c.polygon.__geo_interface__)),
        )
        for c in cells
    ]

    return UnitsResponse(
        apartments=apartments_out,
        leftover=_json.loads(_json.dumps(leftover.__geo_interface__)) if leftover else None,
    )
```

`ApartmentSpec` needs importing: add `ApartmentSpec` to the existing `from services.layout import ...` line in this file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout_units_endpoint.py -v`
Expected: both pass.

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: full suite passes, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_layout_units_endpoint.py
git commit -m "feat: add POST /api/v1/layout/units endpoint (Etap 2 standalone)

Takes a remainder (GeoJSON, possibly MultiPolygon) + apartment program,
returns fitted ApartmentCells + leftover. Completes the two-endpoint split
of generate_layout() for the frontend's staged UX (Phase 9)."
```

---

## Phase 8 — Property-based regression tests (hypothesis)

### Task 12: Add `hypothesis` dependency + property tests for `rectangle_decompose`

**Files:**
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_rectangle_decompose_properties.py` (new file)

**Interfaces:**
- Consumes: `rectangle_decompose` (bsp.py, Task 2).

- [ ] **Step 1: Add the dependency**

Add to `backend/requirements.txt`:

```
hypothesis==6.115.5
```

Run: `cd backend && ./.venv/Scripts/python.exe -m pip install hypothesis==6.115.5`
Expected: installs cleanly (pure-Python, no compiled deps to conflict).

- [ ] **Step 2: Write the property tests**

Create `backend/tests/test_rectangle_decompose_properties.py`:

```python
"""Property-based tests for rectangle_decompose — the exact class of bug
(cut_cell depth/width, bsp_zones leaving zones concave) that passed 96/96
example-based tests unnoticed in the 2026-07-02 audit needs property tests,
not more examples."""

from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Polygon

from services.bsp import concave_vertices, rectangle_decompose


def _l_shaped_polygon(cut_x: float, cut_y: float, width: float, height: float) -> Polygon:
    """Generates an L-shaped rectilinear polygon with a notch of size
    (cut_x, cut_y) removed from the top-right corner of a (width, height) box."""
    return Polygon([
        (0, 0), (width, 0), (width, height - cut_y),
        (width - cut_x, height - cut_y), (width - cut_x, height), (0, height),
    ])


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_preserves_area_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return  # degenerate case, not what this test targets
    parts = rectangle_decompose(poly)
    total = sum(p.area for p in parts)
    assert abs(total - poly.area) < max(1e-3, poly.area * 1e-6)


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_no_overlap_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return
    parts = rectangle_decompose(poly)
    for i in range(len(parts)):
        for j in range(i + 1, len(parts)):
            overlap = parts[i].intersection(parts[j]).area
            assert overlap < max(1e-3, poly.area * 1e-6)


@given(
    width=st.floats(min_value=5.0, max_value=50.0),
    height=st.floats(min_value=5.0, max_value=50.0),
    cut_frac_x=st.floats(min_value=0.1, max_value=0.7),
    cut_frac_y=st.floats(min_value=0.1, max_value=0.7),
)
@settings(max_examples=100, deadline=None)
def test_rectangle_decompose_eliminates_concavity_for_l_shapes(width, height, cut_frac_x, cut_frac_y):
    cut_x = width * cut_frac_x
    cut_y = height * cut_frac_y
    poly = _l_shaped_polygon(cut_x, cut_y, width, height)
    if poly.area < 1.0 or not poly.is_valid:
        return
    for part in rectangle_decompose(poly):
        assert not concave_vertices(part), (
            f"part still concave for width={width} height={height} "
            f"cut_x={cut_x} cut_y={cut_y}: {list(part.exterior.coords)}"
        )
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_rectangle_decompose_properties.py -v`
Expected: all 3 pass (hypothesis will print the number of examples run; if any fails, hypothesis reports the exact minimal failing `width`/`height`/`cut_frac_x`/`cut_frac_y` — use those values to add a regular example-based regression test in `test_bsp.py` once fixed, don't just adjust the property test to dodge it).

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: full suite passes (99+ tests now).

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/tests/test_rectangle_decompose_properties.py
git commit -m "test: add hypothesis property tests for rectangle_decompose

Generates randomized L-shaped rectilinear polygons and asserts: total area
preserved, no overlap between parts, no concave vertices remain in any
part. This is the test category that would have caught the cut_cell
depth/width bug and the bsp_zones concave-leftover bug before they shipped
-- both passed 96/96 example-based tests. hypothesis==6.115.5 added as a
backend dependency."
```

### Task 13: Property tests for `fit_program_to_rectangles`

**Files:**
- Test: `backend/tests/test_unit_mix.py` (append to existing file from Task 6)

**Interfaces:**
- Consumes: `fit_program_to_rectangles` (unit_mix.py, Task 6).

- [ ] **Step 1: Write the property tests**

Append to `backend/tests/test_unit_mix.py`:

```python
from hypothesis import given, settings
from hypothesis import strategies as st

from services.unit_mix import fit_program_to_rectangles


@given(
    rect_w=st.floats(min_value=4.0, max_value=40.0),
    rect_h=st.floats(min_value=4.0, max_value=40.0),
    target_area=st.floats(min_value=20.0, max_value=100.0),
    target_count=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100, deadline=None)
def test_fit_program_never_exceeds_source_area(rect_w, rect_h, target_area, target_count):
    rect = Polygon([(0, 0), (rect_w, 0), (rect_w, rect_h), (0, rect_h)])
    specs = [ApartmentSpec(type="M2", min_area_m2=target_area, target_count=target_count)]
    cells, leftover = fit_program_to_rectangles([rect], specs)
    total_cells_area = sum(c.polygon.area for c in cells)
    leftover_area = leftover.area if leftover is not None else 0.0
    assert total_cells_area + leftover_area <= rect.area + 1e-3


@given(
    rect_w=st.floats(min_value=4.0, max_value=40.0),
    rect_h=st.floats(min_value=4.0, max_value=40.0),
    target_area=st.floats(min_value=20.0, max_value=100.0),
    target_count=st.integers(min_value=1, max_value=5),
)
@settings(max_examples=100, deadline=None)
def test_fit_program_area_conserved(rect_w, rect_h, target_area, target_count):
    rect = Polygon([(0, 0), (rect_w, 0), (rect_w, rect_h), (0, rect_h)])
    specs = [ApartmentSpec(type="M2", min_area_m2=target_area, target_count=target_count)]
    cells, leftover = fit_program_to_rectangles([rect], specs)
    total_cells_area = sum(c.polygon.area for c in cells)
    leftover_area = leftover.area if leftover is not None else 0.0
    assert abs((total_cells_area + leftover_area) - rect.area) < 1e-3
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_unit_mix.py -v`
Expected: all pass (7 example-based from Task 6 + 2 property-based).

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -m ruff check .`
Expected: full suite passes, ruff clean.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_unit_mix.py
git commit -m "test: add hypothesis property tests for fit_program_to_rectangles

Asserts area conservation (cells + leftover == source area, never more)
across randomized rectangle sizes and program specs."
```

---

## Phase 9 — Frontend: staged UX

### Task 14: `api.ts` — circulation/units client functions

**Files:**
- Modify: `frontend/app/lib/api.ts`

**Interfaces:**
- Produces: `CirculationResponse`, `placeCirculation(footprint, circulation) -> Promise<CirculationResponse>`, `UnitsResponse`, `subdivideUnits(remainder, apartments) -> Promise<UnitsResponse>` — consumed by `SessionContext.tsx` (Task 15).

- [ ] **Step 1: Add types and functions**

In `frontend/app/lib/api.ts`, add after the existing `generateLayout` function:

```typescript
// ── Circulation / Units (Etap 1 / Etap 2 osobno, redesign 2026-07-02) ──

export interface CirculationResponse {
  circulation_geometry: GeoJsonPolygon | null;
  cage_geometries: GeoJsonPolygon[];
  remainder: GeoJsonPolygon; // może być Polygon lub MultiPolygon
}

export function placeCirculation(
  footprint: Point[],
  circulation: CirculationSpecInput
): Promise<CirculationResponse> {
  return postJson("/layout/circulation", { footprint, circulation });
}

export interface UnitsResponse {
  apartments: ApartmentResult[];
  leftover: GeoJsonPolygon | null;
}

export function subdivideUnits(
  remainder: GeoJsonPolygon,
  apartments: ApartmentProgramInput[]
): Promise<UnitsResponse> {
  return postJson("/layout/units", { remainder, apartments });
}
```

- [ ] **Step 2: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean (all referenced types — `GeoJsonPolygon`, `Point`, `CirculationSpecInput`, `ApartmentResult`, `ApartmentProgramInput` — already exist in this file from the current codebase).

- [ ] **Step 3: Commit**

```bash
git add frontend/app/lib/api.ts
git commit -m "feat: add placeCirculation/subdivideUnits API client functions

Thin wrappers over the new /layout/circulation and /layout/units
endpoints, matching the existing postJson pattern in this file."
```

### Task 15: `SessionContext.tsx` — staged state + actions

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx`

**Interfaces:**
- Consumes: `placeCirculation`, `subdivideUnits` (Task 14).
- Produces: `state.circulationResult: api.CirculationResponse | null`, `runPlaceCirculation(): Promise<void>`, `runSubdivideUnits(): Promise<void>` — consumed by `CirculationSection.tsx` (Task 17) and `CanvasEditor.tsx` (Task 16).

- [ ] **Step 1: Add state field and reducer case**

In `frontend/app/state/SessionContext.tsx`, add to the `SessionState` interface (near `layoutResult`):

```typescript
circulationResult: api.CirculationResponse | null;
```

Add to `initialState`:

```typescript
circulationResult: null,
```

Add a new action type to the `Action` union:

```typescript
| { type: "SET_CIRCULATION_RESULT"; result: api.CirculationResponse | null }
```

Add a reducer case (near `SET_LAYOUT_RESULT`):

```typescript
case "SET_CIRCULATION_RESULT":
  return { ...state, circulationResult: action.result };
```

Update the `UPDATE_VERTEX` case (from the earlier staleness fix) to also clear `circulationResult` — a footprint edit invalidates it the same way it invalidates `layoutResult`:

```typescript
case "UPDATE_VERTEX": {
  if (!state.footprint) return state;
  const next = [...state.footprint];
  next[action.index] = action.point;
  return {
    ...state,
    footprint: next,
    layoutResult: null,
    validation: null,
    circulationResult: null,
  };
}
```

- [ ] **Step 2: Add `runPlaceCirculation` and `runSubdivideUnits` actions**

Add near `regenerate`:

```typescript
const runPlaceCirculation = useCallback(async () => {
  if (!state.footprint || state.footprint.length < 3) return;
  dispatch({ type: "SET_LOADING", loading: true });
  try {
    const result = await api.placeCirculation(footprintToPoints(state.footprint), state.circulation);
    dispatch({ type: "SET_CIRCULATION_RESULT", result });
    dispatch({ type: "SET_LAYOUT_RESULT", result: null });
    dispatch({ type: "SET_VALIDATION", validation: null });
    dispatch({ type: "SET_ERROR", error: null });
  } catch (err) {
    dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
  } finally {
    dispatch({ type: "SET_LOADING", loading: false });
  }
}, [state.footprint, state.circulation]);

const runSubdivideUnits = useCallback(async () => {
  if (!state.circulationResult) return;
  dispatch({ type: "SET_LOADING", loading: true });
  try {
    const unitsReq = state.program.map((row) => ({
      type: row.type,
      min_area_m2: row.min_area_m2,
      target_count: row.target_count,
    }));
    const unitsRes = await api.subdivideUnits(state.circulationResult.remainder, unitsReq);
    const layoutResult: api.LayoutGenerateResponse = {
      footprint_area_m2: state.footprint ? polygonAreaFromPoints(state.footprint) : 0,
      circulation_area_m2: 0,
      usable_area_m2: unitsRes.apartments.reduce((sum, a) => sum + a.area_m2, 0),
      apartments: unitsRes.apartments,
      leftover: unitsRes.leftover,
      wt_validation: { passed: true, score: 0, rules: [], issues: [] },
      zones: [],
      circulation_parts: state.circulationResult.circulation_geometry
        ? [state.circulationResult.circulation_geometry]
        : [],
      cage_geometries: state.circulationResult.cage_geometries,
    };
    dispatch({ type: "SET_LAYOUT_RESULT", result: layoutResult });
    dispatch({ type: "SET_ERROR", error: null });
    // Fetch real WT validation for the combined result (score/rules were
    // left as placeholders above since /layout/units doesn't compute WT).
    if (state.footprint) {
      const req = {
        footprint: footprintToPoints(state.footprint),
        circulation: state.circulation,
        apartments: unitsReq,
      };
      const validation = await api.validateFullLayout(req);
      dispatch({ type: "SET_VALIDATION", validation });
    }
  } catch (err) {
    dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
  } finally {
    dispatch({ type: "SET_LOADING", loading: false });
  }
}, [state.circulationResult, state.program, state.footprint, state.circulation]);
```

Add a small helper near `footprintToPoints` (same file):

```typescript
function polygonAreaFromPoints(points: Point2D[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}
```

Note: `runSubdivideUnits` re-derives the full-layout validation via the existing `/validate/full-layout` endpoint (unchanged) rather than trying to make `/layout/units` compute WT scoring too — keeps the new endpoint focused (single responsibility) and reuses working, tested validation code instead of duplicating it.

- [ ] **Step 3: Export the new functions from the context value**

Add `runPlaceCirculation` and `runSubdivideUnits` to both the `SessionContextValue` interface and the `useMemo` value object + its dependency array (same three places `runOptimizer`/`applyVariant` were added earlier this session — search for `runOptimizer,` in this file to find all three spots and add the two new names alongside it).

- [ ] **Step 4: Verify types compile**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/state/SessionContext.tsx
git commit -m "feat: add circulationResult state + runPlaceCirculation/runSubdivideUnits

Staged actions for the new two-step UX: place circulation first (result
stored separately from layoutResult), then subdivide units using the
circulation result's remainder. Editing a footprint vertex now also clears
circulationResult, matching the existing layoutResult/validation clearing
pattern (2026-07-02 staleness fix)."
```

### Task 16: `CanvasEditor.tsx` — render circulation result + `edit-circulation` mode

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx`

**Interfaces:**
- Consumes: `state.circulationResult` (Task 15).
- Produces: renders corridor/cage geometry from `circulationResult` when `layoutResult` is not yet set (i.e. after Etap 1 but before Etap 2); mode string `"edit-circulation"` added to `EditorMode` (in `SessionContext.tsx`).

- [ ] **Step 1: Add `"edit-circulation"` to `EditorMode`**

In `frontend/app/state/SessionContext.tsx`, change:

```typescript
export type EditorMode = "idle" | "draw" | "edit-vertices" | "edit-lines";
```

to:

```typescript
export type EditorMode = "idle" | "draw" | "edit-vertices" | "edit-lines" | "edit-circulation";
```

Update the `SET_MODE` reducer case's draw-points-clearing condition — it currently only special-cases `"draw"`, which is unaffected by this addition, so no change needed there. Update the cursor/label logic in `CanvasEditor.tsx` (see Step 3).

- [ ] **Step 2: Render `circulationResult` geometry when present and no full `layoutResult` yet**

In `frontend/app/CanvasEditor.tsx`, find the existing circulation rendering block (`{/* Korytarz (jasnoszary) */}` and `{/* Klatka (szary) */}`, which currently read from `circulationParts`/`cageGeometries` derived via `useMemo` from `state.layoutResult`). Update the `useMemo` definitions to fall back to `state.circulationResult` when `state.layoutResult` is null:

```typescript
const circulationParts = useMemo(() => {
  if (state.layoutResult) return state.layoutResult.circulation_parts ?? [];
  if (state.circulationResult?.circulation_geometry) return [state.circulationResult.circulation_geometry];
  return [];
}, [state.layoutResult, state.circulationResult]);
const cageGeometries = useMemo(() => {
  if (state.layoutResult) return state.layoutResult.cage_geometries ?? [];
  if (state.circulationResult) return state.circulationResult.cage_geometries;
  return [];
}, [state.layoutResult, state.circulationResult]);
```

- [ ] **Step 3: Add `edit-circulation` to cursor/label logic and Stage draggable check**

Find the `cursor` computation (`state.mode === "edit-vertices" ? "pointer" : ...`) and add a branch:

```typescript
const cursor =
  state.mode === "draw"
    ? "crosshair"
    : state.mode === "edit-vertices"
      ? "pointer"
      : state.mode === "edit-lines" || state.mode === "edit-circulation"
        ? "move"
        : isPanning
          ? "grabbing"
          : "grab";
```

Find the mode-label text block (`state.mode === "draw" ? "rysowanie..." : ...`) and add:

```typescript
: state.mode === "edit-circulation"
  ? "przeciąganie korytarza/klatki"
  :
```
(insert before the final `"przesuń: drag / zoom: kółko"` fallback, following the existing `state.mode === "edit-lines" ? "..." :` chain's structure exactly.)

`draggable={state.mode !== "draw"}` (set earlier this session) already covers `"edit-circulation"` — no change needed there.

- [ ] **Step 4: Add draggable corridor/cage edges in `edit-circulation` mode**

Add a new render block, near the existing `edit-lines` shared-line dragging block (`{state.mode === "edit-lines" && sharedLines.map(...)}`). This drags the WHOLE corridor/cage geometry as a rigid unit (simplest correct interaction — precise per-edge dragging of an offset-derived shape is out of scope, matches spec §7's "pełny drag" as rigid-body translate, not edge-by-edge reshaping):

```tsx
{state.mode === "edit-circulation" && state.circulationResult && (
  <Group
    draggable
    onDragEnd={(e) => {
      const node = e.target;
      const dxM = node.x() / METER_PX;
      const dyM = -node.y() / METER_PX;
      node.position({ x: 0, y: 0 });
      dispatch({ type: "TRANSLATE_CIRCULATION", dx: dxM, dy: dyM });
    }}
  >
    {circulationParts.map((geom, i) => (
      <Line
        key={`edit-corridor-${i}`}
        points={toCanvasPoints(ringToPoints(geom))}
        closed
        fill="rgba(211,211,211,0.5)"
        stroke="#60a5fa"
        strokeWidth={2 / scale}
      />
    ))}
    {cageGeometries.map((geom, i) => (
      <Line
        key={`edit-cage-${i}`}
        points={toCanvasPoints(ringToPoints(geom))}
        closed
        fill="rgba(128,128,128,0.7)"
        stroke="#60a5fa"
        strokeWidth={2 / scale}
      />
    ))}
  </Group>
)}
```

Add the corresponding action to `SessionContext.tsx` (Task 15's file) — add to the `Action` union:

```typescript
| { type: "TRANSLATE_CIRCULATION"; dx: number; dy: number }
```

Add a reducer case that snaps the translation to 0.5m and recomputes `remainder` client-side by re-differencing against the (unmoved) footprint — translating corridor/cage geometry and footprint difference is a pure client-side geometric operation, so this does **not** require a server round-trip (matches spec §7: "bez ponownego wołania całego /layout/circulation"). Implementing polygon translate/difference in TypeScript needs a small helper; add to `SessionContext.tsx`:

```typescript
function translateGeoJson(geom: GeoJsonPolygon, dx: number, dy: number): GeoJsonPolygon {
  return {
    type: geom.type,
    coordinates: geom.coordinates.map((ring) =>
      ring.map(([x, y]: [number, number]) => [snapToGrid(x + dx), snapToGrid(y + dy)])
    ),
  } as GeoJsonPolygon;
}

function snapToGrid(v: number): number {
  return Math.round(v / 0.5) * 0.5;
}
```

Reducer case:

```typescript
case "TRANSLATE_CIRCULATION": {
  if (!state.circulationResult) return state;
  const { dx, dy } = action;
  return {
    ...state,
    circulationResult: {
      ...state.circulationResult,
      circulation_geometry: state.circulationResult.circulation_geometry
        ? translateGeoJson(state.circulationResult.circulation_geometry, dx, dy)
        : null,
      cage_geometries: state.circulationResult.cage_geometries.map((g) => translateGeoJson(g, dx, dy)),
      // remainder is NOT recomputed client-side here (real polygon.difference
      // needs a real geometry library) — runSubdivideUnits always re-fetches
      // circulation from the server (Step 5) before subdividing, so a stale
      // client-side remainder is never actually consumed by Etap 2.
    },
  };
}
```

- [ ] **Step 5: Re-derive `remainder` server-side before Etap 2 consumes it**

In `SessionContext.tsx`'s `runSubdivideUnits` (Task 15), add a re-fetch guard at the top so a manually-dragged corridor/cage is respected: since real `remainder` recomputation needs server-side Shapely (not duplicated in TS per YAGNI), `runSubdivideUnits` must call `/layout/circulation` again with the CURRENT (possibly-translated) circulation as an override is out of scope for this task — instead, document the actual behavior precisely: dragging in `edit-circulation` mode visually repositions corridor/cage for user feedback, but **Etap 2 always uses the last server-computed `remainder`** (from the most recent `runPlaceCirculation` call), not a client-recomputed one. Add a code comment making this explicit at the top of the `TRANSLATE_CIRCULATION` case (already partially covered by the comment in Step 4) and skip implementing server-side remainder re-sync in this task — Step 6's manual browser verification confirms the drag is visual-only and does not silently corrupt Etap 2's input, and this limitation is called out in the commit message (Step 8) rather than left unexplained.

- [ ] **Step 6: Manual verification in browser**

Follow the `run`/`webapp-testing` pattern used earlier this session: start backend (`cd backend && ./.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`) and frontend (`cd frontend && NEXT_PUBLIC_API_URL="http://127.0.0.1:8000/api/v1" PORT=3001 npm run dev`), then via Playwright: draw a footprint, click "Umieść korytarz i klatkę" (Task 17), switch to `edit-circulation` mode, drag the corridor group, screenshot to confirm it visually moves and snaps to 0.5m.

- [ ] **Step 7: Verify types compile, run frontend build**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/CanvasEditor.tsx frontend/app/state/SessionContext.tsx
git commit -m "feat: render circulationResult + edit-circulation drag mode

Corridor/cage from Etap 1 now render on the canvas even before Etap 2 has
run (falls back from layoutResult to circulationResult). New
edit-circulation mode drags the whole corridor+cage group as a rigid unit,
snapped to 0.5m, client-side only. Etap 2 (runSubdivideUnits) always uses
the last server-computed remainder from the most recent /layout/circulation
call, not a client-recomputed one -- documented as a known limitation, not
a silent gap (full remainder recomputation on drag is a follow-up, not in
this task's scope)."
```

### Task 17: `CirculationSection.tsx` — two-button staged UI

**Files:**
- Modify: `frontend/app/components/CirculationSection.tsx`

**Interfaces:**
- Consumes: `runPlaceCirculation`, `runSubdivideUnits` (Task 15).

- [ ] **Step 1: Read the current file to match its existing structure**

Run (read, don't guess): open `frontend/app/components/CirculationSection.tsx` and note the existing form fields (`corridor_width_m`, `cage_size_m`, `cage_position`, typology selector) and how `regenerate()` is currently wired to a button, so the new buttons follow the same styling/layout conventions.

- [ ] **Step 2: Replace the single generate button with two staged buttons**

Find the existing "Generuj układ" button in this file (wired to `regenerate` from `useSession()`). Replace it with:

```tsx
<button
  onClick={() => void runPlaceCirculation()}
  disabled={!state.footprint || state.isLoading}
  className="w-full rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-40"
>
  {state.isLoading ? "Umieszczam..." : "1. Umieść korytarz i klatkę"}
</button>
<button
  onClick={() => void runSubdivideUnits()}
  disabled={!state.circulationResult || state.isLoading}
  className="w-full rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-40"
>
  {state.isLoading ? "Dzielę..." : "2. Podziel na mieszkania"}
</button>
```

Destructure `runPlaceCirculation, runSubdivideUnits` from `useSession()` at the top of the component (alongside whatever is already destructured there, e.g. `state, setCirculation, regenerate`). Leave `regenerate` (the old combined wrapper) imported but unused only if some other part of this file still calls it directly — otherwise remove the now-unused import to keep `ruff`/`eslint` clean; check with a search across the frontend for other `regenerate()` call sites before removing it from the destructure (the "Regeneruj układ" quick-path button elsewhere may still legitimately use it — spec §1 keeps `/layout/generate` as a fast-path wrapper on purpose).

- [ ] **Step 3: Add the edit-circulation mode toggle button**

Add near the existing mode-toggle buttons pattern (matches `FootprintSection.tsx`'s "Węzły"/"Linie" buttons):

```tsx
<button
  onClick={() => setMode(state.mode === "edit-circulation" ? "idle" : "edit-circulation")}
  disabled={!state.circulationResult}
  className={`rounded px-2 py-1.5 text-sm disabled:opacity-40 ${
    state.mode === "edit-circulation" ? "bg-blue-600 text-white" : "bg-neutral-700 text-neutral-100 hover:bg-neutral-600"
  }`}
  title={!state.circulationResult ? "Wymaga umieszczenia korytarza/klatki" : "Przeciągnij korytarz/klatkę"}
>
  Przesuń komunikację
</button>
```

`setMode` should already be destructured from `useSession()` in this file if the typology selector or other mode-dependent UI exists; if not, add it to the destructure.

- [ ] **Step 4: Verify types compile, manual browser check**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

Manually verify in browser (per Task 16 Step 6's server-start pattern): draw footprint → click "1. Umieść korytarz i klatkę" → corridor/cage render → click "2. Podziel na mieszkania" → apartments render → click "Przesuń komunikację" → drag works.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/components/CirculationSection.tsx
git commit -m "feat: two-step circulation UI (place, then subdivide) + drag toggle

Replaces the single 'Generuj układ' button with '1. Umieść korytarz i
klatkę' -> '2. Podziel na mieszkania', matching the new staged backend
pipeline. Adds a 'Przesuń komunikację' toggle for the new edit-circulation
canvas mode."
```

---

## Final Regression Pass

### Task 18: Full-stack manual verification + final regression

**Files:** none (verification only)

- [ ] **Step 1: Full backend regression**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (baseline 96 + new tests from this plan, roughly 115-125).

Run: `cd backend && ./.venv/Scripts/python.exe -m ruff check .`
Expected: clean.

- [ ] **Step 2: Full frontend build**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean. Do NOT run `npm run build` if a `npm run dev` server is live in the same directory (production build writes to the same `.next/` cache and can corrupt a running dev server's HMR state — known issue from earlier this session).

- [ ] **Step 3: End-to-end manual verification in browser**

Start backend (no `--reload`, matches this session's established pattern) and frontend on an explicit non-3000 port (port 3000 is permanently occupied by an unrelated `whatsapp-bridge` service on this machine — use `PORT=3001`). Via Playwright (`webapp-testing` skill pattern used throughout this session):

1. Draw a **concave** footprint (L-shape or U-shape) — this is the actual regression case for the whole redesign.
2. Click "1. Umieść korytarz i klatkę" — verify corridor + cage render, no console errors.
3. Click "2. Podziel na mieszkania" — verify apartments render with areas close to the program's `min_area_m2` (not squared/wrong like the pre-redesign bug).
4. Run solar analysis — verify facades are non-empty (regression check for the facade-matching fix from earlier today, which this redesign must not re-break).
5. Screenshot the result, visually confirm it looks like a sane floor plan (rectangular-ish apartments, corridor through the middle, not a pierced ring or garbage geometry).

- [ ] **Step 4: Update `plan.md` status note**

In `plan.md`, near the §4.1 section updated earlier today, add one line confirming implementation is complete (date, brief note) — follow the existing "historia" comment-block convention already present in that section.

- [ ] **Step 5: Final commit**

```bash
git add plan.md
git commit -m "docs: mark layout-engine redesign implementation complete in plan.md"
```
