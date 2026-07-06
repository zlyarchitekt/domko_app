# Corridor Net-Shrink + Iterations Right-Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two independent fixes reported by the user after live-testing the apartment-type-colors feature: (1) the corridor/cage-circulation fill still overlaps wall bands the same way apartments used to — apply the same net-geometry (wall-shrunk) treatment already shipped for apartments; (2) the cage/apartment iteration lists are buried inside the left sidebar's tab panels — move them into a dedicated new right-side sidebar.

**Architecture:** Corridor fix mirrors the apartment `net_geometry` pattern shipped in the previous plan (`docs/superpowers/plans/2026-07-06-apartment-type-colors.md`): reuse `services/wall_geometry.net_polygon()`, add a sibling `_net` field next to every existing `circulation_geometry` field across all 4 backend response models, and make the frontend prefer the net variant with a raw-geometry fallback. Sidebar fix extracts the two already-working iteration-list JSX blocks (cage iterations in `CirculationSection.tsx`, unit iterations in `ProgramSection.tsx`) verbatim into a new `IterationsSidebar.tsx`, rendered as a new flex sibling in `page.tsx`.

**Tech Stack:** FastAPI + Pydantic + Shapely (backend), Next.js + React + Tailwind (frontend). No new dependencies.

## Global Constraints

- `NET_SHRINK_M = 0.10` (backend/services/wall_geometry.py:19) — do not hardcode this value anywhere; import the constant if a numeric literal is ever needed in a test.
- `net_polygon(polygon)` (backend/services/wall_geometry.py:25) works on both `Polygon` and `MultiPolygon` inputs (plain shapely `.buffer()`, no type-specific logic) — safe to call on `circulation_geometry` directly without a geom_type guard beforehand.
- `_net_geometry_json(polygon)` (backend/api/v1/endpoints/layout.py:459) already exists (apartment-colors plan) and returns `None` when the shrunk result is empty OR not a simple `Polygon` (i.e. it collapsed into a `MultiPolygon`). Reuse it verbatim for every single-object corridor field in this plan — do not write a second near-duplicate helper.
- `_decompose_to_polygons(geom)` (backend/api/v1/endpoints/layout.py:344) already splits a `Polygon`/`MultiPolygon`/`None` into a JSON-safe `list[dict]` of simple polygons. For the one LIST-shaped surface in this plan (`LayoutGenerateResponse.circulation_parts`), call it on the ALREADY-shrunk geometry (`_decompose_to_polygons(net_polygon(geom))`) rather than shrinking each decomposed part separately — one shrink-then-split, not split-then-shrink-each.
- Dual-surface gotcha (recurring theme in this repo, see project memory `gotcha_dual_layout_api_surface.md`): a `circulation_geometry` field exists on FOUR separate Pydantic response models in `backend/api/v1/endpoints/layout.py` — `CirculationResponse` (:493, shared by 3 endpoints: `/circulation`, `/circulation/move-cage`, `/circulation/add-manual`), `ReshapeCirculationResponse` (:813, `/circulation/reshape`), `CageIterationMetaResult` (:65, embedded in both `CirculationResponse.cage_iterations` and `LayoutGenerateResponse.cage_iterations` via the single shared `_serialize_cage_iteration` helper at :435), and `LayoutGenerateResponse.circulation_parts` (:168, a decomposed LIST, not a single object, populated by the shared `layout_result_to_response` at :300 which is also reused by `api/v1/endpoints/optimizer.py`). Task 1 below touches all of these — miss one and that one surface silently keeps showing the raw (wall-overlapping) corridor fill.
- Frontend fallback contract, mirroring the apartment pattern exactly: every net field is optional/nullable (`T | null | undefined`); the frontend always falls back to the existing raw field when the net field is absent, never crashes or renders nothing.
- No automated frontend tests exist in this repo; `cd frontend && npx tsc --noEmit` (exit 0) is the verification bar for every frontend task.
- Backend verification bar: `cd backend && ./.venv/Scripts/python.exe -m pytest -q` (exit 0, no regressions in the existing 233+ tests) plus new tests for the new behavior.
- Git hygiene: every task stages ONLY the files it names, by name. Never `git add -A` or `git add .`.

---

### Task 1: Backend — corridor net-geometry on all 4 response surfaces

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
  - `CirculationResponse` model (:493-506)
  - `ReshapeCirculationResponse` model (:813-818)
  - `CageIterationMetaResult` model (:65-79)
  - `LayoutGenerateResponse` model (:160-199)
  - `_serialize_cage_iteration` (:435-456)
  - `layout_result_to_response` (:276-...; construction site :300-..., specifically the `circulation_parts=` line at :319)
  - `place_circulation_endpoint` (`/circulation`, construction site :587-602)
  - `reshape_circulation_endpoint` (`/circulation/reshape`, construction site :849-858)
  - `move_cage_endpoint` (`/circulation/move-cage`, construction site :917-926)
  - `add_manual_element_endpoint` (`/circulation/add-manual`, construction site :1013-1022)
