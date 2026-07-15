# L/U Shapes: Corridor Spine, Honest Typology, Editing QoL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Written for cheap/small implementer models:** every step carries complete code and exact commands. Line numbers are from 2026-07-15 (commit `96f157b`) — ALWAYS re-locate by searching the quoted strings, never trust raw line numbers. If current code at a site differs from a "current code" block, STOP and report BLOCKED instead of guessing a merge.

**Goal:** (A) two quick editing wins — a "Wyczyść mieszkania" button that clears apartments without touching circulation, and corridor-axis segment dragging (like footprint edge dragging); (B) corridors that work on L/U and other concave footprints via a connected corridor SPINE (today each zone gets an independent strip — on an L they can miss each other, and trakt slicing misreads an L-shaped corridor's direction); (C) honest typology — presets that actually configure corridor topology, the senseless "Pozycja klatki" select removed, new `corridor_mode` (double-loaded / gallery).

**Architecture:** The spine is the single source of truth for horizontal circulation: an ordered polyline built per zone with the existing trakt-aware axis (`_corridor_axis_offset`), then CONNECTED at zone seams (endpoints snapped to a shared joint), buffered into one corridor polygon. Trakt slicing gets the spine's segments and cuts perpendicular to the NEAREST SEGMENT's own axis (not the corridor part's bbox). Cage spread/ends metrics measure along the spine's arc length. `corridor_mode="gallery"` prefers the flush (single-loaded) axis candidate — that plus real preset mapping makes typology honest. Vertical circulation (cages) already runs on the optimization kernel (Etap 1-3); this plan only fixes its geometry inputs (spine-touch constraint, arc-length metrics).

**Tech Stack:** Python 3.11 + Shapely 2.x + FastAPI, Next.js + Konva. No new dependencies.

## Global Constraints

- Backend bar: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` exit 0 (ALWAYS the venv python — global python lacks deps). Frontend bar: `cd frontend && npx tsc --noEmit` exit 0 (no frontend unit tests exist).
- Determinism: identical inputs → identical outputs; only `random.Random(seed)`.
- Rectangle regression bar: on any convex rectangle footprint the spine is a single segment and ALL existing outputs (corridor polygon, centerline, dots, remainder) must stay byte-identical to today. Tests asserting today's rectangle behavior must pass UNMODIFIED in Tasks 3-6.
- Hard bans unchanged: every apartment touches circulation AND facade, MRR ratio ≤ 3 (`HARD_MAX_ASPECT_RATIO`); winner = best hard-valid.
- Dual-surface rule: any new request/response field goes through BOTH `/layout/circulation`+`/layout/units` and `/layout/generate` (shared serializers `_serialize_cage_iteration` / `_serialize_unit_iteration` / `layout_result_to_response`).
- `MIN_TRAKT_DEPTH_M` (circulation.py) and `NET_SHRINK_M` (wall_geometry.py) are imported, never re-hardcoded.
- Trakt depth rule (user 2026-07-15): a residential band between corridor and facade is valid ONLY at depth `[MIN_TRAKT_DEPTH_M, MAX_ONE_SIDED_TRAKT_M]` (one-sided daylighting, ≤ 7 m) or `≥ MIN_THROUGH_TRAKT_M` (through-apartments, ≥ 10 m). The (7, 10) range is forbidden for axis candidates and warned about in validation. New constants in circulation.py: `MAX_ONE_SIDED_TRAKT_M = 7.0`, `MIN_THROUGH_TRAKT_M = 10.0` — import, never re-hardcode.
- Corridor NEVER hugs a facade in `corridor_mode="double"` (user 2026-07-15: "korytarz powinien środkować") — flush axis candidates exist ONLY in `corridor_mode="gallery"`. Legacy clamp remains the last-resort fallback for degenerate zones.
- Cage philosophy (user 2026-07-15): as FEW cages as evacuation allows (slider = maximum, engine picks the smallest k with zero red dots), positioned to waste no daylight facade (interior/by-corridor, north facade, or concave corner — never gratuitously on the south facade).
- Git hygiene: stage ONLY files the task names, by name; never `git add -A` / `git add .`. Commit message per task as given.
- Implementer contract: TDD where a task defines tests (write → RED → implement → GREEN); full suite once before reporting; report lists every pre-existing test you had to update, each with a 1-line justification; never weaken an assertion to presence-only.

---

## CZĘŚĆ A — szybkie usprawnienia edycji (niezależne od reszty; można równolegle z B)

### Task 1: Przycisk "Wyczyść mieszkania" (komunikacja zostaje)

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx`
- Modify: `frontend/app/components/CirculationSection.tsx`

**Interfaces:**
- Produces: reducer action `{ type: "CLEAR_APARTMENTS" }`, context fn `clearApartments(): void`.

- [ ] **Step 1: Reducer action.** In `SessionContext.tsx` find the `type Action =` union (search `| { type: "SET_TOTAL_UNITS"`) and add one member:

```ts
  | { type: "CLEAR_APARTMENTS" }
```

Find the reducer `switch` case `case "SET_ITERATIONS_COUNT":` and add directly above it:

```ts
    case "CLEAR_APARTMENTS":
      // Czyści WYŁĄCZNIE wynik podziału na mieszkania (user 2026-07-15):
      // komunikacja (circulationResult + elementy ręczne) zostaje nietknięta,
      // w przeciwieństwie do istniejącego "Wyczyść", które zeruje oba.
      return {
        ...state,
        layoutResult: null,
        lastIterations: [],
        validation: null,
        solarResult: null,
        activeUnitSeed: null,
        derivedTotalUnits: null,
        netRemainderM2: null,
        selectedApartmentId: null,
      };
```

- [ ] **Step 2: Context exposure.** Next to the existing clear function (search the string `Wyczyść` in SessionContext.tsx to find how the current clear is exposed; if the clear logic lives in the component instead, just add a new callback next to `setIterationsCount`):

```ts
  const clearApartments = useCallback(() => dispatch({ type: "CLEAR_APARTMENTS" }), []);
```

Add `clearApartments: () => void;` to the `SessionContextValue` interface (next to `setIterationsCount`) and `clearApartments,` to BOTH provider `value` object lists (search `setIterationsCount,` — it appears in the same lists; mirror it).

- [ ] **Step 3: Button.** In `CirculationSection.tsx` find the existing "Wyczyść" button (search `Wyczyść`). Add a sibling button directly ABOVE it:

```tsx
        <button
          onClick={clearApartments}
          disabled={!state.layoutResult && state.lastIterations.length === 0}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-zinc-800/70 px-3 py-2 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700/70 disabled:cursor-not-allowed disabled:opacity-40 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          title="Usuwa podział na mieszkania (iteracje, walidację); korytarz i klatki zostają."
        >
          Wyczyść mieszkania
        </button>
```

Add `clearApartments` to this component's `useSession()` destructure.

- [ ] **Step 4: Verify + commit.** `cd frontend && npx tsc --noEmit` → exit 0.

```bash
git add frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: Wyczysc mieszkania button clears apartment results while keeping circulation"
```

---

### Task 2: Drag segmentu osi korytarza (jak krawędzie obrysu)

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (the centerline `<Line>` render, search `key={\`centerline-${i}\`}`)

**Interfaces:**
- Consumes (all pre-existing, verify by search before editing): `flattenCenterline(centerline)` → `{x,y}[]`, `segmentsFromFlatPath(flat)` → `[Point2D, Point2D][]`, `runReshapeCirculation(segments)` (POST /circulation/reshape + reducer), `METER_PX`, `CIRCULATION_SNAP_M` / `snapNodeToGrid` (2026-07-14 snap helpers).
- Produces: no new exports — the centerline `<Line>` becomes draggable in `edit-corridor-centerline` mode; dragging translates BOTH endpoints of that segment by the drag delta (snap 0.1 m), shared endpoints of neighboring segments move with them (flat-path indices i and i+1). Shift is NOT needed: translating a segment by any delta keeps it parallel to itself, which is exactly the footprint-edge "Shift" behavior — free shear makes no sense for an axis, so plain drag = parallel move.

- [ ] **Step 1: Current code.** Find (verbatim as of `96f157b`, re-verify):

```tsx
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke="#60a5fa"
              strokeWidth={3 / scale}
              listening={state.mode === "edit-corridor-centerline"}
              onDblClick={(e) => {
```

- [ ] **Step 2: Replace the opening props** so the Line is draggable with snap + commit (keep the existing `onDblClick` block untouched below):

```tsx
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke="#60a5fa"
              strokeWidth={3 / scale}
              hitStrokeWidth={12 / scale}
              listening={state.mode === "edit-corridor-centerline"}
              draggable={state.mode === "edit-corridor-centerline"}
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragMove={(e) => {
                snapNodeToGrid(e.target);
              }}
              onDragEnd={(e) => {
                // Przesunięcie CAŁEGO segmentu osi (user 2026-07-15): oba końce
                // dostają tę samą deltę -> segment zostaje równoległy do siebie
                // (odpowiednik Shift-dragu krawędzi obrysu). Wspólne końce
                // sąsiadów jadą razem, bo edytujemy flat-path pod indeksami
                // i oraz i+1 (flat[i]/flat[i+1] == seg.points, jak w onDblClick).
                e.cancelBubble = true;
                if (!state.circulationResult) return;
                const node = e.target;
                const dxM = Math.round(node.x() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                const dyM = -Math.round(node.y() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                node.position({ x: 0, y: 0 });
                if (dxM === 0 && dyM === 0) return;
                const flat = flattenCenterline(state.circulationResult.centerline);
                const moved = flat.map((p, idx) =>
                  idx === i || idx === i + 1 ? { x: p.x + dxM, y: p.y + dyM } : p
                );
                void runReshapeCirculation(segmentsFromFlatPath(moved));
              }}
              onDblClick={(e) => {
```

(The rest of the existing `onDblClick` body stays exactly as is.)

- [ ] **Step 3: Verify + commit.** `cd frontend && npx tsc --noEmit` → exit 0. Manual sanity is Task 10's job.

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: corridor centerline segments are draggable (parallel move, 0.1m snap), like footprint edges"
```

---

## CZĘŚĆ B — spine komunikacji dla L/U (backend; Taski 3→7 sekwencyjnie)

### Task 3: `services/corridor_spine.py` — spójny spine z segmentów stref

**Files:**
- Create: `backend/services/corridor_spine.py`
- Test: `backend/tests/test_corridor_spine.py` (new)

**Interfaces:**
- Consumes: `_corridor_axis_offset`, `NET_SHRINK_M`, `MIN_TRAKT_DEPTH_M` (import from `services.circulation` — no cycle: circulation does NOT import this module until Task 4, and in Task 4 circulation imports lazily inside the function).
- Produces (Tasks 4-6 rely on these exact signatures):
  - `@dataclass SpineSegment: p1: tuple[float, float]; p2: tuple[float, float]; zone_index: int`
  - `build_spine(zones: list[Polygon], cages_by_zone: dict[int, list[Polygon]], corridor_width_m: float) -> list[SpineSegment]` — one axis segment per viable zone (trakt-aware offset, cage-anchored), endpoints CONNECTED at zone seams.
  - `spine_polygon(segments, corridor_width_m, footprint) -> Polygon | MultiPolygon` — union of per-segment strips (grown width = `corridor_width_m + 2*NET_SHRINK_M`, flat caps) clipped to footprint.
  - `nearest_segment_index(point: tuple[float, float], segments) -> int`

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_corridor_spine.py`):

```python
"""Spine korytarza (plan 2026-07-15 §B): segmenty stref połączone na szwach
w jedną spójną komunikację -- fix dla L/U, gdzie osobne paski per strefa
potrafiły się nie stykać."""

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from services.bsp import rectangle_decompose
from services.corridor_spine import build_spine, nearest_segment_index, spine_polygon


def _zones(footprint):
    return rectangle_decompose(footprint)


def test_rectangle_spine_is_single_segment():
    fp = box(0, 0, 40, 12)
    segments = build_spine(_zones(fp), {}, corridor_width_m=1.5)
    assert len(segments) == 1
    (x1, y1), (x2, y2) = segments[0].p1, segments[0].p2
    assert y1 == y2  # poziomy, wzdłuż dłuższej osi
    assert abs(x2 - x1) == 40.0


def test_l_shape_spine_is_connected():
    """L 30x20 z ramionami 8 m: 2 strefy -> 2 segmenty, których końce
    SPOTYKAJĄ SIĘ w jednym punkcie (staw narożny), a poligon korytarza
    jest jednym spójnym komponentem."""
    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    zones = _zones(l_shape)
    assert len(zones) == 2
    segments = build_spine(zones, {}, corridor_width_m=1.5)
    assert len(segments) == 2
    endpoints = [segments[0].p1, segments[0].p2, segments[1].p1, segments[1].p2]
    # dokładnie jedna para końców pokrywa się (wspólny staw)
    shared = [
        (a, b) for ai, a in enumerate(endpoints) for b in endpoints[ai + 1:]
        if abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
    ]
    assert len(shared) == 1, endpoints

    poly = spine_polygon(segments, 1.5, l_shape)
    assert poly.geom_type == "Polygon", "korytarz L musi być jednym spójnym poligonem"
    assert poly.area > 0
    assert l_shape.buffer(1e-6).contains(poly)


def test_u_shape_spine_connected_three_segments():
    u_shape = Polygon([
        (0, 0), (36, 0), (36, 20), (28, 20), (28, 8), (8, 8), (8, 20), (0, 20),
    ])
    zones = _zones(u_shape)
    segments = build_spine(zones, {}, corridor_width_m=1.5)
    assert len(segments) == len(zones)
    poly = spine_polygon(segments, 1.5, u_shape)
    assert poly.geom_type == "Polygon", "korytarz U musi być spójny"


def test_spine_respects_cage_anchor():
    """Klatka przy południowej krawędzi prostokąta przyciąga oś (w granicach
    reguły traktów) -- identycznie jak _corridor_axis_offset."""
    fp = box(0, 0, 40, 12)
    cage = box(0, 0, 4.2, 5.7)
    segments = build_spine(_zones(fp), {0: [cage]}, corridor_width_m=1.5)
    y = segments[0].p1[1]
    from services.circulation import MIN_TRAKT_DEPTH_M, NET_SHRINK_M
    half = (1.5 + 2 * NET_SHRINK_M) / 2.0
    south, north = (y - half) - 0.0, 12.0 - (y + half)
    for band in (south, north):
        assert band <= 1e-6 or band >= MIN_TRAKT_DEPTH_M - 1e-6


def test_nearest_segment_index():
    fp = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    segments = build_spine(_zones(fp), {}, corridor_width_m=1.5)
    horizontal = 0 if abs(segments[0].p1[1] - segments[0].p2[1]) < 1e-6 else 1
    vertical = 1 - horizontal
    assert nearest_segment_index((20.0, 4.0), segments) == horizontal
    assert nearest_segment_index((4.0, 15.0), segments) == vertical
```

- [ ] **Step 2: RED.** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_corridor_spine.py -v` → `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `backend/services/corridor_spine.py`:

```python
"""Spine korytarza (plan 2026-07-15 §B): pozioma komunikacja jako JEDNA
spójna łamana zamiast niezależnych pasków per strefa. Segment na strefę
liczony dotychczasową regułą traktów (_corridor_axis_offset), a potem końce
segmentów sąsiadujących stref są ŁĄCZONE na szwie: koniec segmentu bliższy
szwu jest przesuwany do punktu przecięcia z osią segmentu sąsiada
(staw narożny "L"). Poligon korytarza = unia pasków per segment, przycięta
do obrysu -- z konstrukcji spójna tam, gdzie segmenty się stykają."""

from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.ops import unary_union

from services.circulation import NET_SHRINK_M, _corridor_axis_offset

_SEAM_TOL_M = 0.5
"""Maksymalny dystans strefa-strefa uznawany za wspólny szew."""


@dataclass
class SpineSegment:
    p1: tuple[float, float]
    p2: tuple[float, float]
    zone_index: int

    @property
    def horizontal(self) -> bool:
        return abs(self.p2[1] - self.p1[1]) <= abs(self.p2[0] - self.p1[0])


def _zone_axis_segment(
    zone: Polygon, zone_index: int, cages: list[Polygon], corridor_width_m: float
) -> SpineSegment | None:
    minx, miny, maxx, maxy = zone.bounds
    w, h = maxx - minx, maxy - miny
    grown = corridor_width_m + 2 * NET_SHRINK_M
    half = grown / 2.0
    cages_union = unary_union(cages) if cages else None
    if w >= h:
        if grown >= h:
            return None
        cage_bounds = (cages_union.bounds[1], cages_union.bounds[3]) if cages_union else None
        mid = _corridor_axis_offset(miny, maxy, half, cage_bounds)
        return SpineSegment(p1=(minx, mid), p2=(maxx, mid), zone_index=zone_index)
    if grown >= w:
        return None
    cage_bounds = (cages_union.bounds[0], cages_union.bounds[2]) if cages_union else None
    mid = _corridor_axis_offset(minx, maxx, half, cage_bounds)
    return SpineSegment(p1=(mid, miny), p2=(mid, maxy), zone_index=zone_index)


def _connect_at_seam(a: SpineSegment, b: SpineSegment) -> None:
    """Modyfikuje IN PLACE: dosuwa bliższe szwu końce segmentów a i b do
    wspólnego stawu = punkt (x osi pionowego, y osi poziomego). Dla pary
    równoległych segmentów (kolinearne strefy) staw = środek odcinka
    łączącego najbliższe końce."""
    if a.horizontal != b.horizontal:
        hseg, vseg = (a, b) if a.horizontal else (b, a)
        joint = (vseg.p1[0], hseg.p1[1])
    else:
        pairs = [(pa, pb) for pa in (a.p1, a.p2) for pb in (b.p1, b.p2)]
        pa, pb = min(pairs, key=lambda pq: math.dist(pq[0], pq[1]))
        joint = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)

    for seg in (a, b):
        if math.dist(seg.p1, joint) <= math.dist(seg.p2, joint):
            seg.p1 = joint
        else:
            seg.p2 = joint


def build_spine(
    zones: list[Polygon],
    cages_by_zone: dict[int, list[Polygon]],
    corridor_width_m: float,
) -> list[SpineSegment]:
    segments: list[SpineSegment] = []
    for i, zone in enumerate(zones):
        if not zone.is_valid or zone.area < 1e-6:
            continue
        seg = _zone_axis_segment(zone, i, cages_by_zone.get(i, []), corridor_width_m)
        if seg is not None:
            segments.append(seg)

    # łącz każdą parę segmentów, których strefy się stykają (deterministycznie
    # po indeksach rosnąco)
    for ai in range(len(segments)):
        for bi in range(ai + 1, len(segments)):
            za = zones[segments[ai].zone_index]
            zb = zones[segments[bi].zone_index]
            if za.distance(zb) <= _SEAM_TOL_M:
                _connect_at_seam(segments[ai], segments[bi])
    return segments


def spine_polygon(
    segments: list[SpineSegment], corridor_width_m: float, footprint: Polygon
) -> "Polygon | MultiPolygon":
    grown = corridor_width_m + 2 * NET_SHRINK_M
    strips = [
        LineString([s.p1, s.p2]).buffer(grown / 2.0, cap_style="flat", join_style="mitre")
        for s in segments
        if math.dist(s.p1, s.p2) > 1e-9
    ]
    if not strips:
        return Polygon()
    # flat caps zostawiają szczelinę w stawie -- domknij ją kwadratem w stawie
    joints = []
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            for pa in (segments[i].p1, segments[i].p2):
                for pb in (segments[j].p1, segments[j].p2):
                    if math.dist(pa, pb) < 1e-9:
                        joints.append(Point(pa).buffer(grown / 2.0, cap_style="square"))
    return unary_union(strips + joints).intersection(footprint)


def nearest_segment_index(point: tuple[float, float], segments: list[SpineSegment]) -> int:
    p = Point(point)
    return min(
        range(len(segments)),
        key=lambda i: LineString([segments[i].p1, segments[i].p2]).distance(p),
    )
```

- [ ] **Step 4: GREEN + full suite** (nothing imports the module yet → no regressions expected). If `test_l_shape_spine_is_connected` fails on `shared == 1`, print the endpoints and check `_connect_at_seam`'s joint math against the actual zone layout before touching the test — the test encodes the spec.

- [ ] **Step 5: Commit.**

```bash
git add backend/services/corridor_spine.py backend/tests/test_corridor_spine.py
git commit -m "feat: connected corridor spine - per-zone trakt-aware segments joined at zone seams"
```

---

### Task 4: `_assemble_with_cages` na spine (spójny korytarz w L/U)

**Files:**
- Modify: `backend/services/circulation.py` (`_assemble_with_cages`, search `def _assemble_with_cages`)
- Test: `backend/tests/test_circulation.py` (append)

**Interfaces:**
- Consumes: Task 3's `build_spine`, `spine_polygon` (LAZY import inside `_assemble_with_cages` — corridor_spine imports circulation at module level, the reverse must stay function-local to avoid the cycle).
- Produces: `CirculationResult` gains `spine_segments: list[tuple[tuple[float, float], tuple[float, float]]]` (dataclass field, default `[]` — find `class CirculationResult` and append the field with a docstring "Segmenty spine (plan 2026-07-15) -- źródło kierunków cięcia traktów"). Task 5 consumes it.

- [ ] **Step 1: Failing test** (append to `backend/tests/test_circulation.py`):

```python
def test_l_shape_corridor_is_connected_and_reaches_both_wings():
    """Plan 2026-07-15 §B: na L korytarz to JEDEN spójny poligon łączący oba
    skrzydła (stare paski per strefa umiały się nie stykać), a centerline
    podąża za spine (wspólny staw)."""
    from services.circulation import place_circulation

    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    result = place_circulation(
        l_shape, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    corridor_only = result.circulation_geometry.difference(
        unary_union(result.cage_polygons)
    )
    assert corridor_only.geom_type == "Polygon", (
        f"korytarz na L musi być spójny, jest {corridor_only.geom_type}"
    )
    # spine wystawiony w wyniku, >= 2 segmenty na 2 strefach
    assert len(result.spine_segments) >= 2
    # kropki ewakuacyjne istnieją i nie wszystkie czerwone
    assert result.evacuation_dots
    assert any(d.status != "red" for d in result.evacuation_dots)
```

(Import `unary_union` at the top of the test file if absent: `from shapely.ops import unary_union`.)

- [ ] **Step 2: RED**, then **implement**: inside `_assemble_with_cages`, replace the per-zone corridor block:

Current code (search `corridor = _build_corridor(zone_remaining, corridor_width_m, cages_union)`):

```python
    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue

        zone_cages = local_cages.get(i, [])
        cages_union = unary_union(zone_cages) if zone_cages else None
        zone_remaining = zone.polygon.difference(cages_union) if cages_union is not None else zone.polygon

        corridor = _build_corridor(zone_remaining, corridor_width_m, cages_union)
        if corridor.area > 0:
            circulation_geom = unary_union([circulation_geom, corridor])
            zone_remaining = zone_remaining.difference(corridor)

        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)
```

Replace with:

```python
    # Spine (plan 2026-07-15): segmenty per strefa liczone tą samą regułą
    # traktów co _build_corridor, ale ŁĄCZONE na szwach stref -- na L/U
    # korytarz jest jednym spójnym poligonem zamiast luźnych pasków.
    from services.corridor_spine import build_spine, spine_polygon  # lazy: cykl

    spine = build_spine(
        [z.polygon for z in zones],
        {i: local_cages.get(i, []) for i in range(len(zones))},
        corridor_width_m,
    )
    corridor_poly = spine_polygon(spine, corridor_width_m, footprint)
    if corridor_poly.area > 0:
        circulation_geom = unary_union([circulation_geom, corridor_poly])

    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        zone_cages = local_cages.get(i, [])
        cages_union = unary_union(zone_cages) if zone_cages else None
        zone_remaining = zone.polygon.difference(cages_union) if cages_union is not None else zone.polygon
        zone_remaining = zone_remaining.difference(corridor_poly)
        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)
```

Then the centerline block below (search `seg = _corridor_centerline(zone.polygon, corridor_width_m, cages_union)`): replace the per-zone `_corridor_centerline` call with the spine segments —

```python
    raw_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for s in spine:
        zone_cages = local_cages.get(s.zone_index, [])
        raw_segments.extend(_split_segment_at_cage_positions((s.p1, s.p2), zone_cages))
```

Finally, where `CirculationResult(...)` is constructed in this function, pass `spine_segments=[(s.p1, s.p2) for s in spine]` (after adding the field to the dataclass per Interfaces).

- [ ] **Step 3: GREEN + full suite.** Rectangle regression bar applies: single-zone footprints produce a 1-segment spine whose strip is IDENTICAL to `_build_corridor`'s (same axis offset math, same grown width) — if any rectangle test fails, the spine math drifted from `_build_corridor`; fix the code, not the test. Multi-zone tests asserting the OLD disconnected shape (if any exist) may be updated with justification.

- [ ] **Step 4: Commit.**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: circulation assembles from the connected spine - L/U corridors are one polygon"
```

---

### Task 5: Trakt slicing per segment spine

**Files:**
- Modify: `backend/services/trakt_division.py` (`slice_trakts`), `backend/services/unit_mix.py` (`_UnitsGenerator.build` + `iterate_units` threading), `backend/services/layout.py` (pass spine into iterate_units), `backend/api/v1/endpoints/layout.py` (units endpoint pass-through)
- Test: `backend/tests/test_trakt_division.py`, `backend/tests/test_unit_iterations.py` (append)

**Interfaces:**
- `slice_trakts(..., spine_segments: list[tuple[tuple[float,float],tuple[float,float]]] | None = None)` — when given, the cut direction for a component comes from the NEAREST spine segment's own axis (horizontal segment → vertical cuts), not from the corridor part's bbox (which misreads an L-shaped corridor polygon).
- `iterate_units(..., spine_segments=None)` → threads to the generator → `slice_trakts`.
- `CirculationResult.spine_segments` (Task 4) is the source: `services/layout.py` generate-path passes `circulation.spine_segments`; `/layout/units` endpoint gets a new OPTIONAL request field `spine_segments: list[list[list[float]]] | None = None` (frontend sends it from the circulation response in a LATER task — for now the endpoint accepts and threads it; None = today's behavior).

- [ ] **Step 1: Failing test** (append to `backend/tests/test_trakt_division.py`):

```python
def test_l_corridor_cuts_follow_nearest_segment():
    """L-korytarz jako jeden poligon: bez spine bbox całości kłamie o kierunku.
    Ze spine komponent przy poziomym ramieniu tnie się pionowo, a przy
    pionowym -- poziomo; każda komórka dotyka korytarza."""
    corridor = Polygon([(0, 3), (30, 3), (30, 5), (2, 5), (2, 20), (0, 20)])  # L-pas
    north_wing = box(0, 5, 30, 12).difference(box(0, 5, 2, 12))  # trakt przy poziomym ramieniu
    east_wing = box(2, 5, 8, 20).difference(corridor)  # trakt przy pionowym ramieniu
    spine = [((0.0, 4.0), (30.0, 4.0)), ((1.0, 5.0), (1.0, 20.0))]

    cells_n, _ = slice_trakts(north_wing, corridor, _specs(60, 60, 60), rng=None, spine_segments=spine)
    assert len(cells_n) == 3
    for c in cells_n:
        minx, miny, maxx, maxy = c.polygon.bounds
        assert (maxy - miny) > 6.9  # pełna głębokość traktu (7 m) -> cięcia pionowe
        assert c.polygon.distance(corridor) < 1e-6

    cells_e, _ = slice_trakts(east_wing, corridor, _specs(40, 40), rng=None, spine_segments=spine)
    assert len(cells_e) >= 1
    for c in cells_e:
        assert c.polygon.distance(corridor) < 1e-6
```

- [ ] **Step 2: RED**, then **implement** in `slice_trakts`: add the parameter, and replace the orientation derivation. Current code (search `horizontal = (pmaxx - pminx) >= (pmaxy - pminy)`):

```python
        part = next((p for p in corridor_parts if component.distance(p) < _TOUCH_TOL_M), None)
        if part is None or not queue:
            leftover_parts.append(component)
            continue
        pminx, pminy, pmaxx, pmaxy = part.bounds
        horizontal = (pmaxx - pminx) >= (pmaxy - pminy)
```

Replace with:

```python
        part = next((p for p in corridor_parts if component.distance(p) < _TOUCH_TOL_M), None)
        if part is None or not queue:
            leftover_parts.append(component)
            continue
        if spine_segments:
            # kierunek z NAJBLIŻSZEGO segmentu spine (plan 2026-07-15 Task 5):
            # bbox całego L-korytarza kłamie o osi lokalnego ramienia
            cx, cy = component.centroid.x, component.centroid.y
            from shapely.geometry import LineString as _LS, Point as _Pt
            best = min(spine_segments, key=lambda s: _LS([s[0], s[1]]).distance(_Pt(cx, cy)))
            horizontal = abs(best[1][1] - best[0][1]) <= abs(best[1][0] - best[0][0])
        else:
            pminx, pminy, pmaxx, pmaxy = part.bounds
            horizontal = (pmaxx - pminx) >= (pmaxy - pminy)
```

(If `part.bounds` unpacking is used further below for the notch-widening denominator, verify it still resolves — the denominator uses COMPONENT depth per 2026-07-13 fix, so removing the `pminx...` unpack from this branch is safe; keep it in the else-branch only.)

Threading: `_UnitsGenerator.__init__` gains `spine_segments=None` stored on self, `build` passes it to `slice_trakts`; `iterate_units(..., spine_segments=None)` passes into the generator; `services/layout.py` generate-path call adds `spine_segments=circulation.spine_segments` (the Task 4 field); units endpoint request model gains `spine_segments: list[list[list[float]]] | None = None` converted to tuples and passed. Frontend wiring of the field is Task 7's checklist item (response already carries it after Task 4 — add `spine_segments?: number[][][]` to `CirculationResponse` serialization: in `backend/api/v1/endpoints/layout.py` add `spine_segments: list[list[list[float]]] = []` to `CirculationResponse` and fill from `result.spine_segments` at all 3 construction sites + reshape + `_serialize_cage_iteration` — the dual-surface drill from corridor-net-shrink applies verbatim).

- [ ] **Step 3: e2e** (append to `backend/tests/test_unit_iterations.py`):

```python
def test_l_footprint_units_all_touch_circulation_and_facade():
    """e2e L: spine + trakt-per-segment -> istnieje iteracja hard-valid."""
    from services.circulation import place_circulation

    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    circ = place_circulation(
        l_shape, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto",
    )
    _cells, metas, best_seed, _ = iterate_units(
        circ.remainder, SHARES, iterations=20,
        footprint=l_shape, circulation_geometry=circ.circulation_geometry,
        spine_segments=circ.spine_segments,
    )
    assert any(m.hard_valid for m in metas), [m.hard_violations for m in metas][:5]
    assert next(m for m in metas if m.seed == best_seed).hard_valid
```

- [ ] **Step 4: GREEN + full suite + commit.**

```bash
git add backend/services/trakt_division.py backend/services/unit_mix.py backend/services/layout.py backend/api/v1/endpoints/layout.py backend/tests/test_trakt_division.py backend/tests/test_unit_iterations.py
git commit -m "feat: trakt slicing cuts perpendicular to the nearest spine segment - correct on L/U corridors"
```

---

### Task 6: Metryki klatek wzdłuż łuku spine

**Files:**
- Modify: `backend/services/cage_placement.py` (`_score_placement` — `ends` i `spread`)
- Test: `backend/tests/test_cage_placement.py` (append)

**Interfaces:**
- Consumes: `result.spine_segments` (Task 4) — `_score_placement(result, footprint, num_cages, weights)` already receives `result`; replace the bbox-axis projection with arc-length along the spine polyline. Reuse `_distances_along_centerline`/`_join_centerlines` from `services.circulation` if their signatures fit; otherwise compute inline (code below).

- [ ] **Step 1: Failing test:**

```python
def test_spread_measured_along_spine_arc_on_l_shape():
    """Na L dwie klatki na KOŃCACH obu ramion są idealnie rozstawione wzdłuż
    łuku spine -- bbox-owa projekcja na jedną oś widziała je jako stłoczone."""
    from services.circulation import place_circulation
    from services.cage_placement import CageWeights, _score_placement

    l_shape = Polygon([(0, 0), (30, 0), (30, 8), (8, 8), (8, 20), (0, 20)])
    result = place_circulation(
        l_shape, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=2,
    )
    if len(result.cage_polygons) < 2:
        import pytest
        pytest.skip("auto nie postawił 2 klatek na tym L (pula kandydatów)")
    _score, comps = _score_placement(result, l_shape, 2, CageWeights())
    assert 0.0 <= comps["spread"] <= 1.0
    assert 0.0 <= comps["ends"] <= 1.0
```

Plus a STRONG unit test of the helper itself (no geometry pipeline):

```python
def test_arc_positions_on_bent_spine():
    from services.cage_placement import _arc_positions

    spine = [((0.0, 0.0), (10.0, 0.0)), ((10.0, 0.0), (10.0, 10.0))]  # łuk 20 m
    ts = _arc_positions([(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)], spine)
    assert [round(t, 3) for t in ts] == [0.0, 0.5, 1.0]
```

- [ ] **Step 2: Implement** in `cage_placement.py` a helper + rewire `_score_placement`:

```python
def _arc_positions(points, spine_segments):
    """Pozycje punktów [0..1] wzdłuż łuku łamanej spine: rzut punktu na
    najbliższy segment + skumulowana długość poprzednich segmentów."""
    from shapely.geometry import LineString, Point

    lines = [LineString([p1, p2]) for p1, p2 in spine_segments]
    lengths = [ln.length for ln in lines]
    total = sum(lengths) or 1.0
    prefix = [0.0]
    for ln_len in lengths[:-1]:
        prefix.append(prefix[-1] + ln_len)
    out = []
    for pt in points:
        p = Point(pt)
        i = min(range(len(lines)), key=lambda k: lines[k].distance(p))
        out.append((prefix[i] + lines[i].project(p)) / total)
    return out
```

In `_score_placement`, replace the bbox projection block (search `horizontal = (maxx - minx) >= (maxy - miny)` INSIDE `_score_placement` — NOT the one in `_candidate_cages`):

```python
    spine = getattr(result, "spine_segments", None) or []
    if spine:
        ts = sorted(_arc_positions([(c.centroid.x, c.centroid.y) for c in cages], spine))
    else:
        horizontal = (maxx - minx) >= (maxy - miny)
        axis_len = (maxx - minx) if horizontal else (maxy - miny)
        axis_len = axis_len or 1.0
        ts = sorted(
            ((c.centroid.x - minx) / axis_len if horizontal else (c.centroid.y - miny) / axis_len)
            for c in cages
        )
```

(The `ends`/`spread` formulas below the block stay unchanged — they consume `ts`.)

- [ ] **Step 3: GREEN + full suite + commit.** Rectangle regression: 1-segment spine arc positions ≡ old bbox projection (same normalization) — existing concrete-value tests must pass unmodified.

```bash
git add backend/services/cage_placement.py backend/tests/test_cage_placement.py
git commit -m "feat: cage ends/spread metrics measured along the spine arc - correct on L/U"
```

---

### Task 7: Weryfikacja Części B na żywo + frontend spine passthrough

**Files:**
- Modify: `frontend/app/lib/api.ts` (`CirculationResponse` + `subdivideUnits`), `frontend/app/state/SessionContext.tsx` (`runSubdivideUnits`)

- [ ] **Step 1:** `api.ts`: add `spine_segments?: number[][][];` to `CirculationResponse`; add optional trailing param `spineSegments?: number[][][]` to `subdivideUnits` posted as `spine_segments`. `SessionContext.tsx` `runSubdivideUnits`: pass `state.circulationResult.spine_segments`. `npx tsc --noEmit` exit 0.
- [ ] **Step 2:** Full backend suite exit 0. Fresh servers (kill orphaned uvicorn workers via `Get-CimInstance Win32_Process` filter `spawn_main|uvicorn` — see gotcha memory; verify freshness BEHAVIORALLY: POST an L-footprint and check `spine_segments` present in the response, not just HTTP 200).
- [ ] **Step 3:** Live smoke: `/layout/generate` on the L `[(0,0),(30,0),(30,8),(8,8),(8,20),(0,20)]` with the standard 4-type program → corridor one connected polygon, ≥1 hard-valid iteration, winner hard-valid. Same for U.
- [ ] **Step 4:** Commit frontend files; hand user checklist: L-obrys → Umieść → korytarz spójny przez narożnik; Podziel → mieszkania pełnotraktowe w obu skrzydłach, narożne "L"; drag segmentu osi (Task 2) działa na obu ramionach; "Wyczyść mieszkania" zostawia korytarz.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx
git commit -m "feat: frontend threads spine_segments from circulation response into unit division"
```

---

## CZĘŚĆ C — uczciwa typologia (po Części B)

### Task 8: `corridor_mode` (double | gallery) + usunięcie selecta "Pozycja klatki"

**Files:**
- Modify: `backend/services/circulation.py` (`_corridor_axis_offset` + `place_circulation`), `backend/services/corridor_spine.py` (threading), `backend/services/layout.py` (`LayoutInput`), `backend/api/v1/endpoints/layout.py` (`CirculationSpec`), `frontend/app/lib/api.ts`, `frontend/app/state/SessionContext.tsx`, `frontend/app/components/CirculationSection.tsx`
- Test: `backend/tests/test_circulation.py`, `backend/tests/test_layout_circulation_endpoint.py` (append)

**Interfaces:**
- `_corridor_axis_offset(lo, hi, half, cage_bounds, prefer_flush: bool = False)` — with `prefer_flush=True` the flush candidates (jednotrakt) are preferred over the balanced one when feasible (gallery = korytarz przy elewacji, single-loaded).
- `CirculationSpec.corridor_mode: str = Field(default="double", pattern="^(double|gallery)$")`, threaded: endpoint → `place_circulation(corridor_mode=...)` → `build_spine(..., prefer_flush=corridor_mode == "gallery")` → `_zone_axis_segment` → `_corridor_axis_offset`. `LayoutInput.corridor_mode: str = "double"` for `/generate`. Dual-surface.
- UI: the "Pozycja klatki" `<select>` (CAGE_MODES) is REMOVED from `CirculationSection.tsx` (backend keeps accepting `cage_position` for old payloads, defaults "auto" — mark the CirculationSpec field docstring "deprecated 2026-07-15, UI no longer sends it"). In its place a "Tryb korytarza" select: `double` → "Dwutrakt (korytarz w środku)", `gallery` → "Galeriowiec (korytarz przy elewacji)".

- [ ] **Step 1: Failing tests:**

```python
def test_corridor_axis_offset_prefer_flush():
    from services.circulation import MIN_TRAKT_DEPTH_M, _corridor_axis_offset

    # strefa [0,12], half 0.85, bez klatki: balanced normalnie wygrywa środkiem,
    # prefer_flush wybiera krawędź (jednotrakt >= MIN)
    mid = _corridor_axis_offset(0.0, 12.0, 0.85, None, prefer_flush=True)
    band_lo, band_hi = (mid - 0.85) - 0.0, 12.0 - (mid + 0.85)
    assert min(band_lo, band_hi) <= 1e-6
    assert max(band_lo, band_hi) >= MIN_TRAKT_DEPTH_M - 1e-9


def test_gallery_mode_endpoint_produces_single_loaded_corridor():
    body = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5,
                        "corridor_mode": "gallery"},
    }
    r = client.post("/api/v1/layout/circulation", json=body)
    assert r.status_code == 200
    from shapely.geometry import shape
    corridor = shape(r.json()["circulation_geometry"])
    minx, miny, maxx, maxy = corridor.bounds
    # korytarz dotyka jednej z długich elewacji (y=0 lub y=12)
    assert miny <= 1e-6 or maxy >= 12 - 1e-6
```

(Match the target test file's existing client/fixture convention before pasting.)

- [ ] **Step 2: Implement the NEW axis-candidate rule** (this REPLACES the Etap-1 rule inside `_corridor_axis_offset` — user 2026-07-15: corridor must centre in double mode, flush only in gallery, trakt depths in [4,7] ∪ [10,∞)):

Add constants next to `MIN_TRAKT_DEPTH_M`:

```python
MAX_ONE_SIDED_TRAKT_M = 7.0
"""Maks. głębokość traktu doświetlanego jednostronnie (user 2026-07-15)."""
MIN_THROUGH_TRAKT_M = 10.0
"""Min. głębokość traktu mieszkań na przestrzał; zakres (7, 10) m jest
architektonicznie martwy -- ani jednostronne, ani przestrzałowe."""


def _band_depth_ok(depth: float) -> bool:
    """Dopuszczalna głębokość pasa mieszkalnego: ~0 (brak pasa), [MIN, 7]
    (jednostronne) albo >= 10 (przestrzał)."""
    return (
        depth <= 1e-6
        or MIN_TRAKT_DEPTH_M - 1e-9 <= depth <= MAX_ONE_SIDED_TRAKT_M + 1e-9
        or depth >= MIN_THROUGH_TRAKT_M - 1e-9
    )
```

Rewrite `_corridor_axis_offset` body (signature: `(lo, hi, half, cage_bounds, prefer_flush: bool = False)`), keeping `legacy` fallback identical:

```python
    center = (lo + hi) / 2.0
    anchor = (cage_bounds[0] + cage_bounds[1]) / 2.0 if cage_bounds is not None else center
    legacy = max(lo + half, min(hi - half, anchor))

    def bands(mid: float) -> tuple[float, float]:
        return (mid - half) - lo, hi - (mid + half)

    candidates: list[float] = []
    if prefer_flush:
        # galeriowiec: korytarz przy krawędzi, jedyny trakt musi być legalny
        for flush in (lo + half, hi - half):
            b1, b2 = bands(flush)
            if _band_depth_ok(b1) and _band_depth_ok(b2):
                candidates.append(flush)
    if not candidates:
        # dwutrakt: oba pasy legalnej głębokości, oś możliwie blisko klatki.
        # Szukamy najbliższego anchora punktu, gdzie OBA pasy przechodzą
        # _band_depth_ok: skan po siatce 0.1 m jest deterministyczny, tani
        # (max ~kilkaset kroków) i odporny na nieciągłość przedziałów.
        step = 0.1
        best = None
        mid = lo + half
        while mid <= hi - half + 1e-9:
            b1, b2 = bands(mid)
            if b1 > 1e-6 and b2 > 1e-6 and _band_depth_ok(b1) and _band_depth_ok(b2):
                if best is None or abs(mid - anchor) < abs(best - anchor):
                    best = mid
            mid += step
        if best is not None:
            candidates.append(best)
    if cage_bounds is not None:
        touch_lo, touch_hi = cage_bounds[0] - half, cage_bounds[1] + half
        candidates = [c for c in candidates if touch_lo <= c <= touch_hi]
    if not candidates:
        return legacy
    return min(candidates, key=lambda c: abs(c - anchor))
```

Note the intentional change vs Etap 1: double mode has NO flush candidates anymore (they exist only under `prefer_flush`). Etap-1 tests that assert flush behavior in double mode (search `test_corridor_axis_offset_prefers_balanced_then_flush` and the trakt-rule contract tests from 2026-07-13) MUST be updated to the new contract: bands ~0-or-legal-depth, flush only via prefer_flush — each update justified in the report. The 68×12 repro test keeps passing (bands 4.0/6.3 valid) — if it fails, the scan logic is wrong, not the test.

Thread `prefer_flush` through `_build_corridor`/`_corridor_centerline` (both already share the helper) and `corridor_spine._zone_axis_segment`/`build_spine`; `place_circulation(corridor_mode: str = "double")` maps to `prefer_flush=corridor_mode == "gallery"`. Endpoint fields + frontend select per Interfaces (copy the "Strategia szukania" select block as a template; state field goes in `state.circulation` like `strategy`).

- [ ] **Step 2b: Trakt-depth warning in validation.** In `backend/services/wt_validation.py` (find the existing "heurystyka" rules — e.g. "Udział komunikacji w obrysie" — and follow their exact result-object convention) add a heuristic rule `code="heurystyka"`, description "Głębokość traktu": for each remainder band implied by the corridor (compute from `circulation_geometry` bounds vs footprint bounds per horizontal/vertical spine segment, or simpler: for each apartment cell, its depth = MRR shorter side), flag apartments whose depth falls in `(MAX_ONE_SIDED_TRAKT_M, MIN_THROUGH_TRAKT_M)` — detail listing the offending cells. NEVER cite a WT § for this — it is a user heuristic (repo rule: no fabricated §-citations).

- [ ] **Step 3: GREEN + full suite + tsc + commit.**

```bash
git add backend/services/circulation.py backend/services/corridor_spine.py backend/services/layout.py backend/api/v1/endpoints/layout.py backend/tests/test_circulation.py backend/tests/test_layout_circulation_endpoint.py frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: corridor_mode double|gallery replaces the cage-position select; gallery prefers flush single-loaded axis"
```

---

### Task 9: Sensowne rozmieszczanie klatek (minimum klatek, bez marnowania światła, kotwice przy spine)

**Files:**
- Modify: `backend/services/cage_placement.py` (`_candidate_cages`, `_score_placement`, `iterate_cage_placement`), `frontend/app/components/CirculationSection.tsx` (slider label + weight label)
- Test: `backend/tests/test_cage_placement.py` (append + update old-contract tests with justifications)

**Interfaces:**
- `_candidate_cages(footprint, zones, num_cages=1, spine_segments=None)` — NEW anchors along the spine (cage snapped to either side of the corridor strip, every `CANDIDATE_EDGE_STEP_M` of arc) so cages can finally sit INTERIOR by the corridor, not only on zone edges (root cause of "klatki zawsze przy elewacji").
- `_score_placement`: component `corners` REPLACED by `light_waste` (same dict key budget: remove "corners", add "light_waste"; `CageWeights.corners` field renamed `light_waste` — update the API `CageWeightsInput`, frontend type, defaults and slider label, dual-surface).
- `iterate_cage_placement`: minimal-k search — slider is a MAXIMUM; budget split across k=1..num_cages; winner = smallest k whose best candidate has zero red evacuation dots; if no k achieves zero, the candidate with the lowest red-dot share wins.

- [ ] **Step 1: Failing tests:**

```python
def test_light_waste_component():
    """Klatka przy południowej elewacji marnuje światło (dev→1), klatka
    wewnętrzna/przy północnej -- nie (dev→0). Północ = +y (konwencja
    solar.py: azymut 0 = N)."""
    from services.cage_placement import _light_waste_for_cage
    from shapely.geometry import box

    fp = box(0, 0, 40, 12)
    south_cage = box(10, 0, 14.2, 5.7)      # styk z y=0 (południe)
    north_cage = box(10, 6.3, 14.2, 12)     # styk z y=12 (północ)
    interior = box(10, 3, 14.2, 8.7)        # zero styku z obrysem

    assert _light_waste_for_cage(south_cage, fp) > 0.9
    assert _light_waste_for_cage(north_cage, fp) < 0.1
    assert _light_waste_for_cage(interior, fp) == 0.0


def test_minimal_k_wins_when_evacuation_satisfied():
    """Suwak = maksimum: na 40x12 z progami domyślnymi 1 klatka wystarcza
    (zero czerwonych) -> zwycięzca ma 1 klatkę mimo num_cages=3."""
    footprint = _rect(0, 0, 40, 12)
    result, metas, best_seed = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=3, weights=CageWeights(), iterations=30,
    )
    winner = next(m for m in metas if m.seed == best_seed)
    reds = sum(1 for d in winner.result.evacuation_dots if d.status == "red")
    assert reds == 0
    assert winner.cages_count == 1, "1 klatka wystarcza na 40 m przy progach 20/40"


def test_more_cages_when_evacuation_demands():
    """Bardzo ciasny próg dojścia wymusza więcej klatek: zwycięzca to
    najmniejsze k dowożące zero czerwonych (albo najlepszy egress)."""
    footprint = _rect(0, 0, 60, 12)
    result, metas, best_seed = iterate_cage_placement(
        footprint, corridor_width_m=1.5, num_cages=4, weights=CageWeights(),
        iterations=40, max_dist_single_m=12.0, max_dist_multi_m=18.0,
    )
    winner = next(m for m in metas if m.seed == best_seed)
    assert winner.cages_count >= 2


def test_candidate_pool_contains_spine_adjacent_anchors():
    """Kotwice przy korytarzu: istnieją kandydaci NIE dotykający obrysu
    (wnętrze budynku, dosunięci do pasa korytarza)."""
    from services.bsp import rectangle_decompose
    from services.circulation import Zone
    from services.cage_placement import _candidate_cages

    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=p) for p in rectangle_decompose(footprint)]
    spine = [((0.0, 6.0), (40.0, 6.0))]
    candidates = _candidate_cages(footprint, zones, num_cages=2, spine_segments=spine)
    interior = [
        c for _zi, c in candidates
        if c.exterior.distance(footprint.exterior) > 0.5
    ]
    assert interior, "brak kandydatów wewnętrznych przy spine"
```

- [ ] **Step 2: Implement.**

`_light_waste_for_cage(cage, footprint) -> float` in cage_placement.py:

```python
def _light_waste_for_cage(cage: Polygon, footprint: Polygon) -> float:
    """Udział obwodu klatki sklejonego z elewacją NIE-północną (user
    2026-07-15: klatka ma nie marnować doświetlanej elewacji; północ i
    wnętrze/narożnik wewnętrzny są darmowe). Krawędź elewacji jest
    'północna', gdy jej zewnętrzna normalna ma składową +y > |składowej x|
    (konwencja solar.py: azymut 0 = N = +y)."""
    edge = footprint.exterior.buffer(0.01)
    contact = cage.boundary.intersection(edge)
    if contact.is_empty or contact.length <= 1e-9:
        return 0.0
    non_north = 0.0
    coords = list(footprint.exterior.coords)
    # CCW ring: zewnętrzna normalna krawędzi (dx,dy) to (dy,-dx)
    if not footprint.exterior.is_ccw:
        coords = coords[::-1]
    from shapely.geometry import LineString
    for a, b in zip(coords[:-1], coords[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        nx, ny = dy, -dx
        seg_contact = cage.boundary.intersection(LineString([a, b]).buffer(0.02))
        if seg_contact.is_empty:
            continue
        is_north = ny > abs(nx)
        if not is_north:
            non_north += seg_contact.length
    return min(1.0, non_north / max(contact.length, 1e-9))
```

In `_score_placement`: replace the `corners_devs` block with `light_waste = sum(_light_waste_for_cage(c, footprint) for c in cages) / k if k else 1.0`; components dict key `"corners"` → `"light_waste"`; `CageWeights.corners` → `CageWeights.light_waste` (default 0.5). Grep ALL references to `corners` in cage weights across backend (`CageWeightsInput` in endpoints), frontend (`api.ts` CageWeightsInput, `initialCirculation.cage_weights`, the WAGI KLATEK label list — new label: `["light_waste", "Nie marnuj elewacji (płd.)"]`), and localStorage backfill (merge `{ ...defaults, ...parsed }` pattern handles the rename: old sessions carry `corners`, ignored; `light_waste` fills from defaults — verify the cage_weights merge is per-key, if it's a plain object replace add a one-line backfill).

Spine anchors in `_candidate_cages(..., spine_segments=None)`: after existing anchors, for each spine segment place anchors every `CANDIDATE_EDGE_STEP_M` of its length, with the cage rectangle snapped to EITHER side of the corridor strip (offset from the axis by `corridor_half + cage_depth/2`, both orientations; corridor_half = unknown here — pass `corridor_half_m: float = 0.0` as an extra parameter, threaded from the caller which knows `corridor_width_m`; candidates filtered by footprint containment as today). `iterate_cage_placement` builds a preliminary spine (`build_spine(zones..., cages_by_zone={}, ...)` — lazy import) to feed both `_candidate_cages` and (post-selection) the final assembly.

Minimal-k in `iterate_cage_placement`: replace the single hybrid run with a deterministic loop `for k in range(1, num_cages + 1)`, each k getting `max(6, iterations // num_cages)` evaluations of the existing hybrid (genomes sample exactly k candidates); collect per-k best; winner = smallest k with `red_dots == 0` on its best candidate, else global best by (red-dot share, score). Metas: unique candidates across ALL k, ranked as today (dedupe_and_rank), so the user still browses everything.

- [ ] **Step 3: GREEN + full suite.** Expected old-contract updates (justify each): `test_iterative_placement_delivers_requested_cage_count` / `test_count_component_penalizes_shortfall_not_more_cages` (Etap-1 "deliver requested k" contract → new minimal-k contract: slider is max; count component becomes `k / num_cages` cost again OR is dropped in favor of the minimal-k selection — implementer picks the simpler and documents it), plus any test asserting `corners` in components.

- [ ] **Step 4: Commit.**

```bash
git add backend/services/cage_placement.py backend/tests/test_cage_placement.py backend/api/v1/endpoints/layout.py frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: cages seek interior/north positions (light_waste), spine-adjacent candidates, minimal count satisfying evacuation"
```

---

### Task 10: Presety typologii naprawdę konfigurują układ (po Tasku 9 — używa light_waste)

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx` (`applyTypologyPreset`, search that name), `frontend/app/components/CirculationSection.tsx` (`TYPOLOGY_LABELS` descriptions)
- Test: none automated (frontend) — backend suggestion endpoint untouched in this task.

**Interfaces:** preset → concrete `SET_CIRCULATION` patch. Mapping table (jedyne źródło prawdy, wklejone do kodu jako stała):

```ts
/** Uczciwe presety typologii (plan 2026-07-15 §C): typologia ustawia
 * topologię korytarza, liczbę klatek i profil wag -- nie tylko szerokość
 * korytarza jak dotąd. num_cages liczony z długości budynku (1 klatka na
 * każde rozpoczęte 25 m dłuższego boku bbox obrysu, min 1). */
const TYPOLOGY_CONFIG: Record<string, {
  corridor_mode: "double" | "gallery";
  cagesPer25m: boolean;
  cage_weights: api.CageWeightsInput;
}> = {
  klatkowiec_wzdluzny: {
    corridor_mode: "double", cagesPer25m: true,
    cage_weights: { egress: 1.0, count: 0.8, light_waste: 0.8, ends: 0.2, spread: 1.0 },
  },
  punktowiec: {
    corridor_mode: "double", cagesPer25m: false, // zawsze 1 klatka
    cage_weights: { egress: 1.0, count: 0.8, light_waste: 0.8, ends: 0.0, spread: 0.0 },
  },
  galeriowiec: {
    corridor_mode: "gallery", cagesPer25m: true,
    cage_weights: { egress: 1.0, count: 0.8, light_waste: 0.6, ends: 0.8, spread: 0.6 },
  },
  klatkowiec_narozny: {
    corridor_mode: "double", cagesPer25m: true,
    cage_weights: { egress: 1.0, count: 0.8, light_waste: 1.0, ends: 0.3, spread: 0.6 },
  },
  szeregowiec: {
    corridor_mode: "gallery", cagesPer25m: true,
    cage_weights: { egress: 1.0, count: 0.5, light_waste: 0.6, ends: 0.5, spread: 1.0 },
  },
};
```

- [ ] **Step 1:** In `applyTypologyPreset`, after the existing preset fetch, extend the `SET_CIRCULATION` patch: keep the existing `corridor_width_m`/`cage_size_m`/`place_cage` mapping and ADD `corridor_mode`, `num_cages` (from footprint bbox longer side: `Math.max(1, Math.ceil(longerSideM / 25))` when `cagesPer25m`, else 1 — compute from `state.footprint` bounds; when no footprint, keep current num_cages), `cage_weights` from the table, and `cage_iterations: state.iterationsCount` so the preset immediately uses the iterative engine on next "Rozmieść iteracyjnie".
- [ ] **Step 2:** Update `TYPOLOGY_LABELS` hover/description text (title attribute on options) to state what the preset actually sets, honestly (e.g. "Galeriowiec: korytarz przy elewacji, klatki co ~25 m").
- [ ] **Step 3:** tsc + commit.

```bash
git add frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: typology presets configure corridor mode, cage count and weight profiles for real"
```

---

### Task 11: Weryfikacja całości na żywo

**Files:** none.

- [ ] Full backend suite + tsc. Fresh servers (behavioral freshness check!).
- [ ] Live: L i U przez `/generate` (spójny korytarz, hard-valid winner); gallery mode na prostokącie (korytarz przy elewacji, mieszkania jednostronnie); preset "galeriowiec" ustawia mode+num_cages+wagi (sprawdź w request payload przeglądarki albo w state).
- [ ] Checklist dla usera: (1) L-obrys → korytarz przez narożnik jednym pasem, mieszkania w obu skrzydłach od korytarza do elewacji; (2) U analogicznie; (3) "Galeriowiec" → korytarz przy elewacji; (4) select "Pozycja klatki" zniknął, jest "Tryb korytarza"; (5) drag segmentu osi (całej linii) działa, węzły jak dotąd; (6) "Wyczyść mieszkania" zostawia komunikację; (7) regresja: prostokąt wygląda jak przed zmianami.
- [ ] Ledger entry per repo practice.

---

## Poza zakresem (świadomie)

- **Klatkowiec sekcyjny / punktowiec bez korytarza** (mieszkania obsługiwane bezpośrednio z lobby klatki, 2-4 na piętro na sekcję): wymaga NOWEGO generatora podziału (klastry per klatka zamiast traktów) — osobny plan po akceptacji spine'u. `corridor_mode` jest już zaprojektowany tak, żeby przyjąć trzecią wartość ("point") bez zmian API.
- **Skośne ściany**: trakt slicing w lokalnym układzie segmentu spine (wektor kierunku zamiast osi x/y) — spine z tego planu jest do tego gotowy (segmenty niosą kierunek), zmiana dotknie tylko `_clip`/`_clip_area` w trakt_division. Osobny plan.
- **Solar jako trzeci cel Pareto**: bez zmian względem planu 2026-07-14 (punkt rozszerzenia `objectives_from_components`).
