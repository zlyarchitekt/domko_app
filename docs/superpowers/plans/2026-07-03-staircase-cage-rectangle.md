# Staircase Cage Rectangle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fictional square staircase cage with a realistic 4.0×5.5m rectangle and draw its internal subdivision (2 stair flights, landings, elevator, shaft, corridor strip) as a purely decorative frontend overlay.

**Architecture:** Backend `services/circulation.py` cage-builder functions (`_corner_cage_convex`, `_centered_cage`, `_edge_cage`) and `services/bsp.py`'s `corner_cage` switch from a single `size` scalar (square) to `width`/`depth` (rectangle), fed by two new module constants. The existing `cage_size_m` API parameter stays accepted but is ignored by geometry (documented API-compat decision, spec §6). Frontend `CanvasEditor.tsx` draws the 5-zone subdivision proportionally scaled to each cage polygon's bounding box — pure Konva decoration, `listening={false}`, no API/state changes.

**Tech Stack:** FastAPI + Shapely 2.x (backend), Next.js/TypeScript + react-konva (frontend), pytest.

## Global Constraints

- `CAGE_WIDTH_M = 4.0`, `CAGE_DEPTH_M = 5.5` — exact names and values (spec §4.1); geometry ignores `cage_size_m` from now on, but the parameter must remain accepted everywhere it exists today (no API breaking change).
- Approved v4 layout (spec §3), zone fractions of the 400×550 rectangle: top row (landing 240×150 at left | shaft 160×150 at right), middle row (two flights 120×250 each at left | elevator 160×250 at right), bottom row (landing+corridor 400×150 full width). Bottom row renders at the min-Y side of the bounding box.
- Purely visual: no WT rule changes (§68 still uses `stair_width_m`), no new API fields, still exactly one `cage_polygon` per cage in `place_circulation()`'s result.
- No rotation — cage rectangle is always axis-aligned: `width` along X, `depth` along Y (for corner/center modes); for edge mode (`1a`/`1b`) `width` runs along the chosen edge and `depth` runs inward along its normal (spec §4.2).
- The overlay must scale proportionally to the actual polygon bounding box, never hardcode 400×550 pixel values (spec §4.3.2).

---

## File Structure

- Modify `backend/services/bsp.py` — `corner_cage()` takes `width`/`depth` instead of `size`; per-adjacent-edge extent picked by axis rule.
- Modify `backend/services/circulation.py` — new constants; `_build_cage`, `_place_cage_by_mode`, `_corner_cage_convex`, `_centered_cage`, `_edge_cage` take `width`/`depth`; `place_circulation()` passes the constants and documents that `cage_size_m` is ignored.
- Test `backend/tests/test_bsp.py` — `corner_cage` rectangle test.
- Test `backend/tests/test_circulation.py` — update existing `_place_cage_by_mode` call signatures; new bounds tests per mode.
- Modify `frontend/app/CanvasEditor.tsx` — `CageSubdivisionOverlay` render helper + wiring after the existing cage render block.

### Task boundary rationale

Task 1 (bsp.py) must land before Task 2 (circulation.py) because `_build_cage` forwards to `corner_cage` — changing both signatures in one commit per file keeps each task's test cycle self-contained. Task 3 (frontend) only needs the rectangle to exist, not any specific backend internals.

---

### Task 1: `corner_cage()` rectangle in `services/bsp.py`

