# DOMKO_APP — Typologie Budynków Wielorodzinnych

> Parametry numeryczne dla algorytmu BSP.  
> Źródło: wiedza dziedzinowa (do weryfikacji przez architekta).  
> Format: presety wczytywane przy starcie algorytmu generowania układu.

---

## 1. Klatkowiec wzdłużny (blok klatkowy)

Najbardziej powszechna typologia w Polsce (PRL i deweloperka post-2000).  
Klatka przy elewacji, mieszkania po obu stronach korytarza wewnętrznego.

```
┌──────┬────┬──────┬────┬──────┐  ← elewacja frontowa (pd/pd-wsch)
│  M   │    │  M   │    │  M   │
│front │KOR.│front │KOR.│front │
│      │KLAT│      │KLAT│      │
│  M   │    │  M   │    │  M   │
│ back │    │ back │    │ back │
└──────┴────┴──────┴────┴──────┘  ← elewacja tylna
```

### Parametry BSP

| Parametr | Wartość | Uwagi |
|---|---|---|
| `takt_front_min` | 4.0 m | głębokość mieszkań od elewacji frontowej do korytarza |
| `takt_front_max` | 6.5 m | |
| `takt_back_min` | 4.0 m | głębokość mieszkań od korytarza do elewacji tylnej |
| `takt_back_max` | 6.5 m | |
| `corridor_width` | 1.4 m | szerokość korytarza wewnętrznego (WT §64: min. 1.4m) |
| `staircase_width` | 2.5 m | wymiar klatki prostopadle do korytarza |
| `staircase_depth` | 3.5 m | wymiar klatki wzdłuż korytarza |
| `staircase_position` | `elewacja` | klatka od strony elewacji frontowej lub tylnej |
| `apts_per_staircase` | 2–6 | mieszkania na klatkę na kondygnację |
| `staircase_spacing_min` | 12 m | min. odstęp między klatkami (oś–oś) |
| `staircase_spacing_max` | 24 m | max. odstęp = ~2 × max. dojście/2 |
| `typical_apt_width` | 5.2–9.0 m | szerokość mieszkania wzdłuż elewacji |
| `double_loaded` | `true` | mieszkania po obu stronach korytarza |
| `building_depth_total` | 10–16 m | całkowita głębokość budynku (2 trakty + korytarz) |

### Typowe programy mieszkań

| Pozycja w budynku | Typowy typ | Metraż |
|---|---|---|
| narożna, front | M3/M4 | 55–75 m² |
| środkowa, front | M2/M3 | 38–58 m² |
| narożna, back | M3/M4 | 55–75 m² |
| środkowa, back | M1/M2 | 28–45 m² |

---

## 2. Punktowiec (wieżowiec / blok punktowy)

Klatka centralna, mieszkania dookoła. Typowe dla budynków 6–16 kondygnacji.

```
        N
        │
   ┌────┼────┐
   │ M  │  M │  W
───┤ NW │ NE ├───
   │    KLAT │
   │    KOR. │
───┤ SW │ SE ├───
   │ M  │  M │  E
   └────┼────┘
        │
        S
```

### Parametry BSP

| Parametr | Wartość | Uwagi |
|---|---|---|
| `staircase_position` | `środek` | klatka centralna |
| `staircase_width` | 3.0–4.0 m | klatka + winda |
| `staircase_depth` | 3.0–4.0 m | |
| `corridor_type` | `okrężny` | korytarz otacza klatkę ze wszystkich stron |
| `corridor_width` | 1.5 m | |
| `takt_min` | 4.5 m | od klatki do elewacji zewnętrznej |
| `takt_max` | 7.0 m | |
| `apts_per_floor` | 4–8 | |
| `typical_apt_width` | 4.5–8.0 m | wzdłuż elewacji |
| `double_loaded` | `false` | mieszkania jednostronnie (od klatki na zewnątrz) |
| `building_footprint_ideal` | kwadrat/prostokąt do 1:1.5 | przy większym stosunku traci na wydajności |

### Typowe programy mieszkań

| Orientacja | Typowy typ | Metraż |
|---|---|---|
| S/SE/SW | M2/M3 (lepsze nasłonecznienie) | 38–65 m² |
| E/W | M2/M3 | 38–60 m² |
| N/NE/NW | M1/M2 (gorsze, tańsze) | 28–45 m² |

---

## 3. Galeriowiec

Zewnętrzny korytarz (galeria) wzdłuż jednej elewacji. Mieszkania jednostronne — wszystkie wychodzą na jedną stronę. Popularny w klimacie ciepłym, w PL rzadszy, ale obecny w zabudowie osiedlowej lat 60–70.

```
← galeria (korytarz zewnętrzny, niezadaszony lub półotwarty)
┌────┬────┬────┬────┬────┐  ← elewacja tylna (N lub pd zależnie od orientacji)
│ M  │ M  │ M  │ M  │ M  │
│    │    │    │    │    │
└────┴────┴────┴────┴────┘  ← elewacja frontowa (strona galerii)
KLAT                  KLAT   ← klatki przy narożnikach lub co ~30m
```

### Parametry BSP

| Parametr | Wartość | Uwagi |
|---|---|---|
| `staircase_position` | `narożnik` lub `elewacja_boczna` | |
| `corridor_type` | `zewnętrzny` | galeria wzdłuż elewacji |
| `corridor_width` | 1.5–2.0 m | szersza bo zewnętrzna |
| `takt_min` | 5.0 m | głębokość mieszkań (budynek jednostronny) |
| `takt_max` | 9.0 m | |
| `double_loaded` | `false` | jednostronne |
| `apts_per_staircase` | 4–8 | dostęp z galerii |
| `staircase_spacing_max` | 30 m | WT §58 jednostronne |
| `typical_apt_width` | 4.5–7.5 m | |
| `building_depth_total` | 6.5–11 m | mniejsza niż klatkowiec (1 trakt) |

