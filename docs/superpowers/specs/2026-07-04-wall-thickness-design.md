# Grubość ścian — silnik geometrii + rysowanie + powierzchnia netto

**Data:** 2026-07-04
**Status:** zaakceptowany przez użytkownika ("wszystko ok, działaj")

## 1. Problem

Dziś każda krawędź poligonu (obrys, granica między mieszkaniami, korytarzem,
klatką) ma zerową grubość — ściany nie istnieją geometrycznie. Powierzchnia
mieszkania to po prostu `polygon.area`, czyli powierzchnia "na osiach", nie
rzeczywista powierzchnia użytkowa (netto). Użytkownik: *"ściana zewnętrzna
(czyli obrys) ma mieć 40cm grubości, oś ściany ustawiona wewnątrz ściany
10cm od wewnętrznego lica, ściany wewnętrzne po 20cm grubości, oś ścian
wewnątrz na środku"*.

## 2. Zakres tej fazy

Ustalone w rozmowie (patrz §7 dla pełnej mapy odłożonych tematów):

**W zakresie:**
- Nowy moduł obliczający powierzchnię netto (po odjęciu grubości ścian) dla
  dowolnej istniejącej komórki (mieszkanie, korytarz, klatka).
- Rysowanie realnej grubości ścian na płótnie.
- Wystawienie powierzchni netto tam, gdzie użytkownik może ją zobaczyć
  (etykieta na zaznaczonym/najechanym mieszkaniu — patrz §5.3).

**Świadomie POZA zakresem tej fazy** (silnik tylko DOKŁADA nową, pochodną
warstwę — nie zmienia niczego, co dziś istnieje):
- WT §94 ust.1 (min. powierzchnia mieszkania, 25m² — to JEDYNA rzecz, którą
  faktycznie reguluje ten przepis) nadal liczone na osiach, jak dziś.
  Reguła nie wie o ścianach.