**Files:**
- Modify: `backend/services/bsp.py:199-254` (`corner_cage`)
- Test: `backend/tests/test_bsp.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `corner_cage(polygon: Polygon, corner: tuple[float, float], width: float = 1.0, depth: float = 1.0) -> Polygon` — consumed by Task 2's `_build_cage`. Extent rule: along each of the two edges adjacent to the corner, the cage extends by `width` if that edge is more horizontal (`abs(dx) >= abs(dy)`), else by `depth`.

- [ ] **Step 1: Write the failing test**

Add at the end of `backend/tests/test_bsp.py`:

```python
def test_corner_cage_builds_rectangle_with_width_and_depth():
    """Spec 2026-07-03 (staircase-cage-rectangle) §4.2: cage is a width x depth
    rectangle, not a square. For an axis-aligned concave corner the extent
    along the horizontal adjacent edge must be `width` and along the vertical
    adjacent edge `depth`."""
    from services.bsp import corner_cage

    # L-shape with a concave vertex at (6, 6); its adjacent edges run
    # horizontally (toward (12, 6)) and vertically (toward (6, 12)).
    l_shape = Polygon([(0, 0), (12, 0), (12, 6), (6, 6), (6, 12), (0, 12)])
    cage = corner_cage(l_shape, (6, 6), width=4.0, depth=5.5)

    minx, miny, maxx, maxy = cage.bounds
    w = maxx - minx
    h = maxy - miny
    assert abs(w - 4.0) < 1e-6, f"expected width 4.0 along X, got {w}"
    assert abs(h - 5.5) < 1e-6, f"expected depth 5.5 along Y, got {h}"
    assert cage.area > 1e-6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_bsp.py::test_corner_cage_builds_rectangle_with_width_and_depth -v`
Expected: FAIL with `TypeError: corner_cage() got an unexpected keyword argument 'width'`

- [ ] **Step 3: Rewrite `corner_cage()`**

Replace the whole function in `backend/services/bsp.py` (lines 199-254) with:

```python
def corner_cage(
    polygon: Polygon,
    corner: tuple[float, float],
    width: float = 1.0,
    depth: float = 1.0,
) -> Polygon:
    """Generuje prostokątną klatkę w narożniku (przy wierzchołku wklęsłym).

    Rozpiętość wzdłuż każdej z dwóch krawędzi przylegających do narożnika:
    `width` gdy krawędź jest bardziej pozioma (|dx| >= |dy|), `depth` gdy
    bardziej pionowa — spec 2026-07-03 (staircase-cage-rectangle) §4.2,
    reguła deterministyczna dla prostokąta zamiast dawnego kwadratu o boku
    `size`. Klatka jest orientowana tak, by leżeć wewnątrz poligonu wzdłuż
    dwóch krawędzi przylegających do danego wierzchołka.
    """
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    idx = next(
        (
            i
            for i, p in enumerate(coords)
            if abs(p[0] - corner[0]) < 1e-9 and abs(p[1] - corner[1]) < 1e-9
        ),
        None,
    )
    if idx is None:
        raise ValueError("Corner not found in polygon")
    prev = coords[(idx - 1) % n]
    nxt = coords[(idx + 1) % n]

    def unit(v: tuple[float, float]) -> tuple[float, float]:
        length = (v[0] ** 2 + v[1] ** 2) ** 0.5
        if length == 0:
            return (0.0, 0.0)
        return (v[0] / length, v[1] / length)

    def extent(e: tuple[float, float]) -> float:
        return width if abs(e[0]) >= abs(e[1]) else depth

    e1 = unit((prev[0] - corner[0], prev[1] - corner[1]))
    e2 = unit((nxt[0] - corner[0], nxt[1] - corner[1]))
    s1 = extent(e1)
    s2 = extent(e2)

    def make_cage(sign: int) -> Polygon:
        return Polygon(
            [
                (corner[0], corner[1]),
                (corner[0] + sign * e1[0] * s1, corner[1] + sign * e1[1] * s1),
                (
                    corner[0] + sign * (e1[0] * s1 + e2[0] * s2),
                    corner[1] + sign * (e1[1] * s1 + e2[1] * s2),
                ),
                (corner[0] + sign * e2[0] * s2, corner[1] + sign * e2[1] * s2),
            ]
        )

    candidates = []
    for sign in (1, -1):
        cage = make_cage(sign)
        if not cage.is_valid or cage.area <= 0:
            continue
        candidates.append((cage, polygon.intersection(cage).area))
    if not candidates:
        raise ValueError("Cannot build a non-degenerate cage for the given corner")
    best_cage = max(candidates, key=lambda item: item[1])[0]

    if not polygon.contains(best_cage):
        best_cage = best_cage.intersection(polygon)
    return best_cage
```

- [ ] **Step 4: Fix any existing `corner_cage` callers/tests in test_bsp.py**

Search: `grep -n "corner_cage" backend/tests/test_bsp.py backend/services/`
Existing positional calls `corner_cage(poly, corner, size)` become `corner_cage(poly, corner, width=size, depth=size)` **inside test_bsp.py only** (a square is a valid rectangle, so old square-based assertions stay meaningful). Do NOT change `backend/services/circulation.py`'s `_build_cage` in this task — that is Task 2's job; `_build_cage` currently passes `size` positionally, which after this change binds to `width` and leaves `depth=1.0`. That temporary mismatch is acceptable within this task boundary because no test pins `_build_cage`'s depth, and Task 2 immediately follows.

- [ ] **Step 5: Run the bsp test file, then the full backend suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_bsp.py -v`
Expected: all pass.
Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass (156 as of branch head; count may drift ±, zero failures is the requirement).

