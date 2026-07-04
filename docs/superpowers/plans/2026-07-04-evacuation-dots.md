# Etap 3: Kropki ewakuacyjne co 1m — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Kropki co 1m na osi każdego korytarza: zielona (1 klatka osiągalna, <20m), szara (≥2 klatki, <40m do bliższej), czerwona (reszta). Zastępują dzisiejsze kolorowanie odcinków osi.

**Architecture:** Nowy moduł czystych funkcji `backend/services/evacuation.py` buduje graf sieci osi (węzły=końce/przecięcia segmentów, krawędzie=odcinki), znajduje wejścia do klatek (styk osi z poligonem klatki), liczy Dijkstrą odległość każdego węzła do każdej klatki, próbkuje kropki co 1m. Wynik (`evacuation_dots`) doklejany do `CirculationResult` i serializowany we WSZYSTKICH trzech odpowiedziach: `/layout/circulation`, `/layout/circulation/reshape`, `/layout/generate` (dual-surface gotcha). Frontend renderuje kropki i neutralizuje kolor osi.

**Tech Stack:** shapely + stdlib heapq (bez networkx), react-konva.

**Spec:** `docs/superpowers/specs/2026-07-04-evacuation-dots-design.md`
**Wymaga:** zaimplementowanego Etapu 2 (manualne korytarze w centerline) — plan `2026-07-04-manual-circulation-drawing.md`. Działa też bez niego (sama sieć auto), ale weryfikacja ręczna zakłada Etap 2.

## Global Constraints

- Progi 20/40m to wartości DOMYŚLNE (stałe `CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M` / `..._DOUBLE_LOADED_M` z `circulation.py:22-23`) — user edytuje je w panelu, idą w requeście (`max_dist_single_m`/`max_dist_multi_m`), a `compute_evacuation_dots` bierze je jako parametry. To heurystyki robocze usera — w komentarzach i opisach NIE przypisywać im § WT (utrwalona zasada: żadnych fabrykowanych citations).
- Krok próbkowania `SAMPLE_STEP_M = 1.0`; tolerancja wejścia do klatki `CAGE_ENTRY_TOLERANCE_M = 0.25`; tolerancja deduplikacji węzłów `1e-6`.
- Testy backendu: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_evacuation.py -v` (globalny python bez zależności). Frontend bez testów automatycznych — typecheck `cd frontend && npx tsc --noEmit` + weryfikacja ręczna.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001`.
- Kolory kropek: zielona `#22c55e`, szara `#9ca3af`, czerwona `#ef4444`. Oś po zmianie: neutralna `#60a5fa`.

---

### Task 1: Moduł evacuation.py — graf, Dijkstra, próbkowanie (TDD)

**Files:**
- Create: `backend/services/evacuation.py`
- Test: `backend/tests/test_evacuation.py` (nowy plik)

**Interfaces:**
- Consumes: `shapely.geometry.Polygon/LineString/Point`, stałe progów z `services.circulation`
- Produces (używane w Tasku 2):
  - `@dataclass EvacuationDot: x: float; y: float; status: str; distance_m: float | None` (`status ∈ {"green","gray","red"}`)
  - `compute_evacuation_dots(segments: list[tuple[tuple[float, float], tuple[float, float]]], cage_polygons: list[Polygon], green_max_m: float = GREEN_MAX_M, gray_max_m: float = GRAY_MAX_M) -> list[EvacuationDot]` — progi edytowalne (spec, uzupełnienie z review usera)

- [ ] **Step 1: Napisz failing testy**

Utwórz `backend/tests/test_evacuation.py`:

```python
"""Testy grafu ewakuacyjnego (spec 2026-07-04-evacuation-dots §6)."""

from shapely.geometry import Polygon

from services.evacuation import EvacuationDot, compute_evacuation_dots


def _cage(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_single_cage_straight_corridor_green_then_red():
    # klatka przy (0,0); oś od (0,0) do (30,0) -> do 20m zielone, dalej czerwone
    segments = [((0.0, 0.0), (30.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert len(dots) >= 30
    greens = [d for d in dots if d.status == "green"]
    reds = [d for d in dots if d.status == "red"]
    assert greens and reds
    assert all(d.distance_m is not None and d.distance_m < 20.0 for d in greens)
    assert all(d.distance_m is None or d.distance_m >= 20.0 for d in reds)
    assert not [d for d in dots if d.status == "gray"]


def test_two_cages_make_gray():
    # klatki na obu końcach osi 30m -> każdy punkt osiąga 2 klatki, bliższa
    # zawsze <=15m<40m -> wszystko szare (także <20m od klatki: spec §2)
    segments = [((0.0, 0.0), (30.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0), _cage(30.0, -1.0, 32.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert dots
    assert all(d.status == "gray" for d in dots)


def test_two_cages_far_apart_red_in_middle():
    # oś 100m, klatki na końcach: środek ma bliższą ~50m > 40m -> czerwony
    segments = [((0.0, 0.0), (100.0, 0.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0), _cage(100.0, -1.0, 102.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    mids = [d for d in dots if 45.0 <= d.x <= 55.0]
    assert mids and all(d.status == "red" for d in mids)


def test_branch_distances_via_graph():
    # T: pień (0,0)-(20,0), odgałęzienie w (10,0) do (10,15); klatka przy (0,0).
    # Punkt (10,10) ma odległość 10 (gałąź) + 10 (pień) = 20 -> czerwony (>=20),
    # punkt (10,5) -> 15m -> zielony.
    segments = [((0.0, 0.0), (20.0, 0.0)), ((10.0, 0.0), (10.0, 15.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    near = min(dots, key=lambda d: abs(d.x - 10.0) + abs(d.y - 5.0))
    far = min(dots, key=lambda d: abs(d.x - 10.0) + abs(d.y - 10.0))
    assert near.status == "green"
    assert far.status == "red"


def test_island_without_cage_is_red_with_null_distance():
    segments = [((50.0, 50.0), (60.0, 50.0))]
    cages = [_cage(-2.0, -1.0, 0.0, 1.0)]
    dots = compute_evacuation_dots(segments, cages)
    assert dots
    assert all(d.status == "red" and d.distance_m is None for d in dots)


def test_no_cages_all_red():
    segments = [((0.0, 0.0), (10.0, 0.0))]
    dots = compute_evacuation_dots(segments, [])
    assert dots and all(d.status == "red" and d.distance_m is None for d in dots)
```

- [ ] **Step 2: Uruchom testy — mają FAILować**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_evacuation.py -v`
Expected: `ModuleNotFoundError: No module named 'services.evacuation'`

- [ ] **Step 3: Implementacja `backend/services/evacuation.py`**

```python
"""Kropki ewakuacyjne co 1m wzdłuż osi korytarzy (spec 2026-07-04-
evacuation-dots). Czyste funkcje: shapely + stdlib. Progi 20/40m to robocze
heurystyki projektu (wartości usera) -- celowo BEZ przypisania § WT."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from services.circulation import (
    CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M as GRAY_MAX_M,
    CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M as GREEN_MAX_M,
)

SAMPLE_STEP_M = 1.0
CAGE_ENTRY_TOLERANCE_M = 0.25
_NODE_TOL = 1e-6


@dataclass
class EvacuationDot:
    x: float
    y: float
    status: str  # "green" | "gray" | "red"
    distance_m: float | None


def _node_key(p: tuple[float, float]) -> tuple[float, float]:
    # deduplikacja węzłów z tolerancją: klucz po zaokrągleniu do 1e-6
    return (round(p[0], 6), round(p[1], 6))


def _split_at_crossings(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Dzieli segmenty w punktach wzajemnych przecięć (skrzyżowania bez
    wspólnego końca), żeby graf miał węzeł na każdym skrzyżowaniu."""
    result: list[tuple[tuple[float, float], tuple[float, float]]] = []
    lines = [LineString([p1, p2]) for p1, p2 in segments]
    for i, (p1, p2) in enumerate(segments):
        cuts: list[float] = []
        me = lines[i]
        if me.length < _NODE_TOL:
            continue
        for j, other in enumerate(lines):
            if i == j:
                continue
            inter = me.intersection(other)
            if inter.is_empty:
                continue
            pts = []
            if inter.geom_type == "Point":
                pts = [inter]
            elif hasattr(inter, "geoms"):
                pts = [g for g in inter.geoms if g.geom_type == "Point"]
            for pt in pts:
                t = me.project(pt)
                if _NODE_TOL < t < me.length - _NODE_TOL:
                    cuts.append(t)
        ts = sorted(set([0.0] + cuts + [me.length]))
        for a, b in zip(ts, ts[1:]):
            pa = me.interpolate(a)
            pb = me.interpolate(b)
            result.append(((pa.x, pa.y), (pb.x, pb.y)))
    return result


