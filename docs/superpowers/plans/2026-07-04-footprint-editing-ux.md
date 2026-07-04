# Etap 0+1: Wyłączenie solar/optymalizatora + UX edycji obrysu — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ukryć sekcje Solar/Optymalizator za flagą oraz dodać pełną edycję obrysu budynku: hover-highlight ścian i węzłów, dblclick wstaw/usuń punkt, drag całego odcinka (swobodny / Shift-prostopadły).

**Architecture:** Rozszerzamy istniejący tryb `edit-vertices` w `CanvasEditor.tsx` (bez nowych trybów, bez refactoru). Geometria edycji ląduje w nowym module czystych funkcji `frontend/app/lib/polygonEdit.ts`. Stan obrysu podmieniany w całości nową akcją `SET_FOOTPRINT_POINTS` w `SessionContext`, która unieważnia wyniki pochodne identycznie jak istniejące `UPDATE_VERTEX`.

**Tech Stack:** Next.js + React, react-konva/Konva 9, TypeScript. Backend nietykany.

**Spec:** `docs/superpowers/specs/2026-07-04-footprint-editing-ux-design.md`

## Global Constraints

- **Bez testów automatycznych** — decyzja usera. Zamiast cyklu TDD: implementacja → `npx tsc --noEmit` w `frontend/` → weryfikacja ręczna → commit.
- Snap siatki: `SNAP_M = 0.5` m (wartość istniejąca, przenoszona do `polygonEdit.ts`).
- Obrys ma minimum 3 punkty — usuwanie poniżej tej liczby zablokowane.
- Konwencja canvasa: świat w metrach, oś Y do góry; canvas w px, oś Y w dół. Konwersja: `x_px = x_m * METER_PX`, `y_px = -y_m * METER_PX` (`METER_PX = 50`).
- Konva event-bubbling: KAŻDY handler `onDragStart`/`onDragEnd`/`onDblClick` na obiektach wewnątrz Stage MUSI ustawiać `e.cancelBubble = true` — inaczej Stage łapie zdarzenie i „odlatuje" widok (znany, wielokrotnie naprawiany bug w tym pliku).
- Kolor akcentu interakcji na canvasie: `#60a5fa` (używany już przy rysowaniu obrysu).
- Uruchomienie dev: backend `backend/.venv/Scripts/python.exe -m uvicorn main:app --reload` z katalogu `backend/` (globalny python NIE MA zależności); frontend `npm run dev -- -p 3001` z `frontend/` (port 3000 zajęty przez zewnętrzny proces whatsapp-bridge).

---

### Task 1: Flaga SHOW_SOLAR_OPTIMIZER (Etap 0)

**Files:**
- Modify: `frontend/app/components/Sidebar.tsx` (linie 14–19 i 63–107)

**Interfaces:**
- Consumes: nic
- Produces: stała modułowa `SHOW_SOLAR_OPTIMIZER: boolean` w `Sidebar.tsx` (nieeksportowana — dotyczy tylko tego pliku)

- [ ] **Step 1: Dodaj flagę i odfiltruj zakładki**

W `frontend/app/components/Sidebar.tsx` zamień obecną definicję `TABS` (linie 14–19):

```tsx
const TABS = [
  { key: "layout", label: "Układ", icon: LayoutGrid },
  { key: "solar", label: "Słońce", icon: Sun },
  { key: "optimizer", label: "Optymalizacja", icon: Sparkles },
  { key: "export", label: "Eksport", icon: Download },
] as const;
```

na:

```tsx
/** Etap 0 (spec 2026-07-04 footprint-editing-ux §1): analiza słońca i
 *  optymalizator wyłączone z UI do czasu ukończenia etapów 1–4.
 *  Backend (solar.py, optimizer.py) zostaje nietknięty — przywrócenie to
 *  zmiana tej jednej flagi. */
const SHOW_SOLAR_OPTIMIZER = false;

const ALL_TABS = [
  { key: "layout", label: "Układ", icon: LayoutGrid },
  { key: "solar", label: "Słońce", icon: Sun },
  { key: "optimizer", label: "Optymalizacja", icon: Sparkles },
  { key: "export", label: "Eksport", icon: Download },
] as const;

const TABS = ALL_TABS.filter(
  ({ key }) => SHOW_SOLAR_OPTIMIZER || (key !== "solar" && key !== "optimizer")
);
```

