# Wall Thickness Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute and render real wall thickness (40cm exterior, 20cm interior) as a purely additive derived layer, without changing any existing geometry-generating logic.

**Architecture:** New standalone module `services/wall_geometry.py` derives net (usable) polygons and wall bands from already-generated axis geometry using Shapely `buffer`/`difference`/`union` — no per-edge custom offset code needed, because every cell's own edge is exactly 10cm from its interior face regardless of wall type (spec §3). `ApartmentCell` gains a `net_area_m2` field populated at generation time; the API and frontend surface it plus a new `wall_bands` field, without touching WT rules, `unit_mix.py`'s cutting targets, or solar analysis. Separately, `CAGE_WIDTH_M`/`CAGE_DEPTH_M` grow by 20cm (now clear dimensions, not axis) since that's a two-constant change; `corridor_width_m` stays axis-based, deferred to the next project. A pre-existing fabricated WT citation (`§94 ust.2` for room width) gets corrected to `code="heurystyka"` as an unrelated, small, explicitly-flagged fix.

**Tech Stack:** FastAPI + Shapely 2.x (backend), Next.js/TypeScript + react-konva (frontend), pytest.

## Global Constraints

- `WALL_EXTERIOR_THICKNESS_M = 0.40`, `WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M = 0.10`, `WALL_INTERIOR_THICKNESS_M = 0.20`, `NET_SHRINK_M = 0.10` — exact names/values (spec §4).
- `net_polygon(polygon) = polygon.buffer(-NET_SHRINK_M, join_style="mitre")` — exact formula (spec §3).
- No changes to `bsp.py`, `unit_mix.py`'s cutting logic, `circulation.py`'s `_build_corridor`/`_corridor_centerline`, `wt_validation.py`'s numeric thresholds, or `solar_analysis.py` — this phase only ADDS a derived reporting/rendering layer (spec §2).
- Exception: `CAGE_WIDTH_M`/`CAGE_DEPTH_M` in `circulation.py` change from `4.0`/`5.5` to `4.2`/`5.7` (spec §6/§6a) — this is the one place existing values change.
- `wszystkie_komórki` for `interior_wall_bands` = all `ApartmentCell.polygon` + `circulation_geometry`, explicitly EXCLUDING `LayoutResult.leftover` (spec §3).

---

## File Structure

- Create `backend/services/wall_geometry.py` — the new computational module (net_polygon, exterior_wall_band, interior_wall_bands).
- Test `backend/tests/test_wall_geometry.py` — new file for the above.
- Modify `backend/services/layout.py` — `ApartmentCell.net_area_m2` field.
- Modify `backend/services/unit_mix.py` — populate `net_area_m2` when constructing cells.
- Modify `backend/services/circulation.py` — bump `CAGE_WIDTH_M`/`CAGE_DEPTH_M`.
- Modify `backend/tests/test_circulation.py` — update `test_cage_constants_match_spec`.
- Modify `backend/api/v1/endpoints/layout.py` — `ApartmentResult.net_area_m2`, `LayoutGenerateResponse.wall_bands`, wiring in `layout_result_to_response()`.
- Test `backend/tests/test_layout_generate_endpoint.py` or nearest existing endpoint test file — new assertions for the added fields.
- Modify `frontend/app/lib/api.ts` — matching TS types.
- Modify `frontend/app/CanvasEditor.tsx` — wall bands layer + net-area label.
- Modify `backend/services/wt_validation.py` and `backend/services/apartment_validation.py` — §9's citation fix.
- Modify `backend/tests/test_wt_validation.py` and `backend/tests/test_validate.py` — fallout from the citation fix.

---

### Task 1: `wall_geometry.py` — net polygons and wall bands

**Files:**
- Create: `backend/services/wall_geometry.py`
- Test: `backend/tests/test_wall_geometry.py`

**Interfaces:**
- Consumes: nothing new (pure Shapely).
- Produces: `net_polygon(polygon: Polygon) -> Polygon`, `exterior_wall_band(footprint: Polygon) -> Polygon`, `interior_wall_bands(footprint: Polygon, cells: list[Polygon]) -> Polygon`, plus constants `WALL_EXTERIOR_THICKNESS_M`, `WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M`, `WALL_INTERIOR_THICKNESS_M`, `NET_SHRINK_M` — consumed by Task 2 (`unit_mix.py`) and Task 4 (API layer).

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_wall_geometry.py (new file)

