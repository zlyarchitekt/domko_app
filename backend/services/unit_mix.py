"""Etap 2 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
dopasowanie programu mieszkań do przestrzeni pozostałej po komunikacji.
Zastępuje services.layout._slice_apartments (sekwencyjne FIFO, trwałe
odrzucanie części — audyt 2026-07-02, znalezisko #6). Reużywa
services.layout._cut_cell (naprawiony 2026-07-02, bug depth/width) do
samego cięcia — zmienia się tylko WYBÓR, którą specyfikację i który
prostokąt ciąć, nie mechanika cięcia."""

from __future__ import annotations

import uuid

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

from services.bsp import rectangle_decompose
from services.layout import (
    MIN_CELL_DIMENSION_M,
    ApartmentCell,
    ApartmentSpec,
    _cut_cell,
    _polygon_parts,
)
from services.wall_geometry import net_polygon

AREA_TOLERANCE = 0.03
"""±3% (Finch §B.2, adaptowane) — patrz spec §5. Powyżej tej tolerancji
komórka jest wciąż tworzona (najlepsze dostępne dopasowanie), ale oznaczona
ApartmentCell.area_tolerance_exceeded=True zamiast cichego zaakceptowania
dowolnego odchylenia."""

_FEASIBILITY_EPS = 1e-6
"""Tolerancja zmiennoprzecinkowa przy porównywaniu cut_size z wymiarem
prostokąta wzdłuż osi cięcia — patrz komentarze w fit_program_to_rectangles."""


def fit_program_to_rectangles(
    rectangles: list[Polygon], specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Zachłanne dopasowanie: dla każdego prostokąta wybiera specyfikację
    programu dającą najmniejsze odchylenie procentowe od min_area_m2 —
    próbuje WSZYSTKIE pozostałe specyfikacje, nie tylko czoło kolejki FIFO
    jak dawne _slice_apartments (audyt 2026-07-02, znalezisko #6)."""
    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)

    if not queue or not rectangles:
        leftover_geoms = [r for r in rectangles if r.area > 1e-6]
        leftover = unary_union(leftover_geoms) if leftover_geoms else None
        return [], (
            leftover if leftover is not None and not leftover.is_empty and leftover.area > 1e-6 else None
        )

    cells: list[ApartmentCell] = []
    remaining_rects: list[Polygon] = list(rectangles)
    unused_specs: list[ApartmentSpec] = list(queue)
    leftover_parts: list[Polygon] = []
    idx = 0

    while remaining_rects:
        idx %= len(remaining_rects)
        rect = remaining_rects[idx]
        bounds = rect.bounds
        if len(bounds) != 4:
            leftover_parts.append(remaining_rects.pop(idx))
            continue
        minx, miny, maxx, maxy = bounds
        w, h = maxx - minx, maxy - miny
        horizontal = w >= h
        available_depth = h if horizontal else w
        # The dimension actually consumed by the cut (x for a horizontal
        # cut, y for a vertical one) — a spec whose required cut_size
        # exceeds this doesn't physically fit this rectangle at all, no
        # matter how well `cut_size * available_depth` matches the target
        # area algebraically (see feasibility check below).
        along_axis_extent = w if horizontal else h

        if available_depth < 1e-6 or not unused_specs:
            leftover_parts.append(remaining_rects.pop(idx))
            continue

        best_i: int | None = None
        best_deviation = float("inf")
        for i, spec in enumerate(unused_specs):
            fitted = spec.min_area_m2 / available_depth
            cut_size = max(fitted, MIN_CELL_DIMENSION_M)
            if cut_size > along_axis_extent + _FEASIBILITY_EPS:
                # Bug found while implementing this task: cut_size is
                # ALWAYS a near-perfect (deviation~0) match algebraically,
                # since cut_size = min_area_m2 / available_depth makes
                # cut_size * available_depth == min_area_m2 by construction
                # — regardless of whether that cut_size actually fits
                # inside the rectangle. Without this feasibility check, an
                # oversized spec (e.g. 80m^2 in a 30m^2 rectangle) would
                # "win" the best-match selection with deviation=0, then
                # silently fail in _cut_cell and retire the whole rectangle
                # as leftover instead of trying a smaller spec that fits.
                # Strictly-greater (not >=): cut_size == along_axis_extent
                # is a legitimate exact fit, handled below.
                continue
            projected_area = cut_size * available_depth
            deviation = abs(projected_area - spec.min_area_m2) / spec.min_area_m2
            if deviation < best_deviation:
                best_deviation = deviation
                best_i = i

        if best_i is None:
            # No remaining spec physically fits this rectangle.
            leftover_parts.append(remaining_rects.pop(idx))
            continue
        spec = unused_specs[best_i]
        fitted = spec.min_area_m2 / available_depth
        cut_size = max(fitted, MIN_CELL_DIMENSION_M)

        if cut_size >= along_axis_extent - _FEASIBILITY_EPS:
            # Exact (or near-exact) fit — the whole rectangle becomes the
            # cell, no split needed. _cut_cell's own strict `cut_x/cut_y >=
            # maxx/maxy` boundary check would otherwise reject this (the cut
            # line lands exactly on the rectangle's far edge, producing no
            # second fragment), silently discarding a perfectly valid
            # whole-rectangle cell — e.g. 3 apartments of 40m^2 exactly
            # filling a 120m^2 strip lost the 3rd apartment to "leftover"
            # before this fix.
            cell_poly, rest = rect, None
        else:
            cell_poly, rest = _cut_cell(rect, cut_size, horizontal)
        if cell_poly is None or cell_poly.area < 1e-6:
            leftover_parts.append(remaining_rects.pop(idx))
            continue

        cells.append(
            ApartmentCell(
                id=str(uuid.uuid4())[:8],
                type=spec.type,
                polygon=cell_poly,
                area_tolerance_exceeded=best_deviation > AREA_TOLERANCE,
                net_area_m2=net_polygon(cell_poly).area,
            )
        )
        unused_specs.pop(best_i)

        rest_parts = _polygon_parts(rest)
        if rest_parts:
            remaining_rects[idx] = rest_parts[0]
            remaining_rects.extend(rest_parts[1:])
            idx += 1
        else:
            remaining_rects.pop(idx)

    leftover_geoms = leftover_parts + [p for p in remaining_rects if p.area > 1e-6]
    leftover = unary_union(leftover_geoms) if leftover_geoms else None
    return cells, (
        leftover if leftover is not None and not leftover.is_empty and leftover.area > 1e-6 else None
    )


def subdivide_units(
    remainder: Polygon | MultiPolygon, specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Etap 2 pełny: dekompozycja `remainder` (może być wklęsła/wieloczęściowa)
    na prostokąty, potem dopasowanie programu."""
    rectangles = rectangle_decompose(remainder)
    return fit_program_to_rectangles(rectangles, specs)