- [ ] **Step 2: Popraw typ activeTab**

W tym samym pliku (linia 23) typ stanu odwołuje się do `TABS` — po filtrze
typ się zwęża niepoprawnie. Zamień:

```tsx
const [activeTab, setActiveTab] = useState<(typeof TABS)[number]["key"]>("layout");
```

na:

```tsx
const [activeTab, setActiveTab] = useState<(typeof ALL_TABS)[number]["key"]>("layout");
```

- [ ] **Step 3: Ukryj sekcje w zakładce „Układ"**

W bloku `{activeTab === "layout" && (...)}` (linie 68–69) zamień:

```tsx
              <SolarSection />
              <OptimizerSection />
```

na:

```tsx
              {SHOW_SOLAR_OPTIMIZER && <SolarSection />}
              {SHOW_SOLAR_OPTIMIZER && <OptimizerSection />}
```

Bloków `{activeTab === "solar" && ...}` i `{activeTab === "optimizer" && ...}`
(linie 98–107) NIE ruszaj — po odfiltrowaniu zakładek są nieosiągalne, a
zostawienie ich minimalizuje diff i ułatwia przywrócenie.

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, bez błędów.

- [ ] **Step 5: Weryfikacja ręczna**

Uruchom frontend (backend niepotrzebny do tego kroku): `cd frontend && npm run dev -- -p 3001`.
Otwórz http://localhost:3001. Sprawdź:
- W nawigacji panelu bocznego są TYLKO zakładki „Układ" i „Eksport".
- W zakładce „Układ" nie ma sekcji „Słońce"/„Optymalizacja"; są Footprint, Program, Komunikacja, przycisk „Generuj układ", Walidacja.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/components/Sidebar.tsx
git commit -m "feat: hide solar and optimizer sections behind SHOW_SOLAR_OPTIMIZER flag (Etap 0)"
```

---

### Task 2: Moduł geometrii polygonEdit.ts

**Files:**
- Create: `frontend/app/lib/polygonEdit.ts`
- Modify: `frontend/app/CanvasEditor.tsx:12-21` (przeniesienie SNAP_M/snap)

**Interfaces:**
- Consumes: typ `Point2D` z `frontend/app/state/SessionContext.tsx` (`{ x: number; y: number }`)
- Produces (używane w Taskach 4–6):
  - `SNAP_M: number` (= 0.5)
  - `snap(value: number): number`
  - `type Delta = { dx: number; dy: number }`
  - `insertVertexAt(points: Point2D[], segmentIndex: number, point: Point2D): Point2D[] | null`
  - `removeVertexAt(points: Point2D[], index: number): Point2D[] | null`
  - `projectDeltaOnNormal(p1: Point2D, p2: Point2D, delta: Delta): Delta`
  - `constrainSegmentDelta(p1: Point2D, p2: Point2D, delta: Delta, perpendicular: boolean): Delta`
  - `translateSegment(points: Point2D[], segmentIndex: number, delta: Delta): Point2D[] | null`

Konwencja: `points` to otwarty ring obrysu (bez powtórzonego pierwszego punktu
na końcu — tak trzyma go `SessionContext.state.footprint`). Segment `i` łączy
`points[i]` z `points[(i+1) % n]`, więc segmentów jest tyle co punktów
(ostatni domyka wielokąt).

- [ ] **Step 1: Utwórz `frontend/app/lib/polygonEdit.ts`**

```ts
/** Czyste funkcje edycji obrysu budynku (spec 2026-07-04 footprint-editing-ux
 *  §2). Zero zależności od Konvy/Reacta — operują na ringu Point2D[]
 *  (otwartym: bez zduplikowanego pierwszego punktu; segment i łączy
 *  points[i] z points[(i+1) % n]). */

import type { Point2D } from "../state/SessionContext";

