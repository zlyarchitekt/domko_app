# Korytarz jako edytowalna linia środkowa — projekt

**Data:** 2026-07-03
**Status:** zaakceptowany przez użytkownika ("pasuje, działaj")
**Powiązane:** `docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md` (Etap 1 `place_circulation()`)

## 1. Problem

Zgłoszenie użytkownika (uwaga #3 z 2026-07-02):

> czemu podczas ustawiania komunikacji pojawia się tylko jedna klatka i zero
> korytarzy? powinno być tak, że pojawia się korytarz, jest on zbudowany jako
> linia z punktami w narożnikach, które można edytować, zaznaczony jest offset
> w obu kierunkach, żeby korytarz miał szerokość zgodnie z wpisanym
> parametrem. 20m od klatki linia środkowa korytarza powinna zmienić kolor,
> żeby informować, że przekraczamy maksymalne wartości.

Dzisiejszy stan (`services/circulation.py`): `place_circulation()` poprawnie
generuje korytarz per-strefa (`_build_corridor()`), ale frontend renderuje go
wyłącznie jako wypełniony prostokąt, przesuwany w całości jako sztywna bryła
(`edit-circulation` Group w `CanvasEditor.tsx:515-555`). Nie istnieje żadna
reprezentacja linii środkowej, więc nie ma czego edytować punkt-po-punkcie i
nie ma jak pokazać przekroczenia dopuszczalnej odległości do klatki kolorem.

## 2. Zakres

W zakresie:
- Backend: obliczenie połączonej linii środkowej korytarza (per strefa +
  łączenie stref), klasyfikacja jedno-/dwutraktowa per odcinek, odległość
  wzdłuż linii od najbliższej klatki, nowy endpoint do przeliczania po edycji.
- Frontend: nakładka kolorowej linii środkowej na istniejący wypełniony
  prostokąt korytarza, przeciąganie wierzchołków linii, przeliczanie po
  puszczeniu myszy.
- Korekta wartości granicznej §58 ust.4 (jednostronna) z 30m na 20m + nowa
  wartość dla dwustronnej (40m) — patrz §7.

Poza zakresem (świadomie odłożone, nie są potrzebne do spełnienia zgłoszenia):
- Zmiana szerokości korytarza przez przeciąganie krawędzi offsetu (offset
  pozostaje sterowany wyłącznie polem "Szerokość korytarza (m)" w
  `CirculationSection.tsx`, tak jak dziś).
- Rozszerzenie istniejącej reguły WT §58 ust.4 (`_rule_max_corridor_distance`,
  odległość Dijkstra mieszkanie→klatka) o klasyfikację jedno-/dwutraktową —
  patrz §7, świadomie odłożone jako osobna praca.
- Straight-skeleton / medial-axis dla obrysów wklęsłych — odrzucone wcześniej
  w tej sesji jako zbyt kruche; łączenie odcinków przez najbliższe końce
  (§3.2) jest prostsze i wystarczające dla prostokątnych stref z
  `rectangle_decompose()`.

## 3. Backend

### 3.1 Linia środkowa per strefa

`_build_corridor()` (circulation.py:159-193) już liczy `mid_y`/`mid_x` — środek
szerokości korytarza wzdłuż dłuższego boku strefy — zanim zwróci wypełniony
prostokąt. Dodajemy nową funkcję zwracającą tę samą oś jako 2-punktowy
odcinek zamiast (albo obok) prostokąta:

```python
def _corridor_centerline(polygon: Polygon, width: float, cage_polygon: Polygon | None = None) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Odcinek środkowy korytarza strefy — ta sama oś co _build_corridor(),
    zwrócona jako 2 punkty zamiast wypełnionego prostokąta. None jeśli
    strefa zbyt mała, żeby zmieścić korytarz o zadanej szerokości."""
```

Logika identyczna z `_build_corridor()` do obliczenia `mid_x`/`mid_y` (ten sam
kod wyrównania do pozycji klatki), ale zwraca
`((minx, mid_y), (maxx, mid_y))` (strefa pozioma) albo
`((mid_x, miny), (mid_x, maxy))` (strefa pionowa) zamiast prostokąta. Zwraca
`None` gdy `width >= min(w, h)` (korytarz nie mieści się w strefie — ten sam
warunek co dzisiejsze `corridor.intersection(polygon)` dający pusty wynik).

`_build_corridor()` pozostaje bez zmian (nadal używany do wypełnionego
prostokąta pod spodem) — `_corridor_centerline()` to nowa, równoległa funkcja
using tę samą logikę wyrównania, nie refaktor istniejącej.

### 3.2 Łączenie odcinków stref w jedną ścieżkę

Każda strefa z `rectangle_decompose()` ma własny 2-punktowy odcinek. Łączymy
je w jedną połączoną ścieżkę (zaakceptowane w brainstormingu: "Połączona
ścieżka przez cały budynek") metodą najbliższych końców — NIE
straight-skeleton (odrzucone wcześniej jako zbyt kruche dla wklęsłych
kształtów; tu nie jest nawet potrzebne, bo `rectangle_decompose()` już daje
prawie-prostokątne strefy):

```python
def _join_centerlines(
    segments: list[tuple[tuple[float, float], tuple[float, float]]]
) -> list[tuple[float, float]]:
    """Łączy odcinki centerline sąsiednich stref w jedną łamaną, zaczynając
    od pierwszego odcinka i za każdym razem dołączając odcinek, którego
    najbliższy koniec leży najbliżej bieżącego końca ścieżki. Zwraca listę
    punktów (nie odcinków) — kolejne pary tworzą łamaną."""
```

Algorytm (zachłanny nearest-neighbor, O(n²) — liczba stref w praktyce < 20,
więc wydajność nie jest problemem):
1. Start: punkty pierwszego segmentu jako początek ścieżki.
2. Dopóki są niepołączone segmenty: znajdź segment, którego bliższy koniec
   ma najmniejszą odległość euklidesową do ostatniego punktu ścieżki; dołącz
   go (w kolejności bliższy→dalszy koniec) do ścieżki.
3. Segmenty w strefach zbyt małych na korytarz (`_corridor_centerline()`
   zwróciło `None`) są pomijane — nie przerywają łączenia, po prostu ta strefa
   nie ma własnego odcinka.

Wynik: pojedyncza łamana (`list[tuple[float,float]]`) reprezentująca całą
sieć korytarzy budynku. Rozgałęzienia (więcej niż 2 strefy stykające się w
jednym punkcie) nie są w zakresie tego MVP — nearest-neighbor da wtedy jedną
sensowną ścieżkę (nie graf), co wystarcza dla typowych klatkowców/galeriowców
w typologies.md. Rozgałęzione siatki korytarzy (np. duży punktowiec z
korytarzem w kształcie plus) są rzadkością w tym typie zabudowy i mogą być
dodane później jako graf, jeśli się pojawią w praktyce.

### 3.3 Klasyfikacja jedno-/dwutraktowa per odcinek

Zaakceptowane w brainstormingu: klasyfikacja geometryczna, NIE zależna od
danych Etapu 2 (mieszkania jeszcze nie istnieją, gdy `place_circulation()`
działa). Dla każdego odcinka centerline sprawdzamy, czy po obu stronach
(prostopadle do kierunku odcinka, w odległości `MIN_ROOM_WIDTH_M` — istniejąca
stała WT z `wt_validation.py`, wymóg minimalnej głębokości pomieszczenia) w
obrębie strefy zostaje wystarczająco dużo miejsca na mieszkanie:

```python
def _classify_segment_loading(
    zone_polygon: Polygon, segment: tuple[tuple[float, float], tuple[float, float]], corridor_width: float
) -> str:
    """Zwraca "single" albo "double". Sprawdza, po której stronie odcinka
    (w strefie, po odjęciu pasa korytarza o szerokości corridor_width)
    dostępna głębokość >= MIN_ROOM_WIDTH_M z wt_validation.py. "double" tylko
    jeśli obie strony spełniają warunek; w przeciwnym razie "single"."""
```

Implementacja: zbuduj dwa prostokąty-sondy (po `MIN_ROOM_WIDTH_M` głębokości,
na długości odcinka) po obu stronach osi, sprawdź
`probe.intersection(zone_polygon).area > probe.area * 0.9` dla każdego (próg
0.9 spójny z istniejącym wzorcem `cage_polygon.area > zone.polygon.area * 0.9`
w `place_circulation()`).

### 3.4 Odległość wzdłuż linii do najbliższej klatki

Zaakceptowane: długość łuku (arc-length) wzdłuż połączonej ścieżki, NIE
Dijkstra po siatce (ta metoda zarezerwowana dla istniejącej reguły WT §58
mieszkanie→klatka w `wt_validation.py`, gdzie siatka jest potrzebna, bo
ścieżka mieszkanie→korytarz→klatka nie leży na jednej znanej z góry linii).
Tutaj ścieżka JEST już znana (połączona centerline z §3.2), więc:

```python
def _distances_along_centerline(
    path: list[tuple[float, float]], cage_points: list[tuple[float, float]]
) -> list[float]:
    """Dla każdego wierzchołka `path` zwraca odległość (długość łuku wzdłuż
    `path`) do najbliższego punktu w `cage_points` (rzutowanego na
    najbliższy punkt na `path`). Jeśli `cage_points` puste, zwraca listę
    float('inf') (brak klatki -> brak odniesienia, patrz F2-04's istniejący
    wzorzec "Brak klatki" w _rule_max_corridor_distance)."""
```

Punkt odniesienia klatki: centroid każdego `cage_polygon` z
`CirculationResult.cage_polygons`, rzutowany na najbliższy punkt na `path`
(via `shapely.ops.nearest_points` — już zaimportowane w `wt_validation.py`,
tu importowane analogicznie w `circulation.py`).

### 3.5 Nowa struktura wyniku

```python
@dataclass
class CorridorCenterlineSegment:
    """Jeden odcinek połączonej linii środkowej korytarza."""
    points: tuple[tuple[float, float], tuple[float, float]]
    loading: str  # "single" | "double"
    distance_start_m: float  # odległość wzdłuż linii do najbliższej klatki, punkt początkowy
    distance_end_m: float
    max_distance_m: float  # 20.0 (single) albo 40.0 (double) — patrz §7
    exceeds_max: bool  # True jeśli max(distance_start_m, distance_end_m) > max_distance_m
```

`CirculationResult` (circulation.py:212-222) zyskuje nowe pole:

```python
    centerline: list[CorridorCenterlineSegment] = field(default_factory=list)
```

`place_circulation()` wypełnia je: dla każdej strefy woła
`_corridor_centerline()`, łączy przez `_join_centerlines()`, klasyfikuje przez
`_classify_segment_loading()`, liczy odległości przez
`_distances_along_centerline()`, składa listę `CorridorCenterlineSegment`.
Strefy bez korytarza (za małe) nie generują odcinka — `centerline` może być
krótsza niż `len(zones)`.

### 3.6 Nowy endpoint: przeliczanie po edycji

Zaakceptowane: przeliczanie na serwerze dopiero po puszczeniu myszy (nie przy
każdym ruchu). Frontend podczas przeciągania porusza punktami tylko wizualnie
(bez requestu); po `onDragEnd` woła nowy endpoint z edytowaną linią.

```python
class CenterlineSegmentInput(BaseModel):
    points: list[list[float]] = Field(..., min_length=2, max_length=2)

class ReshapeCirculationRequest(BaseModel):
    footprint: list[list[float]] = Field(..., min_length=3)
    centerline: list[CenterlineSegmentInput] = Field(..., min_length=1)
    corridor_width_m: float = Field(..., gt=0)
    cage_geometries: list[dict] = Field(default_factory=list)  # GeoJSON polygons, z istniejącego CirculationResponse.cage_geometries

class ReshapeCirculationResponse(BaseModel):
    circulation_geometry: dict | None
    remainder: dict
    centerline: list[dict]  # serializowane CorridorCenterlineSegment (points/loading/distance_start_m/distance_end_m/max_distance_m/exceeds_max)

@router.post("/circulation/reshape", response_model=ReshapeCirculationResponse)
def reshape_circulation_endpoint(request: ReshapeCirculationRequest):
    """Przelicza geometrię korytarza (bufor wokół edytowanej linii środkowej,
    szerokość = corridor_width_m) + klasyfikację/odległości segmentów, po
    edycji wierzchołków przez użytkownika (F2-04-bis)."""
```

Implementacja `reshape_circulation_endpoint`:
1. Zbuduj geometrię korytarza jako `buffer` każdego odcinka linii o
   `corridor_width_m / 2` (płaskie zakończenia — `cap_style="flat"` w
   Shapely), zunifikowane (`unary_union`) i przycięte do `footprint`
   (`shapely.buffer` + `intersection`, analogicznie do istniejącego wzorca
   `corridor.intersection(polygon)` w `_build_corridor()`).
2. `remainder = footprint.difference(unary_union([circulation_geometry] + cage_polygons))`.
3. Klasyfikacja per odcinek: `_classify_segment_loading()`, ale liczona
   względem `footprint` zamiast pojedynczej strefy (edytowana linia już nie
   jest przywiązana do stref z `rectangle_decompose()`) — sonda po obu
   stronach sprawdzana przez `probe.intersection(footprint.difference(circulation_geometry))`.
4. Odległości: `_distances_along_centerline()` na edytowanej ścieżce
   (spłaszczonej z `request.centerline` w kolejność punktów — kolejne
   segmenty muszą się stykać końcami; jeśli nie stykają się dokładnie,
   traktuj każdy odcinek segmentu niezależnie i licz odległość od jego
   własnych końców, żeby uniknąć crasha na nieciągłej edycji użytkownika).

To NOWY endpoint, nie modyfikacja `place_circulation()` — pierwsze
wygenerowanie linii (przycisk "Umieść korytarz i klatkę") nadal używa
`POST /layout/circulation` z §3.5; `POST /layout/circulation/reshape` jest
wywoływany wyłącznie po edycji.

## 4. Frontend

### 4.1 Renderowanie

W `CanvasEditor.tsx`, wewnątrz istniejącego bloku `edit-circulation`
(linie 515-555) i w trybie podglądu (poza edycją — linie 494-512), nakładamy
kolorową linię środkową NA ISTNIEJĄCY wypełniony prostokąt korytarza
(prostokąt pozostaje, reprezentuje offset/szerokość zgodnie z uwagą
użytkownika: "zaznaczony jest offset w obu kierunkach, żeby korytarz miał
szerokość zgodnie z wpisanym parametrem"):

```tsx
{state.circulationResult?.centerline?.map((seg, i) => (
  <Line
    key={`centerline-${i}`}
    points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
    stroke={seg.exceeds_max ? "#ef4444" : "#22c55e"}
    strokeWidth={3 / scale}
  />
))}
```

Kolor: zielony (`#22c55e`) w normie, czerwony (`#ef4444`) przy
`exceeds_max === true` — spójne z istniejącą paletą statusów w
`STATUS_COLORS` (CanvasEditor.tsx, używane dla mieszkań).

### 4.2 Przeciąganie wierzchołków

Nowy tryb edycji analogiczny do istniejącego `edit-vertices` (obrys) —
każdy punkt styku odcinków centerline renderowany jako mały przeciągalny
`Circle`, tak jak wierzchołki obrysu. Podczas przeciągania (`onDragMove`):
tylko lokalna aktualizacja pozycji punktu w stanie klienckim (bez requestu do
backendu — kolor odcinka NIE przelicza się w locie, zaakceptowane w
brainstormingu: "Przelicz po puszczeniu myszy"). Po `onDragEnd`: wywołanie
`POST /layout/circulation/reshape` z pełną edytowaną linią; odpowiedź
nadpisuje `state.circulationResult.circulation_geometry`, `.remainder`,
`.centerline` (kolory/odległości/geometria korytarza wszystkie na raz, w
jednym requeście — unika stanu pośredniego, gdzie linia już się przesunęła
ale kolor jeszcze nie).

Wzorzec `e.cancelBubble = true` na `onDragStart`/`onDragEnd` (wymagany na tej
sesji dla każdego przeciąganego elementu wewnątrz Stage — patrz Konva
event-bubbling bug naprawiony wcześniej w tej samej sesji) stosowany
identycznie jak w pozostałych 4 miejscach `CanvasEditor.tsx`.

### 4.3 Stan sesji

`SessionContext.tsx`:
- `CirculationResult` (typ frontendowy, w `lib/api.ts`) zyskuje pole
  `centerline: CorridorCenterlineSegmentDTO[]` (kształt odpowiadający
  backendowemu `CorridorCenterlineSegment`, serializowany jak reszta
  `CirculationResponse`).
- Nowa akcja `RESHAPE_CIRCULATION` (analogiczna do istniejącej
  `TRANSLATE_CIRCULATION`) — reducer podmienia
  `circulationResult.{circulation_geometry,remainder,centerline}` wynikiem z
  `/circulation/reshape`.
- Nowy callback `runReshapeCirculation(editedCenterline)` w
  `SessionContextValue`, wołający `api.reshapeCirculation(...)` (nowa funkcja
  w `lib/api.ts`, wzorowana na istniejącym `placeCirculation()`).

## 5. Przepływ końcowy (użytkownik)

1. Użytkownik klika "Umieść korytarz i klatkę" (istniejący przycisk,
   `CirculationSection.tsx:122-129`) → `POST /layout/circulation` →
   `circulationResult` (teraz z `centerline`) → canvas renderuje wypełniony
   prostokąt + kolorową linię środkową.
2. Użytkownik włącza "Przesuń komunikację" (istniejący tryb
   `edit-circulation`) — bez zmian, nadal przesuwa całość jako sztywną bryłę.
3. **Nowość:** osobny tryb (nowy przycisk w `CirculationSection.tsx`, np.
   "Edytuj linię korytarza") pokazuje przeciągalne wierzchołki centerline z
   §4.2. Przeciągnięcie wierzchołka → po puszczeniu myszy → przeliczenie →
   canvas aktualizuje geometrię korytarza i kolor linii.
4. Segmenty przekraczające próg (20m jednotraktowy / 40m dwutraktowy od
   najbliższej klatki) są czerwone; w normie — zielone.

## 6. Testy

Backend (`test_circulation.py`, rozszerzenie istniejącego pliku z
18-taskowego planu z 2026-07-02):
- `_corridor_centerline()`: zwraca poprawny 2-punktowy odcinek dla strefy
  poziomej i pionowej; `None` gdy strefa za mała.
- `_join_centerlines()`: 3 odcinki z rozłącznymi końcami → jedna łamana w
  poprawnej kolejności (nearest-neighbor).
- `_classify_segment_loading()`: strefa z miejscem na mieszkania po obu
  stronach → `"double"`; strefa z miejscem tylko po jednej stronie (np. wzdłuż
  krawędzi obrysu) → `"single"`.
- `_distances_along_centerline()`: prosta ścieżka 3-punktowa, jedna klatka na
  końcu → odległości rosnące liniowo od klatki; brak klatek → `inf`.
- `place_circulation()`: `CirculationResult.centerline` niepuste dla
  standardowego prostokątnego footprintu z korytarzem; `exceeds_max=True`
  gdy sztucznie wymuszony długi footprint (> 20m single-traktowy).

Backend (`test_layout_circulation_endpoint.py`, rozszerzenie): `centerline`
obecne i serializowalne w odpowiedzi `POST /layout/circulation`.

Backend (nowy `test_layout_circulation_reshape_endpoint.py`):
- Edytowana linia → poprawna geometria korytarza (bufor + przycięcie do
  footprintu).
- Edytowana linia wydłużona ponad próg → `exceeds_max=True` na dotkniętym
  segmencie.
- Nieciągła edycja (segmenty się nie stykają) → endpoint nie crashuje, liczy
  per-segment.

Frontend: manualna weryfikacja Playwright (wzorzec z reszty sesji — dev
server + zrzuty ekranu) obu trybów (podgląd + edycja wierzchołków) w obu
motywach (dark/light), sprawdzająca kolor linii i że przeciąganie nie
odpala centrowania widoku (regresja Konva event-bubbling z tej samej sesji).

## 7. Korekta wartości granicznej §58 ust.4

Podczas brainstormingu, w odpowiedzi na pytanie czy nowa funkcja ma
reużywać istniejącą stałą `DEFAULT_MAX_CORRIDOR_DISTANCE_M = 30.0`
(`wt_validation.py:41`, dziś jedyna, bez rozróżnienia jedno-/dwutraktowy),
użytkownik odpowiedział konkretną korektą wartości: "jednostronny powinien
mieć 20m a dwustronny 40" — to nie jest wybór "reużyć czy nie", to korekta
merytoryczna wartości granicznej (ten sam wzorzec co wcześniejsza korekta
`MIN_CAGE_FACADE_CONTACT_M`, patrz `feedback_wt_no_cage_facade_requirement.md`
w pamięci projektu).

Decyzja (rozstrzygnięcie niejednoznaczności z brainstormingu, udokumentowana
tutaj zamiast dopytywać ponownie):

- `wt_validation.py`: `DEFAULT_MAX_CORRIDOR_DISTANCE_M` (jednostronna)
  zmieniana z `30.0` na `20.0`. Weryfikacja: wszystkie istniejące testy w
  `test_wt_validation.py` (`test_max_corridor_distance_rule_passes_for_
  reachable_apartment`, `test_corridor_distance_is_not_euclidean_for_l_shaped_
  corridor`) przekazują `max_corridor_distance_m=30.0` jawnie jako parametr
  (nie polegają na wartości domyślnej) — zmiana wartości domyślnej NIE psuje
  żadnego istniejącego testu.
- Nowa stała `MAX_CORRIDOR_DISTANCE_DOUBLE_LOADED_M = 40.0` w
  `wt_validation.py`, obok istniejącej (przemianowanej pośrednio przez
  komentarz — sama nazwa `DEFAULT_MAX_CORRIDOR_DISTANCE_M` zostaje
  niezmieniona, żeby nie łamać istniejących importów/wywołań, dokumentacja w
  docstringu doprecyzowana: "jednostronna (single-loaded)").
- **Świadomie poza zakresem:** istniejąca reguła WT §58 ust.4
  (`_rule_max_corridor_distance`, odległość Dijkstra mieszkanie→klatka) NIE
  jest rozszerzana o klasyfikację jedno-/dwutraktową w tym projekcie — nadal
  używa pojedynczego progu (`DEFAULT_MAX_CORRIDOR_DISTANCE_M`, teraz 20.0) dla
  wszystkich mieszkań niezależnie od tego, czy korytarz przy nich jest
  jedno- czy dwutraktowy. Efekt: mieszkania przy korytarzu dwutraktowym będą
  ocenianie nieco za surowo (limit 20m zamiast należnych im 40m) do czasu
  osobnej poprawki. Powód odłożenia: reguła Dijkstra liczy odległość
  mieszkanie→klatka (inny punkt odniesienia niż odcinek linii środkowej) i
  nie ma dziś dostępu do klasyfikacji jedno-/dwutraktowej strefy (ta wiedza
  istnieje tylko w Etapie 1, reguła WT działa na już wygenerowanym
  `LayoutResult` po Etapie 2). Rozszerzenie tej reguły to osobna, dobrze
  odizolowana praca — nie blokuje zgłoszenia użytkownika (edytowalna linia
  korytarza z kolorem), które dotyczy wyłącznie nowej wizualizacji.
  Zanotowane tu jawnie, żeby nie zgubić tego follow-upu.
- Nowe stałe `CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0` /
  `..._DOUBLE_LOADED_M = 40.0` w `circulation.py` (osobne od
  `wt_validation.py`'s stałych — różne moduły, różne miejsce w cyklu życia
  layoutu, ta sama wartość liczbowa nie uzasadnia współdzielenia importu
  między Etapem 1 (circulation.py) a walidacją post-Etap-2
  (wt_validation.py); duplikacja dwóch `float` stałych jest tańsza niż
  sprzężenie tych dwóch modułów).

## 8. Ryzyka / założenia

- `_join_centerlines()` zakłada, że graf sąsiedztwa stref jest ścieżką
  (każda strefa styka się z co najwyżej dwiema innymi w sensie ciągłości
  korytarza) — poprawne dla typologii z typologies.md używanych w tym
  projekcie (klatkowiec wzdłużny/narożny, punktowiec, galeriowiec,
  szeregowiec). Rozgałęzione siatki nie są testowane ani gwarantowane.
- Bufor `cap_style="flat"` w §3.6 może dać nieznacznie inną geometrię
  narożników niż oryginalny `_build_corridor()`'s wzajemnie prostopadłe
  prostokąty przy zakrętach ścieżki — akceptowalne, bo to nowa ścieżka
  (edytowana przez użytkownika), nie musi bit-a-bit odtwarzać
  automatycznego wyniku Etapu 1.
