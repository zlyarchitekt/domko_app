# Kolory mieszkań wg typu + mieszkanie kończy się na ścianie — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) Każdy typ mieszkania (M1–M5) dostaje przypisywalny kolor przez okrągły swatch przy wierszu w panelu „Struktura mieszkań"; mieszkania tego typu wypełniają się tym kolorem, a dotychczasowe kolorowanie statusem walidacji staje się kolorem obramowania. (B) Strefa mieszkania przestaje „wylewać się" na ścianę — renderuje się na poligonie NETTO (w świetle ścian) zamiast surowym (na osiach).

**Architecture:** Backend już liczy poligon netto dla `net_area_m2` (`net_polygon`, `wall_geometry.py`) — dokładamy serializację tego poligonu jako `ApartmentResult.net_geometry` we wszystkich trzech miejscach konstrukcji (dual-surface: `/generate`, `/units`, per-iteracja), bez dotykania silnika. Frontend: nowe pole `typeColors: Record<string,string>` na `SessionState` (kluczowane typem, trwałe przez istniejący `localStorage`, backfill w `RESTORE_STATE`); natywny `<input type="color">` w okrągłym swatchu w `ProgramSection.tsx`; przebieg renderu mieszkań w `CanvasEditor.tsx:1116` rozdziela fill (kolor per typ) od stroke (kolor statusu) i przełącza geometrię z surowej na `apt.net_geometry ?? apt.geometry`. Kolejność z-order (`wall_bands` pod mieszkaniami) NIE wymaga zmiany — gdy mieszkanie jest netto, pasy ścian wypełniają szczeliny bez zasłaniania.

**Tech Stack:** shapely + FastAPI/Pydantic (backend), Next.js/react-konva (frontend). Zero nowych zależności (`<input type="color">` natywny).

**Spec:** `docs/superpowers/specs/2026-07-06-apartment-type-colors-design.md`
**Wymaga:** Etap wall-thickness (`net_polygon`, `wall_bands`, commit e36d000) + iteracyjny podział mieszkań (`_serialize_unit_iteration`) — wdrożone.

## Global Constraints

- Backend venv: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v` — pełny przebieg musi PASS po każdym tasku backendowym. Globalny `python` w PATH nie ma zależności — ZAWSZE `.venv/Scripts/python.exe`.
- Frontend: brak testów automatycznych; `cd frontend && npx tsc --noEmit` musi zwrócić exit 0 po każdym tasku frontendowym.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001` (port 3000 zajęty przez whatsapp-bridge na tej maszynie).
- Git hygiene: `git add` TYLKO konkretne zmienione pliki po nazwie. NIGDY `git add -A`/`git add .`.
- Dual-surface (footgun z pamięci projektu — `net_area_m2` dwa razy gubiło się na ścieżce dwukrokowej): każde pole dodane do `ApartmentResult` musi zostać wypełnione we WSZYSTKICH trzech call-site'ach w `layout.py` (`layout_result_to_response`, `subdivide_units_endpoint`, `_serialize_unit_iteration`).
- Silnik geometrii (`unit_mix.py`, `circulation.py`, `wall_geometry.py`) zostaje NIETKNIĘTY — ten plan tylko serializuje i renderuje już-policzone kształty.

---

