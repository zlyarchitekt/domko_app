"""Etap 2 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
dopasowanie programu mieszkań do przestrzeni pozostałej po komunikacji.
Zastępuje services.layout._slice_apartments (sekwencyjne FIFO, trwałe
odrzucanie części — audyt 2026-07-02, znalezisko #6). Reużywa
services.layout._cut_cell (naprawiony 2026-07-02, bug depth/width) do
samego cięcia — zmienia się tylko WYBÓR, którą specyfikację i który
prostokąt ciąć, nie mechanika cięcia."""

from __future__ import annotations

import math
import random
import uuid
from dataclasses import asdict, dataclass, field

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
    rectangles: list[Polygon], specs: list[ApartmentSpec], rng: random.Random | None = None
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Zachłanne dopasowanie: dla każdego prostokąta wybiera specyfikację
    programu dającą najmniejsze odchylenie procentowe od min_area_m2 —
    próbuje WSZYSTKIE pozostałe specyfikacje, nie tylko czoło kolejki FIFO
    jak dawne _slice_apartments (audyt 2026-07-02, znalezisko #6)."""
    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)

    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(rectangles := list(rectangles))

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


@dataclass
class ProgramShare:
    """Wiersz struktury % (spec §1): sztuki wynikają z powierzchni budynku,
    nie z pola usera."""

    type: str
    percentage: float
    area_min_m2: float
    area_max_m2: float
    min_facade_m: float = 3.0
    """Minimalny styk mieszkania tego typu ze ścianą zewnętrzną (spec §4,
    komponent daylight) -- per typ, pomysł usera ze screena Finch
    'Min facade length'."""


@dataclass
class UnitWeights:
    """7 wag scoringu (spec §4, mapowanie z Finch 'Unit weights')."""

    size: float = 0.8
    mix: float = 0.6
    grid: float = 0.3
    shape: float = 0.5
    daylight: float = 0.7
    squareness: float = 0.5
    adjacency: float = 1.0


@dataclass
class IterationMeta:
    seed: int
    score: float
    units_count: int
    components: dict = field(default_factory=dict)
    """dev per waga: {"size": ..., "mix": ..., ...} -- 0 = idealnie."""
    cells: list = field(default_factory=list)
    """list[ApartmentCell] -- pełne komórki TEJ iteracji (nie tylko
    najlepszej), spec 2026-07-05-circulation-iteration-selection-and-drag
    §1. Typ `list` bez parametru celowo -- ApartmentCell żyje w
    services.layout, import tu utworzyłby cykl (layout.py importuje z
    unit_mix.py)."""
    hard_valid: bool = True
    """False gdy iteracja łamie ZAKAZ (user 2026-07-11): każde mieszkanie
    musi dotykać komunikacji ORAZ elewacji. min_facade_m/wagi adjacency i
    daylight pozostają miękkim scoringiem -- zakaz sprawdza sam styk (>0)."""


def derive_total_units(net_remainder_m2: float, shares: list[ProgramShare]) -> int:
    total_pct = sum(s.percentage for s in shares)
    if total_pct <= 0:
        raise ValueError("Struktura mieszkań: wszystkie udziały procentowe są zerowe")
    avg = sum((s.percentage / total_pct) * (s.area_min_m2 + s.area_max_m2) / 2.0 for s in shares)
    if avg <= 0:
        raise ValueError("Struktura mieszkań: nieprawidłowe przedziały wielkości")
    return max(1, math.floor(net_remainder_m2 / avg))


def allocate_counts(shares: list[ProgramShare], total_units: int) -> dict[str, int]:
    total_pct = sum(s.percentage for s in shares)
    if total_pct <= 0:
        raise ValueError("Struktura mieszkań: wszystkie udziały procentowe są zerowe")
    raw = [(s, total_units * s.percentage / total_pct) for s in shares]
    counts = {s.type: math.floor(r) for s, r in raw}
    deficit = total_units - sum(counts.values())
    by_frac = sorted(raw, key=lambda sr: sr[1] - math.floor(sr[1]), reverse=True)
    for s, _ in by_frac[:deficit]:
        counts[s.type] += 1
    return counts


_GRID_M = 0.5
_DAYLIGHT_MIN_CONTACT_M = 3.0
_SQUARENESS_CAP_RATIO = 2.5


