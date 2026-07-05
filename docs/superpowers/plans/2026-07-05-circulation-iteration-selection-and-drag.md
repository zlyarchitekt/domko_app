# Etap 5: Wybór iteracji z listy, niezależne przesuwanie klatek, Generuj układ na aktualnej geometrii — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Listy iteracji (klatki + mieszkania) niosą pełną geometrię dla każdej iteracji, nie tylko najlepszej; klik w wiersz ładuje tę iterację jako aktywny wynik; każda klatka przesuwalna osobno (nie jako jedna bryła z korytarzem); „Generuj układ" używa dokładnie aktualnie wyświetlanej geometrii komunikacji zamiast liczyć ją od zera, gdy taka już istnieje.

**Architecture:** Backend już liczy pełny wynik każdej iteracji wewnątrz `iterate_cage_placement`/`iterate_units` — rozszerzamy `CageIterationMeta`/`IterationMeta` o pole z pełnym wynikiem tej iteracji i serializujemy je do API (dual-surface: `/circulation`+`/generate` dla klatek, `/units`+`/generate` dla mieszkań). Nowy endpoint `POST /layout/circulation/move-cage` przelicza korytarz po przesunięciu jednej klatki, reużywając `_assemble_with_cages` (kontrakt z Etapu 2b). Frontend: klik w wiersz listy zamienia aktywny wynik (nie osobny "tryb podglądu"); `CanvasEditor.tsx`'s jeden `<Group draggable>` (korytarz+wszystkie klatki) dzieli się na osobny Group na korytarz i osobny per klatka; `regenerate()` deleguje do już istniejącego `runSubdivideUnits()` zamiast wołać `/layout/generate` od zera, gdy komunikacja już istnieje.

**Tech Stack:** shapely (backend), Next.js/react-konva (frontend).

**Spec:** `docs/superpowers/specs/2026-07-05-circulation-iteration-selection-and-drag-design.md`
**Wymaga:** Etap 2b (iteracyjne klatki), Etap 4 (iteracyjny podział na mieszkania), Etap 2 (manualne elementy) — wszystkie wdrożone.

## Global Constraints

- Backend venv: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v` — pełny przebieg musi PASS po każdym tasku backendowym.
- Frontend: brak testów automatycznych, `cd frontend && npx tsc --noEmit` musi zwrócić exit 0 po każdym tasku frontendowym.
- Dev: backend `cd backend && .venv/Scripts/python.exe -m uvicorn main:app --reload`; frontend `cd frontend && npm run dev -- -p 3001`.
- Git hygiene: `git add` TYLKO konkretne zmienione pliki po nazwie. NIGDY `git add -A`/`git add .` (wcześniej w tej sesji taki add wciągnął przypadkowe pliki scratch z innej sesji).
- Determinizm z Etapu 2b/4 (`random.Random(seed)` per iteracja) — żadna zmiana w tym planie nie dotyka pętli losującej, tylko dodaje serializację już policzonych wyników. Nie zmieniać scoringu ani kolejności iteracji.
- Dual-surface: każde pole dodane do jednej odpowiedzi (`/circulation` lub `/units`) musi się pojawić też na `/generate` — wzorzec już ustalony (`evacuation_dots`, `cage_iterations`).

---

### Task 1: Backend — pełna geometria każdej iteracji klatek

**Files:**
- Modify: `backend/services/cage_placement.py` (`CageIterationMeta` :38-43, `iterate_cage_placement` :145-200)
- Modify: `backend/api/v1/endpoints/layout.py` (`CageIterationMetaResult` :63-67, `layout_result_to_response` :323-327, `place_circulation_endpoint` :501-505)
- Test: `backend/tests/test_cage_placement.py`

**Interfaces:**
- Consumes: `CirculationResult`, `_assemble_with_cages`, `_serialize_dots`, `_serialize_centerline` (istniejące)
- Produces: `CageIterationMeta.result: CirculationResult` (konsumowane w Task 3/4 frontend); `CageIterationMetaResult` z polami geometrii (konsumowane w Task 4)

- [ ] **Step 1: Napisz failing test**

Dopisz do `backend/tests/test_cage_placement.py`:

```python
def test_iterate_cage_placement_metas_carry_full_result():
    footprint = _rect(0, 0, 40, 12)
    _, metas, best_seed = iterate_cage_placement(
        footprint, 1.5, num_cages=2, weights=CageWeights(), iterations=5
    )
    for m in metas:
        assert m.result is not None
        assert isinstance(m.result.cage_polygons, list)
        # liczba klatek w wyniku zgadza się z policzoną wcześniej cages_count
        assert len(m.result.cage_polygons) == m.cages_count
    best = next(m for m in metas if m.seed == best_seed)
    assert len(best.result.centerline) >= 1
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -k full_result -v`
Expected: `TypeError: CageIterationMeta.__init__() got an unexpected keyword argument` (bo test importu jeszcze nie sprawdza, po prostu AttributeError na `m.result` — sprawdź faktyczny błąd i potwierdź że to brak pola, nie coś innego).

- [ ] **Step 2: Dodaj pole `result` do `CageIterationMeta`**

W `backend/services/cage_placement.py`, dataclass `CageIterationMeta` (linia ~38):

```python
@dataclass
class CageIterationMeta:
    seed: int
    score: float
    cages_count: int
    components: dict = field(default_factory=dict)
    result: "CirculationResult | None" = None
    """Pełny wynik TEJ iteracji (klatki, korytarz, centerline, kropki) —
    spec 2026-07-05-circulation-iteration-selection-and-drag §1. None
    tylko jeśli ktoś konstruuje CageIterationMeta ręcznie bez wyniku
    (nie zdarza się w iterate_cage_placement)."""