from shapely.geometry import Polygon

from services.wall_geometry import (
    NET_SHRINK_M,
    WALL_EXTERIOR_THICKNESS_M,
    WALL_INTERIOR_THICKNESS_M,
    exterior_wall_band,
    interior_wall_bands,
    net_polygon,
)


def test_constants_match_spec():
    """Spec 2026-07-04 (wall-thickness) §4 -- pins the exact approved values."""
    assert WALL_EXTERIOR_THICKNESS_M == 0.40
    assert WALL_INTERIOR_THICKNESS_M == 0.20
    assert NET_SHRINK_M == 0.10


def test_net_polygon_shrinks_uniformly_by_10cm():
    rect = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    net = net_polygon(rect)
    minx, miny, maxx, maxy = net.bounds
    assert abs(minx - 0.10) < 1e-9
    assert abs(miny - 0.10) < 1e-9
    assert abs(maxx - 9.90) < 1e-9
    assert abs(maxy - 5.90) < 1e-9


def test_net_polygon_too_small_returns_empty_not_crash():
    tiny = Polygon([(0, 0), (0.15, 0), (0.15, 0.15), (0, 0.15)])
    net = net_polygon(tiny)
    assert net.is_empty


def test_exterior_wall_band_area_matches_perimeter_times_thickness():
    # 10x6 rectangle: perimeter 32m. Band = footprint.buffer(0.30) - footprint.buffer(-0.10),
    # i.e. a ring of outer width 0.30 and inner width 0.10 around all 4 sides plus
    # 4 corner squares (mitred join) -- for a rectangle the exact area is:
    # (10+0.6)*(6+0.6) - (10-0.2)*(6-0.2) computed directly below, not approximated.
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    band = exterior_wall_band(footprint)
    expected_area = (10 + 0.6) * (6 + 0.6) - (10 - 0.2) * (6 - 0.2)
    assert abs(band.area - expected_area) < 1e-6


def test_interior_wall_bands_between_two_adjacent_rectangles():
    footprint = Polygon([(0, 0), (10, 0), (10, 6), (0, 6)])
    cell_a = Polygon([(0, 0), (5, 0), (5, 6), (0, 6)])
    cell_b = Polygon([(5, 0), (10, 0), (10, 6), (5, 6)])
    bands = interior_wall_bands(footprint, [cell_a, cell_b])
    # The gap between the two cells' net polygons is exactly 0.20m wide (0.10
    # eaten from each side of the shared axis at x=5), spanning the shared
    # net-height (6 - 2*0.10 = 5.8m, since the top/bottom are footprint/exterior
    # edges shrunk by net_polygon the same way as the exterior envelope below).
    minx, miny, maxx, maxy = bands.bounds
    assert abs((maxx - minx) - 0.20) < 1e-6
    assert abs(minx - 4.90) < 1e-6
    assert abs(maxx - 5.10) < 1e-6
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wall_geometry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services.wall_geometry'`

- [ ] **Step 3: Implement `wall_geometry.py`**