- [ ] **Step 6: Commit**

```bash
git add backend/services/bsp.py backend/tests/test_bsp.py
git commit -m "feat: corner_cage builds width x depth rectangle instead of square"
```

---

### Task 2: Rectangle cage in `services/circulation.py`

**Files:**
- Modify: `backend/services/circulation.py` (constants near top; `_build_cage` :36-43; `_place_cage_by_mode` :46-83; `_corner_cage_convex` :86-109; `_centered_cage` :112-125; `_edge_cage` :128-163; `place_circulation` cage call ~:463)
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: Task 1's `corner_cage(polygon, corner, width, depth)`.
- Produces:
  - Module constants `CAGE_WIDTH_M = 4.0`, `CAGE_DEPTH_M = 5.5`.
  - `_place_cage_by_mode(polygon: Polygon, mode: str, width: float, depth: float, preferred_corner: tuple[float, float] | None = None) -> Polygon | None`.
  - `place_circulation()` signature unchanged (still accepts `cage_size_m`), but geometry uses the constants.

- [ ] **Step 1: Update existing tests + add new failing tests**

In `backend/tests/test_circulation.py`, the three existing `_place_cage_by_mode` tests call the old `(polygon, mode, size)` signature. Update them and add rectangle-bounds tests. Replace the first three test functions in the file with:

```python
from services.circulation import CAGE_DEPTH_M, CAGE_WIDTH_M, _place_cage_by_mode


def test_place_cage_auto_convex_uses_bbox_corner():
    rect = Polygon([(0, 0), (20, 0), (20, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "auto", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    assert cage.area > 0
    minx, miny, maxx, maxy = cage.bounds
    assert minx == 0.0 and miny == 0.0  # anchored at the (0,0) corner
    # Rectangle, not square: width along X, depth along Y (spec §4.2).
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6


def test_place_cage_mode_2_centered_rectangle():
    rect = Polygon([(0, 0), (20, 0), (20, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "2", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    cx, cy = cage.centroid.x, cage.centroid.y
    assert abs(cx - 10.0) < 0.5 and abs(cy - 6.0) < 0.5
    minx, miny, maxx, maxy = cage.bounds
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6


def test_place_cage_mode_1a_width_along_edge_depth_inward():
    # Longest edge is the bottom one (30m, horizontal): width runs along it,
    # depth extends inward (up).
    rect = Polygon([(0, 0), (30, 0), (30, 12), (0, 12)])
    cage = _place_cage_by_mode(rect, "1a", CAGE_WIDTH_M, CAGE_DEPTH_M)
    assert cage is not None
    minx, miny, maxx, maxy = cage.bounds
    assert abs((maxx - minx) - CAGE_WIDTH_M) < 1e-6
    assert abs((maxy - miny) - CAGE_DEPTH_M) < 1e-6
    assert abs(miny - 0.0) < 1e-6  # flush with the facade edge


def test_place_cage_invalid_mode_raises():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    try:
        _place_cage_by_mode(rect, "bogus", CAGE_WIDTH_M, CAGE_DEPTH_M)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_cage_constants_match_spec():
    """Spec 2026-07-03 (staircase-cage-rectangle) §4.1 -- pins the exact
    approved dimensions (400x550cm) so a drive-by edit can't silently shrink
    or grow the cage."""
    assert CAGE_WIDTH_M == 4.0
    assert CAGE_DEPTH_M == 5.5
```

Note: the old `test_place_cage_mode_2_centered` is replaced by `test_place_cage_mode_2_centered_rectangle` above (delete the old one); zone rectangles in these tests were enlarged (20×12, 30×12) so the 4.0×5.5 cage fits without clipping and bounds assertions stay exact.