export const SNAP_M = 0.5; // snap do siatki co 0.5m (rysowanie, wierzchołki, linie podziału)

export function snap(value: number): number {
  return Math.round(value / SNAP_M) * SNAP_M;
}

export type Delta = { dx: number; dy: number };

const EPS = 1e-6;

function samePoint(a: Point2D, b: Point2D): boolean {
  return Math.abs(a.x - b.x) < EPS && Math.abs(a.y - b.y) < EPS;
}

/** Wstawia punkt (po snapie) za wierzchołkiem segmentIndex. Zwraca null,
 *  gdy punkt po snapie pokrywa się z którymś końcem segmentu — ten sam
 *  guard co przy wstawianiu punktu osi korytarza. */
export function insertVertexAt(
  points: Point2D[],
  segmentIndex: number,
  point: Point2D
): Point2D[] | null {
  const n = points.length;
  const snapped = { x: snap(point.x), y: snap(point.y) };
  const a = points[segmentIndex];
  const b = points[(segmentIndex + 1) % n];
  if (samePoint(snapped, a) || samePoint(snapped, b)) return null;
  return [...points.slice(0, segmentIndex + 1), snapped, ...points.slice(segmentIndex + 1)];
}

/** Usuwa wierzchołek. Zwraca null przy 3 punktach — obrys nie może
 *  zdegenerować się poniżej trójkąta (spec §4). */
export function removeVertexAt(points: Point2D[], index: number): Point2D[] | null {
  if (points.length <= 3) return null;
  return [...points.slice(0, index), ...points.slice(index + 1)];
}

/** Rzut delty na jednostkową normalną segmentu p1→p2 — zostaje tylko
 *  składowa prostopadła do ściany (drag z Shiftem). */
export function projectDeltaOnNormal(p1: Point2D, p2: Point2D, delta: Delta): Delta {
  const ex = p2.x - p1.x;
  const ey = p2.y - p1.y;
  const len = Math.hypot(ex, ey);
  if (len < EPS) return delta;
  const nx = -ey / len;
  const ny = ex / len;
  const dot = delta.dx * nx + delta.dy * ny;
  return { dx: dot * nx, dy: dot * ny };
}

/** Efektywna delta draga segmentu: opcjonalny rzut na normalną (Shift),
 *  potem snap OBU składowych do SNAP_M — końce leżące na siatce zostają na
 *  siatce. Dla ścian ukośnych snap może zejść z idealnej normalnej o <SNAP_M
 *  (świadomy trade-off: siatka ważniejsza niż idealna prostopadłość; dla
 *  ścian osiowych — dominujący przypadek — prostopadłość jest dokładna). */
export function constrainSegmentDelta(
  p1: Point2D,
  p2: Point2D,
  delta: Delta,
  perpendicular: boolean
): Delta {
  const d = perpendicular ? projectDeltaOnNormal(p1, p2, delta) : delta;
  return { dx: snap(d.dx), dy: snap(d.dy) };
}

/** Przesuwa oba końce segmentu o deltę (ze snapem końców). Zwraca null,
 *  gdy przesunięty koniec pokryłby się z sąsiednim wierzchołkiem
 *  (degeneracja obrysu — spec §4). */
export function translateSegment(
  points: Point2D[],
  segmentIndex: number,
  delta: Delta
): Point2D[] | null {
  const n = points.length;
  const i1 = segmentIndex;
  const i2 = (segmentIndex + 1) % n;
  const next = points.map((p, i) =>
    i === i1 || i === i2 ? { x: snap(p.x + delta.dx), y: snap(p.y + delta.dy) } : p
  );
  const prev = (i1 - 1 + n) % n;
  const after = (i2 + 1) % n;
  if (samePoint(next[i1], next[prev]) || samePoint(next[i2], next[after])) return null;
  return next;
}
```

- [ ] **Step 2: Przenieś SNAP_M/snap w CanvasEditor na import**

W `frontend/app/CanvasEditor.tsx` usuń lokalne definicje (linie 13 i 19–21):

```ts
const SNAP_M = 0.5; // snap do siatki co 0.5m (rysowanie, wierzchołki, linie podziału)
```

```ts
function snap(value: number): number {
  return Math.round(value / SNAP_M) * SNAP_M;
}
```

i dodaj do importów (obok istniejącego `import * as api from "./lib/api";`):

```ts
import { snap } from "./lib/polygonEdit";
```

(Zweryfikowane: `SNAP_M` w CanvasEditor jest używany wyłącznie wewnątrz
usuwanej funkcji `snap` — samego `SNAP_M` nie trzeba importować.)

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/lib/polygonEdit.ts frontend/app/CanvasEditor.tsx
git commit -m "feat: add polygonEdit pure-geometry module, move snap helpers out of CanvasEditor"
```