- `MIN_ROOM_WIDTH_M = 2.4` (dziś błędnie oznaczone w kodzie jako "WT §94
  ust.2") to NIE jest wymóg WT — to była własna wiedza projektowa
  użytkownika, nie przepis. Poprawka tej fałszywej cytaty w kodzie to
  osobna, szybka sprawa (patrz §9), nie część tej fazy.
- `unit_mix.py`'s `fit_program_to_rectangles()` nadal celuje w `min_area_m2`
  na osiach — nie dokłada kompensacji za przyszłe skurczenie do netto.
- `corridor_width_m` **pozostaje wymiarem osiowym bez zmian** w tej fazie —
  patrz §6 dla wyjaśnienia tej świadomej niespójności z wcześniejszą decyzją
  "corridor_width_m = w świetle". Wymiary klatki (`CAGE_WIDTH_M`/
  `CAGE_DEPTH_M`) NIE są tu wyjątkiem — patrz poprawka w §6.
- Analiza słoneczna (`solar_analysis.py`) nadal wykrywa fasady na
  krawędziach-osiach, nie na rzeczywistym licu zewnętrznym.
- Eksport PDF/DXF — nie dodaję tam nowych pól w tej fazie.

## 3. Kluczowa obserwacja geometryczna

Dobrane przez użytkownika liczby (40cm zewn. z podziałem 10/30cm, 20cm
wewn. z podziałem 10/10cm) dają jedną, jednolitą regułę: **każda własna
krawędź komórki (mieszkania/korytarza/klatki) jest dokładnie 10cm od osi
do lica wewnętrznego** — dla ściany zewnętrznej wprost z definicji
użytkownika, dla wewnętrznej też (20cm ÷ 2 = 10cm z każdej strony osi).

Wynika z tego:

```
netto(komórka) = komórka.buffer(-0.10, join_style="mitre")
```

Jedna operacja Shapely, bez własnej logiki przesuwania krawędzi
pojedynczo. `join_style="mitre"` (ostre narożniki), bo geometria w tym
projekcie jest w większości prostokątna po `rectangle_decompose()`.

Pasy ścian do narysowania — też gotowymi operacjami Shapely:

```python
exterior_envelope = footprint.buffer(0.30)          # lico zewnętrzne
interior_envelope = footprint.buffer(-0.10)          # lico wewnętrzne obrysu
exterior_wall_band = exterior_envelope.difference(interior_envelope)
interior_wall_bands = interior_envelope.difference(
    unary_union([netto(c) for c in wszystkie_komórki])
)
```

`wszystkie_komórki` = wszystkie `ApartmentCell.polygon` + `circulation_geometry`
(korytarz+klatka jako jeden zunifikowany kształt — między klatką a
korytarzem nie rysujemy ściany, tak jak dziś nie ma między nimi granicy;
to architektonicznie sensowne, lobby klatki zwykle otwiera się na korytarz).
**Świadomie wyklucza `LayoutResult.leftover`** (niezagospodarowana
resztka) — bez ściany dookoła, więc wizualnie widać ją jako "dziurę" bez
konturu, co jest pożądane (sygnalizuje, że ten obszar wymaga uwagi, a nie
jest prawdziwym pomieszczeniem).

## 4. Nowy moduł: `backend/services/wall_geometry.py`

```python
WALL_EXTERIOR_THICKNESS_M = 0.40
WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M = 0.10  # -> axis-to-exterior-face = 0.30
WALL_INTERIOR_THICKNESS_M = 0.20  # oś na środku, 0.10 z każdej strony
NET_SHRINK_M = 0.10  # wspólna stała z §3 -- ten sam dystans dla obu typów ścian

def net_polygon(polygon: Polygon) -> Polygon:
    """Powierzchnia netto (w świetle ścian) -- spec §3. Zwraca pustą
    geometrię (nie None, nie wyjątek) dla komórek zbyt małych, żeby
    przetrwać skurczenie o 10cm z każdej strony -- wywołujący sprawdza
    `.is_empty`, tak jak przy innych operacjach Shapely w tym projekcie."""

def exterior_wall_band(footprint: Polygon) -> Polygon:
    """Pas ściany zewnętrznej wzdłuż całego obrysu -- spec §3."""

def interior_wall_bands(footprint: Polygon, cells: list[Polygon]) -> Polygon:
    """Pasy ścian wewnętrznych między wszystkimi podanymi komórkami
    (i między komórkami a licem wewnętrznym obrysu) -- spec §3."""
```

Moduł jest czysto obliczeniowy — nie zależy od `layout.py`/`circulation.py`
i nie jest przez nie wywoływany w środku generowania (patrz §2: silnik
istniejący zostaje nietknięty). Wywoływany osobno, na już-gotowym
`LayoutResult`, tam gdzie potrzebna jest wizualizacja/raport.

## 5. Zmiany w istniejącym kodzie

### 5.1 `ApartmentCell` (`services/layout.py`)

Nowe pole, analogicznie do `area_tolerance_exceeded`:

```python
    net_area_m2: float = 0.0
    """Powierzchnia w świetle ścian (wall_geometry.net_polygon(polygon).area)
    -- spec 2026-07-04 wall-thickness §3. Domyślnie 0.0 dla ścieżek, które
    jej nie liczą (np. ręczna edycja mieszkania przed ponownym przeliczeniem)."""
```

Wypełniane w `unit_mix.py`'s `fit_program_to_rectangles()` przy tworzeniu
każdej `ApartmentCell` — jedna dodatkowa linia (`net_area_m2=wall_geometry.
net_polygon(cell_poly).area`) obok istniejącego wypełniania
`area_tolerance_exceeded`.

### 5.2 API (`api/v1/endpoints/layout.py`)

`ApartmentResult` (response model) zyskuje `net_area_m2: float` obok
istniejącego `area_m2`. Wypełniane z `ApartmentCell.net_area_m2` w
`layout_result_to_response()`.

Nowe pole w `LayoutGenerateResponse`: `wall_bands: list[dict]` — GeoJSON
poligonów pasów ścian (`exterior_wall_band` + `interior_wall_bands`,
połączone w jedną listę części przez `_decompose_to_polygons` — helper już
istnieje w tym pliku), liczone raz w `layout_result_to_response()` z gotowego
`LayoutResult` (footprint + apartments + circulation_geometry).

### 5.3 Frontend (`CanvasEditor.tsx`)

- Nowa warstwa rysująca `wall_bands` jako wypełnione kształty (kolor zbliżony
  do konturu obrysu, np. `canvasColors.outline` z niską nieprzezroczystością)
  — pod istniejącymi warstwami mieszkań/korytarza/klatki, żeby ściany
  wizualnie "otaczały" już rysowane kształty zamiast je przesłaniać.
- Etykieta powierzchni netto na zaznaczonym mieszkaniu (`selectedApartmentId`)
  — mały tekst przy środku poligonu, format `"{net_area_m2.toFixed(1)} m² netto"`,
  widoczny tylko gdy `selectedApartmentId === apt.id` (nie na każdym
  mieszkaniu naraz, żeby nie zaśmiecać rysunku — spójne z tym, że dziś też
  tylko zaznaczone mieszkanie ma wyróżniony kontur).

## 6. Klatka DOSTAJE przeliczenie na w świetle teraz; korytarz — nie

Poprawka użytkownika: *"z klatką to nie jest tak jak z korytarzem, powinniśmy
doliczyć 20cm ściany od podanych wymiarów na zewnątrz"*.

Matematyka jest identyczna dla obu (§3: każda własna krawędź komórki to
10cm od osi do lica — więc żądany wymiar w świetle + 20cm z dwóch stron =
potrzebny rozstaw osi, niezależnie od tego czy dana strona styka się z
elewacją czy z sąsiadem). Różnica jest w tym, GDZIE trzeba to wpiąć:

- **Klatka**: `CAGE_WIDTH_M`/`CAGE_DEPTH_M` (`services/circulation.py`) to
  dwie stałe modułowe konsumowane wprost przez `_place_cage_by_mode`/
  `_corner_cage_convex`/`_centered_cage`/`_edge_cage` jako gotowy rozmiar
  prostokąta — same funkcje umieszczające klatkę nie wiedzą i nie muszą
  wiedzieć, że to teraz wymiar "w świetle + zapas na ścianę". **Robimy to w
  tej fazie**: podane w spec 2026-07-03 (staircase-cage-rectangle) 4.0×5.5m
  to wymiary W ŚWIETLE; stałe w kodzie rosną o 20cm każda:
  `CAGE_WIDTH_M = 4.2`, `CAGE_DEPTH_M = 5.7`. Zero zmian w logice
  umieszczania — tylko dwie liczby.
- **Korytarz**: `corridor_width_m` jest konsumowane WEWNĄTRZ
  `_build_corridor()`/`_corridor_centerline()`, funkcji, które są
  centralnym elementem kolejnego projektu ("dopracowanie lokalizowania
  klatek i korytarzy"). Zmiana tu oznaczałaby dotykanie logiki, którą i tak
  zaraz będziemy przerabiać — zostaje na osiach, przeliczenie na w świetle
  dołączymy do tamtego projektu (`żądana_szerokość_w_świetle + 2 *
  NET_SHRINK_M` przy budowaniu rozstawu osi, ten sam wzór).

## 6a. Zmiana w `services/circulation.py`

```python
CAGE_WIDTH_M = 4.2   # było 4.0 -- teraz to rozstaw osi (4.0m w świetle + 20cm ściany, spec 2026-07-04 §6)
CAGE_DEPTH_M = 5.7   # było 5.5 -- analogicznie
```

Test `test_cage_constants_match_spec` (z planu 2026-07-03) trzeba
zaktualizować na nowe wartości — to jedyny test, który wprost pinuje te
liczby (sprawdzone: `backend/tests/test_circulation.py`).

## 7. Mapa odłożonych tematów (dla pamięci, nie część tego planu)

Ustalona kolejność prac po tej fazie:
1. **Ta faza:** ściany (ten dokument).
2. Jakość lokalizowania klatek i korytarzy — w tym: wiele klatek + suwak
   liczby klatek, dodawanie punktów do osi korytarza podczas edycji, oraz
   przeliczenie `corridor_width_m`/wymiarów klatki na w świetle (§6).
3. Jakość dzielenia powierzchni budynku na mieszkania.
4. Reorganizacja paska bocznego: usunięcie zdublowanych sekcji Słońce/
   Optymalizacja z zakładki "Układ" (zostają tylko na własnych zakładkach),
   nowy prawy pasek boczny (bilans powierzchni, spis mieszkań z metrażem i
   nasłonecznieniem), lewy pasek zostaje z aktywnymi kontrolkami.
5. Odłożone bez ustalonej kolejności: WT (przeliczenie na netto), analiza
   słoneczna (fasady na licu, nie osi), lokalizacja geograficzna/optymalizator
   (zależne od słońca).

## 8. Testy

Backend (`backend/tests/test_wall_geometry.py`, nowy plik):
- `net_polygon()` na prostokącie: sprawdza dokładny wynikowy `bounds`
  (skurczenie o 0.10 z każdej strony, nie o dowolną wartość).
- `net_polygon()` na komórce zbyt małej (np. 15×15cm) zwraca pustą
  geometrię, nie wyjątek.
- `exterior_wall_band()`: pole = obwód obrysu × 0.40 (w przybliżeniu, dla
  prostego prostokąta gdzie da się to policzyć wprost).
- `interior_wall_bands()`: dla dwóch sąsiadujących prostokątów (dzielących
  krawędź) sprawdza, że powstały pas ściany ma szerokość dokładnie 0.20m
  między ich netto-poligonami.

Frontend: ręczna weryfikacja Playwright — wygenerować układ, sprawdzić
wizualnie że ściany są rysowane z realną grubością, zaznaczyć mieszkanie i
potwierdzić etykietę netto różną od (mniejszą niż) powierzchni na rysunku
konturu.

Backend (`test_circulation.py`, aktualizacja istniejącego):
- `test_cage_constants_match_spec` zmienia oczekiwane wartości na 4.2/5.7
  (§6a) — bez tego test i tak by czerwienił się po zmianie stałych, ale
  zapisuję explicite, żeby nie zgadywać przy implementacji.

## 9. Poprawka fałszywej cytaty WT w kodzie (osobna, szybka sprawa)

Znalezisko przy okazji tej rozmowy: `backend/services/wt_validation.py:31`
ma `MIN_ROOM_WIDTH_M = 2.4  # §94 ust. 2` — użytkownik potwierdza, że
prawdziwy §94 reguluje WYŁĄCZNIE minimalną powierzchnię mieszkania (25m²,
ust.1); nie ma żadnego "ust.2" o szerokości pokoju. Wartość 2.4m to własna
wiedza projektowa użytkownika, nie przepis WT — dokładnie ten sam wzorzec
błędu co wcześniej znaleziony i poprawiony `MIN_CAGE_FACADE_CONTACT_M`
(patrz pamięć projektu: fabrykowanie §-cytat dla heurystyk projektowych).

**To NIE jest część tej fazy** (WT jest w §7 punkt 5, odłożone) — ale jest
to prosta, izolowana poprawka nazewnictwa (nie logiki): zmienić kod
`§94 ust.2` na `code="heurystyka"` (wzorem istniejącego
`MIN_CAGE_FACADE_CONTACT_M`/`_rule_cage_facade_contact`), zaktualizować
komentarz przy stałej, bez zmiany progu 2.4m ani logiki porównania.
Dotyczy `wt_validation.py` (rule `_rule_room_width`) oraz zduplikowanej
stałej `MIN_ROOM_WIDTH_M` w `apartment_validation.py`. Zostawiam to jako
osobny, mały task do wykonania przy okazji tej fazy (nie wymaga własnego
brainstormu — to czysta poprawka etykiety, nie projektowa decyzja), ale
zaznaczony tu osobno, żeby nie ginął w większym planie ścian.
