# Etap 5: Wybór iteracji z listy, niezależne przesuwanie klatek, Generuj układ na aktualnej geometrii

**Data**: 2026-07-05
**Status**: zaakceptowany (3 pytania zamknięte z userem — jeden spec+plan,
geometria wszystkich iteracji od razu, etykieta zamiast odwracania liczby,
auto-przelicz po drop klatki, Generuj układ używa istniejącej geometrii)
**Zależy od**: Etap 2b (iteracyjne klatki), Etap 4 (iteracyjny podział na
mieszkania), Etap 2 (manualne klatki/korytarze), Etap 3 (kropki ewakuacyjne)
— wszystkie już wdrożone i scalone.

## Kontekst i cel

Trzy niezależne usterki/braki zgłoszone po użyciu Etapu 2b/4 na żywo:

1. Lista iteracji klatek (i analogicznie mieszkań) pokazuje tylko liczby
   (`seed`/`score`/komponenty) dla WSZYSTKICH iteracji, ale pełną geometrię
   tylko dla najlepszej. User nie może kliknąć innej iteracji i zobaczyć jej
   na rysunku. Dodatkowo „score" (niżej = lepiej, 0 = ideał) czytany jest
   intuicyjnie jako „wyżej = lepiej" (typowe dla słowa „score").
2. „Przesuń komunikację" przesuwa korytarz+wszystkie klatki jako jedną
   sztywną bryłę (`TRANSLATE_CIRCULATION`, jeden Group). User chce przesuwać
   pojedynczą klatkę.
3. „Generuj układ" (`/layout/generate`, one-shot) zawsze liczy komunikację
   od zera wg ustawień panelu — gubi ręczne przesunięcia, reshape osi
   korytarza i indywidualnie przesunięte klatki (punkt 2), jeśli user
   wykonał je PRZED kliknięciem.

## Sekcja 1 — geometria wszystkich iteracji (klatki + mieszkania)

Backend już liczy pełny wynik (`CirculationResult` / `list[ApartmentCell]`)
dla KAŻDEJ iteracji wewnątrz pętli (`iterate_cage_placement`,
`iterate_units`) — dziś zachowuje tylko najlepszy, reszta trafia jedynie do
lekkich metadanych (`CageIterationMeta`/`IterationMeta`: seed, score,
count, components). Zmiana: zachować i zserializować geometrię każdej
iteracji, nie tylko najlepszej.

**Backend — klatki** (`services/cage_placement.py`,
`api/v1/endpoints/layout.py`):
- `iterate_cage_placement` zwraca dziś `tuple[CirculationResult, list[CageIterationMeta], int]`
  (najlepszy wynik osobno, metadane bez geometrii). Zmiana: `CageIterationMeta`
  dostaje pole `result: CirculationResult` (pełny wynik TEJ iteracji, nie
  tylko najlepszej). Funkcja nadal zwraca też najlepszy `CirculationResult`
  osobno (`best[1]`) dla zgodności wstecznej z klasycznym trybem/miejscami,
  które nie znają koncepcji list iteracji.
- `CageIterationMetaResult` (Pydantic, w `layout.py`) dostaje:
  `cage_geometries: list[dict]`, `circulation_geometry: dict | None`,
  `centerline: list[CorridorCenterlineSegmentResult]`,
  `evacuation_dots: list[EvacuationDotResult]` — te same kształty co pola
  na `CirculationResponse` dziś, tylko powielone per iteracja.
- Serializacja: reużyć istniejące helpery (`_serialize_dots`, konstruktory
  centerline) zamiast pisać drugi raz.

**Backend — mieszkania** (`services/unit_mix.py`, `layout.py`):
- `iterate_units` zwraca dziś `tuple[list[ApartmentCell], list[IterationMeta], int, int]`.
  Analogicznie: `IterationMeta` dostaje `cells: list[ApartmentCell]` (pełne
  komórki TEJ iteracji).
- `IterationMetaResult` dostaje `apartments: list[ApartmentResult]` ORAZ
  `wall_bands: list[dict]` (te same kształty co `UnitsResponse.apartments`/
  `wall_bands` dziś) — per iteracja, bez wyjątków. Klik w wiersz listy
  zamienia aktywny wynik całościowo (Sekcja 1 niżej), więc ściany muszą
  być gotowe dla KAŻDEJ iteracji, nie tylko najlepszej — inaczej po
  przełączeniu user widziałby mieszkania bez ścian albo ściany
  poprzedniej iteracji. Ten sam koszt-akceptacji co przy klatkach.

**Dual-surface**: pola dodane symetrycznie na `/layout/circulation` +
`/layout/generate` (klatki) i `/layout/units` + `/layout/generate`
(mieszkania) — zgodnie z ustalonym w tej sesji wzorcem (evacuation_dots,
cage_iterations już to robią poprawnie, ten sam mechanizm).

**Koszt**: payload rośnie ~10× dla pól iteracji (typowy budynek to
dziesiątki-setki punktów geometrii, nie tysiące — akceptowalne, zgodnie z
decyzją usera).