```

Potrzebny import typu na górze pliku (jeśli `CirculationResult` nie jest już zaimportowany do adnotacji — sprawdź istniejące importy z `services.circulation`, dodaj `CirculationResult` do istniejącego `from services.circulation import (...)` blocku zamiast nowego importu).

- [ ] **Step 3: Zapisz `result` w pętli iteracji**

W `iterate_cage_placement` (linia ~192), zmień:

```python
        metas.append(CageIterationMeta(seed=seed, score=score,
                                       cages_count=len(result.cage_polygons),
                                       components=components))
```

na:

```python
        metas.append(CageIterationMeta(seed=seed, score=score,
                                       cages_count=len(result.cage_polygons),
                                       components=components, result=result))
```

- [ ] **Step 4: Uruchom test — powinien przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: wszystkie PASS.

- [ ] **Step 5: Rozszerz `CageIterationMetaResult` (API) o geometrię**

W `backend/api/v1/endpoints/layout.py`, `CageIterationMetaResult` (linia ~63):

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
```

(`CenterlineSegmentResult`/`EvacuationDotResult` są zdefiniowane niżej w
tym samym pliku, linie 387/127 — string forward-ref w adnotacji Pydantic
2 rozwiązuje się leniwie przy pierwszym użyciu modelu, przeciwko pełnej
przestrzeni nazw modułu po zaimportowaniu, więc kolejność definicji w
pliku nie ma znaczenia; ten sam wzorzec string forward-ref już istnieje
w tym pliku w `_serialize_centerline`/`_serialize_dots`'s adnotacjach
zwracanego typu, linie 373/396).

- [ ] **Step 6: Napisz helper serializujący jedną iterację + użyj go w obu miejscach**

W `backend/api/v1/endpoints/layout.py`, obok `_serialize_dots`/`_serialize_centerline` (koło linii 396), dodaj:

```python
def _serialize_cage_iteration(m) -> "CageIterationMetaResult":
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
    )
```

W `layout_result_to_response` (linia ~323) zamień:

```python
        cage_iterations=[
            CageIterationMetaResult(seed=m.seed, score=m.score,
                                     cages_count=m.cages_count, components=m.components)
            for m in layout.cage_iteration_metas
        ],
```

na:

```python
        cage_iterations=[_serialize_cage_iteration(m) for m in layout.cage_iteration_metas],
```

W `place_circulation_endpoint` (linia ~501) analogicznie zamień pętlę na
`cage_iterations=[_serialize_cage_iteration(m) for m in cage_iteration_metas],`.

- [ ] **Step 7: Test endpointu — geometria per iteracja w odpowiedzi**

Dopisz do `backend/tests/test_cage_placement.py`:

```python
def test_circulation_endpoint_iterations_carry_geometry():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "footprint": [[0, 0], [40, 0], [40, 12], [0, 12]],
        "circulation": {
            "corridor_width_m": 1.5, "stair_width_m": 1.2, "place_cage": True,
            "cage_size_m": 2.5, "cage_position": "auto", "num_cages": 2,
            "cage_iterations": 5,
            "cage_weights": {"egress": 1.0, "count": 0.5, "corners": 0.3,
                             "ends": 0.3, "spread": 0.5},
        },
        "apartments": [],
    }
    res = client.post("/api/v1/layout/circulation", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_iterations"]) >= 1
    for it in body["cage_iterations"]:
        assert "cage_geometries" in it
        assert isinstance(it["cage_geometries"], list)
        assert len(it["cage_geometries"]) == it["cages_count"]
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: wszystkie PASS.

- [ ] **Step 8: Pełny przebieg + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS.

```bash
git add backend/services/cage_placement.py backend/api/v1/endpoints/layout.py backend/tests/test_cage_placement.py
git commit -m "feat: cage iteration metadata carries full per-iteration geometry"
```

---

### Task 2: Backend — pełna geometria + wall_bands każdej iteracji mieszkań

**Files:**
- Modify: `backend/services/unit_mix.py` (`IterationMeta` :194-199, `iterate_units` :349-395)
- Modify: `backend/api/v1/endpoints/layout.py` (`IterationMetaResult` :48-52, `layout_result_to_response`, `subdivide_units_endpoint`)
- Test: `backend/tests/test_unit_iterations.py`

**Interfaces:**
- Consumes: `ApartmentCell`, `exterior_wall_band`, `interior_wall_bands`, `net_polygon` (istniejące)
- Produces: `IterationMeta.cells: list[ApartmentCell]`; `IterationMetaResult` z `apartments`+`wall_bands`; `_compute_wall_bands(footprint, cells, circulation_geometry, leftover) -> list[dict]` helper (reużywalny, konsumowany też przez istniejące miejsca w tym samym tasku)

- [ ] **Step 1: Napisz failing test**

Dopisz do `backend/tests/test_unit_iterations.py`:

```python
def test_iterate_units_metas_carry_full_cells():
    remainder = _rect(0, 0, 24, 10)
    _, metas, best_seed, _ = iterate_units(remainder, SHARES, iterations=5)
    for m in metas:
        assert m.cells is not None
        assert len(m.cells) == m.units_count
        total_area = sum(c.polygon.area for c in m.cells)
        assert abs(total_area - remainder.area) < 1e-6  # zero-leftover per iteracja
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -k full_cells -v`
Expected: FAIL (AttributeError: 'IterationMeta' object has no attribute 'cells').

- [ ] **Step 2: Dodaj pole `cells` do `IterationMeta`**

W `backend/services/unit_mix.py`, dataclass `IterationMeta` (linia ~194):

```python
@dataclass
class IterationMeta:
    seed: int
    score: float
    units_count: int
    components: dict = field(default_factory=dict)
    """dev per waga: {"size": ..., "mix": ..., ...} -- 0 = idealnie."""
    cells: list = field(default_factory=list)
    """list[ApartmentCell] -- pełne komórki TEJ iteracji (nie tylko
    najlepszej), spec 2026-07-05-circulation-iteration-selection-and-drag
    §1. Typ `list` bez parametru celowo -- ApartmentCell żyje w
    services.layout, import tu utworzyłby cykl (layout.py importuje z
    unit_mix.py)."""