```python
"""Silnik grubości ścian -- spec docs/superpowers/specs/2026-07-04-wall-
thickness-design.md. Czysto obliczeniowy: bierze już-gotową geometrię
(footprint, apartamenty, komunikację) i wyprowadza z niej powierzchnię
netto oraz pasy ścian do narysowania. NIE jest wywoływany w środku
generowania układu (place_circulation/subdivide_units) -- silnik istniejący
zostaje nietknięty (spec §2)."""

from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union

WALL_EXTERIOR_THICKNESS_M = 0.40
WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M = 0.10
"""Oś ściany zewnętrznej 10cm od lica wewnętrznego -> 30cm od lica
zewnętrznego (0.40 - 0.10). Spec §1/§4."""
WALL_INTERIOR_THICKNESS_M = 0.20
"""Oś ściany wewnętrznej na środku -> 10cm z każdej strony. Spec §1/§4."""
NET_SHRINK_M = 0.10
"""Wspólna stała dla obu typów ścian (spec §3): każda własna krawędź
komórki (mieszkania/korytarza/klatki) jest dokładnie 10cm od osi do lica
wewnętrznego, niezależnie czy to ściana zewnętrzna czy wewnętrzna."""


def net_polygon(polygon: Polygon) -> Polygon:
    """Powierzchnia netto (w świetle ścian) -- spec §3. Zwraca pustą
    geometrię (nie None, nie wyjątek) dla komórek zbyt małych, żeby
    przetrwać skurczenie o NET_SHRINK_M z każdej strony."""
    if polygon.is_empty or polygon.area < 1e-9:
        return Polygon()
    net = polygon.buffer(-NET_SHRINK_M, join_style="mitre")
    if net.is_empty or not net.is_valid or net.area < 1e-9:
        return Polygon()
    return net


def exterior_wall_band(footprint: Polygon) -> Polygon:
    """Pas ściany zewnętrznej wzdłuż całego obrysu -- spec §3."""
    exterior_envelope = footprint.buffer(
        WALL_EXTERIOR_THICKNESS_M - WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre"
    )
    interior_envelope = footprint.buffer(-WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre")
    return exterior_envelope.difference(interior_envelope)


def interior_wall_bands(footprint: Polygon, cells: list[Polygon]) -> Polygon:
    """Pasy ścian wewnętrznych między wszystkimi podanymi komórkami (i
    między komórkami a licem wewnętrznym obrysu) -- spec §3. `cells`
    powinno zawierać wszystkie ApartmentCell.polygon + circulation_geometry,
    świadomie BEZ LayoutResult.leftover (spec §3)."""
    interior_envelope = footprint.buffer(-WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre")
    nets = [net_polygon(c) for c in cells if c is not None and not c.is_empty]
    nets = [n for n in nets if not n.is_empty]
    if not nets:
        return interior_envelope
    covered = unary_union(nets)
    return interior_envelope.difference(covered)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wall_geometry.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/wall_geometry.py backend/tests/test_wall_geometry.py
git commit -m "feat: add wall_geometry module for net-area and wall-band computation"
```

---

### Task 2: `ApartmentCell.net_area_m2`

**Files:**
- Modify: `backend/services/layout.py:94-102` (`ApartmentCell` dataclass)
- Modify: `backend/services/unit_mix.py:131-138` (`fit_program_to_rectangles`)
- Test: `backend/tests/test_unit_mix.py`

**Interfaces:**
- Consumes: Task 1's `wall_geometry.net_polygon(polygon: Polygon) -> Polygon`.
- Produces: `ApartmentCell.net_area_m2: float` — consumed by Task 4 (API layer).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_unit_mix.py`:

```python
def test_fit_program_populates_net_area_m2():
    """Spec 2026-07-04 (wall-thickness) §5.1: every generated cell carries
    net_area_m2 = wall_geometry.net_polygon(cell.polygon).area, distinct
    from (smaller than) the axis-based polygon.area."""
    from services.wall_geometry import net_polygon

    rect = Polygon([(0, 0), (30, 0), (30, 6), (0, 6)])
    specs = [ApartmentSpec(type="M2", min_area_m2=40.0, target_count=1)]
    cells, _ = fit_program_to_rectangles([rect], specs)
    assert len(cells) == 1
    cell = cells[0]
    expected_net = net_polygon(cell.polygon).area
    assert abs(cell.net_area_m2 - expected_net) < 1e-9
    assert cell.net_area_m2 < cell.polygon.area
```

Confirm the file already imports `Polygon`, `ApartmentSpec`, and `fit_program_to_rectangles` (it does, per the existing tests in that file) — only the new import of `services.wall_geometry.net_polygon` needs adding, inline in the test as shown.

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_unit_mix.py -k net_area_m2 -v`
Expected: FAIL with `TypeError: ApartmentCell.__init__() got an unexpected keyword argument 'net_area_m2'` (once Step 3 below tries constructing it) — actually first confirm it fails with `AttributeError: 'ApartmentCell' object has no attribute 'net_area_m2'` since the field doesn't exist yet.

