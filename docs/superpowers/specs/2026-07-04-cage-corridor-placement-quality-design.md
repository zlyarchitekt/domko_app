# Klatki/korytarze: wiele klatek, edycja osi, korytarz w świetle — projekt

**Data:** 2026-07-04
**Status:** brainstorm, oczekuje zatwierdzenia

## 1. Problem

Projekt #2 z `project_roadmap_20260704.md` (memory), po zamknięciu fazy
grubości ścian. Trzy potwierdzone braki w `place_circulation()`/edycji
komunikacji:

1. **Zawsze dokładnie 1 klatka** niezależnie od wielkości budynku —
   `place_circulation()` (circulation.py:469-484) przerywa pętlę po strefach
   `break`-iem zaraz po umieszczeniu pierwszej klatki.
2. **Nie da się dodać punktu do osi korytarza podczas edycji** — tryb
   "Edytuj linię korytarza" (`edit-corridor-centerline`) pozwala dziś tylko
   przeciągać istniejące wierzchołki (CanvasEditor.tsx:749-797), nie wstawiać
   nowych.
3. **`corridor_width_m` to dziś oś-do-osi, nie w świetle** — `_build_corridor()`/
   `_corridor_centerline()` budują prostokąt dokładnie `corridor_width_m`
   szeroki, a interior_wall_bands (Wall Task 4) potraktuje ten sam prostokąt
   jako "komórkę" i odejmie `NET_SHRINK_M=0.10` z każdej strony — czyli
   `corridor_width_m=1.5` daje faktycznie **1.3m w świetle**. Klatka
   (`CAGE_WIDTH_M`/`CAGE_DEPTH_M`) dostała analogiczną poprawkę w Wall Task 3
   (§ wall-thickness spec §6); korytarz jeszcze nie.

## 2. Zakres

Trzy niezależne, ale powiązane zmiany w tym samym module (`circulation.py` +
`CanvasEditor.tsx`/`CirculationSection.tsx`). Bez zmian w:
- `subdivide_units()`/dzieleniu na mieszkania (Etap 2) — osobny projekt #3.
- WT-walidacji (`_classify_segment_loading()`'s `MIN_ROOM_WIDTH_M` próbka
  głębokości pozostaje jak dziś, heurystyka niezależna od tej zmiany).
- Kształtu/podziału wizualnego klatki (spec 2026-07-03) — tylko *liczba*
  klatek się zmienia, nie ich geometria.

## 3. Wiele klatek

### 3.1 Backend (`circulation.py`)

Nowy parametr `num_cages: int = 1` na `place_circulation()` i
`CirculationSpec` (layout.py). Pętla po `cage_zone_order` (circulation.py:470-484)
dziś:

```python
if cage_polygon is not None and cage_polygon.area > 0:
    circulation_geom = unary_union([circulation_geom, cage_polygon])
    cage_polygons.append(cage_polygon)
    local_cages[i] = cage_polygon
    break
```

Zmiana: usunięcie `break`, kontynuacja aż `len(cage_polygons) == num_cages`
lub wyczerpanie `cage_zone_order`. Kolejność priorytetu bez zmian (strefy z
wklęsłym narożnikiem oryginalnego obrysu najpierw). Brak błędu, gdy stref
jest mniej niż `num_cages` — po prostu tyle klatek, ile się zmieściło (ten
sam cichy-cap wzorzec co reszta modułu, np. `_corner_cage_convex`'s
`clipped.area > 1e-6` guard).

`CirculationSpec.num_cages: int = Field(default=1, ge=1)` — walidacja górnej
granicy NIE jest potrzebna (pętla i tak zatrzyma się na liczbie stref).

### 3.2 Frontend

`CirculationSpecInput` (api.ts) + `initialCirculation` (SessionContext.tsx)
gain `num_cages: number` (default 1). Nowy suwak w `CirculationSection.tsx`,
pod polem "Pozycja klatki": `<input type="range" min={1} max={8} ...>` z
etykietą "Liczba klatek: {N}". Górna granica 8 to arbitralny, hojny limit UI
(realne budynki z `rectangle_decompose()` rzadko dają >4-5 stref) — backend
i tak cicho przytnie do faktycznej liczby stref.

## 4. Dodawanie punktów do osi korytarza

Czysto frontendowe — `reshape_circulation()` (circulation.py:539) już
przyjmuje dowolną listę segmentów (`centerline_points`), więc wstawienie
nowego wierzchołka to tylko rozbicie jednego segmentu na dwa przed wywołaniem
istniejącego `runReshapeCirculation()`.

`onDblClick` na segmencie `<Line>` linii środkowej (CanvasEditor.tsx:725-733):
1. Konwersja pozycji kliknięcia (Konva pointer, world-space przez
   `worldToMeters`, wzorem istniejących handlerów przeciągania) na najbliższy
   punkt na odcinku `seg.points` (rzut ortogonalny, przycięty do `[0,1]`
   parametru odcinka — ten sam wzorzec co `LineString.project()` używane już
   w `_distances_along_centerline()`, tu liczony w TS bez Shapely).
2. Budowa nowej listy segmentów: znaleziony segment zastąpiony dwoma
   (`[p1, nowy]`, `[nowy, p2]`), reszta bez zmian.
3. `void runReshapeCirculation(newSegments)` — identyczne wywołanie jak
   istniejący `onDragEnd` na wierzchołkach (CanvasEditor.tsx:794).

Nowy wierzchołek jest natychmiast przeciągalny — wynika za darmo z istniejącej
pętli renderującej zdeduplikowane wierzchołki (CanvasEditor.tsx:739-748),
która iteruje po `state.circulationResult.centerline` zwróconym przez backend
po `runReshapeCirculation`.