- Test: `backend/tests/test_layout_circulation_endpoint.py`, `backend/tests/test_layout.py`, `backend/tests/test_cage_placement.py`

**Interfaces:**
- Consumes: `net_polygon` (already imported in this file, `from services.wall_geometry import exterior_wall_band, interior_wall_bands, net_polygon` :17), `_net_geometry_json` (already defined in this file, :459), `_decompose_to_polygons` (already defined, :344).
- Produces: `circulation_geometry_net: dict | None` on `CirculationResponse`, `ReshapeCirculationResponse`, `CageIterationMetaResult`; `circulation_parts_net: list[dict]` on `LayoutGenerateResponse`.

Before starting, re-read the CURRENT content at every line range above with the Read tool — this plan was written against `main` at commit `e57e479`; verify no drift before editing (this repo has had many same-day commits).

- [ ] **Step 1: Add `circulation_geometry_net` field to `CirculationResponse`**

At `backend/api/v1/endpoints/layout.py:493-506`, current code:

```python
class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) -- spec §4."""
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""
    cage_iterations: list[CageIterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego (puste w trybie klasycznym,
    cage_iterations=0) -- spec 2026-07-04-cage-placement-iterations §4."""
    cage_best_seed: int = 0
    """Seed zwycięskiej iteracji (0 w trybie klasycznym)."""
```

Replace the first line with:

```python
class CirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Poligon korytarza+klatki w świetle ścian (wall_geometry.net_polygon) --
    spec 2026-07-06 corridor-net-shrink §1. None gdy netto puste albo nie jest
    prostym Polygonem; front spada wtedy na `circulation_geometry` (surowy)."""
    cage_geometries: list[dict] = []
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) -- spec §4."""
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""
    cage_iterations: list[CageIterationMetaResult] = []
    """Metadane 1 na iterację trybu iteracyjnego (puste w trybie klasycznym,
    cage_iterations=0) -- spec 2026-07-04-cage-placement-iterations §4."""
    cage_best_seed: int = 0
    """Seed zwycięskiej iteracji (0 w trybie klasycznym)."""
```

- [ ] **Step 2: Populate it at all 3 `CirculationResponse` construction sites**

At `backend/api/v1/endpoints/layout.py:587-602` (`/circulation`), current code:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

Insert a `circulation_geometry_net=` line immediately after the `circulation_geometry=` block:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None
            else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

At `backend/api/v1/endpoints/layout.py:917-926` (`/circulation/move-cage`), current code:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

Apply the same insertion:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

At `backend/api/v1/endpoints/layout.py:1013-1022` (`/circulation/add-manual`), current code:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

Same insertion again:

```python
    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
```

- [ ] **Step 3: Add + populate `circulation_geometry_net` on `ReshapeCirculationResponse`**

At `backend/api/v1/endpoints/layout.py:813-818`, current code:

```python
class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""
```

Replace with:

```python
class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Jak CirculationResponse.circulation_geometry_net -- spec 2026-07-06
    corridor-net-shrink §1."""
    remainder: dict
    centerline: list[CenterlineSegmentResult] = []
    evacuation_dots: list[EvacuationDotResult] = []
    """Kropki ewakuacyjne co 1m wzdłuż osi -- spec 2026-07-04-evacuation-dots."""
```

At `backend/api/v1/endpoints/layout.py:849-858`, current code:

```python
    return ReshapeCirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )
```

Replace with:

```python
    return ReshapeCirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None
            else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(result.circulation_geometry)
            if result.circulation_geometry is not None
            else None
        ),
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )
```

- [ ] **Step 4: Add + populate `circulation_geometry_net` on `CageIterationMetaResult`**

At `backend/api/v1/endpoints/layout.py:65-79`, current code:

```python
class CageIterationMetaResult(BaseModel):
    seed: int
    score: float
    cages_count: int
    components: dict[str, float] = {}
    cage_geometries: list[dict] = []
    circulation_geometry: dict | None = None
    centerline: list["CenterlineSegmentResult"] = []
    evacuation_dots: list["EvacuationDotResult"] = []
    remainder: dict | None = None
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) TEJ konkretnej
    iteracji -- puste gdy manual_corridors nie podano przy serializacji
    (np. z /layout/generate, który nie ma warnings na top-levelu),
    naprawa Finding 2 (Etap 5 review)."""
```