- [ ] **Step 3: Add the field to `ApartmentCell`**

In `backend/services/layout.py`, modify the dataclass (currently ends at line 102):

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
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian (wall_geometry.net_polygon(polygon).area)
    -- spec 2026-07-04 wall-thickness §5.1. Domyślnie 0.0 dla ścieżek, które
    jej nie liczą (np. ręczna edycja mieszkania przed ponownym przeliczeniem)."""
```

- [ ] **Step 4: Populate it in `unit_mix.py`**

In `backend/services/unit_mix.py`, add the import (near the top, alongside the existing `from services.layout import (...)`):

```python
from services.wall_geometry import net_polygon
```

Modify the `ApartmentCell` construction (lines 131-138):

```python
        cells.append(
            ApartmentCell(
                id=str(uuid.uuid4())[:8],
                type=spec.type,
                polygon=cell_poly,
                area_tolerance_exceeded=best_deviation > AREA_TOLERANCE,
                net_area_m2=net_polygon(cell_poly).area,
            )
        )
```

- [ ] **Step 5: Run tests to verify they pass, then full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_unit_mix.py -v`
Expected: all pass.
Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass (no other code constructs `ApartmentCell` with positional args past `area_tolerance_exceeded`, so the new defaulted field can't break existing callers — verify this holds if any test fails unexpectedly).

- [ ] **Step 6: Commit**

```bash
git add backend/services/layout.py backend/services/unit_mix.py backend/tests/test_unit_mix.py
git commit -m "feat: populate ApartmentCell.net_area_m2 from wall_geometry"
```

---

### Task 3: Cage dimensions become clear (not axis) — bump the two constants

**Files:**
- Modify: `backend/services/circulation.py` (the `CAGE_WIDTH_M`/`CAGE_DEPTH_M` constants added in the 2026-07-03 staircase-cage-rectangle plan)
- Modify: `backend/tests/test_circulation.py` (`test_cage_constants_match_spec`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `CAGE_WIDTH_M = 4.2`, `CAGE_DEPTH_M = 5.7` — no other task depends on the exact value, but nothing else in this plan touches these functions.

- [ ] **Step 1: Update the failing test first**

In `backend/tests/test_circulation.py`, find `test_cage_constants_match_spec` (added in the 2026-07-03 plan) and change its assertions:

```python
def test_cage_constants_match_spec():
    """Spec 2026-07-04 (wall-thickness) §6/§6a -- cage dimensions are now
    CLEAR (w świetle) dimensions from the user, with 20cm of wall added to
    get the axis-to-axis rectangle the placement functions actually build:
    4.0m clear + 0.20m wall = 4.2m axis width, 5.5m + 0.20m = 5.7m axis depth."""
    assert CAGE_WIDTH_M == 4.2
    assert CAGE_DEPTH_M == 5.7
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -k cage_constants_match_spec -v`
Expected: FAIL — `assert 4.0 == 4.2`

- [ ] **Step 3: Bump the constants**

In `backend/services/circulation.py`, find the existing constants (added 2026-07-03):

```python
CAGE_WIDTH_M = 4.2
CAGE_DEPTH_M = 5.7
"""Rzeczywisty obrys klatki schodowej: WYMIARY W ŚWIETLE (4.0x5.5m, spec
2026-07-03 staircase-cage-rectangle) + 20cm ściany wewnętrznej z każdej
strony (spec 2026-07-04 wall-thickness §6) = 4.2x5.7m rozstaw osi, który te
funkcje faktycznie budują: 2 biegi 120x250 + winda 160x250 + spoczniki/
korytarz 150 na górze i dole, W ŚWIETLE, plus zapas na ściany."""
```

- [ ] **Step 4: Run tests, then full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_circulation.py -v`
Expected: all pass — check specifically that no OTHER test in this file hardcodes `4.0`/`5.5`/`22.0` (the old 22m² area) as an expected cage dimension; if one does, update it to `4.2`/`5.7`/`23.94` (4.2×5.7) following the same reasoning as this task, and note which test in the commit message.

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "fix: cage dimensions are clear (w swietle), not axis -- grow CAGE_WIDTH_M/CAGE_DEPTH_M by 20cm"
```

---

### Task 4: API — `net_area_m2` and `wall_bands`

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Test: `backend/tests/test_layout_circulation_endpoint.py` (or wherever `/layout/generate` is already tested — search `grep -rn "post.*layout/generate" backend/tests/` if unsure; the plan assumes a test file exists that already POSTs to `/layout/generate` and inspects the response, e.g. `test_wt_validation.py::test_layout_generate_endpoint_exposes_wt_rules`)

**Interfaces:**
- Consumes: Task 1's `wall_geometry.exterior_wall_band`/`interior_wall_bands`, Task 2's `ApartmentCell.net_area_m2`.
- Produces: `ApartmentResult.net_area_m2: float`, `LayoutGenerateResponse.wall_bands: list[dict]` — consumed by Task 5 (frontend).

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_wt_validation.py` (reuses the existing `test_layout_generate_endpoint_exposes_wt_rules`'s pattern of POSTing to `/layout/generate`):

```python
def test_layout_generate_endpoint_exposes_net_area_and_wall_bands():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/layout/generate",
        json={
            "footprint": [[0, 0], [20, 0], [20, 20], [0, 20]],
            "circulation": {"corridor_width_m": 1.5, "cage_size_m": 3.0, "place_cage": True},
            "apartments": [
                {"type": "M2", "min_area_m2": 40.0, "target_count": 4},
            ],
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["apartments"]) >= 1
    for apt in data["apartments"]:
        assert "net_area_m2" in apt
        assert apt["net_area_m2"] < apt["area_m2"]
    assert "wall_bands" in data
    assert len(data["wall_bands"]) >= 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py -k net_area_and_wall_bands -v`
Expected: FAIL — `KeyError: 'net_area_m2'`

- [ ] **Step 3: Implement**

In `backend/api/v1/endpoints/layout.py`, add the import:

```python
from services.wall_geometry import exterior_wall_band, interior_wall_bands
```

Modify `ApartmentResult` (lines 43-47):

```python
class ApartmentResult(BaseModel):
    id: str
    type: str
    area_m2: float
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian -- spec 2026-07-04 wall-thickness §5.2."""
    geometry: dict