---

### Task 3: Akcja SET_FOOTPRINT_POINTS w SessionContext

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx` (union Action ~linia 122, reducer ~linia 191, interfejs ~linia 338, callbacki ~linia 441, obiekt value ~linia 744)

**Interfaces:**
- Consumes: nic nowego
- Produces (używane w Taskach 5–6): `setFootprintPoints(points: Point2D[]): void` w `SessionContextValue` — podmienia cały ring obrysu i unieważnia `layoutResult`/`validation`/`circulationResult`

- [ ] **Step 1: Dodaj typ akcji**

W union `Action`, bezpośrednio po linii `| { type: "UPDATE_VERTEX"; index: number; point: Point2D }`:

```ts
  | { type: "SET_FOOTPRINT_POINTS"; points: Point2D[] }
```

- [ ] **Step 2: Dodaj case w reducerze**

Bezpośrednio po zamykającej klamrze `case "UPDATE_VERTEX": { ... }`:

```ts
    case "SET_FOOTPRINT_POINTS":
      // Jak UPDATE_VERTEX wyżej: wyniki pochodne liczone ze starego obrysu
      // (layout, walidacja, komunikacja) są po tej podmianie nieaktualne.
      return {
        ...state,
        footprint: action.points,
        layoutResult: null,
        validation: null,
        circulationResult: null,
      };
```

- [ ] **Step 3: Dodaj metodę do interfejsu**

W `interface SessionContextValue`, po linii `updateVertex: (index: number, point: Point2D) => void;`:

```ts
  setFootprintPoints: (points: Point2D[]) => void;
```

- [ ] **Step 4: Dodaj callback**

Po istniejącym `const updateVertex = useCallback(...)` (linie 438–441):

```ts
  const setFootprintPoints = useCallback(
    (points: Point2D[]) => dispatch({ type: "SET_FOOTPRINT_POINTS", points }),
    []
  );
```

- [ ] **Step 5: Dodaj do obiektu value**

W obiekcie przekazywanym do providera (lista ~linia 744, obok `updateVertex`)
dodaj `setFootprintPoints`. Jeśli obiekt jest budowany przez `useMemo` z
tablicą zależności — dodaj `setFootprintPoints` również do zależności
(wzoruj się 1:1 na tym, jak wpisany jest `updateVertex`).

- [ ] **Step 6: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/state/SessionContext.tsx
git commit -m "feat: add SET_FOOTPRINT_POINTS action replacing whole footprint ring"
```

---

### Task 4: Hover-highlight ścian i węzłów obrysu

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (stan ~linia 337, pochodne ~linia 379, render obrysu ~linia 682, render wierzchołków ~linia 1136)

**Interfaces:**
- Consumes: nic nowego (czysty UI)
- Produces (używane w Taskach 5–6): stała pochodna `footprintSegments: [Point2D, Point2D][]` oraz stany `hoveredOutlineSegment`/`hoveredOutlineVertex` i hitboxy segmentów, na które Taski 5–6 dowieszą handlery

- [ ] **Step 1: Dodaj stany hover**

Obok istniejącego `const [hoveredFacade, setHoveredFacade] = useState<...>(null);` (~linia 337):

```ts
  const [hoveredOutlineSegment, setHoveredOutlineSegment] = useState<number | null>(null);
  const [hoveredOutlineVertex, setHoveredOutlineVertex] = useState<number | null>(null);
```

- [ ] **Step 2: Dodaj pochodną footprintSegments**

