# Corridor Centerline Editing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the corridor's silent, non-editable fill with an editable centerline (draggable vertices, colored green/red by distance-to-cage threshold) layered on top of the existing filled rectangle.

**Architecture:** Backend `services/circulation.py` gains centerline computation (per-zone axis → nearest-endpoint joining → single/double-loaded classification → arc-length distance to nearest cage) exposed on `CirculationResult.centerline` and through the existing `POST /layout/circulation` endpoint. A new `POST /layout/circulation/reshape` endpoint recomputes geometry + classification from a user-edited centerline. Frontend renders the centerline as a colored `Line` overlay and adds a new `edit-corridor-centerline` mode with draggable vertex `Circle`s (client-side move during drag, single reshape request on drag end).

**Tech Stack:** FastAPI + Shapely 2.x (backend), Next.js/TypeScript + react-konva (frontend), pytest (backend tests).

## Global Constraints

- Single-loaded max distance to cage: 20.0m (was 30.0m — user correction, see spec §7).
- Double-loaded max distance to cage: 40.0m (new).
- Existing `MIN_ROOM_WIDTH_M = 2.4` (wt_validation.py) is the probe depth used to classify single vs. double loading — do not introduce a second constant for this.
- Existing WT §58 ust.4 rule (`_rule_max_corridor_distance`, Dijkstra-based apartment→cage distance) is explicitly OUT OF SCOPE for single/double classification in this plan — it only picks up the corrected 20.0m default. Do not touch its Dijkstra logic.
- No straight-skeleton / medial-axis — nearest-endpoint segment joining only.
- Every draggable Konva node in this codebase requires `e.cancelBubble = true` on both `onDragStart` and `onDragEnd` (Stage-level pan/centering bug, fixed earlier this session — see `CanvasEditor.tsx`'s existing 4 draggable elements for the pattern).
- Centerline recompute happens only on drag end (one request), never during drag (client-only visual move).

---

## File Structure

**Backend:**
- Modify `backend/services/circulation.py` — add `_corridor_centerline()`, `_join_centerlines()`, `_classify_segment_loading()`, `_distances_along_centerline()`, `CorridorCenterlineSegment` dataclass; extend `CirculationResult` with `centerline` field; wire into `place_circulation()`.
- Modify `backend/services/wt_validation.py` — `DEFAULT_MAX_CORRIDOR_DISTANCE_M` 30.0 → 20.0, docstring clarifies "single-loaded".
- Modify `backend/api/v1/endpoints/layout.py` — serialize `centerline` on `CirculationResponse`; add `ReshapeCirculationRequest`/`ReshapeCirculationResponse` models + `POST /circulation/reshape` endpoint.
- Test `backend/tests/test_circulation.py` — new tests for the 4 new functions + `place_circulation()`'s `centerline` field.
- Test `backend/tests/test_layout_circulation_endpoint.py` — `centerline` present in `/circulation` response.
- Test `backend/tests/test_wt_validation.py` — default-value regression test for the 20.0m correction.
- New test `backend/tests/test_layout_circulation_reshape_endpoint.py` — reshape endpoint contract.

**Frontend:**
- Modify `frontend/app/lib/api.ts` — `CorridorCenterlineSegment` type, `centerline` field on `CirculationResponse`, `reshapeCirculation()` function.
- Modify `frontend/app/state/SessionContext.tsx` — `EditorMode` gains `"edit-corridor-centerline"`; new `RESHAPE_CIRCULATION` action + reducer case; new `runReshapeCirculation()` callback.
- Modify `frontend/app/CanvasEditor.tsx` — render centerline `Line` overlay (both preview and edit modes); add draggable vertex `Circle`s for `edit-corridor-centerline` mode.
- Modify `frontend/app/components/CirculationSection.tsx` — new toggle button for the `edit-corridor-centerline` mode.

---

### Task 1: Backend — `_corridor_centerline()` per-zone axis extraction

**Files:**
- Modify: `backend/services/circulation.py`
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: nothing new (uses `Polygon.bounds`, mirrors `_build_corridor()`'s existing `mid_x`/`mid_y` alignment logic at circulation.py:159-193).
- Produces: `_corridor_centerline(polygon: Polygon, width: float, cage_polygon: Polygon | None = None) -> tuple[tuple[float, float], tuple[float, float]] | None` — consumed by Task 3 (`place_circulation`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_circulation.py — add at end of file

def test_corridor_centerline_horizontal_zone():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (20, 0), (20, 4), (0, 4)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    assert abs(y1 - 2.0) < 1e-6 and abs(y2 - 2.0) < 1e-6  # centered on mid_y
    assert {round(x1), round(x2)} == {0, 20}


def test_corridor_centerline_vertical_zone():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (4, 0), (4, 20), (0, 20)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    assert abs(x1 - 2.0) < 1e-6 and abs(x2 - 2.0) < 1e-6  # centered on mid_x
    assert {round(y1), round(y2)} == {0, 20}


def test_corridor_centerline_aligns_to_cage():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    # centroid.y = 5.8 -- deliberately close to maxy(6) so the clamp
    # (mid_y <= maxy - half) actually engages instead of just passing
    # cage_y through unclamped.
    cage = Polygon([(0, 5.6), (2, 5.6), (2, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=1.5, cage_polygon=cage)
    assert seg is not None
    (_, y1), (_, y2) = seg
    assert abs(y1 - 5.25) < 1e-6 and abs(y2 - 5.25) < 1e-6  # mid_y clamped to maxy(6) - half(0.75)


def test_corridor_centerline_none_when_too_narrow():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (1.0, 0), (1.0, 20), (0, 20)])  # width 1.0m < corridor 1.5m
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k corridor_centerline -v`
Expected: FAIL with `ImportError: cannot import name '_corridor_centerline'`

- [ ] **Step 3: Implement `_corridor_centerline()`**

Add to `backend/services/circulation.py`, directly after `_build_corridor()` (after line 193):

```python
def _corridor_centerline(
    polygon: Polygon, width: float, cage_polygon: Polygon | None = None
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Oś korytarza strefy jako 2-punktowy odcinek — ta sama oś, ten sam
    warunek wyrównania do klatki co _build_corridor(), tylko zwrócona jako
    linia zamiast wypełnionego prostokąta (spec §3.1). None gdy korytarz
    o zadanej szerokości nie mieści się w strefie."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return None
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny
    half = width / 2.0

    if w >= h:
        if width >= h:
            return None
        if cage_polygon:
            cage_y = cage_polygon.centroid.y
            mid_y = max(miny + half, min(maxy - half, cage_y))
        else:
            mid_y = (miny + maxy) / 2.0
        return ((minx, mid_y), (maxx, mid_y))
    else:
        if width >= w:
            return None
        if cage_polygon:
            cage_x = cage_polygon.centroid.x
            mid_x = max(minx + half, min(maxx - half, cage_x))
        else:
            mid_x = (minx + maxx) / 2.0
        return ((mid_x, miny), (mid_x, maxy))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k corridor_centerline -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: add per-zone corridor centerline extraction"
```

---

### Task 2: Backend — `_join_centerlines()` nearest-endpoint joining

**Files:**
- Modify: `backend/services/circulation.py`
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: list of segments in the shape produced by Task 1's `_corridor_centerline()`.
- Produces: `_join_centerlines(segments: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[tuple[float, float]]` — consumed by Task 4 (`place_circulation`) and Task 3 (`_distances_along_centerline` operates on its output).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_circulation.py — add at end of file

def test_join_centerlines_single_segment():
    from services.circulation import _join_centerlines

    path = _join_centerlines([((0, 0), (10, 0))])
    assert path == [(0, 0), (10, 0)]


def test_join_centerlines_two_segments_already_touching():
    from services.circulation import _join_centerlines

    segs = [((0, 0), (10, 0)), ((10, 0), (10, 10))]
    path = _join_centerlines(segs)
    assert path == [(0, 0), (10, 0), (10, 10)]


def test_join_centerlines_reversed_segment_orientation():
    from services.circulation import _join_centerlines

    # Second segment's endpoints are listed far-then-near relative to path end.
    segs = [((0, 0), (10, 0)), ((10, 10), (10, 0))]
    path = _join_centerlines(segs)
    assert path == [(0, 0), (10, 0), (10, 10)]


def test_join_centerlines_three_segments_picks_nearest_each_step():
    from services.circulation import _join_centerlines

    # Start at (0,0)-(10,0). Nearest next endpoint to (10,0) is (10,0) of
    # the THIRD segment listed (not the second) -- verifies nearest-search,
    # not list order.
    segs = [
        ((0, 0), (10, 0)),
        ((20, 20), (30, 20)),  # far away, should be picked last
        ((10, 0), (10, 10)),   # near, should be picked second
    ]
    path = _join_centerlines(segs)
    assert path[0] == (0, 0)
    assert path[1] == (10, 0)
    assert path[2] == (10, 10)
    assert path[-1] in ((20, 20), (30, 20))


def test_join_centerlines_empty_list():
    from services.circulation import _join_centerlines

    assert _join_centerlines([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k join_centerlines -v`
Expected: FAIL with `ImportError: cannot import name '_join_centerlines'`

- [ ] **Step 3: Implement `_join_centerlines()`**

Add to `backend/services/circulation.py`, directly after `_corridor_centerline()`:

```python
def _join_centerlines(
    segments: list[tuple[tuple[float, float], tuple[float, float]]]
) -> list[tuple[float, float]]:
    """Łączy odcinki centerline sąsiednich stref w jedną łamaną (spec §3.2).
    Zachłanny nearest-neighbor: zaczyna od pierwszego segmentu, za każdym
    razem dołącza segment, którego bliższy koniec leży najbliżej ostatniego
    punktu ścieżki. NIE straight-skeleton (odrzucone jako zbyt kruche dla
    wklęsłych kształtów w tej sesji) -- niepotrzebne tu, bo rectangle_
    decompose() już daje prawie-prostokątne strefy."""
    if not segments:
        return []

    remaining = list(segments[1:])
    path: list[tuple[float, float]] = [segments[0][0], segments[0][1]]

    while remaining:
        last = path[-1]
        best_idx = None
        best_dist = None
        best_reversed = False
        for i, (p1, p2) in enumerate(remaining):
            d1 = math.hypot(p1[0] - last[0], p1[1] - last[1])
            d2 = math.hypot(p2[0] - last[0], p2[1] - last[1])
            if best_dist is None or d1 < best_dist:
                best_dist, best_idx, best_reversed = d1, i, False
            if d2 < best_dist:
                best_dist, best_idx, best_reversed = d2, i, True
        p1, p2 = remaining.pop(best_idx)
        if best_reversed:
            path.append(p2)
            path.append(p1)
        else:
            path.append(p1)
            path.append(p2)

    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k join_centerlines -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: join per-zone corridor centerlines into one path"
```

---

### Task 3: Backend — single/double-loaded classification + arc-length distance

**Files:**
- Modify: `backend/services/circulation.py`
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: `MIN_ROOM_WIDTH_M` from `services.wt_validation` (existing constant, value 2.4).
- Produces:
  - `_classify_segment_loading(zone_polygon: Polygon, segment: tuple[tuple[float, float], tuple[float, float]], corridor_width: float) -> str` (`"single"` or `"double"`) — consumed by Task 4.
  - `_distances_along_centerline(path: list[tuple[float, float]], cage_points: list[tuple[float, float]]) -> list[float]` — consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_circulation.py — add at end of file

def test_classify_segment_loading_double_when_room_both_sides():
    from services.circulation import _classify_segment_loading

    # Wide zone: corridor in the middle, >= MIN_ROOM_WIDTH_M (2.4) of
    # room depth available on both sides.
    zone = Polygon([(0, 0), (20, 0), (20, 8), (0, 8)])
    segment = ((0, 4), (20, 4))  # horizontal centerline at mid-height
    loading = _classify_segment_loading(zone, segment, corridor_width=1.5)
    assert loading == "double"


def test_classify_segment_loading_single_when_room_one_side_only():
    from services.circulation import _classify_segment_loading

    # Corridor runs along one long edge -- no room depth on the far side.
    zone = Polygon([(0, 0), (20, 0), (20, 3.5), (0, 3.5)])
    segment = ((0, 0.75), (20, 0.75))  # centerline hugging the y=0 edge
    loading = _classify_segment_loading(zone, segment, corridor_width=1.5)
    assert loading == "single"


def test_distances_along_centerline_linear_path_one_cage():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0), (10, 10)]
    cage_points = [(0, 0)]
    distances = _distances_along_centerline(path, cage_points)
    assert distances == [0.0, 10.0, 20.0]


def test_distances_along_centerline_no_cages_returns_inf():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0)]
    distances = _distances_along_centerline(path, [])
    assert distances == [float("inf"), float("inf")]


def test_distances_along_centerline_picks_nearest_cage():
    from services.circulation import _distances_along_centerline

    path = [(0, 0), (10, 0), (20, 0)]
    cage_points = [(0, 0), (20, 0)]
    distances = _distances_along_centerline(path, cage_points)
    assert distances == [0.0, 10.0, 0.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k "classify_segment_loading or distances_along_centerline" -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement both functions**

Add to `backend/services/circulation.py`, directly after `_join_centerlines()`. First update the shapely import at the top of the file (line 12) to also bring in `LineString` and `Point` (both used below, and `Point` is reused again in Task 4):

```python
from shapely.geometry import LineString, Point, Polygon
```

Then add the two functions:

```python
def _classify_segment_loading(
    zone_polygon: Polygon, segment: tuple[tuple[float, float], tuple[float, float]], corridor_width: float
) -> str:
    """"single" albo "double" (spec §3.3) -- geometryczne, NIE zależne od
    danych Etapu 2 (mieszkania jeszcze nie istnieją, gdy place_circulation()
    działa). Sonduje obie strony odcinka na głębokość MIN_ROOM_WIDTH_M
    (wt_validation.py) poza pasem korytarza."""
    from services.wt_validation import MIN_ROOM_WIDTH_M

    (x1, y1), (x2, y2) = segment
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return "single"
    ux, uy = dx / length, dy / length
    normal_x, normal_y = -uy, ux

    half_corridor = corridor_width / 2.0
    depth = MIN_ROOM_WIDTH_M
    sides_with_room = 0
    for sign in (1.0, -1.0):
        near = (
            x1 + normal_x * half_corridor * sign,
            y1 + normal_y * half_corridor * sign,
        )
        far = (
            near[0] + normal_x * depth * sign,
            near[1] + normal_y * depth * sign,
        )
        far2 = (
            x2 + normal_x * (half_corridor + depth) * sign,
            y2 + normal_y * (half_corridor + depth) * sign,
        )
        near2 = (
            x2 + normal_x * half_corridor * sign,
            y2 + normal_y * half_corridor * sign,
        )
        probe = Polygon([near, far, far2, near2])
        if not probe.is_valid or probe.area < 1e-9:
            continue
        clipped = probe.intersection(zone_polygon)
        if clipped.area > probe.area * 0.9:
            sides_with_room += 1

    return "double" if sides_with_room >= 2 else "single"


def _distances_along_centerline(
    path: list[tuple[float, float]], cage_points: list[tuple[float, float]]
) -> list[float]:
    """Odległość (długość łuku wzdłuż `path`) każdego wierzchołka `path` do
    najbliższego punktu w `cage_points`, rzutowanego na najbliższy punkt na
    `path` (spec §3.4). float('inf') dla wszystkich gdy `cage_points` puste."""
    if len(path) < 2:
        return [float("inf")] * len(path)

    cumulative = [0.0]
    for i in range(1, len(path)):
        p1, p2 = path[i - 1], path[i]
        cumulative.append(cumulative[-1] + math.hypot(p2[0] - p1[0], p2[1] - p1[1]))

    if not cage_points:
        return [float("inf")] * len(path)

    line = LineString(path)
    cage_arc_positions = [line.project(Point(cp)) for cp in cage_points]

    result = []
    for i, point in enumerate(path):
        vertex_arc = cumulative[i]
        result.append(min(abs(vertex_arc - cage_arc) for cage_arc in cage_arc_positions))
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k "classify_segment_loading or distances_along_centerline" -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: add corridor loading classification and arc-length distance"
```

---

### Task 4: Backend — wire centerline into `place_circulation()` + `CorridorCenterlineSegment`

**Files:**
- Modify: `backend/services/circulation.py`
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: `_corridor_centerline` (Task 1), `_join_centerlines` (Task 2), `_classify_segment_loading`/`_distances_along_centerline` (Task 3).
- Produces:
  - `CorridorCenterlineSegment` dataclass with fields `points`, `loading`, `distance_start_m`, `distance_end_m`, `max_distance_m`, `exceeds_max` — consumed by Task 5 (endpoint serialization) and by the frontend types in Task 8.
  - `CirculationResult.centerline: list[CorridorCenterlineSegment]` — consumed by Task 5.
  - `CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0`, `CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M = 40.0` module constants.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_circulation.py — add at end of file

def test_place_circulation_populates_centerline():
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
    )
    assert len(result.centerline) >= 1
    seg = result.centerline[0]
    assert seg.loading in ("single", "double")
    assert seg.max_distance_m in (20.0, 40.0)
    assert isinstance(seg.exceeds_max, bool)


def test_place_circulation_centerline_exceeds_max_on_long_single_loaded_building():
    from services.circulation import place_circulation

    # 50m long, 3m deep -> definitely single-loaded, far end exceeds 20m.
    footprint = Polygon([(0, 0), (50, 0), (50, 3), (0, 3)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.4,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.0,
        cage_position="1a",
    )
    assert any(seg.loading == "single" for seg in result.centerline)
    assert any(seg.exceeds_max for seg in result.centerline)


def test_place_circulation_no_cage_gives_inf_distance_not_crash():
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    result = place_circulation(
        footprint,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=False,
        cage_size_m=2.5,
        cage_position="auto",
    )
    assert len(result.centerline) >= 1
    assert all(seg.exceeds_max is False for seg in result.centerline)  # inf never "exceeds" a real building
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k "populates_centerline or exceeds_max_on_long or no_cage_gives_inf" -v`
Expected: FAIL — `CirculationResult` has no attribute `centerline` (AttributeError) or empty list assertion failure.

- [ ] **Step 3: Implement**

In `backend/services/circulation.py`, add the two module constants near the top, directly after `CAGE_POSITION_MODES`'s docstring (after line 19):

```python
CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0
CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M = 40.0
"""Progi kolorowania linii środkowej korytarza (spec §7) -- świadomie
osobne od wt_validation.py's DEFAULT_MAX_CORRIDOR_DISTANCE_M (inny moduł,
inny punkt cyklu życia layoutu; duplikacja dwóch float jest tańsza niż
sprzężenie Etapu 1 z walidacją post-Etap-2)."""
```

Add the dataclass, directly after `CirculationResult` (after line 222, before `def place_circulation`):

```python
@dataclass
class CorridorCenterlineSegment:
    """Jeden odcinek połączonej linii środkowej korytarza (spec §3.5)."""

    points: tuple[tuple[float, float], tuple[float, float]]
    loading: str  # "single" | "double"
    distance_start_m: float
    distance_end_m: float
    max_distance_m: float
    exceeds_max: bool
```

Add the new field to `CirculationResult` (modify the dataclass at lines 212-222):

```python
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
    centerline: list[CorridorCenterlineSegment] = field(default_factory=list)
```

In `place_circulation()`, after the existing loop that builds `remainder_parts` (after line 300's `remainder = unary_union(...)` line, before the final `return CirculationResult(...)`), add:

```python
    raw_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        local_cage = local_cages.get(i)
        seg = _corridor_centerline(zone.polygon, corridor_width_m, local_cage)
        if seg is not None:
            raw_segments.append(seg)

    centerline_path = _join_centerlines(raw_segments)
    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]
    arc_distances = _distances_along_centerline(centerline_path, cage_points)

    centerline: list[CorridorCenterlineSegment] = []
    for i in range(len(centerline_path) - 1):
        p1, p2 = centerline_path[i], centerline_path[i + 1]
        midpoint = Point((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        containing_zone = next(
            (z.polygon for z in zones if z.polygon.buffer(1e-6).contains(midpoint)),
            footprint,
        )
        loading = _classify_segment_loading(containing_zone, (p1, p2), corridor_width_m)
        max_dist = (
            CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M
            if loading == "double"
            else CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M
        )
        d_start, d_end = arc_distances[i], arc_distances[i + 1]
        centerline.append(
            CorridorCenterlineSegment(
                points=(p1, p2),
                loading=loading,
                distance_start_m=d_start,
                distance_end_m=d_end,
                max_distance_m=max_dist,
                exceeds_max=(max(d_start, d_end) > max_dist) if math.isfinite(max(d_start, d_end)) else False,
            )
        )
```

And update the final `return` statement (line 302-307) to include the new field:

```python
    return CirculationResult(
        zones=zones,
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
    )
```

Note: the `containing_zone` lookup above is a best-effort fallback (used only for classification, not geometry) — since `centerline_path` is already joined across zones, a segment's exact originating zone isn't always trivially recoverable after joining. Using `footprint` as the fallback is safe because `_classify_segment_loading`'s probe-intersection check degrades gracefully (probes clipped against the full footprint still correctly detect "no room on this side" for exterior-hugging segments).

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -v`
Expected: all tests in the file pass (previous tasks' tests + these 3)

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all tests pass (127 previous + new ones from Tasks 1-4)

- [ ] **Step 6: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: compute corridor centerline with loading classification and distance thresholds"
```

---

### Task 5: Backend — correct `DEFAULT_MAX_CORRIDOR_DISTANCE_M` to 20.0

**Files:**
- Modify: `backend/services/wt_validation.py:41`
- Test: `backend/tests/test_wt_validation.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `DEFAULT_MAX_CORRIDOR_DISTANCE_M = 20.0` (was `30.0`) — no other task depends on this value directly (existing tests all pass an explicit override).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wt_validation.py — add at end of file

def test_default_max_corridor_distance_is_20m():
    """Regression for the 2026-07-03 domain correction: WT §58 ust.4
    single-loaded threshold is 20m, not 30m (see
    docs/superpowers/specs/2026-07-03-corridor-centerline-editing-design.md
    §7). All other tests in this file pass an explicit
    max_corridor_distance_m override, so this is the only place the actual
    default value is pinned."""
    from services.wt_validation import DEFAULT_MAX_CORRIDOR_DISTANCE_M

    assert DEFAULT_MAX_CORRIDOR_DISTANCE_M == 20.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py -k default_max_corridor_distance -v`
Expected: FAIL — `assert 30.0 == 20.0`

- [ ] **Step 3: Fix the constant**

In `backend/services/wt_validation.py`, change line 41:

```python
DEFAULT_MAX_CORRIDOR_DISTANCE_M = 20.0  # §58 ust. 4 — komunikacja jednostronna (single-loaded); patrz spec 2026-07-03 §7 dla wartości dwustronnej (40.0, tylko w circulation.py -- ta reguła nie klasyfikuje jedno/dwutraktowo, patrz spec §7 "świadomie poza zakresem")
```

- [ ] **Step 4: Run test to verify it passes, then run the full wt_validation suite for regressions**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py -v`
Expected: all pass (the new test + all existing ones, which use explicit overrides so are unaffected)

- [ ] **Step 5: Commit**

```bash
git add backend/services/wt_validation.py backend/tests/test_wt_validation.py
git commit -m "fix: correct WT §58 ust.4 single-loaded corridor distance from 30m to 20m"
```

---

### Task 6: Backend — serialize `centerline` on `POST /layout/circulation`

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Test: `backend/tests/test_layout_circulation_endpoint.py`

**Interfaces:**
- Consumes: `CirculationResult.centerline` (Task 4), `CorridorCenterlineSegment` (Task 4).
- Produces: `CirculationResponse.centerline: list[dict]` (JSON shape: `{"points": [[x,y],[x,y]], "loading": str, "distance_start_m": float, "distance_end_m": float, "max_distance_m": float, "exceeds_max": bool}`) — consumed by Task 8 (frontend types).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_layout_circulation_endpoint.py — add at end of file

def test_circulation_endpoint_includes_centerline():
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
    assert len(body["centerline"]) >= 1
    seg = body["centerline"][0]
    assert len(seg["points"]) == 2
    assert seg["loading"] in ("single", "double")
    assert seg["max_distance_m"] in (20.0, 40.0)
    assert isinstance(seg["exceeds_max"], bool)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_layout_circulation_endpoint.py -k includes_centerline -v`
Expected: FAIL — `KeyError: 'centerline'`

- [ ] **Step 3: Implement**

In `backend/api/v1/endpoints/layout.py`, add a serializer helper and a field to `CirculationResponse`. First, add the model field (modify the `CirculationResponse` class at lines 191-194):

```python
class CenterlineSegmentResult(BaseModel):
    points: list[list[float]]
    loading: str
    distance_start_m: float
    distance_end_m: float
    max_distance_m: float
    exceeds_max: bool


class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
```

Add a shared serializer function, directly after `_decompose_to_polygons` (after line 188):

```python
def _serialize_centerline(segments) -> list["CenterlineSegmentResult"]:
    return [
        CenterlineSegmentResult(
            points=[list(seg.points[0]), list(seg.points[1])],
            loading=seg.loading,
            distance_start_m=seg.distance_start_m,
            distance_end_m=seg.distance_end_m,
            max_distance_m=seg.max_distance_m,
            exceeds_max=seg.exceeds_max,
        )
        for seg in segments
    ]
```

Update `place_circulation_endpoint`'s return statement (lines 221-229) to include it:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
    )
```

`distance_start_m`/`distance_end_m` may be `float('inf')` when there's no cage — Pydantic/FastAPI serializes Python `inf` as JSON `Infinity` by default (not strict JSON, but consistent with how this codebase already returns floats; the frontend only compares `exceeds_max`, a plain bool, so this is not a problem in practice). No special-casing needed.

- [ ] **Step 4: Run test to verify it passes, then run the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_layout_circulation_endpoint.py
git commit -m "feat: expose corridor centerline on /layout/circulation response"
```

---

### Task 7: Backend — `POST /layout/circulation/reshape` endpoint

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Modify: `backend/services/circulation.py` (new `reshape_circulation` function)
- Test: New `backend/tests/test_layout_circulation_reshape_endpoint.py`

**Interfaces:**
- Consumes: `_classify_segment_loading`, `_distances_along_centerline` (Task 3), `CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M`/`_DOUBLE_LOADED_M` (Task 4), `CorridorCenterlineSegment` (Task 4), `_serialize_centerline` (Task 6).
- Produces: `POST /api/v1/layout/circulation/reshape` — consumed by Task 9 (frontend `reshapeCirculation()`).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_layout_circulation_reshape_endpoint.py (new file)

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def _base_request(centerline_points, corridor_width_m=1.5):
    return {
        "footprint": [[0, 0], [30, 0], [30, 6], [0, 6]],
        "centerline": [{"points": [list(p1), list(p2)]} for p1, p2 in centerline_points],
        "corridor_width_m": corridor_width_m,
        "cage_geometries": [
            {
                "type": "Polygon",
                "coordinates": [[[0, 0], [2, 0], [2, 6], [0, 6], [0, 0]]],
            }
        ],
    }


def test_reshape_endpoint_returns_geometry_and_centerline():
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 3), (30, 3))]),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["circulation_geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert body["remainder"]["type"] in ("Polygon", "MultiPolygon")
    assert len(body["centerline"]) == 1
    assert body["centerline"][0]["loading"] in ("single", "double")


def test_reshape_endpoint_flags_exceeds_max_for_long_edited_line():
    # Edited line stretches the single-loaded segment past the 20m threshold.
    response = client.post(
        "/api/v1/layout/circulation/reshape",
        json=_base_request([((2, 0.75), (30, 0.75))], corridor_width_m=1.5),
    )
    assert response.status_code == 200
    body = response.json()
    assert any(seg["exceeds_max"] for seg in body["centerline"])


def test_reshape_endpoint_rejects_empty_centerline():
    request_body = _base_request([((2, 3), (30, 3))])
    request_body["centerline"] = []
    response = client.post("/api/v1/layout/circulation/reshape", json=request_body)
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_layout_circulation_reshape_endpoint.py -v`
Expected: FAIL with 404 (endpoint doesn't exist yet)

- [ ] **Step 3: Implement `reshape_circulation()` service function**

Add to `backend/services/circulation.py`, at the end of the file:

```python
def reshape_circulation(
    footprint: Polygon,
    centerline_points: list[tuple[tuple[float, float], tuple[float, float]]],
    corridor_width_m: float,
    cage_polygons: list[Polygon],
) -> CirculationResult:
    """Przelicza geometrię korytarza + klasyfikację/odległości segmentów po
    edycji linii środkowej przez użytkownika (spec §3.6). Buduje geometrię
    jako bufor (cap_style="flat") wokół każdego edytowanego odcinka, zamiast
    ponownie dzielić footprint na strefy -- edytowana linia już nie jest
    przywiązana do rectangle_decompose()'s stref."""
    half = corridor_width_m / 2.0
    buffered_parts = [
        LineString([p1, p2]).buffer(half, cap_style="flat")
        for p1, p2 in centerline_points
    ]
    circulation_geom = unary_union(buffered_parts).intersection(footprint)
    circulation_geom = unary_union([circulation_geom] + cage_polygons)

    remainder = footprint.difference(circulation_geom)

    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]

    centerline: list[CorridorCenterlineSegment] = []
    for p1, p2 in centerline_points:
        arc_distances = _distances_along_centerline([p1, p2], cage_points)
        loading = _classify_segment_loading(footprint, (p1, p2), corridor_width_m)
        max_dist = (
            CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M
            if loading == "double"
            else CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M
        )
        d_start, d_end = arc_distances[0], arc_distances[1]
        centerline.append(
            CorridorCenterlineSegment(
                points=(p1, p2),
                loading=loading,
                distance_start_m=d_start,
                distance_end_m=d_end,
                max_distance_m=max_dist,
                exceeds_max=(max(d_start, d_end) > max_dist) if math.isfinite(max(d_start, d_end)) else False,
            )
        )

    return CirculationResult(
        zones=[],
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
    )
```

`LineString` and `Point` are already imported at module level from Task 3's Step 3 change — no new import needed here.

- [ ] **Step 4: Add the endpoint**

In `backend/api/v1/endpoints/layout.py`, add at the end of the file:

```python
class ReshapeSegmentInput(BaseModel):
    points: list[list[float]] = Field(..., min_length=2, max_length=2)


class ReshapeCirculationRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    centerline: list[ReshapeSegmentInput] = Field(..., min_length=1)
    corridor_width_m: float = Field(..., gt=0)
    cage_geometries: list[dict] = Field(default_factory=list)


class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []


@router.post("/circulation/reshape", response_model=ReshapeCirculationResponse)
def reshape_circulation_endpoint(request: ReshapeCirculationRequest):
    """Przelicza korytarz po edycji linii środkowej przez użytkownika (F2-04-bis)."""
    from services.circulation import reshape_circulation

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    centerline_points = [
        ((seg.points[0][0], seg.points[0][1]), (seg.points[1][0], seg.points[1][1]))
        for seg in request.centerline
    ]
    cage_polygons = [_shape(g) for g in request.cage_geometries]

    result = reshape_circulation(footprint, centerline_points, request.corridor_width_m, cage_polygons)

    return ReshapeCirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_layout_circulation_reshape_endpoint.py -v`
Expected: 3 passed

- [ ] **Step 6: Run the full backend suite for regressions**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add backend/services/circulation.py backend/api/v1/endpoints/layout.py backend/tests/test_layout_circulation_reshape_endpoint.py
git commit -m "feat: add /layout/circulation/reshape endpoint for edited centerlines"
```

---

### Task 8: Frontend — API types and client function

**Files:**
- Modify: `frontend/app/lib/api.ts`

**Interfaces:**
- Consumes: JSON shape from Task 6 (`CirculationResponse.centerline`) and Task 7 (`POST /circulation/reshape`).
- Produces: `CorridorCenterlineSegment` type, `CirculationResponse.centerline`, `reshapeCirculation()` function — consumed by Task 9 (SessionContext) and Task 10 (CanvasEditor).

- [ ] **Step 1: Add types and function**

In `frontend/app/lib/api.ts`, modify the existing `CirculationResponse` interface (lines 178-182):

```typescript
export interface CorridorCenterlineSegment {
  points: [Point, Point];
  loading: "single" | "double";
  distance_start_m: number;
  distance_end_m: number;
  max_distance_m: number;
  exceeds_max: boolean;
}

export interface CirculationResponse {
  circulation_geometry: GeoJsonPolygon | null;
  cage_geometries: GeoJsonPolygon[];
  remainder: GeoJsonPolygon; // może być Polygon lub MultiPolygon (patrz backend CirculationResult.remainder)
  centerline: CorridorCenterlineSegment[];
}
```

Add the reshape function directly after `placeCirculation()` (after line 189):

```typescript
export interface ReshapeCirculationRequest {
  footprint: Point[];
  centerline: { points: [Point, Point] }[];
  corridor_width_m: number;
  cage_geometries: GeoJsonPolygon[];
}

export interface ReshapeCirculationResponse {
  circulation_geometry: GeoJsonPolygon | null;
  remainder: GeoJsonPolygon;
  centerline: CorridorCenterlineSegment[];
}

export function reshapeCirculation(req: ReshapeCirculationRequest): Promise<ReshapeCirculationResponse> {
  return postJson("/layout/circulation/reshape", req);
}
```

- [ ] **Step 2: Verify the frontend typechecks**

Run: `cd frontend && npm run build 2>&1 | tail -50` (or `npx tsc --noEmit` if faster — check `frontend/package.json` scripts first)
Expected: no new TypeScript errors referencing `api.ts`

- [ ] **Step 3: Commit**

```bash
git add frontend/app/lib/api.ts
git commit -m "feat: add corridor centerline types and reshape API client function"
```

---

### Task 9: Frontend — SessionContext state and actions

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx`

**Interfaces:**
- Consumes: `api.CorridorCenterlineSegment`, `api.reshapeCirculation()` (Task 8).
- Produces: `EditorMode` includes `"edit-corridor-centerline"`; `runReshapeCirculation(points: Point2D[][]) => Promise<void>` on `SessionContextValue` — consumed by Task 10 (CanvasEditor) and Task 11 (CirculationSection).

- [ ] **Step 1: Extend `EditorMode`**

In `frontend/app/state/SessionContext.tsx`, modify line 8:

```typescript
export type EditorMode = "idle" | "draw" | "edit-vertices" | "edit-lines" | "edit-circulation" | "edit-corridor-centerline";
```

- [ ] **Step 2: Add the `RESHAPE_CIRCULATION` action type**

Modify the action union around line 145 (directly after `TRANSLATE_CIRCULATION`):

```typescript
  | { type: "TRANSLATE_CIRCULATION"; dx: number; dy: number }
  | { type: "RESHAPE_CIRCULATION"; result: api.ReshapeCirculationResponse }
```

- [ ] **Step 3: Add the reducer case**

In the reducer, directly after the `"TRANSLATE_CIRCULATION"` case (after line 273's closing `}`):

```typescript
    case "RESHAPE_CIRCULATION": {
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: {
          ...state.circulationResult,
          circulation_geometry: action.result.circulation_geometry,
          remainder: action.result.remainder,
          centerline: action.result.centerline,
        },
      };
    }
```

- [ ] **Step 4: Add `runReshapeCirculation` callback**

In `frontend/app/state/SessionContext.tsx`, directly after `runPlaceCirculation` (after line 490):

```typescript
  const runReshapeCirculation = useCallback(
    async (segments: [Point2D, Point2D][]) => {
      if (!state.footprint || !state.circulationResult) return;
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const result = await api.reshapeCirculation({
          footprint: footprintToPoints(state.footprint),
          centerline: segments.map(([p1, p2]) => ({
            points: [
              [p1.x, p1.y],
              [p2.x, p2.y],
            ] as [api.Point, api.Point],
          })),
          corridor_width_m: state.circulation.corridor_width_m,
          cage_geometries: state.circulationResult.cage_geometries,
        });
        dispatch({ type: "RESHAPE_CIRCULATION", result });
        dispatch({ type: "SET_ERROR", error: null });
      } catch (err) {
        dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [state.footprint, state.circulationResult, state.circulation.corridor_width_m]
  );
```

- [ ] **Step 5: Register in `SessionContextValue` interface, `useMemo` value, and deps array**

Add to the interface (directly after `runSubdivideUnits: () => Promise<void>;` around line 329):

```typescript
  runReshapeCirculation: (segments: [Point2D, Point2D][]) => Promise<void>;
```

Add to the `useMemo` value object (directly after `runSubdivideUnits,` around line 701):

```typescript
      runReshapeCirculation,
```

Add to the deps array (directly after `runSubdivideUnits,` around line 730):

```typescript
      runReshapeCirculation,
```

- [ ] **Step 6: Verify the frontend typechecks**

Run: `cd frontend && npx tsc --noEmit 2>&1 | tail -50`
Expected: no new TypeScript errors referencing `SessionContext.tsx`

- [ ] **Step 7: Commit**

```bash
git add frontend/app/state/SessionContext.tsx
git commit -m "feat: add edit-corridor-centerline mode and reshape action to session state"
```

---

### Task 10: Frontend — render centerline overlay + draggable vertices in `CanvasEditor.tsx`

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx`

**Interfaces:**
- Consumes: `state.circulationResult.centerline` (Task 9), `runReshapeCirculation` (Task 9).
- Produces: visual centerline overlay + `edit-corridor-centerline` drag mode — no other task depends on this.

- [ ] **Step 1: Render the colored centerline overlay**

In `frontend/app/CanvasEditor.tsx`, directly after the existing cage-rendering block (after line 512, before the `edit-circulation` Group at line 514), add:

```tsx
          {/* Linia środkowa korytarza — kolor wg progu odległości do klatki (F2-04-bis) */}
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke={seg.exceeds_max ? "#ef4444" : "#22c55e"}
              strokeWidth={3 / scale}
              listening={false}
            />
          ))}
```

- [ ] **Step 2: Add draggable centerline vertices for the new edit mode**

Directly after the block from Step 1, add:

```tsx
          {/* Wierzchołki linii korytarza — edytowalne (F2-04-bis) */}
          {state.mode === "edit-corridor-centerline" &&
            state.circulationResult?.centerline &&
            (() => {
              // Flatten segment endpoints into a de-duplicated vertex list so shared
              // endpoints between adjacent segments render (and drag) as one point.
              const verts: { x: number; y: number }[] = [];
              for (const seg of state.circulationResult.centerline) {
                for (const [x, y] of seg.points) {
                  if (!verts.some((v) => Math.abs(v.x - x) < 1e-6 && Math.abs(v.y - y) < 1e-6)) {
                    verts.push({ x, y });
                  }
                }
              }
              return verts.map((v, i) => (
                <Circle
                  key={`centerline-vertex-${i}`}
                  x={v.x * METER_PX}
                  y={-v.y * METER_PX}
                  radius={6 / scale}
                  fill="#ffffff"
                  stroke="#22c55e"
                  strokeWidth={2 / scale}
                  draggable
                  onDragStart={(e) => {
                    e.cancelBubble = true;
                  }}
                  onDragMove={(e) => {
                    const node = e.target;
                    const snapped = worldToMeters(
                      node.x() * scale + position.x,
                      node.y() * scale + position.y
                    );
                    node.x(snapped.x * METER_PX);
                    node.y(-snapped.y * METER_PX);
                  }}
                  onDragEnd={(e) => {
                    // Same Konva bubbling issue as every other draggable node in this
                    // Stage (footprint vertices, shared lines, edit-circulation Group)
                    // — without cancelBubble the Stage's own onDragEnd reads this
                    // node's raw coordinates and snaps the whole pannable view.
                    e.cancelBubble = true;
                    const snapped = worldToMeters(
                      e.target.x() * scale + position.x,
                      e.target.y() * scale + position.y
                    );
                    const movedFrom = v;
                    const newSegments: [Point2D, Point2D][] = state.circulationResult!.centerline.map((seg) => {
                      const [p1, p2] = seg.points;
                      const newP1 =
                        Math.abs(p1[0] - movedFrom.x) < 1e-6 && Math.abs(p1[1] - movedFrom.y) < 1e-6
                          ? { x: snapped.x, y: snapped.y }
                          : { x: p1[0], y: p1[1] };
                      const newP2 =
                        Math.abs(p2[0] - movedFrom.x) < 1e-6 && Math.abs(p2[1] - movedFrom.y) < 1e-6
                          ? { x: snapped.x, y: snapped.y }
                          : { x: p2[0], y: p2[1] };
                      return [newP1, newP2];
                    });
                    void runReshapeCirculation(newSegments);
                  }}
                />
              ));
            })()}
```

- [ ] **Step 3: Pull `runReshapeCirculation` from the session hook**

Find the existing `useSession()` destructuring near the top of the `CanvasEditor` component (search for `runPlaceCirculation` or `updateVertex` in the destructured list) and add `runReshapeCirculation` to it.

- [ ] **Step 4: Update the cursor logic to cover the new mode**

Modify the `cursor` ternary (lines 343-352) to include the new mode alongside `edit-lines`/`edit-circulation`:

```typescript
  const cursor =
    state.mode === "draw"
      ? "crosshair"
      : state.mode === "edit-vertices" || state.mode === "edit-corridor-centerline"
        ? "pointer"
        : state.mode === "edit-lines" || state.mode === "edit-circulation"
          ? "move"
          : isPanning
            ? "grabbing"
            : "grab";
```

- [ ] **Step 5: Manual verification with Playwright**

Start the dev servers (backend + frontend, per this project's existing dev workflow) and, using Playwright:
1. Draw a simple rectangular footprint.
2. Click "Umieść korytarz i klatkę" — verify a green (or red, if it exceeds threshold) centerline appears on top of the gray corridor fill.
3. Switch to the new centerline-edit mode toggle (added in Task 11) and drag a vertex — verify the line moves visually during drag and the color/geometry updates once after release (one network request, not one per frame).
4. Verify dragging a vertex does NOT re-center or jump the view (regression check for the Konva bubbling bug fixed earlier this session).

Take a screenshot and visually confirm all four points before marking this task done.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: render editable corridor centerline overlay on canvas"
```

---

### Task 11: Frontend — toggle button in `CirculationSection.tsx`

**Files:**
- Modify: `frontend/app/components/CirculationSection.tsx`

**Interfaces:**
- Consumes: `setMode` (existing), `"edit-corridor-centerline"` mode (Task 9).
- Produces: nothing consumed by later tasks — final UI wiring.

- [ ] **Step 1: Add the toggle button**

In `frontend/app/components/CirculationSection.tsx`, directly after the existing "Przesuń komunikację" button (after line 150, before the closing `</div>` at line 151), add:

```tsx
        <button
          onClick={() => setMode(state.mode === "edit-corridor-centerline" ? "idle" : "edit-corridor-centerline")}
          disabled={!state.circulationResult}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "edit-corridor-centerline"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.circulationResult ? "Wymaga umieszczenia korytarza/klatki" : "Przeciągnij punkty linii korytarza"}
        >
          <Move size={13} />
          Edytuj linię korytarza
        </button>
```

- [ ] **Step 2: Manual verification with Playwright**

With the dev server running, click the new "Edytuj linię korytarza" button and verify it toggles into the mode (visually highlighted, matching the existing "Przesuń komunikację" button's active-state style) and that draggable vertex circles from Task 10 appear on the canvas.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/components/CirculationSection.tsx
git commit -m "feat: add UI toggle for corridor centerline editing mode"
```

---

## Self-Review Notes

**Spec coverage:**
- §3.1 `_corridor_centerline()` → Task 1. §3.2 `_join_centerlines()` → Task 2. §3.3 `_classify_segment_loading()` → Task 3. §3.4 `_distances_along_centerline()` → Task 3. §3.5 `CorridorCenterlineSegment`/`CirculationResult.centerline` → Task 4. §3.6 reshape endpoint → Task 7. §4.1 rendering → Task 10. §4.2 dragging/reshape-on-release → Task 10. §4.3 session state → Task 9. §5 UI flow step 3 (new toggle) → Task 11. §7 threshold correction → Task 5 (existing constant) + Task 4 (new constants). §6 test plan → covered across Tasks 1-7's test steps + Task 10/11's manual Playwright checks.
- §8 risks (branching assumption, buffer cap-style deviation) are documented limitations, not required behavior — no task needed.

**Type consistency check:** `CorridorCenterlineSegment` fields (`points`, `loading`, `distance_start_m`, `distance_end_m`, `max_distance_m`, `exceeds_max`) are identical across Task 4 (Python dataclass), Task 6 (`CenterlineSegmentResult` Pydantic model), Task 7 (reshape response), and Task 8 (TypeScript interface) — verified name-for-name.

**Placeholder scan:** none found; Task 7 Step 3 contains an explicit note flagging and removing a scratch/dead code line introduced mid-derivation (not a placeholder — a correction instruction for the implementer, since the function was derived in two passes).