```

Modify `LayoutGenerateResponse` (lines 64-77), add one field:

```python
    wall_bands: list[dict] = []
    """Pasy ścian (zewnętrzne + wewnętrzne), GeoJSON, do narysowania na
    płótnie -- spec 2026-07-04 wall-thickness §5.2."""
```

Modify `layout_result_to_response()` (lines 126-165): update `apartments_out` to include `net_area_m2`, and compute `wall_bands`:

```python
    apartments_out = [
        ApartmentResult(
            id=a.id,
            type=a.type,
            area_m2=a.polygon.area,
            net_area_m2=a.net_area_m2,
            geometry=json.loads(json.dumps(a.polygon.__geo_interface__)),
        )
        for a in layout.apartments
    ]

    wall_cells = [a.polygon for a in layout.apartments]
    if layout.circulation_geometry is not None:
        wall_cells.append(layout.circulation_geometry)
    wall_geoms = [exterior_wall_band(layout.footprint)]
    if wall_cells:
        wall_geoms.append(interior_wall_bands(layout.footprint, wall_cells))
    wall_bands_out = [g for geom in wall_geoms for g in _decompose_to_polygons(geom)]
```

And add `wall_bands=wall_bands_out` to the returned `LayoutGenerateResponse(...)` call (alongside the existing `cage_geometries=...` line).

- [ ] **Step 4: Run tests, then full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py -v`
Expected: all pass.
Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_wt_validation.py
git commit -m "feat: expose net_area_m2 and wall_bands on /layout/generate"
```

---

### Task 5: Frontend — render wall bands + net-area label

**Files:**
- Modify: `frontend/app/lib/api.ts`
- Modify: `frontend/app/CanvasEditor.tsx`

**Interfaces:**
- Consumes: Task 4's `net_area_m2`/`wall_bands` fields.
- Produces: nothing consumed later — final visual layer.

- [ ] **Step 1: Add TS types**

In `frontend/app/lib/api.ts`, modify `ApartmentResult`:

```typescript
export interface ApartmentResult {
  id: string;
  type: string;
  area_m2: number;
  net_area_m2: number;
  geometry: GeoJsonPolygon;
}
```

Modify `LayoutGenerateResponse` (add one field, matching the existing `cage_geometries: GeoJsonPolygon[];` line's style):

```typescript
  wall_bands: GeoJsonPolygon[];
