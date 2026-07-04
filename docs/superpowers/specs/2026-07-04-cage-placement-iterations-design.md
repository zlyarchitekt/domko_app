# Etap 2b: Iteracyjny auto-placement klatek schodowych ze scoringiem

**Data**: 2026-07-04
**Status**: zaakceptowany (review usera — screen „Filter/Egress/Weights"
z Finch3D, propozycja mapowania przyjęta bez uwag)
**Zależy od**: Etap 3 (moduł `evacuation.py` — scoring dojść liczy kropki),
Etap 2 (elementy manualne dokładane PO wyniku iteracyjnym, bez zmian).
**Kolejność wdrożeń**: 2 → 3 → 2b → 4.

## Kontekst i cel

Dzisiejszy auto-placement (`place_circulation` + `_place_cage_by_mode`,
tryby "1a"/"1b"/"2"/"3"/"auto") stawia klatki deterministycznie według
jednej reguły na strefę. User chce trybu iteracyjnego wzorowanego na
Finch3D: 10 iteracji proponujących RÓŻNE lokalizacje klatek, ocenianych
wagami, z wyborem najlepszej i licznikiem iteracji w panelu.

Stary tryb ZOSTAJE (przycisk „Umieść korytarz i klatkę" bez zmian).
Dochodzi nowy przycisk **„Rozmieść iteracyjnie"**.

## Sekcja 1 — parametry (panel Komunikacja)

- **Filtr**: `num_cages` — istniejący suwak; iteracje losują liczbę klatek
  z zakresu 1..num_cages (num_cages = górny limit, nie sztywna liczba).
- **Limity dojść**: `max_dist_single_m` / `max_dist_multi_m` — WSPÓLNE
  pola z Etapem 3 (te same wartości sterują kropkami i scoringiem).
- „Shared path ≤" (wspólna droga ewakuacyjna z Finch): świadomie
  POMINIĘTE — wymaga analizy rozłączności dróg w grafie, odrzuconej już
  przy projektowaniu kropek (Etap 3, decyzja 1). Odnotowane jako
  potencjalne rozszerzenie.

## Sekcja 2 — wagi scoringu (suwaki 0–1)

```
cage_score = Σ wᵢ · devᵢ / Σ wᵢ      (mniejszy = lepszy; Σ wᵢ = 0 → 0)
```

| Waga (Finch) | Klucz API | Komponent devᵢ (0 = idealnie) | Default |
|---|---|---|---|
| Minimize invalid egress distances | `egress` | udział kropek czerwonych w całej sieci (z `compute_evacuation_dots` przy progach z Sekcji 1) | 1.0 |
| Minimize number of stairwells | `count` | `liczba_klatek / num_cages` — mniej klatek spełniających resztę kryteriów = lepiej | 0.5 |
| Place stairwells in corners | `corners` | średnia po klatkach: odległość centroidu klatki do najbliższego narożnika obrysu / (przekątna_bbox_obrysu / 2), cap 1 | 0.3 |
| Place stairwells on ends | `ends` | średnia po klatkach: odległość rzutu centroidu na dłuższą oś bbox obrysu do bliższego końca tej osi / (długość_osi / 2), cap 1 | 0.3 |
| Even distribution of stairwells | `spread` | dla klatek posortowanych wzdłuż dłuższej osi: znormalizowane odchylenie odstępów od idealnie równych; 0 dla 1 klatki | 0.5 |

`corners` i `ends` celowo konkurują — user balansuje suwakami.

## Sekcja 3 — algorytm iteracji

Nowy moduł `backend/services/cage_placement.py` (czyste funkcje):

1. **Pula kandydatów pozycji klatki** (punkty kotwiczenia, po net-obrysie):
   4 narożniki bbox każdej strefy (`rectangle_decompose`), środki krawędzi
   stref, punkty co ~5m wzdłuż lica wewnętrznego obrysu. Kandydat = pozycja
   prostokąta klatki `CAGE_WIDTH_M × CAGE_DEPTH_M` (obie orientacje);
   odrzucany, gdy klatka nie mieści się w obrysie lub koliduje z już
   wybraną klatką tej iteracji.
2. **Iteracja** `seed ∈ 0..9` (`random.Random(seed)`):
   - `k = rng.randint(1, num_cages)`;
   - losowy wybór `k` kandydatów bez kolizji;
   - korytarz: istniejący pipeline (`_build_corridor` per strefa z
     wylosowanymi klatkami) — bez zmian mechaniki;
   - centerline + `compute_evacuation_dots` (progi z Sekcji 1);
   - `cage_score` wg Sekcji 2.
3. **Wynik**: `CirculationResult` najlepszej iteracji + metadane
   `cage_iterations: [{seed, score, cages_count, egress_dev, count_dev,
   corners_dev, ends_dev, spread_dev}]` + `best_seed`.
4. Elementy manualne (Etap 2) dokładane PO wyborze najlepszej iteracji —
   ta sama ścieżka merge co przy trybie klasycznym.

Determinizm: te same wejścia → te same wyniki (seed per iteracja).

## Sekcja 4 — API

`CirculationSpec` dostaje:

```
cage_iterations: int = 0        # 0 = tryb klasyczny (dzisiejszy), >0 = iteracyjny
cage_weights: { egress: 1.0, count: 0.5, corners: 0.3, ends: 0.3, spread: 0.5 }
```

`CirculationResponse` (i `/layout/generate` — dual-surface gotcha):

```
cage_iterations: [{seed, score, cages_count, ...dev per komponent}]
cage_best_seed: int
```

Puste/0 przy trybie klasycznym. Przycisk „Rozmieść iteracyjnie" =
`runPlaceCirculation` z `cage_iterations: 10`.

## Sekcja 5 — frontend

Panel Komunikacja:
- przycisk **„Rozmieść iteracyjnie"** obok istniejącego (aktywny gdy jest
  obrys);