Obok pozostałych `useMemo` (po `const sharedLines = ...`, ~linia 379):

```ts
  // Segmenty obrysu jako pary punktów; segment i łączy footprint[i] z
  // footprint[(i+1) % n] — ostatni domyka wielokąt (konwencja polygonEdit.ts).
  const footprintSegments = useMemo<[Point2D, Point2D][]>(() => {
    if (!footprint || footprint.length < 2) return [];
    return footprint.map((p, i) => [p, footprint[(i + 1) % footprint.length]] as [Point2D, Point2D]);
  }, [footprint]);
```

- [ ] **Step 3: Dodaj podświetlenie i hitboxy segmentów**

Bezpośrednio PO bloku `{/* Obrys */}` (`<Line points={footprintCanvasPoints} ... />`, ~linia 690) dodaj:

```tsx
          {/* Podświetlenie ściany obrysu pod myszą (tryb edycji) */}
          {state.mode === "edit-vertices" &&
            hoveredOutlineSegment !== null &&
            footprintSegments[hoveredOutlineSegment] && (
              <Line
                points={toCanvasPoints([...footprintSegments[hoveredOutlineSegment]])}
                stroke="#60a5fa"
                strokeWidth={4 / scale}
                listening={false}
              />
            )}

          {/* Niewidoczne hitboxy segmentów obrysu: hover (Task 4),
              dblclick-wstaw (Task 5), drag ściany (Task 6) */}
          {state.mode === "edit-vertices" &&
            footprintSegments.map(([a, b], i) => (
              <Line
                key={`outline-hit-${i}`}
                points={toCanvasPoints([a, b])}
                stroke="#000000"
                opacity={0}
                strokeWidth={2 / scale}
                hitStrokeWidth={14 / scale}
                onMouseEnter={() => setHoveredOutlineSegment(i)}
                onMouseLeave={() => setHoveredOutlineSegment(null)}
              />
            ))}
```

(Konva: `opacity={0}` nie wyłącza hit-detection — hit canvas rysuje kształt
niezależnie od przezroczystości; `hitStrokeWidth` poszerza strefę łapania.)

- [ ] **Step 4: Hover na węzłach**

W istniejącym renderze wierzchołków obrysu (`{/* Wierzchołki obrysu — edytowalne (F1-06) */}`, ~linia 1136) zamień:

```tsx
                radius={6 / scale}
                fill="#ffffff"
```

na:

```tsx
                radius={(hoveredOutlineVertex === i ? 9 : 6) / scale}
                fill={hoveredOutlineVertex === i ? "#60a5fa" : "#ffffff"}
```

i dodaj do tego samego `<Circle>` (obok `onDragStart`):

```tsx
                onMouseEnter={() => setHoveredOutlineVertex(i)}
                onMouseLeave={() => setHoveredOutlineVertex(null)}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 6: Weryfikacja ręczna**

Frontend + backend uruchomione (patrz Global Constraints). Narysuj obrys,
wejdź w tryb edycji wierzchołków. Sprawdź:
- Najechanie na ścianę → niebieskie podświetlenie znika/pojawia się płynnie.
- Najechanie na węzeł → kółko rośnie i robi się niebieskie.
- Pan/zoom canvasa działa bez zmian; poza trybem edycji brak podświetleń.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: hover-highlight footprint walls and vertices in edit mode"
```

---

### Task 5: Dblclick — wstaw punkt na ścianie, usuń węzeł

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (import ~linia 11, destrukturyzacja useSession ~linia 330, hitboxy z Taska 4, Circle wierzchołków ~linia 1136)

**Interfaces:**
- Consumes: `insertVertexAt`/`removeVertexAt` z `polygonEdit.ts` (Task 2), `setFootprintPoints` z `SessionContext` (Task 3), hitboxy segmentów (Task 4)
- Produces: nic dla kolejnych tasków

- [ ] **Step 1: Rozszerz import i destrukturyzację**

Import z Taska 2 rozszerz do:

```ts
import { snap, insertVertexAt, removeVertexAt } from "./lib/polygonEdit";
```

