# Etap 2: Ręczne rysowanie klatek schodowych i korytarzy

**Data**: 2026-07-04
**Status**: zaakceptowany (brainstorming z userem)
**Poprzedza**: spec 2026-07-04-footprint-editing-ux (Etap 0+1)
**Następuje po nim**: spec 2026-07-04-evacuation-dots (Etap 3, zależy od modelu z tego specu)

## Kontekst i cel

User rysuje komunikację ręcznie: klatkę schodową jako dowolny wielokąt
(punktami, jak obrys budynku) i korytarz jako łamaną-oś (szerokość w świetle
z panelu). Elementy ręczne WSPÓŁISTNIEJĄ z auto-rozmieszczaniem
(`num_cages`, przycisk „Rozmieść komunikację"): manual dokłada się do
istniejącego wyniku, każdy element ręczny da się osobno usunąć.

Decyzje z brainstormingu:

1. Klatka: rysowanie punktami jak obrys (klik-klik-dblclick, min 3 punkty,
   snap 0.5m). Bez trybu prostokątnego.
2. Korytarz: rysowanie osi (łamana, min 2 punkty, snap 0.5m); szerokość
   w świetle z istniejącego pola `corridor_width_m` w panelu Komunikacja.
3. Współistnienie: manual DODAJE do aktualnej komunikacji. Elementy manualne
   przeżywają ponowne auto-rozmieszczenie (są dokładane zawsze na końcu);
   znikają wyłącznie przez usunięcie z listy w panelu.
4. Architektura: backend liczy całą geometrię (podejście A) — frontend
   zbiera punkty i renderuje; merge, buffer osi, remainder i centerline
   robi Python.

## Co już istnieje (reużywane)

- Rysowanie punktami ze snapem: tryb `draw` w `CanvasEditor.tsx`
  (handleStageClick/handleStageDblClick, drawingPoints).
- Model osi korytarza: `CorridorCenterlineSegment` w
  `backend/services/circulation.py`, edycja frontendowa (dblclick/drag)
  i `/layout/circulation/reshape`.
- Ściany 20cm klatek/korytarzy: `wall_geometry.py` — komórki komunikacji
  przechodzą przez `interior_wall_bands` jak mieszkania; NIC do zrobienia.
- Auto-placement: `place_circulation()` z `num_cages`.

## Sekcja 1 — UI i tryby rysowania

Panel Komunikacja (`CirculationSection.tsx`) dostaje dwa przyciski:
**„Rysuj klatkę"** i **„Rysuj korytarz"**. Nowe wartości `EditorMode`:
`"draw-cage"` i `"draw-corridor"` (obok istniejących).

- `draw-cage`: klik dodaje punkt (snap 0.5m), dblclick zamyka wielokąt —
  wymaga min 3 punktów; w trakcie rysowania dashed podgląd jak przy obrysie.
- `draw-corridor`: klik dodaje punkt osi, dblclick kończy łamaną — wymaga
  min 2 punktów; podgląd: dashed łamana + półprzezroczysty pas o szerokości
  `corridor_width_m` wokół niej.
- Esc/przycisk przerywa rysowanie (czyści punkty robocze, wraca do idle) —
  ta sama semantyka co przy rysowaniu obrysu.

## Sekcja 2 — stan frontendu

`SessionContext` dostaje listy elementów manualnych:

```ts
manualCages: { id: string; ring: Point2D[] }[]
manualCorridors: { id: string; path: Point2D[] }[]
```

Akcje: `ADD_MANUAL_CAGE`, `ADD_MANUAL_CORRIDOR`, `REMOVE_MANUAL_ELEMENT`
(po id). Każda zmiana list unieważnia `circulationResult`/`layoutResult`/
`validation` (wzorzec UPDATE_VERTEX) i wywołuje ponowne
`runPlaceCirculation()` — komunikacja przelicza się od razu, bo elementy
manualne mają sens tylko w połączeniu z wynikiem backendu.

Panel Komunikacja renderuje listę elementów: „Klatka 1", „Klatka 2",
„Korytarz 1"… z przyciskiem usuń (ikona kosza) przy każdym. Hover na
pozycji listy podświetla odpowiadającą geometrię na canvasie (kolor
akcentu #60a5fa).

## Sekcja 3 — API i backend

`CirculationSpecInput` (frontend `api.ts`) i odpowiadający mu model
Pydantic dostają:

```
manual_cages: list[list[[x, y]]]      # ringi wielokątów (bez duplikatu 1. punktu)
manual_corridors: list[list[[x, y]]]  # łamane osi
```

`place_circulation()` po dotychczasowej pracy (auto-klatki gdy
`num_cages > 0`, auto-korytarz) dokłada elementy manualne:

1. Każdy ring z `manual_cages` → `Polygon` → dołączony do `cage_polygons`
   i do unii `circulation_geometry`.
2. Każda łamana z `manual_corridors` → `LineString.buffer(width/2,
   cap_style="flat")` → poligon korytarza dołączony do unii
   `circulation_geometry`; łamana wchodzi do `centerline` jako segmenty
   (z tym samym liczeniem odległości co segmenty auto).
3. `remainder` = footprint minus cała zunifikowana komunikacja
   (istniejąca ścieżka przeliczenia — bez zmian logiki).

`num_cages = 0` + brak auto-korytarza + elementy manualne = układ w pełni
ręczny; ta sama ścieżka kodu.

## Sekcja 4 — walidacja i przypadki brzegowe

- Klatka wystająca poza obrys (ring nie zawiera się w footprincie):
  odrzucona — HTTP 422 z komunikatem; frontend pokazuje błąd w panelu
  i NIE dodaje elementu do listy.
- Oś korytarza wychodząca poza obrys: pas korytarza przycinany do
  footprintu (intersection) — bez błędu; oś poza obrysem po prostu nie
  produkuje geometrii.
- Korytarz niedotykający żadnej klatki: DOZWOLONY (bez błędu) — Etap 3
  pokaże czerwone kropki; panel pokazuje miękkie ostrzeżenie
  („Korytarz N nie styka się z żadną klatką").
- Nakładanie się elementów (klatka na korytarzu, korytarz na korytarzu):
  dozwolone — unia geometrii to naturalnie skleja.
- Ręczna klatka nachodząca na auto-klatkę: dozwolone (unia); user widzi
  wynik i sam poprawia.

## Sekcja 5 — weryfikacja (ręczna)

1. „Rysuj klatkę" → 4 kliki + dblclick → klatka pojawia się na canvasie,
   w liście panelu „Klatka 1"; wall_bands 20cm wokół niej po generacji.
2. „Rysuj korytarz" → łamana 3-punktowa + dblclick → pas korytarza
   o szerokości z panelu, oś edytowalna (dblclick/drag jak auto-oś).
3. Auto „Rozmieść komunikację" przy istniejących elementach manualnych →
   auto-wynik się zmienia, manualne zostają.
4. Usunięcie elementu z listy → geometria znika, remainder rośnie.
5. Klatka narysowana częściowo poza obrysem → błąd w panelu, brak elementu.
6. Regresja: auto-placement bez manuali, edycja osi auto-korytarza,
   `/layout/units` na remainder z manualami — działają.
