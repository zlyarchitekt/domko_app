# Redesign silnika generowania układu — obrys → korytarz/klatka → mieszkania

**Data:** 2026-07-02
**Status:** zaakceptowany do implementacji
**Kontekst:** przebudowa `backend/services/layout.py` + `backend/services/bsp.py` po audycie z 2026-07-02, który znalazł, że obecny algorytm (`bsp_zones`) nie dekomponuje realnych obrysów wklęsłych na prostokąty — cicho zwraca strefy wciąż wklęsłe, co psuje korytarz, klatkę i podział na mieszkania w sposób niewykrywalny bez ręcznej weryfikacji (patrz `docs/../ANALIZA_FINCH3D` i pamięć `project_deep_audit_20260702`). Inspiracja architektoniczna: analiza aplikacji Finch 3D (`ANALIZA_FINCH3D/specyfikacja_systemowa_finch3d.md`).

Rozdział "Pokoje" (Finch Moduł 4 — adaptacyjne rzuty wewnętrzne, solver Cassowary) **jest świadomie poza zakresem** tego zadania — decyzja użytkownika.

---

## 1. Architektura — dwa jawne etapy

Dziś: `generate_layout()` robi wszystko w jednej rekurencyjnej funkcji (`bsp_zones`), z ukrytym założeniem że każda "strefa" jest prostokątem. Nowy podział:

```
Etap 0 (bez zmian): obrys
  footprint_service.py (/footprint/from-points) — bez zmian
  dxf_import.py (/footprint/import-dxf) — bez zmian

Etap 1: place_circulation(footprint, params) → CirculationResult
  backend/services/circulation.py (NOWY plik)
  - klatka wg trybu 1a/1b/2/3/auto — PRZENIESIONA z layout.py, logika bez zmian
    (_edge_cage, _centered_cage, _corner_cage_convex, corner_cage dla wklęsłych)
  - korytarz: footprint.buffer(-corridor_width_m) → footprint.difference(offset)
    → pas wzdłuż wnętrza obrysu, przycięty po stronie klatki (patrz §3)
  - wynik: circulation_geometry (Polygon|MultiPolygon), cage_polygons, 
    remainder (Polygon|MultiPolygon — przestrzeń zostająca na mieszkania,
    MOŻE BYĆ wklęsła/wieloczęściowa, to jest oczekiwane, nie błąd)

Etap 2: subdivide_units(remainder, apartment_specs) → UnitMixResult
  backend/services/unit_mix.py (NOWY plik)
  2a. rectangle_decompose(remainder) → list[Polygon]  (patrz §4)
      — realna dekompozycja wielokąta (także wklęsłego) na prostokąty,
        zastępuje fikcyjną obsługę wklęsłości w bsp_zones
  2b. fit_program_to_rectangles(rectangles, specs) → list[ApartmentCell], leftover
      — knapsack/DP zamiast dzisiejszego sekwencyjnego FIFO (patrz §5)

generate_layout() (ZOSTAJE, jako wrapper):
  circulation = place_circulation(...)
  units = subdivide_units(circulation.remainder, ...)
  return LayoutResult(...)  # dokładnie ten sam kształt co dziś
```

**Dlaczego wrapper, nie usunięcie starego kontraktu:** `optimizer.py` (`_run_lp_branch`/`_run_ga_branch`) i `/api/v1/layout/generate` potrzebują pełnego wyniku za jednym wywołaniem — przeszukiwanie wariantów w optymalizatorze zostaje nietknięte. Frontend, solar_analysis.py, wt_validation.py, export_* konsumują `LayoutResult` — jego kształt (pola, typy) **nie zmienia się**.

## 2. Nowe/zmienione endpointy API

| Endpoint | Status | Opis |
|---|---|---|
| `POST /api/v1/layout/circulation` | **NOWY** | Etap 1 osobno. Wejście: footprint + circulation params (tak jak dziś `CirculationSpec`). Wyjście: `circulation_geometry`, `cage_geometries`, `remainder` (GeoJSON, może być MultiPolygon). |
| `POST /api/v1/layout/units` | **NOWY** | Etap 2 osobno. Wejście: `remainder` (z etapu 1, ewentualnie po ręcznej korekcie na canvasie) + program mieszkań. Wyjście: `apartments`, `leftover`. |
| `POST /api/v1/layout/generate` | **ZOSTAJE** | Wrapper wołający oba etapy po kolei — używany przez optymalizator i jako "szybka ścieżka" (np. przy imporcie DXF, gdy użytkownik nie chce ręcznie korygować kroków). |
| `POST /api/v1/layout/split` | bez zmian, ale naprawiony | `split_polygon_by_edge` (bsp.py) dostaje tę samą, solidną dekompozycję z §4 zamiast dzisiejszego gubienia powierzchni dla >2 przecięć. |