W destrukturyzacji `useSession()` na górze komponentu (~linia 330) dodaj
`setFootprintPoints` (wzoruj się na tym, jak pobierany jest `updateVertex`).

- [ ] **Step 2: Dblclick na hitboxie segmentu → wstaw punkt**

Do hitboxa z Taska 4 Step 3 dodaj handler:

```tsx
                onDblClick={(e) => {
                  e.cancelBubble = true;
                  if (!footprint) return;
                  const stage = stageRef.current;
                  const pointer = stage?.getPointerPosition();
                  if (!pointer) return;
                  const clicked = worldToMeters(pointer.x, pointer.y);
                  const next = insertVertexAt(footprint, i, clicked);
                  if (next) setFootprintPoints(next);
                }}
```

(`worldToMeters` już snapuje do 0.5m; `insertVertexAt` snapuje ponownie —
idempotentne. Zwraca null przy pokryciu z końcem segmentu → no-op, wzorzec
z osi korytarza.)

- [ ] **Step 3: Dblclick na węźle → usuń**

Do `<Circle>` wierzchołków obrysu (ten sam co w Tasku 4 Step 4) dodaj:

```tsx
                onDblClick={(e) => {
                  e.cancelBubble = true;
                  if (!footprint) return;
                  const next = removeVertexAt(footprint, i);
                  if (next) setFootprintPoints(next);
                }}
```

(`removeVertexAt` zwraca null przy 3 punktach → dblclick ignorowany.)

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Weryfikacja ręczna**

W trybie edycji wierzchołków:
- Dblclick na ścianie dodaje węzeł w klikniętym miejscu (na siatce 0.5m); obrys się nie zmienia kształtem.
- Dblclick na węźle usuwa go; przy obrysie 3-punktowym dblclick nic nie robi.
- Po każdej edycji wynik generacji znika (unieważniony) — przycisk „Generuj układ" działa i liczy od nowego obrysu.
- Widok NIE odlatuje po dblclicku (cancelBubble działa).

- [ ] **Step 6: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: dblclick inserts/removes footprint vertex (min-3 guard)"
```

---

### Task 6: Drag odcinka obrysu (swobodny / Shift-prostopadły)

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (import, stan draga, hitboxy z Taska 4, render podglądu)

**Interfaces:**
- Consumes: `constrainSegmentDelta`/`translateSegment`/`Delta` z `polygonEdit.ts` (Task 2), `setFootprintPoints` (Task 3), hitboxy segmentów (Task 4)
- Produces: nic dla kolejnych tasków

- [ ] **Step 1: Rozszerz import i dodaj stan draga**

Import rozszerz do:

```ts
import {
  snap,
  insertVertexAt,
  removeVertexAt,
  constrainSegmentDelta,
  translateSegment,
  type Delta,
} from "./lib/polygonEdit";
```

Obok stanów hover z Taska 4 dodaj:

```ts
  // Podgląd przeciąganego segmentu obrysu: delta już po constrainie
  // (Shift-rzut na normalną + snap 0.5m) — render liczy translateSegment
  // z aktualnego footprint, commit robi to samo w onDragEnd.
  const [segmentDrag, setSegmentDrag] = useState<{ index: number; delta: Delta } | null>(null);
```

- [ ] **Step 2: Dodaj drag do hitboxa segmentu**

Do hitboxa z Taska 4 Step 3 dodaj:

```tsx
                draggable
                onDragStart={(e) => {
                  e.cancelBubble = true;
                }}
                onDragMove={(e) => {
                  const node = e.target;
                  const [a, b] = footprintSegments[i];
                  // node.x/y to translacja w px świata (Stage skaluje potomków)
                  const raw: Delta = { dx: node.x() / METER_PX, dy: -node.y() / METER_PX };
                  const d = constrainSegmentDelta(a, b, raw, e.evt.shiftKey);
                  setSegmentDrag({ index: i, delta: d });
                }}
                onDragEnd={(e) => {
                  // cancelBubble: patrz komentarz przy onDragEnd wierzchołków —
                  // bez tego Stage czyta surowe współrzędne node'a i „odlatuje".
                  e.cancelBubble = true;
                  const node = e.target;
                  const [a, b] = footprintSegments[i];
                  const raw: Delta = { dx: node.x() / METER_PX, dy: -node.y() / METER_PX };
                  node.position({ x: 0, y: 0 });
                  setSegmentDrag(null);
                  if (!footprint) return;
                  const d = constrainSegmentDelta(a, b, raw, e.evt.shiftKey);
                  const next = translateSegment(footprint, i, d);
                  if (next) setFootprintPoints(next);
                }}