```

- [ ] **Step 2: Typecheck to find call sites needing updates**

Run: `cd frontend && npx tsc --noEmit 2>&1 | head -50`
Expected: any errors point at places constructing a `LayoutGenerateResponse`-shaped object by hand (e.g. `runSubdivideUnits` in `SessionContext.tsx`, which builds one from `/layout/units` + `/layout/circulation` responses) — add `net_area_m2: 0` per apartment (that path doesn't have wall data yet, `0` matches the backend's own default-for-unpopulated-paths convention from Task 2) and `wall_bands: []` there. Fix each reported site, re-run until clean.

- [ ] **Step 3: Add canvas theme colors**

In `frontend/app/CanvasEditor.tsx`, extend the `canvasColors` object (the same one with `outline`/`outlineFill` per theme) — add a `wallFill` entry to both the dark and light branches:

```typescript
          wallFill: "rgba(161,161,170,0.45)",
```

(dark branch) and

```typescript
          wallFill: "rgba(82,82,91,0.35)",
```

(light branch) — placed as a new line alongside the existing `outline`/`outlineFill` entries in each branch.

- [ ] **Step 4: Render the wall bands layer**

Directly after the existing `{/* Obrys */}` footprint-rendering block (search for that comment), before the apartments/corridor/cage rendering, add:

```tsx
          {/* Ściany -- pasy zewn./wewn., spec 2026-07-04 wall-thickness */}
          {(state.layoutResult?.wall_bands ?? []).map((geom, i) => (
            <Line
              key={`wall-${i}`}
              points={toCanvasPoints(ringToPoints(geom))}
              closed
              fill={canvasColors.wallFill}
              listening={false}
            />
          ))}
```

- [ ] **Step 5: Add the net-area label on the selected apartment**

Find the existing apartment-rendering `.map()` block (renders each `apt` with `colors`/`isSelected`/etc.). Directly after that `<Line>` element (inside the same `.map()` callback, same returned fragment/group — check whether apartments are currently returned as a bare `<Line>` or wrapped in a `<Group>`; if bare, wrap in a `<Group key={apt.id}>` containing both the existing `<Line>` and the new `<Text>` below, adjusting the existing element's own `key` prop accordingly since the Group now owns it), add:

```tsx
              {isSelected && (
                <Text
                  x={center.x * METER_PX}
                  y={-center.y * METER_PX}
                  text={`${apt.net_area_m2.toFixed(1)} m² netto`}
                  fontSize={11 / scale}
                  fill="#ffffff"
                  fontStyle="bold"
                  shadowColor="#000000"
                  shadowBlur={4}
                  listening={false}
                  offsetX={30 / scale}
                />
              )}
```

(`center` is already computed in this block for the existing hover/tooltip logic — reuse it, don't recompute.)

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no output.

- [ ] **Step 7: Manual verification with Playwright**

Start backend (`backend/.venv/Scripts/python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`) and frontend (`NEXT_PUBLIC_API_URL="http://localhost:8000/api/v1" npm run dev -- --port 3010`; kill/restart either if already running from a prior session — check with curl first). Using Playwright (reuse the session's established zoom-out-before-drawing + "Zamknij obrys" button pattern): draw a rectangle footprint, click "Generuj układ", screenshot — confirm a visible wall band traces the building perimeter and internal apartment divisions. Click an apartment, screenshot — confirm the "X.X m² netto" label appears and shows a smaller number than the apartment's filled area would suggest. No console errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/app/lib/api.ts frontend/app/CanvasEditor.tsx
git commit -m "feat: render wall bands and net-area label on canvas"
```