```

- [ ] **Step 3: Zapisz `cells` w pętli iteracji**

W `iterate_units` (linia ~391), zmień:

```python
        metas.append(IterationMeta(seed=seed, score=score, units_count=len(cells), components=components))
```

na:

```python
        metas.append(IterationMeta(seed=seed, score=score, units_count=len(cells),
                                   components=components, cells=list(cells)))
```

(`list(cells)` — kopia listy, bo `cells` jest dalej mutowany/nadpisywany
w kolejnych obiegach pętli poprzez ponowne przypisanie zmiennej, ale
żeby uniknąć jakiejkolwiek dwuznaczności co do aliasingu referencji do
tych samych obiektów `ApartmentCell` między iteracjami — sama lista
`cells` jest tworzona od nowa co iterację przez `fit_program_to_rectangles`,
więc `list(cells)` to płytka kopia wskaźnika na już-unikalne obiekty tej
iteracji, wystarczające).

- [ ] **Step 4: Uruchom test — powinien przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`
Expected: wszystkie PASS.

- [ ] **Step 5: Wydziel `_compute_wall_bands` helper w `layout.py` (endpoints)**

W `backend/api/v1/endpoints/layout.py`, kod liczący `wall_bands_out` istnieje dziś w DWÓCH miejscach niemal identycznie: `layout_result_to_response` (linie ~268-298) i `subdivide_units_endpoint` (linie ~625-652). Wydziel wspólną funkcję obok `_decompose_to_polygons` (koło linii 348):

```python
def _compute_wall_bands(
    footprint: Polygon, wall_cells: list[Polygon], leftover: Polygon | None
) -> list[dict]:
    """Pasy ścian (zewn.+wewn.) dla danego zestawu komórek -- wspólne dla
    /layout/generate, /layout/units (wynik główny) i /layout/units
    (wynik każdej iteracji, Task 2). `wall_cells` to apartments+circulation_
    geometry (jeśli istnieje), BEZ leftover (patrz interior_wall_bands
    docstring)."""
    wall_geoms = [exterior_wall_band(footprint)]
    if wall_cells:
        interior_bands = interior_wall_bands(footprint, wall_cells)
        if leftover is not None and not leftover.is_empty:
            interior_bands = interior_bands.difference(leftover)
        wall_geoms.append(interior_bands)
    return [g for geom in wall_geoms for g in _decompose_to_polygons(geom)]
```

Zamień ciało `layout_result_to_response`'s wall_bands blok (linie ~268-298) na:

```python
    wall_cells = [a.polygon for a in layout.apartments]
    if layout.circulation_geometry is not None:
        wall_cells.append(layout.circulation_geometry)
    wall_bands_out = _compute_wall_bands(layout.footprint, wall_cells, layout.leftover)
```

Zamień ciało `subdivide_units_endpoint`'s wall_bands blok (linie ~625-652) na:

```python
    wall_bands_out: list[dict] = []
    if footprint is not None:
        wall_cells = [c.polygon for c in cells]
        if circulation_geometry is not None:
            wall_cells.append(circulation_geometry)
        wall_bands_out = _compute_wall_bands(footprint, wall_cells, leftover)
```

