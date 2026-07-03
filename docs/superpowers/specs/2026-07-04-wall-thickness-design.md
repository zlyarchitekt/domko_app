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
- WT §94 (min. powierzchnia/szerokość pokoju) nadal liczone na osiach, jak
  dziś. Reguła nie wie o ścianach.
- `unit_mix.py`'s `fit_program_to_rectangles()` nadal celuje w `min_area_m2`
  na osiach — nie dokłada kompensacji za przyszłe skurczenie do netto.
- `corridor_width_m` i wymiary klatki (`CAGE_WIDTH_M`/`CAGE_DEPTH_M`,
  4.0×5.5m) **pozostają wymiarami osiowymi bez zmian** w tej fazie — patrz
  §6 dla wyjaśnienia tej świadomej niespójności z wcześniejszą decyzją
  "corridor_width_m = w świetle".
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

## 6. Świadoma niespójność: `corridor_width_m` dalej osiowe

Wcześniej w tej rozmowie ustalone: `corridor_width_m` ma docelowo oznaczać
szerokość **w świetle** (użytkownik: *"1.5m = w świetle"*), z systemem
dokładającym połowę grubości ściany z każdej strony do rozstawu osi. **Ta
faza tego nie robi** — `_build_corridor()`/`_corridor_centerline()` w
`circulation.py` zostają nietknięte, `corridor_width_m` nadal jest
interpretowane jako rozstaw osi, tak jak dziś. Po dodaniu tej fazy,
faktyczna szerokość korytarza w świetle będzie o ok. 20cm mniejsza niż
wpisana wartość (ściana z każdej strony zjada po 10cm) — to samo dotyczy
wymiarów klatki (4.0×5.5m to nadal wymiary osiowe, nie w świetle).

**Dlaczego to świadomy wybór, nie przeoczenie:** przeliczenie osi na w
świetle dla korytarza/klatki wymaga wiedzy, KTÓRE boki stykają się z jakim
typem ściany (klatka w narożniku może stykać się z 2 elewacjami =
zewnętrzna 40cm, korytarz zawsze między dwoma mieszkaniami = wewnętrzna
20cm) — to jest dokładnie zakres kolejnego, osobnego projektu
("dopracowanie lokalizowania klatek i korytarzy"), który i tak już posiada
`_build_corridor`/`_place_cage_by_mode`. Robienie tego tutaj rozjeżdżałoby
się z ustaloną kolejnością prac. Ten silnik (`wall_geometry.py`) jest
napisany tak, żeby kolejny projekt mógł z niego skorzystać wprost (np.
`_build_corridor` policzy potrzebny rozstaw osi jako
`żądana_szerokość_w_świetle + 2 * NET_SHRINK_M`), ale samo dołożenie tej
logiki do `circulation.py` zostaje odłożone.

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
