# Etap 4: Podział na mieszkania — liczba z powierzchni, iteracje, zero resztek

**Data**: 2026-07-04
**Status**: zaakceptowany (brainstorming z userem)
**Zależy od**: remainder z komunikacji (auto lub manualnej — Etap 2);
niezależny od kropek (Etap 3)

## Kontekst i cel

Cała powierzchnia budynku, która nie jest klatką ani korytarzem, MUSI być
podzielona na mieszkania — zero resztek. Liczba mieszkań NIE jest zadawana
przez usera: wynika ze struktury procentowej i wielkości narysowanego
budynku. Podział przeprowadza 10 iteracji z scoringiem, wybiera najlepszą;
user widzi listę iteracji z wynikami i steruje jednym suwakiem wagi
struktura↔wielkości.

Decyzje z brainstormingu:

1. Pole „liczba mieszkań" ZNIKA z panelu Program; liczba wyliczana
   z powierzchni, pokazywana readonly.
2. ~~Jeden suwak wagi~~ ZMIENIONE w review usera 2026-07-04 (screen
   „Unit weights" z Finch3D): **7 wag-suwaków** (0–1), scoring
   wielokryterialny — patrz Sekcja 4.
3. Różnorodność iteracji: losowa kolejność przydziału specyfikacji i
   wyboru prostokątów, deterministyczny seed per iteracja (0..9) —
   wyniki powtarzalne.
4. Licznik iteracji: batch — jedna odpowiedź HTTP z listą 10 iteracji
   i ich score'ami; panel pokazuje listę, najlepsza podświetlona.
   (Bez live-streamingu — YAGNI przy <1s obliczeń.)

## Co już istnieje (baza do zmian)

- `fit_program_to_rectangles()` + `subdivide_units()` w
  `backend/services/unit_mix.py` — zachłanne dopasowanie, JEDEN przebieg,
  leftover dozwolony. Staje się wnętrzem pojedynczej iteracji.
- `recomputeDerivedProgram()` w `SessionContext.tsx` — wylicza
  `target_count` z `totalUnits` i `percentage`. Zmienia źródło
  `totalUnits` z pola na wyliczenie.
- `ProgramSection.tsx` — pole `totalUnits` (input, linia ~39) do usunięcia,
  suwak `w` do dodania.
- Endpoint `/layout/units` i `/layout/generate` — OBIE ścieżki muszą
  dostać iteracje (gotcha „dual layout API surface").

## Sekcja 1 — liczba mieszkań z powierzchni

Średnia wielkość mieszkania ze struktury:

```
avg_m2 = Σ (percentage_i / 100) · (area_min_i + area_max_i) / 2
```

Liczba mieszkań: `totalUnits = max(1, floor(net_remainder_m2 / avg_m2))`,
gdzie `net_remainder_m2` = powierzchnia remainder po odjęciu pasów ścian
(netto, spójnie z `net_area_m2` już liczonym).

Liczy BACKEND (ma dokładny remainder); zwraca w odpowiedzi
`derived_total_units: int` + `net_remainder_m2: float`. Frontend pokazuje
w panelu Program: „≈ N mieszkań (z M m² netto)". `target_count` per typ
dalej wylicza `recomputeDerivedProgram`, ale z `derived_total_units`
zamiast pola input. Gdy brak obrysu/komunikacji — panel pokazuje „—"
(bez liczby), przycisk podziału nieaktywny.

Zaokrąglanie sztuk per typ: largest-remainder (suma sztuk = totalUnits,
bez dryfu z zaokrągleń).

## Sekcja 2 — iteracje z seedem

`subdivide_units()` dostaje parametry `iterations: int = 10` i `weights`
(7 wag z Sekcji 4). Pętla po `seed in range(iterations)`:

1. `rng = random.Random(seed)`.
2. Tasowanie: kolejność kolejki specyfikacji (`rng.shuffle`) i kolejność
   kandydujących prostokątów przy wyborze cięcia.
3. Przebieg `fit_program_to_rectangles` (z losowością z pkt 2).
4. Doklejenie resztek (Sekcja 3).
5. Scoring (Sekcja 4).

Wynik: najlepsza iteracja (najniższy score) jako właściwy układ +
metadane wszystkich: `iterations: [{seed, score, units_count,
structure_dev, size_dev}]`.

## Sekcja 3 — zero resztek

Po dopasowaniu programu każda część leftover (może być MultiPolygon —
iterujemy po `geoms`):

1. Znajdź sąsiadujące mieszkanie o najdłuższej wspólnej krawędzi
   (`shared boundary length` przez `intersection` obwodów).
2. Doklej część do tego mieszkania (`unary_union`), zaktualizuj
   `area_m2`.
3. Część bez żadnego sąsiada-mieszkania (np. enklawa za klatką):
   doklej do najbliższego mieszkania (min odległość geometrii) —
   mieszkanie może wtedy być niespójne (MultiPolygon); oznacz
   `ApartmentCell.merged_disjoint = True` (kara +0.5 w komponencie
   `adjacency` scoringu, widoczna flaga w odpowiedzi).
4. Powtarzaj aż leftover pusty. Po scaleniu `leftover = None` ZAWSZE
   (twarda gwarancja specu: cała powierzchnia przydzielona).

Mieszkanie rozepchane poza `area_max_m2` NIE jest błędem — odchylenie
łapie scoring.

## Sekcja 4 — scoring wielokryterialny (7 wag)

```
score = Σ wᵢ · devᵢ / Σ wᵢ          (mniejszy = lepszy; Σ wᵢ = 0 → score 0)
```

Każdy komponent `devᵢ` znormalizowany do ~[0,1] (0 = idealnie). Wagi `wᵢ`
z suwaków 0–1 w panelu Program (mapowanie ze screena Finch „Unit weights",
zaakceptowane 2026-07-04):

| Waga | Klucz API | Komponent devᵢ | Default |
|---|---|---|---|
| Size m² | `size` | średnie względne wyjście powierzchni poza przedział [min,max] typu: `max(0, min−a)/min` lub `max(0, a−max)/max` | 0.8 |
| Unit Mix | `mix` | L1 między docelowym a osiągniętym udziałem SZTUK per typ: `Σ\|target_share − actual_share\|` | 0.6 |
| Grid lines | `grid` | udział wierzchołków poligonów mieszkań leżących POZA siatką 0.5m (tolerancja 1e-6) | 0.3 |
| Shape aware | `shape` | średnio `1 − area / area(minimum_rotated_rectangle)` — kara za nieprostokątność | 0.5 |
| Daylight | `daylight` | udział mieszkań ze stykiem ze ścianą zewnętrzną krótszym niż **próg danego TYPU** (`min_facade_m`, edytowalny per wiersz struktury, domyślnie 3.0m — pomysł usera 2026-07-04 ze screena Finch „Min facade length"); czysto geometrycznie, moduł solar pozostaje WYŁĄCZONY | 0.7 |
| Squareness | `squareness` | średnio `min(1, (dłuższy_bok_bbox/krótszy − 1) / 1.5)` — 0 przy kwadracie, 1 przy proporcji ≥ 2.5:1 | 0.5 |
| Adjacency | `adjacency` | udział mieszkań BEZ styku z geometrią komunikacji (korytarz/klatka) — brak wejścia to najcięższa wada | 1.0 |

- Kara za `merged_disjoint` (enklawa doklejona bez wspólnej krawędzi):
  +0.5 do komponentu `adjacency` danego mieszkania (przed uśrednieniem).
- `daylight` i `adjacency` wymagają obrysu i geometrii komunikacji —
  request `/layout/units` już je niesie (`footprint`,
  `circulation_geometry`, oba opcjonalne). Gdy brak → te dwa komponenty
  liczone jako 0 i pomijane w Σwᵢ (bez karania w ciemno).
- Wagi wysyłane w request do `/layout/units` i `/layout/generate` jako
  obiekt `weights: {size, mix, grid, shape, daylight, squareness,
  adjacency}` (floaty 0–1, defaulty jak w tabeli).

## Sekcja 5 — API i frontend

Request (`UnitsRequest` i `LayoutGenerateRequest`): `iterations: int = 10`
(zakres 1–50), `weights: {size, mix, grid, shape, daylight, squareness,
adjacency}` (floaty 0–1, defaulty z tabeli Sekcji 4).

Response (obie ścieżki — dual-surface gotcha):

```
derived_total_units: int
net_remainder_m2: float
iterations: [{ seed: int, score: float, units_count: int,
               structure_dev: float, size_dev: float }]
best_seed: int
```

`apartments` w odpowiedzi = wynik najlepszej iteracji. `leftover` znika
z odpowiedzi jako geometria (zawsze None) — pole zostaje dla
kompatybilności, zawsze null.

Panel Program (`ProgramSection.tsx`):
- pole input `totalUnits` USUNIĘTE → tekst readonly „≈ N mieszkań
  (M m² netto)";
- każdy wiersz struktury dostaje pole „Min. styk z elewacją [m]"
  (`min_facade_m`, krok 0.5, domyślnie 3.0) — zasila próg komponentu
  `daylight` dla mieszkań tego typu;
- sekcja „Wagi" — 7 suwaków (0–1, krok 0.05) jak na screenie Finch:
  Size m², Unit Mix, Grid lines, Shape aware, Daylight, Squareness,
  Adjacency, z defaultami z tabeli Sekcji 4;
- po podziale: lista 10 iteracji „#seed — score — liczba mieszkań",
  najlepsza podświetlona (licznik iteracji, którego chciał user).

`SET_TOTAL_UNITS`/`state.totalUnits` w `SessionContext`: zastąpione
wartością z backendu (`derived_total_units` po każdej odpowiedzi);
`recomputeDerivedProgram` bez zmian koncepcji.

## Sekcja 6 — przypadki brzegowe

- Remainder mniejszy niż najmniejsze `area_min` w strukturze:
  `totalUnits = 1`, jedno mieszkanie = cały remainder (dowolny typ
  o najbliższej wielkości), score odzwierciedla odchylenie.
- Struktura sumująca się ≠ 100%: istniejące ostrzeżenie w panelu
  zostaje; backend normalizuje udziały do sumy (proporcjonalnie).
- Wszystkie wiersze 0%: 422 z komunikatem (nie ma z czego liczyć).
- `iterations = 1`: działa (jedna iteracja, lista 1-elementowa).

## Sekcja 7 — weryfikacja

Backend: testy pytest w `backend/tests/test_unit_iterations.py`:
determinizm (ten sam seed → ten sam wynik), zero-leftover na obrysie L
z klatką, largest-remainder (suma sztuk = totalUnits), skrajne wagi
(tylko `mix`=1 vs tylko `size`=1 dają score równy odpowiednio
structure/size-komponentowi), komponenty geometryczne (grid/shape/
squareness) na spreparowanych poligonach, enklawa → merged_disjoint
podbija `adjacency`.

Frontend ręcznie:
1. Mały obrys (np. 12×10m) → kilka mieszkań; duży (40×15m) →
   kilkanaście+ — liczba skaluje się z powierzchnią.
2. Pole liczby mieszkań zniknęło; widać „≈ N mieszkań".
3. Po „Generuj układ": lista 10 iteracji ze score, najlepsza
   podświetlona; canvas pokazuje najlepszą.
4. Skrajne ustawienia wag (np. adjacency=1 reszta=0 vs size=1 reszta=0)
   → widocznie inne zwycięskie układy/score.
5. Zero szarych dziur między mieszkaniami a ścianami — cała powierzchnia
   pokryta (mieszkania/komunikacja/ściany).