Usuń zbędne komentarze/duplikację które opisywały TO SAMO w obu miejscach
(zostaw JEDEN, w `_compute_wall_bands`'s docstring, resztę skróć albo
usuń — nie kopiuj wielo-akapitowych komentarzy do obu call site'ów).

- [ ] **Step 6: Rozszerz `IterationMetaResult` o `apartments`+`wall_bands`**

W `backend/api/v1/endpoints/layout.py`, `IterationMetaResult` (linia ~48):

```python
class IterationMetaResult(BaseModel):
    seed: int
    score: float
    units_count: int
    components: dict[str, float] = {}
    apartments: list["ApartmentResult"] = []
    wall_bands: list[dict] = []
```

(`ApartmentResult` jest zdefiniowany niżej, linia 104 — string
forward-ref rozwiązuje się tak samo jak w Task 1 Step 5, kolejność
definicji bez znaczenia).

- [ ] **Step 7: Helper serializujący jedną iterację mieszkań**

Obok `_serialize_cage_iteration` (Task 1 Step 6), dodaj:

```python
def _serialize_unit_iteration(m, footprint: Polygon | None, circulation_geometry) -> "IterationMetaResult":
    apartments_out = [
        ApartmentResult(
            id=c.id, type=c.type, area_m2=c.polygon.area, net_area_m2=c.net_area_m2,
            geometry=json.loads(json.dumps(c.polygon.__geo_interface__)),
        )
        for c in m.cells
    ]
    wall_bands_out: list[dict] = []
    if footprint is not None:
        wall_cells = [c.polygon for c in m.cells]
        if circulation_geometry is not None:
            wall_cells.append(circulation_geometry)
        # iterate_units gwarantuje zero resztek (spec Etap 4 §3) -- leftover
        # zawsze None dla każdej iteracji tego silnika, nie tylko najlepszej.
        wall_bands_out = _compute_wall_bands(footprint, wall_cells, None)
    return IterationMetaResult(
        seed=m.seed, score=m.score, units_count=m.units_count, components=m.components,
        apartments=apartments_out, wall_bands=wall_bands_out,
    )
```

W `subdivide_units_endpoint`, bezpośrednio przed `return UnitsResponse(...)`
(koło linii 659, zaraz po bloku liczącym `net_remainder_m2`), dodaj:

```python
    iterations_out = (
        [_serialize_unit_iteration(m, footprint, circulation_geometry) for m in iteration_metas]
        if shares else []
    )
```

W `return UnitsResponse(...)` (linie 659-669), zamień:

```python
        iterations=[
            IterationMetaResult(seed=m.seed, score=m.score, units_count=m.units_count, components=m.components)
            for m in iteration_metas
        ],
```

na:

```python
        iterations=iterations_out,
```

W `layout_result_to_response`, analogicznie zamień:

```python
        iterations=[
            IterationMetaResult(seed=m.seed, score=m.score, units_count=m.units_count, components=m.components)
            for m in layout.iteration_metas
        ],
```

na:

```python
        iterations=[
            _serialize_unit_iteration(m, layout.footprint, layout.circulation_geometry)
            for m in layout.iteration_metas
        ],
```

(`layout.footprint`/`layout.circulation_geometry` — sprawdź dokładne
nazwy pól na `LayoutResult`, powinny już istnieć skoro
`layout_result_to_response` ich gdzie indziej używa w tej samej funkcji).

- [ ] **Step 8: Test endpointu**

Dopisz do `backend/tests/test_unit_iterations.py`:

```python
def test_units_endpoint_iterations_carry_geometry_and_walls():
    from fastapi.testclient import TestClient
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
    assert len(body["iterations"]) == 5
    for it in body["iterations"]:
        assert len(it["apartments"]) == it["units_count"]
        assert len(it["wall_bands"]) > 0
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py -v`
Expected: wszystkie PASS.

- [ ] **Step 9: Pełny przebieg + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS (upewnij się że wydzielenie `_compute_wall_bands`
nie zmieniło zachowania — istniejące testy `test_layout.py`/
`test_layout_units_endpoint.py` sprawdzające `wall_bands` muszą przejść
identycznie).

```bash
git add backend/services/unit_mix.py backend/api/v1/endpoints/layout.py backend/tests/test_unit_iterations.py
git commit -m "feat: unit iteration metadata carries full per-iteration geometry and wall_bands"
```

---

### Task 3: Backend — endpoint przesunięcia pojedynczej klatki

**Files:**
- Modify: `backend/services/cage_placement.py` (nowa funkcja `assign_cages_to_zones`)
- Modify: `backend/api/v1/endpoints/layout.py` (nowy endpoint)
- Test: `backend/tests/test_cage_placement.py`

**Interfaces:**
- Consumes: `_assemble_with_cages`, `Zone`, `rectangle_decompose` (istniejące)
- Produces: `assign_cages_to_zones(cages: list[Polygon], zones: list[Zone]) -> dict[int, list[Polygon]]`; `POST /layout/circulation/move-cage`

- [ ] **Step 1: Napisz failing test dla `assign_cages_to_zones`**

Dopisz do `backend/tests/test_cage_placement.py`:

```python
from services.cage_placement import assign_cages_to_zones


def test_assign_cages_to_zones_matches_containing_bbox():
    # Prostokąt 40x12: rectangle_decompose zwraca 1 strefę = cały footprint.
    footprint = _rect(0, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=footprint)]
    cage_a = box(2, 2, 6.2, 7.7)
    cage_b = box(30, 2, 34.2, 7.7)
    result = assign_cages_to_zones([cage_a, cage_b], zones)
    assert result == {0: [cage_a, cage_b]}


def test_assign_cages_to_zones_multi_zone():
    left = _rect(0, 0, 8, 12)
    right = _rect(8, 0, 40, 12)
    zones = [Zone(name="Z0", polygon=left), Zone(name="Z1", polygon=right)]
    cage_left = box(1, 2, 5.2, 7.7)
    cage_right = box(30, 2, 34.2, 7.7)
    result = assign_cages_to_zones([cage_left, cage_right], zones)
    assert result == {0: [cage_left], 1: [cage_right]}
```

(zaimportuj `Zone` z `services.circulation` i `box` z `shapely.geometry`
u góry pliku testowego, jeśli jeszcze nie są zaimportowane — sprawdź
istniejące importy przed dopisaniem).

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -k assign_cages -v`
Expected: `ImportError: cannot import name 'assign_cages_to_zones'`.

- [ ] **Step 2: Implementacja `assign_cages_to_zones`**

W `backend/services/cage_placement.py`, obok `_candidate_cages`, dodaj:

```python
def assign_cages_to_zones(cages: list[Polygon], zones: list[Zone]) -> dict[int, list[Polygon]]:
    """Przypisuje każdą klatkę do strefy, której bbox ją zawiera (spec
    2026-07-05-circulation-iteration-selection-and-drag §2 -- przesunięta
    klatka musi trafić do właściwej strefy przed przeliczeniem korytarza).
    Klatka niepasująca do żadnej strefy (np. przeciągnięta poza obrys)
    jest pomijana -- wywołujący (endpoint) waliduje osobno przez
    `footprint.contains`, więc to nie powinno się zdarzyć w praktyce."""
    result: dict[int, list[Polygon]] = {}
    for cage in cages:
        for zi, zone in enumerate(zones):
            if zone.polygon.buffer(1e-9).contains(cage):
                result.setdefault(zi, []).append(cage)
                break
    return result
```

- [ ] **Step 3: Uruchom testy — powinny przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: wszystkie PASS.

- [ ] **Step 4: Failing test endpointu `/circulation/move-cage`**

Dopisz do `backend/tests/test_cage_placement.py`:

```python
def test_move_cage_endpoint_recomputes_zone_corridor():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    footprint = [[0, 0], [40, 0], [40, 12], [0, 12]]
    cage = box(2, 2, 6.2, 7.7)
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(cage))],
        "corridor_width_m": 1.5,
        "max_dist_single_m": 20.0,
        "max_dist_multi_m": 40.0,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["cage_geometries"]) == 1
    assert body["circulation_geometry"] is not None
    assert len(body["centerline"]) >= 1


