# Etap 2: Ręczne rysowanie klatek i korytarzy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Przyciski „Rysuj klatkę" (wielokąt punktami) i „Rysuj korytarz" (oś-łamana + szerokość z panelu); elementy manualne mergowane przez backend z auto-wynikiem, usuwalne z listy w panelu.

**Architecture:** Frontend zbiera punkty (reużycie trybu rysowania obrysu), trzyma listy `manualCages`/`manualCorridors` w SessionContext i wysyła je w `CirculationSpecInput`. Backend (`place_circulation`) po auto-pipeline dokłada manualne elementy do `circulation_geometry`/`cage_polygons`/`centerline` i odejmuje je od `remainder`. Jedno źródło prawdy geometrii: backend.

**Tech Stack:** FastAPI + shapely (backend), Next.js + react-konva (frontend).

**Spec:** `docs/superpowers/specs/2026-07-04-manual-circulation-drawing-design.md`

## Global Constraints

- Snap siatki 0.5m — frontend snapuje przy klikaniu (istniejący `worldToMeters`).
- Konwencja canvasa: `x_px = x_m * METER_PX`, `y_px = -y_m * METER_PX` (`METER_PX = 50`); każdy handler `onDragEnd`/`onDblClick` wewnątrz Stage ustawia `e.cancelBubble = true`.
- Pas korytarza budowany jak w `reshape_circulation` ([circulation.py:560](../../backend/services/circulation.py)): `half = (corridor_width_m + 2*NET_SHRINK_M)/2`, `LineString.buffer(half, cap_style="flat")`.
- Frontend bez testów automatycznych (decyzja usera, Etap 0+1); backend: zmiany objęte istniejącą suitą + 3 nowe testy w `test_layout.py` (logika merge jest algorytmiczna — analogia do zaakceptowanych testów Etapu 3/4).
- Typecheck frontendu: `cd frontend && npx tsc --noEmit`. Testy backendu: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout.py -v` (globalny python NIE MA zależności).
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001` (port 3000 zajęty).
- Kolor akcentu: `#60a5fa`.

---

### Task 1: Backend — manualne elementy w place_circulation

**Files:**
- Modify: `backend/services/circulation.py:427-546` (funkcja `place_circulation`)
- Modify: `backend/api/v1/endpoints/layout.py:26-36` (model `CirculationSpec`), `:267-308` (`CirculationResponse` + endpoint)
- Test: `backend/tests/test_layout.py` (dopisanie na końcu pliku)

**Interfaces:**
- Consumes: istniejące `CirculationResult`, `_distances_along_centerline`, `_classify_segment_loading`, `_make_centerline_segment`, `NET_SHRINK_M`
- Produces:
  - `place_circulation(..., manual_cages: list[Polygon] | None = None, manual_corridors: list[list[tuple[float, float]]] | None = None) -> CirculationResult`
  - `CirculationSpec.manual_cages: list[list[list[float]]]` i `.manual_corridors: list[list[list[float]]]` (Pydantic, default `[]`)
  - `CirculationResponse.warnings: list[str]` (default `[]`)
  - ValueError „Klatka N wykracza poza obrys budynku" → HTTP 422

- [ ] **Step 1: Napisz failing test**

Na końcu `backend/tests/test_layout.py` dodaj:

```python
from services.circulation import place_circulation as _pc


def _square(x0, y0, x1, y1):
    from shapely.geometry import Polygon
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_manual_cage_merged_into_result():
    footprint = _square(0, 0, 30, 12)
    manual_cage = [(1.0, 1.0), (5.0, 1.0), (5.0, 6.0), (1.0, 6.0)]
    result = _pc(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
        manual_cages=[manual_cage], manual_corridors=[],
    )
    assert len(result.cage_polygons) == 1
    assert abs(result.cage_polygons[0].area - 20.0) < 1e-6
    # remainder nie zawiera wnętrza klatki
    from shapely.geometry import Point
    assert not result.remainder.buffer(-1e-9).contains(Point(3.0, 3.5))


def test_manual_corridor_buffered_and_in_centerline():
    footprint = _square(0, 0, 30, 12)
    path = [(2.0, 6.0), (28.0, 6.0)]
    result = _pc(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
        manual_cages=[], manual_corridors=[path],
    )
    assert result.circulation_geometry is not None
    # pas: długość 26m x (1.5 + 2*0.10) szerokości
    assert abs(result.circulation_geometry.area - 26.0 * 1.7) < 0.5
    manual_segs = [s for s in result.centerline if s.points == ((2.0, 6.0), (28.0, 6.0))]
    assert len(manual_segs) == 1


def test_manual_cage_outside_footprint_raises():
    import pytest as _pytest
    footprint = _square(0, 0, 10, 10)
    outside = [(8.0, 8.0), (14.0, 8.0), (14.0, 12.0), (8.0, 12.0)]
    with _pytest.raises(ValueError, match="wykracza poza obrys"):
        _pc(
            footprint, corridor_width_m=1.5, stair_width_m=1.2,
            place_cage=False, cage_size_m=2.5, cage_position="auto", num_cages=1,
            manual_cages=[outside], manual_corridors=[],
        )
```

- [ ] **Step 2: Uruchom test — ma FAILować**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout.py -k manual -v`
Expected: 3× FAIL — `TypeError: place_circulation() got an unexpected keyword argument 'manual_cages'`

- [ ] **Step 3: Implementacja w place_circulation**

W `backend/services/circulation.py` zmień sygnaturę (linia 427):

```python
def place_circulation(
    footprint: Polygon,
    corridor_width_m: float,
    stair_width_m: float,
    place_cage: bool,
    cage_size_m: float,
    cage_position: str,
    num_cages: int = 1,
    manual_cages: list[Polygon] | list[list[tuple[float, float]]] | None = None,
    manual_corridors: list[list[tuple[float, float]]] | None = None,
) -> CirculationResult:
```

Bezpośrednio PRZED `return CirculationResult(...)` (linia 540) wstaw blok merge:

```python
    # ── Manualne elementy (spec 2026-07-04 manual-circulation-drawing §3) ──
    # Dokładane PO auto-pipeline: manual przeżywa każde ponowne auto-
    # rozmieszczenie; znika tylko przez usunięcie z listy we froncie.
    manual_cages = manual_cages or []
    manual_corridors = manual_corridors or []

    for idx, ring in enumerate(manual_cages):
        cage_poly = ring if isinstance(ring, Polygon) else Polygon(ring)
        if not cage_poly.is_valid or cage_poly.area < 1e-6:
            raise ValueError(f"Klatka {idx + 1}: nieprawidłowy wielokąt")
        if not footprint.buffer(1e-6).contains(cage_poly):
            raise ValueError(f"Klatka {idx + 1} wykracza poza obrys budynku")
        circulation_geom = unary_union([circulation_geom, cage_poly])
        cage_polygons.append(cage_poly)
        remainder = remainder.difference(cage_poly)

    half = (corridor_width_m + 2 * NET_SHRINK_M) / 2.0
    all_cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]
    for path in manual_corridors:
        if len(path) < 2:
            continue
        band = LineString(path).buffer(half, cap_style="flat").intersection(footprint)
        if band.is_empty:
            continue
        circulation_geom = unary_union([circulation_geom, band])
        remainder = remainder.difference(band)
        # Odległości liczone per manualna ścieżka (osobna od auto-ścieżki);
        # Etap 3 (evacuation-dots) zastąpi to grafem całej sieci.
        arc = _distances_along_centerline([tuple(p) for p in path], all_cage_points)
        for i in range(len(path) - 1):
            p1, p2 = tuple(path[i]), tuple(path[i + 1])
            loading = _classify_segment_loading(footprint, (p1, p2), corridor_width_m)
            centerline.append(_make_centerline_segment(p1, p2, loading, arc[i], arc[i + 1]))
```

Uwaga: `cage_points`/`arc_distances` auto-ścieżki (linie 525-526) liczone są
PRZED tym blokiem — zostają bez zmian; manualne klatki nie wpływają wstecz
na odległości auto-segmentów w tym etapie (Etap 3 ujednolica to grafem).

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout.py -v`
Expected: wszystkie PASS (nowe 3 + dotychczasowe bez regresji).

- [ ] **Step 5: Rozszerz API endpointu**

W `backend/api/v1/endpoints/layout.py`:

Model `CirculationSpec` (po linii 35, za `num_cages`):

```python
    manual_cages: list[list[list[float]]] = Field(default_factory=list)
    """Ringi ręcznie narysowanych klatek [[x,y],...] bez duplikatu 1. punktu
    (spec 2026-07-04 manual-circulation-drawing §3)."""
    manual_corridors: list[list[list[float]]] = Field(default_factory=list)
    """Łamane osi ręcznie narysowanych korytarzy [[x,y],...]."""
```

Model `CirculationResponse` (po linii 271, za `centerline`):

```python
    warnings: list[str] = []
    """Miękkie ostrzeżenia (np. korytarz niedotykający klatki) -- spec §4."""
```

W `place_circulation_endpoint` (linia 289) rozszerz wywołanie:

```python
    try:
        result = place_circulation(
            footprint,
            corridor_width_m=circulation.corridor_width_m,
            stair_width_m=circulation.stair_width_m,
            place_cage=circulation.place_cage,
            cage_size_m=circulation.cage_size_m,
            cage_position=circulation.cage_position,
            num_cages=circulation.num_cages,
            manual_cages=[[(p[0], p[1]) for p in ring] for ring in circulation.manual_cages],
            manual_corridors=[[(p[0], p[1]) for p in path] for path in circulation.manual_corridors],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
```

Przed `return CirculationResponse(...)` policz ostrzeżenia:

```python
    warnings: list[str] = []
    for i, path in enumerate(circulation.manual_corridors):
        if len(path) < 2:
            continue
        axis = LineString([(p[0], p[1]) for p in path])
        touches_any = any(axis.distance(c) <= 0.25 for c in result.cage_polygons)
        if not touches_any:
            warnings.append(f"Korytarz {i + 1} nie styka się z żadną klatką")
```

(import `LineString` z shapely na górze pliku) i dodaj `warnings=warnings`
do konstruktora odpowiedzi.

- [ ] **Step 6: Druga ścieżka API — /layout/generate (dual-surface gotcha)**

Przycisk „Generuj układ" idzie przez `generate_layout()` → `place_circulation()`
([layout.py:130-156](../../backend/services/layout.py)) — bez przekazania manuali
kliknięcie „Generuj" po cichu by je gubiło (dokładnie ten sam błąd, który
w projekcie zdarzył się już dwa razy z `net_area_m2` i `wall_bands`).

W `backend/services/layout.py`:

`LayoutInput` (po `num_cages: int = 1`, linia 89):

```python
    manual_cages: list[list[tuple[float, float]]] = field(default_factory=list)
    manual_corridors: list[list[tuple[float, float]]] = field(default_factory=list)
```

`generate_layout` — wywołanie `place_circulation` (linia 146) dostaje:

```python
        manual_cages=input.manual_cages,
        manual_corridors=input.manual_corridors,
```

W `backend/api/v1/endpoints/layout.py`, w `generate_layout_endpoint` — w miejscu
gdzie budowany jest `LayoutInput` z `request.circulation`, dodaj mapowanie:

```python
        manual_cages=[[(p[0], p[1]) for p in ring] for ring in request.circulation.manual_cages],
        manual_corridors=[[(p[0], p[1]) for p in path] for path in request.circulation.manual_corridors],
```

oraz obejmij wywołanie tym samym `try/except ValueError → 422` co w Step 5.

Frontend: `regenerate()` w `SessionContext.tsx` wysyła `state.circulation` —
po Task 2 Step 3 `initialCirculation` ma puste listy, ale `regenerate` musi
wstrzykiwać AKTUALNE listy manuali tak samo jak `runPlaceCirculation`.
W `regenerate` (miejsce, gdzie budowany jest request z `circulation:
state.circulation`) zamień na:

```ts
        circulation: {
          ...state.circulation,
          manual_cages: state.manualCages.map((c) => c.ring.map((p) => [p.x, p.y] as api.Point)),
          manual_corridors: state.manualCorridors.map((c) => c.path.map((p) => [p.x, p.y] as api.Point)),
        },
```

i dodaj `state.manualCages`, `state.manualCorridors` do tablicy zależności
`useCallback` `regenerate`. (Ten fragment frontendu wykonaj razem z Taskiem 2 —
wpisany tu, żeby całość dual-surface była w jednym miejscu planu.)

