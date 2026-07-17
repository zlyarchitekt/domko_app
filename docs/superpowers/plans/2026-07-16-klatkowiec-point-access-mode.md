# Klatkowiec (tryb punktowy) + auto-decyzja klatka-vs-korytarz — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Budynek w systemie klatkowym (sama klatka + hol, mieszkania wchodzą
bezpośrednio, zwykle 1-6 na poziom) działający RÓWNOLEGLE z systemem
korytarzowym; tryb `auto` porównuje oba warianty per strefa wspólną funkcją
kosztu i wybiera lepszy — bez sztywnych reguł.

**Architecture:** Nowy moduł `services/point_access.py` (trzon = klatka + hol,
kandydaci kotwic, podział "wiatraczkiem" wokół trzonu). `corridor_mode`
rozszerzony o `"point"` i `"auto"`. Auto = enumeracja kombinacji trybów per
strefa (≤3 stref po rectangle_decompose → ≤8 kombinacji), każda oceniona
szybkim przebiegiem silnika mieszkań; wygrywa najniższy composite (score
zwycięzcy + udział komunikacji). Wiedza domenowa: `docs/references/typologia-klatkowa.md`.

**Tech Stack:** FastAPI + Shapely 2 (backend), Next.js + Konva (frontend),
pytest. Zawsze `backend/.venv/Scripts/python.exe` (globalny python nie ma
zależności).

## Global Constraints

- Komunikacja klatkowca ma cel 9-13% powierzchni strefy (referencje §1) —
  wchodzi do composite, NIE jest hard-banem.
- Każde mieszkanie musi dotykać trzonu (cage+hol) I elewacji; proporcje ≤ 1:3
  (`HARD_MAX_ASPECT_RATIO = 3.0`) — egzekwuje istniejący
  `hard_constraint_violations`, nie duplikować.
- Klatka nie marnuje elewacji nie-północnej — reużyć `_light_waste_for_cage`.
- Bez sztywnego limitu mieszkań na klatkę (user 2026-07-16).
- Determinizm: wyłącznie `random.Random(seed)`; `base_seed` przesuwa wszystko.
- Testy: `./.venv/Scripts/python.exe -m pytest -q` z katalogu `backend/`;
  przed planem suita = 305 passed.
- Commity per task, wiadomości z planu, stopka
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

- Create: `backend/services/point_access.py` — trzon (cage+hol), kotwice,
  podział strefy wokół trzonu. Jedna odpowiedzialność: geometria klatkowca.
- Create: `backend/tests/test_point_access.py`
- Modify: `backend/services/circulation.py` — dispatch `corridor_mode="point"`
  w `place_circulation` (strefy punktowe nie dostają korytarza/spine).
- Modify: `backend/services/cage_placement.py` — iteracje punktowe
  (enumeracja kotwic zamiast SA) + auto-decyzja.
- Modify: `backend/services/unit_mix.py` + `backend/services/trakt_division.py`
  — routing komponentów: strefa punktowa → cięcie wokół trzonu.
- Modify: `backend/api/v1/endpoints/layout.py` — `corridor_mode` przyjmuje
  `point|auto`, response niesie `zone_access_modes`.
- Modify: `frontend/app/lib/api.ts`, `frontend/app/state/SessionContext.tsx`,
  `frontend/app/components/CirculationSection.tsx` — select + presety.

---

### Task 1: Trzon punktowy — geometria cage+hol i kandydaci kotwic

**Files:**
- Create: `backend/services/point_access.py`
- Test: `backend/tests/test_point_access.py`

**Interfaces:**
- Consumes: `services.circulation.CAGE_WIDTH_M` (=4.2), `CAGE_DEPTH_M` (=5.7),
  `services.cage_placement._light_waste_for_cage(cage, footprint) -> float`.
- Produces:
  - `HALL_DEPTH_M = 1.8` (stała modułu)
  - `build_point_core(zone: Polygon, anchor: str) -> tuple[Polygon, Polygon] | None`
    — `(cage, hall)`; `anchor` ∈ `{"north","south","east","west","center"}`;
    `None` gdy trzon nie mieści się w strefie.
  - `core_polygon(cage: Polygon, hall: Polygon) -> Polygon` — unia.
  - `anchor_candidates(zone: Polygon) -> list[str]` — kotwice mieszczące trzon,
    posortowane rosnąco po `_light_waste_for_cage` (center liczone jako 0.0).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_point_access.py
"""Testy trybu klatkowego (plan 2026-07-16, referencje
docs/references/typologia-klatkowa.md)."""

from shapely.geometry import Polygon

from services.point_access import (
    HALL_DEPTH_M,
    anchor_candidates,
    build_point_core,
    core_polygon,
)


def _rect(x0, y0, x1, y1):
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def test_build_point_core_north_flush_hall_inside():
    zone = _rect(0, 0, 23, 13.75)  # wzorzec 3 z referencji
    core = build_point_core(zone, "north")
    assert core is not None
    cage, hall = core
    # klatka dosunięta do północnej krawędzi, wyśrodkowana w x
    assert abs(cage.bounds[3] - 13.75) < 1e-6
    assert abs((cage.bounds[0] + cage.bounds[2]) / 2 - 11.5) < 1e-6
    # hol przylega od południa (wnętrza), głębokość HALL_DEPTH_M
    assert abs(hall.bounds[3] - cage.bounds[1]) < 1e-6
    assert abs((hall.bounds[3] - hall.bounds[1]) - HALL_DEPTH_M) < 1e-6
    # całość w strefie
    assert core_polygon(cage, hall).within(zone.buffer(1e-6))


def test_build_point_core_center_no_facade_contact():
    zone = _rect(0, 0, 17, 20)  # wzorzec 2: punktowiec, trzon bez okien
    core = build_point_core(zone, "center")
    assert core is not None
    cage, hall = core
    assert core_polygon(cage, hall).distance(zone.exterior) > 0.5


def test_build_point_core_none_when_zone_too_small():
    assert build_point_core(_rect(0, 0, 5, 5), "north") is None