---

### Task 6: Fix fabricated WT §94 ust.2 citation (spec §9)

**Files:**
- Modify: `backend/services/wt_validation.py`
- Modify: `backend/services/apartment_validation.py`
- Modify: `backend/tests/test_wt_validation.py`
- Modify: `backend/tests/test_validate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks in this plan (independent finding, bundled here per spec §9 rather than a separate plan).
- Produces: `_rule_room_width()`'s `WTRule.code` changes from `"§94 ust.2"` to `"heurystyka"` — no other task depends on this code value.

- [ ] **Step 1: Update the two fallout tests first**

In `backend/tests/test_wt_validation.py`, change `test_all_rules_present_and_scored` (currently asserts the codes set):

```python
def test_all_rules_present_and_scored():
    layout = _layout(SQUARE_20, corridor_width_m=2.0, cage_size_m=3.0, place_cage=True)
    result = validate_layout_wt(layout)
    codes = {r.code for r in result.rules}
    # §94 ust.2 (room width) is not a real WT paragraph -- only §94 ust.1
    # (min. apartment area) exists; room width is now code="heurystyka"
    # like the other non-statutory checks (spec 2026-07-04 wall-thickness §9).
    assert codes == {"§94 ust.1", "§64", "§68 ust.1", "§58 ust.4", "heurystyka"}
    assert 0 <= result.score <= 100
    assert result.passed == all(r.passed for r in result.rules)
```

And `test_room_width_rule_fails_for_narrow_apartment` (currently looks up by `r.code == "§94 ust.2"`, which no longer uniquely identifies the rule once its code becomes the shared `"heurystyka"` value):

```python
def test_room_width_rule_fails_for_narrow_apartment():
    narrow_apt = ApartmentCell(
        id="narrow", type="1-room", polygon=Polygon([(0, 0), (30, 0), (30, 1.5), (0, 1.5)])
    )
    layout = _layout(SQUARE_20, apartments=[])
    layout.apartments.append(narrow_apt)
    result = validate_layout_wt(layout)
    width_rule = next(r for r in result.rules if r.description == "Min. szerokość pokoju")
    assert width_rule.passed is False
    assert f"< {MIN_ROOM_WIDTH_M}" in width_rule.detail