Replace with:

```python
class CageIterationMetaResult(BaseModel):
    seed: int
    score: float
    cages_count: int
    components: dict[str, float] = {}
    cage_geometries: list[dict] = []
    circulation_geometry: dict | None = None
    circulation_geometry_net: dict | None = None
    """Jak CirculationResponse.circulation_geometry_net, per iteracja --
    spec 2026-07-06 corridor-net-shrink §1."""
    centerline: list["CenterlineSegmentResult"] = []
    evacuation_dots: list["EvacuationDotResult"] = []
    remainder: dict | None = None
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) TEJ konkretnej
    iteracji -- puste gdy manual_corridors nie podano przy serializacji
    (np. z /layout/generate, który nie ma warnings na top-levelu),
    naprawa Finding 2 (Etap 5 review)."""
```

At `backend/api/v1/endpoints/layout.py:435-456` (`_serialize_cage_iteration` — the ONE shared helper used by both `/circulation`'s `cage_iterations=` list and `/generate`'s `cage_iterations=` list), current code:

```python
def _serialize_cage_iteration(m, manual_corridors: list | None = None) -> "CageIterationMetaResult":
    return CageIterationMetaResult(
        seed=m.seed, score=m.score, cages_count=m.cages_count, components=m.components,
        cage_geometries=(
            [json.loads(json.dumps(c.__geo_interface__)) for c in m.result.cage_polygons]
            if m.result is not None else []
        ),
        circulation_geometry=(
            json.loads(json.dumps(m.result.circulation_geometry.__geo_interface__))
            if m.result is not None and m.result.circulation_geometry is not None else None
        ),
        centerline=_serialize_centerline(m.result.centerline) if m.result is not None else [],
        evacuation_dots=_serialize_dots(m.result.evacuation_dots) if m.result is not None else [],
        remainder=(
            json.loads(json.dumps(m.result.remainder.__geo_interface__))
            if m.result is not None else None
        ),
        warnings=(
            _compute_manual_corridor_warnings(manual_corridors, m.result.cage_polygons)
            if manual_corridors is not None and m.result is not None else []
        ),
    )
```

Replace with:

```python
def _serialize_cage_iteration(m, manual_corridors: list | None = None) -> "CageIterationMetaResult":
    return CageIterationMetaResult(
        seed=m.seed, score=m.score, cages_count=m.cages_count, components=m.components,
        cage_geometries=(
            [json.loads(json.dumps(c.__geo_interface__)) for c in m.result.cage_polygons]
            if m.result is not None else []
        ),
        circulation_geometry=(
            json.loads(json.dumps(m.result.circulation_geometry.__geo_interface__))
            if m.result is not None and m.result.circulation_geometry is not None else None
        ),
        circulation_geometry_net=(
            _net_geometry_json(m.result.circulation_geometry)
            if m.result is not None and m.result.circulation_geometry is not None else None
        ),
        centerline=_serialize_centerline(m.result.centerline) if m.result is not None else [],
        evacuation_dots=_serialize_dots(m.result.evacuation_dots) if m.result is not None else [],
        remainder=(
            json.loads(json.dumps(m.result.remainder.__geo_interface__))
            if m.result is not None else None
        ),
        warnings=(
            _compute_manual_corridor_warnings(manual_corridors, m.result.cage_polygons)
            if manual_corridors is not None and m.result is not None else []
        ),
    )
```

- [ ] **Step 5: Add + populate `circulation_parts_net` on `LayoutGenerateResponse`**

At `backend/api/v1/endpoints/layout.py:160-199`, find:

```python
    circulation_parts: list[dict] = []
    """Corridor+cage geometry, decomposed into individual Polygon parts (may be
    a MultiPolygon internally — e.g. both sides of a double-loaded corridor),
    for frontend rendering (F2-07)."""
```

Insert immediately after it:

```python
    circulation_parts_net: list[dict] = []
    """circulation_parts w świetle ścian (net_polygon na całej geometrii przed
    dekompozycją) -- spec 2026-07-06 corridor-net-shrink §1. Front: gdy
    niepusta, renderuje TĘ listę zamiast circulation_parts."""
```

At `backend/api/v1/endpoints/layout.py:300-...` (`layout_result_to_response`, shared with `optimizer.py`), find:

```python
        circulation_parts=_decompose_to_polygons(layout.circulation_geometry),
```

Replace with:

```python
        circulation_parts=_decompose_to_polygons(layout.circulation_geometry),
        circulation_parts_net=(
            _decompose_to_polygons(net_polygon(layout.circulation_geometry))
            if layout.circulation_geometry is not None else []
        ),
```

- [ ] **Step 6: Write tests verifying REAL shrink (not tautological) and dual-surface presence**

Add to `backend/tests/test_layout_circulation_endpoint.py` (append at end of file; if this exact file doesn't exist, add these to `backend/tests/test_circulation.py` instead — check which file already has the FastAPI `TestClient`-based `/circulation` endpoint tests referenced in Global Constraints and follow that file's existing fixture/helper conventions for building a valid footprint+circulation request):

```python
def test_circulation_endpoint_net_geometry_is_actually_smaller(client, valid_circulation_request):
    """circulation_geometry_net must be a REAL shrink, not just present --
    Task 1 review of the apartment-colors plan caught a sibling bug where new
    tests only checked field type/presence, never that the polygon actually
    shrank (see .superpowers/sdd/progress.md, Task 1 fix f484e8e)."""
    from shapely.geometry import shape

    response = client.post("/api/v1/layout/circulation", json=valid_circulation_request)
    assert response.status_code == 200
    body = response.json()

    assert body["circulation_geometry"] is not None
    assert body["circulation_geometry_net"] is not None

    raw_area = shape(body["circulation_geometry"]).area
    net_area = shape(body["circulation_geometry_net"]).area
    assert net_area < raw_area
```

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py -k net_geometry -v` (adjust path to wherever you actually added the test per the file-existence check above)
Expected: FAIL (`KeyError: 'circulation_geometry_net'` or similar) before Steps 1-2, PASS after.

If a `client`/`valid_circulation_request` fixture does not already exist in the target test file, do not invent one from scratch — grep the target file for the existing `/circulation` POST test (there is at least one, referenced in Global Constraints) and reuse its exact request-building pattern inline instead of adding new fixtures.

Now add a dual-surface generate-endpoint test to `backend/tests/test_layout.py` (append near the existing circulation-area tests, e.g. near the `test_layout.py:112-113` area referenced in Global Constraints — read that neighborhood first to match its existing footprint/circulation setup instead of inventing a new one):

```python
def test_generate_endpoint_circulation_parts_net_is_smaller(client):
    """Dual-surface: /generate must expose circulation_parts_net too, not just
    /circulation -- same net_geometry dual-surface gotcha that has bitten this
    repo repeatedly (evacuation_dots, wall_bands, net_area_m2 previously)."""
    from shapely.geometry import shape

    request_body = {
        "footprint": [[0, 0], [12, 0], [12, 10], [0, 10]],
        "circulation": {"corridor_width_m": 1.5, "place_cage": True, "cage_size_m": 2.5},
        "apartments": [],
    }
    response = client.post("/api/v1/layout/generate", json=request_body)
    assert response.status_code == 200
    body = response.json()

    assert len(body["circulation_parts"]) > 0
    assert len(body["circulation_parts_net"]) > 0

    raw_total = sum(shape(p).area for p in body["circulation_parts"])
    net_total = sum(shape(p).area for p in body["circulation_parts_net"])
    assert net_total < raw_total
```

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_layout.py -k circulation_parts_net -v`
Expected: FAIL before Step 5, PASS after. If the footprint/circulation/apartments payload shape above doesn't match this file's existing `/generate` request convention, adjust it to match (check a neighboring `/generate` test in the same file first) rather than guessing.

Add one more test to `backend/tests/test_cage_placement.py` (near the existing iterative-placement endpoint test referenced at `test_cage_placement.py:238`) verifying `circulation_geometry_net` is present on at least one entry of `cage_iterations` when `cage_iterations > 0` is requested — read the neighboring test at that line first to reuse its exact request payload, then assert:

```python
    assert any(m["circulation_geometry_net"] is not None for m in body["cage_iterations"])
```

- [ ] **Step 7: Run the full backend suite**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all tests pass (233 pre-existing + the new ones from Step 6), 0 failures.