def test_anchor_candidates_prefer_north_and_center():
    zone = _rect(0, 0, 23, 13.75)
    cands = anchor_candidates(zone)
    assert set(cands) <= {"north", "south", "east", "west", "center"}
    # north i center mają light_waste 0 -> przed south
    assert cands.index("north") < cands.index("south")
    assert cands.index("center") < cands.index("south")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_point_access.py -q`
Expected: FAIL / ERROR `ModuleNotFoundError: services.point_access`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/services/point_access.py
"""Tryb klatkowy (plan 2026-07-16): trzon = klatka schodowa + hol wejściowy,
mieszkania wchodzą bezpośrednio z holu -- zero korytarza. Wiedza domenowa:
docs/references/typologia-klatkowa.md (komunikacja 9-13%, trzon centralnie
bez okien albo przy północnej elewacji, każde mieszkanie dotyka trzonu)."""

from __future__ import annotations

from shapely.geometry import Polygon

from services.circulation import CAGE_DEPTH_M, CAGE_WIDTH_M

HALL_DEPTH_M = 1.8
"""Głębokość holu wejściowego doklejonego do klatki od strony wnętrza
(referencje: hol 15-25 m2; 1.8 m x szerokość klatki 4.2 = 7.6 m2 + podest)."""

_ANCHORS = ("north", "center", "south", "east", "west")


def build_point_core(zone: Polygon, anchor: str) -> tuple[Polygon, Polygon] | None:
    """(klatka, hol) dla kotwicy w strefie-prostokącie; None gdy nie mieści.

    north/south: klatka flush do krawędzi, wyśrodkowana w x, hol od wnętrza.
    east/west: analogicznie na osi x (klatka obrócona: szerokość wzdłuż y).
    center: klatka w środku strefy, hol od południa."""
    minx, miny, maxx, maxy = zone.bounds
    w, h = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    def rect(x0, y0, x1, y1):
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    if anchor in ("north", "south", "center"):
        need_w, need_h = CAGE_WIDTH_M, CAGE_DEPTH_M + HALL_DEPTH_M
        if need_w > w + 1e-9 or need_h > h + 1e-9:
            return None
        x0 = cx - CAGE_WIDTH_M / 2.0
        if anchor == "north":
            cage = rect(x0, maxy - CAGE_DEPTH_M, x0 + CAGE_WIDTH_M, maxy)
            hall = rect(x0, cage.bounds[1] - HALL_DEPTH_M, x0 + CAGE_WIDTH_M, cage.bounds[1])
        elif anchor == "south":
            cage = rect(x0, miny, x0 + CAGE_WIDTH_M, miny + CAGE_DEPTH_M)
            hall = rect(x0, cage.bounds[3], x0 + CAGE_WIDTH_M, cage.bounds[3] + HALL_DEPTH_M)
        else:  # center
            y0 = cy - (CAGE_DEPTH_M - HALL_DEPTH_M) / 2.0
            cage = rect(x0, y0, x0 + CAGE_WIDTH_M, y0 + CAGE_DEPTH_M)
            hall = rect(x0, y0 - HALL_DEPTH_M, x0 + CAGE_WIDTH_M, y0)
    else:  # east / west -- klatka obrócona 90 stopni
        need_w, need_h = CAGE_DEPTH_M + HALL_DEPTH_M, CAGE_WIDTH_M
        if need_w > w + 1e-9 or need_h > h + 1e-9:
            return None
        y0 = cy - CAGE_WIDTH_M / 2.0
        if anchor == "east":
            cage = rect(maxx - CAGE_DEPTH_M, y0, maxx, y0 + CAGE_WIDTH_M)
            hall = rect(cage.bounds[0] - HALL_DEPTH_M, y0, cage.bounds[0], y0 + CAGE_WIDTH_M)
        else:
            cage = rect(minx, y0, minx + CAGE_DEPTH_M, y0 + CAGE_WIDTH_M)
            hall = rect(cage.bounds[2], y0, cage.bounds[2] + HALL_DEPTH_M, y0 + CAGE_WIDTH_M)

    core = cage.union(hall)
    if not core.within(zone.buffer(1e-6)):
        return None
    return cage, hall


def core_polygon(cage: Polygon, hall: Polygon) -> Polygon:
    return cage.union(hall)


def anchor_candidates(zone: Polygon) -> list[str]:
    """Kotwice mieszczące trzon, rosnąco po marnowaniu doświetlanej elewacji
    (center nie dotyka elewacji -> 0.0). Remis rozstrzyga kolejność _ANCHORS
    (north przed center: preferuj klatkę z oknami, gdy oba darmowe)."""
    from services.cage_placement import _light_waste_for_cage

    scored = []
    for rank, a in enumerate(_ANCHORS):
        core = build_point_core(zone, a)
        if core is None:
            continue
        cage, hall = core
        scored.append((_light_waste_for_cage(cage, zone), rank, a))
    scored.sort()
    return [a for _, _, a in scored]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_point_access.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/services/point_access.py backend/tests/test_point_access.py
git commit -m "feat: point-access core (cage+hall) with anchor candidates for klatkowiec mode"
```

---

### Task 2: Podział strefy wokół trzonu ("wiatraczek")

**Files:**
- Modify: `backend/services/point_access.py`
- Test: `backend/tests/test_point_access.py`

**Interfaces:**
- Consumes: `core_polygon` z Task 1; `services.layout.ApartmentSpec`
  (pola: `type: str`, `min_area_m2: float`, `target_count: int`);
  `services.trakt_division.slice_trakts(remainder, circulation_geometry,
  specs, rng, queue_override=None, component_order=None, spine_segments=None,
  footprint=None) -> tuple[list[ApartmentCell], Polygon|None]`.
- Produces:
  - `point_zone_components(zone: Polygon, core: Polygon) -> list[tuple[Polygon, bool]]`
    — części remainder strefy z kierunkiem cięcia `horizontal: bool`
    (cięcia PROSTOPADLE do krawędzi styku z trzonem, żeby każda komórka
    zachowała styk).
  - `slice_point_zone(zone, core, specs, rng, queue_override=None,
    component_order=None) -> tuple[list[ApartmentCell], Polygon | None]`
    — kontrakt zwrotu identyczny jak `slice_trakts`.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_point_access.py
import random

from services.layout import ApartmentSpec
from services.point_access import point_zone_components, slice_point_zone


def test_point_zone_components_all_touch_core():
    zone = _rect(0, 0, 23, 13.75)
    cage, hall = build_point_core(zone, "center")
    core = core_polygon(cage, hall)
    comps = point_zone_components(zone, core)
    assert len(comps) >= 3
    for poly, _horiz in comps:
        assert poly.distance(core) < 0.06


