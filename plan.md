# DOMKO_APP — Dokumentacja Projektowa

> **Status:** DRAFT v0.3 — gotowy do akceptacji przez Bartosza  
> **Ostatnia aktualizacja:** 2026-06-30  
> **Folder projektu:** `C:\Praca\01 AI\HERMES\DOMKO_APP\`

---

## 1. Opis Produktu

### 1.1 Problem

Architekt projektujący budynek mieszkalny wielorodzinny wykonuje podział kondygnacji na mieszkania ręcznie w CAD. Typowy proces wygląda tak:

1. Import rzutu z DXF → rysowanie linii podziałowych w CAD
2. Ręczne liczenie powierzchni każdego mieszkania
3. Sprawdzanie dostępu do klatki schodowej i korytarza (ręcznie, często pomijane na wstępnym etapie)
4. Sprawdzanie nasłonecznienia (zlecane osobno i czasochłonne)
5. Iteracja — zaczynanie od nowa po każdej zmianie układu

**Efekt:** 2–4 godziny pracy na jeden wariant układu kondygnacji. Sprawdzenie nasłonecznienia to dodatkowe godziny pracy.

### 1.2 Rozwiązanie

DOMKO_APP to narzędzie do wstępnego projektowania układu kondygnacji budynku mieszkalnego wielorodzinnego. Umożliwia:

- Import obrysu kondygnacji z DXF lub narysowanie go na siatce 1m×1m
- Interaktywny podział obrysu na mieszkania z walidacją powierzchni w czasie rzeczywistym
- Automatyczne umieszczanie komunikacji (korytarz + klatka schodowa) z walidacją styku każdego mieszkania
- Analizę nasłonecznienia każdej elewacji zewnętrznej z przypisaniem do konkretnego mieszkania
- Automatyczne ustawienie grubości ściany zewnętrznej i wewnętrznych mieszkanie-komunikacja i mieszkania-mieszkanie.

### 1.3 Użytkownicy docelowi

- Architekci na etapie koncepcji / projektu budowlanego
- Deweloperzy weryfikujący layout zaproponowany przez biuro
- Studenci architektury

### 1.4 Wartość biznesowa

| Bez DOMKO_APP | Z DOMKO_APP |
|---|---|
| 2–4h na wariant układu | ~10 min na wariant |
| Nasłonecznienie — osobne zlecenie | Wbudowane, wynik od razu |
| Brak walidacji WT w czasie rzeczywistym | Walidacja live |
| Iteracja = zaczynanie od nowa w CAD | Zmiana → natychmiastowy wynik |

---

## 2. Funkcjonalności

### 2.1 MVP (wersja 1.0)

#### Moduł A — Import i rysunek obrysu
- [ ] Import pliku DXF — odczyt zamkniętych polilinii jako wielokąt (obrys kondygnacji)
- [ ] Ręczne rysowanie wielokąta na siatce 1m×1m (snapowanie do siatki)
- [ ] Podgląd skali (obrys + wymiary w metrach)
- [ ] Możliwość edycji wierzchołków po imporcie

#### Moduł B — Komunikacja (korytarz + klatka schodowa)
> **Historia:** ten moduł biegnie jako **Etap 1** (patrz §4.1) — przed
> podziałem na mieszkania w module C, nie po nim. Kolejność modułów B/C w
> tym pliku była odwrócona względem faktycznego algorytmu do 2026-07-02
> (§4.1 opisywał poprawną kolejność, ale ten checklist — nie); poprawione.

- [ ] Automatyczne umieszczenie klatki i korytarza przez algorytm (Etap 1 — `place_circulation()`, poprzedza podział na mieszkania w module C)
- [ ] Możliwość ręcznego przesunięcia / zmiany wymiarów klatki po auto-umieszczeniu
- [ ] Walidacja styku: każde mieszkanie musi dzielić co najmniej jeden odcinek ściany z korytarzem lub klatką, długość styku minimum 1,2m,
- [ ] Walidacja wymiarów klatki (według ustawień użytkownika)
- [ ] Walidacja długości korytarza (według ustawień użytkownika)
- [ ] Wizualizacja styków (podświetlenie krawędzi z kontaktem)

#### Moduł C — Program i automatyczny podział na mieszkania
- [ ] **Sidebar parametrów** (zawsze widoczny obok canvasu):
  - Liczba i typy mieszkań (kawalerka (M1), M2, M3, M4, M5+) z docelowymi metrażami
  - Orientacja klatki schodowej (pozycja preferowana: środek / narożnik / konkretna ściana) wymiar klatki (wstępnie 5,7 x 5,2 m ale to ustawiania)
  - Szerokość korytarza (domyślnie 1,4m)
  - Bilans automatyczny: suma programu vs pow. kondygnacji, procent komunikacji
- [ ] **Automatyczny algorytm podziału** (Etap 2 — `subdivide_units()`, patrz §4.1):
  - Na podstawie programu z sidebaru algorytm dzieli **pozostałość po komunikacji** (remainder z modułu B) na mieszkania, nie cały obrys
  - Uwzględnia: minimalne szerokości pomieszczeń, minimalne powierzchnie WT, dostęp do komunikacji
  - Wynik: kompletny układ mieszkań dopasowany do już umieszczonej klatki i korytarza
  - Możliwość generowania różnych wariantów, które są oceniane według parametrów (system punktacji)
- [ ] **Korekta ręczna** po auto-podziale:
  - Przeciąganie linii podziałowych (drag) skok co 0,5m
  - Zmiana przypisania typu mieszkania do segmentu
  - Przerysowanie wybranego segmentu (delete + redraw)
  - Po każdej korekcie: re-walidacja WT na żywo
- [ ] Walidacja w czasie rzeczywistym (na canvasie):
  - Sygnalizacja kolorem: zielony OK / żółty ostrzeżenie / czerwony błąd
  - Lista błędów w sidebarze (klik → podświetlenie segmentu)
- [ ] Etykiety na canvasie: numer mieszkania, typ, powierzchnia

#### Moduł D — Analiza nasłonecznienia
- [ ] Wybór lokalizacji na mapie (Leaflet + OpenStreetMap) → lat/lng
- [ ] Wybór daty analizy (domyślnie: 21.03 — równonoc wiosenna, wymagana przez WT §13)
- [ ] Wyznaczenie elewacji zewnętrznych (krawędzie wielokątów mieszkań stykające się z obrysem budynku)
- [ ] Przypisanie każdej elewacji zewnętrznej do mieszkania
- [ ] Obliczenie liczby godzin bezpośredniego nasłonecznienia elewacji w wybranym dniu (pvlib)
- [ ] Wizualizacja: kolorowe oznaczenie elewacji (gradient od 0h do 6h+, najważniejsze minimum 3h dla mieszkania)
- [ ] Tabela wyników: mieszkanie → elewacja → orientacja (N/NE/E/...) → godziny nasłonecznienia → status WT

#### Moduł E — Optymalizator nasłonecznienia
- [ ] **Optymalizator pozycji klatki** (algorytm genetyczny / LP solver):
  - Kryterium celu: maksymalizacja łącznych godzin nasłonecznienia mieszkań (suma ważona: kawalerki × 0.8, M2+ × 1.0)
  - Zmienne: pozycja klatki (oś X wzdłuż elewacji), szerokość korytarza, podział traktów
  - Constraint: każde mieszkanie ≥ 3h (WT §13), każde mieszkanie ma dostęp do klatki (WT §58)
  - Output: top-3 warianty układu z rankingiem nasłonecznienia + compliance score
  - Implementacja: `scipy.optimize` (LP) lub `DEAP` / `pymoo` (GA); pvlib w pętli fitness function
- [ ] Porównanie wariantów side-by-side (canvas split-view)

#### Moduł F — Eksport
- [ ] **Eksport DXF** — układ kondygnacji z podziałem na warstwy (obrys, mieszkania, komunikacja, etykiety)
- [ ] Eksport JSON — pełny stan projektu (import/load)
- [ ] Eksport PDF — raport nasłonecznienia (tabela + wizualizacja)

### 2.2 Wersja 2.0 (poza MVP)

- Analiza zacienienia przez sąsiednie budynki (import bryły otoczenia z DXF)
- Tryb wielokondygnacyjny (kilka pięter, różne układy)
- Analiza wielodniowa / roczna (heliodon) — pełny wykres rocznego nasłonecznienia

---

## 3. Architektura Techniczna

### 3.1 Stack — DECYZJA: Web App z backendem Python

```
┌─────────────────────────────────────┐
│        FRONTEND (React/Next.js)     │
│  - Konva.js (canvas, rysowanie)     │
│  - Leaflet (mapa, lokalizacja)      │
│  - TailwindCSS (UI)                 │
│  - (brak dxf-parser — DXF tylko backend) │
└───────────────┬─────────────────────┘
                │ REST API (JSON/GeoJSON)
