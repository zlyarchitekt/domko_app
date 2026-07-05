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
                if fp.contains(cage):
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
        # zachłannie bierz niekolidujące, max 1 klatka na strefę
        # (_assemble_with_cages dostaje dict {indeks_strefy: klatka})
        local_cages: dict[int, Polygon] = {}
        for zi, cage in pool:
            if len(local_cages) >= k:
                break
            if zi in local_cages:
                continue
            if any(cage.intersects(existing) for existing in local_cages.values()):
                continue
            local_cages[zi] = cage
        if not local_cages:
            continue
        result = _assemble_with_cages(
            footprint, zones, local_cages, corridor_width_m,
            max_dist_single_m, max_dist_multi_m,
        )
        score, components = _score_placement(result, footprint, num_cages, weights)
        metas.append(CageIterationMeta(seed=seed, score=score,
                                       cages_count=len(result.cage_polygons),
                                       components=components))
        if best is None or score < best[0]:
            best = (score, result)
    if best is None:
        raise ValueError("Obrys zbyt mały na klatkę schodową")
    best_seed = min(metas, key=lambda m: m.score).seed
    return best[1], metas, best_seed
