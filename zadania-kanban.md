# DOMKO_APP — Rejestr zadań Kanban

> **Projekt:** DOMKO_APP  
> **Repo:** https://github.com/zlyarchitekt/domko_app  
> **Kod lokalny:** `C:\Praca\01 AI\HERMES\DOMKO_APP\`  
> **Board Kanban:** `domko`  
> **Ostatnia aktualizacja:** 2026-07-01  

## Podsumowanie

| Status | Liczba |
|--------|--------|
| ✅ done | 57 |
| ⏸️ blocked | 1 |
| **Razem** | **58** |

---

## Faza 0 — Setup projektu

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_1b20e5dd` | **F0-01** | ✅ done | dev | Inicjalizacja repo — monorepo /frontend + /backend, git init, .gitignore |
| `t_108f6061` | **F0-02** | ✅ done | dev | Backend setup — FastAPI + uvicorn + Shapely + pvlib + ezdxf + networkx — pyproject.toml, uv venv, health endpoint GET /api/health |
| `t_54eb0255` | **F0-03** | ✅ done | dev | Frontend setup — Next.js App Router + Konva.js + Tailwind + react-leaflet — scaffolding, strona główna z pustym canvasem |
| `t_2ac7f5d3` | **F0-04** | ✅ done | dev | Docker Compose — backend + frontend w jednym docker compose up, hot-reload dev mode |
| `t_1a01e210` | **F0-05** | ✅ done | automation | CI — GitHub Actions: lint (ruff + eslint) + testy przy każdym push |
| `t_15f92401` | **F0-06** | ✅ done | dev | Struktura folderów backendu — models/, services/, api/, tests/ jak w planie §3.3 |
---

## Faza 1 — Import i rysunek obrysu

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_12156cbc` | **F1-01** | ✅ done | dev | Backend /api/footprint/import-dxf — ezdxf → Shapely Polygon (LWPOLYLINE, POLYLINE, HATCH), zwraca GeoJSON |
| `t_734af2a1` | **F1-02** | ✅ done | dev | Backend /api/footprint/from-points — walidacja zamknięcia, self-intersection check |
| `t_49589533` | **F1-03** | ✅ done | dev | Frontend — canvas z siatką 1m (Konva.js), zoom, pan, fit-to-screen |
| `t_e5c6ec52` | **F1-04** | ✅ done | dev | Frontend — rysowanie wielokąta: klik po klik, snap do siatki co 0.01m, zamknięcie dwuklikiem |
| `t_d036f0e6` | **F1-05** | ✅ done | dev | Frontend — upload DXF drag&drop → POST /api/footprint/import-dxf → render polygonu na canvasie |
| `t_da5f31db` | **F1-06** | ✅ done | dev | Frontend — edycja wierzchołków obrysu: drag&drop punktów ze snap do siatki |
| `t_f53dece3` | **F1-07** | ✅ done | dev | Frontend — sidebar: wymiary boków + łączna powierzchnia live |
| `t_e0dfa965` | **F1-08** | ✅ done | dev | Testy importu DXF — prostokąt, L-kształt, polygon wklęsły, plik z wieloma warstwami |
---

## Faza 2 — Program i podział BSP

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_73eaaf1c` | **F2-01** | ✅ done | dev | Frontend — sidebar komponent 320px, scrollowalny, sekcje: Program / Komunikacja / Walidacja / Eksport |
| `t_3b1b6790` | **F2-02** | ✅ done | dev | Frontend — ApartmentTypeRow: typ (M1-M5), liczba, docelowy m², bilans live vs pow. kondygnacji |
| `t_665a85d9` | **F2-03** | ✅ done | dev | Frontend — parametry komunikacji: pozycja klatki (1A/1B/2/3), toggle poza obrysem, wymiar klatki 5.7×5.2m, max dojście, min odl. między klatkami, szer. korytarza 1.4m |
| `t_32791c41` | **F2-04** | ✅ done | dev | Backend /api/layout/generate — algorytm BSP: pozycja klatki, korytarz wzdłuż osi, podział na mieszkania, dopasowanie do programu, walidacja WT |
| `t_9e581f9d` | **F2-05** | ✅ done | dev | Backend BSP — obsługa obrysów wklęsłych (L/U-kształt): wykrycie concave vertices, podział na strefy, klatka w narożniku |
| `t_f6ae35dd` | **F2-06** | ✅ done | dev | Backend /api/layout/split — Shapely split polygonu linią, obsługa edge cases |
| `t_0563b0bc` | **F2-07** | ✅ done | dev | Frontend — render wyniku BSP na canvasie: klatka (szary), korytarz (jasnoszary), mieszkania (kolory wg typu) |
| `t_a4d92c53` | **F2-08** | ✅ done | dev | Frontend — tryb 'przesuń linię': drag&drop linii granicznych, skok 0.01m |
| `t_d3a0c744` | **F2-09** | ✅ done | dev | Frontend — live walidacja po drag: re-call /api/layout/validate-apartment, aktualizacja kolorów segmentów |
| `t_472304d6` | **F2-10** | ✅ done | dev | Frontend — 'pinned moves': zapamiętanie ręcznych korekt, zachowanie przy Regeneruj |
| `t_a075e7b4` | **F2-11** | ✅ done | dev | Frontend — przycisk [Regeneruj układ] z zachowaniem pinnedMoves + system punktacji wariantów |
| `t_05aeea63` | **F2-12** | ✅ done | dev | Frontend — etykiety na segmentach: ID, typ, m²; klik → podświetlenie w sidebarze |
---