```

In `backend/tests/test_validate.py`, update the codes set and its explanatory comment:

```python
    # 7 rules: the 5 unique codes below (heurystyka now shared by 3 rules --
    # circulation_utilization, cage_facade_contact, and room_width, since
    # none of them are real WT paragraphs -- spec 2026-07-04 wall-thickness
    # §9) + the extra cage-facade-contact rule, same "heurystyka" code as
    # circulation_utilization's, so the CODE set stays 5 unique values even
    # though the rule COUNT is 7.
    assert len(data["wt_rules"]) == 7
    assert {r["code"] for r in data["wt_rules"]} == {
        "§94 ust.1",
        "§64",
        "§68 ust.1",
        "§58 ust.4",
        "heurystyka",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py backend/tests/test_validate.py -v`
Expected: FAIL — the codes-set assertions now expect 5 values but the code still produces `"§94 ust.2"` (6 values), and the `next(...)` lookup by description finds nothing yet since the rule's `description` field also needs checking (see Step 3 — confirm it's already exactly `"Min. szerokość pokoju"`, which it is per the current code, so only `code` changes).

- [ ] **Step 3: Fix `_rule_room_width` in `wt_validation.py`**

```python
def _rule_room_width(layout: LayoutResult) -> WTRule:
    """Heurystyka (NIE WT): min. szerokość pokoju. §94 reguluje WYŁĄCZNIE
    minimalną powierzchnię mieszkania (ust.1, 25m2) -- nie ma żadnego
    "ust.2" o szerokości pokoju. Wartość MIN_ROOM_WIDTH_M to własna wiedza
    projektowa, nie przepis (poprawka 2026-07-04, spec wall-thickness §9,
    ten sam wzorzec co MIN_CAGE_FACADE_CONTACT_M)."""
    failing = [
        f"{apt.id}: {_apartment_min_width(apt):.2f} m < {MIN_ROOM_WIDTH_M} m"
        for apt in layout.apartments
        if _apartment_min_width(apt) < MIN_ROOM_WIDTH_M
    ]
    passed = not failing
    detail = (
        f"Wszystkie mieszkania spełniają zalecaną min. szerokość pokoju ({MIN_ROOM_WIDTH_M} m, heurystyka nie-WT)."
        if passed
        else "Mieszkania poniżej zalecanej szerokości pokoju (heurystyka nie-WT): " + "; ".join(failing)
    )
    return WTRule(code="heurystyka", description="Min. szerokość pokoju", passed=passed, detail=detail)
```

Also update the constant's own comment (line 31):

```python
MIN_ROOM_WIDTH_M = 2.4
"""Zalecana min. szerokość pokoju -- NIE jest to wymóg WT (prawdziwy §94
reguluje wyłącznie min. powierzchnię mieszkania, ust.1). Własna wiedza
projektowa, poprawka 2026-07-04 (wcześniej błędnie oznaczone "§94 ust.2")."""
```

- [ ] **Step 4: Fix `apartment_validation.py`**

Update the module docstring line (`- apartment-level checks (area §94 ust.1, room width §94 ust.2) — this module`) to:

```
- apartment-level checks (area §94 ust.1 -- real WT; room width -- design
  heuristic, not WT, see wt_validation.py's MIN_ROOM_WIDTH_M) — this module
```

Update the constant (currently `MIN_ROOM_WIDTH_M = 2.4  # WT §94 ust. 2`):

```python
MIN_ROOM_WIDTH_M = 2.4  # Zalecana szerokość, NIE wymóg WT (patrz wt_validation.py)
```

Update `validate_apartment()`'s docstring (`"""Validate a single apartment cell against area (§94 ust. 1) and width (§94 ust. 2)."""`) to:

```python
    """Validate a single apartment cell against area (§94 ust. 1, real WT)
    and width (design heuristic, not WT -- see MIN_ROOM_WIDTH_M above)."""
```

And the error-message text this function builds (`f"{apt.id}: szerokość {width:.2f} m < {MIN_ROOM_WIDTH_M} m (WT §94 ust. 2)."`) drops the false "WT" framing:

```python
            f"{apt.id}: szerokość {width:.2f} m < {MIN_ROOM_WIDTH_M} m (zalecana min. szerokość, nie WT)."
```

- [ ] **Step 5: Run tests, then full suite**

Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_wt_validation.py backend/tests/test_validate.py -v`
Expected: all pass.
Run: `backend/.venv/Scripts/python.exe -m pytest backend/tests/ -v`
Expected: all pass. Grep for any remaining test asserting `"§94 ust.2"` or `"WT §94 ust. 2"` in a detail string (`grep -rn "94 ust" backend/tests/`) and update if found.

- [ ] **Step 6: Commit**

```bash
git add backend/services/wt_validation.py backend/services/apartment_validation.py backend/tests/test_wt_validation.py backend/tests/test_validate.py
git commit -m "fix: correct fabricated WT §94 ust.2 citation for room-width heuristic"
```

---

## Self-Review Notes

**Spec coverage:** §3 formula → Task 1. §4 module/constants → Task 1. §5.1 `ApartmentCell` field → Task 2. §5.2 API fields → Task 4. §5.3 frontend rendering → Task 5. §6/§6a cage constants → Task 3. §9 citation fix → Task 6. §7 (roadmap) and §8 test list are covered across all tasks' test steps.

**Placeholder scan:** clean — every step has complete code; Task 4's Step 2 "Expected: FAIL" note and Task 3/6's fallout-test instructions name the exact assertion values rather than saying "update as needed."

**Type consistency:** `net_area_m2` name and type (`float`) identical across `ApartmentCell` (Task 2), `ApartmentResult` (Task 4), and the TS `ApartmentResult` interface (Task 5). `wall_bands` identical across `LayoutGenerateResponse` (Task 4) and its TS counterpart (Task 5). `wall_geometry.net_polygon`/`exterior_wall_band`/`interior_wall_bands` signatures match between Task 1's definition and Task 2/4's call sites.