def _cell_geometry_devs(cell: ApartmentCell) -> tuple[float, float, float]:
    """(grid, shape, squareness) dla jednej komórki."""
    polys = list(cell.polygon.geoms) if hasattr(cell.polygon, "geoms") else [cell.polygon]
    coords = [pt for p in polys for pt in p.exterior.coords[:-1]]
    off = sum(
        1
        for x, y in coords
        if abs(x - round(x / _GRID_M) * _GRID_M) > 1e-6 or abs(y - round(y / _GRID_M) * _GRID_M) > 1e-6
    )
    grid = off / len(coords) if coords else 0.0

    mrr = cell.polygon.minimum_rotated_rectangle
    shape = max(0.0, 1.0 - cell.polygon.area / mrr.area) if mrr.area > 1e-9 else 0.0

    xs = [pt[0] for pt in mrr.exterior.coords[:-1]]
    ys = [pt[1] for pt in mrr.exterior.coords[:-1]]
    side_a = math.hypot(xs[1] - xs[0], ys[1] - ys[0])
    side_b = math.hypot(xs[2] - xs[1], ys[2] - ys[1])
    longer, shorter = max(side_a, side_b), min(side_a, side_b)
    ratio = longer / shorter if shorter > 1e-9 else _SQUARENESS_CAP_RATIO
    squareness = min(1.0, max(0.0, (ratio - 1.0) / (_SQUARENESS_CAP_RATIO - 1.0)))
    return grid, shape, squareness


def _merge_leftover_into_cells(cells: list[ApartmentCell], leftover) -> None:
    """Zero resztek: część leftover -> mieszkanie o najdłuższej wspólnej
    krawędzi; bez sąsiada -> najbliższe mieszkanie + merged_disjoint.
    Mutuje cells in-place."""
    if leftover is None or leftover.is_empty or not cells:
        return
    parts = list(leftover.geoms) if hasattr(leftover, "geoms") else [leftover]
    for part in parts:
        if part.is_empty or part.area < 1e-9:
            continue
        best_i, best_shared = -1, 0.0
        for i, cell in enumerate(cells):
            shared = cell.polygon.boundary.intersection(part.boundary).length
            if shared > best_shared:
                best_i, best_shared = i, shared
        if best_i >= 0 and best_shared > 1e-6:
            cells[best_i].polygon = unary_union([cells[best_i].polygon, part])
        else:
            nearest = min(range(len(cells)), key=lambda i: cells[i].polygon.distance(part))
            cells[nearest].polygon = unary_union([cells[nearest].polygon, part])
            cells[nearest].merged_disjoint = True
    for cell in cells:
        cell.net_area_m2 = net_polygon(cell.polygon).area


def _score_iteration(
    cells: list[ApartmentCell],
    shares: list[ProgramShare],
    weights: UnitWeights,
    footprint: Polygon | None,
    circulation_geometry,
) -> tuple[float, dict]:
    """(score, components) -- spec §4. daylight bez footprint i adjacency
    bez circulation_geometry są pomijane (wypadają z sumy wag)."""
    n = len(cells) or 1
    total_pct = sum(s.percentage for s in shares) or 1.0

    mix = sum(
        abs(s.percentage / total_pct - sum(1 for c in cells if c.type == s.type) / n)
        for s in shares
    )

    bounds = {s.type: (s.area_min_m2, s.area_max_m2) for s in shares}
    size_devs = []
    for c in cells:
        lo, hi = bounds.get(c.type, (0.0, float("inf")))
        area = c.polygon.area
        if lo > 0 and area < lo:
            size_devs.append((lo - area) / lo)
        elif hi > 0 and area > hi:
            size_devs.append((area - hi) / hi)
        else:
            size_devs.append(0.0)
    size = sum(size_devs) / n

    geo = [_cell_geometry_devs(c) for c in cells]
    grid = sum(g[0] for g in geo) / n
    shape = sum(g[1] for g in geo) / n
    squareness = sum(g[2] for g in geo) / n

    components = {"size": size, "mix": mix, "grid": grid, "shape": shape, "squareness": squareness}
    active = {
        "size": weights.size, "mix": weights.mix, "grid": weights.grid,
        "shape": weights.shape, "squareness": weights.squareness,
    }

    if footprint is not None:
        edge = footprint.exterior.buffer(0.01)
        facade_min = {s.type: s.min_facade_m for s in shares}
        short_contact = sum(
            1
            for c in cells
            if c.polygon.boundary.intersection(edge).length
            < facade_min.get(c.type, _DAYLIGHT_MIN_CONTACT_M)
        )
        components["daylight"] = short_contact / n
        active["daylight"] = weights.daylight

    if circulation_geometry is not None and not circulation_geometry.is_empty:
        adj_devs = []
        for c in cells:
            base = 0.0 if c.polygon.distance(circulation_geometry) < 0.01 else 1.0
            if c.merged_disjoint:
                base += 0.5
            adj_devs.append(base)
        components["adjacency"] = sum(adj_devs) / n
        active["adjacency"] = weights.adjacency

    total_w = sum(active.values())
    if total_w <= 0:
        return 0.0, components
    score = sum(active[k] * components[k] for k in active) / total_w
    return score, components