- [ ] **Step 7: Testy + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS.

```bash
git add backend/services/circulation.py backend/services/layout.py backend/api/v1/endpoints/layout.py backend/tests/test_layout.py
git commit -m "feat: merge manual cages and corridors into place_circulation result"
```

---

### Task 2: Frontend — typy API i stan elementów manualnych

**Files:**
- Modify: `frontend/app/lib/api.ts:124-131` (`CirculationSpecInput`), `:193-198` (`CirculationResponse`)
- Modify: `frontend/app/state/SessionContext.tsx` (EditorMode :8, SessionState ~:44, initial ~:69, Action ~:116, reducer, callbacki, value)

**Interfaces:**
- Consumes: Task 1 (pola API)
- Produces (używane w Taskach 3–4):
  - typy `ManualCage = { id: string; ring: Point2D[] }`, `ManualCorridor = { id: string; path: Point2D[] }` (eksport z SessionContext)
  - stan `manualCages: ManualCage[]`, `manualCorridors: ManualCorridor[]`, `hoveredManualId: string | null`
  - akcje/callbacki: `addManualCage(ring)`, `addManualCorridor(path)`, `removeManualElement(id)`, `setHoveredManualId(id | null)`
  - `runPlaceCirculation(overrides?: { manualCages?: ManualCage[]; manualCorridors?: ManualCorridor[] })` — wysyła listy w spec
  - nowe EditorMode: `"draw-cage"`, `"draw-corridor"`

- [ ] **Step 1: api.ts**

W `CirculationSpecInput` (po `num_cages: number;`):

```ts
  manual_cages: Point[][];
  manual_corridors: Point[][];
```

W `CirculationResponse` (po `centerline`):

```ts
  warnings?: string[];
```

- [ ] **Step 2: SessionContext — typy, stan, akcje**

Linia 8 — rozszerz union:

```ts
export type EditorMode = "idle" | "draw" | "edit-vertices" | "edit-lines" | "edit-circulation" | "edit-corridor-centerline" | "draw-cage" | "draw-corridor";
```

Po definicji `ProgramRow` dodaj eksportowane typy:

```ts
export interface ManualCage { id: string; ring: Point2D[] }
export interface ManualCorridor { id: string; path: Point2D[] }
```

`SessionState` (po `circulationResult`):

```ts
  manualCages: ManualCage[];
  manualCorridors: ManualCorridor[];
  hoveredManualId: string | null;
```

`initialState`: `manualCages: [], manualCorridors: [], hoveredManualId: null,`.

Union `Action` (po `SET_CIRCULATION_RESULT`):

```ts
  | { type: "ADD_MANUAL_CAGE"; ring: Point2D[] }
  | { type: "ADD_MANUAL_CORRIDOR"; path: Point2D[] }
  | { type: "REMOVE_MANUAL_ELEMENT"; id: string }
  | { type: "SET_HOVERED_MANUAL"; id: string | null }
```

Reducer (obok `SET_CIRCULATION_RESULT`):

```ts
    case "ADD_MANUAL_CAGE":
      return {
        ...state,
        manualCages: [...state.manualCages, { id: crypto.randomUUID(), ring: action.ring }],
        drawingPoints: [],
        mode: "idle",
        // jak UPDATE_VERTEX: wyniki pochodne są nieaktualne do czasu przeliczenia
        layoutResult: null, validation: null,
      };
    case "ADD_MANUAL_CORRIDOR":
      return {
        ...state,
        manualCorridors: [...state.manualCorridors, { id: crypto.randomUUID(), path: action.path }],
        drawingPoints: [],
        mode: "idle",
        layoutResult: null, validation: null,
      };
    case "REMOVE_MANUAL_ELEMENT":
      return {
        ...state,
        manualCages: state.manualCages.filter((c) => c.id !== action.id),
        manualCorridors: state.manualCorridors.filter((c) => c.id !== action.id),
        layoutResult: null, validation: null,
      };
    case "SET_HOVERED_MANUAL":
      return { ...state, hoveredManualId: action.id };
```

Rozszerz też `SET_MODE` (linia 161): czyszczenie `drawingPoints` ma
obejmować nowe tryby rysowania:

```ts
        drawingPoints:
          ["draw", "draw-cage", "draw-corridor"].includes(action.mode) ||
          ["draw", "draw-cage", "draw-corridor"].includes(state.mode)
            ? []
            : state.drawingPoints,
```

- [ ] **Step 3: runPlaceCirculation z manualami**

Zamień istniejący callback (linie 495–509) na:

```ts
  const runPlaceCirculation = useCallback(
    async (overrides?: { manualCages?: ManualCage[]; manualCorridors?: ManualCorridor[] }) => {
      if (!state.footprint || state.footprint.length < 3) return;
      // overrides: handler po dispatch(ADD_/REMOVE_) ma świeżą listę wcześniej
      // niż state z closure — bez tego pierwszy przelicz po dodaniu elementu
      // wysyłałby listę sprzed dodania.
      const cages = overrides?.manualCages ?? state.manualCages;
      const corridors = overrides?.manualCorridors ?? state.manualCorridors;
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const result = await api.placeCirculation(footprintToPoints(state.footprint), {
          ...state.circulation,
          manual_cages: cages.map((c) => c.ring.map((p) => [p.x, p.y] as api.Point)),
          manual_corridors: corridors.map((c) => c.path.map((p) => [p.x, p.y] as api.Point)),
        });
        dispatch({ type: "SET_CIRCULATION_RESULT", result });
        dispatch({ type: "SET_LAYOUT_RESULT", result: null });
        dispatch({ type: "SET_VALIDATION", validation: null });
        dispatch({ type: "SET_ERROR", error: null });
      } catch (err) {
        dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [state.footprint, state.circulation, state.manualCages, state.manualCorridors]
  );
```

`initialCirculation` (linia 69) dostaje `manual_cages: [], manual_corridors: [],`.

UWAGA: `runPlaceCirculation` jest już wywoływany bezargumentowo
(CirculationSection linia 140) — sygnatura z opcjonalnym parametrem jest
wstecznie zgodna.

- [ ] **Step 4: Callbacki + interfejs + value**

W `SessionContextValue` (po `runPlaceCirculation`):

```ts
  addManualCage: (ring: Point2D[]) => void;
  addManualCorridor: (path: Point2D[]) => void;
  removeManualElement: (id: string) => void;
  setHoveredManualId: (id: string | null) => void;
```

Implementacje (obok pozostałych `useCallback`):

```ts
  const addManualCage = useCallback((ring: Point2D[]) => dispatch({ type: "ADD_MANUAL_CAGE", ring }), []);
  const addManualCorridor = useCallback((path: Point2D[]) => dispatch({ type: "ADD_MANUAL_CORRIDOR", path }), []);
  const removeManualElement = useCallback((id: string) => dispatch({ type: "REMOVE_MANUAL_ELEMENT", id }), []);
  const setHoveredManualId = useCallback((id: string | null) => dispatch({ type: "SET_HOVERED_MANUAL", id }), []);
```

Dodaj wszystkie 4 do obiektu `value` (i tablicy zależności useMemo, jeśli
jest — wzoruj się na `updateVertex`).

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx
git commit -m "feat: manual cages/corridors state, API fields, runPlaceCirculation overrides"
```

---

### Task 3: CanvasEditor — tryby rysowania klatki i korytarza

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (handleStageClick ~:519, handleStageDblClick ~:547, cursor ~:554, render podglądu ~:706-719, destrukturyzacja useSession ~:330)

**Interfaces:**
- Consumes: Task 2 (`addManualCage`, `addManualCorridor`, `runPlaceCirculation(overrides)`, tryby `draw-cage`/`draw-corridor`, `state.manualCages/manualCorridors/hoveredManualId`)
- Produces: kompletny UX rysowania; podświetlanie elementu z listy panelu

- [ ] **Step 1: Klik dodaje punkt w nowych trybach**

W `handleStageClick` (linia 519) rozszerz warunek trybu: tam gdzie obecnie
obsługiwany jest `state.mode === "draw"`, dopuść też `"draw-cage"` i
`"draw-corridor"` (punkty lądują w `state.drawingPoints` przez istniejący
`ADD_DRAW_POINT` — reużycie mechanizmu 1:1, ze snapem z `worldToMeters`).

- [ ] **Step 2: Dblclick kończy rysowanie elementu**

Zamień `handleStageDblClick` (linie 547–552) na:

```ts
  const handleStageDblClick = () => {
    if (state.mode === "draw") {
      void finishDrawing();
      return;
    }
    if (state.mode === "draw-cage") {
      if (state.drawingPoints.length < 3) return;
      const ring = [...state.drawingPoints];
      const nextCages = [...state.manualCages, { id: "pending", ring }];
      addManualCage(ring);
      // świeża lista przez overrides — patrz komentarz w runPlaceCirculation
      void runPlaceCirculation({ manualCages: nextCages });
      return;
    }
    if (state.mode === "draw-corridor") {
      if (state.drawingPoints.length < 2) return;
      const path = [...state.drawingPoints];
      const nextCorridors = [...state.manualCorridors, { id: "pending", path }];
      addManualCorridor(path);
      void runPlaceCirculation({ manualCorridors: nextCorridors });
      return;
    }
  };