## Faza 3 — Walidacja Warunków Technicznych

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_f83111a9` | **F3-01** | ✅ done | aec | Backend wt_validator.py — tabela reguł WT §94 (pow., szer. pokoju), §64 (korytarz), §68 (klatka), §58 (dojście Dijkstra 0.5m), §13 (nasłonecznienie) |
| `t_3700108f` | **F3-02** | ✅ done | dev | Backend /api/validate/apartment — min pow. wg typu, min szer. 2.4m, zwraca errors/warnings |
| `t_4567758a` | **F3-03** | ✅ done | dev | Backend /api/validate/communication — adjacency check min 1.2m, odległość korytarzowa Dijkstra (networkx), zasięg klatki, min odl. między klatkami |
| `t_4cef14e3` | **F3-04** | ✅ done | dev | Backend /api/validate/full-layout — agregacja wszystkich błędów, score 0-100 |
| `t_f8241b85` | **F3-05** | ✅ done | dev | Frontend — lista błędów/ostrzeżeń w sidebarze: ikona + opis, klik → zoom+podświetlenie segmentu na canvasie |
| `t_893524c9` | **F3-06** | ✅ done | dev | Frontend — kolorowanie segmentów: zielony OK / żółty ostrzeżenie (±5%) / czerwony błąd WT |
---

## Faza 4 — Analiza nasłonecznienia (Solar)

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_6c35d5a3` | **F4-01** | ✅ done | dev | Frontend — mapa Leaflet: tryb 'wybierz lokalizację', klik → lat/lng do state, podgląd wybranego punktu |
| `t_d9663416` | **F4-02** | ✅ done | dev | Frontend — date picker (domyślnie 21.03), toggle śródmiejski (§13 ust.2: min 1.5h zamiast 3h) |
| `t_9f6d6b3d` | **F4-03** | ✅ done | dev | Backend /api/solar/analyze — wyznaczenie elewacji zewnętrznych, pvlib sun position loop 15min, dot product wektor słońca · normalna ściany, zliczanie godzin |
| `t_bff320bb` | **F4-04** | ✅ done | dev | Backend — orientacja elewacji: azymut normalnej → N/NE/E/SE/S/SW/W/NW, porównanie z WT §13 (3h lub 1.5h śródmiejskie) |
| `t_52ef3cbe` | **F4-05** | ✅ done | dev | Frontend — tryb 'nasłonecznienie': elewacje kolorowane gradientem niebieski(0h)→żółty(3h)→czerwony(6h+) |
| `t_c470cf6b` | **F4-06** | ✅ done | dev | Frontend — tooltip na elewacji: wykres godzinowy bar chart, orientacja, godziny, status WT |
| `t_96ac3f4b` | **F4-07** | ✅ done | dev | Frontend — tabela wyników w sidebarze: mieszkanie / elewacja / orientacja / godz. / status WT |
| `t_1e7edf1e` | **F4-08** | ✅ done | dev | Testy solar — wyniki pvlib vs suncalc.org dla Warszawy (52.23N, 21.03), tolerancja ±15min |
---

