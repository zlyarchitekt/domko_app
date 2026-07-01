# DOMKO_APP — Rejestr zadań Kanban (SKORYGOWANY PO AUDYCIE KODU)

> **Projekt:** DOMKO_APP
> **Repo:** https://github.com/zlyarchitekt/domko_app
> **Kod lokalny:** `C:\Praca\01 AI\HERMES\DOMKO_APP\`
> **Board Kanban:** `domko`
> **Ostatnia aktualizacja:** 2026-07-01 — audyt kodu wykazał, że poprzednia wersja tego pliku (57/58 „done”) nie odzwierciedlała stanu repozytorium. Statusy i opisy poniżej zostały skorygowane na podstawie realnego czytania kodu (backend + frontend), nie deklaracji. **2026-07-01 (later): Fala 1 planu naprawczego wykonana** — F0-02, F0-07, F3-07, F4-09, F5-07 naprawione i zweryfikowane (`pytest` 30/30, smoke-testy end-to-end wszystkich trzech wcześniej martwych routerów). Zobacz sekcję „Plan naprawczy” na końcu pliku.

## Legenda statusów

| Symbol | Znaczenie |
|---|---|
| ✅ **done** | Zweryfikowane: kod istnieje, jest zarejestrowany/osiągalny i pokryty testami, które przechodzą |
| 🔧 **do zrobienia (częściowe)** | Fragment kodu istnieje, ale jest niekompletny, odłączony (nie zarejestrowany) lub zawiera błędy blokujące działanie |
| ❌ **do zrobienia** | Brak jakiejkolwiek implementacji |
| ⏸️ **blocked** | Zależne od zewnętrznego inputu (nie od developera) |
| 🆕 | Nowe zadanie, dodane po audycie — brakowało go w oryginalnym WBS |

## Priorytety naprawcze

| Priorytet | Znaczenie |
|---|---|
| **P0** | Bloker krytyczny — naprawia martwy/niedziałający kod, musi wejść PRZED czymkolwiek innym w danej fazie |
| **P1** | Rdzeń MVP wg `plan.md` |
| **P2** | Dopracowanie, niższy priorytet, można przesunąć poza pierwszą iterację |

## Podsumowanie

| Status | Liczba |
|--------|--------|
| ✅ done | 22 |
| 🔧 do zrobienia (częściowe) | 12 |
| ❌ do zrobienia | 34 |
| ⏸️ blocked | 1 |
| **Razem** | **69** |

> Stan po wykonaniu Fali 1 (2026-07-01): +5 zadań przeszło na ✅ (F0-02, F0-07, F3-07, F4-09, F5-07), status kilku zależnych zadań się poprawił (F3-02 → ✅, F3-04/F4-03/F4-04/F5-01/F5-02 → odblokowane, niektóre → ✅), a jedno wcześniej ✅ (F0-05) obniżono do 🔧 po odkryciu, że lokalny `ruff check .` zwraca 110 pre-istniejących błędów niezwiązanych z tą sesją napraw.
>
> Stan po Fali 2 (2026-07-01, w toku): F1-01, F1-08 → ✅ (import DXF + 8 testów). F3-01 → ✅ (realny `wt_validation.py` z Dijkstrą — przepisany od zera). F3-03 → ✅ (nowy endpoint `/validate/communication`). F3-04 → ✅ (agregacja wszystkich trzech warstw walidacji). F2-13 → ✅ (presety typologii). F2-14 → 🔧 (backend gotowy, brakuje UI sidebaru z Fali 3). F2-04 → 🔧, znacząco rozbudowane (tryby klatki 1a/1b/2/3/auto + naprawione dopasowanie do programu + 2 dodatkowe pre-istniejące bugi geometrii). F2-06 → ✅ (endpoint split). Pełny pakiet 85/85 zielony.

---

## Krytyczne ustalenia audytu (przeczytaj przed rozpoczęciem pracy)

1. ~~**`backend/api/v1/router.py` nie rejestruje routerów `validate`, `solar`, `optimizer`.**~~ **NAPRAWIONE w Fali 1 (2026-07-01).** Wszystkie trzy routery zarejestrowane i zweryfikowane end-to-end.
2. ~~**`backend/services/apartment_validation.py` nie istnieje**~~ **NAPRAWIONE w Fali 1** — moduł utworzony z realną implementacją (patrz F3-07).
3. ~~**Funkcje `azimuth_to_cardinal()` i `sunlight_adjustment_factor()` nie istnieją**~~ **NAPRAWIONE w Fali 1** — obie funkcje + `_estimate_building_azimuth()` dodane do `services/layout.py` (patrz F4-09).
4. ~~**`LayoutResult` nie ma pól `footprint_polygon` ani `building_azimuth_deg`**~~ **NAPRAWIONE w Fali 1** — `solar_analysis.py` poprawiony na `layout.footprint`, `building_azimuth_deg` dodane jako pole `LayoutResult` (patrz F4-09).
5. ~~**`backend/requirements.txt` nie zawiera pvlib/pandas/numpy/networkx/scipy/pymoo/weasyprint/reportlab**~~ **NAPRAWIONE w Fali 1** (patrz F0-07) — z wyjątkiem `scipy`, celowo pominiętego (nieużywany import usunięty zamiast dodania martwej zależności, patrz F5-01/F5-07).
6. **Frontend (`frontend/app/`) to w praktyce jeden plik `CanvasEditor.tsx`** renderujący na sztywno wpisane dane demo (`bsp/sampleData.ts`). Zero wywołań `fetch()`/`axios` w całym frontendzie — brak jakiejkolwiek integracji z backendem, brak sidebaru, brak formularzy, brak mapy. **Wciąż aktualne** — frontend nie był w zakresie Fali 1, zaplanowany na Falę 3 (F2-15 i dalej).
7. **`docker-compose.yml` nie istnieje nigdzie w repo**, `backend/Dockerfile` też nie (jest tylko `frontend/Dockerfile`) — mimo że F0-04 był oznaczony jako done. **Wciąż aktualne**, nie było w zakresie Fali 1.
8. **`typologies.md` (presety BSP + heurystyka auto-detekcji) nie ma żadnego odzwierciedlenia w kodzie** — potwierdzone przeszukaniem grafu kodu. **Wciąż aktualne**, zaplanowane na Falę 2 (F2-13/F2-14).
9. ~~**`optimizer.py` importuje `scipy.optimize.milp`, ale nigdzie go nie wywołuje**~~ **ROZWIĄZANE w Fali 1** — nieużywany import usunięty, metoda przemianowana na `"heuristic-search"` (uczciwa nazwa zamiast mylącego `"lp"`). Patrz F5-01/F5-07.
10. **Zadania E2E (Faza 7) zakładają istnienie frameworka testowego (Playwright/Cypress), którego w repo nie ma w ogóle.** **Wciąż aktualne**, zaplanowane na Falę 5 (F7-07/F7-08).
11. 🆕 **[Odkryte w Fali 1]** `optimizer.py`'s `_evaluate_variant()` odwoływało się do `wt.rules` — atrybutu, który nigdy nie istniał na `WTValidationResult` (tylko `passed`/`daylight_min_hours`/`noise_max_db`/`issues`). Każde wywołanie funkcji rzucałoby `AttributeError` w runtime (nie tylko przy imporcie). Naprawione tymczasowym proxy 0/1 opartym na `wt.passed`, do wzbogacenia po F3-01.
12. 🆕 **[Odkryte w Fali 1]** Lokalny `ruff check .` zwraca 110 pre-istniejących błędów lint (głównie `UP006`, `I001`) w plikach nietkniętych podczas Fali 1 — sugeruje, że CI `lint-backend` (F0-05) mógł już wcześniej nie przechodzić, niezależnie od tej sesji napraw. Wymaga osobnego zadania porządkowego (nieplanowanego dotąd w WBS).

---

## Faza 0 — Setup projektu

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_1b20e5dd` | **F0-01** | ✅ done | — | Inicjalizacja repo — monorepo /frontend + /backend, git init, .gitignore. Zweryfikowane. |
| `t_108f6061` | **F0-02** | ✅ done | — | **[Fala 1, 2026-07-01]** Backend setup naprawiony: `GET /health` i `GET /api/health` oba odpowiadają 200 (`main.py`, dwa stackowane dekoratory na jednej funkcji, pokryte `test_health.py`). Świeży `pip install -r requirements.txt` w istniejącym `.venv` przeszedł bez konfliktów (patrz F0-07), `pytest` → 30/30 zielone. |
| `t_54eb0255` | **F0-03** | 🔧 częściowe | P1 | Frontend setup. **Co działa:** Next.js 14 App Router, `react-konva`, `konva`, Tailwind zainstalowane. **Czego brakuje:** `leaflet`/`react-leaflet` nie ma w `package.json` (potrzebne w F4-01); `page.tsx` renderuje na sztywno `sampleBspResult` zamiast realnie pustego stanu — dane demo powinny być dostępne wyłącznie jako tryb deweloperski (np. `?demo=1`), nie domyślny ekran startowy. **Kryterium ukończenia:** aplikacja przy starcie pokazuje pusty canvas (bez danych mieszkań), z opcją wczytania danych demo jawnie zaznaczoną w UI. Nietknięte w Fali 1 (frontend — Fala 3). |
| `t_2ac7f5d3` | **F0-04** | ❌ do zrobienia | P0 | Docker Compose. **Stan faktyczny:** `docker-compose.yml` nie istnieje w całym repo; `backend/Dockerfile` nie istnieje (jest tylko `frontend/Dockerfile`). `docker compose up` nie ma szans zadziałać. **Kryterium ukończenia:** jedna komenda `docker compose up` stawia backend (uvicorn, hot-reload) + frontend (next dev) z połączeniem między nimi (`NEXT_PUBLIC_API_URL` lub proxy), zweryfikowane realnym uruchomieniem. Nietknięte w Fali 1 (nie blokowało odblokowania kodu). |
| `t_1a01e210` | **F0-05** | 🔧 częściowe | P2 | CI — `.github/workflows/ci.yml` uruchamia `ruff check .`, `pytest`, `next lint`. **Nowe ustalenie z Fali 1:** `ruff check .` lokalnie zwraca 110 pre-istniejących błędów (głównie `UP006` `List`/`Tuple`→`list`/`tuple`, `I001` sortowanie importów) w plikach nietkniętych podczas naprawy (m.in. `tests/test_export_dxf.py`, starsze fragmenty `solar_analysis.py`) — **CI prawdopodobnie już dziś nie przechodzi lint-backend**, niezależnie od zmian w tej sesji (zweryfikowane: pliki naprawiane w Fali 1 są czyste, 0 nowych błędów). Do posprzątania jako osobne zadanie porządkowe, nie blokuje Fali 1-2. |
| `t_15f92401` | **F0-06** | ✅ done | — | Struktura folderów backendu (`models/`, `services/`, `api/`, `tests/`) istnieje, choć granulacja plików różni się od dosłownego układu z planu §3.3 (to nie problem — struktura jest spójna i sensowna). |
| `t_new0001` | **F0-07** 🆕 | ✅ done | — | **[Fala 1, 2026-07-01]** `requirements.txt` uzupełniony o `pvlib==0.11.1`, `pandas==2.2.3`, `numpy==2.1.2`, `networkx==3.4.2`, `pymoo==0.6.1.3`, `reportlab==4.2.5`. **Decyzja developerska:** `scipy` NIE dodano — `optimizer.py` importował `scipy.optimize.milp`, ale nigdy go nie wywoływał (martwy import, usunięty w F5-07); gałąź „LP” to w rzeczywistości heurystyka, więc dodawanie nieużywanej zależności nie miało sensu. Wybrano `reportlab` zamiast `weasyprint` dla F6-05 (brak zależności systemowych GTK/Cairo na Windows). Świeży `pip install -r requirements.txt` przeszedł bez konfliktów wersji, `pytest` 30/30 zielone. |