**Frontend — wybór i render**:
- Klik w wiersz listy (`CirculationSection.tsx` / `ProgramSection.tsx`)
  ustawia TĘ iterację jako aktywny wynik — dispatch zamienia
  `state.circulationResult` (klatki) / `state.apartments`+`state.leftover`
  (mieszkania) na geometrię wybranej iteracji, dokładnie tak jakby
  backend zwrócił ją jako główny wynik. Żaden osobny „tryb podglądu" nie
  istnieje — wybrana iteracja PO PROSTU staje się aktualnym wynikiem, więc
  PRZELICZ dojść / Generuj układ / eksport / podział na mieszkania
  automatycznie działają na tym co user aktualnie ogląda, bez
  specjalnych przypadków.
- Osobno trzymany tylko `cageIterationsList`/`unitIterationsList` (już
  istnieje) + `activeCageSeed`/`activeUnitSeed: number | null` —
  WYŁĄCZNIE do podświetlania w liście (który wiersz jest aktualnie
  załadowany), nie do renderowania canvasu. `null` = jeszcze nic nie
  wybrano ręcznie, canvas pokazuje to co backend zwrócił jako główny
  wynik (czyli najlepszą iterację — bez zmiany domyślnego zachowania).
- Lista pokazuje DWA stany wizualnie: „najlepsza" (zawsze widoczne,
  akcent/gwiazdka przy `best_seed`) i „aktualnie załadowana"
  (obramowanie na wybranym wierszu, jeśli różny od najlepszego).
- Nowe uruchomienie iteracji (klik „Rozmieść iteracyjnie"/„Podziel na
  mieszkania" ponownie) zastępuje całą listę i wynik jak dziś — domyślnie
  aktywny = najlepsza z nowej listy, `activeCageSeed`/`activeUnitSeed`
  resetuje się do `null`.
- Etykieta: „score" → „odchylenie" (lub „niedopasowanie") + statyczny
  dopisek pod nagłówkiem listy: „niżej = lepiej, 0 = idealne dopasowanie
  do wag". Same liczby w JSON/API bez zmian (pole nadal `score`).

## Sekcja 2 — niezależne przesuwanie klatek

Dziś: jeden `<Group draggable>` w `CanvasEditor.tsx` (tryb
`edit-circulation`) zawiera WSZYSTKIE `circulationParts` (korytarz) i
WSZYSTKIE `cageGeometries` (klatki) — jeden `onDragEnd` liczy jedno
`dx`/`dy` i dispatch'uje `TRANSLATE_CIRCULATION` na całość.

**Zmiana**:
- Korytarz zostaje jako dzisiejsza zbiorcza bryła, ALE bez klatek w
  środku (osobny `<Group draggable>` tylko dla `circulationParts`,
  zachowuje dzisiejsze `TRANSLATE_CIRCULATION` — zgrubne przesunięcie
  całości, nie usuwane, bo nie było o to proszone).
- Każda klatka z `cageGeometries` dostaje WŁASNY `<Group draggable>`
  (klucz = indeks w `cageGeometries`, ten sam porządek co
  `state.circulationResult.cage_geometries`).
- `onDragEnd` pojedynczej klatki: liczy `dx`/`dy` tej klatki, dispatch
  nowej akcji `DRAG_CAGE { index, dx, dy }` → wywołuje nowy backend
  request z **aktualną** geometrią wszystkich klatek (łącznie z już
  wcześniej przesuniętymi w tej samej sesji edycji) plus przesuniętą
  pozycją klatki `index`.
- **Backend**: nowy endpoint `POST /layout/circulation/move-cage` (osobny
  od `/circulation/reshape` — inny kształt wejścia, ten przesuwa wielokąt
  klatki, tamten kształtuje oś). Request: `footprint`, obecne
  `cage_geometries` (lista, z tą przesuniętą już podmienioną na nową
  pozycję przez frontend przed wysłaniem), `corridor_width_m`,
  `max_dist_single_m`/`max_dist_multi_m`. Backend odtwarza `zones`
  (`rectangle_decompose(footprint)`, tak jak `place_circulation` robi
  dziś), przypisuje każdą klatkę do strefy, której bbox ją zawiera
  (analogiczna zasada do `_candidate_cages`'s zone-containment check z
  Etapu 2b), woła `_assemble_with_cages` z pełnym zestawem klatek
  (dict strefa→lista klatek, kontrakt z Etapu 2b) — to przelicza
  korytarz+centerline+kropki dla WSZYSTKICH stref na nowo z jednego
  przebiegu (tańsze i prostsze niż ręczne „przelicz tylko jedną strefę",
  bo `_assemble_with_cages` już to robi per-strefowo i strefy bez
  zmienionej klatki dadzą identyczny wynik co przed przesunięciem).
  Zwraca `CirculationResponse`-kształt (klatki, korytarz, centerline,
  kropki) — walidacja 422 gdy klatka poza obrysem lub koliduje z inną
  (te same komunikaty co ręczne klatki, Etap 2).
- Przesunięta klatka staje się od tego momentu częścią wyniku tak jak
  klatka ręczna (Etap 2) w tej pozycji — kolejne „Rozmieść iteracyjnie"
  nadpisze ją świeżym wynikiem (brak trwałości między trybami, zgodnie z
  dzisiejszym zachowaniem manual vs auto).
- Walidacja: klatka nie może wyjść poza obrys (`fp.contains`) ani
  kolidować z inną klatką — 422 z komunikatem, tak jak przy rysowaniu
  ręcznej klatki (Etap 2).

## Sekcja 3 — Generuj układ na aktualnej geometrii

Dziś `regenerate()` (`SessionContext.tsx`) zawsze woła `/layout/generate`
z pełną specyfikacją komunikacji (`state.circulation` + manual
cages/corridors) — endpoint liczy korytarz+klatki OD ZERA (auto albo
iteracyjnie wg `cage_iterations`), ignorując:
- ręczne przesunięcie całości (`TRANSLATE_CIRCULATION`),
- reshape osi korytarza (`edit-corridor-centerline`),
- przesunięcie pojedynczej klatki (Sekcja 2, nowe).

**Zmiana** — `regenerate()` rozgałęzia się:

```
if (state.circulationResult) {
  // komunikacja już istnieje na canvasie (auto/iteracyjnie/ręcznie/
  // przesunięta/zreshape'owana) — użyj JEJ dokładnie, nie licz od nowa
  wywołaj runSubdivideUnits() na aktualnym state.circulationResult
  (remainder, circulation_geometry, cage_geometries — dokładnie jak
  dziś robi przycisk "2 Podziel na mieszkania", ten sam callback)
  + api.validateFullLayout(...) na wyniku
  złóż w LayoutResult-kształt (jak dziś robi regenerate() ręcznie
  budując layoutResult z unitsRes, patrz istniejący kod)
} else {
  // nic jeszcze nie policzone — zachowanie dokładnie jak dziś
  wywołaj istniejący pełny /layout/generate
}
```

Zero nowego endpointu backendu dla tej ścieżki — `/layout/units` już
przyjmuje `remainder`+`circulation_geometry`+`footprint` bezpośrednio
(Etap 4 Task 2), dokładnie to czego trzeba. Jedyna zmiana to WYBÓR, którą
już istniejącą ścieżkę frontend woła.

Efekt: „Generuj układ" po ręcznych korektach = WYSIWYG (dokładnie to co
widać na canvasie + podział na mieszkania + walidacja + wall_bands).
„Generuj układ" na świeżym obrysie (bez wcześniejszych kliknięć w sekcji
Komunikacja) = bez zmian, jak dziś.