```

(`id: "pending"` jest tylko w liście-override do requestu — backend nie czyta
id; reducer nadaje właściwy `crypto.randomUUID()`.)

Do destrukturyzacji `useSession()` dodaj: `addManualCage, addManualCorridor,
removeManualElement` nie jest tu potrzebny, `runPlaceCirculation`.

- [ ] **Step 3: Kursor i podgląd rysowania**

Cursor (linia 554): dopisz nowe tryby do gałęzi crosshair:

```ts
    state.mode === "draw" || state.mode === "draw-cage" || state.mode === "draw-corridor"
      ? "crosshair"
      : ...
```

Po istniejącym bloku „Rysowanie w toku" (linie 708–719) dodaj podgląd pasa
korytarza:

```tsx
          {/* Podgląd pasa korytarza przy rysowaniu osi (draw-corridor) */}
          {state.mode === "draw-corridor" && drawingCanvasPoints.length >= 4 && (
            <Line
              points={drawingCanvasPoints}
              stroke="#60a5fa"
              opacity={0.25}
              strokeWidth={(state.circulation.corridor_width_m + 0.2) * METER_PX}
              lineCap="butt"
              lineJoin="round"
              listening={false}
            />
          )}
```

(Istniejący dashed podgląd łamanej działa dla nowych trybów automatycznie,
bo czyta `drawingPoints`; `closed` zostaje sterowane liczbą punktów — dla
`draw-corridor` NIE zamykamy: rozszerz warunek `closed` istniejącej linii
podglądu na `state.mode !== "draw-corridor" && state.drawingPoints.length >= 3`.)

- [ ] **Step 4: Podświetlenie elementu manualnego z listy panelu**

Po renderze klatek (blok `{/* Klatka (szary) */}`, ~linia 734-743) dodaj:

```tsx
          {/* Highlight elementu manualnego wskazanego w liście panelu */}
          {state.hoveredManualId &&
            state.manualCages
              .filter((c) => c.id === state.hoveredManualId)
              .map((c) => (
                <Line
                  key={`manual-hl-${c.id}`}
                  points={toCanvasPoints(c.ring)}
                  closed
                  stroke="#60a5fa"
                  strokeWidth={3 / scale}
                  listening={false}
                />
              ))}
          {state.hoveredManualId &&
            state.manualCorridors
              .filter((c) => c.id === state.hoveredManualId)
              .map((c) => (
                <Line
                  key={`manual-hl-${c.id}`}
                  points={toCanvasPoints(c.path)}
                  stroke="#60a5fa"
                  strokeWidth={4 / scale}
                  listening={false}
                />
              ))}
```

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: draw-cage and draw-corridor canvas modes with live preview"
```

---

### Task 4: Panel Komunikacja — przyciski, lista, ostrzeżenia

**Files:**
- Modify: `frontend/app/components/CirculationSection.tsx` (destrukturyzacja :24-33, przyciski :138-181)

**Interfaces:**
- Consumes: Task 2 (`removeManualElement`, `setHoveredManualId`, `setMode`, `runPlaceCirculation(overrides)`, `state.manualCages/manualCorridors`, `state.circulationResult.warnings`)
- Produces: kompletne UI Etapu 2