def test_move_cage_endpoint_rejects_cage_outside_footprint():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    footprint = [[0, 0], [40, 0], [40, 12], [0, 12]]
    cage = box(38, 10, 45, 16)  # wystaje poza obrys
    payload = {
        "footprint": footprint,
        "cage_geometries": [json.loads(_shape_to_json(cage))],
        "corridor_width_m": 1.5,
    }
    res = client.post("/api/v1/layout/circulation/move-cage", json=payload)
    assert res.status_code == 422
```

Dodaj helper na górze pliku testowego (jeśli nie istnieje już podobny —
sprawdź, `json`/`shapely.geometry.mapping` mogą być już zaimportowane):

```python
import json
from shapely.geometry import mapping


def _shape_to_json(geom) -> str:
    return json.dumps(mapping(geom))
```

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -k move_cage -v`
Expected: FAIL (404, endpoint nie istnieje).

- [ ] **Step 5: Implementacja endpointu**

W `backend/api/v1/endpoints/layout.py`, obok `ReshapeCirculationRequest`/
`reshape_circulation_endpoint` (koło linii 720), dodaj:

```python
class MoveCageRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    cage_geometries: list[dict] = Field(..., min_length=1)
    """Aktualne wielokąty WSZYSTKICH klatek, z tą przesuniętą już podmienioną
    na nową pozycję (frontend wysyła cały zestaw, nie tylko jedną)."""
    corridor_width_m: float = Field(default=1.5, gt=0)
    max_dist_single_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M, gt=0)
    max_dist_multi_m: float = Field(default=CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M, gt=0)


@router.post("/circulation/move-cage", response_model=CirculationResponse)
def move_cage_endpoint(request: MoveCageRequest):
    """Przelicza korytarz po przesunięciu jednej lub więcej klatek (spec
    2026-07-05-circulation-iteration-selection-and-drag §2). Różni się od
    /circulation/reshape (który kształtuje oś bez stref) -- tu klatki
    wracają do zestawu stref (rectangle_decompose) i _assemble_with_cages
    przelicza korytarz per strefa, tak jak przy pierwszym umieszczeniu."""
    from services.cage_placement import assign_cages_to_zones
    from services.circulation import Zone, _assemble_with_cages
    from services.bsp import rectangle_decompose

    try:
        footprint = _points_to_polygon(request.footprint)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        cages = [_shape(g) for g in request.cage_geometries]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid cage geometry: {exc}")

    fp_buffered = footprint.buffer(1e-9)
    for cage in cages:
        if not fp_buffered.contains(cage):
            raise HTTPException(status_code=422, detail="Klatka poza obrysem")
    for i, a in enumerate(cages):
        for b in cages[i + 1:]:
            if a.intersects(b):
                raise HTTPException(status_code=422, detail="Klatki kolidują ze sobą")

    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    local_cages = assign_cages_to_zones(cages, zones)

    result = _assemble_with_cages(
        footprint, zones, local_cages, request.corridor_width_m,
        request.max_dist_single_m, request.max_dist_multi_m,
    )

    return CirculationResponse(
        circulation_geometry=(
            json.loads(json.dumps(result.circulation_geometry.__geo_interface__))
            if result.circulation_geometry is not None else None
        ),
        cage_geometries=[json.loads(json.dumps(c.__geo_interface__)) for c in result.cage_polygons],
        remainder=json.loads(json.dumps(result.remainder.__geo_interface__)),
        centerline=_serialize_centerline(result.centerline),
        evacuation_dots=_serialize_dots(result.evacuation_dots),
    )
```

- [ ] **Step 6: Uruchom testy — powinny przejść**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -v`
Expected: wszystkie PASS.

- [ ] **Step 7: Pełny przebieg + commit**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v`
Expected: wszystkie PASS.

```bash
git add backend/services/cage_placement.py backend/api/v1/endpoints/layout.py backend/tests/test_cage_placement.py
git commit -m "feat: /layout/circulation/move-cage recomputes zone corridor after moving one cage"
```

---

### Task 4: Frontend — wybór iteracji z listy (klatki + mieszkania) + etykieta

**Files:**
- Modify: `frontend/app/lib/api.ts` (`CageIterationMeta` :153-158, `IterationMeta` :138-143, `CirculationResponse`, `UnitsResponse`, `LayoutGenerateResponse`)
- Modify: `frontend/app/state/SessionContext.tsx`
- Modify: `frontend/app/components/CirculationSection.tsx`
- Modify: `frontend/app/components/ProgramSection.tsx`

**Interfaces:**
- Consumes: pola geometrii z Task 1/2 (`cage_geometries`/`circulation_geometry`/`centerline`/`evacuation_dots` per `CageIterationMeta`; `apartments`/`wall_bands` per `IterationMeta`)
- Produces: klik w wiersz listy ustawia aktywny wynik (`state.circulationResult` / `state.layoutResult`)

