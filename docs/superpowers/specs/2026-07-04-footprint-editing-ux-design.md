# Etap 0+1: Wyłączenie solar/optymalizatora + UX edycji obrysu

**Data**: 2026-07-04
**Status**: zaakceptowany (brainstorming z userem, bez testów automatycznych na życzenie usera)

## Kontekst i cel

User zdefiniował docelowy workflow aplikacji jako sekwencję małych, domkniętych
etapów (każdy działa „perfekcyjnie" zanim ruszy następny):

- **Etap 0**: wyłączenie analizy słońca i optymalizatora (ten spec, sekcja 1)
- **Etap 1**: wygodna edycja obrysu budynku (ten spec, sekcje 2–5)
- **Etap 2**: ręczne rysowanie klatek schodowych i korytarzy (przyszły spec)
- **Etap 3**: kropki ewakuacyjne co 1m na osi korytarza (przyszły spec)
- **Etap 4**: podział na mieszkania z iteracjami i scoringiem (przyszły spec)

Decyzje kierunkowe podjęte podczas brainstormingu:

1. Auto-rozmieszczanie komunikacji (suwak `num_cages`, `/layout/circulation`)
   **współistnieje** z przyszłym rysowaniem ręcznym — nic nie usuwamy.
2. Drag odcinka obrysu: **bez Shift swobodnie, z Shift prostopadle** do odcinka.
3. Podejście A: rozszerzamy istniejący tryb `edit-vertices`, bez refactoru
   CanvasEditor; geometria w nowym module czystych funkcji.
4. Bez testów automatycznych (vitest/Playwright) — tylko ręczna weryfikacja.

## Co już działa (nie ruszamy)

- Siatka kropek co 1m, osie w (0,0), snap 0.5m (`SNAP_M`), rysowanie obrysu punktami.
- Ściana 40cm z offsetem 10cm do wewnątrz (`wall_bands`, `NET_SHRINK_M`);
  strefy dochodzą do ściany, nie nachodzą.
- Drag pojedynczego węzła obrysu (tryb `edit-vertices`, `updateVertex`).
- Edycja osi korytarza: dblclick wstawia/usuwa punkt, drag segmentów
  (tryb `edit-corridor-centerline`).
- Struktura mieszkań w % z wyliczaną liczbą sztuk (`ProgramSection`).

## Sekcja 1 — Etap 0: wyłączenie solar + optymalizatora

Jedna stała modułowa w `frontend/app/components/Sidebar.tsx`:

```ts
const SHOW_SOLAR_OPTIMIZER = false;
```

Warunkowe renderowanie `SolarSection` i `OptimizerSection` (oraz ewentualnych
odwołań do nich w statusach/panelu). Pliki komponentów i endpointy backendu
(`solar.py`, `optimizer.py`) zostają nietknięte — nikt ich nie wywołuje.
Przywrócenie = zmiana jednej linii.

## Sekcja 2 — Etap 1: interakcje na obrysie

Wszystko w istniejącym trybie `edit-vertices` (żadnych nowych trybów):

- **Hover na odcinku**: niewidoczny hitbox (przezroczysta `Line` o szerokim
  `strokeWidth`, np. ~12/scale) na każdym odcinku obrysu; `onMouseEnter/Leave`
  → podświetlenie widocznej linii odcinka (kolor akcentu, grubsza kreska),
  kursor `pointer`.
- **Hover na węźle**: `onMouseEnter/Leave` na istniejących `Circle` → większy
  promień + kolor akcentu.
- **Dblclick na odcinku** → wstawia węzeł w punkcie kliknięcia (snap 0.5m).
  Ten sam wzorzec co oś korytarza (`onDblClick` na hitboxie).
- **Dblclick na węźle** → usuwa węzeł. Guard: minimum 3 punkty obrysu.
- **Drag węzła**: bez zmian (istniejący `updateVertex`).
- **Drag odcinka** (nowość): hitbox odcinka `draggable`.
  - Bez Shift: oba końce przesuwają się o deltę myszy (swobodnie).
  - Z Shift: delta rzutowana na normalną odcinka (ruch tylko prostopadle,
    kąty sąsiednich odcinków zachowane).
  - Stan Shift czytany na bieżąco w trakcie draga (można wcisnąć/puścić w locie).
  - Oba końce snapują do 0.5m na bieżąco podczas draga — spójnie z istniejącym
    dragiem pojedynczego węzła (snap w `onDragMove`).

Geometria w nowym pliku `frontend/app/lib/polygonEdit.ts` — czyste funkcje na
`Point2D[]`, zero zależności od Konvy/Reacta:

- `insertVertexAt(points, segmentIndex, point)` — wstawia po snapie, odrzuca duplikat sąsiada
- `removeVertexAt(points, index)` — z guardem min 3 punkty
- `translateSegment(points, segmentIndex, delta, { perpendicular })` — z rzutem
  delty na normalną odcinka przy `perpendicular: true`

## Sekcja 3 — stan i przepływ danych

Jedna nowa akcja w `SessionContext`: `SET_FOOTPRINT_POINTS` (podmienia cały
ring obrysu). Wszystkie edycje: handler w CanvasEditor → funkcja z
`polygonEdit.ts` → dispatch nowego ringu. Istniejące `UPDATE_VERTEX` zostaje
(drag pojedynczego węzła bez zmian).

Przeliczenia pochodne (ściany 40cm, komunikacja, mieszkania) — jak dziś:
uruchamiane jawnie przyciskami (`regenerate`, `runPlaceCirculation`, ...),
bez auto-przeliczania po każdej edycji obrysu.

## Sekcja 4 — guardy i przypadki brzegowe

- Usuwanie węzła zablokowane przy 3 punktach (dblclick ignorowany).
- Wstawienie odrzucone, gdy po snapie nowy punkt pokrywa się z którymś
  z końców odcinka.
- Drag odcinka: jeśli po snapie któryś koniec pokrywa się z sąsiednim węzłem,
  edycja odrzucona (revert do stanu sprzed draga) — obrys nie może się
  zdegenerować.
- Samoprzecięcia obrysu po dragu: **nie walidujemy** w tym etapie. Backend
  odrzuca niepoprawną geometrię przy generacji. Znane ograniczenie.

## Sekcja 5 — weryfikacja (ręczna)

Bez testów automatycznych (decyzja usera). Scenariusz ręczny po implementacji:

1. Solar i Optymalizator niewidoczne w panelu bocznym; reszta paneli działa.
2. Narysuj obrys → tryb edycji → hover podświetla ściany i węzły.
3. Dblclick na ścianie wstawia punkt; dblclick na punkcie usuwa
   (przy 3 punktach usuwanie zablokowane).
4. Drag ściany bez Shift — swobodny; z Shift — tylko prostopadle.
5. Po edycji obrysu „Generuj" działa, ściany 40cm i strefy renderują się
   poprawnie.
6. Regresja: rysowanie obrysu, drag węzła, edycja osi korytarza — bez zmian.