## Faza 5 — Optymalizator układu

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_dd98cd9d` | **F5-01** | ✅ done | dev | Backend /api/optimizer/run — LP (scipy.optimize) dla prostych obrysów, GA (pymoo NSGA-II) dla wklęsłych/wielu klatek |
| `t_359496af` | **F5-02** | ✅ done | dev | Backend — funkcja fitness optymalizatora: pvlib w pętli z cache pozycji słońca (raz na sesję), constraint WT §13 + §58 |
| `t_b2e174f4` | **F5-03** | ✅ done | dev | Backend — constraint validation w pętli: adjacency + Dijkstra zasięg klatki + WT §13 min godziny |
| `t_5261dbca` | **F5-04** | ✅ done | dev | Frontend — przycisk [▶ Optymalizuj], progress bar (5-30s), cancel button |
| `t_0138b5c4` | **F5-05** | ✅ done | dev | Frontend — panel porównania: 3 karty side-by-side, miniatura układu (canvas snapshot) + solar_score + wt_compliance_score + total_sun_hours |
| `t_45e4f171` | **F5-06** | ✅ done | dev | Frontend — klik na wariant → załaduj do głównego canvasu jako aktywny układ (replace current layout) |
---

## Faza 6 — Eksport danych

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_7d747421` | **F6-01** | ✅ done | dev | Backend /api/export/dxf — ezdxf write: warstwy OBRYS/MIESZKANIA/KOMUNIKACJA/TEKST/ELEWACJE z atrybutami godzin słońca |
| `t_708c006b` | **F6-02** | ✅ done | dev | Frontend — przycisk [Eksport DXF] → download .dxf |
| `t_cfec375d` | **F6-03** | ✅ done | dev | Backend /api/export/json — pełny stan projektu: footprint, apartments, solar, optimizer results |
| `t_ceb5f54b` | **F6-04** | ✅ done | dev | Frontend — [Eksport JSON] + [Import JSON]: drag&drop wczytanie projektu |
| `t_00cbe528` | **F6-05** | ✅ done | dev | Backend /api/export/pdf — weasyprint HTML→PDF: wizualizacja układu (PNG) + tabela nasłonecznienia + dane lokalizacji |
| `t_d2f4e48d` | **F6-06** | ✅ done | dev | Testy round-trip DXF — eksport → import → porównanie geometrii Shapely (area diff < 0.01m²) |
---

## Faza 7 — Testy E2E i dokumentacja

| ID | Task | Status | Assignee | Opis |
|-----|------|--------|----------|------|
| `t_41c8522a` | **F7-01** | ✅ done | dev | E2E — pełny flow: import DXF → BSP generuj → korekta ręczna → solar → optymalizuj top-3 → eksport DXF |
| `t_c60c8814` | **F7-02** | ✅ done | dev | E2E — obrys wklęsły: L-kształt i U-kształt, weryfikacja podziału na strefy i zasięgu klatek |
| `t_185ad5c5` | **F7-03** | ✅ done | dev | E2E — program niemożliwy: za duże mieszkania, suma > pow. kondygnacji → czytelny komunikat + sugestia korekty |
| `t_0a1d729e` | **F7-04** | ✅ done | dev | Performance — /api/solar/analyze < 3s, /api/optimizer/run LP < 10s, GA < 30s dla 20 mieszkań |
| `t_166ee690` | **F7-05** | ⏸️ blocked | dev | UX review — testy z Bartoszem (architektem): lista poprawek → implementacja |
| `t_81e3b664` | **F7-06** | ✅ done | dev | README — instrukcja uruchomienia Docker Compose, opis endpointów API, opis typologii presetów |

---

## Szczegóły zadań

### Faza 0 — Setup projektu

#### ✅ F0-01 — Inicjalizacja repo — monorepo /frontend + /backend, git init, .gitignore

- **ID:** `t_1b20e5dd`
- **Status:** done
- **Assignee:** dev
- **Opis:** Inicjalizacja repo — monorepo /frontend + /backend, git init, .gitignore

#### ✅ F0-02 — Backend setup — FastAPI + uvicorn + Shapely + pvlib + ezdxf + networkx — pyproje

- **ID:** `t_108f6061`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend setup — FastAPI + uvicorn + Shapely + pvlib + ezdxf + networkx — pyproject.toml, uv venv, health endpoint GET /api/health