┌───────────────▼─────────────────────┐
│        BACKEND (Python/FastAPI)     │
│  - Shapely (geometria poligonów)    │
│  - ezdxf (import DXF)              │
│  - pvlib / pysolar (nasłonecznienie)│
│  - GeoJSON (format danych)          │
└─────────────────────────────────────┘
```

**Uzasadnienie:**
- Geometria i solar calculations — najdojrzalsze biblioteki są w Pythonie (Shapely, pvlib)
- Frontend React/Next.js — stack znany Bartoszowi, szybki development
- REST API — prosta integracja, łatwe testowanie endpointów
- Brak bazy danych w MVP — projekt trzymany w pamięci sesji / eksportowany do JSON

### 3.2 Biblioteki techniczne

#### Backend Python
| Biblioteka | Zastosowanie | Status |
|---|---|---|
| `ezdxf` | Import DXF, odczyt polilinii/hatchy | ✅ sprawdzona |
| `shapely` | Podział polygonów, area calc, intersections | ✅ sprawdzona |
| `pvlib` | Pozycja słońca (azymut, elewacja), promieniowanie | ✅ sprawdzona |
| `fastapi` | REST API | ✅ sprawdzona |
| `uvicorn` | ASGI server | ✅ sprawdzona |

#### Frontend
| Biblioteka | Zastosowanie | Status |
|---|---|---|
| `konva.js` | Canvas 2D: rysowanie, snapowanie, polygon editing | ✅ rekomendowana |
| `react-konva` | React wrapper dla Konva | ✅ sprawdzona |
| `leaflet` + `react-leaflet` | Mapa do wyboru lokalizacji | ✅ sprawdzona |
| `dxf-parser` | ~~Parsowanie DXF po stronie klienta~~ | **Nie potrzebne** — DXF przetwarzany wyłącznie na backendzie (ezdxf). Frontend robi tylko file upload (multipart/form-data). |

> **Uwaga:** Biblioteki zweryfikowane — nie wymaga dodatkowego researchu.

### 3.6 Presety typologii budynków

Plik `typologies.md` zawiera parametry numeryczne 5 polskich typologii wielorodzinnych, wczytywane przez algorytm BSP jako presety. Sidebar pozwala użytkownikowi wybrać typologię przed generowaniem układu.

Presety zdefiniowane: klatkowiec wzdłużny, punktowiec, galeriowiec, klatkowiec narożny (L-kształt), szeregowiec.

Heurystyka auto-detekcji typologii na podstawie bbox ratio obrysu — algorytm sugeruje preset zanim użytkownik cokolwiek kliknie.

**Plik:** `C:\Praca\01 AI\HERMES\DOMKO_APP\typologies.md` — wymaga weryfikacji przez Bartosza przed zakodowaniem.

```
domko_backend/
├── main.py                  # FastAPI app, routing
├── models/
│   ├── footprint.py         # Pydantic: BuildingFootprint, Apartment, Corridor
│   ├── solar.py             # Pydantic: SolarRequest, SolarResult, FacadeResult
│   └── layout.py            # Pydantic: LayoutProgram, LayoutSession
├── services/
│   ├── dxf_import.py        # ezdxf → Shapely Polygon
│   ├── polygon_ops.py       # split, validate, area, adjacency check
│   ├── solar_calc.py        # pvlib: sun position → facade illumination hours
│   └── wt_validator.py      # Warunki Techniczne: reguły walidacji
├── api/
│   ├── footprint.py         # /api/footprint endpoints
│   ├── layout.py            # /api/layout endpoints
│   ├── solar.py             # /api/solar endpoints
│   └── validate.py          # /api/validate endpoints
└── tests/
    ├── test_dxf_import.py
    ├── test_polygon_ops.py
    └── test_solar_calc.py