- [ ] **Step 1: Przyciski rysowania**

Do destrukturyzacji dodaj `removeManualElement, setHoveredManualId`.
Po przycisku „Edytuj linię korytarza" (linia 180) dodaj:

```tsx
        <button
          onClick={() => setMode(state.mode === "draw-cage" ? "idle" : "draw-cage")}
          disabled={!state.footprint}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "draw-cage"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.footprint ? "Najpierw narysuj obrys" : "Klikaj punkty, dblclick zamyka klatkę"}
        >
          Rysuj klatkę
        </button>
        <button
          onClick={() => setMode(state.mode === "draw-corridor" ? "idle" : "draw-corridor")}
          disabled={!state.footprint}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "draw-corridor"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.footprint ? "Najpierw narysuj obrys" : "Klikaj punkty osi, dblclick kończy korytarz"}
        >
          Rysuj korytarz
        </button>
```

- [ ] **Step 2: Lista elementów manualnych + usuwanie + hover**

Po bloku przycisków (za `</div>` linii 181) dodaj:

```tsx
      {(state.manualCages.length > 0 || state.manualCorridors.length > 0) && (
        <div className="space-y-1 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Elementy ręczne</div>
          {state.manualCages.map((c, i) => (
            <div
              key={c.id}
              onMouseEnter={() => setHoveredManualId(c.id)}
              onMouseLeave={() => setHoveredManualId(null)}
              className="flex items-center justify-between rounded-lg bg-zinc-900/70 px-2 py-1 text-xs text-zinc-300 light:bg-zinc-100 light:text-zinc-700"
            >
              <span>Klatka {i + 1}</span>
              <button
                onClick={() => {
                  removeManualElement(c.id);
                  void runPlaceCirculation({ manualCages: state.manualCages.filter((x) => x.id !== c.id) });
                }}
                className="text-zinc-500 hover:text-red-400"
                title="Usuń"
              >
                ✕
              </button>
            </div>
          ))}
          {state.manualCorridors.map((c, i) => (
            <div
              key={c.id}
              onMouseEnter={() => setHoveredManualId(c.id)}
              onMouseLeave={() => setHoveredManualId(null)}
              className="flex items-center justify-between rounded-lg bg-zinc-900/70 px-2 py-1 text-xs text-zinc-300 light:bg-zinc-100 light:text-zinc-700"
            >
              <span>Korytarz {i + 1}</span>
              <button
                onClick={() => {
                  removeManualElement(c.id);
                  void runPlaceCirculation({ manualCorridors: state.manualCorridors.filter((x) => x.id !== c.id) });
                }}
                className="text-zinc-500 hover:text-red-400"
                title="Usuń"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {(state.circulationResult?.warnings?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-300 light:text-amber-700">
          {state.circulationResult!.warnings!.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}
```

- [ ] **Step 3: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/components/CirculationSection.tsx
git commit -m "feat: manual circulation draw buttons, element list with remove and hover-highlight"
```

---

### Task 5: Weryfikacja ręczna (spec §5)

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1–4
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. Obrys → „Rysuj klatkę" → 4 kliki + dblclick → klatka na canvasie i „Klatka 1" w liście.
2. „Rysuj korytarz" → 3 punkty + dblclick → pas o szerokości z panelu; oś edytowalna (tryb „Edytuj linię korytarza").
3. „Umieść korytarz i klatkę" (auto) przy istniejących manualach → auto się zmienia, manuale zostają.
4. Usuń element z listy → geometria znika po przeliczeniu.
5. Klatka częściowo poza obrysem → czerwony błąd w panelu (422), element NIE trafia do listy. UWAGA: dispatch ADD wykonuje się przed odpowiedzią — sprawdź, czy po 422 element trzeba usunąć z listy; jeśli test ujawni, że zostaje, popraw handler dblclick tak, by dodawał do stanu dopiero PO sukcesie requestu (przenieś `addManualCage` za `await`).
6. Korytarz z dala od klatek → żółte ostrzeżenie w panelu.
7. „Podziel na mieszkania" na remainder z manualami → mieszkania + ściany 20cm wokół manualnych elementów.
8. Regresja: auto-flow bez manuali, reshape osi, generacja pełna.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