- 5 suwaków wag (0–1, krok 0.05) z defaultami z Sekcji 2, zwinięte w
  sekcję „Wagi klatek" (rozwijaną — panel już jest gęsty);
- lista iteracji „#seed — score — liczba klatek", najlepsza podświetlona
  (ten sam wzorzec co lista iteracji mieszkań, Etap 4).

Canvas: bez nowych elementów — wynik renderuje się jak każdy
`circulationResult` (klatki, korytarz, oś, kropki z Etapu 3).

## Sekcja 6 — przypadki brzegowe

- Zero kandydatów mieszczących klatkę (obrys mniejszy niż klatka):
  422 z komunikatem („Obrys zbyt mały na klatkę schodową").
- Wszystkie wagi 0: score 0 dla każdej iteracji — wygrywa seed 0
  (stabilnie, deterministycznie).
- `num_cages = 1`: iteracje różnią się tylko pozycją jednej klatki.
- Obrys wklęsły: kandydaci per strefa po `rectangle_decompose` —
  mechanizm identyczny jak dziś.

## Sekcja 7 — weryfikacja

Backend: testy pytest w `backend/tests/test_cage_placement.py`:
determinizm, respektowanie filtra (nigdy > num_cages), kandydaci nie
wystają z obrysu, `egress`-waga=1 wybiera układ z mniejszą liczbą
czerwonych kropek na spreparowanym przypadku, `spread` preferuje klatki
rozsunięte, 422 dla obrysu mniejszego od klatki.

Frontend ręcznie:
1. „Rozmieść iteracyjnie" na prostokącie 40×12, num_cages=3 → lista 10
   iteracji, najlepsza podświetlona, klatki w sensownych miejscach.
2. `egress=1`, reszta 0 → wynik z minimalną liczbą czerwonych kropek.
3. `corners=1`, reszta 0 → klatki w narożnikach; `ends=1` → na końcach.
4. Zmiana progów dojść (Etap 3) + ponowne „Rozmieść iteracyjnie" →
   inny zwycięzca, spójny z kropkami.
5. Stary przycisk „Umieść korytarz i klatkę" działa jak dotychczas.
6. Manuale przeżywają rozmieszczenie iteracyjne.