def _build_graph(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[list[tuple[float, float]], list[tuple[int, int, float]]]:
    """Zwraca (nodes, edges); edges = (u, v, length)."""
    nodes: list[tuple[float, float]] = []
    index: dict[tuple[float, float], int] = {}

    def _add(p: tuple[float, float]) -> int:
        k = _node_key(p)
        if k not in index:
            index[k] = len(nodes)
            nodes.append((float(p[0]), float(p[1])))
        return index[k]

    edges: list[tuple[int, int, float]] = []
    for p1, p2 in segments:
        u, v = _add(p1), _add(p2)
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if u != v and length > _NODE_TOL:
            edges.append((u, v, length))
    return nodes, edges


def _dijkstra(
    n_nodes: int, adj: dict[int, list[tuple[int, float]]], sources: list[int]
) -> list[float]:
    dist = [math.inf] * n_nodes
    heap: list[tuple[float, int]] = []
    for s in sources:
        dist[s] = 0.0
        heapq.heappush(heap, (0.0, s))
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u] + _NODE_TOL:
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist[v] - _NODE_TOL:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def compute_evacuation_dots(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    cage_polygons: list[Polygon],
    green_max_m: float = GREEN_MAX_M,
    gray_max_m: float = GRAY_MAX_M,
) -> list[EvacuationDot]:
    if not segments:
        return []
    split = _split_at_crossings(segments)
    nodes, edges = _build_graph(split)
    if not edges:
        return []

    adj: dict[int, list[tuple[int, float]]] = {}
    for u, v, w in edges:
        adj.setdefault(u, []).append((v, w))
        adj.setdefault(v, []).append((u, w))

    # wejścia do klatek: węzły w odległości <= tolerancji od poligonu klatki
    dist_per_cage: list[list[float]] = []
    for cage in cage_polygons:
        sources = [i for i, p in enumerate(nodes) if cage.distance(Point(p)) <= CAGE_ENTRY_TOLERANCE_M]
        dist_per_cage.append(_dijkstra(len(nodes), adj, sources) if sources else [math.inf] * len(nodes))

    def _status(dists: list[float]) -> tuple[str, float | None]:
        reachable = [d for d in dists if math.isfinite(d)]
        if not reachable:
            return "red", None
        d = min(reachable)
        if len(reachable) >= 2:
            return ("gray" if d < gray_max_m else "red"), d
        return ("green" if d < green_max_m else "red"), d

    dots: list[EvacuationDot] = []
    seen: set[tuple[float, float]] = set()
    for u, v, w in edges:
        n_samples = max(1, int(math.floor(w / SAMPLE_STEP_M)))
        for k in range(n_samples + 1):
            t = min(w, k * SAMPLE_STEP_M)
            x = nodes[u][0] + (nodes[v][0] - nodes[u][0]) * (t / w)
            y = nodes[u][1] + (nodes[v][1] - nodes[u][1]) * (t / w)
            key = _node_key((x, y))
            if key in seen:
                continue
            seen.add(key)
            # spec §5: oś wewnątrz klatki nie dostaje kropek
            if any(c.contains(Point((x, y))) for c in cage_polygons):
                continue
            sample_dists = [
                min(dc[u] + t, dc[v] + (w - t)) for dc in dist_per_cage
            ] if dist_per_cage else []
            status, d = _status(sample_dists)
            dots.append(EvacuationDot(x=x, y=y, status=status, distance_m=d))
    return dots
```

- [ ] **Step 4: Uruchom testy — mają przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_evacuation.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/evacuation.py backend/tests/test_evacuation.py
git commit -m "feat: evacuation graph module - Dijkstra over corridor network, 1m dot sampling"
```

---

### Task 2: Wpięcie w CirculationResult i wszystkie trzy odpowiedzi API

**Files:**
- Modify: `backend/services/circulation.py:376-388` (`CirculationResult`), `:540-546` i `:589-595` (returny), `backend/services/layout.py:110-127` (`LayoutResult`), `:130-` (`generate_layout`)
- Modify: `backend/api/v1/endpoints/layout.py` (`CirculationResponse` :267-271, `LayoutGenerateResponse` :68-84, `ReshapeCirculationResponse` — sekcja za :468, `layout_result_to_response` :134)
- Test: `backend/tests/test_evacuation.py` (1 test integracyjny)

