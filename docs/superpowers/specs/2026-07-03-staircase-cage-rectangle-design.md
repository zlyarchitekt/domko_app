# Klatka schodowa jako prostokąt z wizualnym podziałem — projekt

**Data:** 2026-07-03
**Status:** zaakceptowany przez użytkownika ("mamy to! super")

## 1. Problem

Dzisiejsza klatka schodowa (`_place_cage_by_mode` w `services/circulation.py`, oraz
`corner_cage` w `services/bsp.py`) to zawsze **kwadrat** o boku `cage_size_m`
(pojedynczy skalar, per typologia uśredniony z `TypologyPreset.staircase_dims_m`
w `typology_presets.py`). Użytkownik: *"musimy trochę poprawić klatki schodowe...
klatka to prostokąt (więc podaje 2x wymiary) a nie kwadrat"* — kwadrat nie
odzwierciedla realnej geometrii klatki (biegi + spoczniki + winda), co wygląda
jak "ściema" (fikcja) na rzucie.

## 2. Zakres

**Czysto wizualne** (potwierdzone przez użytkownika) — nowy kształt/podział NIE
wpływa na:
- reguły WT (§68 szerokość biegu nadal sprawdzana jak dziś, przez istniejący
  `stair_width_m`, niezależnie od nowych wymiarów biegu/windy poniżej)
- powierzchnię użytkową/bilans poza naturalną konsekwencją większego obrysu
  klatki (patrz §5)
- API/typy danych zwracane przez `place_circulation()` — nadal jeden
  `cage_polygon` per klatka, tylko teraz prostokątny zamiast kwadratowy

Wewnętrzny podział na spocznik/bieg/winda/szacht/korytarz to **czysto
dekoracyjna nakładka rysowana na froncie**, nie osobne poligony/pola API.

## 3. Zatwierdzony układ (4 iteracje z wizualnym companion, v4 finalna)

Obrys klatki: prostokąt **400×550cm (4.0m × 5.5m = 22m²)**, oś X = szerokość,
oś Y = głębokość. Trzy rzędy (od strony wejścia/korytarza licząc jako "dół"):

```
Y=0 ────────────────────────────────────────
    │  spocznik 240×150   │   szacht 160×150 │   <- górny rząd
Y=150───────────────────────────────────────
    │ bieg     │ bieg     │                  │
    │ 120×250  │ 120×250  │   winda 160×250  │   <- środkowy rząd
    │  (hatch, │ (hatch,  │   (prostokąt +   │
    │  strzałka│ strzałka │    X po przekąt- │
    │  w górę) │ w górę)  │    nych)         │
Y=400───────────────────────────────────────
    │      spocznik + korytarz razem          │
    │      (400×150, pełna szerokość)         │   <- dolny rząd
Y=550───────────────────────────────────────
    X=0      X=120      X=240             X=400
```

Kluczowe decyzje z iteracji wizualnych (żeby nie zgadywać ponownie):
- **2 biegi obok siebie** (nie 1 szeroki), każdy **120×250cm** (szerokość×głębokość),
  strzałki w górę (kierunek wejścia na piętro wyżej) — to jest domyślny,
  jedyny obsługiwany wariant w tym projekcie (patrz §6, "1 bieg" odłożone).
- **Górny spocznik 240×150** — szerokość zwężona z pierwotnie podanych 300cm,
  żeby dokładnie odpowiadać 2×120cm biegów (użytkownik zaakceptował tę zmianę
  bez zastrzeżeń).
- **Winda 160×250** (szerokość×głębokość, czyli **pionowa/portret**) — czysty
  prostokąt z X po przekątnych (standardowy symbol szybu windy), wyrównana
  głębokością dokładnie z biegami (250cm), BEZ wewnętrznego podziału na
  szacht/kabinę/przedsionek (to była błędna wcześniejsza iteracja v3,
  poprawiona przez użytkownika: *"winda ma być cały czas 250(pion)x160(poziom)"*).
- **Szacht 160×150** — osobna strefa w górnym rzędzie, na prawo od spocznika,
  nad windą (ta sama kolumna X co winda, ten sam rząd Y co górny spocznik).
  Reprezentuje nadszybie/kontynuację szybu, nie jest przejściem dla ludzi.