## Sekcja 4 — przypadki brzegowe

- Przesunięcie klatki poza obrys → 422, klatka wraca na starą pozycję
  (analogicznie do 422 przy rysowaniu ręcznej klatki poza obrysem, Etap 2
  — ten sam UX, nie dodajemy nowego).
- „Generuj układ" gdy `state.circulationResult` istnieje, ale user
  ZMIENIŁ ustawienia w panelu Komunikacja (np. `corridor_width_m`) PO
  wygenerowaniu komunikacji, bez ponownego kliknięcia „Umieść..."/
  "Rozmieść...": nowe ustawienia NIE zostaną zastosowane (bo używamy
  istniejącej geometrii) — to jest zamierzone (WYSIWYG > respektowanie
  niedziałających jeszcze zmian panelu), ale warto rozważyć wizualny
  sygnał „ustawienia zmienione, kliknij ponownie Umieść/Rozmieść żeby
  zastosować" — NICE TO HAVE, nie blokujące, do oceny w planie.

## Sekcja 5 — weryfikacja

Backend: testy pytest — geometria każdej iteracji w odpowiedzi API
(klatki i mieszkania) zgadza się z tym co zwróciłaby ta iteracja
uruchomiona osobno (determinizm); nowy endpoint przesunięcia klatki:
poprawne przeliczenie korytarza tej strefy, inne strefy bez zmian, 422
poza obrysem/kolizja.

Frontend ręcznie:
1. „Rozmieść iteracyjnie" → klik w inną niż najlepsza iterację z listy →
   canvas pokazuje TĘ iterację (inne klatki/korytarz), najlepsza nadal
   oznaczona osobno.
2. Etykieta „odchylenie, niżej = lepiej" widoczna, najlepsza (najniższa
   liczba) faktycznie podświetlona.
3. Przesuń pojedynczą klatkę w trybie „Przesuń komunikację" → tylko ta
   klatka się rusza, korytarz w jej strefie przelicza się automatycznie,
   reszta bez zmian.
4. Umieść korytarz i klatkę (albo iteracyjnie) → ręcznie przesuń klatkę
   → „Generuj układ" → wynik używa PRZESUNIĘTEJ pozycji, nie liczy nowej.
5. Świeży obrys, od razu „Generuj układ" (bez wcześniejszych kliknięć w
   Komunikacji) → zachowanie identyczne jak dziś.
6. Regresja: PRZELICZ dojścia, eksport, podział na mieszkania — działają
   na aktualnie wyświetlanej (wybranej z listy lub przesuniętej)
   geometrii.