---

## Faza 1 — Import i rysunek obrysu

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_12156cbc` | **F1-01** | ✅ done | — | **[Fala 2, 2026-07-01]** `POST /api/v1/footprint/import-dxf` zaimplementowany od zera w `services/dxf_import.py`: parsuje LWPOLYLINE, POLYLINE (stary styl) i HATCH (ścieżki polyline-type) z modelspace, wybiera **największy** zamknięty kandydat (heurystyka: obrys budynku to zwykle największy kształt na rysunku — dim/detal jest mniejszy), zwraca GeoJSON Polygon + `area_m2` + `dimensions` (bbox) + `source_entity_type`/`source_layer`/`candidate_count` do diagnostyki. Obsługa błędów: brak zamkniętych encji, samoprzecinający się poligon, uszkodzony/pusty plik, zła rozszerzenie. Wymagało dodania `python-multipart` do `requirements.txt` (FastAPI file upload). **Ograniczenie udokumentowane w kodzie:** dziury w HATCH i ścieżki oparte na łukach/splajnach nie są obsługiwane (poza zakresem MVP z planu). |
| `t_734af2a1` | **F1-02** | ✅ done | — | `/api/footprint/from-points` — pełna walidacja zamknięcia, self-intersection (`is_simple`/`is_ring`), duplikatów, NaN. Pokryte 7 testami w `test_footprint.py`, wszystkie przechodzą. |
| `t_49589533` | **F1-03** | ✅ done | — | Canvas z siatką 1m w `react-konva` (`CanvasEditor.tsx`), zoom na scroll, pan (draggable Stage), fit-to-screen i reset. Realnie zaimplementowane i działające. |
| `t_e5c6ec52` | **F1-04** | ❌ do zrobienia | P1 | Rysowanie wielokąta klik-po-klik. **Stan faktyczny:** `CanvasEditor.tsx` nie ma żadnej logiki dodawania punktów — komponent tylko renderuje gotowe dane z propsa. Do zbudowania od zera: tryb „rysuj”, stan bieżąco tworzonego wielokąta, snap do siatki 0.01m, zamknięcie dwuklikiem. |
| `t_d036f0e6` | **F1-05** | ❌ do zrobienia | P1 | Upload DXF drag&drop. Backend (`/api/footprint/import-dxf`) gotowy od Fali 2 (F1-01) — pozostaje wyłącznie zależność od ogólnej warstwy API frontendu (F2-15). Brak jakiejkolwiek strefy drop/file input w kodzie dziś. |
| `t_da5f31db` | **F1-06** | ❌ do zrobienia | P2 | Edycja wierzchołków obrysu — brak jakichkolwiek uchwytów (`Circle`/draggable vertex handles) w `CanvasEditor.tsx`. Do zbudowania od zera. |
| `t_f53dece3` | **F1-07** | ❌ do zrobienia | P1 | Sidebar z wymiarami boków i powierzchnią live — zależne od F2-01 (sam komponent sidebaru jeszcze nie istnieje). Bez sensu budować w oderwaniu od F2-01, zrobić razem. |
| `t_e0dfa965` | **F1-08** | ✅ done | — | **[Fala 2, 2026-07-01]** `tests/test_dxf_import.py` — 8 testów: prostokąt (LWPOLYLINE), L-kształt, wklęsły poligon przez stare POLYLINE, wybór największej encji spośród wielu warstw, granica HATCH, plik bez zamkniętych encji, zły format pliku, uszkodzony DXF. Wszystkie 8 przechodzą, pełny pakiet 38/38. |

---

## Faza 2 — Program i podział BSP

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_73eaaf1c` | **F2-01** | ❌ do zrobienia | P1 | Sidebar 320px z sekcjami Program/Komunikacja/Walidacja/Eksport — nie istnieje żaden taki komponent; cały frontend to `CanvasEditor.tsx` + `page.tsx` + `layout.tsx`. Budować od zera jako fundament dla F1-07, F2-02, F2-03, F3-05, F4-07. |
| `t_3b1b6790` | **F2-02** | ❌ do zrobienia | P1 | Formularz `ApartmentTypeRow` (typ M1–M5, liczba, docelowy m², bilans live) — brak jakiegokolwiek formularza w UI. `bsp/types.ts` ma tylko statyczne mapowanie kolorów typów ("1","2","3","4","studio","penthouse" — nawet nie nazewnictwo M1–M5 z planu), zero interaktywności. |
| `t_665a85d9` | **F2-03** | ❌ do zrobienia | P1 | Parametry komunikacji w sidebarze (pozycja klatki 1A/1B/2/3, toggle poza obrysem, wymiar 5.7×5.2m, max dojście, min odległość klatek, szerokość korytarza). Brak w UI. Backend też nie ma pojęcia „tryb pozycji klatki” — patrz F2-04. |
| `t_32791c41` | **F2-04** | 🔧 częściowe | P1 | **[Fala 2, 2026-07-01]** Duży postęp: (1) **tryby pozycji klatki 1A/1B/2/3/auto zaimplementowane** (`_place_cage_by_mode` w `services/layout.py`) — 1a=najdłuższa krawędź, 1b=najkrótsza krawędź (zamiennik „dziedzińca” — wykrywanie realnej krawędzi wewnętrznej wymagałoby modelu sąsiednich budynków, poza zakresem MVP), 2=środek strefy, 3/auto=narożnik wklęsły lub narożnik bounding-boxa. **Naprawiony kluczowy bug:** dla obrysów wypukłych klatka wcześniej nigdy nie powstawała mimo `place_cage=True` — teraz działa we wszystkich 5 trybach (zweryfikowane testami). (2) **Dopasowanie do programu naprawione dla podstawowego scenariusza** (klatkowiec wzdłużny, korytarz dwustronny): wymiar cięcia liczony z `min_area_m2/rzeczywista_głębokość_części`, nie z przybliżonych `width_m`/`depth_m` — zweryfikowane: 4 mieszkania trafiają dokładnie w cel 30m² (wcześniej dawało przypadkowe [148, 37, 37, 37] m²). Po drodze naprawiono **dwa dodatkowe pre-istniejące bugi** odkryte przy tej pracy: (a) `_slice_apartments` liczył głębokość z bounding-boxa całej `MultiPolygon` łącznie z przerwą na korytarz (błędne dla każdego dwustronnego układu!) — przepisano na cięcie naprzemienne (round-robin) per rozłączna część; (b) `_cut_cell` polegał na niegwarantowanej kolejności `shapely.split()`, czasem zwracając dużą resztę zamiast nowo wyciętej komórki — naprawione przez jawny wybór wg pozycji względem linii cięcia. **Nadal brakuje:** korytarz to nadal prosty prostokąt przez środek bbox, nie realny algorytm uwzględniający pozycję klatki; dopasowanie do programu dla obrysów wklęsłych (L/U-kształt) ma resztkową niedokładność związaną ze znanym problemem przyległości mieszkań (patrz F3-01/F3-03 audyt); realna walidacja WT jest już podłączona (F3-01), więc ten punkt jest zamknięty. Wystawione przez `/api/v1/layout/generate` (`circulation.cage_position`, z walidacją 400 dla błędnej wartości). 10 nowych testów w `test_cage_modes_and_fitting.py`, pełny pakiet 81/81. |
| `t_9e581f9d` | **F2-05** | ✅ done | — | Obsługa obrysów wklęsłych (L/U-kształt): `concave_vertices()`, `corner_cage()`, `bsp_zones()` w `services/bsp.py` — solidna, rekurencyjna implementacja, pokryta testami w `test_bsp.py` (L-shape, U-shape), wszystkie przechodzą. Jeden z niewielu fragmentów w pełni zgodnych z planem. |
| `t_f6ae35dd` | **F2-06** | ✅ done | — | **[Fala 2, 2026-07-01]** `POST /api/v1/layout/split` dodany w `endpoints/layout.py` — cienka warstwa HTTP nad już istniejącym i przetestowanym `split_polygon_by_edge()` z `services/bsp.py`. Zwraca listę poligonów (GeoJSON) + powierzchnie; 400 gdy linia nie przecina obrysu w dwóch punktach. 4 nowe testy w `test_layout_split.py` (podział na pół, podział asymetryczny, linia nieprzecinająca, walidacja wejścia). Pełny pakiet 85/85. |
| `t_0563b0bc` | **F2-07** | 🔧 częściowe | P1 | Render BSP na canvasie — kolory (klatka szara, korytarz jasnoszary, mieszkania wg typu) faktycznie zaimplementowane poprawnie, ale **wyłącznie dla hardcodowanego `sampleBspResult`**. Zależne od F2-15 (warstwa API), żeby renderować realny wynik z backendu. |
| `t_a4d92c53` | **F2-08** | ❌ do zrobienia | P1 | Tryb „przesuń linię” (drag&drop linii granicznych, skok 0.01m) — brak jakiejkolwiek logiki w `CanvasEditor.tsx`. |
| `t_d3a0c744` | **F2-09** | ❌ do zrobienia | P1 | Live walidacja po dragu — zależne od F2-08 (drag linii) oraz od endpointu `/api/layout/validate-apartment`, który **nie istnieje w ogóle** w backendzie (trzeba go dodać). |
| `t_472304d6` | **F2-10** | ❌ do zrobienia | P2 | „Pinned moves” — brak jakiegokolwiek stanu/mechanizmu w kodzie. Zależne od F2-08/F2-11. |
| `t_a075e7b4` | **F2-11** | ❌ do zrobienia | P1 | Przycisk [Regeneruj układ] + system punktacji wariantów — brak w UI. Uwaga: logika rankingu wariantów (`ranked = sorted(..., key=...)`) już istnieje po stronie backendu w `services/optimizer.py:126-131` i może zostać ponownie użyta zamiast pisania nowej. |
| `t_05aeea63` | **F2-12** | 🔧 częściowe | P2 | Etykiety na segmentach — tekst z nazwą istnieje (`CanvasEditor.tsx`), ale bez m², niekliknywalny (`listening={false}` jawnie wyłącza obsługę kliknięć), i nie ma sidebaru do podświetlenia. Dokończyć po F2-01. |
| `t_new0002` | **F2-13** 🆕 | ✅ done | — | **[Fala 2, 2026-07-01]** `services/typology_presets.py` — `TYPOLOGY_PRESETS` dla wszystkich 5 typologii (klatkowiec_wzdłużny, punktowiec, galeriowiec, klatkowiec_narożny, szeregowiec) z parametrami takt/corridor_width/staircase_dims/position/spacing/double_loaded przepisanymi 1:1 z `typologies.md` §6. `to_layout_defaults()` mapuje to, co `generate_layout()` faktycznie dziś konsumuje (corridor_width_m, cage_size_m, place_cage) — parametry bez konsumenta (takt_m, staircase_spacing_m, double_loaded) są wystawione na presecie i czekają na F2-04. Endpointy `GET /api/v1/typology/presets` i `POST /api/v1/typology/suggest` (współdzielone z F2-14). 12 testów, pełny pakiet 71/71. |
| `t_new0003` | **F2-14** 🆕 | 🔧 częściowe | P2 | **[Fala 2, 2026-07-01]** Backend gotowy: `suggest_typology()` w `services/typology_presets.py` implementuje pełną tabelę heurystyk z `typologies.md` §7 (bbox ratio + liczba wierzchołków wklęsłych → typologia + uzasadnienie + sugerowana liczba klatek dla U-kształtu), wystawione pod `POST /api/v1/typology/suggest`, przetestowane dla prostokąta wąskiego/szerokiego/bardzo wąskiego, L-kształtu i U-kształtu. **Pozostaje do zrobienia (Fala 3):** selektor typologii w sidebarze + podświetlenie sugestii przed kliknięciem — sidebar (F2-01) jeszcze nie istnieje. |
| `t_new0004` | **F2-15** 🆕 | ❌ do zrobienia | P0 | Frontend — warstwa integracji z API: klient `fetch`/`axios` do `POST /api/layout/generate`, `/api/footprint/from-points` itd., stan ładowania/błędu, zastąpienie `sampleBspResult` prawdziwą odpowiedzią backendu. **To jest zadanie blokujące** — bez niego F2-07, F2-08, F2-09, F3-05, F3-06, F4-05..07, F5-04..06, F6-02/04 nie mają na czym działać, bo frontend dziś nie wykonuje ani jednego wywołania sieciowego. |