#### ✅ F0-03 — Frontend setup — Next.js App Router + Konva.js + Tailwind + react-leaflet — scaf

- **ID:** `t_54eb0255`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend setup — Next.js App Router + Konva.js + Tailwind + react-leaflet — scaffolding, strona główna z pustym canvasem

#### ✅ F0-04 — Docker Compose — backend + frontend w jednym docker compose up, hot-reload dev m

- **ID:** `t_2ac7f5d3`
- **Status:** done
- **Assignee:** dev
- **Opis:** Docker Compose — backend + frontend w jednym docker compose up, hot-reload dev mode

#### ✅ F0-05 — CI — GitHub Actions: lint (ruff + eslint) + testy przy każdym push

- **ID:** `t_1a01e210`
- **Status:** done
- **Assignee:** automation
- **Opis:** CI — GitHub Actions: lint (ruff + eslint) + testy przy każdym push

#### ✅ F0-06 — Struktura folderów backendu — models/, services/, api/, tests/ jak w planie §3.3

- **ID:** `t_15f92401`
- **Status:** done
- **Assignee:** dev
- **Opis:** Struktura folderów backendu — models/, services/, api/, tests/ jak w planie §3.3

### Faza 1 — Import i rysunek obrysu

#### ✅ F1-01 — Backend /api/footprint/import-dxf — ezdxf → Shapely Polygon (LWPOLYLINE, POLYLIN

- **ID:** `t_12156cbc`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/footprint/import-dxf — ezdxf → Shapely Polygon (LWPOLYLINE, POLYLINE, HATCH), zwraca GeoJSON

#### ✅ F1-02 — Backend /api/footprint/from-points — walidacja zamknięcia, self-intersection che

- **ID:** `t_734af2a1`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/footprint/from-points — walidacja zamknięcia, self-intersection check

#### ✅ F1-03 — Frontend — canvas z siatką 1m (Konva.js), zoom, pan, fit-to-screen

- **ID:** `t_49589533`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — canvas z siatką 1m (Konva.js), zoom, pan, fit-to-screen

#### ✅ F1-04 — Frontend — rysowanie wielokąta: klik po klik, snap do siatki co 0.01m, zamknięci

- **ID:** `t_e5c6ec52`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — rysowanie wielokąta: klik po klik, snap do siatki co 0.01m, zamknięcie dwuklikiem

#### ✅ F1-05 — Frontend — upload DXF drag&drop → POST /api/footprint/import-dxf → render polygo

- **ID:** `t_d036f0e6`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — upload DXF drag&drop → POST /api/footprint/import-dxf → render polygonu na canvasie

#### ✅ F1-06 — Frontend — edycja wierzchołków obrysu: drag&drop punktów ze snap do siatki

- **ID:** `t_da5f31db`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — edycja wierzchołków obrysu: drag&drop punktów ze snap do siatki

#### ✅ F1-07 — Frontend — sidebar: wymiary boków + łączna powierzchnia live

- **ID:** `t_f53dece3`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — sidebar: wymiary boków + łączna powierzchnia live

#### ✅ F1-08 — Testy importu DXF — prostokąt, L-kształt, polygon wklęsły, plik z wieloma warstw

- **ID:** `t_e0dfa965`
- **Status:** done
- **Assignee:** dev
- **Opis:** Testy importu DXF — prostokąt, L-kształt, polygon wklęsły, plik z wieloma warstwami

### Faza 2 — Program i podział BSP

#### ✅ F2-01 — Frontend — sidebar komponent 320px, scrollowalny, sekcje: Program / Komunikacja 

- **ID:** `t_73eaaf1c`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — sidebar komponent 320px, scrollowalny, sekcje: Program / Komunikacja / Walidacja / Eksport

#### ✅ F2-02 — Frontend — ApartmentTypeRow: typ (M1-M5), liczba, docelowy m², bilans live vs po

- **ID:** `t_3b1b6790`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — ApartmentTypeRow: typ (M1-M5), liczba, docelowy m², bilans live vs pow. kondygnacji

#### ✅ F2-03 — Frontend — parametry komunikacji: pozycja klatki (1A/1B/2/3), toggle poza obryse