**Interfaces:**
- Consumes: `compute_evacuation_dots` (Task 1)
- Produces:
  - `CirculationResult.evacuation_dots: list[EvacuationDot]` (default `[]`)
  - `LayoutResult.evacuation_dots: list[EvacuationDot]` (default `[]`)
  - pole odpowiedzi `evacuation_dots: [{x, y, status, distance_m}]` w `CirculationResponse`, `ReshapeCirculationResponse` i `LayoutGenerateResponse`

- [ ] **Step 1: Failing test integracyjny**

Dopisz do `backend/tests/test_evacuation.py`:

```python
def test_place_circulation_returns_dots():
    from shapely.geometry import Polygon as _P
    from services.circulation import place_circulation

    footprint = _P([(0, 0), (30, 0), (30, 12), (0, 12)])
    result = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2,
        place_cage=True, cage_size_m=2.5, cage_position="auto", num_cages=1,
    )
    assert result.centerline  # sanity
    assert result.evacuation_dots
    assert {d.status for d in result.evacuation_dots} <= {"green", "gray", "red"}
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_evacuation.py -k place -v`
Expected: FAIL — `AttributeError: ... no attribute 'evacuation_dots'`

- [ ] **Step 2: CirculationResult + oba returny + parametry progów**

`circulation.py` — do dataclass `CirculationResult` (po `centerline`, linia 387):

```python
    evacuation_dots: list = field(default_factory=list)
    """list[EvacuationDot] -- spec 2026-07-04-evacuation-dots. Typ `list`
    bez parametru, żeby uniknąć importu cyklicznego (evacuation.py importuje
    stałe z tego modułu)."""
```

Sygnatury OBU funkcji dostają edytowalne progi (na końcu listy parametrów,
z defaultami = stałe modułu):

```python
    max_dist_single_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M,
    max_dist_multi_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M,
```

W `place_circulation` — przed `return CirculationResult(...)` (a PO bloku
manuali z Etapu 2, jeśli już wdrożony):

```python
    from services.evacuation import compute_evacuation_dots

    all_segments = [seg.points for seg in centerline]
    evacuation_dots = compute_evacuation_dots(
        all_segments, cage_polygons,
        green_max_m=max_dist_single_m, gray_max_m=max_dist_multi_m,
    )
```

i `evacuation_dots=evacuation_dots` w konstruktorze. To samo w
`reshape_circulation` przed jego `return` (linia 589):

```python
    from services.evacuation import compute_evacuation_dots

    evacuation_dots = compute_evacuation_dots(
        centerline_points, cage_polygons,
        green_max_m=max_dist_single_m, gray_max_m=max_dist_multi_m,
    )
```

i `evacuation_dots=evacuation_dots` w konstruktorze.

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_evacuation.py -v`
Expected: wszystkie PASS.

- [ ] **Step 3: LayoutResult + generate_layout (trzecia ścieżka)**

`services/layout.py` — do dataclass `LayoutResult` (po `stair_width_m`, linia 127):

```python
    evacuation_dots: list = field(default_factory=list)
    """Passthrough z CirculationResult -- /layout/generate serializuje kropki
    tak samo jak /layout/circulation (dual-surface gotcha)."""
```

W `generate_layout` w konstruktorze `LayoutResult(...)` dodaj:

```python
        evacuation_dots=circulation.evacuation_dots,
```

- [ ] **Step 4: Serializacja we wszystkich trzech odpowiedziach**

`backend/api/v1/endpoints/layout.py`:

Wspólny model + helper (obok `CenterlineSegmentResult`, linia 258):

```python
class EvacuationDotResult(BaseModel):
    x: float
    y: float
    status: str
    distance_m: float | None = None


def _serialize_dots(dots) -> list["EvacuationDotResult"]:
    return [
        EvacuationDotResult(
            x=d.x, y=d.y, status=d.status,
            distance_m=_finite_or_none(d.distance_m) if d.distance_m is not None else None,
        )
        for d in dots
    ]
```

Pola w modelach odpowiedzi (wszystkie trzy):

```python
    evacuation_dots: list[EvacuationDotResult] = []