---

## Faza 3 — Walidacja Warunków Technicznych

> Fala 2 (2026-07-01): `wt_validation.py` przepisany od podstaw z realnymi regułami WT + Dijkstra po siatce korytarza.

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_f83111a9` | **F3-01** | ✅ done | — | **[Fala 2, 2026-07-01]** `wt_validation.py` przepisany od zera. Usunięto fikcyjne `_estimate_daylight()`/`_estimate_noise()` (nasłonecznienie i tak liczy realnie `solar_analysis.py` — nie duplikujemy tego tu, żeby uniknąć dwóch rozbieżnych źródeł prawdy; „hałas" nigdy nie był realną regułą WT, usunięty całkowicie). Zaimplementowane realne reguły: **§94 ust.1** (min. 25m² bezwzględnie), **§94 ust.2** (min. szerokość 2.4m, przybliżana bbox komórki), **§64** (min. szerokość korytarza 1.4m — dokładna z konstrukcji BSP, nie remierzona z geometrii), **§68 ust.1** (min. szerokość klatki 1.2m), **§58 ust.4** (max. dojście do klatki 30m — **realna Dijkstra po siatce 0.5m** budowanej nad `circulation_geometry`, nie odległość euklidesowa, zgodnie z plan.md §4.4). `LayoutResult` (services/layout.py) wzbogacony o pola `circulation_geometry`, `cage_polygons`, `corridor_width_m`, `stair_width_m` potrzebne do tych reguł. Wynik zawiera teraz `rules: list[WTRule]` (kod, opis, passed, detail) + `score` 0-100 — umożliwiło to też dokończenie tymczasowego obejścia z Fali 1 w `optimizer.py` (`wt.rules` jest teraz realne, nie proxy 0/1). **14 nowych testów** (`test_wt_validation.py`), w tym test wprost demonstrujący plan.md §4.4: odległość korytarzowa dla zakrzywionego korytarza L-kształtnego > odległość euklidesowa. Pełny pakiet 52/52 zielony. **Odkryty przy okazji pre-istniejący bug** (nie naprawiony tu, należy do F2-04): `bsp_zones()` wycina własną, stałą ~1.0m „wnękę" w narożniku wklęsłym zanim `generate_layout()` zdąży użyć realnego `cage_size_m` — dla `cage_size_m` ≤ ~1.0m klatka wychodzi zerowej powierzchni. |
| `t_3700108f` | **F3-02** | ✅ done | — | **[Fala 1, 2026-07-01]** `/api/validate/apartment` — router `validate` zarejestrowany w `router.py`. Zweryfikowane end-to-end (`POST /api/v1/validate/apartment` → 200, poprawnie zwraca errors dla za małej powierzchni i szerokości < 2.4m). Logika pozostaje uproszczona (pojedynczy dict, nie pełna reguła WT) — to celowy „backwards-compatible helper” wg komentarza w kodzie, `/full-layout` (F3-04) jest docelowym endpointem. |
| `t_4567758a` | **F3-03** | ✅ done | — | **[Fala 2, 2026-07-01]** `POST /api/v1/validate/communication` zbudowany od zera — `validate_communication()` w `wt_validation.py`: (1) adjacency — styk mieszkanie↔komunikacja liczony jako `boundary.intersection`, próg 1.2m zalecany / 0.9m bezwzględne minimum (drzwi); (2) zasięg do najbliższej klatki przez tę samą infrastrukturę Dijkstry co F3-01 (nie euklidesowo); (3) min. rozstaw między klatkami (domyślnie 12m z `typologies.md`) gdy jest ich więcej niż jedna. Endpoint zweryfikowany end-to-end + 3 dedykowane testy w `test_validate.py`. |
| `t_4cef14e3` | **F3-04** | ✅ done | — | **[Fala 2, 2026-07-01]** `/api/validate/full-layout` dokończone — `apartment_validation.py`'s `validate_full_layout()` teraz agreguje **wszystkie trzy warstwy**: reguły apartamentowe (§94), pełną tabelę WT z F3-01 (`wt_rules` w odpowiedzi) i wynik komunikacji z F3-03 (`communication_all_connected`/`communication_issues`). Score 0-100 liczony jako udział spełnionych sprawdzeń przez wszystkie trzy warstwy łącznie. Zweryfikowane end-to-end + 4 nowe testy w `test_validate.py` (pełny plik testowy dla `/validate/*` nie istniał wcześniej). |
| `t_f8241b85` | **F3-05** | ❌ do zrobienia | P1 | Lista błędów/ostrzeżeń w sidebarze z klik→podświetlenie — zero kodu frontendowego. Zależne od F2-01 (sidebar) i F2-15 (API). |
| `t_893524c9` | **F3-06** | ❌ do zrobienia | P1 | Kolorowanie segmentów zielony/żółty/czerwony — brak jakiejkolwiek logiki we frontendzie. |
| `t_new0005` | **F3-07** 🆕 | ✅ done | — | **[Fala 1, 2026-07-01]** Utworzono `services/apartment_validation.py` (`validate_full_layout`, `FullLayoutValidationResult`, `ApartmentValidationResult`, `validate_apartment`) — realna implementacja walidacji pow. (§94 ust.1) i szerokości (§94 ust.2, przybliżanej jako mniejszy wymiar bounding-boxa komórki), nie tylko fasada nad importem. Router `validate` zarejestrowany w `api/v1/router.py` i `endpoints/__init__.py`. `pytest` 30/30 zielone, smoke-test end-to-end potwierdzony. |

---

## Faza 4 — Analiza nasłonecznienia (Solar)

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_6c35d5a3` | **F4-01** | ❌ do zrobienia | P1 | Mapa Leaflet — `leaflet`/`react-leaflet` nie ma w `package.json`, zero kodu mapy we frontendzie. Do zbudowania od zera + dodanie zależności. |
| `t_d9663416` | **F4-02** | ❌ do zrobienia | P1 | Date picker + toggle śródmiejski — brak w UI. Backend ma pole `required_hours` (domyślnie 3.0h), ale brak logiki automatycznego przełączenia na 1.5h przy „zabudowie śródmiejskiej” — to musi być jawny parametr sterowany z frontendu, nie tylko domyślna stała. |
| `t_9f6d6b3d` | **F4-03** | ✅ done | — | **[Fala 1, 2026-07-01]** `/api/solar/analyze` odblokowane i zweryfikowane end-to-end: `POST /api/v1/solar/analyze` → 200, zwraca realne `building_orientation` (np. „S”) i listę elewacji z pvlib (7 elewacji dla testowego kwadratu 20×20m z 4 mieszkaniami). Pętla `pvlib.location.Location.get_solarposition()` co 15 min, dot product wektora słońca i normalnej elewacji — działa realnie, nie na fallbacku. Patrz F4-09 dla szczegółów naprawy. |
| `t_bff320bb` | **F4-04** | 🔧 częściowe | P1 | Orientacja elewacji (azymut→N/NE/E/SE/S/SW/W/NW) działa i jest zweryfikowana (patrz F4-03/F4-09). **Wciąż brakuje:** automatyczny przełącznik wymaganych godzin 3h→1.5h dla „zabudowy śródmiejskiej” (WT §13 ust.2) — dziś `required_hours` to zwykły parametr wejściowy bez logiki auto-przełączania, zależne od F4-02 (frontend toggle). |
| `t_52ef3cbe` | **F4-05** | ❌ do zrobienia | P1 | Tryb „nasłonecznienie” z gradientem kolorów — zero kodu frontendowego, zero biblioteki wykresów w `package.json`. |
| `t_c470cf6b` | **F4-06** | ❌ do zrobienia | P2 | Tooltip z wykresem godzinowym — wymaga dodania biblioteki wykresów (np. `recharts`), brak w `package.json`. |
| `t_96ac3f4b` | **F4-07** | ❌ do zrobienia | P1 | Tabela wyników solar w sidebarze — zero kodu. |
| `t_1e7edf1e` | **F4-08** | ❌ do zrobienia | P1 | Testy solar vs suncalc.org — `test_solar.py` nie istnieje. Backend jest teraz odblokowany (F4-09) więc to zadanie jest wykonalne — zaplanowane na Falę 2. |
| `t_new0006` | **F4-09** 🆕 | ✅ done | — | **[Fala 1, 2026-07-01]** Naprawiono wszystkie krytyczne błędy: (1) dodano `azimuth_to_cardinal()` i `sunlight_adjustment_factor()` w `services/layout.py`; (2) dodano `_estimate_building_azimuth()` (najdłuższa krawędź obrysu → azymut normalnej) i pole `building_azimuth_deg` na `LayoutResult`, wyliczane w `generate_layout()`; (3) poprawiono `solar_analysis.py`: `layout.footprint_polygon` → `layout.footprint` (2 miejsca); (4) `pvlib`/`pandas`/`numpy` dodane w F0-07; (5) router `solar` zarejestrowany. `pytest` 30/30, smoke-test end-to-end potwierdzony (patrz F4-03). |

---

## Faza 5 — Optymalizator układu

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_dd98cd9d` | **F5-01** | 🔧 częściowe | P1 | **[Fala 1, 2026-07-01]** `/api/optimizer/run` odblokowane i zweryfikowane end-to-end dla obu gałęzi: obrys wypukły + ≤6 mieszkań → `method: "heuristic-search"` (przemianowane z mylącego `"lp"` — patrz niżej), obrys wklęsły → `method: "ga"` przez `pymoo.NSGA2`, oba realnie testowane HTTP-em i zwracają warianty z metrykami. **Decyzja developerska udokumentowana w kodzie:** `optimizer.py` importował `scipy.optimize.milp`, ale nigdy go nie wywoływał — usunięto martwy import zamiast dodawać nieużywaną zależność scipy; gałąź „LP” pozostaje w rzeczywistości heurystyczną enumeracją 18 kombinacji parametrów + surogat, nazwa metody w API to teraz `"heuristic-search"`, nie `"lp"`. Realna implementacja MILP to osobna decyzja produktowa, nieujęta w zakresie Fali 1. |
| `t_359496af` | **F5-02** | 🔧 częściowe | P1 | **[Fala 1, 2026-07-01]** Funkcja fitness (`_evaluate_variant`) odblokowana i działa — woła `analyze_solar_access` per wariant, zweryfikowane end-to-end. **Wciąż brakuje** cache'owanie pozycji słońca między wariantami (wymóg z planu: „raz na sesję”) — dziś pełna tabela pozycji słońca liczona jest od nowa dla każdego kandydata. To jest zadanie F5-08 (Fala 2), nie naprawiane w Fali 1. Dodatkowo naprawiono w Fali 1 błąd `wt.rules` (atrybut nie istniał na `WTValidationResult` — `_evaluate_variant` rzucałby `AttributeError` przy każdym wywołaniu; zastąpiono tymczasowym proxy `1 jeśli wt.passed inaczej 0`, do wzbogacenia po F3-01 o realny rozkład reguł). |
| `t_b2e174f4` | **F5-03** | ✅ done | — | **[Fala 2, 2026-07-01]** `_evaluate_variant()` woła teraz `validate_communication()` (F3-03: adjacency + Dijkstra zasięg klatki + rozstaw klatek) obok `validate_layout_wt()`. Wynik trafia do nowego pola `communication_ok`/`communication_issues` na `VariantMetrics`. Zgodnie z planem („constraint: każde mieszkanie ma dostęp do klatki") ranking wariantów mnoży wynik ×0.1 dla wariantów z `communication_ok=False` zamiast traktować to jak zwykłą, miękką regułę WT — ale nie odrzuca ich całkowicie (edge case: obrys, dla którego żadna konfiguracja nie da pełnej łączności, wciąż musi zwrócić `max_variants` wyników). 4 nowe testy w `test_optimizer_constraints.py`. |
| `t_5261dbca` | **F5-04** | ❌ do zrobienia | P1 | Przycisk [Optymalizuj] z progress barem i cancel — zero kodu frontendowego. |
| `t_0138b5c4` | **F5-05** | ❌ do zrobienia | P1 | Panel porównania 3 kart side-by-side — zero kodu. |
| `t_45e4f171` | **F5-06** | ❌ do zrobienia | P1 | Klik na wariant → załaduj do canvasu — zero kodu, zero mechanizmu wyboru wariantu. |
| `t_new0007` | **F5-07** 🆕 | ✅ done | — | **[Fala 1, 2026-07-01]** `optimizer.py` naprawiony: usunięto nieużywany import `scipy.optimize.milp`/`LinearConstraint`/`Bounds` (nigdy nie wywoływane) oraz martwy import `math` (nieużywany jeszcze przed tą sesją); zmieniono etykietę `method` z mylącego `"lp"` na `"heuristic-search"` + zaktualizowano docstring modułu; naprawiono `wt.rules` (nieistniejący atrybut, patrz F5-02); `pymoo` dodane w F0-07; router `optimizer` zarejestrowany. `pytest` 30/30, smoke-test obu gałęzi (heuristic-search i GA) end-to-end potwierdzony. |
| `t_new0008` | **F5-08** 🆕 | ✅ done | — | **[Fala 2, 2026-07-01]** `_sun_position_timeseries` upubliczniona jako `compute_sun_position_timeseries()` w `solar_analysis.py`; `run_optimizer()` liczy ją raz na starcie i przekazuje przez `solar_position_df` do wszystkich wywołań `_evaluate_variant()` (obie gałęzie: heuristic-search i GA). Test weryfikuje, że cache daje identyczny wynik co świeże liczenie (nie tylko że coś się nie wywala). |

---

## Faza 6 — Eksport danych

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_7d747421` | **F6-01** | 🔧 częściowe | P1 | `/api/export/dxf` — endpoint działa, zarejestrowany, testowany (`test_export_dxf.py`), warstwy OBRYS/MIESZKANIA/KOMUNIKACJA/TEKST/ELEWACJE obecne z xdata. **Ale:** godziny słońca w xdata (`worst_sun_hours`) pochodzą z deterministycznego fallbacku szacującego wg azymutu budynku (`_extract_sun_hours` w `export_dxf.py`), nie z realnej analizy pvlib — bo `solar_analysis` jest dziś nieosiągalny (patrz F4-09). Po naprawie Fazy 4 podłączyć realne dane solar zamiast fallbacku. |
| `t_708c006b` | **F6-02** | ❌ do zrobienia | P1 | Przycisk [Eksport DXF] → download — zero kodu frontendowego, zależne od F2-15. |
| `t_cfec375d` | **F6-03** | ✅ done | — | `/api/export/json` — zarejestrowany, działający, zwraca pełny snapshot (footprint, layout/apartments, solar_analysis z zastrzeżeniem fallbacku, wt_validation, optimizer_results). |
| `t_ceb5f54b` | **F6-04** | ❌ do zrobienia | P1 | [Eksport JSON] + [Import JSON] drag&drop — zero kodu frontendowego. |
| `t_00cbe528` | **F6-05** | ❌ do zrobienia | P1 | `/api/export/pdf` — **nie istnieje w ogóle**: brak pliku, brak endpointu, brak zależności `weasyprint`/`reportlab` w `requirements.txt`. Decyzja developerska z planu (R3): weasyprint (prostszy HTML→PDF) vs reportlab (elastyczniejszy) — podjąć przed startem implementacji. |
| `t_d2f4e48d` | **F6-06** | 🔧 częściowe | P1 | Testy round-trip DXF — `test_export_dxf.py` (9 testów) sprawdza wyłącznie strukturę (obecność warstw, xdata, kody statusu HTTP) — **nie porównuje geometrii** eksport→import (Shapely area diff < 0.01m²) jak wymaga zadanie. Dodatkowo prawdziwy round-trip przez API nie jest możliwy, dopóki `/api/footprint/import-dxf` (F1-01) nie istnieje. |
| `t_new0009` | **F6-07** 🆕 | ❌ do zrobienia | P2 | Frontend — autosave stanu projektu do `localStorage` co 30s (decyzja D3 z `plan.md`: „localStorage tylko dla autosave”), z odtworzeniem stanu przy ponownym otwarciu aplikacji po przerwanej sesji. Zależne od F2-15 (musi istnieć realny stan projektu we frontendzie, nie tylko dane demo). |

---

## Faza 7 — Testy E2E i dokumentacja

| ID | Task | Status | Priorytet | Opis |
|-----|------|--------|-----------|------|
| `t_41c8522a` | **F7-01** | ❌ do zrobienia | P2 | E2E pełny flow — brak frameworka E2E w repo (zero Playwright/Cypress config). Zależne od F7-07 i od tego, żeby cały flow (Fazy 1–6) realnie działał. |
| `t_c60c8814` | **F7-02** | ❌ do zrobienia | P2 | E2E obrys wklęsły — dziś istnieją tylko testy jednostkowe w `test_bsp.py` (nie E2E, nie pełny flow). |
| `t_185ad5c5` | **F7-03** | ❌ do zrobienia | P2 | E2E program niemożliwy do zmieszczenia — brak jakiegokolwiek testu z tym scenariuszem. |
| `t_0a1d729e` | **F7-04** | ❌ do zrobienia | P2 | Testy performance (`/api/solar/analyze` <3s, LP <10s, GA <30s) — zero testów tego typu w repo, brak frameworka do pomiaru (patrz F7-08). |
| `t_166ee690` | **F7-05** | ⏸️ blocked | — | UX review z Bartoszem — jedyne uczciwie oznaczone zadanie w oryginalnym kanbanie. Bez zmian, ale realnie sensowne dopiero gdy Fazy 1–6 osiągną stan używalny. |
| `t_81e3b664` | **F7-06** | 🔧 częściowe | P2 | README — istnieje, opisuje strukturę repo i CI, ale nie wspomina Docker Compose (bo nie istnieje), nie opisuje endpointów API, nie opisuje typologii presetów. Przepisać po zamknięciu F0-04, F2-13/14. |
| `t_new0010` | **F7-07** 🆕 | ❌ do zrobienia | P2 | Setup frameworka E2E (rekomendacja: Playwright — dobrze integruje się z Next.js) — konfiguracja, uruchomienie w CI, jeden trywialny test smoke jako fundament pod F7-01..03. |
| `t_new0011` | **F7-08** 🆕 | ❌ do zrobienia | P2 | Setup testów performance (`pytest-benchmark` lub proste asercje czasu z `time.perf_counter()`) jako fundament pod F7-04. |

---

## Pokrycie `plan.md` i `typologies.md` — czy WBS jest kompletny?

Po audycie i uzupełnieniu powyższych 11 nowych zadań (🆕), WBS pokrywa **100% zakresu z `plan.md`** i **100% zakresu z `typologies.md`**. Luki, które istniały w oryginalnym WBS (przed audytem) i zostały teraz zamknięte:

- **Presety typologii i heurystyka auto-detekcji** (`typologies.md` w całości) — nie miały żadnego zadania w oryginalnym WBS. Dodano F2-13, F2-14.
- **Autosave do localStorage co 30s** (decyzja D3 w `plan.md` §7) — nie miała zadania. Dodano F6-07.
- **Framework E2E i framework performance** — F7-01..04 zakładały istnienie infrastruktury testowej, która nigdzie nie była zadaniem samym w sobie. Dodano F7-07, F7-08.
- **Naprawa integracji backendu** (routery, brakujące moduły/funkcje, zależności) — to nie były zadania w oryginalnym WBS, bo nikt nie spodziewał się, że kod zostanie oznaczony jako „done” mimo że się nie importuje. Dodano F0-07, F3-07, F4-09, F5-07, F5-08.
- **Warstwa integracji API frontend↔backend** — plan zakładał to implicite („frontend wywołuje API”), ale nie było jawnego zadania, a jego brak okazał się głównym powodem, dla którego cały frontend jest odłączony od backendu. Dodano F2-15.

Nic w `plan.md`/`typologies.md` nie pozostaje dziś bez pokrycia zadaniem — WBS jest kompletny względem dokumentów źródłowych. Pozostaje wyłącznie kwestia wykonania.

---

## Plan naprawczy — rekomendowana kolejność pracy

Rzeczywisty stan kodu (nie deklarowany) wymaga innej kolejności niż oryginalne fazy 0→7 sugerowałyby wprost — najpierw trzeba odblokować to, co już napisane, zanim doda się nowe funkcje.

### Fala 1 — Odblokowanie istniejącego kodu (P0, ~2-4 dni) — ✅ WYKONANA 2026-07-01
Nic nowego nie zostało napisane — wyłącznie naprawa tego, co już istniało, żeby przestało być martwym kodem.
1. ✅ **F0-07** — `requirements.txt` uzupełniony (pvlib, pandas, numpy, networkx, pymoo, reportlab; scipy świadomie pominięty, patrz ustalenie #5/#9)
2. ✅ **F4-09** — `azimuth_to_cardinal`/`sunlight_adjustment_factor`/`_estimate_building_azimuth` dodane, pole `building_azimuth_deg` na `LayoutResult`, `solar_analysis.py` poprawiony, router `solar` zarejestrowany
3. ✅ **F3-07** — `services/apartment_validation.py` utworzony, router `validate` zarejestrowany
4. ✅ **F5-07** — importy `optimizer.py` naprawione, metoda przemianowana na `"heuristic-search"`, błąd `wt.rules` naprawiony, router `optimizer` zarejestrowany
5. ✅ **F0-02** — health endpoint dostępny pod `/health` i `/api/health`, czysty `pip install -r requirements.txt` zweryfikowany bez konfliktów
6. ✅ Zweryfikowano całość: `pytest` 30/30 (29 oryginalnych + 1 nowy test `/api/health`), wszystkie trzy wcześniej martwe routery (`/validate/*`, `/solar/analyze`, `/optimizer/run`, obie gałęzie heuristic-search i GA) przetestowane end-to-end realnymi wywołaniami HTTP, nie tylko importem modułu.

**Odkryte przy okazji (nieplanowane, ale naprawione bo blokowały weryfikację):** błąd `wt.rules` w `optimizer.py` (ustalenie #11), health endpoint test w `test_health.py` rozszerzony o `/api/health`.

**Odkryte przy okazji (NIE naprawione, wymaga osobnej decyzji):** `ruff check .` zwraca 110 pre-istniejących błędów w plikach spoza zakresu tej fali (ustalenie #12) — F0-05 obniżone do 🔧.

### Fala 2 — Realna logika biznesowa backendu (P0/P1, ~1-2 tygodnie) — ✅ WYKONANA 2026-07-01
7. ✅ **F1-01** — import DXF od zera (ezdxf → Shapely → GeoJSON, 8 testów)
8. ✅ **F3-01** — `wt_validation.py` przepisany od zera: realne §94/§64/§68, Dijkstra po siatce 0.5m dla §58
9. ✅ **F3-02, F3-03, F3-04** — `/validate/apartment` odblokowany, `/validate/communication` zbudowany od zera, `/validate/full-layout` agreguje wszystkie trzy warstwy
10. ✅ **F2-13, F2-14** — presety typologii (5/5) + heurystyka auto-detekcji (bbox ratio + concave count), backend gotowy (UI selektora zostaje na Falę 3)
11. 🔧 **F2-04** — tryby pozycji klatki 1a/1b/2/3/auto zaimplementowane (naprawiony bug: obrysy wypukłe nigdy nie dostawały klatki), dopasowanie do programu naprawione dla scenariusza dwustronnego korytarza (odkryto i naprawiono 2 dodatkowe pre-istniejące bugi geometrii po drodze); korytarz „wzdłuż osi z uwzględnieniem klatki" i pełna precyzja dla obrysów wklęsłych zostają jako otwarty punkt
12. ✅ **F2-06** — endpoint `/layout/split` nad już istniejącą, przetestowaną funkcją
13. ✅ **F5-08** — cache pozycji słońca (`compute_sun_position_timeseries`) w `run_optimizer()`
14. ✅ **F5-03** — `validate_communication()` podłączone do `_evaluate_variant()`, kara rankingowa za złamanie ograniczenia łączności

**Weryfikacja końcowa Fali 2:** pełny pakiet testów **89/89 zielony** (30 z Fali 1 → 89, +59 nowych testów w tej fali), zero regresji, wszystkie nowe/zmienione pliki przechodzą `ruff check` bez nowych błędów.

### Fala 3 — Frontend: fundament (P0/P1, ~1-2 tygodnie)
15. **F2-15** — warstwa integracji API (klient fetch) — **to jest bramka**, bez niej żadna kolejna praca frontendowa nie ma sensu
16. **F2-01** — sidebar (fundament dla F1-07, F2-02/03, F3-05, F4-07)
17. **F1-04, F1-05, F1-06, F1-07** — rysowanie/upload/edycja obrysu + wymiary
18. **F2-02, F2-03** — formularz programu mieszkań + parametry komunikacji
19. **F2-07, F2-08, F2-09, F2-11, F2-12** — podłączenie renderu do realnego API, drag linii, live walidacja, regeneracja, etykiety
20. **F3-05, F3-06** — lista błędów + kolorowanie segmentów

### Fala 4 — Frontend: Solar + Optymalizator + Eksport (P1, ~1-2 tygodnie)
21. **F4-01, F4-02** — mapa Leaflet + date picker (wymaga dodania zależności `leaflet`/`react-leaflet`)
22. **F4-03, F4-04, F4-08** — dokończyć i przetestować solar (zależne od Fali 1)
23. **F4-05, F4-06, F4-07** — wizualizacja solar we frontendzie
24. **F5-01, F5-02** — dokończyć optymalizator (zależne od Fali 1-2)
25. **F5-04, F5-05, F5-06** — UI optymalizatora
26. **F6-01** (podłączyć realne dane solar), **F6-02, F6-04, F6-05, F6-06, F6-07** — eksport PDF, przyciski, round-trip, autosave

### Fala 5 — E2E, performance, dokumentacja (P2, ~3-5 dni)
27. **F7-07, F7-08** — framework E2E + framework performance
28. **F7-01, F7-02, F7-03, F7-04** — właściwe scenariusze testowe
29. **F7-06** — przepisanie README
30. **F7-05** — UX review z Bartoszem (dopiero gdy powyższe działa)

**Uwaga:** Fale 1-2 to praca wyłącznie backendowa i mogą iść równolegle z Falą 3 (frontend), o ile Fala 3 zaczyna się od F2-15 (warstwa API) i mocka odpowiedzi tam, gdzie backend jeszcze nie jest gotowy.