- [ ] **Step 1: Rozszerz typy w `api.ts`**

```ts
export interface CageIterationMeta {
  seed: number;
  score: number;
  cages_count: number;
  components?: Record<string, number>;
  cage_geometries?: GeoJsonPolygon[];
  circulation_geometry?: GeoJsonPolygon | null;
  centerline?: CorridorCenterlineSegment[];
  evacuation_dots?: EvacuationDot[];
}
```

```ts
export interface IterationMeta {
  seed: number;
  score: number;
  units_count: number;
  components?: Record<string, number>;
  apartments?: ApartmentResult[];
  wall_bands?: GeoJsonPolygon[];
}
```

(Reszta interfejsów — `CirculationResponse`, `UnitsResponse`,
`LayoutGenerateResponse` — już referencuje `CageIterationMeta[]`/
`IterationMeta[]`, więc automatycznie dziedziczą nowe opcjonalne pola,
bez zmian w tych interfejsach).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 3: SessionContext — akcje wyboru iteracji**

Dodaj do stanu (`initialState`, koło innych `null`-default pól):

```ts
  activeCageSeed: null as number | null,
  activeUnitSeed: null as number | null,
```

Dodaj do typu akcji (`SessionAction` union, koło `SET_CIRCULATION_RESULT`):

```ts
  | { type: "SELECT_CAGE_ITERATION"; seed: number }
  | { type: "SELECT_UNIT_ITERATION"; seed: number }
```

Reducer (koło `case "SET_CIRCULATION_RESULT":`):

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
        },
        // wybór innej iteracji unieważnia ewentualny wcześniejszy podział na
        // mieszkania (ten sam wzorzec co ADD_MANUAL_CAGE/REMOVE_MANUAL_ELEMENT)
        layoutResult: null,
        validation: null,
      };
    }
    case "SELECT_UNIT_ITERATION": {
      // state.lastIterations (nie state.layoutResult.iterations) -- to jest
      // dokładnie ta tablica którą renderuje ProgramSection.tsx, więc klik w
      // wiersz zawsze trafia w meta z tej samej listy co user widzi.
      if (!state.layoutResult) return state;
      const meta = state.lastIterations.find((m) => m.seed === action.seed);
      if (!meta || !meta.apartments) return state;
      return {
        ...state,
        activeUnitSeed: action.seed,
        layoutResult: {
          ...state.layoutResult,
          apartments: meta.apartments,
          wall_bands: meta.wall_bands ?? state.layoutResult.wall_bands,
          leftover: null,
        },
      };
    }
```

Zresetuj `activeCageSeed`/`activeUnitSeed` do `null` przy każdym nowym
uruchomieniu iteracji. W reducerze zamień:

```ts
    case "SET_CIRCULATION_RESULT":
      return { ...state, circulationResult: action.result };
```

na:

```ts
    case "SET_CIRCULATION_RESULT":
      return { ...state, circulationResult: action.result, activeCageSeed: null };
```

i zamień:

```ts
    case "SET_LAYOUT_RESULT":
      return { ...state, layoutResult: action.result, solarResult: null };
```

na:

```ts
    case "SET_LAYOUT_RESULT":
      return { ...state, layoutResult: action.result, solarResult: null, activeUnitSeed: null };
```

(zachowaj istniejący komentarz nad `SET_LAYOUT_RESULT` bez zmian — dotyczy
`solarResult`, nadal aktualny).

Dodaj `selectCageIteration`/`selectUnitIteration` callbacki (wzorzec
`setHoveredManualId`, prosty jednolinijkowy dispatch):

```ts
  const selectCageIteration = useCallback((seed: number) => {
    dispatch({ type: "SELECT_CAGE_ITERATION", seed });
  }, []);
  const selectUnitIteration = useCallback((seed: number) => {
    dispatch({ type: "SELECT_UNIT_ITERATION", seed });
  }, []);
```

Dodaj oba do `SessionContextValue` interfejsu i do zwracanego `value`
obiektu (ten sam wzorzec co `setHoveredManualId` — znajdź jego 3 miejsca
wystąpienia w pliku: interfejs, `useCallback`, `value`, i powiel dla
nowych dwóch callbacków). Dodaj też `activeCageSeed`/`activeUnitSeed` do
`SessionContextValue`/`value` (proste odczyty stanu, bez callbacku).

- [ ] **Step 4: CirculationSection — klikalna lista + etykieta**

W `frontend/app/components/CirculationSection.tsx`, destrukturyzacji
kontekstu dodaj `selectCageIteration`, `activeCageSeed`. Zamień blok listy
iteracji (linie ~277-297):

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

- [ ] **Step 5: ProgramSection — klikalna lista + etykieta**

Analogicznie w `frontend/app/components/ProgramSection.tsx`, destrukturyzacji
dodaj `selectUnitIteration`, `activeUnitSeed`. Zamień blok (linie ~188-209):

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

- [ ] **Step 6: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx frontend/app/components/ProgramSection.tsx
git commit -m "feat: click an iteration row to load it as the active result"
```

---

### Task 5: Frontend — niezależne przesuwanie klatek

**Files:**
- Modify: `frontend/app/lib/api.ts` (nowa funkcja `moveCage`)
- Modify: `frontend/app/state/SessionContext.tsx` (nowy callback `runMoveCage`)
- Modify: `frontend/app/CanvasEditor.tsx` (`edit-circulation` blok :1055-1099)

**Interfaces:**
- Consumes: `POST /layout/circulation/move-cage` (Task 3)
- Produces: `runMoveCage(cageIndex: number, dx: number, dy: number): Promise<boolean>`