---

## 4. Klatkowiec narożny / L-kształt

Klatka w narożniku wewnętrznym budynku L-kształtnego. Obsługuje oba skrzydła.  
Typowe dla zabudowy kwartałowej i plomb miejskich.

```
┌─────────────┐
│  skrzydło A │
│  M  M  M    │
│             KLAT ← w narożniku wewnętrznym
│  M  M  M    │    │
└─────────────┘    │ skrzydło B
                   │  M  M  M  │
                   └───────────┘
```

### Parametry BSP

| Parametr | Wartość | Uwagi |
|---|---|---|
| `staircase_position` | `narożnik` | narożnik wewnętrzny (concave vertex) |
| `staircase_coverage` | `oba_skrzydła` | obsługuje skrzydło A i B |
| `max_arm_length` | 28 m | max. długość ramienia (WT §58: 30m - bufor 2m) |
| `corridor_width` | 1.5 m | |
| `takt_min` | 4.5 m | |
| `takt_max` | 6.5 m | |
| `double_loaded` | `true` lub `false` | zależy od szerokości skrzydła |
| `min_wing_width` | 9.0 m | poniżej tej szerokości nie da się zrobić korytarza dwustronnego |

### Uwaga dla algorytmu

Jeśli `arm_length > max_arm_length` → algorytm automatycznie dodaje drugą klatkę przy końcu dłuższego skrzydła.

---

## 5. Szeregowiec wielorodzinny (townhouse / zabudowa segmentowa)

Budynki 2–3 kondygnacyjne, wejścia bezpośrednio z zewnątrz lub przez małe klatki.  
Brak korytarza wspólnego — każde mieszkanie ma własne wejście lub małą klatkę dla 2 mieszkań.

```
front ↓
┌──┬──┬──┬──┬──┬──┐
│M │M │M │M │M │M │
│  │  │  │  │  │  │
│  │  │  │  │  │  │
└──┴──┴──┴──┴──┴──┘
  K  K  K  K  K    ← klatki/wejścia co 1–2 segmenty
```

### Parametry BSP

| Parametr | Wartość | Uwagi |
|---|---|---|
| `staircase_position` | `elewacja` | wejście od strony frontowej |
| `staircase_per_apt` | 0.5–1.0 | 1 klatka na 1–2 mieszkania |
| `corridor_type` | `brak` | brak korytarza wspólnego |
| `takt_min` | 5.5 m | głębokość segmentu |
| `takt_max` | 12.0 m | przy głębszych segmentach antresola |
| `typical_apt_width` | 5.0–8.0 m | szerokość segmentu |
| `double_loaded` | `false` | |
| `building_depth_total` | 8–14 m | |

---

## 6. Mapping: typologia → preset BSP

```python
TYPOLOGY_PRESETS = {
    "klatkowiec_wzdluzny": {
        "takt_front": (4.5, 6.5),
        "takt_back": (4.0, 6.0),
        "corridor_width": 1.5,
        "staircase_dims": (2.5, 3.5),
        "staircase_position": "elewacja",
        "apts_per_staircase": (2, 4),
        "staircase_spacing": (12, 24),
        "double_loaded": True,
    },
    "punktowiec": {
        "takt": (4.5, 7.0),
        "corridor_width": 1.5,
        "staircase_dims": (3.5, 3.5),
        "staircase_position": "środek",
        "apts_per_floor": (4, 8),
        "double_loaded": False,
    },
    "galeriowiec": {
        "takt": (5.0, 9.0),
        "corridor_width": 2.0,
        "staircase_position": "narożnik",
        "staircase_spacing": (15, 30),
        "double_loaded": False,
    },
    "klatkowiec_narozny": {
        "takt": (4.5, 6.5),
        "corridor_width": 1.5,
        "staircase_position": "narożnik",
        "max_arm_length": 28,
        "double_loaded": True,
    },
    "szeregowiec": {
        "takt": (5.5, 12.0),
        "corridor_width": 0,          # brak korytarza
        "staircase_position": "elewacja",
        "staircase_per_apt": 0.5,
        "double_loaded": False,
    },
}
```

---

## 7. Heurystyki doboru typologii na podstawie kształtu obrysu

Algorytm może automatycznie sugerować typologię na podstawie geometrii wejściowej:

| Kształt obrysu | bbox ratio (dł/szer) | Sugerowana typologia |
|---|---|---|
| prostokąt, ratio > 2.0 | wąski prostokąt | klatkowiec wzdłużny |
| prostokąt, ratio 1.0–1.8 | kwadrat/lekki prostokąt | punktowiec |
| L-kształt | dwa ramiona | klatkowiec narożny |
| U-kształt | trzy ramiona | klatkowiec narożny × 2 (dwie klatki) |
| wąski, ratio > 3.0 | bardzo wąski | galeriowiec lub szeregowiec |

> **Do weryfikacji przez Bartosza:** proporcje traktów (zwłaszcza takt_back dla klatkowca) mogą się różnić w zależności od standardu rynkowego vs. deweloperki ekonomicznej. Proszę o korektę wartości min/max na podstawie doświadczenia projektowego.

---

*Plik wygenerowany: 2026-06-30 | Wymaga weryfikacji architekta przed zakodowaniem presetów BSP.*