```

### 3.7 API Endpoints

#### Footprint
```
POST /api/footprint/import-dxf
  Request:  multipart/form-data { file: .dxf }
  Response: { polygon: GeoJSON Polygon, area: float, dimensions: {...} }

POST /api/footprint/from-points
  Request:  { points: [[x,y], ...] }  # w metrach od punktu (0,0)
  Response: { polygon: GeoJSON Polygon, area: float }
```

#### Layout
```
POST /api/layout/circulation  (NOWY, redesign 2026-07-02 — patrz §4.1)
  Request:  { footprint: GeoJSON, circulation: CirculationSpec }
  Response: { circulation_geometry: GeoJSON, cage_geometries: [GeoJSON, ...],
              remainder: GeoJSON }  # Polygon lub MultiPolygon

POST /api/layout/units  (NOWY, redesign 2026-07-02 — patrz §4.1)
  Request:  { remainder: GeoJSON, apartments: [ApartmentProgram, ...] }
  Response: { apartments: [ApartmentResult, ...], leftover: GeoJSON | null }

POST /api/layout/generate  (wrapper: circulation + units za jednym wywołaniem —
                             używany przez optymalizator i "szybką ścieżkę")

POST /api/layout/split
  Request:  { footprint: GeoJSON, split_line: [[x1,y1],[x2,y2]] }
  Response: { polygons: [GeoJSON, ...], areas: [float, ...] }

POST /api/layout/validate-apartment
  Request:  { polygon: GeoJSON, type: "M1"|"M2"|"M3"|"M4"|"M5" }
  Response: { valid: bool, area: float, errors: [str], warnings: [str] }

POST /api/layout/validate-communication
  Request:  { apartments: [GeoJSON], corridor: GeoJSON, staircase: GeoJSON }
  Response: { all_connected: bool, issues: [{apartment_id, error}] }
```

#### Solar
```
POST /api/solar/analyze
  Request: {
    apartments: [{ id, polygon: GeoJSON }],
    building_footprint: GeoJSON,
    location: { lat, lng },
    date: "YYYY-MM-DD",
    time_step_minutes: 15
  }
  Response: {
    facades: [{
      apartment_id: str,
      edge: [[x1,y1],[x2,y2]],
      orientation_deg: float,
      orientation_label: "N"|"NE"|"E"|...,
      sun_hours: float,
      wt_compliant: bool,
      wt_required_hours: float
    }]
  }
```

#### Validate (Warunki Techniczne)
```
POST /api/validate/full-layout
  Request:  { apartments, corridor, staircase, location, date }
  Response: { score: float, issues: [...], warnings: [...] }
```

#### Optimizer
```
POST /api/optimizer/run
  Request: {
    footprint: GeoJSON,
    program: [{ type: "M1"|"M2"|"M3"|"M4"|"M5", count: int, target_area: float }],
    location: { lat, lng },
    date: "YYYY-MM-DD",
    staircase_mode: "1A"|"1B"|"2"|"3",
    mode: "LP"|"GA",
    max_variants: 3
  }
  Response: {
    variants: [{
      rank: int,
      layout: { apartments: [...], corridor: GeoJSON, staircases: [...] },
      solar_score: float,       // suma godzin nasłonecznienia wszystkich mieszkań
      wt_compliance_score: float, // % mieszkań spełniających WT §13
      total_sun_hours: float,
      violations: [str]
    }]
  }
```

### 3.8 Model danych (frontend state)

```typescript
interface Session {
  footprint: Polygon;          // GeoJSON Polygon — obrys budynku
  apartments: Apartment[];
  corridor: Polygon | null;
  staircase: Polygon | null;
  location: LatLng | null;
  analysisDate: string | null;
  solarResults: SolarResult[] | null;
}

interface Apartment {
  id: string;
  polygon: Polygon;            // GeoJSON
  type: "studio"|"M2"|"M3"|"M4"|"M5";
  targetArea: number;          // m²
  actualArea: number;          // m² — obliczane przez backend
  label: string;               // np. "A-03"
  validation: ApartmentValidation;
}

interface SolarResult {
  apartmentId: string;
  facades: FacadeResult[];
}

interface FacadeResult {
  edge: [Point, Point];
  orientationDeg: number;
  orientationLabel: string;
  sunHours: number;
  wtCompliant: boolean;
}
```

---

## 4. Logika Biznesowa

### 4.1 Algorytm generowania układu — dwa jawne etapy (redesign 2026-07-02)

> **Historia:** pierwotna wersja tej sekcji opisywała tylko ręczny podział linią
> (`split_polygon`, zostaje jako `/layout/split`, patrz niżej). Automatyczny
> generator (dawne `bsp_zones()` w `services/bsp.py`) traktował umieszczenie
> klatki, korytarza i podział na mieszkania jako jedną rekurencyjną funkcję z
> ukrytym założeniem, że każda "strefa" jest prostokątem — audyt z 2026-07-02
> wykazał, że to założenie cicho zawodzi dla realnych obrysów wklęsłych
> (dokładny opis: `docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md`,
> inspiracja: analiza Finch 3D w `ANALIZA_FINCH3D/`). Zastąpione poniższym
> pipeline'em.

**Etap 1 — `place_circulation()` (`services/circulation.py`):** klatka wg
trybu 1a/1b/2/3/auto (bez zmian logiki względem poprzedniej wersji, patrz
§4.3) + korytarz jako pas wzdłuż wnętrza obrysu liczony przez
`footprint.buffer(-width).difference(...)` (dojrzałe operacje GEOS, celowo
NIE straight-skeleton — niestabilny dla wierzchołków wklęsłych, czyli
dokładnie tam gdzie zależy nam na poprawności). Wynik: `circulation_geometry`,
`cage_geometries`, `remainder` (przestrzeń na mieszkania — może być
wklęsła/wieloczęściowa, to oczekiwane).

**Etap 2 — `subdivide_units()` (`services/unit_mix.py`):** (a) realna
dekompozycja `remainder` na prostokąty przez cięcie przez wierzchołki
wklęsłe (nie fikcyjny stały nibble jak poprzednio), (b) dopasowanie programu
mieszkań do prostokątów zachłanną heurystyką najlepszego dopasowania
(zamiast sztywnego FIFO), z tolerancją powierzchni ±3% (inspiracja: Finch
§B.2).

`generate_layout()`/`POST /layout/generate` **zostaje** jako wrapper wołający
oba etapy po kolei — potrzebny m.in. optymalizatorowi, który przeszukuje
warianty pozycji klatki (patrz §4.3, ostatni akapit) i wymaga pełnego wyniku
za jednym wywołaniem. Frontend dostaje też oba etapy osobno
(`/layout/circulation`, `/layout/units`) do jawnych kroków UX — patrz spec.

Ręczny podział linią (dawny §4.1) zostaje bez zmian jako `/layout/split`,
naprawiony tą samą techniką dekompozycji co Etap 2a (dziś gubi powierzchnię
dla obrysów wklęsłych z >2 przecięciami linii).

### 4.2 Walidacja styku z komunikacją

```python
def validate_adjacency(
    apartment: Polygon,
    corridor: Polygon,
    staircase: Polygon,
    min_contact_length: float = 0.9  # min 90cm — drzwi
) -> tuple[bool, str]:
    contact_with_corridor = apartment.boundary.intersection(corridor.boundary)
    contact_with_staircase = apartment.boundary.intersection(staircase.boundary)
    
    total_contact = (
        contact_with_corridor.length + contact_with_staircase.length
    )
    return total_contact >= min_contact_length, ...