def test_slice_point_zone_units_touch_core_and_facade():
    """Wzorzec 5 z referencji: 5 mieszkań wiatraczkiem, każde dotyka trzonu."""
    zone = _rect(0, 0, 23, 13.75)
    cage, hall = build_point_core(zone, "center")
    core = core_polygon(cage, hall)
    specs = [
        ApartmentSpec(type="2Pd", min_area_m2=55, target_count=2),
        ApartmentSpec(type="2Pm", min_area_m2=45, target_count=2),
        ApartmentSpec(type="P1", min_area_m2=33, target_count=1),
    ]
    cells, leftover = slice_point_zone(zone, core, specs, rng=random.Random(1))
    assert 3 <= len(cells) <= 6
    for c in cells:
        assert c.polygon.distance(core) < 0.06, "mieszkanie bez styku z trzonem"
        assert c.polygon.exterior.intersection(zone.exterior).length > 1.0 or \
            c.polygon.boundary.intersection(zone.exterior).length > 1.0
    # pustka co najwyżej marginalna
    left_area = 0.0 if leftover is None or leftover.is_empty else leftover.area
    assert left_area / (zone.area - core.area) < 0.10
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_point_access.py -q`
Expected: FAIL `ImportError: point_zone_components`

- [ ] **Step 3: Write implementation**

```python
# dopisz do backend/services/point_access.py
from shapely.geometry import MultiPolygon


def _parts(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if isinstance(g, Polygon) and g.area > 1e-6]
    return []


def point_zone_components(zone: Polygon, core: Polygon) -> list[tuple[Polygon, bool]]:
    """Remainder strefy pocięty pionowo na krawędziach trzonu (core.minx,
    core.maxx) na pas zachodni / środkowy / wschodni; pas środkowy dzielony
    poziomo nad/pod trzonem. Kierunek cięcia komórek: prostopadle do
    krawędzi styku z trzonem -- pasy boczne (styk pionową krawędzią trzonu)
    tną poziomo (horizontal=True w konwencji slice_trakts: kursor po x?
    NIE -- horizontal=True znaczy 'korytarz poziomy, kursor po x'. Tu:
    pas STYKAJĄCY SIĘ pionową krawędzią trzonu musi być cięty POZIOMO,
    czyli kursor po y -> horizontal=False; pas nad/pod trzonem styka się
    poziomą krawędzią -> cięcia pionowe -> horizontal=True)."""
    minx, miny, maxx, maxy = zone.bounds
    cminx, cminy, cmaxx, cmaxy = core.bounds
    remainder = zone.difference(core)

    def band(x0, y0, x1, y1):
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            return None
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    out: list[tuple[Polygon, bool]] = []
    for rect, horiz in (
        (band(minx, miny, cminx, maxy), False),   # zachód: styk pionowy -> tnij po y
        (band(cmaxx, miny, maxx, maxy), False),   # wschód
        (band(cminx, cmaxy, cmaxx, maxy), True),  # nad trzonem: tnij po x
        (band(cminx, miny, cmaxx, cminy), True),  # pod trzonem (hol)
    ):
        if rect is None:
            continue
        for poly in _parts(remainder.intersection(rect)):
            if poly.area > 1.0:
                out.append((poly, horiz))
    return out


