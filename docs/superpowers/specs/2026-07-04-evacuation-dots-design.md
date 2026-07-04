# Etap 3: Kropki ewakuacyjne co 1m na osi korytarza

**Data**: 2026-07-04
**Status**: zaakceptowany (brainstorming z userem)
**Zależy od**: spec 2026-07-04-manual-circulation-drawing (Etap 2 — sieć
korytarzy może pochodzić z auto + manuali; kropki liczą się na całości)

## Kontekst i cel

Wzdłuż osi każdego korytarza, co 1 metr, kropka pokazująca jakość dojścia
ewakuacyjnego do klatek schodowych:

- **zielona** — osiągalna dokładnie 1 klatka, odległość < 20 m
- **szara** — osiągalne ≥ 2 różne klatki, odległość do bliższej < 40 m
  (szara również poniżej 20 m — celowo, żeby nie myliła się z zieloną)
- **czerwona** — każdy pozostały przypadek (w tym 0 osiągalnych klatek)

Odległość = najkrótsza droga WZDŁUŻ SIECI OSI korytarzy do punktu wejścia
do klatki (nie w linii prostej).

Progi 20/40 m to robocze wartości usera — w kodzie i odpowiedziach
oznaczane jako heurystyka, BEZ przypisywania § WT (utrwalona zasada
projektu: żadnych fabrykowanych citations).

Decyzje z brainstormingu:

1. „Dwa dojścia" = z punktu osiągalne ≥ 2 różne klatki; limit 40 m liczony
   do bliższej. Bez wymogu rozłączności dróg (świadome uproszczenie
   względem WT).
2. Kropki ZASTĘPUJĄ dzisiejsze kolorowanie odcinków osi wg
   `exceeds_max`/loading — oś rysowana neutralnie, jedyny wskaźnik
   ewakuacji to kropki.
3. Obliczenia w backendzie (Dijkstra własny, bez nowej zależności —
   sieci korytarzy mają dziesiątki węzłów, nie tysiące).
4. (Uzupełnienie 2026-07-04, review usera) Progi 20/40 m są EDYTOWALNE
   w panelu Komunikacja; po zmianie wartości przycisk **PRZELICZ** odświeża
   kropki bez ruszania geometrii (lekki endpoint `POST /layout/evacuation`).

## Co już istnieje (reużywane / zastępowane)

- `_distances_along_centerline()` w `circulation.py` — liczy odległość
  łukową wzdłuż JEDNEJ połączonej ścieżki; nie umie sieci z rozgałęzieniami
  ani wielu klatek per punkt. ZASTĘPOWANE przez graf.
- `_classify_segment_loading()` + `exceeds_max` na
  `CorridorCenterlineSegment` — przestają sterować kolorem osi na
  froncie; pola zostają w API (kompatybilność), frontend przestaje ich
  używać do kolorowania.
- Progi: `CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0` i
  `..._DOUBLE_LOADED_M = 40.0` — reużyte jako progi zielona/szara.

## Sekcja 1 — model grafu sieci korytarzy

Nowy moduł `backend/services/evacuation.py` (czyste funkcje, shapely +
stdlib; bez zależności od FastAPI — testowalny samodzielnie):

1. **Węzły**: wszystkie końce segmentów centerline (auto + manualne) po
   deduplikacji (tolerancja 1e-6) + punkty przecięcia segmentów, które się
   krzyżują bez wspólnego końca (split segmentów w punkcie przecięcia).
2. **Krawędzie**: odcinki między węzłami z wagą = długość euklidesowa.
3. **Wejścia do klatek**: dla każdej klatki (`cage_polygons`) punkty osi
   leżące w odległości ≤ `CAGE_ENTRY_TOLERANCE_M = 0.25` od poligonu
   klatki. Jeśli oś przecina klatkę — punkt przecięcia z jej brzegiem.
   Każde wejście dostaje etykietę klatki (indeks), żeby rozróżniać
   „ile RÓŻNYCH klatek osiągalnych".
4. **Dijkstra** z multi-źródłem per klatka: dla każdej klatki k liczymy
   `dist_k(node)` — najkrótszą odległość każdego węzła do najbliższego
   wejścia klatki k. Sieci są małe; O(K · E log V) bez znaczenia.

## Sekcja 2 — próbkowanie i statusy kropek

1. Wzdłuż każdej krawędzi grafu co 1.0 m punkt próbkowania (plus punkt na
   każdym węźle). Odległość próbki do klatki k = min po obu końcach
   krawędzi: `min(dist_k(end1) + odległość_wzdłuż_krawędzi_do_end1,
   dist_k(end2) + odległość_do_end2)`.