### Task 1: Backend — `net_geometry` na `ApartmentResult` (3 call-site'y)

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py` (`ApartmentResult` :116-122; import :17; call-site'y :279-285, :455-458, :693-698)
- Test: `backend/tests/test_layout_units_endpoint.py`, `backend/tests/test_layout.py`

**Interfaces:**
- Consumes: `net_polygon` (już importowany, :17)
- Produces: `_net_geometry_json(polygon) -> dict | None`; `ApartmentResult.net_geometry: dict | None` (konsumowane w Task 4 frontend)

- [ ] **Step 1: Napisz failing test endpointu**

Dopisz do `backend/tests/test_layout_units_endpoint.py`:

```python
def test_units_endpoint_apartments_carry_net_geometry():
    from fastapi.testclient import TestClient
    from shapely.geometry import Polygon
    from main import app

    client = TestClient(app)
    remainder = Polygon([(0, 0), (24, 0), (24, 10), (0, 10)]).__geo_interface__
    payload = {
        "remainder": dict(remainder),
        "footprint": [[0, 0], [24, 0], [24, 10], [0, 10]],
        "apartments": [
            {"type": "M2", "percentage": 50, "area_min_m2": 38, "area_max_m2": 48,
             "min_area_m2": 43, "target_count": 0},
            {"type": "M3", "percentage": 50, "area_min_m2": 58, "area_max_m2": 70,
             "min_area_m2": 64, "target_count": 0},
        ],
        "iterations": 5,
    }
    res = client.post("/api/v1/layout/units", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    # wynik główny
    assert body["apartments"], "brak mieszkań w wyniku"
    for apt in body["apartments"]:
        assert "net_geometry" in apt
        assert apt["net_geometry"] is not None, "mieszkanie normalnej wielkości musi mieć netto"
        # netto skurczone względem surowego -> mniejsze pole
        raw_ring = apt["geometry"]["coordinates"][0]
        net_ring = apt["net_geometry"]["coordinates"][0]
        assert len(net_ring) >= 4
        # dual-surface: to samo w każdej iteracji
    for it in body["iterations"]:
        for apt in it["apartments"]:
            assert "net_geometry" in apt
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout_units_endpoint.py -k net_geometry -v`
Expected: FAIL — `KeyError: 'net_geometry'` (pole jeszcze nie istnieje w odpowiedzi). Potwierdź, że to ten błąd, nie inny.

- [ ] **Step 2: Dodaj pole `net_geometry` do modelu `ApartmentResult`**

W `backend/api/v1/endpoints/layout.py`, `ApartmentResult` (:116):

```python
class ApartmentResult(BaseModel):
    id: str
    type: str
    area_m2: float
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian -- spec 2026-07-04 wall-thickness §5.2."""
    geometry: dict
    net_geometry: dict | None = None
    """Poligon netto (w świetle ścian) do wypełnienia strefy mieszkania na
    froncie -- spec 2026-07-06 apartment-type-colors §3.2. None gdy netto
    puste (komórka zbyt mała) lub nie jest prostym Polygonem; front spada
    wtedy na `geometry` (surowy, na osiach)."""
```

- [ ] **Step 3: Dodaj helper `_net_geometry_json`**

W `backend/api/v1/endpoints/layout.py`, tuż przed `_serialize_unit_iteration` (:453) — obok pozostałych helperów `_serialize_*`:

```python
def _net_geometry_json(polygon: Polygon) -> dict | None:
    """GeoJSON poligonu netto (w świetle ścian) -- spec 2026-07-06
    apartment-type-colors §3.2. None gdy netto puste albo nie jest prostym
    Polygonem (ringToPoints na froncie czyta coordinates[0], więc
    MultiPolygon odpada -> front spada na geometrię surową)."""
    net = net_polygon(polygon)
    if net.is_empty or net.geom_type != "Polygon":
        return None
    return json.loads(json.dumps(net.__geo_interface__))
```

(`net_polygon`, `json`, `Polygon` są już zaimportowane w tym pliku — `net_polygon` w linii importu :17, `Polygon` z shapely, `json` używany w całym pliku. Nie dodawaj nowych importów; potwierdź grep-em jeśli wątpliwe.)

- [ ] **Step 4: Wypełnij `net_geometry` we WSZYSTKICH trzech call-site'ach**

Call-site 1 — `layout_result_to_response` (:279):

```python
    apartments_out = [
        ApartmentResult(
            id=a.id,
            type=a.type,
            area_m2=a.polygon.area,
            net_area_m2=a.net_area_m2,
            geometry=json.loads(json.dumps(a.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(a.polygon),
        )
        for a in layout.apartments
    ]
```

Call-site 2 — `_serialize_unit_iteration` (:455):

```python
    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area, net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(c.polygon),
        )
        for c in m.cells
    ]
```

Call-site 3 — `subdivide_units_endpoint` (:693):

```python
    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area,
            net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
            net_geometry=_net_geometry_json(c.polygon),
        )
        for c in cells
    ]
```

- [ ] **Step 5: Uruchom test — powinien przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout_units_endpoint.py -k net_geometry -v`
Expected: PASS.

- [ ] **Step 6: Test /generate + test degradacji dla komórki zbyt małej**

Dopisz do `backend/tests/test_layout.py` (endpoint `/layout/generate`) test sprawdzający obecność `net_geometry` na `apartments[]` (analogiczny do Step 1, ale dla `/layout/generate` — użyj istniejącego w tym pliku wzorca payloadu `/generate`, nie kopiuj payloadu /units).

Dopisz do `backend/tests/test_layout.py` test jednostkowy helpera:

```python
def test_net_geometry_json_none_for_tiny_cell():
    from api.v1.endpoints.layout import _net_geometry_json
    from shapely.geometry import box

    # 15x15cm -- za małe, żeby przetrwać skurczenie o 10cm z każdej strony
    assert _net_geometry_json(box(0, 0, 0.15, 0.15)) is None
    # normalny prostokąt -> dict GeoJSON
    net = _net_geometry_json(box(0, 0, 5, 4))
    assert net is not None and net["type"] == "Polygon"
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_layout.py -k "net_geometry" -v`
Expected: PASS.

- [ ] **Step 7: Pełny przebieg + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS (istniejące testy `ApartmentResult` nie sprawdzają braku pól, więc nowe opcjonalne pole ich nie zepsuje).

```bash
git add backend/api/v1/endpoints/layout.py backend/tests/test_layout_units_endpoint.py backend/tests/test_layout.py
git commit -m "feat: ApartmentResult carries net_geometry (in-the-clear polygon) on all 3 surfaces"
```

---

### Task 2: Frontend — typ w API + stan `typeColors` w SessionContext

**Files:**
- Modify: `frontend/app/lib/api.ts` (`ApartmentResult` :192-198)
- Modify: `frontend/app/state/SessionContext.tsx` (`DEFAULT_UNIT_WEIGHTS` :116; `SessionState` :65-97; `initialState` :129-169; `Action` union :171-213; reducer :301 i :466/:571; callbacki :656; `SessionContextValue` :505-551; `value` :1150-1210)

**Interfaces:**
- Consumes: `ApartmentResult.net_geometry` (Task 1)
- Produces: `state.typeColors`, `DEFAULT_TYPE_COLORS`, `setTypeColor` (konsumowane w Task 3/4)

- [ ] **Step 1: `api.ts` — pole `net_geometry`**

W `frontend/app/lib/api.ts`, `ApartmentResult` (:192):

```ts
export interface ApartmentResult {
  id: string;
  type: string;
  area_m2: number;
  net_area_m2: number;
  geometry: GeoJsonPolygon;
  net_geometry?: GeoJsonPolygon | null;
}
```

- [ ] **Step 2: `DEFAULT_TYPE_COLORS` w SessionContext**

W `frontend/app/state/SessionContext.tsx`, obok `DEFAULT_UNIT_WEIGHTS` (:116):

```ts
/** Domyślna paleta kolorów wypełnienia per typ mieszkania -- spec
 * 2026-07-06 apartment-type-colors §2.1. Hex #rrggbb (to samo co zwraca
 * <input type="color">), rozróżnialne na obu motywach. User nadpisuje przez
 * swatch w ProgramSection; nadpisania trzymane w state.typeColors. */
export const DEFAULT_TYPE_COLORS: Record<string, string> = {
  M1: "#38bdf8",
  M2: "#34d399",
  M3: "#a78bfa",
  M4: "#fbbf24",
  M5: "#f472b6",
};
```

- [ ] **Step 3: `SessionState` + `initialState`**

W `SessionState` (:96, po `activeUnitSeed`):

```ts
  activeCageSeed: number | null;
  activeUnitSeed: number | null;
  typeColors: Record<string, string>;
```

W `initialState` (:168, po `activeUnitSeed: null,`):

```ts
  activeCageSeed: null,
  activeUnitSeed: null,
  typeColors: DEFAULT_TYPE_COLORS,
```

- [ ] **Step 4: Akcja + reducer**

W unii `Action` (:184, obok `SET_UNIT_WEIGHT`):

```ts
  | { type: "SET_TYPE_COLOR"; aptType: string; color: string }
```

W reducerze, obok `case "SET_UNIT_WEIGHT":` (:301):

```ts
    case "SET_TYPE_COLOR":
      return { ...state, typeColors: { ...state.typeColors, [action.aptType]: action.color } };
```

- [ ] **Step 5: Backfill w `RESTORE_STATE`**

W `SessionProvider`, w dispatchu `RESTORE_STATE` (:571-574), dołóż `typeColors` obok istniejącego merge'a `circulation` (ten sam wzorzec, ten sam powód — stara sesja bez pola rzuciłaby TypeError):

```ts
          dispatch({
            type: "RESTORE_STATE",
            state: {
              ...parsed,
              circulation: { ...initialCirculation, ...parsed.circulation },
              typeColors: { ...DEFAULT_TYPE_COLORS, ...parsed.typeColors },
            },
          });
```

(Zapis do `localStorage` nie wymaga zmian — cały `state` jest już serializowany, :582-585.)

- [ ] **Step 6: Callback + wpięcie do kontekstu**

Obok `setUnitWeight` (:656):

```ts
  const setTypeColor = useCallback(
    (aptType: string, color: string) => dispatch({ type: "SET_TYPE_COLOR", aptType, color }),
    []
  );
```

W interfejsie `SessionContextValue`, obok `setUnitWeight` (:518):

```ts
  setUnitWeight: (key: keyof api.UnitWeightsInput, value: number) => void;
  setTypeColor: (aptType: string, color: string) => void;
```

W obiekcie `value` (:1164, po `setUnitWeight,`) dodaj `setTypeColor,`; w tablicy zależności `useMemo` (:1207, po `setUnitWeight,`) dodaj `setTypeColor,`.

- [ ] **Step 7: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx
git commit -m "feat: typeColors state (per-apartment-type fill color) + net_geometry API field"
```

---

### Task 3: Frontend — okrągły swatch koloru w wierszu typu (ProgramSection)

**Files:**
- Modify: `frontend/app/components/ProgramSection.tsx` (import :3-5; destrukturyzacja :19-28; wiersz `<select>` :74-85)

**Interfaces:**
- Consumes: `state.typeColors`, `DEFAULT_TYPE_COLORS`, `setTypeColor` (Task 2)
- Produces: UI swatch (bez nowych eksportów)

- [ ] **Step 1: Import `DEFAULT_TYPE_COLORS` + destrukturyzacja `setTypeColor`**

W `frontend/app/components/ProgramSection.tsx`, zamień import (:4):

```ts
import { useSession, DEFAULT_TYPE_COLORS } from "../state/SessionContext";
```

W destrukturyzacji `useSession()` (:20-28) dodaj `setTypeColor`:

```ts
  const {
    state,
    updateProgramRow,
    addProgramRow,
    removeProgramRow,
    setUnitWeight,
    setTypeColor,
    selectUnitIteration,
    activeUnitSeed,
  } = useSession();
```

- [ ] **Step 2: Swatch przed `<select>`**

W wierszu programu, na początku `<div className="flex items-center gap-1.5">` (:74), PRZED `<select>` (:75) wstaw:

```tsx
            <div className="flex items-center gap-1.5">
              <label
                className="relative h-6 w-6 shrink-0 cursor-pointer rounded-full border border-zinc-600/60 light:border-zinc-300"
                style={{ backgroundColor: state.typeColors?.[row.type] ?? DEFAULT_TYPE_COLORS[row.type] ?? "#9ca3af" }}
                title={`Kolor mieszkań typu ${row.type} na rysunku`}
              >
                <input
                  type="color"
                  value={state.typeColors?.[row.type] ?? DEFAULT_TYPE_COLORS[row.type] ?? "#9ca3af"}
                  onChange={(e) => setTypeColor(row.type, e.target.value)}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label={`Kolor typu ${row.type}`}
                />
              </label>
              <select
```

(Reszta `<select>` bez zmian — tylko wstawiamy swatch przed nim. Swatch pokazuje aktualny kolor tłem labela; ukryty `<input type="color">` otwiera natywny próbnik OS po kliknięciu i wpina wartość przez `setTypeColor`.)

- [ ] **Step 3: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/components/ProgramSection.tsx
git commit -m "feat: per-apartment-type color swatch button in program panel"
```

---

### Task 4: Frontend — render mieszkań: fill per typ, stroke per status, geometria netto

**Files:**
- Modify: `frontend/app/CanvasEditor.tsx` (import :8; nowy helper obok `ringToPoints` :26-29; przebieg mieszkań :1116-1169 — konkretnie derivacja koloru :1116-1130, źródło `ring` :1133, propsy `<Line>` :1152-1153)

**Interfaces:**
- Consumes: `state.typeColors`, `DEFAULT_TYPE_COLORS` (Task 2); `apt.net_geometry` (Task 1)
- Produces: render (bez nowych eksportów)

- [ ] **Step 1: Import `DEFAULT_TYPE_COLORS`**

W `frontend/app/CanvasEditor.tsx`, zamień import (:8):

```ts
import { useSession, Point2D, DEFAULT_TYPE_COLORS } from "./state/SessionContext";
```

- [ ] **Step 2: Helper `hexToRgba`**

Obok `ringToPoints` (:26-29), dodaj:

```ts
/** #rrggbb (jak z <input type="color">) -> rgba() z zadaną alfą. Wypełnienie
 * mieszkania per typ musi być pół-przezroczyste (etykieta + pasy ścian pod
 * spodem czytelne) -- spec 2026-07-06 apartment-type-colors §2.3. */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  if ([r, g, b].some(Number.isNaN)) return `rgba(148, 163, 184, ${alpha})`;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
```

- [ ] **Step 3: Rozdziel fill/stroke i przełącz geometrię na netto**

W przebiegu mieszkań (:1116), zamień blok derivacji koloru + źródło `ring` (:1116-1133):

```tsx
          {/* Mieszkania — wypełnienie wg TYPU (spec 2026-07-06 §2.3),
              obramowanie wg statusu walidacji, geometria NETTO (§3.2). */}
          {apartments.map((apt) => {
            // W trybie Słońce (state.solarResult) fill/stroke zostają wg
            // logiki słonecznej; kolor per typ tylko w widoku domyślnym
            // (spec §2.3 "Decyzja: tryb Słońce"). Zmiana geometrii na netto
            // (niżej) obowiązuje w OBU widokach -- usterka §B jest
            // geometryczna, nie zależy od trybu koloru.
            let fill: string;
            let stroke: string;
            const hasSolarData = !!state.solarResult;
            if (hasSolarData) {
              const solFa = state.solarResult!.facades.filter(f => f.apartment_id === apt.id);
              if (solFa.length > 0) {
                const isPassing = solFa.some(f => f.meets_wt);
                fill = isPassing ? "rgba(249, 115, 22, 0.3)" : "rgba(75, 85, 99, 0.3)";
                stroke = isPassing ? "#f97316" : "#4b5563";
              } else {
                fill = "rgba(255,255,255,0.1)";
                stroke = "#666";
              }
            } else {
              const status = apartmentStatuses.get(apt.id) ?? "ok";
              stroke = STATUS_COLORS[status].stroke;
              const hex = state.typeColors?.[apt.type] ?? DEFAULT_TYPE_COLORS[apt.type] ?? "#9ca3af";
              fill = hexToRgba(hex, 0.45);
            }

            const isSelected = state.selectedApartmentId === apt.id;
            // Geometria NETTO (w świetle ścian) -- strefa kończy się na licu
            // ściany, nie na osi (spec 2026-07-06 §3.2). Fallback do surowej,
            // gdy backend nie przysłał netto (stara sesja / komórka zbyt mała).
            const ring = ringToPoints(apt.net_geometry ?? apt.geometry);
```

- [ ] **Step 4: Zaktualizuj propsy `<Line>`**

W tym samym przebiegu, w `<Line>` (:1152-1153), zamień odwołania do usuniętego `colors`:

```tsx
                <Line
                  points={pts}
                  closed
                  fill={fill}
                  stroke={isSelected ? "#3b82f6" : stroke}
                  strokeWidth={(isSelected ? 3 : 1.5) / scale}
```

(Reszta `<Line>` — handlery `onClick`/`onMouseEnter`/`onMouseLeave`, `data-center-*`, etykieta netto — bez zmian. `center` liczony z `ring` teraz z netto: środek netto ≈ środek surowego, etykieta netto zostaje na miejscu. Przebieg etykiet :1189 zostaje na `apt.geometry` surowym — nie dotykać.)

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0. (Jeśli `tsc` zgłosi „`colors` is not defined" gdziekolwiek — znaczy, że jakieś inne odwołanie do starego `colors` zostało; grep `colors\.` w bloku :1116-1186 i zamień.)

```bash
git add frontend/app/CanvasEditor.tsx
git commit -m "feat: apartment fill=per-type color, stroke=status, geometry=net (stops at wall)"
```

---

### Task 5: Weryfikacja ręczna

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1-4
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints).

- [ ] **Step 2: Scenariusz (spec §5)**

1. Narysuj obrys → „Umieść korytarz i klatkę" → „Podziel na mieszkania".
   Mieszkania wypełnione kolorami wg typu (M1 sky, M2 emerald, …), NIE
   jednym kolorem statusu.
2. Panel „Struktura mieszkań": przy każdym wierszu okrągły swatch w kolorze
   typu. Klik → natywny próbnik → zmień kolor M2 → wszystkie M2 na płótnie
   zmieniają wypełnienie natychmiast.
3. Obramowanie mieszkania nadal wg statusu (zielony/żółty/czerwony) —
   niezależnie od wypełnienia. Zaznaczone mieszkanie: obramowanie niebieskie.
4. §B: wypełnienie KOŃCZY się na wewnętrznym licu ściany — między dwoma
   mieszkaniami widać szary pas ściany (0.20m), przy elewacji pełny pas
   (0.40m). Kolor NIE wchodzi na ścianę (porównaj ze zrzutem usera sprzed
   zmiany).
5. Przeładuj stronę (F5) — wybrane kolory typów przeżywają (localStorage).
6. Klik w inną iterację na liście „Iteracje" → mieszkania nadal netto (nie
   „wylane"), kolory per typ zachowane (potwierdza dual-surface Task 1).
7. Regresja: etykiety `typ`+`m²`, etykieta netto na zaznaczonym mieszkaniu,
   przełącz na zakładkę Słońce (fill słoneczny nadal działa, geometria
   netto), eksport DXF/PDF — bez błędów.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