- [ ] **Step 8: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_layout_circulation_endpoint.py backend/tests/test_layout.py backend/tests/test_cage_placement.py
git commit -m "feat: corridor circulation_geometry gets a net (wall-shrunk) sibling on all 4 response surfaces"
```

(Adjust the `git add` file list to whatever test file(s) you actually touched per Step 6's file-existence check — stage only the files you actually changed, by name.)

---

### Task 2: Frontend — wire circulation_geometry_net/circulation_parts_net into api.ts + SessionContext.tsx

**Files:**
- Modify: `frontend/app/lib/api.ts` (interfaces: `CirculationResponse` :258-267, `ReshapeCirculationResponse` :285-290, `CageIterationMeta` :155-166, `LayoutGenerateResponse` :215-231 — re-verify these line numbers against the current file first, this plan's line numbers are from a snapshot and this file has drifted before)
- Modify: `frontend/app/state/SessionContext.tsx` (reducer cases `RESHAPE_CIRCULATION` and `SELECT_CAGE_ITERATION`)

**Interfaces:**
- Consumes: Task 1's new backend fields (`circulation_geometry_net`, `circulation_parts_net`).
- Produces: typed fields available to Task 3's canvas render.

- [ ] **Step 1: Add the new optional fields to 4 interfaces in `api.ts`**

In `frontend/app/lib/api.ts`, find `export interface CirculationResponse {` and add `circulation_geometry_net?: GeoJsonPolygon | null;` immediately after the existing `circulation_geometry: GeoJsonPolygon | null;` line.

Find `export interface ReshapeCirculationResponse {` and add the same field immediately after its `circulation_geometry: GeoJsonPolygon | null;` line.

Find `export interface CageIterationMeta {` and add `circulation_geometry_net?: GeoJsonPolygon | null;` immediately after its existing `circulation_geometry?: GeoJsonPolygon | null;` line.

Find `export interface LayoutGenerateResponse {` and add `circulation_parts_net?: GeoJsonPolygon[];` immediately after its existing `circulation_parts: GeoJsonPolygon[];` line.

- [ ] **Step 2: Run typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0 (pure additive optional fields, nothing consumes them yet).

- [ ] **Step 3: Wire the field into the `RESHAPE_CIRCULATION` reducer**

In `frontend/app/state/SessionContext.tsx`, find the `case "RESHAPE_CIRCULATION":` block (search for this string — do not trust a stale line number). Current shape:

```ts
    case "RESHAPE_CIRCULATION": {
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: {
          ...state.circulationResult,
          circulation_geometry: action.result.circulation_geometry,
          remainder: action.result.remainder,
          centerline: action.result.centerline,
          evacuation_dots: action.result.evacuation_dots,
        },
      };
    }
```

Add one line so it reads:

```ts
    case "RESHAPE_CIRCULATION": {
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: {
          ...state.circulationResult,
          circulation_geometry: action.result.circulation_geometry,
          circulation_geometry_net: action.result.circulation_geometry_net,
          remainder: action.result.remainder,
          centerline: action.result.centerline,
          evacuation_dots: action.result.evacuation_dots,
        },
      };
    }
```

- [ ] **Step 4: Wire the field into the `SELECT_CAGE_ITERATION` reducer**

In the same file, find `case "SELECT_CAGE_ITERATION": {` (search by string). Current shape:

```ts
    case "SELECT_CAGE_ITERATION": {
      if (!state.circulationResult?.cage_iterations) return state;
      const meta = state.circulationResult.cage_iterations.find((m) => m.seed === action.seed);
      if (!meta) return state;
      return {
        ...state,
        activeCageSeed: action.seed,
        circulationResult: {
          ...state.circulationResult,
          cage_geometries: meta.cage_geometries ?? state.circulationResult.cage_geometries,
          circulation_geometry: meta.circulation_geometry ?? state.circulationResult.circulation_geometry,
          centerline: meta.centerline ?? state.circulationResult.centerline,
          evacuation_dots: meta.evacuation_dots ?? state.circulationResult.evacuation_dots,
          remainder: meta.remainder ?? state.circulationResult.remainder,
          warnings: meta.warnings ?? state.circulationResult.warnings,
        },
        layoutResult: null,
        validation: null,
      };
    }
```

Add one line so the merged object also carries `circulation_geometry_net`:

```ts
    case "SELECT_CAGE_ITERATION": {
      if (!state.circulationResult?.cage_iterations) return state;
      const meta = state.circulationResult.cage_iterations.find((m) => m.seed === action.seed);
      if (!meta) return state;
      return {
        ...state,
        activeCageSeed: action.seed,
        circulationResult: {
          ...state.circulationResult,
          cage_geometries: meta.cage_geometries ?? state.circulationResult.cage_geometries,
          circulation_geometry: meta.circulation_geometry ?? state.circulationResult.circulation_geometry,
          circulation_geometry_net: meta.circulation_geometry_net ?? state.circulationResult.circulation_geometry_net,
          centerline: meta.centerline ?? state.circulationResult.centerline,
          evacuation_dots: meta.evacuation_dots ?? state.circulationResult.evacuation_dots,
          remainder: meta.remainder ?? state.circulationResult.remainder,
          warnings: meta.warnings ?? state.circulationResult.warnings,
        },
        layoutResult: null,
        validation: null,
      };
    }
```

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx
git commit -m "feat: wire circulation_geometry_net/circulation_parts_net through api types and reducers"
```

---

### Task 3: Frontend — canvas renders corridor at net geometry

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (the `circulationParts` useMemo, currently at :386-390 — re-verify by searching for `const circulationParts = useMemo`, this file has had frequent same-day changes)

**Interfaces:**
- Consumes: `state.layoutResult.circulation_parts_net`, `state.circulationResult.circulation_geometry_net` (Task 2)
- Produces: same `circulationParts` variable already consumed at the two existing render sites (`{/* Korytarz (jasnoszary) */}` and the `edit-circulation` draggable Group) — **no changes needed at either render site**, both already map over `circulationParts` and will pick up the net geometry automatically once this one derivation changes.

- [ ] **Step 1: Change the `circulationParts` derivation to prefer net geometry**

Current code (search for `const circulationParts = useMemo`):

```ts
  const circulationParts = useMemo(() => {
    if (state.layoutResult) return state.layoutResult.circulation_parts ?? [];
    if (state.circulationResult?.circulation_geometry) return [state.circulationResult.circulation_geometry];
    return [];
  }, [state.layoutResult, state.circulationResult]);
```

Replace with:

```ts
  // Koytarz renderuje się w świetle ścian (net), z fallbackiem na surową
  // geometrię gdy backend nie przysłał netto (stara sesja / zbyt cienki
  // pas) -- spec 2026-07-06 corridor-net-shrink §1, ten sam wzorzec co
  // apt.net_geometry ?? apt.geometry dla mieszkań.
  const circulationParts = useMemo(() => {
    if (state.layoutResult) {
      const net = state.layoutResult.circulation_parts_net ?? [];
      return net.length > 0 ? net : state.layoutResult.circulation_parts ?? [];
    }
    if (state.circulationResult) {
      if (state.circulationResult.circulation_geometry_net) {
        return [state.circulationResult.circulation_geometry_net];
      }
      if (state.circulationResult.circulation_geometry) {
        return [state.circulationResult.circulation_geometry];
      }
    }
    return [];
  }, [state.layoutResult, state.circulationResult]);
```

- [ ] **Step 2: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: corridor fill renders at net (wall-shrunk) geometry, same as apartments"
```

---

### Task 4: Frontend — new right-side IterationsSidebar

**Files:**
- Create: `frontend/app/components/IterationsSidebar.tsx`
- Modify: `frontend/app/components/CirculationSection.tsx` (remove the cage-iterations block, currently :279-303 — re-verify by searching for `Iteracje klatek`)
- Modify: `frontend/app/components/ProgramSection.tsx` (remove the unit-iterations block, currently :229-253 — re-verify by searching for `state.lastIterations.length > 0`)
- Modify: `frontend/app/page.tsx`

**Interfaces:**
- Consumes: `state.circulationResult.cage_iterations`, `state.circulationResult.cage_best_seed`, `activeCageSeed`, `selectCageIteration`, `state.lastIterations`, `activeUnitSeed`, `selectUnitIteration` (all pre-existing on `useSession()`, unchanged by this task).
- Produces: no new exports; purely a UI relocation, moved verbatim.

- [ ] **Step 1: Read the two current blocks before removing them**

In `frontend/app/components/CirculationSection.tsx`, search for `Iteracje klatek` and read the containing block (the `{(state.circulationResult?.cage_iterations?.length ?? 0) > 0 && ( ... )}` block, roughly 25 lines). In `frontend/app/components/ProgramSection.tsx`, search for `state.lastIterations.length > 0` and read that containing block (roughly 25 lines). Confirm both still match the code shown below before proceeding — if they've drifted, use the CURRENT code as the source of truth for Steps 2-4, not this plan's snapshot.

- [ ] **Step 2: Create `IterationsSidebar.tsx` with both blocks moved verbatim**

Create `frontend/app/components/IterationsSidebar.tsx`:

```tsx
"use client";

import { useSession } from "../state/SessionContext";

export default function IterationsSidebar() {
  const { state, selectCageIteration, activeCageSeed, selectUnitIteration, activeUnitSeed } = useSession();

  const hasCageIterations = (state.circulationResult?.cage_iterations?.length ?? 0) > 0;
  const hasUnitIterations = state.lastIterations.length > 0;

  if (!hasCageIterations && !hasUnitIterations) return null;

  return (
    <div className="h-full shrink-0 p-3">
      <aside className="flex h-full w-[260px] flex-col gap-3 overflow-y-auto rounded-2xl border border-zinc-800/80 bg-zinc-900/70 p-3 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80 light:shadow-[0_1px_0_0_rgba(0,0,0,0.02)_inset,0_12px_32px_-12px_rgba(0,0,0,0.12)]">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 light:text-zinc-500">
          Iteracje
        </div>

        {hasCageIterations && (
          <div className="space-y-0.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Iteracje klatek ({state.circulationResult!.cage_iterations!.length})
            </div>
            <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
            {state.circulationResult!.cage_iterations!.map((m) => {
              const isBest = m.seed === (state.circulationResult!.cage_best_seed ?? -1);
              const isActive = activeCageSeed === m.seed || (activeCageSeed === null && isBest);
              return (
                <button
                  key={m.seed}
                  onClick={() => selectCageIteration(m.seed)}
                  className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                    isBest ? "text-accent-400" : "text-zinc-500"
                  } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
                >
                  <span>#{m.seed}{isBest ? " ★" : ""}</span>
                  <span>{m.cages_count} klatek</span>
                  <span>odchylenie {m.score.toFixed(3)}</span>
                </button>
              );
            })}
          </div>
        )}

        {hasUnitIterations && (
          <div className="space-y-0.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Iteracje mieszkań ({state.lastIterations.length})
            </div>
            <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
            {state.lastIterations.map((m) => {
              const isBest = state.lastIterations.every((o) => m.score <= o.score);
              const isActive = activeUnitSeed === m.seed || (activeUnitSeed === null && isBest);
              return (
                <button
                  key={m.seed}
                  onClick={() => selectUnitIteration(m.seed)}
                  className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                    isBest ? "text-accent-400" : "text-zinc-500"
                  } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
                >
                  <span>#{m.seed}{isBest ? " ★" : ""}</span>
                  <span>{m.units_count} szt.</span>
                  <span>odchylenie {m.score.toFixed(3)}</span>
                </button>
              );
            })}
          </div>
        )}
      </aside>
    </div>
  );
}
```

(Note: the "Iteracje mieszkań" heading text is new — previously this block's heading was plain "Iteracje ({count})" because it lived inside `ProgramSection` where context made "mieszkań" implicit. Now that both lists sit side-by-side in one shared panel, disambiguating the heading avoids two panels both saying just "Iteracje".)

- [ ] **Step 3: Remove the cage-iterations block from `CirculationSection.tsx`**

In `frontend/app/components/CirculationSection.tsx`, delete this block entirely (the one starting `{(state.circulationResult?.cage_iterations?.length ?? 0) > 0 && (` and ending at its matching `)}`):

```tsx
      {(state.circulationResult?.cage_iterations?.length ?? 0) > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje klatek ({state.circulationResult!.cage_iterations!.length})
          </div>
          <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
          {state.circulationResult!.cage_iterations!.map((m) => {
            const isBest = m.seed === (state.circulationResult!.cage_best_seed ?? -1);
            const isActive = activeCageSeed === m.seed || (activeCageSeed === null && isBest);
            return (
              <button
                key={m.seed}
                onClick={() => selectCageIteration(m.seed)}
                className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                  isBest ? "text-accent-400" : "text-zinc-500"
                } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
              >
                <span>#{m.seed}{isBest ? " ★" : ""}</span>
                <span>{m.cages_count} klatek</span>
                <span>odchylenie {m.score.toFixed(3)}</span>
              </button>
            );
          })}
        </div>
      )}