## 3. Etap 1 — korytarz jako offset (nie bounding-box)

Zastępuje `_build_corridor()` (dziś: prostokąt z bounding-boxa strefy — działa tylko dla prostokątów).

```python
def _corridor_band(footprint: Polygon, width: float) -> Polygon | MultiPolygon:
    """Pas komunikacji wzdłuż wnętrza obrysu, szerokości `width`."""
    inner = footprint.buffer(-width)
    if inner.is_empty:
        # obrys za wąski na korytarz o tej szerokości na całym obwodzie —
        # zwróć całość jako korytarz (brak miejsca na mieszkania to wtedy
        # realny wynik programu, nie błąd algorytmu)
        return footprint
    return footprint.difference(inner)
```

To wykorzystuje `Polygon.buffer()`/`difference()` — dojrzałe, testowane od lat operacje GEOS, solidne dla obrysów wklęsłych (w przeciwieństwie do custom straight-skeleton, którego świadomie unikamy — uzasadnienie w rozmowie: `polyskel` jest niestabilny właśnie dla wierzchołków wklęsłych, czyli tam gdzie najbardziej nam zależy na poprawności).

**Ograniczenie do jednej strony (tryb klatki):** dla trybów 1a/1b (klatka przy elewacji) pas korytarza jest dalej przycinany do połowy obrysu (od strony klatki) tak jak dziś robi to pośrednio `_build_corridor` przez `cage_polygon.centroid` — logika wyboru strony zostaje, zmienia się tylko GEOMETRIA bazowa korytarza (offset zamiast bboxa).

**Cage placement** (`_place_cage_by_mode` + `_edge_cage`/`_centered_cage`/`_corner_cage_convex`/`corner_cage`) **przenosi się bez zmian logiki** z `layout.py`/`bsp.py` do nowego `circulation.py` — to nie jest zepsute, to jest przenoszone dla porządku (moduł per etap).

`remainder = footprint.difference(unary_union([circulation_geometry] + cage_polygons))` — może być `MultiPolygon`, może mieć wklęsłe części. To jest wejście do Etapu 2.

## 4. Etap 2a — dekompozycja na prostokąty (rectangle_decompose)

Zastępuje fikcyjną obsługę wklęsłości w `bsp_zones()` (dziś: wycina stały nibble 1×1m z pierwszego wklęsłego wierzchołka, często zostawiając resztę wciąż wklęsłą).

Algorytm — **rekurencyjny podział prowadzony po wierzchołkach wklęsłych, nie po stałym rozmiarze klatki**:

```python
def rectangle_decompose(poly: Polygon) -> list[Polygon]:
    """Dzieli (możliwie wklęsły) poligon na listę prostokątów."""
    if not concave_vertices(poly):
        # Poligon wypukły. Jeśli to NIE jest dokładnie prostokąt (skośny
        # czworobok po ekstremalnej edycji wierzchołka), zostaje jedną
        # "strefą" nie-prostokątną — świadomie zaakceptowane ograniczenie
        # (patrz §10 "Co NIE jest w zakresie"). fit_program_to_rectangles
        # (§5) operuje wtedy na jego bounding-boxie, tak jak dziś.
        return [poly]
    idx, x, y = concave_vertices(poly)[0]
    # Tnij PROSTĄ przechodzącą przez wierzchołek wklęsły, prostopadle do
    # jednej z sąsiadujących krawędzi (nie stały nibble 1x1m) — to jest
    # standardowa technika "rectangular decomposition of rectilinear
    # polygons przez wierzchołki refleksywne", rozszerzona o rzut na
    # najbliższą krawędź dla poligonów nie w pełni prostokątnych.
    part_a, part_b = split_polygon_by_edge(poly, cut_line_through(poly, idx, x, y))
    return rectangle_decompose(part_a) + rectangle_decompose(part_b)
```

Kluczowa różnica względem dzisiejszego `bsp_zones`: cięcie prowadzone jest **przez realny wierzchołek wklęsły na całą szerokość/głębokość poligonu** (tak jak `split_polygon_by_edge` już robi dla ręcznego podziału), a nie przez stały mały kwadrat w rogu. To gwarantuje, że KAŻDA rekurencja faktycznie usuwa wklęsłość (bo tnie przez punkt, który ją powodował), zamiast czasem zostawiać ją nietkniętą.