```

### 4.3 Typy pozycji klatki schodowej

**Kluczowa zasada:** pozycja klatki bezpośrednio determinuje które elewacje zewnętrzne przypadają mieszkaniom — to najważniejsza zmienna optymalizatora nasłonecznienia. Zmiana pozycji klatki → zmiana podziału budynku → zmiana ekspozycji słonecznej każdego mieszkania.

Cztery tryby — parametr w sidebarze. Tryb 1 ma dwa warianty (front/tył vs dziedziniec):

```
TRYB 1A: PRZY ELEWACJI ZEWNĘTRZNEJ — FRONT / TYŁ
Klatka przylega do elewacji frontowej lub tylnej (ulica / ogród).
Typowe dla budynków klatkowych wzdłużnych.
Algorytm: najdłuższa krawędź zewnętrzna → klatka wyrasta do środka.

┌──────────────────────────────┐
│  M-01  │ KLAT │  M-02  │ M-03│  ← elewacja pd. (ul.)
│        │      │         │    │
└────────┴──────┴─────────┴────┘
          ▲ klatka przy elewacji frontowej

TRYB 1B: PRZY ELEWACJI OD DZIEDZIŃCA (wewnętrzna)
Klatka przy elewacji wewnętrznej (dziedziniec, podwórze).
Charakterystyczne dla zabudowy kwartałowej — klatka "skierowana" w dziedziniec,
elewacja frontowa w całości dostępna dla mieszkań.

Efekt na nasłonecznienie: wszystkie mieszkania mają dostęp do elewacji frontowej
(zazwyczaj lepiej nasłonecznionej) — brak "przerwy" na klatkę od strony ulicy.
Korytarz biegnie od klatki do mieszkań frontowych.

┌──────────────┬──────┬──────────────┐
│    M-01      │ KOR. │    M-02      │  ← elewacja frontowa pd. (ulica) — ciągła
│    (front)   │      │    (front)   │
│──────────────│      │──────────────│
│    M-03      │ KLAT │    M-04      │  ← klatka od strony dziedzińca (N)
│    (back)    │      │    (back)    │
└──────────────┴──────┴──────────────┘
                 ▲ klatka od dziedzińca/podwórza

Algorytm: znajdź krawędź wewnętrzną (dziedziniec) lub najkrótszą krawędź zewnętrzną
→ umieść klatkę; korytarz biegnie wzdłuż całej kondygnacji.

TRYB 2: W ŚRODKU TRAKTU (klatka centralna)
Klatka pływa wewnątrz obrysu, otoczona korytarzem ze wszystkich stron.
Typowe dla budynków punktowych / wieżowców.
Algorytm: środek ciężkości obrysu → umieść klatkę; korytarz okrąża ją dookoła.

┌──────────────────────────────┐
│  M-01  │        │  M-02      │
│        │ KOR.   │            │
│  M-03  │ KLAT.  │  M-04      │
│        │ KOR.   │            │
│  M-05  │        │  M-06      │
└──────────────────────────────┘

TRYB 3: NAROŻNIK
Klatka umieszczona w narożniku obrysu (wypukłym lub przy narożniku wewnętrznym).
Typowe dla budynków L/U-kształtnych — klatka obsługuje oba skrzydła.
Algorytm: znajdź narożnik obrysu → ustaw klatkę na styku dwóch ścian.
```

**Wpływ pozycji klatki na algorytm BSP:**

```
Przykład — ta sama bryła, różna pozycja klatki:

TRYB 1A (klatka od frontu pd.):          TRYB 1B (klatka od dziedzińca N):
┌───┬──┬───┬──┬───┐                      ┌─────────────────────────┐
│ M │KL│ M │KL│ M │ ← front pd. ☀️      │  M-01  │ KOR │  M-02   │ ← front pd. ☀️☀️☀️
│   │AT│   │AT│   │                      │        │ .   │         │
│ M │  │ M │  │ M │ ← back N ❌          │  M-03  │KLAT.│  M-04   │ ← back N ❌
└───┴──┴───┴──┴───┘                      └────────┴─────┴─────────┘
Wynik: część front-pd. "przepada" na       Wynik: cała elewacja pd. dostępna
klatkę → gorsze nasłonecznienie M-01/M-02   dla M-01/M-02 → lepsze nasłonecznienie

Optymalizator wybiera TRYB 1B dla tej orientacji budynku.
```

### 4.4 Problem narożników wewnętrznych (wklęsłe obrysy)

Kluczowe: algorytm musi liczyć **odległość korytarzową** (jak człowiek chodzi), nie euklidesową.

```
Problem — L-kształt z jedną klatką:

┌────────┐
│  M-01  │
│        │──────────────┐
│ KLAT.  │     KOR.     │  M-04  │
│        │──────────────┘        │
│  M-02  │              ┌────────┤
│        │              │  M-05  │
└────────┘              └────────┘