```

Then remove `selectCageIteration` and `activeCageSeed` from this file's `useSession()` destructure (find the block starting `const { state, setCirculation, ...`) — they were only used inside the block just deleted. Grep the rest of the file for `selectCageIteration` and `activeCageSeed` first to confirm zero remaining references before removing them from the destructure.

- [ ] **Step 4: Remove the unit-iterations block from `ProgramSection.tsx`**

In `frontend/app/components/ProgramSection.tsx`, delete this block entirely (the one starting `{state.lastIterations.length > 0 && (` and ending at its matching `)}`, immediately before the component's closing `</section>`):

```tsx
      {state.lastIterations.length > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje ({state.lastIterations.length})
          </div>
          <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
          {state.lastIterations.map((m) => {
            const isBest = state.lastIterations.every((o) => m.score <= o.score);
            const isActive = activeUnitSeed === m.seed || (activeUnitSeed === null && isBest);
            return (
              <button
                key={m.seed}
                onClick={() => selectUnitIteration(m.seed)}
                className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                  isBest ? "text-accent-400" : "text-zinc-500"
                } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
              >
                <span>#{m.seed}{isBest ? " ★" : ""}</span>
                <span>{m.units_count} szt.</span>
                <span>odchylenie {m.score.toFixed(3)}</span>
              </button>
            );
          })}
        </div>
      )}