```

(Stan Shift czytany z `e.evt.shiftKey` przy KAŻDYM `dragmove` — wciśnięcie/
puszczenie w trakcie draga działa. `translateSegment` zwraca null przy
degeneracji → drag porzucony, obrys bez zmian = revert ze specu §4.)

- [ ] **Step 3: Render podglądu przeciąganego obrysu**

Bezpośrednio po bloku podświetlenia ściany (Task 4 Step 3) dodaj:

```tsx
          {/* Podgląd obrysu podczas draga ściany (dashed, jak rysowanie) */}
          {state.mode === "edit-vertices" &&
            segmentDrag &&
            footprint &&
            (() => {
              const preview = translateSegment(footprint, segmentDrag.index, segmentDrag.delta);
              if (!preview) return null;
              return (
                <Line
                  points={toCanvasPoints(preview)}
                  closed
                  stroke="#60a5fa"
                  strokeWidth={2 / scale}
                  dash={[6 / scale, 4 / scale]}
                  listening={false}
                />
              );
            })()}
```

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Weryfikacja ręczna**

W trybie edycji wierzchołków:
- Złap ścianę i ciągnij bez Shift → dashed podgląd jedzie za myszą w dowolnym kierunku, skoki co 0.5m.
- Z Shiftem → podgląd rusza się TYLKO prostopadle do ściany; kąty sąsiadów zachowane (sprawdź na ścianie pionowej i poziomej).
- Wciśnij/puść Shift w trakcie draga → tryb zmienia się w locie.
- Puść mysz → obrys przyjmuje kształt podglądu, węzły na siatce 0.5m.
- Drag węzła pojedynczego działa jak wcześniej; pan/zoom bez zmian; widok nie odlatuje po dragu.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: drag footprint wall segment, free or Shift-perpendicular, 0.5m snap"
```

---

### Task 7: Pełna weryfikacja ręczna (spec §5) + regresja

**Files:** brak zmian w kodzie (task weryfikacyjny; ewentualne poprawki wg znalezisk)

**Interfaces:**
- Consumes: całość Tasków 1–6
- Produces: potwierdzenie wykonania scenariusza ze specu §5

- [ ] **Step 1: Uruchom aplikację**

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload
```

```bash
cd frontend && npm run dev -- -p 3001
```

- [ ] **Step 2: Przejdź scenariusz specu §5**

1. Solar i Optymalizator niewidoczne; zakładki tylko „Układ" i „Eksport".
2. Narysuj obrys → tryb edycji → hover podświetla ściany i węzły.
3. Dblclick na ścianie wstawia punkt; dblclick na punkcie usuwa; przy 3 punktach usuwanie zablokowane.
4. Drag ściany bez Shift swobodny; z Shift prostopadły; Shift przełączalny w locie.
5. Po edycji obrysu „Generuj układ" działa — ściany 40cm (wall_bands) i strefy renderują się poprawnie na NOWYM obrysie.
6. Regresja: rysowanie obrysu od zera, drag pojedynczego węzła, edycja osi korytarza (dblclick wstaw/usuń, drag), przesuwanie komunikacji, eksport — bez zmian zachowania.

- [ ] **Step 3: Napraw znaleziska (jeśli są) i commituj każdą poprawkę osobno**

Format commitów poprawek: `fix: <co> (<który punkt scenariusza>)`.

- [ ] **Step 4: Zgłoś wynik userowi**

Raport: która część scenariusza przeszła, co poprawiono, co ewentualnie
zostaje jako znane ograniczenie (spec §4 przewiduje brak walidacji
samoprzecięć).
