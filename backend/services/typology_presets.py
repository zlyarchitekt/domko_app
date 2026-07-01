"""Typology presets and auto-detection heuristic — see typologies.md.

Two responsibilities (F2-13 + F2-14):
1. TYPOLOGY_PRESETS: numeric BSP parameters per building typology, transcribed
   from typologies.md §6 (`TYPOLOGY_PRESETS` python block in that doc).
2. suggest_typology(): a geometric heuristic (bbox ratio + concave vertex
   count) that suggests a typology before the user picks one, per
   typologies.md §7 and plan.md §3.6.

NOTE: not every preset parameter (takt ranges, staircase_spacing,
double_loaded, staircase_per_apt) has a corresponding field in
services.layout.LayoutInput yet — the BSP algorithm only consumes
corridor_width_m/cage_size_m/place_cage today. `to_layout_defaults()` maps
what is consumable now; the rest is exposed on the preset for F2-04 to wire
up when the cage-position-mode rework lands (see zadania-kanban.md F2-04).
"""

from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from services.bsp import concave_vertices

KLATKOWIEC_WZDLUZNY = "klatkowiec_wzdluzny"
PUNKTOWIEC = "punktowiec"
GALERIOWIEC = "galeriowiec"
KLATKOWIEC_NAROZNY = "klatkowiec_narozny"
SZEREGOWIEC = "szeregowiec"

ALL_TYPOLOGIES = (
    KLATKOWIEC_WZDLUZNY,
    PUNKTOWIEC,
    GALERIOWIEC,
    KLATKOWIEC_NAROZNY,
    SZEREGOWIEC,
)


@dataclass(frozen=True)
class TypologyPreset:
    key: str
    label: str
    staircase_position: str
    corridor_width_m: float
    staircase_dims_m: tuple[float, float]
    double_loaded: bool
    takt_m: tuple[float, float]
    """(min, max) głębokość traktu — parametr wejściowy dla przyszłego F2-04."""
    staircase_spacing_m: tuple[float, float] | None = None
    max_arm_length_m: float | None = None
    staircase_per_apt: float | None = None
    apts_per_staircase: tuple[int, int] | None = None


TYPOLOGY_PRESETS: dict[str, TypologyPreset] = {
    KLATKOWIEC_WZDLUZNY: TypologyPreset(
        key=KLATKOWIEC_WZDLUZNY,
        label="Klatkowiec wzdłużny",
        staircase_position="elewacja",
        corridor_width_m=1.5,
        staircase_dims_m=(2.5, 3.5),
        double_loaded=True,
        takt_m=(4.5, 6.5),
        staircase_spacing_m=(12.0, 24.0),
        apts_per_staircase=(2, 4),
    ),
    PUNKTOWIEC: TypologyPreset(
        key=PUNKTOWIEC,
        label="Punktowiec",
        staircase_position="środek",
        corridor_width_m=1.5,
        staircase_dims_m=(3.5, 3.5),
        double_loaded=False,
        takt_m=(4.5, 7.0),
        apts_per_staircase=(4, 8),
    ),
    GALERIOWIEC: TypologyPreset(
        key=GALERIOWIEC,
        label="Galeriowiec",
        staircase_position="narożnik",
        corridor_width_m=2.0,
        staircase_dims_m=(2.0, 2.0),
        double_loaded=False,
        takt_m=(5.0, 9.0),
        staircase_spacing_m=(15.0, 30.0),
    ),
    KLATKOWIEC_NAROZNY: TypologyPreset(
        key=KLATKOWIEC_NAROZNY,
        label="Klatkowiec narożny / L-kształt",
        staircase_position="narożnik",
        corridor_width_m=1.5,
        staircase_dims_m=(2.5, 2.5),
        double_loaded=True,
        takt_m=(4.5, 6.5),
        max_arm_length_m=28.0,
    ),
    SZEREGOWIEC: TypologyPreset(
        key=SZEREGOWIEC,
        label="Szeregowiec wielorodzinny",
        staircase_position="elewacja",
        corridor_width_m=0.0,
        staircase_dims_m=(1.2, 1.2),
        double_loaded=False,
        takt_m=(5.5, 12.0),
        staircase_per_apt=0.5,
    ),
}