Brak nowego przycisku/trybu — działa w istniejącym trybie
`edit-corridor-centerline`.

### 4.1 Usuwanie punktów

`onDblClick` na istniejącym wierzchołku (`<Circle>`, CanvasEditor.tsx:750-796
— dziś ma tylko `onDragStart`/`onDragMove`/`onDragEnd`) usuwa go z płaskiej
listy wierzchołków (`flat_path`, ten sam spłaszczony ciąg co budowany w
`reshape_circulation()`, circulation.py:566-568) i przebudowuje segmenty z
sąsiadujących punktów, po czym woła `runReshapeCirculation()` jak przy
dodawaniu/przeciąganiu.

**Guard: nie usuwać, gdy `flat_path.length <= 2`** — dwa punkty to jeden
segment, minimalna oś korytarza; usunięcie jednego zostawiłoby zerodługościowy
"korytarz" albo pojedynczy punkt bez geometrii. Przy `length === 2` dwuklik na
wierzchołku jest no-opem (żadnego wywołania `runReshapeCirculation`).

Konflikt zdarzeń: `<Circle>` już ma `onDragStart`/`onDragEnd` z
`e.cancelBubble = true` — `onDblClick` to osobny handler Konva, nie
koliduje z drag (dwuklik bez przeciągnięcia nie odpala `onDragMove`/
`onDragEnd`), więc nie wymaga dodatkowej logiki różnicującej "klik" od
"przeciągnięcie".

## 5. Korytarz w świetle (nie oś-do-osi)

Analogiczne do Wall Task 3 (`CAGE_WIDTH_M`/`CAGE_DEPTH_M` +20cm). Zmiana w
`_build_corridor()` i `_corridor_centerline()` (circulation.py:176-245):
budowany prostokąt ma szerokość `corridor_width_m + 2 * NET_SHRINK_M` (import
`from services.wall_geometry import NET_SHRINK_M`), zamiast `corridor_width_m`
wprost. Wywołania `half = width / 2.0` zamienione na
`half = (width + 2 * NET_SHRINK_M) / 2.0` w obu funkcjach (`width` = parametr
`corridor_width_m` przekazany przez wywołującego, nazwa bez zmian dla
zgodności z resztą pliku).

`reshape_circulation()` (circulation.py:539) buduje geometrię przez
`LineString(...).buffer(half, cap_style="flat")` — `half` tu też rośnie o
`NET_SHRINK_M` (bufor promienia = `corridor_width_m/2 + NET_SHRINK_M`, żeby
edytowana oś dawała ten sam efektywny prostokąt co `_build_corridor()`).

Etykieta UI (`CirculationSection.tsx:114`): "Szerokość korytarza (w świetle,
m)" zamiast "Szerokość korytarza (m)". Wartość domyślna `1.5` bez zmian —
oznacza teraz 1.5m w świetle (realnie budowany prostokąt: 1.7m oś-do-osi).

**Konsekwencja:** korytarze "zjadają" o 20cm więcej powierzchni niż dziś
(ta sama, świadomie zaakceptowana konsekwencja jak przy klatce w Wall Task 3,
patrz wall-thickness spec §5) — nie wymaga dalszej akcji.

## 6. Testy

- `test_circulation.py`: `place_circulation(..., num_cages=N)` zwraca
  `len(cage_polygons) <= N` i `== min(N, liczba stref zdolnych pomieścić klatkę)`
  dla N=1,2,3 na footprintach z wieloma strefami (np. L-shape → 2 strefy po
  `rectangle_decompose`).
- `test_circulation.py`: `_build_corridor()`/`_corridor_centerline()` z
  `corridor_width_m=1.5` dają prostokąt/oś o efektywnej szerokości 1.7m
  (bounds sprawdzone bezpośrednio), oraz że `net_polygon()` tego prostokąta
  (Wall Task 1's `wall_geometry.net_polygon`) ma szerokość ~1.5m (w granicach
  `join_style="mitre"` narożników) — potwierdza że "w świetle" faktycznie
  odpowiada obiecanej wartości po odjęciu ścian.
- `test_circulation.py`: `reshape_circulation()` z ręcznie rozbitym segmentem
  (symulacja dodania punktu) zwraca ten sam `circulation_geometry` co przed
  rozbiciem (rozbicie segmentu na dwa współliniowe nie powinno zmieniać
  geometrii bufora) — regresja na wypadek błędu w logice `half`.
- Playwright: dodać klatkę suwakiem →2, umieścić, potwierdzić wizualnie 2
  klatki; dwuklik na linii korytarza w trybie edycji, potwierdzić nowy
  przeciągalny wierzchołek; dwuklik na tym nowym wierzchołku, potwierdzić że
  zniknął; dwuklik na jednym z pozostałych 2 wierzchołków (oś z powrotem przy
  minimum), potwierdzić że NIC się nie usuwa (guard §4.1).

## 7. Świadomie poza zakresem

- Ręczny wybór, która strefa dostaje klatkę (§3.1 opcja B, odrzucona przez
  użytkownika na rzecz automatycznego przydziału wg priorytetu).
- Usuwanie wierzchołków osi korytarza (tylko dodawanie — usuwanie nie było
  proszone, odłożone jeśli okaże się potrzebne).
- Walidacja WT dla wielu klatek (np. maks. odległość do najbliższej klatki
  per mieszkanie) — `_distances_along_centerline()` już liczy odległość do
  najbliższej z `cage_points`, więc wielo-klatkowy przypadek działa od razu
  bez zmian, ale nowe reguły WT specyficzne dla >1 klatki nie są częścią
  tego projektu.