- **ID:** `t_665a85d9`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — parametry komunikacji: pozycja klatki (1A/1B/2/3), toggle poza obrysem, wymiar klatki 5.7×5.2m, max dojście, min odl. między klatkami, szer. korytarza 1.4m

#### ✅ F2-04 — Backend /api/layout/generate — algorytm BSP: pozycja klatki, korytarz wzdłuż osi

- **ID:** `t_32791c41`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/layout/generate — algorytm BSP: pozycja klatki, korytarz wzdłuż osi, podział na mieszkania, dopasowanie do programu, walidacja WT

#### ✅ F2-05 — Backend BSP — obsługa obrysów wklęsłych (L/U-kształt): wykrycie concave vertices

- **ID:** `t_9e581f9d`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend BSP — obsługa obrysów wklęsłych (L/U-kształt): wykrycie concave vertices, podział na strefy, klatka w narożniku

#### ✅ F2-06 — Backend /api/layout/split — Shapely split polygonu linią, obsługa edge cases

- **ID:** `t_f6ae35dd`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/layout/split — Shapely split polygonu linią, obsługa edge cases

#### ✅ F2-07 — Frontend — render wyniku BSP na canvasie: klatka (szary), korytarz (jasnoszary),

- **ID:** `t_0563b0bc`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — render wyniku BSP na canvasie: klatka (szary), korytarz (jasnoszary), mieszkania (kolory wg typu)

#### ✅ F2-08 — Frontend — tryb 'przesuń linię': drag&drop linii granicznych, skok 0.01m

- **ID:** `t_a4d92c53`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — tryb 'przesuń linię': drag&drop linii granicznych, skok 0.01m

#### ✅ F2-09 — Frontend — live walidacja po drag: re-call /api/layout/validate-apartment, aktua

- **ID:** `t_d3a0c744`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — live walidacja po drag: re-call /api/layout/validate-apartment, aktualizacja kolorów segmentów

#### ✅ F2-10 — Frontend — 'pinned moves': zapamiętanie ręcznych korekt, zachowanie przy Regener

- **ID:** `t_472304d6`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — 'pinned moves': zapamiętanie ręcznych korekt, zachowanie przy Regeneruj

#### ✅ F2-11 — Frontend — przycisk [Regeneruj układ] z zachowaniem pinnedMoves + system punktac

- **ID:** `t_a075e7b4`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — przycisk [Regeneruj układ] z zachowaniem pinnedMoves + system punktacji wariantów

#### ✅ F2-12 — Frontend — etykiety na segmentach: ID, typ, m²; klik → podświetlenie w sidebarze

- **ID:** `t_05aeea63`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — etykiety na segmentach: ID, typ, m²; klik → podświetlenie w sidebarze

### Faza 3 — Walidacja Warunków Technicznych

#### ✅ F3-01 — Backend wt_validator.py — tabela reguł WT §94 (pow., szer. pokoju), §64 (korytar

- **ID:** `t_f83111a9`
- **Status:** done
- **Assignee:** aec
- **Opis:** Backend wt_validator.py — tabela reguł WT §94 (pow., szer. pokoju), §64 (korytarz), §68 (klatka), §58 (dojście Dijkstra 0.5m), §13 (nasłonecznienie)

#### ✅ F3-02 — Backend /api/validate/apartment — min pow. wg typu, min szer. 2.4m, zwraca error

- **ID:** `t_3700108f`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/validate/apartment — min pow. wg typu, min szer. 2.4m, zwraca errors/warnings

#### ✅ F3-03 — Backend /api/validate/communication — adjacency check min 1.2m, odległość koryta

- **ID:** `t_4567758a`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/validate/communication — adjacency check min 1.2m, odległość korytarzowa Dijkstra (networkx), zasięg klatki, min odl. między klatkami

#### ✅ F3-04 — Backend /api/validate/full-layout — agregacja wszystkich błędów, score 0-100

- **ID:** `t_4cef14e3`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/validate/full-layout — agregacja wszystkich błędów, score 0-100

#### ✅ F3-05 — Frontend — lista błędów/ostrzeżeń w sidebarze: ikona + opis, klik → zoom+podświe

- **ID:** `t_f8241b85`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — lista błędów/ostrzeżeń w sidebarze: ikona + opis, klik → zoom+podświetlenie segmentu na canvasie