- **Dolny rząd: "spocznik + korytarz razem"**, 400×150, pełna szerokość —
  łączy dolny spocznik biegów z fragmentem korytarza przed windą w jedną
  strefę (użytkownik: *"korytarz i górny spocznik razem"* — połączenie, nie
  osobne cienkie pasy). Nominalna głębokość 150cm (zbieżna z domyślnym
  `corridor_width_m=1.5`), ale wliczona NA SZTYWNO w `CAGE_DEPTH_M` z §4.1 —
  nakładka frontendowa etykietuje ten pas jako stronę korytarza, nie zmienia
  rozmiaru wraz z parametrem `corridor_width_m` (czysto wizualne, patrz §2).

## 4. Architektura

### 4.1 Nowe stałe (`services/circulation.py`)

```python
CAGE_WIDTH_M = 4.0   # 2×1.2m biegi + 1.6m winda/szacht (spec §3)
CAGE_DEPTH_M = 5.5   # 1.5m spocznik + 2.5m biegi/winda + 1.5m spocznik/korytarz
```

### 4.2 Budowa geometrii — zamiana kwadratu na prostokąt

`_corner_cage_convex`, `_centered_cage`, `_edge_cage` (circulation.py) oraz
`corner_cage` (bsp.py) dziś przyjmują `size: float` i budują kwadrat
`size × size`. Zamieniane na `width: float, depth: float`, budujące
`width × depth`:

- **Tryb "2" (środek, `_centered_cage`)**: prostokąt wyśrodkowany w strefie,
  `width` wzdłuż X, `depth` wzdłuż Y — bez zmian w logice poza zamianą
  jednego `half = size/2` na `half_w = width/2`, `half_h = depth/2`.
- **Tryby "1a"/"1b" (`_edge_cage`, wzdłuż najdłuższej/najkrótszej krawędzi)**:
  `width` biegnie WZDŁUŻ krawędzi (kierunek `ux,uy`), `depth` biegnie do
  wnętrza (kierunek normalnej) — naturalne dopasowanie do istniejącej
  struktury funkcji (już liczy `ux,uy` i `normal_x,normal_y` osobno).
- **Tryby "3"/"auto" (`_corner_cage_convex`, narożnik)**: `width` wzdłuż osi X
  bounding-boxa, `depth` wzdłuż osi Y — wybór arbitralny (nie ma jednej
  "poprawnej" krawędzi w narożniku), ale deterministyczny i wystarczający dla
  zakresu "czysto wizualne".

**Bez rotacji** — prostokąt zawsze osiowo wyrównany (X=width, Y=depth) w
układzie współrzędnych świata, niezależnie od kąta elewacji. Zaakceptowane
uproszczenie (użytkownik: "ok") — obrysy w tym projekcie są już w większości
prostokątne po `rectangle_decompose()`, więc brak rotacji rzadko będzie
zauważalny; pełne dopasowanie kątowe odłożone poza zakres.

### 4.3 Frontend — dekoracyjna nakładka (`CanvasEditor.tsx`)

Dla każdego `cage_geometries[i]` (nadal pojedynczy poligon-prostokąt z
backendu, bez zmian w API), frontend:
1. Liczy `minx,miny,maxx,maxy` z poligonu (bounding box — poligon jest już
   prostokątem, więc to dokładne rogi).
2. Skaluje 5 stref z §3 proporcjonalnie do faktycznych `(maxx-minx)`,
   `(maxy-miny)` tego konkretnego poligonu (na wypadek gdyby przyszłe zmiany
   `CAGE_WIDTH_M`/`CAGE_DEPTH_M` lub inny `cage_size_m` dały inny rozmiar niż
   dokładnie 400×550 — nakładka ma być proporcjonalna, nie zahardkodowana w
   pikselach).
3. Rysuje (Konva `Line`/`Rect`/`Text`, wzorem istniejących adnotacji
   solarnych): 2× bieg (hatching + strzałka), spocznik górny, winda (prostokąt
   + X), szacht, pas "spocznik+korytarz" na dole — same etykiety co w §3.