- [ ] **Step 1: `api.ts` — funkcja `moveCage`**

```ts
export interface MoveCageRequest {
  footprint: Point[];
  cage_geometries: GeoJsonPolygon[];
  corridor_width_m: number;
  max_dist_single_m: number;
  max_dist_multi_m: number;
}

export function moveCage(req: MoveCageRequest): Promise<CirculationResponse> {
  return postJson("/layout/circulation/move-cage", req);
}
```

- [ ] **Step 2: SessionContext — `runMoveCage`**

Dodaj obok `runPlaceCirculation` (ten sam plik):

```ts
  const runMoveCage = useCallback(
    async (cageIndex: number, dxM: number, dyM: number): Promise<boolean> => {
      if (!state.footprint || !state.circulationResult) return false;
      const cages = state.circulationResult.cage_geometries.map((g, i) => {
        if (i !== cageIndex) return g;
        // przesunięcie wielokąta o (dxM, dyM) w metrach -- ring GeoJSON
        const coords = g.coordinates[0].map(([x, y]) => [x + dxM, y + dyM] as [number, number]);
        return { type: "Polygon" as const, coordinates: [coords] };
      });
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const result = await api.moveCage({
          footprint: footprintToPoints(state.footprint),
          cage_geometries: cages,
          corridor_width_m: state.circulation.corridor_width_m,
          max_dist_single_m: state.circulation.max_dist_single_m,
          max_dist_multi_m: state.circulation.max_dist_multi_m,
        });
        dispatch({ type: "SET_CIRCULATION_RESULT", result });
        dispatch({ type: "SET_ERROR", error: null });
        return true;
      } catch (err) {
        dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
        return false;
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [state.footprint, state.circulationResult, state.circulation.corridor_width_m,
     state.circulation.max_dist_single_m, state.circulation.max_dist_multi_m]
  );
```

Dodaj `runMoveCage` do `SessionContextValue` interfejsu i do `value`
zwracanego obiektu (ten sam wzorzec co `runPlaceCirculation`).

`SET_CIRCULATION_RESULT`'s reducer case dostał w Task 4 Step 3
`activeCageSeed: null`, ale nie czyści `layoutResult`/`validation` —
przesunięta klatka (ten task) powinna tak samo unieważniać wcześniejszy
podział na mieszkania jak wybór innej iteracji. Zamień (stan PO Task 4
Step 3):

```ts
    case "SET_CIRCULATION_RESULT":
      return { ...state, circulationResult: action.result, activeCageSeed: null };
```

na:

```ts
    case "SET_CIRCULATION_RESULT":
      return { ...state, circulationResult: action.result, activeCageSeed: null,
               layoutResult: null, validation: null };
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 4: CanvasEditor — rozdziel Group na korytarz i każdą klatkę osobno**

W `frontend/app/CanvasEditor.tsx`, zamień blok `edit-circulation` (linie
~1055-1099):

```tsx
          {/* Przesuwanie CAŁEJ komunikacji jako sztywnej bryły (edit-circulation) */}
          {state.mode === "edit-circulation" && state.circulationResult && (
            <Group
              draggable
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragEnd={(e) => {
                e.cancelBubble = true;
                const node = e.target;
                const dxM = node.x() / METER_PX;
                const dyM = -node.y() / METER_PX;
                node.position({ x: 0, y: 0 });
                dispatch({ type: "TRANSLATE_CIRCULATION", dx: dxM, dy: dyM });
              }}
            >
              {circulationParts.map((geom, i) => (
                <Line
                  key={`edit-corridor-${i}`}
                  points={toCanvasPoints(ringToPoints(geom))}
                  closed
                  fill="rgba(211,211,211,0.5)"
                  stroke="#60a5fa"
                  strokeWidth={2 / scale}
                />
              ))}
            </Group>
          )}
          {/* Przesuwanie KAŻDEJ klatki osobno (spec 2026-07-05 §2) */}
          {state.mode === "edit-circulation" && state.circulationResult && cageGeometries.map((geom, i) => (
            <Group
              key={`edit-cage-group-${i}`}
              draggable
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragEnd={(e) => {
                e.cancelBubble = true;
                const node = e.target;
                const dxM = node.x() / METER_PX;
                const dyM = -node.y() / METER_PX;
                node.position({ x: 0, y: 0 });
                void runMoveCage(i, dxM, dyM);
              }}
            >
              <Line
                points={toCanvasPoints(ringToPoints(geom))}
                closed
                fill="rgba(128,128,128,0.7)"
                stroke="#60a5fa"
                strokeWidth={2 / scale}
              />
              {cageSubdivisionShapes(geom, `edit-cage-sub-${i}`, scale, canvasColors.axis, canvasColors.axisText)}
            </Group>
          ))}
```

`runMoveCage` musi być dostępny w scope tego komponentu. W
`CanvasEditor.tsx:330`, zamień:

```ts
  const { state, addDrawPoint, removeLastDrawPoint, finishDrawing, updateVertex, setFootprintPoints, selectApartment, updateApartmentsAndValidate, runReshapeCirculation, addManualCage, addManualCorridor, runPlaceCirculation, dispatch } = useSession();
```

na (dopisz `runMoveCage` na końcu listy, przed `dispatch`):

```ts
  const { state, addDrawPoint, removeLastDrawPoint, finishDrawing, updateVertex, setFootprintPoints, selectApartment, updateApartmentsAndValidate, runReshapeCirculation, addManualCage, addManualCorridor, runPlaceCirculation, runMoveCage, dispatch } = useSession();
```

- [ ] **Step 5: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/CanvasEditor.tsx
git commit -m "feat: drag individual cages independently, corridor recomputes per zone"
```