2. Dla każdej próbki: `reachable = [k for k in cages if dist_k < inf]`,
   `d = min(dist_k)`.
3. Status:
   - `len(reachable) == 1` i `d < 20.0` → `"green"`
   - `len(reachable) >= 2` i `d < 40.0` → `"gray"`
   - inaczej → `"red"`

## Sekcja 3 — API

`compute_evacuation_dots()` przyjmuje progi jako parametry
(`green_max_m`, `gray_max_m`); stałe 20/40 z `circulation.py` są tylko
wartościami DOMYŚLNYMI.

`CirculationSpec` (request) dostaje edytowalne progi:

```
max_dist_single_m: float = 20.0   # zielona, dojście do 1 klatki
max_dist_multi_m: float = 40.0    # szara, dojście do >=2 klatek
```

`CirculationResponse` (i `/layout/generate` — obie ścieżki API, patrz
gotcha „dual layout API surface": pole MUSI wejść do OBU odpowiedzi)
dostaje:

```
evacuation_dots: [{ x: float, y: float, status: "green"|"gray"|"red", distance_m: float | null }]
```

`distance_m = null` gdy nieosiągalna żadna klatka. Kropki liczone w
`place_circulation()` / `reshape_circulation()` po zbudowaniu centerline —
zawsze aktualne po każdej zmianie komunikacji (auto, manual, reshape).

**PRZELICZ — lekki endpoint** `POST /layout/evacuation`:

```
request:  { centerline: [{points: [[x,y],[x,y]]}], cage_geometries: [GeoJSON],
            max_dist_single_m: float, max_dist_multi_m: float }
response: { evacuation_dots: [...] }
```

Celowo NIE przelicza geometrii (korytarzy, remainder, ścian) — użytkownik
z ręcznie przesuniętą osią dostaje tylko przemalowane kropki. Frontend po
odpowiedzi podmienia wyłącznie `circulationResult.evacuation_dots`.

## Sekcja 4 — frontend

`CanvasEditor.tsx`:

- Render kropek: `Circle` promień `3 / scale`, kolory: zielona `#22c55e`,
  szara `#9ca3af`, czerwona `#ef4444`; `listening={false}` (kropki nie
  łapią myszy — nie przeszkadzają w edycji osi).
- Oś korytarza: kolor neutralny (dotychczasowy zielony/czerwony wg
  `exceeds_max` USUNIĘTY) — `#60a5fa` w obu motywach, jak inne elementy
  edycyjne.
- Kropki widoczne zawsze gdy `circulationResult`/`layoutResult` je zawiera
  (nie tylko w trybie edycji) — to informacja projektowa, nie narzędzie
  edycji.

Panel Komunikacja:
- dwa pola liczbowe: „Dojście do 1 klatki ≤ [20] m" i „Dojście do ≥2
  klatek ≤ [40] m" (krok 1m, min 1);
- przycisk **PRZELICZ** (aktywny gdy istnieje `circulationResult`) —
  woła `POST /layout/evacuation` z aktualną osią, klatkami i progami,
  podmienia tylko kropki;
- zbiorcze podsumowanie pod listą elementów — liczba kropek czerwonych
  („Dojścia: 3 punkty poza limitem" / „Dojścia: OK").

## Sekcja 5 — przypadki brzegowe

- Brak klatek (0 wejść): wszystkie kropki czerwone, `distance_m = null`.
- Korytarz-wyspa (składowa grafu bez wejścia do klatki): kropki czerwone.
- Oś w całości wewnątrz klatki: segment pomijany (0 próbek).
- Dwie klatki stykające się z osią w tym samym punkcie: dwa wejścia,
  dwa różne indeksy klatek → próbki w pobliżu mają ≥2 osiągalne → szare.
- Zmiana szerokości korytarza nie wpływa na kropki (liczone po osi).

## Sekcja 6 — weryfikacja

Backend: testy pytest w `backend/tests/test_evacuation.py` — graf w L,
graf z rozgałęzieniem, dwie klatki (szare), jedna klatka >20m (czerwone),
wyspa bez klatki, 0 klatek. (Testy backendowe zaproponowane w
brainstormingu; user zaakceptował design bez uwag.)

Frontend ręcznie:
1. Auto-komunikacja → kropki co 1m wzdłuż osi, kolory sensowne.
2. Dorysowanie drugiej klatki ręcznej przy korytarzu → kropki między
   klatkami robią się szare.
3. Wydłużenie korytarza dragiem poza 20m od jedynej klatki → końcówka
   czerwona.
4. Stare kolorowanie odcinków zniknęło; oś neutralna.
5. Zmiana progu 20→30 + PRZELICZ → część czerwonych przechodzi na
   zielone; geometria (oś, korytarze, ściany) NIE drgnęła.