Odległość euklidesowa M-04 → KLATKA: ~8m ✅ (wygląda OK)
Odległość korytarzowa  M-04 → KLATKA: ~22m ✅ (mieści się w 30m)
Odległość korytarzowa  M-05 → KLATKA: ~35m 🔴 (przekracza WT §58 dla jednostronnego)
→ ALGORYTM: konieczna druga klatka lub skrócenie ramienia
```

**Implementacja odległości korytarzowej:**
```python
# Nie używamy distance() z Shapely (to odległość euklidesowa).
# Budujemy graf siatki na rzucie korytarza (grid 0.5m), 
# następnie Dijkstra od drzwi mieszkania do najbliższej klatki.

from shapely.geometry import Polygon, Point
import networkx as nx

def corridor_distance(
    apartment_door: Point,
    staircase: Polygon,
    corridor: Polygon,
    grid_step: float = 0.5
) -> float:
    """Odległość wzdłuż korytarza: drzwi mieszkania → klatka schodowa."""
    G = build_corridor_graph(corridor, grid_step)
    start = nearest_grid_node(G, apartment_door)
    end = nearest_grid_node(G, staircase.centroid)
    return nx.shortest_path_length(G, start, end, weight='weight')
```

**Walidacja liczby klatek:**
```python
def validate_staircase_coverage(
    apartments: list[Apartment],
    staircases: list[Polygon],
    corridor: Polygon,
    max_corridor_distance: float  # z WT §58: 30m jednostronne / 40m dwustronne
) -> list[ValidationError]:
    errors = []
    for apt in apartments:
        door = apt.get_door_point(corridor)
        min_dist = min(
            corridor_distance(door, sc, corridor)
            for sc in staircases
        )
        if min_dist > max_corridor_distance:
            errors.append(ValidationError(
                apartment_id=apt.id,
                message=f"Odległość do klatki: {min_dist:.1f}m > {max_corridor_distance}m (WT §58)",
                severity="error"
            ))
    return errors
```

**Sidebar — parametr min. odległości między klatkami:**
```
KOMUNIKACJA
─────────────────────────
Pozycja klatki:  [● Elewacja] [○ Środek] [○ Narożnik]
Klatka poza obrysem: [ ] (wyłączone)
Min. wymiar klatki: [1.2] m × [1.4] m
─────────────────────────
Max. dojście do klatki:
  [● WT §58 auto] = 30m jednostronne
  [○ Wpisz ręcznie]: [___] m
─────────────────────────
Wiele klatek:
  Min. odległość między klatkami: [15] m
  [✓] Dodaj klatkę gdy zasięg przekroczony
─────────────────────────
Szerokość korytarza: [1.5] m
```

### 4.5 Algorytm analizy nasłonecznienia

```python
# Dla każdej krawędzi zewnętrznej mieszkania:
# 1. Sprawdź czy krawędź leży na granicy obrysu budynku (elewacja zewnętrzna)
# 2. Oblicz wektor normalny ściany (orientacja elewacji)
# 3. Dla każdego kroku czasowego w ciągu dnia (co 5 min):
#    a. pvlib.solarposition.get_solarposition(time, lat, lng) → azymut, elewacja
#    b. Oblicz kąt między wektorem słońca a normalną ściany
#    c. Jeśli kąt < 90° i elewacja słońca > 0° → słońce pada na elewację
# 4. Zlicz kroki z nasłonecznieniem × 15min → godziny

def analyze_facade_sunlight(
    edge: tuple[Point, Point],
    lat: float,
    lng: float,
    date: datetime.date,
    time_step_min: int = 5
) -> float:
    wall_normal = compute_normal_vector(edge)
    times = pd.date_range(
        start=f"{date} 04:00", end=f"{date} 21:00",
        freq=f"{time_step_min}min", tz="Europe/Warsaw"
    )
    location = pvlib.location.Location(lat, lng, tz="Europe/Warsaw")
    solar_pos = location.get_solarposition(times)
    
    sun_hours = 0.0
    for _, row in solar_pos.iterrows():
        if row.apparent_elevation > 0:
            sun_vec = solar_azimuth_to_vector(row.azimuth)
            if dot_product(sun_vec, wall_normal) > 0:
                sun_hours += time_step_min / 60.0
    return sun_hours
