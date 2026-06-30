"""Walidacja Warunków Technicznych (WT) dla wygenerowanego układu."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from services.layout import LayoutResult

# Domyślne wartości graniczne z WT (rozporządzenie)
DEFAULT_MIN_DAYLIGHT_HOURS = 3.0
DEFAULT_MAX_NOISE_DB = 50.0
DEFAULT_MIN_ROOM_AREA_M2 = 9.0
DEFAULT_MIN_KITCHEN_AREA_M2 = 4.5
DEFAULT_MIN_APARTMENT_AREA_M2 = 25.0


@dataclass
class WTValidationResult:
    passed: bool
    daylight_min_hours: float | None = None
    noise_max_db: float | None = None
    issues: list[str] = field(default_factory=list)


def validate_layout_wt(layout: LayoutResult, local_law: str | None = None) -> WTValidationResult:
    """Sprawdza podstawowe warunki techniczne dla układu."""
    issues: list[str] = []

    # Pobierz parametry z lokalnego prawa (placeholder)
    min_daylight = DEFAULT_MIN_DAYLIGHT_HOURS
    max_noise = DEFAULT_MAX_NOISE_DB
    min_apartment = DEFAULT_MIN_APARTMENT_AREA_M2

    if local_law and local_law.lower() == "warszawa":
        min_daylight = 2.5
        max_noise = 55.0

    # Sprawdzenie powierzchni mieszkań
    for apt in layout.apartments:
        if apt.polygon.area < min_apartment:
            issues.append(
                f"Mieszkanie {apt.id} ({apt.type}) ma powierzchnię "
                f"{apt.polygon.area:.2f} m2, min. wymagana {min_apartment} m2."
            )

    # Symulacja doświetlenia: uproszczony check w oparciu o wymiary
    daylight_ok, daylight_hours = _estimate_daylight(layout)
    if daylight_hours < min_daylight:
        issues.append(
            f"Szacowane minimalne doświetlenie {daylight_hours:.1f}h < {min_daylight:.1f}h."
        )

    # Symulacja hałasu: uproszczony check
    noise_ok, noise_db = _estimate_noise(layout)
    if noise_db > max_noise:
        issues.append(f"Szacowany poziom hałasu {noise_db:.1f} dB > {max_noise:.1f} dB.")

    # Sprawdzenie czy powierzchnia użytkowa nie przekracza 80% obrysu (dla korytarzy/klatki)
    if layout.footprint_area_m2 > 0:
        utilization = layout.usable_area_m2 / layout.footprint_area_m2
        if utilization > 0.92:
            issues.append(
                f"Współczynnik zagospodarowania {utilization:.2%} przekracza 92%."
            )

    passed = len(issues) == 0
    return WTValidationResult(
        passed=passed,
        daylight_min_hours=daylight_hours,
        noise_max_db=noise_db,
        issues=issues,
    )


def _estimate_daylight(layout: LayoutResult) -> tuple[bool, float]:
    """Uproszczona estymacja doświetlenia: najmniejsza szerokość mieszkania / 2 jako głębokość."""
    if not layout.apartments:
        return True, 999.0
    min_width = min(
        apt.polygon.bounds[2] - apt.polygon.bounds[0]
        for apt in layout.apartments
    )
    # Założenie: każda metra głębokości od okna to -0.5h doświetlenia, max 8h
    hours = max(0.0, 8.0 - (min_width / 2.0) * 0.5)
    return hours >= DEFAULT_MIN_DAYLIGHT_HOURS, hours


def _estimate_noise(layout: LayoutResult) -> tuple[bool, float]:
    """Uproszczona estymacja hałasu: im więcej mieszkań przy korytarzu, tym wyższy."""
    count = len(layout.apartments)
    if count == 0:
        return True, 0.0
    base = 30.0
    db = base + math.log1p(count) * 5.0
    return db <= DEFAULT_MAX_NOISE_DB, db
