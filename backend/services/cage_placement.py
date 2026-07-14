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
from services.optimize import evaluate_genome
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


def _candidate_cages(
    footprint: Polygon, zones: list[Zone], num_cages: int = 1
) -> list[tuple[int, Polygon]]:
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
        # Kotwice rozstawu (plan 2026-07-14 Etap 1): (i+0.5)/k długości strefy
        # wzdłuż dłuższej osi, przy obu krawędziach poprzecznych -- pozycje,
        # które wybrałby projektant przy k klatkach; RandomSearch/SA losują
        # wokół sensownych punktów zamiast czystego chaosu.
        if num_cages > 1:
            horizontal = (maxx - minx) >= (maxy - miny)
            for i_k in range(num_cages):
                t = (i_k + 0.5) / num_cages
                if horizontal:
                    anchors.append((minx + t * (maxx - minx), miny))
                    anchors.append((minx + t * (maxx - minx), maxy))
                else:
                    anchors.append((minx, miny + t * (maxy - miny)))
                    anchors.append((maxx, miny + t * (maxy - miny)))
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
    # Fix 2026-07-14: kara za NIEDOWIEZIENIE żądanej liczby klatek
    # (0 = umieszczono dokładnie num_cages), nie za "posiadanie klatek".
    count = abs(k - num_cages) / num_cages if num_cages > 0 else 0.0

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


class _CageGenerator:
    """Kernel generator (plan 2026-07-14 Etap 2, Task 5): genome = posortowana
    krotka indeksów DOKŁADNIE `num_cages` kandydatów wybranych z puli (albo
    mniej, gdy pula jest mniejsza niż num_cages). `build` umieszcza greedy w
    KOLEJNOŚCI GENOMU (rosnąco po indeksie) -- kandydaci kolidujący z już
    umieszczonymi albo łamiący `_cages_share_valid_corridor` są pomijani, więc
    genom "niewykonalny" (para kolidujących indeksów) po prostu umieszcza
    mniej klatek niż num_cages i score's `count` component to penalizuje
    (patrz Task 3). `build` zwraca `None` gdy żaden kandydat z genomu dał się
    umieścić -- ewaluator zamienia to na score=inf + naruszenie."""

    def __init__(
        self,
        footprint: Polygon,
        zones: list[Zone],
        candidates: list[tuple[int, Polygon]],
        num_cages: int,
        corridor_width_m: float,
        max_dist_single_m: float,
        max_dist_multi_m: float,
    ) -> None:
        self.footprint = footprint
        self.zones = zones
        self.candidates = candidates
        self.num_cages = num_cages
        self.corridor_width_m = corridor_width_m
        self.max_dist_single_m = max_dist_single_m
        self.max_dist_multi_m = max_dist_multi_m

    def random_genome(self, rng: random.Random) -> tuple[int, ...]:
        n = len(self.candidates)
        k = min(self.num_cages, n)
        return tuple(sorted(rng.sample(range(n), k))) if k > 0 else ()

    def mutate(self, genome: tuple[int, ...], rng: random.Random) -> tuple[int, ...]:
        n = len(self.candidates)
        chosen = set(genome)
        available = [i for i in range(n) if i not in chosen]
        if not genome or not available:
            return genome
        replaced = list(genome)
        pos = rng.randrange(len(replaced))
        replaced[pos] = rng.choice(available)
        return tuple(sorted(replaced))

    def build(self, genome: tuple[int, ...]) -> "CirculationResult | None":
        # zachłannie bierz niekolidujące W KOLEJNOŚCI GENOMU; wiele klatek na
        # strefę dozwolone, o ile jeden korytarz strefy może obsłużyć
        # wszystkie jej klatki (_cages_share_valid_corridor) -- (_assemble_
        # with_cages dostaje dict {indeks_strefy: [klatki]})
        local_cages: dict[int, list[Polygon]] = {}
        for idx in genome:
            zi, cage = self.candidates[idx]
            existing_all = [c for cages in local_cages.values() for c in cages]
            if any(cage.intersects(existing) for existing in existing_all):
                continue
            zone_existing = local_cages.get(zi)
            if zone_existing:
                candidate_list = zone_existing + [cage]
                if not _cages_share_valid_corridor(
                    self.zones[zi].polygon, self.corridor_width_m, candidate_list
                ):
                    continue
                local_cages[zi] = candidate_list
            else:
                local_cages[zi] = [cage]
        if not local_cages:
            return None
        return _assemble_with_cages(
            self.footprint, self.zones, local_cages, self.corridor_width_m,
            self.max_dist_single_m, self.max_dist_multi_m,
        )


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
    candidates = _candidate_cages(footprint, zones, num_cages)
    if not candidates:
        raise ValueError("Obrys zbyt mały na klatkę schodową")

    generator = _CageGenerator(
        footprint, zones, candidates, num_cages,
        corridor_width_m, max_dist_single_m, max_dist_multi_m,
    )

    def evaluator(genome: tuple[int, ...], payload: "CirculationResult | None") -> tuple[float, dict, list]:
        if payload is None:
            return float("inf"), {}, ["nie udało się umieścić klatek"]
        score, components = _score_placement(payload, footprint, num_cages, weights)
        return score, components, []

    # Plan 2026-07-14 Etap 2 Task 5: genome nie jest już seedem samym w sobie
    # (posortowana krotka indeksów kandydatów, patrz _CageGenerator) -- każda
    # iteracja losuje SWÓJ genom z random.Random(seed) i to `seed` (indeks
    # 0..iterations-1) zostaje jako stabilny identyfikator wiersza.
    evaluated = [
        evaluate_genome(generator, evaluator, generator.random_genome(random.Random(seed)))
        for seed in range(iterations)
    ]
    metas: list[CageIterationMeta] = [
        CageIterationMeta(
            seed=idx, score=c.score, cages_count=len(c.payload.cage_polygons),
            components=c.components, result=c.payload,
        )
        for idx, c in enumerate(evaluated)
        if c.payload is not None
    ]
    if not metas:
        raise ValueError("Obrys zbyt mały na klatkę schodową")
    best_idx = min(
        (idx for idx, c in enumerate(evaluated) if c.payload is not None),
        key=lambda idx: evaluated[idx].score,
    )
    best = evaluated[best_idx]
    return best.payload, metas, best_idx