- [ ] **Step 2: Run to verify failure**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k "place_cage or cage_constants" -v`
Expected: FAIL with `ImportError: cannot import name 'CAGE_DEPTH_M'`

- [ ] **Step 3: Implement in `circulation.py`**

3a. Add constants directly after the existing `CORRIDOR_CENTERLINE_MAX_DISTANCE_*` constants block near the top:

```python
CAGE_WIDTH_M = 4.0
CAGE_DEPTH_M = 5.5
"""Rzeczywisty obrys klatki schodowej 400x550cm (spec 2026-07-03
staircase-cage-rectangle §3/§4.1): 2 biegi 120x250 + winda 160x250 +
spoczniki/korytarz 150 na górze i dole. Zastępuje dawny kwadrat o boku
`cage_size_m` -- ten parametr pozostaje w API (CirculationSpec,
place_circulation), ale geometria już go nie używa (spec §6)."""
```

3b. `_build_cage` — pass both dimensions through:

```python
def _build_cage(
    polygon: Polygon, corner_data: tuple[int, float, float], width: float, depth: float
) -> Polygon:
    """Buduje prostokątną klatkę w narożniku."""
    from services.bsp import corner_cage

    idx, x, y = corner_data
    return corner_cage(polygon, (x, y), width=width, depth=depth)
```

3c. `_place_cage_by_mode` — replace `size: float` with `width: float, depth: float` and forward:

```python
def _place_cage_by_mode(
    polygon: Polygon,
    mode: str,
    width: float,
    depth: float,
    preferred_corner: tuple[float, float] | None = None,
) -> Polygon | None:
```

(docstring unchanged) and in the body: `_build_cage(polygon, cv[0], width, depth)`, `_corner_cage_convex(polygon, width, depth, preferred=preferred_corner)`, `_centered_cage(polygon, width, depth)`, `_edge_cage(polygon, width, depth, longest=(mode == "1a"))`.

3d. `_corner_cage_convex` — width along X, depth along Y:

```python
def _corner_cage_convex(
    polygon: Polygon, width: float, depth: float, preferred: tuple[float, float] | None = None
) -> Polygon | None:
```

body change (keep the docstring and preferred-corner loop identical, replace only the candidate construction):

```python
    sx = width if ax == minx else -width
    sy = depth if ay == miny else -depth
    candidate = Polygon([(ax, ay), (ax + sx, ay), (ax + sx, ay + sy), (ax, ay + sy)])