---

### Task 6: Frontend — Generuj układ na aktualnej geometrii

**Files:**
- Modify: `frontend/app/state/SessionContext.tsx` (`regenerate` :633-669)

**Interfaces:**
- Consumes: `runSubdivideUnits` (istniejący callback, Etap 4)
- Produces: `regenerate()` z nowym rozgałęzieniem

- [ ] **Step 1: Sprawdź kolejność definicji**

W bieżącym pliku `regenerate` jest zdefiniowany PRZED `runSubdivideUnits`
(linia ~633 vs ~763). Przenieś definicję `regenerate` (cały blok
`const regenerate = useCallback(...)`, linie ~633-669) tak, żeby
znalazła się PO definicji `runSubdivideUnits` (czyli za linią ~826) —
proste przecięcie i wklejenie bloku, bez zmiany jego wewnętrznej treści
na tym kroku. To eliminuje ryzyko ESLint `no-use-before-define` przy
odwołaniu do `runSubdivideUnits` w kolejnym kroku.

- [ ] **Step 2: Typecheck po przeniesieniu (bez zmian logiki jeszcze)**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0 (samo przeniesienie bloku nie zmienia zachowania).

- [ ] **Step 3: Rozgałęzienie `regenerate`**

Zamień ciało `regenerate` na:

```ts
  const regenerate = useCallback(async () => {
    if (!state.footprint || state.footprint.length < 3) return;
    if (state.circulationResult) {
      // Komunikacja już istnieje na canvasie (auto/iteracyjnie/ręcznie/
      // przesunięta/zreshape'owana, wybrana z listy iteracji) -- użyj
      // JEJ dokładnie zamiast liczyć nową od zera (spec 2026-07-05
      // circulation-iteration-selection-and-drag §3). runSubdivideUnits
      // już robi dokładnie to: dzieli aktualny state.circulationResult
      // na mieszkania i liczy walidację -- to jest to samo co "Generuj
      // układ" powinno zwrócić, tyle że bez ponownego liczenia korytarza.
      await runSubdivideUnits();
      return;
    }
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const req: api.LayoutGenerateRequest = {
        ...buildRequest(state.footprint),
        circulation: {
          ...state.circulation,
          manual_cages: state.manualCages.map((c) => c.ring.map((p) => [p.x, p.y] as api.Point)),
          manual_corridors: state.manualCorridors.map((c) => c.path.map((p) => [p.x, p.y] as api.Point)),
        },
        iterations: 10,
        weights: state.unitWeights,
      };
      const [layout, validation] = await Promise.all([
        api.generateLayout(req),
        api.validateFullLayout(req),
      ]);
      dispatch({ type: "SET_LAYOUT_RESULT", result: layout });
      dispatch({ type: "SET_VALIDATION", validation });
      dispatch({
        type: "SET_ITERATION_RESULTS",
        iterations: layout.iterations ?? [],
        derivedTotalUnits: layout.derived_total_units ?? 0,
        netRemainderM2: layout.net_remainder_m2 ?? 0,
      });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.footprint, state.circulationResult, runSubdivideUnits, buildRequest,
      state.circulation, state.manualCages, state.manualCorridors, state.unitWeights]);
```

(dodano `state.circulationResult` i `runSubdivideUnits` do zależności —
brakujący `state.circulationResult` w oryginalnej liście zależności był
już nieścisłością sprzed tego tasku, teraz staje się faktycznie używany
w ciele funkcji więc MUSI być w tablicy zależności).

- [ ] **Step 4: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/state/SessionContext.tsx
git commit -m "fix: Generuj układ reuses existing circulation instead of recomputing it"
```

---

### Task 7: Weryfikacja ręczna

**Files:** brak (task weryfikacyjny)

**Interfaces:**
- Consumes: Taski 1-6
- Produces: raport dla usera

- [ ] **Step 1: Uruchom backend + frontend** (komendy z Global Constraints)

- [ ] **Step 2: Scenariusz**

1. „Rozmieść iteracyjnie" → klik w wiersz NIE-najlepszej iteracji → canvas
   pokazuje jej klatki/korytarz (inne niż najlepsza), gwiazdka nadal przy
   najlepszej, ramka podświetla klikniętą.
2. Etykieta „odchylenie, niżej = lepiej" widoczna nad obiema listami
   (klatki i mieszkania).
3. Analogicznie dla listy iteracji mieszkań po „Podziel na mieszkania" —
   klik w inną iterację zmienia widoczne mieszkania NA CANVASIE.
4. „Przesuń komunikację" → przeciągnij JEDNĄ klatkę → tylko ona się
   rusza, korytarz w jej strefie przelicza się automatycznie (inny kąt/
   pozycja osi), reszta klatek/korytarza bez zmian. Przeciągnięcie poza
   obrys → błąd, klatka wraca.
5. Umieść korytarz i klatkę → przesuń klatkę (punkt 4) → „Generuj układ"
   → wynikowe mieszkania/ściany bazują na PRZESUNIĘTEJ pozycji, nie na
   świeżo policzonej.
6. Świeży obrys, bez wcześniejszych kliknięć w sekcji Komunikacja, od
   razu „Generuj układ" → zachowanie identyczne jak przed tym planem
   (jeden strzał, auto-placement).
7. Regresja: PRZELICZ dojścia, eksport DXF/PDF, WT-walidacja — działają
   na aktualnie wyświetlanej (wybranej z listy lub przesuniętej)
   geometrii bez błędów.

- [ ] **Step 3: Poprawki znalezisk** (commit per poprawka, `fix: ...`), raport dla usera.