#### ✅ F3-06 — Frontend — kolorowanie segmentów: zielony OK / żółty ostrzeżenie (±5%) / czerwon

- **ID:** `t_893524c9`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — kolorowanie segmentów: zielony OK / żółty ostrzeżenie (±5%) / czerwony błąd WT

### Faza 4 — Analiza nasłonecznienia (Solar)

#### ✅ F4-01 — Frontend — mapa Leaflet: tryb 'wybierz lokalizację', klik → lat/lng do state, po

- **ID:** `t_6c35d5a3`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — mapa Leaflet: tryb 'wybierz lokalizację', klik → lat/lng do state, podgląd wybranego punktu

#### ✅ F4-02 — Frontend — date picker (domyślnie 21.03), toggle śródmiejski (§13 ust.2: min 1.5

- **ID:** `t_d9663416`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — date picker (domyślnie 21.03), toggle śródmiejski (§13 ust.2: min 1.5h zamiast 3h)

#### ✅ F4-03 — Backend /api/solar/analyze — wyznaczenie elewacji zewnętrznych, pvlib sun positi

- **ID:** `t_9f6d6b3d`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/solar/analyze — wyznaczenie elewacji zewnętrznych, pvlib sun position loop 15min, dot product wektor słońca · normalna ściany, zliczanie godzin

#### ✅ F4-04 — Backend — orientacja elewacji: azymut normalnej → N/NE/E/SE/S/SW/W/NW, porównani

- **ID:** `t_bff320bb`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend — orientacja elewacji: azymut normalnej → N/NE/E/SE/S/SW/W/NW, porównanie z WT §13 (3h lub 1.5h śródmiejskie)

#### ✅ F4-05 — Frontend — tryb 'nasłonecznienie': elewacje kolorowane gradientem niebieski(0h)→

- **ID:** `t_52ef3cbe`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — tryb 'nasłonecznienie': elewacje kolorowane gradientem niebieski(0h)→żółty(3h)→czerwony(6h+)

#### ✅ F4-06 — Frontend — tooltip na elewacji: wykres godzinowy bar chart, orientacja, godziny,

- **ID:** `t_c470cf6b`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — tooltip na elewacji: wykres godzinowy bar chart, orientacja, godziny, status WT

#### ✅ F4-07 — Frontend — tabela wyników w sidebarze: mieszkanie / elewacja / orientacja / godz

- **ID:** `t_96ac3f4b`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — tabela wyników w sidebarze: mieszkanie / elewacja / orientacja / godz. / status WT

#### ✅ F4-08 — Testy solar — wyniki pvlib vs suncalc.org dla Warszawy (52.23N, 21.03), toleranc

- **ID:** `t_1e7edf1e`
- **Status:** done
- **Assignee:** dev
- **Opis:** Testy solar — wyniki pvlib vs suncalc.org dla Warszawy (52.23N, 21.03), tolerancja ±15min

### Faza 5 — Optymalizator układu

#### ✅ F5-01 — Backend /api/optimizer/run — LP (scipy.optimize) dla prostych obrysów, GA (pymoo

- **ID:** `t_dd98cd9d`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/optimizer/run — LP (scipy.optimize) dla prostych obrysów, GA (pymoo NSGA-II) dla wklęsłych/wielu klatek

#### ✅ F5-02 — Backend — funkcja fitness optymalizatora: pvlib w pętli z cache pozycji słońca (

- **ID:** `t_359496af`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend — funkcja fitness optymalizatora: pvlib w pętli z cache pozycji słońca (raz na sesję), constraint WT §13 + §58

#### ✅ F5-03 — Backend — constraint validation w pętli: adjacency + Dijkstra zasięg klatki + WT

- **ID:** `t_b2e174f4`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend — constraint validation w pętli: adjacency + Dijkstra zasięg klatki + WT §13 min godziny

#### ✅ F5-04 — Frontend — przycisk [▶ Optymalizuj], progress bar (5-30s), cancel button

- **ID:** `t_5261dbca`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — przycisk [▶ Optymalizuj], progress bar (5-30s), cancel button

#### ✅ F5-05 — Frontend — panel porównania: 3 karty side-by-side, miniatura układu (canvas snap

- **ID:** `t_0138b5c4`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — panel porównania: 3 karty side-by-side, miniatura układu (canvas snapshot) + solar_score + wt_compliance_score + total_sun_hours