```

3e. `_centered_cage` — width along X, depth along Y:

```python
def _centered_cage(polygon: Polygon, width: float, depth: float) -> Polygon | None:
    """Klatka wyśrodkowana w strefie (tryb 2 — punktowiec)."""
    center = polygon.centroid
    half_w = width / 2.0
    half_d = depth / 2.0
    candidate = Polygon(
        [
            (center.x - half_w, center.y - half_d),
            (center.x + half_w, center.y - half_d),
            (center.x + half_w, center.y + half_d),
            (center.x - half_w, center.y + half_d),
        ]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None
```

3f. `_edge_cage` — width along the edge, depth inward (only the last block changes; signature gains `width, depth` in place of `size`):

```python
def _edge_cage(polygon: Polygon, width: float, depth: float, longest: bool) -> Polygon | None:
```

```python
    half = width / 2.0
    p_a = (mid_x - ux * half, mid_y - uy * half)
    p_b = (mid_x + ux * half, mid_y + uy * half)
    p_c = (p_b[0] + normal_x * depth, p_b[1] + normal_y * depth)
    p_d = (p_a[0] + normal_x * depth, p_a[1] + normal_y * depth)
```

3g. In `place_circulation()` (~line 463), the cage call becomes:

```python
            cage_polygon = _place_cage_by_mode(
                zone.polygon, cage_position, CAGE_WIDTH_M, CAGE_DEPTH_M, preferred_corner=preferred_corner
            )
```

and extend `place_circulation`'s docstring with one line:

```
    `cage_size_m` jest przyjmowany dla zgodności API, ale geometria klatki
    używa stałych CAGE_WIDTH_M x CAGE_DEPTH_M (spec 2026-07-03 §6).
```

- [ ] **Step 4: Run the circulation test file, fix fallout, then full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -v`
Expected: all pass. Watch specifically for the pre-existing area-reconstruction tests (`test_place_circulation_simple_rectangle` uses a 30×6 footprint — the 5.5m-deep cage gets clipped to 6m depth there; clipping is fine, the reconstruction assertion is size-agnostic).

Then: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass. If `test_wt_validation.py` or endpoint tests fail on cage-size-sensitive assertions, inspect each: assertions on cage EXISTENCE/count stay valid; any assertion hardcoding the old square dimensions must be updated to the new constants (report which in the commit message).

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: staircase cage is a 4.0x5.5m rectangle (CAGE_WIDTH_M/CAGE_DEPTH_M), cage_size_m kept API-only"
```

---

### Task 3: Frontend — cage subdivision overlay in `CanvasEditor.tsx`

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (helper above the component + render wiring directly after the existing `{/* Klatka (szary) */}` block)

**Interfaces:**
- Consumes: existing `cageGeometries` memo (list of GeoJSON polygons) and `canvasColors` theme object; `METER_PX`, `scale` already in scope.
- Produces: nothing consumed later — final visual layer.

- [ ] **Step 1: Add the overlay helper**

Add above the `CanvasEditor` component (after the existing top-level helpers like `ringToPoints`):

```tsx
/** Dekoracyjny podział klatki schodowej (spec 2026-07-03 staircase-cage-rectangle §3/§4.3):
 *  rzędy od strony minY ("strona wejścia/korytarza"): spocznik+korytarz (150/550),
 *  2 biegi 120x250 + winda 160x250 (250/550), spocznik 240x150 + szacht 160x150 (150/550).
 *  Frakcje liczone z bbox konkretnego poligonu, nie zahardkodowane w px. Czysto
 *  wizualne -- zero wpływu na geometrię/WT, listening=false na wszystkim. */
function cageSubdivisionShapes(
  geom: GeoJsonPolygon,
  keyPrefix: string,
  scale: number,
  lineColor: string,
  textColor: string
): React.ReactNode[] {
  const ring = ringToPoints(geom);
  if (ring.length < 3) return [];
  const xs = ring.map((p) => p.x);
  const ys = ring.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const w = maxX - minX;
  const h = maxY - minY;
  if (w < 1e-6 || h < 1e-6) return [];

  // Zone fractions of the approved 400x550 layout.
  const fx = (f: number) => (minX + f * w) * METER_PX;
  const fy = (f: number) => -(minY + f * h) * METER_PX; // canvas Y is flipped
  const X_FLIGHT1 = 120 / 400;
  const X_FLIGHTS = 240 / 400;
  const Y_BOTTOM = 150 / 550; // landing+corridor strip (entrance side = minY)
  const Y_MID_TOP = 400 / 550; // top of flights/elevator band

  const sw = 1 / scale;
  const nodes: React.ReactNode[] = [];

  // Row separators (full width) + column separators.
  nodes.push(
    <Line key={`${keyPrefix}-row-b`} points={[fx(0), fy(Y_BOTTOM), fx(1), fy(Y_BOTTOM)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-row-t`} points={[fx(0), fy(Y_MID_TOP), fx(1), fy(Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-col-f`} points={[fx(X_FLIGHT1), fy(Y_BOTTOM), fx(X_FLIGHT1), fy(Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-col-e`} points={[fx(X_FLIGHTS), fy(Y_BOTTOM), fx(X_FLIGHTS), fy(1)]} stroke={lineColor} strokeWidth={sw} listening={false} />
  );

  // Stair-flight tread hatching: 6 lines per flight across both flights' band.
  for (let i = 1; i <= 6; i++) {
    const t = Y_BOTTOM + (i / 7) * (Y_MID_TOP - Y_BOTTOM);
    nodes.push(
      <Line key={`${keyPrefix}-tread-${i}`} points={[fx(0), fy(t), fx(X_FLIGHTS), fy(t)]} stroke={lineColor} strokeWidth={sw} listening={false} />
    );
  }

  // Direction arrows: left flight up, right flight down (shaft + head marks).
  const arrow = (key: string, xf: number, fromT: number, toT: number) => {
    const head = 0.03 * (toT > fromT ? 1 : -1);
    return [
      <Line key={`${key}-shaft`} points={[fx(xf), fy(fromT), fx(xf), fy(toT)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
      <Line
        key={`${key}-head`}
        points={[fx(xf - 0.02), fy(toT - head), fx(xf), fy(toT), fx(xf + 0.02), fy(toT - head)]}
        stroke={lineColor}
        strokeWidth={sw}
        listening={false}
      />,
    ];
  };
  nodes.push(...arrow(`${keyPrefix}-arr-l`, X_FLIGHT1 / 2, Y_BOTTOM + 0.03, Y_MID_TOP - 0.03));
  nodes.push(...arrow(`${keyPrefix}-arr-r`, (X_FLIGHT1 + X_FLIGHTS) / 2, Y_MID_TOP - 0.03, Y_BOTTOM + 0.03));

  // Elevator X (diagonals across the elevator cell only).
  nodes.push(
    <Line key={`${keyPrefix}-el-1`} points={[fx(X_FLIGHTS), fy(Y_BOTTOM), fx(1), fy(Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-el-2`} points={[fx(1), fy(Y_BOTTOM), fx(X_FLIGHTS), fy(Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />
  );

  // Labels (tiny, theme-following).
  const label = (key: string, xf: number, yf: number, text: string) => (
    <Text
      key={key}
      x={fx(xf)}
      y={fy(yf)}
      text={text}
      fontSize={10 / scale}
      fill={textColor}
      listening={false}
      offsetX={14 / scale}
      offsetY={5 / scale}
    />
  );
  nodes.push(
    label(`${keyPrefix}-lb-sp`, X_FLIGHTS / 2, (Y_MID_TOP + 1) / 2, "spocznik"),
    label(`${keyPrefix}-lb-sz`, (X_FLIGHTS + 1) / 2, (Y_MID_TOP + 1) / 2, "szacht"),
    label(`${keyPrefix}-lb-wd`, (X_FLIGHTS + 1) / 2, (Y_BOTTOM + Y_MID_TOP) / 2, "winda"),
    label(`${keyPrefix}-lb-ko`, 0.5, Y_BOTTOM / 2, "korytarz")
  );

  return nodes;
}
```

Type note: `GeoJsonPolygon` is already imported in this file's `api` types usage (`ringToPoints(geom)` calls exist); if the bare type name isn't imported, use the same type annotation the existing `cageGeometries.map((geom, i) => ...)` block's parameter uses (check the local convention first, don't add a new import style).

- [ ] **Step 2: Wire it in after the existing cage render block**

Directly after the `{/* Klatka (szary) */}` block (the `cageGeometries.map` that draws the gray filled cage):

```tsx
          {/* Podział klatki: biegi/spoczniki/winda/szacht (dekoracja, spec 2026-07-03) */}
          {cageGeometries.flatMap((geom, i) =>
            cageSubdivisionShapes(geom, `cage-sub-${i}`, scale, canvasColors.axis, canvasColors.axisText)
          )}
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no output.

- [ ] **Step 4: Manual verification with Playwright**

Servers: backend `backend/.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`, frontend `NEXT_PUBLIC_API_URL="http://localhost:8000/api/v1" npm run dev -- --port 3010` (port 3000 is taken by an unrelated service on this machine; if a frontend is already running, kill and restart it — long-running dev servers keep a stale `NEXT_PUBLIC_API_URL`).

Script flow (reuse the session's scratchpad pattern from `verify_solar_facade_fix.py`, including: zoom out via mouse wheel before drawing, read actual scale from the on-screen `N.NNx` badge, close the outline via the sidebar "Zamknij obrys" button — canvas double-click is timing-flaky):
1. Draw a large rectangle footprint (e.g. 30×15m world units).
2. Click "Umieść korytarz i klatkę".
3. Screenshot; visually confirm the cage renders as a RECTANGLE (taller than wide) with visible subdivision: bottom strip, two hatched flights with arrows, elevator X, top landing/shaft split, tiny labels.
4. Confirm no console errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: draw staircase cage subdivision overlay (flights, landings, elevator, shaft)"
```

---

## Self-Review Notes

**Spec coverage:** §3 layout fractions → Task 3 constants (`X_FLIGHT1`, `X_FLIGHTS`, `Y_BOTTOM`, `Y_MID_TOP` — 120/400, 240/400, 150/550, 400/550 match 240|160 columns and 150/250/150 rows). §4.1 constants → Task 2. §4.2 per-mode width/depth semantics → Task 2 (corner/center: X/Y; edge: along-edge/inward) + Task 1 (concave corner: per-edge axis rule). §4.3 proportional overlay → Task 3 (fractions of actual bbox). §5 larger cage → no task needed (accepted consequence). §6 out-of-scope items → none implemented; `cage_size_m` kept accepted-but-ignored (Task 2 Step 3g docstring). §8 tests → Tasks 1-2 pytest + Task 3 Playwright.

**Type consistency:** `_place_cage_by_mode(polygon, mode, width, depth, preferred_corner=None)` used identically in Task 2's tests and implementation; `corner_cage(polygon, corner, width, depth)` matches between Task 1's definition and Task 2's `_build_cage` forwarding.

**Placeholder scan:** clean — every code step carries complete code; Task 2 Step 4's "inspect each" fallout instruction names the concrete decision rule (existence/count assertions stay, hardcoded-square-dimension assertions update).