def get_preset(key: str) -> TypologyPreset:
    try:
        return TYPOLOGY_PRESETS[key]
    except KeyError as exc:
        raise ValueError(
            f"Unknown typology '{key}'. Valid options: {', '.join(ALL_TYPOLOGIES)}."
        ) from exc


def to_layout_defaults(preset: TypologyPreset) -> dict:
    """Map a preset onto the LayoutInput fields the BSP algorithm consumes today.

    Fields with no current consumer (takt_m, staircase_spacing_m, ...) are
    intentionally omitted here — see module docstring.
    """
    cage_size = sum(preset.staircase_dims_m) / 2.0
    return {
        "corridor_width_m": preset.corridor_width_m if preset.corridor_width_m > 0 else 1.2,
        "cage_size_m": cage_size,
        "place_cage": preset.corridor_width_m > 0,  # szeregowiec has no shared corridor/cage
    }


# ═══════════════════════════════════════════════════════════════════
# Heurystyka auto-detekcji typologii (typologies.md §7)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class TypologySuggestion:
    typology: str
    bbox_ratio: float
    concave_vertex_count: int
    rationale: str
    suggested_cage_count: int = 1
    alternative: str | None = None
    """Druga sensowna typologia dla tego kształtu, gdy tabela §7 wskazuje dwie możliwości."""


def _bbox_ratio(footprint: Polygon) -> float:
    minx, miny, maxx, maxy = footprint.bounds
    width = maxx - minx
    height = maxy - miny
    if width <= 0 or height <= 0:
        return 1.0
    long_side, short_side = (width, height) if width >= height else (height, width)
    return long_side / short_side if short_side > 0 else float("inf")


def suggest_typology(footprint: Polygon) -> TypologySuggestion:
    """Suggest a typology preset from footprint geometry alone (typologies.md §7).

    | bbox ratio | wierzchołki wklęsłe | sugestia |
    |---|---|---|
    | dowolny | >= 2 | klatkowiec narożny x2 (U-kształt) |
    | dowolny | 1 | klatkowiec narożny (L-kształt) |
    | > 3.0 | 0 | szeregowiec (galeriowiec jako alternatywa) |
    | > 1.8 | 0 | klatkowiec wzdłużny |
    | <= 1.8 | 0 | punktowiec |
    """
    ratio = _bbox_ratio(footprint)
    concave = concave_vertices(footprint)
    concave_count = len(concave)

    if concave_count >= 2:
        return TypologySuggestion(
            typology=KLATKOWIEC_NAROZNY,
            bbox_ratio=round(ratio, 2),
            concave_vertex_count=concave_count,
            suggested_cage_count=2,
            rationale=(
                f"{concave_count} wierzchołki wklęsłe (U-kształt lub bardziej złożony) — "
                "klatkowiec narożny z dwiema klatkami, po jednej na ramię (typologies.md §7)."
            ),
        )

    if concave_count == 1:
        return TypologySuggestion(
            typology=KLATKOWIEC_NAROZNY,
            bbox_ratio=round(ratio, 2),
            concave_vertex_count=concave_count,
            suggested_cage_count=1,
            rationale="1 wierzchołek wklęsły (L-kształt) — klatkowiec narożny, klatka w narożniku wewnętrznym.",
        )

    if ratio > 3.0:
        return TypologySuggestion(
            typology=SZEREGOWIEC,
            bbox_ratio=round(ratio, 2),
            concave_vertex_count=concave_count,
            alternative=GALERIOWIEC,
            rationale=(
                f"Obrys bardzo wąski (bbox ratio {ratio:.1f} > 3.0) — szeregowiec lub galeriowiec "
                "(typologies.md §7); wybrano szeregowiec jako domyślną sugestię."
            ),
        )

    if ratio > 1.8:
        return TypologySuggestion(
            typology=KLATKOWIEC_WZDLUZNY,
            bbox_ratio=round(ratio, 2),
            concave_vertex_count=concave_count,
            rationale=f"Wąski prostokąt (bbox ratio {ratio:.1f} > 1.8) — klatkowiec wzdłużny.",
        )

    return TypologySuggestion(
        typology=PUNKTOWIEC,
        bbox_ratio=round(ratio, 2),
        concave_vertex_count=concave_count,
        rationale=f"Kwadrat/lekki prostokąt (bbox ratio {ratio:.1f} <= 1.8) — punktowiec.",
    )