```

Then remove `selectUnitIteration` and `activeUnitSeed` from this file's `useSession()` destructure (the block starting `const { state, updateProgramRow, ...`) — grep the rest of the file for both names first to confirm zero remaining references (this file also has an `estimatedTotalUnits` feature and other unrelated logic; do not remove anything else).

- [ ] **Step 5: Wire `IterationsSidebar` into `page.tsx`**

Current `frontend/app/page.tsx`:

```tsx
"use client";

import dynamic from "next/dynamic";
import { SessionProvider } from "./state/SessionContext";
import Sidebar from "./components/Sidebar";

const CanvasEditor = dynamic(() => import("./CanvasEditor"), { ssr: false });

export default function Home() {
  return (
    <SessionProvider>
      <main className="flex h-screen w-screen overflow-hidden bg-zinc-950 text-white light:bg-zinc-100 light:text-zinc-900">
        <Sidebar />
        <div className="relative flex-1 bg-[radial-gradient(circle_at_top_left,rgba(91,141,239,0.06),transparent_45%)]">
          <CanvasEditor />
        </div>
      </main>
    </SessionProvider>
  );
}
```

Replace with:

```tsx
"use client";

import dynamic from "next/dynamic";
import { SessionProvider } from "./state/SessionContext";
import Sidebar from "./components/Sidebar";
import IterationsSidebar from "./components/IterationsSidebar";

const CanvasEditor = dynamic(() => import("./CanvasEditor"), { ssr: false });

export default function Home() {
  return (
    <SessionProvider>
      <main className="flex h-screen w-screen overflow-hidden bg-zinc-950 text-white light:bg-zinc-100 light:text-zinc-900">
        <Sidebar />
        <div className="relative flex-1 bg-[radial-gradient(circle_at_top_left,rgba(91,141,239,0.06),transparent_45%)]">
          <CanvasEditor />
        </div>
        <IterationsSidebar />
      </main>
    </SessionProvider>
  );
}
```

- [ ] **Step 6: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0. If it reports `selectCageIteration`/`activeCageSeed`/`selectUnitIteration`/`activeUnitSeed` declared but never used in `CirculationSection.tsx`/`ProgramSection.tsx`, that means Step 3/4's destructure cleanup was missed — go back and remove them (tsc only errors on this if `noUnusedLocals` is set in `tsconfig.json`; check `frontend/tsconfig.json` first — if it's not set, this is a silent lint-only concern, still remove the dead destructure entries for cleanliness but it won't block this step).

```bash
git add frontend/app/components/IterationsSidebar.tsx frontend/app/components/CirculationSection.tsx frontend/app/components/ProgramSection.tsx frontend/app/page.tsx
git commit -m "feat: move cage/unit iteration lists into a new right-side IterationsSidebar"
```

---

### Task 5: Manual verification

**Files:** none (verification task)

- [ ] **Step 1: Backend regression check**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
Expected: all pass, including Task 1's new tests.

- [ ] **Step 2: Frontend typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: Restart both dev servers fresh and hand the user a checklist**

Per this project's standing practice, kill any stale backend/frontend dev processes from earlier work, start one fresh instance of each, verify both respond (`curl`), and hand the user:
- The fresh local URL.
- A written checklist (since browser automation is not used for verification in this project):
  1. Wygeneruj układ z korytarzem+klatką → korytarz (jasnoszary pas) ma teraz szarą szczelinę (~0.20m) między nim a ścianą sąsiedniego mieszkania — nie styka się bezpośrednio ze ścianą jak wcześniej.
  2. Przełącz między iteracjami klatek/mieszkań (z nowego panelu po prawej) → korytarz nadal netto (szczelina widoczna) w każdej iteracji, nie tylko w domyślnej.
  3. Przesuń klatkę ręcznie (tryb "Przesuń komunikację") → korytarz po przeliczeniu nadal netto.
  4. Edytuj oś korytarza (tryb edycji linii środkowej) → po zapisaniu zmiany kształt nadal netto.
  5. Panel po prawej stronie: widoczne listy "Iteracje klatek" i "Iteracje mieszkań" (gdy istnieją), znikają całkowicie gdy nic jeszcze nie wygenerowano. Lewy panel (zakładka "Układ") już NIE pokazuje list iteracji.
  6. Regresja: klik w wiersz iteracji nadal wybiera ją (podświetlenie, canvas się aktualizuje) tak jak wcześniej, tylko z nowego miejsca.

---