```

— w `CirculationResponse` (za `centerline`, linia 271), w
`LayoutGenerateResponse` (za `wall_bands`, linia 84) i w
`ReshapeCirculationResponse` (za jego `centerline`).

Wypełnienie:
- `place_circulation_endpoint`: `evacuation_dots=_serialize_dots(result.evacuation_dots)` w konstruktorze odpowiedzi (linia 299).
- `reshape_circulation_endpoint`: analogicznie w jego konstruktorze odpowiedzi.
- `layout_result_to_response` (linia 134): `evacuation_dots=_serialize_dots(layout.evacuation_dots)`.

Progi w requestach — `CirculationSpec` (linia 26, za `num_cages` / polami
manuali z Etapu 2):

```python
    max_dist_single_m: float = Field(default=20.0, gt=0)
    """Edytowalny próg zielonej kropki (heurystyka usera, nie § WT)."""
    max_dist_multi_m: float = Field(default=40.0, gt=0)
    """Edytowalny próg szarej kropki (>=2 klatki osiągalne)."""
```

`place_circulation_endpoint` przekazuje oba do `place_circulation(...)`:

```python
        max_dist_single_m=circulation.max_dist_single_m,
        max_dist_multi_m=circulation.max_dist_multi_m,
```

`ReshapeCirculationRequest` dostaje te same dwa pola (z tymi samymi
defaultami), a `reshape_circulation_endpoint` przekazuje je do
`reshape_circulation(...)`. `LayoutInput` (services/layout.py) dostaje
`max_dist_single_m: float = 20.0` / `max_dist_multi_m: float = 40.0`,
`generate_layout` przekazuje je do `place_circulation`, a
`generate_layout_endpoint` mapuje z `request.circulation` (trzecia
ścieżka — dual-surface).

- [ ] **Step 5: Testy całości + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS.

```bash
git add backend/services/circulation.py backend/services/layout.py backend/api/v1/endpoints/layout.py backend/tests/test_evacuation.py
git commit -m "feat: thread evacuation_dots through circulation, reshape and generate responses"
```

---

### Task 3: Frontend — render kropek, neutralna oś, podsumowanie w panelu

**Files:**
- Modify: `frontend/app/lib/api.ts` (`CirculationResponse` :193-198, `ReshapeCirculationResponse` :214-218, `LayoutGenerateResponse`)
- Modify: `frontend/app/CanvasEditor.tsx:750-773` (render osi), nowy blok kropek
- Modify: `frontend/app/components/CirculationSection.tsx` (podsumowanie)
- Modify: `frontend/app/state/SessionContext.tsx` (case `RESHAPE_CIRCULATION` — przeniesienie dots)

**Interfaces:**
- Consumes: pole `evacuation_dots` z Task 2
- Produces: kompletny UI Etapu 3

- [ ] **Step 1: Typy api.ts**

Obok `CorridorCenterlineSegment` dodaj:

```ts
export interface EvacuationDot {
  x: number;
  y: number;
  status: "green" | "gray" | "red";
  distance_m: number | null;
}
```

Dodaj pole `evacuation_dots?: EvacuationDot[];` (OPCJONALNE w TS) do
`CirculationResponse`, `ReshapeCirculationResponse` i
`LayoutGenerateResponse`. Opcjonalność jest celowa: `runSubdivideUnits`
w SessionContext buduje obiekt `LayoutGenerateResponse` ręcznie (linie
~553-566) — wymagane pole wymusiłoby dopisywanie go tam i w każdym
przyszłym miejscu konstrukcji; fallback `?? []` w miejscach odczytu
załatwia to samo bezpieczniej.

- [ ] **Step 2: SessionContext — reshape przenosi kropki**

W reducerze, case `RESHAPE_CIRCULATION` aktualizuje `circulationResult`
polami z odpowiedzi reshape — upewnij się, że przepisuje też
`evacuation_dots: action.result.evacuation_dots` (obok `centerline`,
`circulation_geometry`, `remainder` — wzoruj się na istniejących
przepisywanych polach tego case'a).

- [ ] **Step 3: CanvasEditor — neutralna oś + kropki**

Render osi (linia 755) — zamień:

```tsx
              stroke={seg.exceeds_max ? "#ef4444" : "#22c55e"}
```

na:

```tsx
              stroke="#60a5fa"
