# Cage/Corridor Placement Quality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `place_circulation()` supports placing 1–N staircase cages (one per zone, UI slider); the corridor centerline editor gains point insert (double-click a segment) and point removal (double-click a vertex, guarded so the last 2 points can't be removed); `corridor_width_m` is reinterpreted as clear (w świetle) width, matching the treatment `CAGE_WIDTH_M`/`CAGE_DEPTH_M` already got.

**Architecture:** Backend changes are additive and localized to `services/circulation.py` (new `num_cages` loop param, `NET_SHRINK_M`-grown corridor rectangles) plus one new `CirculationSpec` field threaded through the two existing `/layout/circulation` and `/layout/generate` call sites in `api/v1/endpoints/layout.py`. Frontend changes add a slider (mirrors the existing "Pozycja klatki" control pattern) and two new Konva `onDblClick` handlers reusing the existing `runReshapeCirculation()` plumbing — no new endpoints, no new dataclasses.

**Tech Stack:** Python 3 / FastAPI / Shapely (backend), Next.js / React / react-konva / TypeScript (frontend), pytest, Playwright.

## Global Constraints

- `NET_SHRINK_M = 0.10` (`backend/services/wall_geometry.py:19`) — the constant both the cage (Wall Task 3) and this corridor change grow built rectangles by (×2, one per side).
- `num_cages` has no upper-bound validation — the existing per-zone loop silently caps at however many zones can actually fit a cage (same pattern as `_corner_cage_convex`'s area guards).
- Corridor point removal must never drop the centerline below 2 points (1 segment) — guarded client-side as a no-op, not a backend validation error.
- No changes to `subdivide_units()`, WT validation, or cage visual subdivision geometry (spec §2).

---

### Task 1: Backend — `num_cages` support in `place_circulation()`

**Files:**
- Modify: `backend/services/circulation.py:425-536` (`place_circulation` signature + cage-placement loop)
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: existing `_place_cage_by_mode(polygon, mode, width, depth, preferred_corner=None) -> Polygon | None` (circulation.py:54), existing `cage_zone_order` construction (circulation.py:456-463) — unchanged.
- Produces: `place_circulation(footprint, corridor_width_m, stair_width_m, place_cage, cage_size_m, cage_position, num_cages: int = 1) -> CirculationResult` — new keyword-only-by-convention param (has a default, so every existing call site in the codebase and tests keeps working unmodified). `CirculationResult.cage_polygons` can now have length 0..num_cages (previously 0..1).

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_circulation.py` (append at end of file):

```python
def test_place_circulation_num_cages_two_zones_gets_two_cages():
    from services.circulation import place_circulation

    # L-shape: rectangle_decompose gives exactly 2 zones (20x10 and 10x10),
    # both large enough for the 4.2x5.7m cage.
    l_shape = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    result = place_circulation(
        l_shape,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=2,
    )
    assert len(result.cage_polygons) == 2
    # No overlap between the two cages.
    assert result.cage_polygons[0].intersection(result.cage_polygons[1]).area < 1e-9


def test_place_circulation_num_cages_defaults_to_one():
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
    assert len(result.cage_polygons) == 1


def test_place_circulation_num_cages_exceeds_available_zones_caps_silently():
    from services.circulation import place_circulation

    l_shape = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    result = place_circulation(
        l_shape,
        corridor_width_m=1.5,
        stair_width_m=1.2,
        place_cage=True,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=5,
    )
    # Only 2 zones exist in this footprint — no error, just 2 cages.
    assert len(result.cage_polygons) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -k num_cages -v`
Expected: FAIL — `place_circulation() got an unexpected keyword argument 'num_cages'`

- [ ] **Step 3: Implement `num_cages`**

In `backend/services/circulation.py`, change the `place_circulation` signature (line ~425):

```python
def place_circulation(
    footprint: Polygon,
    corridor_width_m: float,
    stair_width_m: float,
    place_cage: bool,
    cage_size_m: float,
    cage_position: str,
    num_cages: int = 1,
) -> CirculationResult:
    """Etap 1: dzieli obrys na prawie-prostokątne strefy (rectangle_decompose),
    umieszcza klatkę i korytarz w każdej, zwraca zunifikowany wynik.

    `cage_size_m` jest przyjmowany dla zgodności API, ale geometria klatki
    używa stałych CAGE_WIDTH_M x CAGE_DEPTH_M (spec 2026-07-03 §6).

    `num_cages`: maksymalna liczba klatek do umieszczenia, jedna na strefę
    (spec 2026-07-04-cage-corridor-placement-quality §3). Jeśli stref
    zdolnych pomieścić klatkę jest mniej niż `num_cages`, umieszczonych
    zostaje tyle, ile się zmieści -- bez błędu (cichy cap, spec §3.1)."""
```

Then replace the cage-placement loop (lines ~469-484):

```python
    if place_cage:
        for i in cage_zone_order:
            if len(cage_polygons) >= num_cages:
                break
            zone = zones[i]
            if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
                continue
            preferred_corner = _find_matching_corner(zone.polygon, original_concave)
            cage_polygon = _place_cage_by_mode(
                zone.polygon, cage_position, CAGE_WIDTH_M, CAGE_DEPTH_M, preferred_corner=preferred_corner
            )
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                circulation_geom = unary_union([circulation_geom, cage_polygon])
                cage_polygons.append(cage_polygon)
                local_cages[i] = cage_polygon
```

(Only change from the original: the `break` after appending is removed, and a new `if len(cage_polygons) >= num_cages: break` guard is added at the top of the loop body. Everything else in the loop body — and the rest of the function, which already reads `local_cages` generically by zone index — is untouched.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -k num_cages -v`
Expected: 3 passed

- [ ] **Step 5: Run the full circulation test file to check for regressions**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -v`
Expected: all pass (existing single-cage tests use the `num_cages=1` default implicitly and must be unaffected)

- [ ] **Step 6: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: support placing multiple staircase cages via num_cages param"
```

---

### Task 2: Backend — `corridor_width_m` becomes clear width

**Files:**
- Modify: `backend/services/circulation.py:176-245` (`_build_corridor`, `_corridor_centerline`), `backend/services/circulation.py:539-585` (`reshape_circulation`)
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: `NET_SHRINK_M` from `backend/services/wall_geometry.py:19` (new import), `net_polygon` from the same module (test-only, to verify the promised clear width survives wall subtraction).
- Produces: `_build_corridor(polygon, width, cage_polygon=None)`, `_corridor_centerline(polygon, width, cage_polygon=None)`, `reshape_circulation(footprint, centerline_points, corridor_width_m, cage_polygons)` — same signatures, but the `width`/`corridor_width_m` parameter now means clear width; callers (Task 1's `place_circulation`, the two API endpoints) pass their existing `corridor_width_m` value unchanged — no call-site changes needed.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_circulation.py`:

```python
def test_build_corridor_width_is_clear_not_axis():
    from services.circulation import _build_corridor
    from services.wall_geometry import NET_SHRINK_M, net_polygon

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    corridor = _build_corridor(zone, width=1.5)
    minx, miny, maxx, maxy = corridor.bounds
    built_width = maxy - miny
    assert abs(built_width - (1.5 + 2 * NET_SHRINK_M)) < 1e-6

    # After wall subtraction (net_polygon shrinks 0.10m per side), the
    # walkable width should be back to the requested 1.5m clear width.
    net = net_polygon(corridor)
    net_minx, net_miny, net_maxx, net_maxy = net.bounds
    assert abs((net_maxy - net_miny) - 1.5) < 1e-6


def test_corridor_centerline_axis_unaffected_by_clear_width_change():
    from services.circulation import _corridor_centerline

    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=1.5)
    assert seg is not None
    (x1, y1), (x2, y2) = seg
    # Centerline axis position is unaffected by the width -- only which
    # widths are still "too wide to fit" changes (checked below).
    assert abs(y1 - 3.0) < 1e-6
    assert abs(y2 - 3.0) < 1e-6


def test_corridor_centerline_none_when_clear_width_plus_walls_too_wide():
    from services.circulation import _corridor_centerline

    # Zone is 6m in the cross-axis; a corridor whose BUILT width (clear +
    # 2*NET_SHRINK_M = 5.8 + 0.2 = 6.0) exactly consumes the whole zone
    # depth must be rejected (existing `if width >= h: return None` guard
    # must compare against the grown width, not the raw clear width).
    zone = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    seg = _corridor_centerline(zone, width=5.8)
    assert seg is None


def test_reshape_circulation_width_matches_build_corridor():
    from services.circulation import reshape_circulation

    footprint = Polygon([(0, 0), (20, 0), (20, 6), (0, 6)])
    result = reshape_circulation(
        footprint,
        centerline_points=[((0, 3), (20, 3))],
        corridor_width_m=1.5,
        cage_polygons=[],
    )
    minx, miny, maxx, maxy = result.circulation_geometry.bounds
    assert abs((maxy - miny) - (1.5 + 2 * 0.10)) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -k "clear_width or reshape_circulation_width" -v`
Expected: FAIL — built width comes back as exactly 1.5 (not 1.7), assertions fail.

- [ ] **Step 3: Implement the clear-width growth**

In `backend/services/circulation.py`, add the import near the top (after the `from services.bsp import ...` line, ~line 15):

```python
from services.wall_geometry import NET_SHRINK_M
```

In `_build_corridor` (~line 176-210), change both `half = width / 2.0` lines to:

```python
    half = (width + 2 * NET_SHRINK_M) / 2.0
```

(there are two occurrences — one in the `if w >= h:` branch, one in the `else:` branch — change both).

In `_corridor_centerline` (~line 213-245), the function currently has:

```python
    half = width / 2.0

    if w >= h:
        if width >= h:
            return None
```

Change to:

```python
    grown_width = width + 2 * NET_SHRINK_M
    half = grown_width / 2.0

    if w >= h:
        if grown_width >= h:
            return None
```

and further down in the `else:` branch, change `if width >= w:` to `if grown_width >= w:`. (The centerline axis position math — `mid_y`/`mid_x` — already only uses `half`, so it automatically reflects the grown width; only the two "does it even fit" guards need the explicit `grown_width` swap-in.)

In `reshape_circulation` (~line 539-556), change:

```python
    half = corridor_width_m / 2.0
```

to:

```python
    half = (corridor_width_m + 2 * NET_SHRINK_M) / 2.0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -v`
Expected: all pass, including the 4 new tests and all pre-existing ones (pre-existing tests that assert exact corridor bounds/widths may need inspection — see Step 5).

- [ ] **Step 5: Check for pre-existing tests asserting old (axis) corridor width and update them**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_circulation.py -v 2>&1 | grep FAIL`

If any pre-existing test (e.g. one asserting exact `_build_corridor`/`_corridor_centerline` bounds against the raw `corridor_width_m` value) now fails, update its expected value to `corridor_width_m + 2 * NET_SHRINK_M` — this is an intentional behavior change (spec §5), not a regression. Re-run the full file until green.

- [ ] **Step 6: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "fix: treat corridor_width_m as clear width, grow built rectangle by 2xNET_SHRINK_M"
```

---

### Task 3: Backend — thread `num_cages` through the API layer

There are two independent call paths to update, not one: `/layout/circulation`
calls `place_circulation()` directly, but `/layout/generate` goes through
`services/layout.py`'s `LayoutInput` dataclass and `generate_layout()`
wrapper, which has its own internal `place_circulation(...)` call — `LayoutInput`
needs its own `num_cages` field too, independent of `CirculationSpec`.

**Files:**
- Modify: `backend/services/layout.py:82-88` (`LayoutInput` dataclass), `:145-152` (`generate_layout()`'s internal `place_circulation(...)` call)
- Modify: `backend/api/v1/endpoints/layout.py:26-34` (`CirculationSpec`), `:111-120` (`/generate`'s `LayoutInput(...)` construction), `:287-294` (`/circulation`'s direct `place_circulation(...)` call)
- Test: `backend/tests/test_layout_circulation_endpoint.py` (`/circulation` path), `backend/tests/test_layout_corridor.py` (`/generate`/`LayoutInput` path — already has `LayoutInput`/`generate_layout` imports and a matching test pattern, see `test_corridor_connects_to_cage_mode_1a`)

**Interfaces:**
- Consumes: `place_circulation(..., num_cages: int = 1)` from Task 1.
- Produces: `LayoutInput.num_cages: int = 1` (services/layout.py), `CirculationSpec.num_cages: int` (JSON field `num_cages`, default `1`, api/v1/endpoints/layout.py) — both consumed by their respective call sites.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_layout_circulation_endpoint.py` (matches the file's existing pattern exactly — `TestClient(app)` as module-level `client`, path prefix `/api/v1`, footprint as `[[x, y], ...]` coordinate pairs, not `{"x":..,"y":..}` objects):

```python
def test_circulation_endpoint_respects_num_cages():
    response = client.post(
        "/api/v1/layout/circulation",
        json={
            "footprint": [[0, 0], [20, 0], [20, 10], [10, 10], [10, 20], [0, 20]],
            "circulation": {
                "corridor_width_m": 1.5,
                "stair_width_m": 1.2,
                "place_cage": True,
                "cage_size_m": 2.5,
                "cage_position": "auto",
                "num_cages": 2,
            },
        },
    )
    assert response.status_code == 200
    assert len(response.json()["cage_geometries"]) == 2
```

- [ ] **Step 2: Write the failing test for the `/generate` path (goes through `LayoutInput`/`generate_layout`, a separate code path from Step 1's direct `place_circulation()` call)**

Append to `backend/tests/test_layout_corridor.py` (same imports/pattern as the existing `test_corridor_connects_to_cage_mode_1a` in that file):

```python
def test_generate_layout_respects_num_cages():
    p1 = Polygon([(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)])
    input = LayoutInput(
        footprint=p1,
        corridor_width_m=1.5,
        cage_size_m=2.5,
        cage_position="auto",
        num_cages=2,
        apartments=[ApartmentSpec(type="M2", min_area_m2=25.0, target_count=2)],
    )
    result = generate_layout(input)
    assert len(result.cage_polygons) == 2
```

- [ ] **Step 3: Run both tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py tests/test_layout_corridor.py -k num_cages -v`
Expected: FAIL — Step 1's test fails because `cage_geometries` length is 1, not 2 (the `num_cages` JSON field is silently ignored by Pydantic until `CirculationSpec` declares it). Step 2's test fails with `TypeError: LayoutInput.__init__() got an unexpected keyword argument 'num_cages'` (it's a `@dataclass`, not Pydantic — unknown kwargs are a hard error, not silently ignored).

- [ ] **Step 4: Implement — `services/layout.py`'s `LayoutInput` and `generate_layout()`**

In `backend/services/layout.py`, add the field to `LayoutInput` (~line 82-90):

```python
@dataclass
class LayoutInput:
    footprint: Polygon
    corridor_width_m: float = 1.5
    stair_width_m: float = 1.2
    place_cage: bool = True
    cage_size_m: float = 2.5
    cage_position: str = "auto"
    num_cages: int = 1
    apartments: list[ApartmentSpec] = field(default_factory=list)
    local_law: str | None = None
```

Then in `generate_layout()`'s internal `place_circulation(...)` call (~line 145-152), add `num_cages=input.num_cages,`:

```python
    circulation = place_circulation(
        footprint,
        corridor_width_m=input.corridor_width_m,
        stair_width_m=input.stair_width_m,
        place_cage=input.place_cage,
        cage_size_m=input.cage_size_m,
        cage_position=input.cage_position,
        num_cages=input.num_cages,
    )
```

- [ ] **Step 5: Implement — `api/v1/endpoints/layout.py`'s `CirculationSpec` and both endpoint call sites**

Add the field to `CirculationSpec` (~line 26-34):

```python
class CirculationSpec(BaseModel):
    corridor_width_m: float = Field(default=1.5, gt=0)
    stair_width_m: float = Field(default=1.2, gt=0)
    place_cage: bool = Field(default=True)
    cage_size_m: float = Field(default=2.5, gt=0)
    cage_position: str = Field(
        default="auto",
        description=f"Tryb pozycji klatki wg plan.md §4.3: {CAGE_POSITION_MODES}",
    )
    num_cages: int = Field(default=1, ge=1)
```

In `/generate`'s `LayoutInput(...)` construction (~line 111-120), add `num_cages=circulation.num_cages,`:

```python
    layout_input = LayoutInput(
        footprint=footprint,
        corridor_width_m=circulation.corridor_width_m,
        stair_width_m=circulation.stair_width_m,
        place_cage=circulation.place_cage,
        cage_size_m=circulation.cage_size_m,
        cage_position=circulation.cage_position,
        num_cages=circulation.num_cages,
        apartments=specs,
        local_law=request.local_law,
    )
```

In `/circulation`'s direct `place_circulation(...)` call (~line 287-294), add the same line:

```python
    result = place_circulation(
        footprint,
        corridor_width_m=circulation.corridor_width_m,
        stair_width_m=circulation.stair_width_m,
        place_cage=circulation.place_cage,
        cage_size_m=circulation.cage_size_m,
        cage_position=circulation.cage_position,
        num_cages=circulation.num_cages,
    )
```

- [ ] **Step 6: Run both tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py tests/test_layout_corridor.py -k num_cages -v`
Expected: 2 passed

- [ ] **Step 7: Run full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add backend/services/layout.py backend/api/v1/endpoints/layout.py backend/tests/test_layout_circulation_endpoint.py backend/tests/test_layout_corridor.py
git commit -m "feat: expose num_cages through LayoutInput/CirculationSpec, thread through /layout/generate and /layout/circulation"
```

---

### Task 4: Frontend — types, state, and multi-cage slider UI

**Files:**
- Modify: `frontend/app/lib/api.ts:124-130` (`CirculationSpecInput`)
- Modify: `frontend/app/state/SessionContext.tsx:69-75` (`initialCirculation`)
- Modify: `frontend/app/components/CirculationSection.tsx` (new slider control, corridor label text)

**Interfaces:**
- Consumes: none new (pure UI + type plumbing).
- Produces: `CirculationSpecInput.num_cages: number`, rendered/editable via `state.circulation.num_cages` / `setCirculation({ num_cages })` (existing `setCirculation` callback already accepts `Partial<CirculationSpecInput>`, no changes needed there).

- [ ] **Step 1: Add the field to the TS type**

In `frontend/app/lib/api.ts`, change (~line 124-130):

```typescript
export interface CirculationSpecInput {
  corridor_width_m: number;
  stair_width_m: number;
  place_cage: boolean;
  cage_size_m: number;
  cage_position: CagePosition;
  num_cages: number;
}
```

- [ ] **Step 2: Add the default to initial state**

In `frontend/app/state/SessionContext.tsx`, change `initialCirculation` (~line 69-75):

```typescript
const initialCirculation: api.CirculationSpecInput = {
  corridor_width_m: 1.5,
  stair_width_m: 1.2,
  place_cage: true,
  cage_size_m: 2.5,
  cage_position: "auto",
  num_cages: 1,
};
```

- [ ] **Step 3: Add the slider to `CirculationSection.tsx`**

In `frontend/app/components/CirculationSection.tsx`, insert this block right after the "Pozycja klatki" `<label>` block (after the closing `</label>` at what is currently line 85, before the `place_cage` checkbox label):

```tsx
      <label className="flex items-center justify-between text-xs text-zinc-400">
        Liczba klatek: {state.circulation.num_cages}
        <input
          type="range"
          min={1}
          max={8}
          step={1}
          value={state.circulation.num_cages}
          onChange={(e) => setCirculation({ num_cages: Number(e.target.value) })}
          className="ml-2 w-24 accent-accent-500"
        />
      </label>
```

- [ ] **Step 4: Update the corridor-width label to say "w świetle"**

In the same file, change the "Szerokość korytarza (m)" label text (~line 114) to:

```tsx
      <label className="flex items-center justify-between text-xs text-zinc-400">
        Szerokość korytarza (w świetle, m)
```

(only the visible text changes — the `<input>` below it is unchanged).

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 6: Manual smoke check**

Start the dev server (`cd frontend && npm run dev`), draw a footprint that decomposes into ≥2 zones (e.g. an L-shape), move the new "Liczba klatek" slider to 2, click "Umieść korytarz i klatkę", confirm 2 gray cage rectangles render on canvas (visual only — full Playwright pass is Task 6's job once point-editing is also in place).

- [ ] **Step 7: Commit**

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: add num_cages slider and clear-width corridor label to Komunikacja panel"
```

---

### Task 5: Frontend — insert and remove corridor centerline points

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx:724-798` (centerline segment rendering + vertex rendering/dragging)

**Interfaces:**
- Consumes: `runReshapeCirculation(segments: [Point2D, Point2D][]) -> Promise<void>` (already defined in `SessionContext.tsx:347`, already used by the existing vertex `onDragEnd` handler at `CanvasEditor.tsx:794` — no changes to its signature).
- Produces: no new exported interfaces — purely new event handlers on existing JSX elements within `CanvasEditor.tsx`.

- [ ] **Step 1: Add a helper to flatten segments and rebuild them after a point-list edit**

In `frontend/app/CanvasEditor.tsx`, add this function near `ringToPoints` (~line 26, right after it):

```typescript
/** Corridor centerline segments are stored as a list of [p1,p2] pairs where
 *  consecutive segments share an endpoint (seg[i][1] === seg[i+1][0]) --
 *  same continuity `reshape_circulation()` assumes server-side (circulation.py
 *  §_join_centerlines). `points` is `[api.Point, api.Point]` where
 *  `api.Point = [number, number]` (a tuple, NOT a `{x,y}` object — see
 *  `frontend/app/lib/api.ts`'s `Point` type). Flattening to a plain
 *  `Point2D[]` list and rebuilding segments from it is the shared primitive
 *  both insert and remove need. */
function flattenCenterline(centerline: api.CorridorCenterlineSegment[]): Point2D[] {
  if (centerline.length === 0) return [];
  const toPt = ([x, y]: api.Point): Point2D => ({ x, y });
  const flat: Point2D[] = [toPt(centerline[0].points[0])];
  for (const seg of centerline) {
    flat.push(toPt(seg.points[1]));
  }
  return flat;
}

function segmentsFromFlatPath(flat: Point2D[]): [Point2D, Point2D][] {
  const segs: [Point2D, Point2D][] = [];
  for (let i = 0; i < flat.length - 1; i++) {
    segs.push([flat[i], flat[i + 1]]);
  }
  return segs;
}
```

- [ ] **Step 2: Add `onDblClick` to insert a point on a centerline segment**

In `frontend/app/CanvasEditor.tsx`, the centerline segments are rendered at ~line 725-733:

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

Change to (adds `onDblClick`, so `listening` must become conditionally `true` in edit mode — `listening={false}` today means the segment never receives any pointer events, which would silently swallow the new handler):

```tsx
          {/* Linia środkowa korytarza — kolor wg progu odległości do klatki (F2-04-bis) */}
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke={seg.exceeds_max ? "#ef4444" : "#22c55e"}
              strokeWidth={3 / scale}
              listening={state.mode === "edit-corridor-centerline"}
              onDblClick={(e) => {
                if (state.mode !== "edit-corridor-centerline" || !state.circulationResult) return;
                e.cancelBubble = true;
                const stage = stageRef.current;
                const pointer = stage?.getPointerPosition();
                if (!pointer) return;
                const clicked = worldToMeters(pointer.x, pointer.y);
                const flat = flattenCenterline(state.circulationResult.centerline);
                // Insert the new point between this segment's two endpoints
                // (index i in the flat path, since flat[i]/flat[i+1] are
                // exactly seg.points[0]/seg.points[1] by construction).
                const newFlat = [...flat.slice(0, i + 1), clicked, ...flat.slice(i + 1)];
                void runReshapeCirculation(segmentsFromFlatPath(newFlat));
              }}
            />
          ))}
```

- [ ] **Step 3: Add `onDblClick` to remove a vertex (guarded at 2-point minimum)**

The vertex-rendering block is at ~line 736-798. Inside the `verts.map((v, i) => (...))` block, the `<Circle>` currently has `onDragStart`/`onDragMove`/`onDragEnd`. Add a sibling `onDblClick` handler:

```tsx
                <Circle
                  key={`centerline-vertex-${i}`}
                  x={v.x * METER_PX}
                  y={-v.y * METER_PX}
                  radius={6 / scale}
                  fill="#ffffff"
                  stroke="#22c55e"
                  strokeWidth={2 / scale}
                  draggable
                  onDblClick={(e) => {
                    e.cancelBubble = true;
                    if (!state.circulationResult) return;
                    const flat = flattenCenterline(state.circulationResult.centerline);
                    // Guard: 2 points = 1 segment = the minimum viable
                    // centerline. Removing one would leave 0 or 1 points and
                    // no geometry -- no-op instead (spec §4.1).
                    if (flat.length <= 2) return;
                    const idx = flat.findIndex(
                      (p) => Math.abs(p.x - v.x) < 1e-6 && Math.abs(p.y - v.y) < 1e-6
                    );
                    if (idx === -1) return;
                    const newFlat = [...flat.slice(0, idx), ...flat.slice(idx + 1)];
                    void runReshapeCirculation(segmentsFromFlatPath(newFlat));
                  }}
                  onDragStart={(e) => {
                    e.cancelBubble = true;
                  }}
```

(the existing `onDragMove`/`onDragEnd` bodies below stay exactly as they are — only the new `onDblClick` prop is inserted, right after `draggable` and before the existing `onDragStart`).

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual smoke check**

`cd frontend && npm run dev`. Draw a footprint, place circulation, enter "Edytuj linię korytarza" mode, double-click the middle of the corridor line — confirm a new draggable vertex appears at the click point and the line still renders correctly. Double-click that new vertex — confirm it disappears and the line reconnects. Double-click one of the two remaining original vertices — confirm nothing happens (still 2 points).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: add corridor centerline point insert (dblclick segment) and remove (dblclick vertex, 2-point guard)"
```

---

### Task 6: Final verification pass

**Files:** none (verification only)

- [ ] **Step 1: Full backend suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: all pass

- [ ] **Step 2: Full frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 3: Playwright end-to-end pass covering all three features together**

Draw an L-shaped footprint (produces 2 zones), set "Liczba klatek" to 2, click "Umieść korytarz i klatkę" — confirm 2 cages render. Enter "Edytuj linię korytarza", double-click a segment to add a point, double-click that point to remove it again, confirm no crash and the centerline is visually intact. Check that the built corridor visually appears ~20cm wider than the `corridor_width_m` input value would have produced before this plan (qualitative — exact pixel measurement not required, the backend tests already pin the exact numbers).

- [ ] **Step 4: Update the SDD progress ledger**

Append to `.superpowers/sdd/progress.md`:

```
--- Cage/corridor placement quality plan ---
Task 1: complete (num_cages in place_circulation)
Task 2: complete (corridor_width_m clear-width)
Task 3: complete (API layer num_cages)
Task 4: complete (frontend slider + label)
Task 5: complete (centerline point insert/remove)
Task 6: complete (final verification)
```

- [ ] **Step 5: Commit the ledger update**

```bash
git add .superpowers/sdd/progress.md
git commit -m "docs: update SDD progress ledger for cage/corridor placement quality plan"
```