Orientacja "dół = strona korytarza" zależy od trybu pozycji klatki (np. dla
trybu "1a" korytarz/wejście jest po stronie krawędzi elewacji) — nakładka
zawsze rysuje dolny rząd jako "stronę wejścia", co jest poprawne dla
wszystkich trybów pozycji o ile orientacja `width`/`depth` z §4.2 jest
konsekwentna (depth = kierunek "w głąb budynku" = ten sam kierunek co
dotychczasowe `size` dla trybów edge/center).

## 5. Konsekwencja: większa klatka

Dzisiejsza klatka (kwadrat, uśredniony `staircase_dims_m`) wychodzi ~2.5-3.5m
bok = 6-12m². Nowy prostokąt to **22m²** — realny, świadomie zaakceptowany
wzrost powierzchni "zjadanej" przez klatkę kosztem mieszkań (przez 3 iteracje
wizualne zeszliśmy z pierwotnych 36m² do 22m², głównie zwężając biegi z
150×360 na 120×250). Nie wymaga dalszej akcji — to naturalna konsekwencja
podania realnych wymiarów zamiast fikcyjnego kwadratu.

## 6. Świadomie poza zakresem (nie implementować teraz)

- **`cage_size_m` staje się polem nieużywanym przez samą geometrię.**
  Pozostaje w `CirculationSpec`/`TypologyPreset.staircase_dims_m`/
  `to_layout_defaults()` bez zmian (unika breaking change w API i presetach
  typologii), ale faktyczny kształt klatki ignoruje je teraz na rzecz stałych
  `CAGE_WIDTH_M`/`CAGE_DEPTH_M` z §4.1. To świadoma niespójność — pełne
  pogodzenie `cage_size_m`/presetów typologii z realnymi wymiarami wymaga
  decyzji wykraczającej poza "czysto wizualne" (np. czy różne typologie mają
  różne warianty klatki), odłożone na przyszły, funkcjonalny przebieg.
- **Tryb "1 bieg"** (dla niższych/mniejszych budynków, wspomniany przez
  użytkownika jako "1/2 biegów") — nieobsługiwany, zawsze 2 biegi. Do dodania
  jeśli okaże się potrzebny.
- **Rotacja prostokąta** względem kąta elewacji (§4.2) — zawsze osiowo
  wyrównany.
- **WT §68 (szerokość biegu) nie jest aktualizowana** o nowy wymiar biegu
  (120cm) — nadal sprawdza istniejący `stair_width_m` jak dziś, niezależnie
  od wizualnego podziału.
- **Realne wymogi budowlane dla dźwigów** (szyb, nadszybie, podszybie,
  wymiary kabiny wg normy) — `szacht`/`winda` to etykiety wizualne, nie
  modelowanie zgodności z normami dźwigowymi.

## 7. Odrębny, odłożony temat: mieszkania "na przestrzał"

Przy okazji tej rozmowy użytkownik zauważył, że **żadna typologia dziś
faktycznie nie generuje mieszkań "na przestrzał"** (dotykających dwóch
przeciwległych elewacji, typowe dla wąskich budynków bez korytarza) —
`SZEREGOWIEC` w `typology_presets.py` ustawia `corridor_width_m=0.0` i
`place_cage=False`, ale endpoint (`layout.py:26`, `Field(gt=0)`) wymaga
korytarza >0, a frontend (`SessionContext.tsx:600`) i tak podstawia 1.2m gdy
preset daje 0. Użytkownik zdecydował: **osobny brainstorm PO tej pracy nad
klatkami** (nie część tego projektu). Zanotowane tutaj wyłącznie żeby nie
zgubić wątku — brak zadania do wykonania w tym planie.

## 8. Testy

Brak automatycznych testów frontendu w tym projekcie dla renderowania
Konva (ustalone wcześniej w sesji) — weryfikacja przez Playwright:
narysować obrys, umieścić klatkę, zrzut ekranu, wizualnie porównać z układem
z §3 (3 rzędy, proporcje, etykiety).

Backend: rozszerzyć `test_circulation.py` o test że
`_place_cage_by_mode(..., cage_position="2")` z nowymi `width`/`depth`
zwraca poligon o `bounds` odpowiadających `CAGE_WIDTH_M`×`CAGE_DEPTH_M`
(w granicach przycięcia do strefy), analogicznie dla "1a"/"1b"/"3"/"auto".