#### ✅ F5-06 — Frontend — klik na wariant → załaduj do głównego canvasu jako aktywny układ (rep

- **ID:** `t_45e4f171`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — klik na wariant → załaduj do głównego canvasu jako aktywny układ (replace current layout)

### Faza 6 — Eksport danych

#### ✅ F6-01 — Backend /api/export/dxf — ezdxf write: warstwy OBRYS/MIESZKANIA/KOMUNIKACJA/TEKS

- **ID:** `t_7d747421`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/export/dxf — ezdxf write: warstwy OBRYS/MIESZKANIA/KOMUNIKACJA/TEKST/ELEWACJE z atrybutami godzin słońca

#### ✅ F6-02 — Frontend — przycisk [Eksport DXF] → download .dxf

- **ID:** `t_708c006b`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — przycisk [Eksport DXF] → download .dxf

#### ✅ F6-03 — Backend /api/export/json — pełny stan projektu: footprint, apartments, solar, op

- **ID:** `t_cfec375d`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/export/json — pełny stan projektu: footprint, apartments, solar, optimizer results

#### ✅ F6-04 — Frontend — [Eksport JSON] + [Import JSON]: drag&drop wczytanie projektu

- **ID:** `t_ceb5f54b`
- **Status:** done
- **Assignee:** dev
- **Opis:** Frontend — [Eksport JSON] + [Import JSON]: drag&drop wczytanie projektu

#### ✅ F6-05 — Backend /api/export/pdf — weasyprint HTML→PDF: wizualizacja układu (PNG) + tabel

- **ID:** `t_00cbe528`
- **Status:** done
- **Assignee:** dev
- **Opis:** Backend /api/export/pdf — weasyprint HTML→PDF: wizualizacja układu (PNG) + tabela nasłonecznienia + dane lokalizacji

#### ✅ F6-06 — Testy round-trip DXF — eksport → import → porównanie geometrii Shapely (area dif

- **ID:** `t_d2f4e48d`
- **Status:** done
- **Assignee:** dev
- **Opis:** Testy round-trip DXF — eksport → import → porównanie geometrii Shapely (area diff < 0.01m²)

### Faza 7 — Testy E2E i dokumentacja

#### ✅ F7-01 — E2E — pełny flow: import DXF → BSP generuj → korekta ręczna → solar → optymalizu

- **ID:** `t_41c8522a`
- **Status:** done
- **Assignee:** dev
- **Opis:** E2E — pełny flow: import DXF → BSP generuj → korekta ręczna → solar → optymalizuj top-3 → eksport DXF

#### ✅ F7-02 — E2E — obrys wklęsły: L-kształt i U-kształt, weryfikacja podziału na strefy i zas

- **ID:** `t_c60c8814`
- **Status:** done
- **Assignee:** dev
- **Opis:** E2E — obrys wklęsły: L-kształt i U-kształt, weryfikacja podziału na strefy i zasięgu klatek

#### ✅ F7-03 — E2E — program niemożliwy: za duże mieszkania, suma > pow. kondygnacji → czytelny

- **ID:** `t_185ad5c5`
- **Status:** done
- **Assignee:** dev
- **Opis:** E2E — program niemożliwy: za duże mieszkania, suma > pow. kondygnacji → czytelny komunikat + sugestia korekty

#### ✅ F7-04 — Performance — /api/solar/analyze < 3s, /api/optimizer/run LP < 10s, GA < 30s dla

- **ID:** `t_0a1d729e`
- **Status:** done
- **Assignee:** dev
- **Opis:** Performance — /api/solar/analyze < 3s, /api/optimizer/run LP < 10s, GA < 30s dla 20 mieszkań

#### ⏸️ F7-05 — UX review — testy z Bartoszem (architektem): lista poprawek → implementacja

- **ID:** `t_166ee690`
- **Status:** blocked
- **Assignee:** dev
- **Opis:** UX review — testy z Bartoszem (architektem): lista poprawek → implementacja

#### ✅ F7-06 — README — instrukcja uruchomienia Docker Compose, opis endpointów API, opis typol

- **ID:** `t_81e3b664`
- **Status:** done
- **Assignee:** dev
- **Opis:** README — instrukcja uruchomienia Docker Compose, opis endpointów API, opis typologii presetów