def slice_point_zone(zone, core, specs, rng, queue_override=None, component_order=None):
    """Cienki adapter na slice_trakts: komponenty wiatraczka podajemy przez
    typed_components-owy mechanizm slice_trakts NIE da się użyć wprost (on
    liczy komponenty per strefa spine'u), więc wołamy jego niskopoziomowy
    kontrakt: slice_trakts z remainder=MultiPolygon pasów i circulation=core
    -- kierunki wymusza się przekazując spine_segments=None i footprint=None
    (wtedy slice_trakts bierze kierunek z geometrii korytarza per komponent),
    ALE trzon nie jest podłużny, więc kierunek per komponent nadpisujemy:
    budujemy sztuczne spine_segments = po jednym odcinku wzdłuż krawędzi
    styku każdego pasa, a footprint=None zostawia ścieżkę per-komponent
    (nearest segment)."""
    from shapely.geometry import LineString  # noqa: F401 (dokumentacja intencji)
    from shapely.ops import unary_union

    from services.trakt_division import slice_trakts

    comps = point_zone_components(zone, core)
    if component_order is not None:
        comps = [comps[i] for i in component_order if i < len(comps)]
    remainder = unary_union([p for p, _ in comps])
    # sztuczny spine: odcinek środkiem każdego pasa, zorientowany tak, żeby
    # nearest-segment w slice_trakts dał żądany kierunek cięcia
    segs = []
    for poly, horiz in comps:
        x0, y0, x1, y1 = poly.bounds
        if horiz:  # cięcia pionowe -> segment poziomy
            segs.append(((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)))
        else:      # cięcia poziome -> segment pionowy
            segs.append((((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)))
    return slice_trakts(
        remainder, core, specs, rng,
        queue_override=queue_override, spine_segments=segs, footprint=None,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_point_access.py -q`
Expected: 6 passed. Jeśli `slice_point_zone` nie trzyma styku (komórka gubi
trzon), sprawdź konwencję kierunku w `slice_trakts` (`horizontal = kursor po
x`) i dopasuj mapowanie `horiz` w `point_zone_components` — test styku jest
źródłem prawdy, konwencja bywa myląca.

- [ ] **Step 5: Commit**

```bash
git add backend/services/point_access.py backend/tests/test_point_access.py
git commit -m "feat: pinwheel zone division around point-access core"
```

---

### Task 3: place_circulation z corridor_mode="point"

**Files:**
- Modify: `backend/services/circulation.py` (funkcja `place_circulation`,
  ~linia 646; dispatch po `corridor_mode`)
- Test: `backend/tests/test_circulation.py`

**Interfaces:**
- Consumes: `build_point_core`, `core_polygon`, `anchor_candidates` (Task 1).
- Produces: `place_circulation(..., corridor_mode="point")` →
  `CirculationResult` z: `circulation_geometry` = unia trzonów wszystkich
  stref, `cage_polygons` = klatki, `remainder` = footprint − trzony,
  `centerline == []`, `spine_segments == []`, `evacuation_dots == []`,
  nowe pole `CirculationResult.zone_access_modes: list[str]`
  (per strefa: `"point"` | `"corridor"`; default `[]` dla starych ścieżek).

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_circulation.py
def test_place_circulation_point_mode_no_corridor():
    """Tryb klatkowy (plan 2026-07-16): sam trzon, zero korytarza/spine."""
    from services.circulation import place_circulation

    footprint = Polygon([(0, 0), (23, 0), (23, 13.75), (0, 13.75)])
    result = place_circulation(
        footprint, corridor_width_m=1.5, stair_width_m=1.2, place_cage=True,
        cage_size_m=2.6, cage_position="auto", num_cages=1,
        corridor_mode="point",
    )
    assert result.centerline == []
    assert result.spine_segments == []
    assert len(result.cage_polygons) == 1
    assert result.zone_access_modes == ["point"]
    # trzon = klatka + hol: komunikacja większa niż sama klatka, ale mała
    cage_area = result.cage_polygons[0].area
    assert cage_area < result.circulation_geometry.area <= cage_area + 4.2 * 1.8 + 1e-6
    # bilans powierzchni się domyka
    assert abs(result.remainder.area + result.circulation_geometry.area
               - footprint.area) < 1e-3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_circulation.py::test_place_circulation_point_mode_no_corridor -q`
Expected: FAIL (obecny kod buduje korytarz i spine)

- [ ] **Step 3: Implementation**

W `CirculationResult` (linia ~531) dopisz pole:

```python
    zone_access_modes: list = field(default_factory=list)
    """Per strefa (indeks = zones): "point" | "corridor" (plan 2026-07-16).
    Puste w wynikach sprzed trybu klatkowego i w ścieżkach manual/reshape."""
```

W `place_circulation`, ZARAZ po `rectangle_decompose`/budowie stref, dodaj
gałąź (przed istniejącą ścieżką spine/korytarza):

```python
    if corridor_mode == "point":
        from services.point_access import anchor_candidates, build_point_core, core_polygon

        cages: list[Polygon] = []
        cores: list[Polygon] = []
        modes: list[str] = []
        for zone in zones:
            cands = anchor_candidates(zone.polygon)
            if not cands:
                raise ValueError(
                    "Strefa za mała na trzon klatkowy -- zmień tryb korytarza"
                )
            cage, hall = build_point_core(zone.polygon, cands[0])
            cages.append(cage)
            cores.append(core_polygon(cage, hall))
            modes.append("point")
        circulation = unary_union(cores)
        remainder = footprint.difference(circulation)
        return CirculationResult(
            zones=zones,
            circulation_geometry=circulation,
            cage_polygons=cages,
            remainder=remainder,
            centerline=[],
            evacuation_dots=[],
            spine_segments=[],
            zone_access_modes=modes,
        )
```

Uwaga dla implementującego: `zones` w tym miejscu to lista obiektów `Zone`
z polem `.polygon` — obejrzyj początek `place_circulation`, użyj tej samej
zmiennej, którą konsumuje dalsza część funkcji. `unary_union` jest już
importowane w module.

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_circulation.py -q`
Expected: wszystkie pass (nowy + stare bez regresji)

- [ ] **Step 5: Commit**

```bash
git add backend/services/circulation.py backend/tests/test_circulation.py
git commit -m "feat: corridor_mode=point places cage+hall cores instead of corridors"
```

---

### Task 4: Silnik mieszkań rozumie strefy punktowe

**Files:**
- Modify: `backend/services/trakt_division.py` (funkcja `typed_components`)
- Modify: `backend/services/unit_mix.py` (przekazanie `point_cores`)
- Test: `backend/tests/test_unit_iterations.py`

**Interfaces:**
- Consumes: `point_zone_components` (Task 2), `CirculationResult.zone_access_modes` (Task 3).
- Produces:
  - `typed_components(remainder, spine_segments=None, footprint=None,
    point_cores=None) -> list[tuple[Polygon, bool | None]]` — gdy
    `point_cores` (lista poligonów trzonów) podane, komponenty stref
    punktowych pochodzą z `point_zone_components` (z kierunkami), reszta
    jak dotąd.
  - `iterate_units(..., point_cores: list | None = None)` — przelotka do
    `typed_components` przez `_UnitsGenerator` (spójność liczby komponentów
    generator/slicer — patrz fix 2026-07-16 w docstringu `typed_components`).
  - `slice_trakts(..., point_cores=None)` — ta sama przelotka.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_unit_iterations.py
def test_iterate_units_point_mode_fills_and_touches_core():
    """Klatkowiec 23x13.75 (wzorzec 3/5): mieszkania wokół trzonu, winner
    hard_valid, pustka <=10%."""
    from services.circulation import place_circulation

    fp = _rect(0, 0, 23, 13.75)
    res = place_circulation(
        fp, corridor_width_m=1.5, stair_width_m=1.2, place_cage=True,
        cage_size_m=2.6, cage_position="auto", num_cages=1,
        corridor_mode="point",
    )
    cells, metas, _, _ = iterate_units(
        res.remainder, SHARES, iterations=10,
        circulation_geometry=res.circulation_geometry, footprint=fp,
        spine_segments=res.spine_segments,
        point_cores=[res.circulation_geometry],
    )
    assert metas[0].components["leftover"] <= 0.10
    for c in cells:
        assert c.polygon.distance(res.circulation_geometry) < 0.06
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py::test_iterate_units_point_mode_fills_and_touches_core -q`
Expected: FAIL `TypeError: iterate_units() got an unexpected keyword argument 'point_cores'`

- [ ] **Step 3: Implementation**

`trakt_division.typed_components` — dodaj parametr i gałąź NA POCZĄTKU:

```python
def typed_components(remainder, spine_segments=None, footprint=None, point_cores=None) -> list:
    ...  # docstring bez zmian, dopisz akapit:
    # Tryb klatkowy (plan 2026-07-16): `point_cores` = poligony trzonów;
    # komponenty wokół trzonu z kierunkami liczy point_zone_components --
    # strefy punktowe NIE przechodzą przez logikę spine.
    if point_cores:
        from shapely.ops import unary_union

        from services.point_access import point_zone_components

        typed: list[tuple[Polygon, "bool | None"]] = []
        cores = unary_union(point_cores)
        # strefa punktowa = bbox trzonu rozszerzony do komponentu remainder,
        # praktycznie: remainder to już footprint-trzony, więc liczymy
        # wiatraczek na CAŁYM remainder względem każdego trzonu osobno
        for core in (point_cores if isinstance(point_cores, list) else [point_cores]):
            zone_like = core.buffer(50.0).intersection(unary_union([remainder, cores]))
            # praktyczne strefy są prostokątne -- użyj bboxa remainder+core
            from shapely.geometry import box
            rb = unary_union([remainder, core]).bounds
            zone_rect = box(*rb)
            typed.extend(point_zone_components(zone_rect, core))
        return typed
    # ... (istniejące gałęzie spine / _polygons bez zmian)
```

Uwaga dla implementującego: powyższa gałąź obsługuje MVP = JEDNA strefa
punktowa na footprint prostokątnym (bbox remainder+core == strefa).
Multi-strefa (L/U mieszane) przychodzi w Task 6 — wtedy `point_cores`
będzie listą par (core, zone_polygon); NIE komplikuj teraz (YAGNI),
ale zostaw komentarz `# Task 6: multi-zone -- pary (core, zone)`.

`slice_trakts` — dodaj parametr `point_cores=None` i przekaż:
`typed = typed_components(remainder, spine_segments, footprint, point_cores)`.

`unit_mix.iterate_units` — parametr `point_cores=None`; przekaż do
`_UnitsGenerator.__init__` (nowy parametr, zapisz `self.point_cores`) i tam:
- `self._n_comp = len(typed_components(remainder, spine_segments, footprint, point_cores))`
- w `build()`: `slice_trakts(..., point_cores=self.point_cores)`.

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_unit_iterations.py tests/test_trakt_division.py -q`
Expected: wszystkie pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/trakt_division.py backend/services/unit_mix.py backend/tests/test_unit_iterations.py
git commit -m "feat: units engine slices point-access zones around the core"
```

---

### Task 5: Iteracje klatek w trybie punktowym (enumeracja kotwic)

**Files:**
- Modify: `backend/services/cage_placement.py` (`iterate_cage_placement`, linia ~394)
- Test: `backend/tests/test_cage_placement.py`

**Interfaces:**
- Consumes: `anchor_candidates`, `build_point_core`, `core_polygon` (Task 1);
  `_light_waste_for_cage`; `CirculationResult` (Task 3).
- Produces: `iterate_cage_placement(..., corridor_mode="point")` →
  `(CirculationResult, list[CageIterationMeta], int)` — metas = po jednym
  wariancie na kotwicę (deterministyczna enumeracja, bez SA; kotwic ≤5 na
  strefę), `score = light_waste_share` wariantu, winner = najniższy score.
  `CageIterationMeta` wypełnione jak w trybie korytarzowym
  (`cage_geometries`, `circulation_geometry`, `remainder`, `warnings`;
  `centerline`/`evacuation_dots` puste).

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_cage_placement.py
def test_iterate_cage_placement_point_mode_enumerates_anchors():
    footprint = _rect(0, 0, 23, 13.75)
    result, metas, best = iterate_cage_placement(
        footprint, 1.5, num_cages=1, weights=CageWeights(), iterations=10,
        corridor_mode="point",
    )
    assert result.zone_access_modes == ["point"]
    assert 1 <= len(metas) <= 5           # co najwyżej 5 kotwic
    assert metas[0].seed == best
    assert result.centerline == []
    scores = [m.score for m in metas]
    assert scores == sorted(scores)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cage_placement.py::test_iterate_cage_placement_point_mode_enumerates_anchors -q`
Expected: FAIL (tryb point nieobsłużony w iterate_cage_placement)

- [ ] **Step 3: Implementation**

Na początku `iterate_cage_placement` (po imports/NET_SHRINK) dodaj:

```python
    if corridor_mode == "point":
        from services.circulation import place_circulation
        from services.point_access import anchor_candidates

        # deterministyczna enumeracja kotwic -- kotwica per wariant; MVP:
        # jedna strefa lub ta sama kotwica we wszystkich strefach (Task 6
        # rozszerzy o kombinacje per strefa przy auto).
        zones_probe = place_circulation(
            footprint, corridor_width_m, 1.2, True, 2.6, "auto",
            num_cages=num_cages, corridor_mode="point",
        )
        anchors = anchor_candidates(zones_probe.zones[0].polygon)
        metas: list[CageIterationMeta] = []
        results: list[CirculationResult] = []
        for a in anchors:
            variant = _place_point_variant(footprint, corridor_width_m, a)
            share = sum(
                _light_waste_for_cage(c, footprint) for c in variant.cage_polygons
            ) / max(1, len(variant.cage_polygons))
            results.append(variant)
            metas.append(_meta_from_result(variant, score=share))
        order = sorted(range(len(metas)), key=lambda i: metas[i].score)
        metas = [metas[i] for i in order]
        for idx, m in enumerate(metas):
            m.seed = idx
        return results[order[0]], metas, 0
```

Dopisz w module dwa helpery (obok istniejących prywatnych):

```python
def _place_point_variant(footprint, corridor_width_m, anchor: str):
    """CirculationResult trybu punktowego z WYMUSZONĄ kotwicą (zamiast
    najlepszej z anchor_candidates)."""
    from shapely.ops import unary_union

    from services.bsp import rectangle_decompose
    from services.circulation import CirculationResult, Zone
    from services.point_access import build_point_core, core_polygon

    zones = [Zone(polygon=z) for z in rectangle_decompose(footprint)]
    cages, cores = [], []
    for z in zones:
        built = build_point_core(z.polygon, anchor)
        if built is None:
            from services.point_access import anchor_candidates
            cands = anchor_candidates(z.polygon)
            if not cands:
                raise ValueError("Strefa za mała na trzon klatkowy")
            built = build_point_core(z.polygon, cands[0])
        cage, hall = built
        cages.append(cage)
        cores.append(core_polygon(cage, hall))
    circulation = unary_union(cores)
    return CirculationResult(
        zones=zones, circulation_geometry=circulation, cage_polygons=cages,
        remainder=footprint.difference(circulation), centerline=[],
        evacuation_dots=[], spine_segments=[],
        zone_access_modes=["point"] * len(zones),
    )


def _meta_from_result(result, score: float) -> CageIterationMeta:
    return CageIterationMeta(
        seed=0, score=score, cages_count=len(result.cage_polygons),
        components={"light_waste": round(score, 4)},
        cage_geometries=list(result.cage_polygons),
        circulation_geometry=result.circulation_geometry,
        remainder=result.remainder, centerline=[], evacuation_dots=[],
        warnings=[],
    )
```

Uwaga: sprawdź konstruktor `Zone` (w `services/circulation.py`) — jeśli ma
więcej pól wymaganych niż `polygon`, skopiuj wzorzec z miejsca, gdzie
`place_circulation` buduje `zones`. Sprawdź też pola `CageIterationMeta`
w tym module i dopasuj `_meta_from_result` (test wskaże braki).

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -q`
Expected: wszystkie pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/cage_placement.py backend/tests/test_cage_placement.py
git commit -m "feat: point-mode cage iterations enumerate core anchors deterministically"
```

---

### Task 6: Tryb auto — porównanie klatka vs korytarz per strefa

**Files:**
- Modify: `backend/services/cage_placement.py`
- Test: `backend/tests/test_cage_placement.py`

**Interfaces:**
- Consumes: Taski 3-5; `iterate_units` (z `point_cores`),
  `services.unit_mix.pick_best_iteration`, `LEFTOVER_WEIGHT`.
- Produces:
  - `decide_access_modes(footprint, shares, corridor_width_m, num_cages,
    weights, iterations, strategy="anneal", base_seed=0) ->
    tuple[CirculationResult, list[CageIterationMeta], int]`
  - `iterate_cage_placement(..., corridor_mode="auto")` deleguje do niej.
  - Composite wariantu = `units_winner.score` (już zawiera karę leftover)
    `+ COMM_SHARE_WEIGHT * (circulation_area / footprint_area)`;
    `COMM_SHARE_WEIGHT = 2.0` (stała modułu z docstringiem: referencje §1 —
    klatkowiec 9-13% vs korytarzowiec więcej; waga premiuje odchudzoną
    komunikację, nie zakazuje korytarza).
  - `shares: list[ProgramShare] | None` — gdy `None` (endpoint /circulation
    nie zna programu), użyj domyślnego programu porównawczego
    `_DEFAULT_PROBE_SHARES` (stała: M1 10% 25-32, M2 40% 38-48,
    M3 40% 58-70, M4 10% 72-90) — służy TYLKO do porównania wariantów.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_cage_placement.py
def test_auto_mode_prefers_point_for_compact_deep_footprint():
    """23x13.75 (wzorzec 3): klatkowiec ma wygrać z korytarzem -- komunikacja
    ~30 m2 vs korytarz przez cały budynek."""
    footprint = _rect(0, 0, 23, 13.75)
    result, metas, _ = iterate_cage_placement(
        footprint, 1.5, num_cages=1, weights=CageWeights(), iterations=8,
        corridor_mode="auto",
    )
    assert result.zone_access_modes == ["point"]


def test_auto_mode_prefers_corridor_for_long_bar():
    """60x12 (trakt 12, budynek długi): korytarz środkiem -- wzorzec 4."""
    footprint = _rect(0, 0, 60, 12)
    result, metas, _ = iterate_cage_placement(
        footprint, 1.5, num_cages=2, weights=CageWeights(), iterations=8,
        corridor_mode="auto",
    )
    assert result.zone_access_modes == ["corridor"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -k auto_mode -q`
Expected: FAIL

- [ ] **Step 3: Implementation**

```python
# dopisz do backend/services/cage_placement.py
COMM_SHARE_WEIGHT = 2.0
"""Waga udziału komunikacji w composite auto-decyzji (plan 2026-07-16).
Referencje (docs/references/typologia-klatkowa.md §1): klatkowiec 9-13%
powierzchni vs korytarzowiec więcej. To rachunek, nie reguła: gruby trakt
albo długie skrzydło i tak wygra korytarzem przez jakość mieszkań."""

_DEFAULT_PROBE_SHARES = None  # leniwe -- ProgramShare importowany w funkcji


def _probe_shares():
    global _DEFAULT_PROBE_SHARES
    if _DEFAULT_PROBE_SHARES is None:
        from services.unit_mix import ProgramShare
        _DEFAULT_PROBE_SHARES = [
            ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
            ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
            ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
            ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
        ]
    return _DEFAULT_PROBE_SHARES


def decide_access_modes(footprint, shares, corridor_width_m, num_cages,
                        weights, iterations, strategy="anneal", base_seed=0):
    """Porównaj warianty korytarzowy i punktowy pełnym (budżetowanym)
    przebiegiem silnika mieszkań; zwróć wynik lepszego. MVP: decyzja
    całobudynkowa (wszystkie strefy ten sam tryb); per-strefa mieszanie --
    następny krok po MVP (patrz plan, sekcja Deferred)."""
    from services.unit_mix import iterate_units

    shares = shares or _probe_shares()
    probe_budget = max(6, iterations // 2)
    candidates = []
    for mode in ("double", "point"):
        try:
            circ, metas, best = iterate_cage_placement(
                footprint, corridor_width_m, num_cages, weights,
                iterations=iterations, strategy=strategy,
                corridor_mode=mode, base_seed=base_seed,
            )
        except ValueError:
            continue  # np. strefa za mała na trzon
        point_cores = [circ.circulation_geometry] if mode == "point" else None
        _cells, umetas, _s, _t = iterate_units(
            circ.remainder, shares, iterations=probe_budget,
            footprint=footprint, circulation_geometry=circ.circulation_geometry,
            strategy=strategy, spine_segments=circ.spine_segments,
            base_seed=base_seed, point_cores=point_cores,
        )
        comm_share = circ.circulation_geometry.area / footprint.area
        composite = umetas[0].score + COMM_SHARE_WEIGHT * comm_share
        # tryb łamiący zakazy twarde przegrywa z czystym niezależnie od score
        rank = (0 if umetas[0].hard_valid else 1, composite)
        label = "corridor" if mode == "double" else "point"
        candidates.append((rank, label, circ, metas, best))
    if not candidates:
        raise ValueError("Auto: żaden tryb komunikacji nie da się zbudować")
    candidates.sort(key=lambda c: c[0])
    _rank, label, circ, metas, best = candidates[0]
    if not circ.zone_access_modes:
        circ.zone_access_modes = [label] * len(circ.zones)
    return circ, metas, best
```

W `iterate_cage_placement` na początku:

```python
    if corridor_mode == "auto":
        return decide_access_modes(
            footprint, None, corridor_width_m, num_cages, weights,
            iterations, strategy=strategy, base_seed=base_seed,
        )
```

Oraz w gałęzi korytarzowej: po zbudowaniu zwycięskiego `CirculationResult`
ustaw `result.zone_access_modes = ["corridor"] * len(result.zones)` (żeby
frontend zawsze dostawał wypełnione pole).

- [ ] **Step 4: Run tests**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_cage_placement.py -q`
Expected: wszystkie pass. Jeśli auto wybierze inaczej niż test oczekuje,
najpierw obejrzyj composite obu wariantów (print w teście) — dopuszczalna
korekta to STROJENIE `COMM_SHARE_WEIGHT` (1.0-4.0), nie zmiana asercji.

- [ ] **Step 5: Commit**

```bash
git add backend/services/cage_placement.py backend/tests/test_cage_placement.py
git commit -m "feat: auto access mode compares corridor vs point variants via units engine"
```

---

### Task 7: API — corridor_mode point/auto + zone_access_modes w response

**Files:**
- Modify: `backend/api/v1/endpoints/layout.py`
- Modify: `backend/services/layout.py` (przelotka `point_cores` w generate)
- Test: `backend/tests/test_layout_circulation_endpoint.py`

**Interfaces:**
- Consumes: Taski 3-6.
- Produces:
  - `CirculationSpec.corridor_mode: Literal["double","gallery","point","auto"]`
    (obecnie `"double" | "gallery"` — rozszerzyć walidację/typ).
  - `CirculationResponse.zone_access_modes: list[str] = []`.
  - `/layout/units` (`UnitsRequest`) + `/layout/generate`: nowe pole
    `point_cores: list[GeoJsonPolygon] | None = None` → przelotka do
    `iterate_units(point_cores=...)`; w `/generate` `LayoutInput` dostaje
    `corridor_mode` już dziś — dopilnuj, żeby gdy circulation wyszło
    punktowe, `services/layout.py` przekazał
    `point_cores=[circ.circulation_geometry]` do silnika mieszkań.

- [ ] **Step 1: Write the failing test**

```python
# dopisz do backend/tests/test_layout_circulation_endpoint.py
def test_circulation_endpoint_point_mode():
    payload = _base_payload()  # istniejący helper w tym pliku; jeśli nazwa
    # inna -- skopiuj payload z test_circulation_endpoint_iterative_mode
    payload["circulation"]["corridor_mode"] = "point"
    payload["footprint"] = [[0, 0], [23, 0], [23, 13.75], [0, 13.75]]
    payload["circulation"]["num_cages"] = 1
    resp = client.post("/api/v1/layout/circulation", json=payload)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["zone_access_modes"] == ["point"]
    assert data["centerline"] == []
    assert data["cage_iterations"], "metas kotwic muszą być na liście iteracji"


def test_circulation_endpoint_auto_mode_returns_modes():
    payload = _base_payload()
    payload["circulation"]["corridor_mode"] = "auto"
    resp = client.post("/api/v1/layout/circulation", json=payload)
    assert resp.status_code == 200, resp.text
    assert resp.json()["zone_access_modes"] != []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py -k "point_mode or auto_mode" -q`
Expected: FAIL (walidacja odrzuca "point"/"auto" albo brak pola w response)

- [ ] **Step 3: Implementation**

W `endpoints/layout.py`:
- `CirculationSpec.corridor_mode` i `LayoutGenerateRequest` — rozszerz typ o
  `"point"` i `"auto"` (tam gdzie dziś jest Literal/walidator dla
  double/gallery).
- `CirculationResponse` — dodaj `zone_access_modes: list[str] = []`;
  w handlerze `/circulation` wypełnij z `result.zone_access_modes`.
- `UnitsRequest` — dodaj `point_cores: list[dict] | None = None`; w handlerze
  `/units` zamień GeoJSON na Shapely (użyj tego samego helpera co dla
  `spine_segments`/geometrii w tym pliku — `shape()` z `shapely.geometry`)
  i przekaż `iterate_units(point_cores=...)`.
- `services/layout.py` — w ścieżce generate: jeśli
  `circulation_result.zone_access_modes` zawiera `"point"`, wywołaj
  `iterate_units(..., point_cores=[circulation_result.circulation_geometry])`.

- [ ] **Step 4: Run tests + import smoke**

Run: `./.venv/Scripts/python.exe -m pytest tests/test_layout_circulation_endpoint.py -q`
Run: `./.venv/Scripts/python.exe -c "import main; print('IMPORT_OK')"`
Expected: pass + IMPORT_OK

- [ ] **Step 5: Commit**

```bash
git add backend/api/v1/endpoints/layout.py backend/services/layout.py backend/tests/test_layout_circulation_endpoint.py
git commit -m "feat: point/auto corridor_mode through API with zone_access_modes"
```

---

### Task 8: Frontend — select trybu, presety, przelotka point_cores

**Files:**
- Modify: `frontend/app/lib/api.ts`
- Modify: `frontend/app/state/SessionContext.tsx`
- Modify: `frontend/app/components/CirculationSection.tsx`

**Interfaces:**
- Consumes: API z Task 7.
- Produces:
  - `CirculationSpecInput.corridor_mode?: "auto" | "double" | "gallery" | "point"`.
  - `CirculationResponse.zone_access_modes?: string[]`.
  - `subdivideUnits(...)` przekazuje `point_cores` gdy
    `state.circulationResult.zone_access_modes` zawiera `"point"`
    (wartość: `[circulation_geometry]` z aktualnego wyniku).
  - Select "Tryb korytarza" w `CirculationSection.tsx` — opcje:
    `auto` → "Auto (klatki vs korytarz)", `double` → "Dwutrakt (korytarz w środku)",
    `gallery` → "Galeriowiec (korytarz przy elewacji)", `point` → "Klatkowy (bez korytarza)".
  - `TYPOLOGY_CONFIG` w `SessionContext.tsx`: preset `punktowiec` →
    `corridor_mode: "point"`, `num_cages: 1`; preset klatkowca sekcyjnego
    (jeśli w tabeli) → `corridor_mode: "point"`; pozostałe bez zmian;
    nowy wpis pomocy w `TYPOLOGY_HINTS` dla trybu klatkowego.

- [ ] **Step 1: Typy + select + preset (frontend bez testów jednostkowych —
  weryfikacja przez tsc i smoke w Task 9)**

W `api.ts` rozszerz typy jak w Interfaces (dokładnie te unie stringów).
W `CirculationSection.tsx` znajdź select "Tryb korytarza" (obecne opcje
double/gallery) i dodaj `auto` + `point` z etykietami j.w.
W `SessionContext.tsx`:
- `initialCirculation.corridor_mode` zostaje `"double"` (bez zmiany domyślnej
  — user wybiera świadomie albo presetem).
- `TYPOLOGY_CONFIG`: wpis punktowca → `corridor_mode: "point"`, `num_cages: 1`.
- `runSubdivideUnits`: po `state.circulationResult` dodaj

```typescript
const pointCores =
  state.circulationResult.zone_access_modes?.includes("point") &&
  state.circulationResult.circulation_geometry
    ? [state.circulationResult.circulation_geometry]
    : undefined;
```

i przekaż `pointCores` jako nowy argument `subdivideUnits` (dodaj parametr
w `api.ts`, POST-uje `point_cores`).

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: 0 błędów

- [ ] **Step 3: Commit**

```bash
git add frontend/app/lib/api.ts frontend/app/state/SessionContext.tsx frontend/app/components/CirculationSection.tsx
git commit -m "feat: point/auto access mode in corridor select, typology presets, point_cores passthrough"
```

---

### Task 9: E2E + golden testy decyzji + weryfikacja live

**Files:**
- Test: `backend/tests/test_unit_iterations.py` (e2e generate)
- Test: `backend/tests/test_cage_placement.py` (golden L)

**Interfaces:**
- Consumes: całość.

- [ ] **Step 1: Golden test L (mieszany potencjał, MVP = decyzja całobudynkowa)**

```python
# dopisz do backend/tests/test_cage_placement.py
def test_auto_mode_L_footprint_decides_and_is_consistent():
    """L 74x12 + noga 14x30: MVP wybiera JEDEN tryb dla całego budynku;
    test pilnuje spójności (modes wypełnione, tyle ile stref) i tego, że
    wynik da się pociąć bez pustki >10%."""
    from services.unit_mix import ProgramShare, iterate_units

    footprint = _rect(0, 0, 74, 12).union(_rect(60, -30, 74, 0))
    result, metas, _ = iterate_cage_placement(
        footprint, 1.5, num_cages=3, weights=CageWeights(), iterations=8,
        corridor_mode="auto",
    )
    assert len(result.zone_access_modes) == len(result.zones)
    assert set(result.zone_access_modes) <= {"point", "corridor"}
    shares = [
        ProgramShare(type="M2", percentage=50, area_min_m2=38, area_max_m2=48),
        ProgramShare(type="M3", percentage=50, area_min_m2=58, area_max_m2=70),
    ]
    point_cores = (
        [result.circulation_geometry]
        if "point" in result.zone_access_modes else None
    )
    _c, umetas, _s, _t = iterate_units(
        result.remainder, shares, iterations=8, footprint=footprint,
        circulation_geometry=result.circulation_geometry,
        spine_segments=result.spine_segments, point_cores=point_cores,
    )
    assert umetas[0].components["leftover"] <= 0.10
```

- [ ] **Step 2: Pełna suita**

Run: `./.venv/Scripts/python.exe -m pytest -q`
Expected: wszystkie pass (bazowo 305 + nowe)

- [ ] **Step 3: Live smoke (KRYTYCZNE: świeży serwer — patrz gotcha)**

```powershell
# zabij sieroty uvicorn (serwują STARY kod):
Get-CimInstance Win32_Process -Filter "Name like '%python%'" |
  Where-Object { $_.CommandLine -match 'uvicorn|spawn_main' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
# start:
Set-Location backend; & ".\.venv\Scripts\python.exe" -m uvicorn main:app --reload --port 8000
```

POST `/api/v1/layout/circulation` z `corridor_mode="point"` na footprint
`[[0,0],[23,0],[23,13.75],[0,13.75]]` → oczekuj `zone_access_modes: ["point"]`,
puste `centerline`; potem `corridor_mode="auto"` na `[[0,0],[60,0],[60,12],[0,12]]`
→ `["corridor"]`. Weryfikuj BEHAWIORALNIE (wartości pól), nie samym HTTP 200.

- [ ] **Step 4: Commit + ledger**

```bash
git add backend/tests/
git commit -m "test: golden auto-decision tests for point vs corridor access"
```

Dopisz wpis do `.superpowers/sdd/progress.md` (data, zakres, wynik suity).

---

## Deferred (świadomie POZA planem — nie implementować)

- Decyzja mieszana per strefa w L/U (ramię A punktowe, ramię B korytarzowe)
  — wymaga par (core, zone) w `typed_components` i łączenia ewakuacji.
- Hybryda "klatka + krótki korytarz" (wzorzec 6 z referencji).
- Parter z wiatrołapem/wózkownią (referencje §9).
- Drag trzonu na canvasie (move-cage dla trybu punktowego).
- Kropki ewakuacyjne w strefach punktowych (dziś: brak kropek = OK).
- Sekcyjny klatkowiec wielotrzonowy: num_cages trzonów wzdłuż długiej strefy
  (pary core+sekcja w typed_components); dziś num_cages ignorowany w point,
  porównanie auto na długich budynkach faworyzuje korytarz artefaktem
  1-trzonu (review Task 6).

## Self-Review (wykonane przy pisaniu)

1. Spec coverage: klatkowiec ✔ (T1-T5), równolegle z korytarzem ✔ (T3/T7),
   auto-decyzja bez sztywnej reguły ✔ (T6, composite), frontend ✔ (T8),
   wiedza z rzutów ✔ (referencje + golden testy T6/T9).
2. Placeholdery: brak TBD; dwa miejsca celowo każą implementującemu
   zweryfikować konstruktory (`Zone`, `CageIterationMeta`) zamiast zgadywać.
3. Spójność typów: `zone_access_modes: list[str]` wszędzie; `point_cores:
   list[Polygon]` backend / `GeoJsonPolygon[]` API; kontrakt zwrotu
   `slice_point_zone` == `slice_trakts`.
