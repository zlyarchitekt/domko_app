"""Iteracyjny auto-placement klatek schodowych (spec 2026-07-04-cage-
placement-iterations). 10 seeded iteracji, scoring 5 wagami, wygrywa
najniższy score. Czyste funkcje + reużycie _assemble_with_cages."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from services.bsp import rectangle_decompose
from services.circulation import (
    CAGE_DEPTH_M,
    CAGE_WIDTH_M,
    CirculationResult,
    Zone,
    _assemble_with_cages,
    _build_corridor,
)

CANDIDATE_EDGE_STEP_M = 5.0


@dataclass
class CageWeights:
    """5 wag scoringu lokalizacji klatek (spec §2, mapowanie z Finch)."""

    egress: float = 1.0
    count: float = 0.5
    corners: float = 0.3
    ends: float = 0.3
    spread: float = 0.5


@dataclass
class CageIterationMeta:
    seed: int
    score: float
    cages_count: int
    components: dict = field(default_factory=dict)
    result: "CirculationResult | None" = None
    """Pełny wynik TEJ iteracji (klatki, korytarz, centerline, kropki) —
    spec 2026-07-05-circulation-iteration-selection-and-drag §1. None
    tylko jeśli ktoś konstruuje CageIterationMeta ręcznie bez wyniku
    (nie zdarza się w iterate_cage_placement)."""


def _candidate_cages(footprint: Polygon, zones: list[Zone]) -> list[tuple[int, Polygon]]:
    """Pula kandydatów: (indeks_strefy, prostokąt klatki). Kotwice: narożniki
    bbox strefy, środki krawędzi bbox; obie orientacje klatki; tylko
    kandydaci w całości wewnątrz obrysu (spec §3.1)."""
    fp = footprint.buffer(1e-9)
    candidates: list[tuple[int, Polygon]] = []
    for zi, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        minx, miny, maxx, maxy = zone.polygon.bounds
        anchors = [
            (minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy),
            ((minx + maxx) / 2, miny), ((minx + maxx) / 2, maxy),
            (minx, (miny + maxy) / 2), (maxx, (miny + maxy) / 2),
        ]
        # dodatkowe kotwice co ~5m wzdłuż dolnej/górnej krawędzi strefy
        x = minx + CANDIDATE_EDGE_STEP_M
        while x < maxx - 1e-6:
            anchors.append((x, miny))
            anchors.append((x, maxy))
            x += CANDIDATE_EDGE_STEP_M
        for ax, ay in anchors:
            for w, d in ((CAGE_WIDTH_M, CAGE_DEPTH_M), (CAGE_DEPTH_M, CAGE_WIDTH_M)):
                # prostokąt dosunięty do kotwicy w stronę wnętrza bbox strefy
                x0 = ax if ax + w <= maxx + 1e-6 else ax - w
                y0 = ay if ay + d <= maxy + 1e-6 else ay - d
                cage = box(x0, y0, x0 + w, y0 + d)
                if zone.polygon.buffer(1e-9).contains(cage) and fp.contains(cage):
                    candidates.append((zi, cage))
    # deduplikacja po zaokrąglonych bounds
    seen: set = set()
    unique: list[tuple[int, Polygon]] = []
    for zi, cage in candidates:
        key = tuple(round(v, 3) for v in cage.bounds)
        if key not in seen:
            seen.add(key)
            unique.append((zi, cage))
    return unique


def assign_cages_to_zones(cages: list[Polygon], zones: list[Zone]) -> dict[int, list[Polygon]]:
    """Przypisuje każdą klatkę do strefy, której bbox ją zawiera (spec
    2026-07-05-circulation-iteration-selection-and-drag §2 -- przesunięta
    klatka musi trafić do właściwej strefy przed przeliczeniem korytarza).
    Klatka niepasująca w całości do żadnej pojedynczej strefy (np.
    przeciągnięta poza obrys, ALBO leżąca w całości wewnątrz obrysu, ale
    okraczająca szew między dwiema strefami wklęsłego footprintu po
    `rectangle_decompose`) jest tu pomijana -- wywołujący (endpoint) MUSI
    sprawdzić, że `sum(len(v) for v in result.values()) == len(cages)`,
    inaczej klatka po cichu znika z wyniku (patrz reviewer finding
    2026-07-06: cage-straddles-zone-boundary)."""
    result: dict[int, list[Polygon]] = {}
    for cage in cages:
        for zi, zone in enumerate(zones):
            if zone.polygon.buffer(1e-6).contains(cage):
                result.setdefault(zi, []).append(cage)
                break
    return result


def _score_placement(
    result: CirculationResult, footprint: Polygon, num_cages: int, weights: CageWeights
) -> tuple[float, dict]:
    cages = result.cage_polygons
    k = len(cages)
    dots = result.evacuation_dots
    egress = (sum(1 for d in dots if d.status == "red") / len(dots)) if dots else 1.0
    count = k / num_cages if num_cages > 0 else 0.0

    minx, miny, maxx, maxy = footprint.bounds
    diag_half = math.hypot(maxx - minx, maxy - miny) / 2.0 or 1.0
    corner_pts = list(footprint.exterior.coords[:-1])
    corners_devs = []
    for c in cages:
        cx, cy = c.centroid.x, c.centroid.y
        d = min(math.hypot(cx - px, cy - py) for px, py in corner_pts)
        corners_devs.append(min(1.0, d / diag_half))
    corners = sum(corners_devs) / k if k else 1.0

    horizontal = (maxx - minx) >= (maxy - miny)
    axis_len = (maxx - minx) if horizontal else (maxy - miny)
    axis_len = axis_len or 1.0
    ts = sorted(
        ((c.centroid.x - minx) / axis_len if horizontal else (c.centroid.y - miny) / axis_len)
        for c in cages
    )
    ends = sum(min(t, 1.0 - t) * 2.0 for t in ts) / k if k else 1.0

    if k <= 1:
        spread = 0.0  # spec §2: 0 dla 1 klatki
    else:
        ideal = [(i + 0.5) / k for i in range(k)]
        spread = min(1.0, sum(abs(t - i) for t, i in zip(ts, ideal)) / k * 2.0)

    components = {"egress": egress, "count": count, "corners": corners, "ends": ends, "spread": spread}
    active = {"egress": weights.egress, "count": weights.count, "corners": weights.corners,
              "ends": weights.ends, "spread": weights.spread}
    total_w = sum(active.values())
    if total_w <= 0:
        return 0.0, components
    return sum(active[key] * components[key] for key in active) / total_w, components


def _cages_share_valid_corridor(
    zone_polygon: Polygon, corridor_width_m: float, cages: list[Polygon]
) -> bool:
    """True gdy zadana lista klatek w jednej strefie może być obsłużona przez
    JEDEN korytarz strefy (wyrównany do ich zunifikowanego centroidu) — tzn.
    korytarz faktycznie styka się z KAŻDĄ z klatek, nie tylko z niektórymi."""
    if len(cages) <= 1:
        return True
    cages_union = unary_union(cages)
    zone_remaining = zone_polygon.difference(cages_union)
    corridor = _build_corridor(zone_remaining, corridor_width_m, cages_union)
    if corridor.is_empty or corridor.area <= 0:
        return False
    return all(corridor.distance(c) < 1e-6 for c in cages)


def iterate_cage_placement(
    footprint: Polygon,
    corridor_width_m: float,
    num_cages: int,
    weights: CageWeights,
    iterations: int = 10,
    max_dist_single_m: float = 20.0,
    max_dist_multi_m: float = 40.0,
) -> tuple[CirculationResult, list[CageIterationMeta], int]:
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    candidates = _candidate_cages(footprint, zones)
    if not candidates:
        raise ValueError("Obrys zbyt mały na klatkę schodową")

    best: tuple[float, CirculationResult] | None = None
    metas: list[CageIterationMeta] = []
    for seed in range(iterations):
        rng = random.Random(seed)
        k = rng.randint(1, max(1, num_cages))
        pool = list(candidates)
        rng.shuffle(pool)
        # zachłannie bierz niekolidujące; wiele klatek na strefę dozwolone,
        # o ile jeden korytarz strefy może obsłużyć wszystkie jej klatki
        # (_cages_share_valid_corridor) -- (_assemble_with_cages dostaje dict
        # {indeks_strefy: [klatki]})
        local_cages: dict[int, list[Polygon]] = {}
        placed_count = 0
        for zi, cage in pool:
            if placed_count >= k:
                break
            existing_all = [c for cages in local_cages.values() for c in cages]
            if any(cage.intersects(existing) for existing in existing_all):
                continue
            zone_existing = local_cages.get(zi)
            if zone_existing:
                candidate_list = zone_existing + [cage]
                if not _cages_share_valid_corridor(zones[zi].polygon, corridor_width_m, candidate_list):
                    continue
                local_cages[zi] = candidate_list
            else:
                local_cages[zi] = [cage]
            placed_count += 1
        if not local_cages:
            continue
        result = _assemble_with_cages(
            footprint, zones, local_cages, corridor_width_m,
            max_dist_single_m, max_dist_multi_m,
        )
        score, components = _score_placement(result, footprint, num_cages, weights)
        metas.append(CageIterationMeta(seed=seed, score=score,
                                       cages_count=len(result.cage_polygons),
                                       components=components, result=result))
        if best is None or score < best[0]:
            best = (score, result)
    if best is None:
        raise ValueError("Obrys zbyt mały na klatkę schodową")
    best_seed = min(metas, key=lambda m: m.score).seed
    return best[1], metas, best_seed
