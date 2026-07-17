# Typologia klatkowa — wiedza referencyjna

Destylacja 6 rzutów konkursowych budynków wielorodzinnych dostarczonych przez
usera 2026-07-16 (czat, screenshoty). Nazewnictwo: Pd/Pm = pokój duży/mały
(2Pd ≈ 50-58 m², 2Pm ≈ 42-52 m²), P1/1P ≈ 25-37 m², 3P/P3 ≈ 60-67 m².

## Przeanalizowane wzorce

| # | Typ | Wymiary | Mieszkań/klatkę | Komunikacja | Uwagi |
|---|-----|---------|-----------------|-------------|-------|
| 1 | punktowiec | ~mały | 4-6 | sam trzon | mieszkania opasują trzon z 4 stron |
| 2 | punktowiec | ~17×20 m | 6 | 48.7 m² / 364.9 m² = 13.3% | klatka+winda W ŚRODKU rzutu, bez światła; lustrzana symetria; parter: wózkownia 17 + wiatrołap 11.7 |
| 3 | klatkowiec TYP1/TYP2 | 23.0×13.75 m | 4-5 | trzon + mały hol | TYP1 klatka centralna, P2d przewietrzane na przestrzał; TYP2 klatka przy PÓŁNOCNEJ elewacji |
| 4 | korytarzowiec B/B1 | 16.98×36.18 m | 8-9 | korytarz podłużny | budynek DŁUGI → 1 klatka + korytarz się opłaca; trakty ~7 m; obok mikro-klatkowce B.1/Bo.2: 2 mieszkania/poziom (1p 28-34 m²) |
| 5 | klatkowiec BA/AC | średni | 5 | ~25 m² ≈ 9% | najefektywniejszy wzorzec: mieszkania "wiatraczkiem", każde dotyka trzonu; parter traci 1 mieszkanie na wózkownię/śmietnik/rowerownię |
| 6 | hybryda TYP C | 30.44 m dł. | 6 | klatka + KRÓTKI korytarz | klatka przy północnej elewacji, korytarz obsługuje 6 mieszkań w limicie dojścia jednokierunkowego |

## Wyciągnięte reguły (potwierdzone przez usera)

1. **Klatkowiec: komunikacja 9-13% powierzchni kondygnacji** (25-49 m²/poziom
   dla 4-6 mieszkań). To główny zysk vs korytarzowiec.
2. **Głębokość budynku klatkowca: 13-17 m** — za dużo na korytarzowiec
   jednostronny (trakt >7 m), w sam raz żeby mieszkania opasały trzon i były
   narożne / przewietrzane na przestrzał.
3. **Pozycja klatki:** centralnie bez okien (punktowiec) ALBO dosunięta do
   północnej elewacji — nigdy nie zjada południa. Spójne z istniejącą wagą
   `light_waste`.
4. **Wejścia do mieszkań bezpośrednio z holu klatki** (hol 15-25 m²); każde
   mieszkanie MUSI dotykać trzonu (cage+hol) — odpowiednik hard-banu "styk
   z komunikacją".
5. **Liczba mieszkań na klatkę bez korytarza: zwykle 1-5(6), ALE bez sztywnego
   limitu** (user 2026-07-16: "nie trzymajmy się sztywno jakiegoś limitu") —
   wynik rachunku geometrii, nie stała.
6. **Korytarz wygrywa gdy:** skrzydło długie (>25-30 m) i jedna klatka ma
   obsłużyć >6 mieszkań, albo trakt gruby (~16 m) — korytarz środkiem.
7. **Decyzja klatka-vs-korytarz to rachunek, nie reguła 0/1** (user):
   porównanie wariantów wspólną funkcją kosztu — udział komunikacji, jakość
   mieszkań (narożność, przewietrzanie, proporcje), liczba klatek, ewakuacja.
8. **Hybrydy są legalne** (wzorzec 6): krótki korytarz doklejony do klatki,
   gdy dojścia mieszczą się w limicie jednokierunkowym; w budynkach L/U
   każde ramię może dostać INNY tryb.
9. **Parter ≠ kondygnacja powtarzalna:** wiatrołap + wózkownia/rowerownia
   kosztem jednego mieszkania (backlog — nie w MVP trybu klatkowego).
