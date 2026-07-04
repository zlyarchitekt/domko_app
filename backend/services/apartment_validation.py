"""Aggregate validation of a full apartment layout against WT thresholds.

Combines three independently-testable layers into one 0-100 score + error list:
- apartment-level checks (area §94 ust.1 -- real WT; room width -- design
  heuristic, not WT, see wt_validation.py's MIN_ROOM_WIDTH_M) — this module
- geometric building-code rules (§64, §68, §58) — services/wt_validation.py
- communication/adjacency checks (contact length, cage reach, cage spacing) —
  services/wt_validation.py's validate_communication()

See zadania-kanban.md F3-01/F3-03/F3-04/F3-07 for the history of this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.layout import ApartmentCell, LayoutResult
from services.wt_validation import (
    WTRule,
    validate_communication,
    validate_layout_wt,
)

MIN_ROOM_WIDTH_M = 2.4  # Zalecana szerokość, NIE wymóg WT (patrz wt_validation.py)

MIN_FACADE_FRONTAGE_M = 3.6
"""Finch §B.2 (adaptowane, nie polskie WT) — min. długość elewacji frontowej
apartamentu, zapobiega bardzo wąskim mieszkaniom. Ostrzeżenie, nie błąd
twardy — to heurystyka jakościowa, nie przepis prawa budowlanego."""

MAX_APARTMENT_ASPECT_RATIO = 2.5
"""Finch §B.2 — max. stosunek głębokości do szerokości mieszkania.
Ostrzeżenie, ta sama logika co wyżej."""


@dataclass
class ApartmentValidationResult:
    apartment_id: str
    type: str
    passed: bool
    area_m2: float
    min_width_m: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class FullLayoutValidationResult:
    passed: bool
    score: int
    apartment_results: list[ApartmentValidationResult]
    wt_rules: list[WTRule]
    communication_all_connected: bool
    communication_issues: list[str]
    aggregated_errors: list[str]
    aggregated_warnings: list[str]


def _apartment_min_width(apt: ApartmentCell) -> float:
    """Approximate the narrower in-plan dimension of an (mostly rectangular) cell."""
    minx, miny, maxx, maxy = apt.polygon.bounds
    return min(maxx - minx, maxy - miny)


def _apartment_aspect_ratio(apt: ApartmentCell) -> float:
    minx, miny, maxx, maxy = apt.polygon.bounds
    w, h = maxx - minx, maxy - miny
    short, long_ = min(w, h), max(w, h)
    return long_ / short if short > 1e-9 else float("inf")


def validate_apartment(
    apt: ApartmentCell, min_area_m2: float | None
) -> ApartmentValidationResult:
    """Validate a single apartment cell against area (§94 ust. 1, real WT)
    and width (design heuristic, not WT -- see MIN_ROOM_WIDTH_M above)."""
    errors: list[str] = []
    warnings: list[str] = []

    area = apt.polygon.area
    width = _apartment_min_width(apt)

    if min_area_m2 is not None and min_area_m2 > 0:
        if area < min_area_m2:
            errors.append(
                f"{apt.id}: powierzchnia {area:.2f} m2 < wymagane {min_area_m2:.2f} m2 (WT §94 ust. 1)."
            )
        elif abs(area - min_area_m2) < min_area_m2 * 0.05:
            warnings.append(
                f"{apt.id}: powierzchnia {area:.2f} m2 blisko minimum ({min_area_m2:.2f} m2)."
            )

    if width < MIN_ROOM_WIDTH_M:
        errors.append(
            f"{apt.id}: szerokość {width:.2f} m < {MIN_ROOM_WIDTH_M} m (zalecana min. szerokość, nie WT)."
        )

    if width < MIN_FACADE_FRONTAGE_M:
        warnings.append(
            f"{apt.id}: szerokość frontu {width:.2f} m < zalecane {MIN_FACADE_FRONTAGE_M} m "
            f"(ryzyko zbyt wąskiego mieszkania, heurystyka nie-WT)."
        )

    ratio = _apartment_aspect_ratio(apt)
    if ratio > MAX_APARTMENT_ASPECT_RATIO:
        warnings.append(
            f"{apt.id}: stosunek głębokość:szerokość {ratio:.2f}:1 > zalecane "
            f"{MAX_APARTMENT_ASPECT_RATIO}:1 (heurystyka nie-WT)."
        )

    return ApartmentValidationResult(
        apartment_id=apt.id,
        type=apt.type,
        passed=not errors,
        area_m2=round(area, 2),
        min_width_m=round(width, 2),
        errors=errors,
        warnings=warnings,
    )


def validate_full_layout(
    layout: LayoutResult,
    spec_by_type: dict[str, float],
    local_law: str | None = None,
    max_corridor_distance_m: float | None = None,
) -> FullLayoutValidationResult:
    """Validate every dimension of a layout and aggregate one 0-100 score.

    `spec_by_type` maps apartment type -> minimum required area (m2), as
    supplied by the caller's program (see POST /api/v1/validate/full-layout).
    """
    apartment_results = [
        validate_apartment(apt, spec_by_type.get(apt.type))
        for apt in layout.apartments
    ]
    wt_result = validate_layout_wt(layout, local_law, max_corridor_distance_m)
    comm_result = validate_communication(
        layout,
        max_corridor_distance_m=max_corridor_distance_m or 30.0,
    )

    aggregated_errors = [e for r in apartment_results for e in r.errors]
    aggregated_errors.extend(r.detail for r in wt_result.rules if not r.passed)
    aggregated_errors.extend(
        f"{issue.apartment_id or 'układ'}: {issue.error}" for issue in comm_result.issues
    )
    aggregated_warnings = [w for r in apartment_results for w in r.warnings]

    passed_checks = sum(1 for r in apartment_results if r.passed)
    passed_checks += sum(1 for r in wt_result.rules if r.passed)
    passed_checks += 1 if comm_result.all_connected else 0
    total_checks = len(apartment_results) + len(wt_result.rules) + 1
    score = round((passed_checks / total_checks) * 100) if total_checks else 100

    all_apartments_passed = all(r.passed for r in apartment_results) if apartment_results else True

    return FullLayoutValidationResult(
        passed=all_apartments_passed and wt_result.passed and comm_result.all_connected,
        score=score,
        apartment_results=apartment_results,
        wt_rules=wt_result.rules,
        communication_all_connected=comm_result.all_connected,
        communication_issues=[
            f"{issue.apartment_id or 'układ'}: {issue.error}" for issue in comm_result.issues
        ],
        aggregated_errors=aggregated_errors,
        aggregated_warnings=aggregated_warnings,
    )