```

### 4.6 Warunki Techniczne — reguły walidacji

Podstawa prawna: **Rozporządzenie Ministra Infrastruktury z dnia 12 kwietnia 2002 r. w sprawie warunków technicznych, jakim powinny odpowiadać budynki i ich usytuowanie** (Dz.U. 2022 poz. 1225 z późn. zm.)

| Parametr | Wartość | Paragraf WT |
|---|---|---|
| Min. pow. mieszkania (1 pokój, tzw. kawalerka) | 25 m² | §94 ust. 1 |
| Min. pow. pokoju w mieszkaniu wielopokojowym | 8 m² | §94 ust. 2 |
| Min. szerokość pokoju | 2,4 m | §94 ust. 2 |
| Min. pow. kuchni (przy oknie) | brak min. wg WT (zwyczajowo 5–6 m²) | — |
| Min. szerokość korytarza komunikacyjnego wewnątrz mieszkania | 1,0 m | §94 ust. 4 |
| Min. szerokość wewnętrznego korytarza budynku wielorodzinnego | 1,4 m przy drzwiach / 1,2 m w prześwitach | §64 |
| Min. szerokość biegu schodowego (budynki ZL IV, klat. ogólnodostępne) | 1,2 m | §68 ust. 1 |
| Min. szer. spocznika na każdym poziomie | 1,2 m (przy schodach prostych) | §68 ust. 3 |
| Max. dojście do klatki — komunikacja jednostronna | 30 m | §58 ust. 4 |
| Max. dojście do klatki — komunikacja dwustronna | 40 m | §58 ust. 4 |
| **Nasłonecznienie — data analizy** | **równonoc wiosenna = 21 marca** | **§13 ust. 1** |
| **Nasłonecznienie — min. czas w ciągu doby** | **3 godziny** (dla co najmniej 1 pokoju w mieszkaniu) | **§13 ust. 1** |
| **Nasłonecznienie — jakiego pomieszczenia dotyczy** | pokój dzienny (lub 1 pokój w kawalerce) | **§13 ust. 1** |
| Nasłonecznienie — wyjątek dla zabudowy śródmiejskiej | dopuszczalne 1,5 h przy gęstej zabudowie | §13 ust. 2 |
| Orientacja — brak wymogu kierunku | WT nie zakazuje elewacji N; wymaga 3h słońca faktycznego | §13 ust. 1 |

**Kluczowe ustalenia dla algorytmu:**

1. **Data: 21 marca** (równonoc wiosenna) — jedyna data wymagana przez WT. Algorytm domyślnie analizuje ten dzień.

2. **Zakres: 1 pokój na mieszkanie** — nie każda elewacja musi mieć 3h; wystarczy że *co najmniej 1 pokój* w mieszkaniu spełnia warunek. Oznacza to że:
   - Jeśli mieszkanie ma elewację E (3h ✅) i N (0h ❌) → mieszkanie jest **ZGODNE** z WT
   - Algorytm przypisuje wyniki do *mieszkania*, nie do każdej elewacji z osobna

3. **Definicja nasłonecznienia** — bezpośrednie promieniowanie słoneczne padające na płaszczyznę elewacji (nie tylko na okno). Algorytm: `dot(sun_vector, wall_normal) > 0` przy `solar_elevation > 0°`

4. **PN-EN 17037** (Daylight in Buildings) — norma **komplementarna**, nie zastępuje WT §13. Dotyczy natężenia dziennego światła dziennego (daylight factor), nie bezpośredniego nasłonecznienia. MVP może ją pominąć.

5. **Wyjątek śródmiejski** — 1,5h zamiast 3h. Implementacja: toggle w sidebarze "Zabudowa śródmiejska (§13 ust. 2)".

---

## 5. UX / Flow aplikacji

### 5.1 Układ interfejsu — Sidebar + Canvas

Zamiast sekwencyjnego wizarda: **persistentny sidebar parametrów** widoczny zawsze obok canvasu. Użytkownik może w dowolnej chwili zmienić parametry i przerenderować wynik algorytmu.

```
┌──────────────────────┬─────────────────────────────────────────┐
│   SIDEBAR (320px)    │           CANVAS (reszta ekranu)        │
│                      │                                         │
│ [Import DXF]         │   ┌─────────────────────────────────┐   │
│ [Rysuj obrys]        │   │                                 │   │
│ ─────────────────    │   │     Interaktywny canvas         │   │
│ PROGRAM MIESZKAŃ     │   │     Siatka 1m × 1m              │   │
│ Kawalerki: 2 × 28m²  │   │                                 │   │
│ M2:        4 × 45m²  │   │  [A-01]  [A-02]  [KLAT.]       │   │
│ M3:        3 × 65m²  │   │  28,4m²  44,9m²                 │   │
│ M4:        1 × 85m²  │   │                                 │   │
│ ─────────────────    │   │  [A-03]  [KOR.]  [A-04]        │   │
│ KOMUNIKACJA          │   │  64,2m²          43,8m²         │   │
│ Klatka: narożnik     │   │                                 │   │
│ Korytarz: 1,5m       │   └─────────────────────────────────┘   │
│ ─────────────────    │                                         │
│ [▶ Generuj układ]    │   [Zoom +] [Zoom -] [Fit]  [Siatka]    │
│                      │                                         │
│ WALIDACJA WT:        │   Tryb: [Zaznacz] [Przesuń linię]       │
│ ✅ A-01 28,4m² OK    │         [Analiza słońca]                │
│ ✅ A-02 44,9m² OK    │                                         │
│ ⚠️ A-04 43,8m² (-1%) │   NASŁONECZNIENIE (po analizie):        │
│ 🔴 A-05 brak klatki  │   [Mapa — kliknij lokalizację]          │
│ ─────────────────    │   Data: [21.03.2026]                    │
│ [Eksport DXF]        │   [▶ Analizuj]                          │
│ [Eksport JSON]       │                                         │
│ [Raport PDF]         │                                         │
└──────────────────────┴─────────────────────────────────────────┘
```

### 5.2 Flow pracy (nie-sekwencyjny)

```
1. OBRYS           Import DXF lub rysowanie na siatce
        ↓
2. PROGRAM         Wypełnienie sidebaru: typy i liczba mieszkań
        ↓
3. GENERUJ         Klik [▶ Generuj układ] → algorytm BSP
        ↓
4. KOREKTA         Drag linii podziałowych, zmiana typów, edit klatki
   ↑               (powrót do 3 po zmianie parametrów w sidebarze)
        ↓
5. SŁOŃCE          Klik lokalizacji na mapie + data → [▶ Analizuj]
        ↓