`split_polygon_by_edge` (bsp.py) dostaje przy okazji naprawę z audytu: obsługę >2 punktów przecięcia (dziś ucina do pierwszego/ostatniego i gubi powierzchnię) oraz przypadku kolinearnego (dziś ignorowany, GEOS-owy analog dzisiejszego buga solarnego) — używając tej samej techniki dystans-do-prostej + rzut parametryczny, którą naprawiłem dziś w `solar_analysis.py`.

## 5. Etap 2b — dopasowanie programu (fit_program_to_rectangles)

Zastępuje dzisiejsze `_slice_apartments`/`_cut_cell` (sekwencyjne, FIFO, trwałe odrzucanie części — bug #6 z audytu).

```python
def fit_program_to_rectangles(
    rectangles: list[Polygon], specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """DP/knapsack: dla każdego prostokąta wybierz najlepiej pasującą
    pozostałą specyfikację (nie tylko czoło kolejki), z tolerancją."""
```

- Dla każdego prostokąta z listy próbujemy WSZYSTKIE pozostałe (nieużyte jeszcze w pełni) specyfikacje programu, nie tylko pierwszą w kolejce — wybieramy tę, która daje **najmniejsze odchylenie procentowe** od `min_area_m2` po przycięciu.
- **Tolerancja ±3% (Finch §B.2)** — jeśli najlepsze dopasowanie mieści się w ±3%, tniemy dokładnie na `min_area_m2` (jak dziś). Jeśli wszystkie dostępne dopasowania wychodzą poza tolerancję, wybieramy najbliższe i **oznaczamy komórkę flagą `area_tolerance_exceeded`** (nowe pole na `ApartmentCell`, konsumowane przez nową regułę walidacji w §6) zamiast cichego zaakceptowania dowolnego odchylenia jak dziś.
- Prostokąt, który nie mieści żadnej pozostałej specyfikacji nawet z przekroczoną tolerancją, trafia do `leftover` (jak dziś) — ale dopiero PO sprawdzeniu wszystkich specyfikacji, nie tylko czoła kolejki.

To nie jest pełny algorytm Knapsack z gwarancją optymalności (NP-trudny w ogólności) — to zachłanna heurystyka "najlepsze dopasowanie z dostępnych", co jest wystarczające dla realnych rozmiarów programu (kilka-kilkanaście typów mieszkań) i dużo lepsze niż dzisiejsze sztywne FIFO.

## 6. Nowe reguły walidacji (z Finch §B.2, C — adaptowane, nie kopiowane 1:1)

Dodane do `apartment_validation.py` jako kolejne pola `ApartmentValidationResult`, **w tym samym dwupoziomowym wzorcu co istniejące reguły** (`MIN_DOOR_CONTACT_LENGTH_M` = twardy błąd vs `MIN_CONTACT_LENGTH_M` = ostrzeżenie):

| Reguła | Próg | Poziom | Uzasadnienie |
|---|---|---|---|
| Min. szerokość frontu elewacyjnego | 3.6 m (Finch: 360cm) | ostrzeżenie | Finch: zapobiega "szparom" mieszkaniowym. U nas: nowa stała `MIN_FACADE_FRONTAGE_M`, liczona jako suma długości krawędzi mieszkania stykających się z obrysem zewnętrznym (nie z korytarzem/klatką) |
| Max. stosunek głębokość:szerokość | 2.5:1 (Finch) | ostrzeżenie | Nowa stała `MAX_APARTMENT_ASPECT_RATIO`, liczona z bounding-boxa komórki (ta sama technika co `_apartment_min_width`) |
| Min. styk klatki z elewacją | 2.4 m (Finch: 240cm) | **twardy błąd** (dotyczy WT §68 doświetlenia klatki/oddymiania — to realny polski wymóg pokrewny, nie tylko heurystyka Finch) | Nowa reguła w `wt_validation.py`, kod `§68 ust.1-doswietlenie`, sprawdza `cage_polygon.boundary.intersection(footprint.boundary).length >= 2.4` |
| Przekroczona tolerancja powierzchni (§5) | >3% odchylenia od `min_area_m2` | ostrzeżenie | Nowe pole `area_tolerance_exceeded`, konsumowane w `validate_apartment()` |

**Nie przenosimy:** progów Finch dla szybu windy (160×210cm) — u nas nie ma modelu windy w ogóle, to nowa funkcja poza zakresem tego zadania, nie próg do samej walidacji istniejącej klatki schodowej.

## 7. Frontend — jawne kroki UX

Sidebar sekcja "Komunikacja" dostaje dwa przyciski zamiast bycia tylko formularzem pod jednym "Generuj układ":

1. **[Umieść korytarz i klatkę]** → `POST /layout/circulation` → renderuje `circulation_geometry`+`cage_geometries` na canvasie.
2. **Nowy tryb edycji `edit-circulation`** (analogiczny do dzisiejszego `edit-vertices`/`edit-lines`) — pełny drag krawędzi korytarza/klatki na canvasie (Konva draggable, snap co 0.5m jak reszta edycji). Po przeciągnięciu: automatyczny re-fetch `remainder` (przeliczenie `footprint.difference(...)` po nowej geometrii) — **bez** ponownego wołania całego `/layout/circulation` (to czysto geometryczna operacja, robimy ją też w `SessionContext.tsx` optymistycznie, tak jak dziś `moveSharedLine`).
3. **[Podziel na mieszkania]** (dawne "Generuj układ", teraz Etap 2) → `POST /layout/units` z `remainder` (ewentualnie po korekcie) + programem → renderuje `apartments`.

`state.layoutResult` (SessionContext) zyskuje pośredni stan: `circulationResult` (Etap 1) osobno od `layoutResult` (pełny, Etap 1+2) — analogicznie do dzisiejszego wzorca gdzie `UPDATE_VERTEX` czyści `layoutResult`/`validation` (naprawione dziś), tu: zmiana korytarza/klatki czyści tylko to, co zależy od Etapu 2 (mieszkania, solar, walidacja), nie cały stan od zera.

## 8. Testowanie

Poza przykładowymi testami (jak dziś) — **testy właściwościowe (property-based, `hypothesis`)** dla `rectangle_decompose` i `fit_program_to_rectangles`, bo dzisiejsze bugi (cut_cell depth/width, bsp_zones concave) przeszły przez 96/96 testów przykładowych niezauważone:
- `rectangle_decompose(poly)`: suma pól wyników == pole `poly` (±epsilon), zero nakładania się wyników, każdy wynik jest realnym prostokątem.
- `fit_program_to_rectangles`: suma pól (apartments + leftover) == suma pól rectangles (±epsilon), żadna komórka nie przekracza pola swojego macierzystego prostokąta.
- Generowanie losowych wielokątów wklęsłych (rectilinear, kontrolowana liczba wierzchołków refleksywnych) jako `hypothesis` strategy — bezpośrednio atakuje klasę bugów z dzisiejszego audytu.

## 9. Migracja / co się nie zmienia

- `LayoutResult`, `ApartmentCell`, `Zone` (dataclassy) — bez zmian pól (dodajemy tylko opcjonalne `area_tolerance_exceeded` na `ApartmentCell`, `default=False`, nie łamie istniejących konsumentów). **Wyjątek:** `circulation_geometry` może teraz faktycznie być `MultiPolygon` w praktyce (korytarz-jako-offset wokół wklęsłego obrysu może rozpaść się na kilka części) — typ pola w Pythonie nie jest dziś twardo wymuszany, ale każdy kod czytający to pole (solar_analysis.py, wt_validation.py, eksporty) musi obsłużyć `hasattr(geom, "geoms")` tak jak już robi `_decompose_to_polygons()` w `layout.py`/endpointach — sprawdzić przy implementacji, nie zakładać `Polygon` bez wyjątku.
- `solar_analysis.py`, `wt_validation.py` (poza nową regułą z §6), `optimizer.py`, `export_*.py`, cały frontend poza sekcją Komunikacja — bez zmian.
- Stare `bsp_zones()`, `_build_corridor()`, `_slice_apartments()`, `_cut_cell()` — usunięte, zastąpione przez `circulation.py`+`unit_mix.py`. `concave_vertices()`, `corner_cage()`, `split_polygon_by_edge()` (naprawiony) — zostają w `bsp.py`, nadal używane przez nowy kod.
- Testy referencyjne dzisiejszych bugów (6×30m → 50m², CW-winding azimuth, wklęsły U/L-kształt) przechodzą na nowy silnik jako regresja.

## 10. Co świadomie NIE jest w zakresie

- Podział mieszkań na pokoje (Finch Moduł 4) — decyzja użytkownika, osobne zadanie w przyszłości.
- Pełna dekompozycja dowolnych wielokątów wypukłych nie-prostokątnych (np. skośny czworokąt po ekstremalnej edycji wierzchołka) — `rectangle_decompose` obsługuje realne wklęsłości (główne źródło dzisiejszych bugów), nie każdy możliwy kształt geometryczny. Udokumentowane ograniczenie, nie cichy błąd.
- Windy / szyby windowe — nowa funkcja, nie próg walidacyjny dla istniejącej klatki.
- Zmiana progów Polish WT (§64, §68, §58 itd.) na wartości z Finch — te zostają Polskim prawem budowlanym, Finch wpływa tylko na ALGORYTM, nie na obowiązujące normy.