```

Po bloku wierzchołków osi korytarza (za linią ~853) dodaj render kropek:

```tsx
          {/* Kropki ewakuacyjne co 1m (spec 2026-07-04-evacuation-dots §4).
              Zawsze widoczne gdy są w wyniku -- informacja projektowa, nie
              narzędzie edycji; listening=false, żeby nie łapały myszy. */}
          {(() => {
            const dots =
              state.circulationResult?.evacuation_dots ??
              state.layoutResult?.evacuation_dots ??
              [];
            const fill = { green: "#22c55e", gray: "#9ca3af", red: "#ef4444" } as const;
            return dots.map((d, i) => (
              <Circle
                key={`evac-dot-${i}`}
                x={d.x * METER_PX}
                y={-d.y * METER_PX}
                radius={3 / scale}
                fill={fill[d.status]}
                listening={false}
              />
            ));
          })()}
```

- [ ] **Step 4: Podsumowanie w panelu Komunikacja**

W `CirculationSection.tsx`, pod listą elementów ręcznych (koniec sekcji,
przed `</section>`):

```tsx
      {(() => {
        const dots = state.circulationResult?.evacuation_dots ?? [];
        if (dots.length === 0) return null;
        const reds = dots.filter((d) => d.status === "red").length;
        return (
          <div
            className={`rounded-lg px-2 py-1.5 text-[11px] ${
              reds > 0
                ? "border border-red-500/20 bg-red-500/10 text-red-300 light:text-red-700"
                : "border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 light:text-emerald-700"
            }`}
          >
            {reds > 0 ? `Dojścia: ${reds} pkt poza limitem (20/40m)` : "Dojścia: OK (limity 20/40m)"}
          </div>
        );
      })()}
```

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/CanvasEditor.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: render evacuation dots, neutral centerline color, panel summary"
```

---

### Task 4: Progi edytowalne w panelu + endpoint PRZELICZ

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (nowy endpoint za `/circulation/reshape`)
- Modify: `frontend/app/lib/api.ts` (`CirculationSpecInput`, nowa funkcja `recomputeEvacuation`)
- Modify: `frontend/app/state/SessionContext.tsx` (initialCirculation, nowy callback `runRecomputeEvacuation`, akcja `SET_EVACUATION_DOTS`)
- Modify: `frontend/app/components/CirculationSection.tsx` (dwa inputy + przycisk PRZELICZ)

**Interfaces:**
- Consumes: `compute_evacuation_dots(segments, cages, green_max_m, gray_max_m)` (Task 1), `_serialize_dots`/`EvacuationDotResult` (Task 2)
- Produces: `POST /layout/evacuation` — przelicza TYLKO kropki (bez geometrii); `runRecomputeEvacuation()` w SessionContext

- [ ] **Step 1: Endpoint backendu**

W `backend/api/v1/endpoints/layout.py`, za `reshape_circulation_endpoint`:

```python
class EvacuationRecomputeRequest(BaseModel):
    centerline: list[dict]
    """[{points: [[x,y],[x,y]]}] -- aktualna oś z frontendu (auto+manual+reshape)."""
    cage_geometries: list[dict] = Field(default_factory=list)
    max_dist_single_m: float = Field(default=20.0, gt=0)
    max_dist_multi_m: float = Field(default=40.0, gt=0)


class EvacuationRecomputeResponse(BaseModel):
    evacuation_dots: list[EvacuationDotResult] = []


@router.post("/evacuation", response_model=EvacuationRecomputeResponse)
def recompute_evacuation_endpoint(request: EvacuationRecomputeRequest):
    """PRZELICZ (spec 2026-07-04-evacuation-dots §3): przemalowuje kropki
    po zmianie progów BEZ ruszania geometrii -- ręcznie przesunięta oś
    zostaje dokładnie tam, gdzie user ją zostawił."""
    from services.evacuation import compute_evacuation_dots

    try:
        segments = [
            ((seg["points"][0][0], seg["points"][0][1]), (seg["points"][1][0], seg["points"][1][1]))
            for seg in request.centerline
        ]
        cages = [_shape(g) for g in request.cage_geometries]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid evacuation payload: {exc}")

    dots = compute_evacuation_dots(
        segments, cages,
        green_max_m=request.max_dist_single_m, gray_max_m=request.max_dist_multi_m,
    )
    return EvacuationRecomputeResponse(evacuation_dots=_serialize_dots(dots))
```

- [ ] **Step 2: api.ts**

`CirculationSpecInput` — dodaj `max_dist_single_m: number;
max_dist_multi_m: number;`. Nowa funkcja:

```ts
export function recomputeEvacuation(req: {
  centerline: { points: [Point, Point] }[];
  cage_geometries: GeoJsonPolygon[];
  max_dist_single_m: number;
  max_dist_multi_m: number;
}): Promise<{ evacuation_dots: EvacuationDot[] }> {
  return postJson("/layout/evacuation", req);
}
```

- [ ] **Step 3: SessionContext**

`initialCirculation` — dodaj `max_dist_single_m: 20, max_dist_multi_m: 40,`.

Akcja + reducer:

```ts
  | { type: "SET_EVACUATION_DOTS"; dots: api.EvacuationDot[] }
```

```ts
    case "SET_EVACUATION_DOTS":
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: { ...state.circulationResult, evacuation_dots: action.dots },
      };
```

Callback (wpisany też do interfejsu i `value`, wzorzec `runPlaceCirculation`):

```ts
  const runRecomputeEvacuation = useCallback(async () => {
    if (!state.circulationResult?.centerline?.length) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const res = await api.recomputeEvacuation({
        centerline: state.circulationResult.centerline.map((seg) => ({ points: seg.points })),
        cage_geometries: state.circulationResult.cage_geometries,
        max_dist_single_m: state.circulation.max_dist_single_m,
        max_dist_multi_m: state.circulation.max_dist_multi_m,
      });
      dispatch({ type: "SET_EVACUATION_DOTS", dots: res.evacuation_dots });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.circulationResult, state.circulation.max_dist_single_m, state.circulation.max_dist_multi_m]);
```

- [ ] **Step 4: Panel — inputy + PRZELICZ**

W `CirculationSection.tsx`, po polu „Szerokość korytarza" (linia ~136):

```tsx
      <label className="flex items-center justify-between text-xs text-zinc-400">
        Dojście do 1 klatki ≤ (m)
        <input
          type="number" step={1} min={1}
          value={state.circulation.max_dist_single_m}
          onChange={(e) => setCirculation({ max_dist_single_m: Number(e.target.value) })}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>
      <label className="flex items-center justify-between text-xs text-zinc-400">
        Dojście do ≥2 klatek ≤ (m)
        <input
          type="number" step={1} min={1}
          value={state.circulation.max_dist_multi_m}
          onChange={(e) => setCirculation({ max_dist_multi_m: Number(e.target.value) })}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>
```

Do bloku przycisków (za „Edytuj linię korytarza") — do destrukturyzacji
dodaj `runRecomputeEvacuation`:

```tsx
        <button
          onClick={() => void runRecomputeEvacuation()}
          disabled={!state.circulationResult || state.isLoading}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-zinc-800/70 px-2 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700/70 disabled:opacity-30 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          title="Przelicz kropki dojść po zmianie progów — bez ruszania geometrii"
        >
          PRZELICZ dojścia
        </button>
```

- [ ] **Step 5: Typecheck + testy + commit**

Run: `cd frontend && npx tsc --noEmit` oraz `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: exit 0 / wszystkie PASS.

```bash
git add backend/api/v1/endpoints/layout.py frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: editable evacuation thresholds with PRZELICZ recompute endpoint"
```

---

### Task 5: Weryfikacja ręczna (spec §6)

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1–4 (+ Etap 2 dla scenariuszy manualnych)
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. Obrys + auto-komunikacja → kropki co 1m wzdłuż osi; przy 1 klatce zielone blisko, czerwone daleko (>20m).
2. Dorysuj ręczną klatkę przy drugim końcu korytarza (Etap 2) → kropki między klatkami przechodzą na szare.
3. Przeciągnij/wydłuż oś poza 40m od obu klatek → środek czerwony.
4. Oś neutralna (#60a5fa) — starych zielonych/czerwonych ODCINKÓW brak.
5. Panel: licznik „Dojścia: N pkt poza limitem" zmienia się z geometrią; przy zerze czerwonych — „Dojścia: OK".
6. „Generuj układ" (pełna ścieżka /generate) → kropki też widoczne (dual-surface potwierdzony).
7. Zmiana progu 20→30 + „PRZELICZ dojścia" → część czerwonych → zielone; oś/korytarze/ściany NIE drgnęły (także po ręcznym reshape osi).
8. Regresja: edycja osi (dblclick/drag), manuale, podział na mieszkania.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