def meets_hard_constraints(
    cells: list, footprint: Polygon | None, circulation_geometry
) -> bool:
    """ZAKAZ (user 2026-07-11): każde mieszkanie musi mieć styk (>0) z
    komunikacją ORAZ z elewacją (ścianą zewnętrzną obrysu). Warunek liczony
    tylko względem geometrii, którą podano -- bez footprint nie da się
    sprawdzić elewacji, bez circulation_geometry komunikacji (wtedy dany
    warunek jest pomijany, jak w _score_iteration)."""
    edge = footprint.exterior.buffer(0.01) if footprint is not None else None
    check_circ = circulation_geometry is not None and not circulation_geometry.is_empty
    for c in cells:
        if check_circ and c.polygon.distance(circulation_geometry) >= 0.01:
            return False
        if edge is not None and c.polygon.boundary.intersection(edge).length <= 0:
            return False
    return True


def pick_best_iteration(metas: list[IterationMeta]) -> IterationMeta:
    """Zwycięzca = najniższy score wśród iteracji spełniających zakaz
    (hard_valid); gdy żadna nie spełnia -- najniższy score w ogóle (frontend
    pokazuje wtedy ostrzeżenie zamiast pustego wyniku)."""
    valid = [m for m in metas if m.hard_valid]
    pool = valid or metas
    return min(pool, key=lambda m: m.score)


def iterate_units(
    remainder: Polygon | MultiPolygon,
    shares: list[ProgramShare],
    iterations: int = 10,
    weights: UnitWeights | None = None,
    footprint: Polygon | None = None,
    circulation_geometry=None,
) -> tuple[list[ApartmentCell], list[IterationMeta], int, int]:
    """Iteracyjny podział (spec §2): seeded przebiegi, zero-leftover merge,
    scoring 7-wagowy, wygrywa najniższy score."""
    weights = weights or UnitWeights()
    if hasattr(remainder, "geoms"):
        net_area = sum(net_polygon(p).area for p in remainder.geoms)
    else:
        net_area = net_polygon(remainder).area
    total_units = derive_total_units(net_area, shares)
    counts = allocate_counts(shares, total_units)
    specs = [
        ApartmentSpec(
            type=s.type,
            min_area_m2=(s.area_min_m2 + s.area_max_m2) / 2.0,
            target_count=counts[s.type],
        )
        for s in shares
        if counts[s.type] > 0
    ]

    rectangles = rectangle_decompose(remainder)
    metas: list[IterationMeta] = []
    for seed in range(iterations):
        rng = random.Random(seed)
        cells, leftover = fit_program_to_rectangles(list(rectangles), specs, rng=rng)
        _merge_leftover_into_cells(cells, leftover)
        if not cells:
            import uuid as _uuid
            from services.layout import ApartmentCell as _Cell

            whole = remainder if remainder.geom_type == "Polygon" else unary_union(remainder)
            cells = [_Cell(id=str(_uuid.uuid4()), type=shares[0].type, polygon=whole)]
            cells[0].net_area_m2 = net_area
        score, components = _score_iteration(cells, shares, weights, footprint, circulation_geometry)
        metas.append(IterationMeta(seed=seed, score=score, units_count=len(cells),
                                   components=components, cells=list(cells),
                                   hard_valid=meets_hard_constraints(cells, footprint, circulation_geometry)))
    winner = pick_best_iteration(metas)
    return winner.cells, metas, winner.seed, total_units


def subdivide_units(
    remainder: Polygon | MultiPolygon, specs: list[ApartmentSpec]
) -> tuple[list[ApartmentCell], Polygon | None]:
    """Etap 2 pełny: dekompozycja `remainder` (może być wklęsła/wieloczęściowa)
    na prostokąty, potem dopasowanie programu."""
    rectangles = rectangle_decompose(remainder)
    return fit_program_to_rectangles(rectangles, specs)