6. EKSPORT         DXF / JSON / PDF
```

Kroki 3 i 4 są iteracyjne — zmiana parametru w sidebarze resetuje propozycję, ale zachowuje ręczne korekty jako "pinned moves" (o ile nie kolidują z nową propozycją).


---

## 6. WBS — Lista Zadań Deweloperskich

### Faza 0: Setup (2–3 dni)
- [ ] **F0-01** Inicjalizacja repo (monorepo: `/frontend`, `/backend`)
- [ ] **F0-02** Backend: FastAPI + uvicorn + Shapely + pvlib + ezdxf — środowisko dev (`uv` / `pip`)
- [ ] **F0-03** Frontend: Next.js + Konva.js + Tailwind + react-leaflet — scaffolding
- [ ] **F0-04** Docker Compose: backend + frontend w jednym poleceniu (`docker compose up`)
- [ ] **F0-05** CI: lint + testy przy każdym commicie (GitHub Actions)
- [ ] **F0-06** Struktura folderów projektu (jak w §3.3)

### Faza 1: Import i rysunek obrysu (3–4 dni)
- [ ] **F1-01** Backend: `POST /api/footprint/import-dxf` — ezdxf → Shapely Polygon (LWPOLYLINE, POLYLINE, HATCH)
- [ ] **F1-02** Backend: `POST /api/footprint/from-points` — walidacja zamknięcia, self-intersection check
- [ ] **F1-03** Frontend: canvas z siatką 1m (Konva.js), zoom, pan, fit-to-screen
- [ ] **F1-04** Frontend: rysowanie wielokąta — klik po klik, snap do siatki, zamknięcie dwuklikiem
- [ ] **F1-05** Frontend: upload DXF (drag & drop) → call API → narysowanie polygonu
- [ ] **F1-06** Frontend: edycja wierzchołków obrysu (drag & drop punktów)
- [ ] **F1-07** Frontend: podgląd wymiarów boków + łączna powierzchnia w sidebarze
- [ ] **F1-08** Testy: DXF z prostokątem, L-kształtem, polygonami wklęsłymi

### Faza 2: Sidebar parametrów i BSP algorytm (6–8 dni — core MVP)
- [ ] **F2-01** Frontend: sidebar komponent (320px, scrollowalny, zawsze widoczny)
- [ ] **F2-02** Frontend: formularz programu — `ApartmentTypeRow` (typ, liczba, docelowy m²), bilans live
- [ ] **F2-03** Frontend: parametry komunikacji w sidebarze:
  - Pozycja klatki: radio [1A: Elewacja front/tył / 1B: Dziedziniec/wewnętrzna / 2: Środek traktu / 3: Narożnik]
  - Toggle: klatka poza obrysem (domyślnie wyłączone)
  - Min. wymiar klatki (szer. × głęb., domyślnie 5.7m × 5.2m)
  - Max. dojście do klatki: [WT auto = 30m] lub [ręcznie]
  - Wiele klatek: min. odległość między klatkami + auto-dodawanie gdy zasięg przekroczony
  - Szerokość korytarza (domyślnie 1.4m)
- [ ] **F2-04** Backend: `POST /api/layout/generate` — algorytm BSP:
  - Krok 1: wyznaczenie pozycji klatki schodowej (wg parametru + sprawdzenie WT)
  - Krok 2: wygenerowanie korytarza (prostoliniowy wzdłuż najdłuższej osi)
  - Krok 3: podział pozostałej powierzchni na mieszkania (BSP: linie prostopadłe do osi korytarza)
  - Krok 4: dopasowanie powierzchni mieszkań do programu (iteracja: przesuń linie graniczne)
  - Krok 5: walidacja WT każdego mieszkania
- [ ] **F2-05** Backend: obsługa wielokątów wklęsłych w BSP (convex decomposition → podział na strefy)
- [ ] **F2-06** Backend: `POST /api/layout/split` — manualne przecięcie polygonu linią (Shapely split)
- [ ] **F2-07** Frontend: render wyniku algorytmu na canvasie (klatka, korytarz, mieszkania w kolorach)
- [ ] **F2-08** Frontend: tryb "przesuń linię" — drag & drop linii granicznych między mieszkaniami
- [ ] **F2-09** Frontend: re-call `/api/layout/validate-apartment` po każdym dragging → live walidacja
- [ ] **F2-10** Frontend: "pinned moves" — zapamiętanie ręcznych korekt przy re-generacji
- [ ] **F2-11** Frontend: przycisk [Regeneruj układ] z zachowaniem pinnedMoves
- [ ] **F2-12** Frontend: etykiety na mieszkaniach (ID, typ, m²), klikalność → podświetlenie w sidebarze

### Faza 3: Walidacja WT (2–3 dni)
- [ ] **F3-01** Backend: moduł `wt_validator.py` — pełna tabela reguł (§94, §64, §68, §58, §13)
- [ ] **F3-02** Backend: `POST /api/validate/apartment` — min pow., min szerokość, typ
- [ ] **F3-03** Backend: `POST /api/validate/communication`:
  - adjacency check (Shapely boundary intersection, min. 90cm kontaktu)
  - **odległość korytarzowa** (Dijkstra po grafie siatki korytarza 0.5m, networkx) — nie euklidesowa
  - walidacja zasięgu każdego mieszkania do najbliższej klatki vs. parametr max. dojścia
  - walidacja min. odległości między klatkami
  - walidacja wymiarów klatki (WT §68)
  - obsługa klatki poza obrysem (gdy toggle włączony: klatka może mieć centroid poza footprintem)
- [ ] **F3-04** Backend: `POST /api/validate/full-layout` — agregacja wszystkich błędów
- [ ] **F3-05** Frontend: lista błędów/ostrzeżeń w sidebarze (klik → podświetlenie na canvasie)
- [ ] **F3-06** Frontend: kolorowanie segmentów (zielony/żółty/czerwony)

### Faza 4: Analiza nasłonecznienia (5–6 dni)
- [ ] **F4-01** Frontend: mapa Leaflet w canvasie (tryb "wybierz lokalizację") → lat/lng do state
- [ ] **F4-02** Frontend: date picker (domyślnie 21.03)
- [ ] **F4-03** Backend: `POST /api/solar/analyze`:
  - Wyznaczenie elewacji zewnętrznych (krawędzie na granicy obrysu budynku)
  - Przypisanie krawędzi do mieszkań
  - pvlib: pętla po czasie (co 15 min, od wschodu do zachodu słońca)
  - Obliczenie dot product: wektor słońca · normalna ściany → czy pada
  - Zliczanie godzin
- [ ] **F4-04** Backend: orientacja elewacji (azymut normalnej → N/NE/E/SE/S/SW/W/NW)
- [ ] **F4-05** Backend: porównanie z WT §13 (min. 3h na 21.03)
- [ ] **F4-06** Frontend: tryb "nasłonecznienie" — elewacje kolorowane gradientem (niebieski→żółty→czerwony)
- [ ] **F4-07** Frontend: tooltip na elewacji — wykres godzinowy nasłonecznienia (bar chart)
- [ ] **F4-08** Frontend: tabela wyników w sidebarze (mieszkanie, elewacje, status WT)
- [ ] **F4-09** Testy: wyniki pvlib vs kalkulator zewnętrzny (suncalc.org) dla Warszawy 21.03

### Faza 5: Optymalizator nasłonecznienia (4–5 dni)
- [ ] **F5-01** Backend: `POST /api/optimizer/run`:
  - Wariant A (LP — szybki, deterministyczny): `scipy.optimize.linprog` z pvlib w pętli oceny
  - Wariant B (GA — wolniejszy, elastyczny): `pymoo` NSGA-II (multi-objective: max słońce + min błędy WT)
  - Rekomendacja MVP: LP dla prostych obrysów, GA gdy ≥ 2 klatki lub obrys wklęsły
  - Parametry wejściowe: footprint, program mieszkań, lokalizacja, data, tryb pozycji klatki (1A/1B/2/3)
  - Output: lista top-3 wariantów `{layout, solar_score, wt_compliance_score, total_sun_hours}`
- [ ] **F5-02** Backend: funkcja fitness — wywołanie pvlib dla każdego kandydatury układu (cache sun position)
- [ ] **F5-03** Backend: constraint validation w pętli optymalizatora (adjacency + WT §58 + WT §13)
- [ ] **F5-04** Frontend: przycisk [▶ Optymalizuj] → progress bar (może trwać 5–30s)
- [ ] **F5-05** Frontend: panel porównania wariantów — 3 karty side-by-side (miniatura układu + score)
- [ ] **F5-06** Frontend: klik na wariant → załaduj do głównego canvasu jako aktywny układ

### Faza 6: Eksport (3–4 dni)
- [ ] **F6-01** Backend: `GET /api/export/dxf` — ezdxf write:
  - Warstwa `OBRYS` — obrys budynku (kolor: biały)
  - Warstwa `MIESZKANIA` — polygony mieszkań (kolor wg typu)
  - Warstwa `KOMUNIKACJA` — klatka + korytarz (kolor: szary)
  - Warstwa `TEKST` — etykiety (ID, typ, m²)
  - Warstwa `ELEWACJE` — krawędzie zewnętrzne z atrybutem godzin słońca
- [ ] **F6-02** Frontend: przycisk [Eksport DXF] → download pliku
- [ ] **F6-03** Backend: `GET /api/export/json` — pełny stan projektu (footprint, apartments, solar)
- [ ] **F6-04** Frontend: [Eksport JSON] + [Import JSON] (wczytanie projektu)
- [ ] **F6-05** Backend: `GET /api/export/pdf` — raport nasłonecznienia (HTML→PDF przez weasyprint lub reportlab):
  - Wizualizacja układu (PNG z canvasu)
  - Tabela: mieszkanie, elewacja, orientacja, godziny, status WT
  - Dane lokalizacji i daty analizy
- [ ] **F6-06** Testy: round-trip DXF (eksport → import → porównanie geometrii)

### Faza 7: Testy E2E i polish (2–3 dni)
- [ ] **F7-01** E2E: pełny flow — import DXF → generuj → korekta → solar → optymalizuj → eksport DXF
- [ ] **F7-02** E2E: obrys wklęsły (np. L-kształt, U-kształt)
- [ ] **F7-03** E2E: program niemożliwy do zmieszczenia (za duże mieszkania) → czytelny komunikat błędu
- [ ] **F7-04** Performance: `/api/solar/analyze` < 3s, `/api/optimizer/run` < 30s dla 20 mieszkań
- [ ] **F7-05** UX: testy z architektem (Bartosz) — feedback → poprawki
- [ ] **F7-06** Dokumentacja: README z instrukcją uruchomienia (Docker Compose)

---

## 7. Otwarte Decyzje / TBD

### Decyzje zamknięte

| # | Decyzja | Rozstrzygnięcie |
|---|---|---|
| D1 | MVP online/offline? | **Online** — mapa Leaflet wymaga internetu do kafelków OSM; pvlib działa offline. Web app na localhost zakłada dostęp do internetu. Lokalizacja projektu wybierana klikiem na mapę → lat/lng. |
| D2 | Automatyczny podział → MVP? | **TAK** — BSP algorytm w MVP, korekta ręczna po auto-podziale |
| D3 | Zapis projektu | **JSON** — eksport/import pliku; localStorage tylko dla autosave (backup co 30s) |
| D4a | Klatka poza obrysem | **Opcja toggle** w sidebarze (domyślnie: wyłączone) |
| D4b | Pozycja klatki | **3 tryby** (parametr w sidebarze): przy elewacji zewnętrznej / w środku traktu / narożnik |
| D4c | Min. odległość między klatkami | **Parametr** w sidebarze (domyślnie: z WT §58); algorytm wymusza min. 1 klatkę na X metrów korytarza |

### TBD — pozostałe otwarte kwestie

| # | Kwestia | Priorytet |
|---|---|---|
| R1 | U-kształt w MVP | **Rozwiązany** — U-kształt = dwa ramiona L z dwiema klatkami. Algorytm wykrywa U-kształt przez bbox ratio + concave vertices, decomponuje na dwie strefy klatkowca narożnego. Nie wymaga convex decomposition — wystarczy rozpoznanie dwóch narożników wewnętrznych i przypisanie klatki do każdego. Koszt: +1 dzień w Fazie 2. |
| R2 | Wyjątek śródmiejski (§13 ust. 2): toggle w sidebarze — domyślnie włączony czy wyłączony? | Niski |
| R3 | Eksport PDF: weasyprint (HTML→PDF, prostszy) vs reportlab (programmatic, elastyczniejszy) | Techniczny, decyzja dewelopera |

> **Uwaga dot. WT:** Wartości §94 (min. pow. pokoju 8m², min. szerokość 2,4m) i §13 (3h/21.03) są zweryfikowane wg Dz.U. 2022 poz. 1225. Bartosz jako architekt z uprawnieniami powinien potwierdzić przed kodowaniem modułu `wt_validator.py` — przepisy mogły ulec zmianie po nowelizacji 2023–2024.

---

## 8. Harmonogram orientacyjny

| Faza | Zakres | Czas | Kumulatywnie |
|---|---|---|---|
| F0: Setup | repo, Docker, CI | 2–3 dni | ~3 dni |
| F1: Obrys | DXF import, canvas, siatka | 3–4 dni | ~7 dni |
| F2: BSP + Sidebar | algorytm podziału, korekta ręczna | 6–8 dni | ~15 dni |
| F3: Walidacja WT | reguły, live feedback | 2–3 dni | ~18 dni |
| F4: Solar | pvlib, mapa, elewacje | 5–6 dni | ~24 dni |
| F5: Optymalizator | LP/GA, top-3 warianty, porównanie | 4–5 dni | ~29 dni |
| F6: Eksport | DXF, JSON, PDF | 3–4 dni | ~33 dni |
| F7: E2E + polish | testy, UX, README | 2–3 dni | ~36 dni |

**Szacowany czas MVP: 6–8 tygodni** (przy pełnym zaangażowaniu developera)

> Faza 5 (Optymalizator) jest najbardziej niepewna czasowo — pvlib w pętli GA może być wolne. Rekomendacja: zacznij od LP (deterministyczny, szybki), GA dodaj w iteracji gdy LP nie wystarczy.

---

*Dokument wymaga akceptacji Bartosza przed rozpoczęciem developmentu.*  
*Po akceptacji: wersja 1.0, zamrożenie zakresu MVP.*
