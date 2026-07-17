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

COMM_SHARE_WEIGHT = 2.0
"""Waga udziału komunikacji w composite auto-decyzji (plan 2026-07-16).
Referencje (docs/references/typologia-klatkowa.md §1): klatkowiec 9-13%
powierzchni vs korytarzowiec więcej. To rachunek, nie reguła: gruby trakt
albo długie skrzydło i tak wygra korytarzem przez jakość mieszkań."""

_DEFAULT_PROBE_SHARES = None  # leniwe -- ProgramShare importowany w funkcji


def _probe_shares():
    global _DEFAULT_PROBE_SHARES
    if _DEFAULT_PROBE_SHARES is None:
        from services.unit_mix import ProgramShare
        _DEFAULT_PROBE_SHARES = [
            ProgramShare(type="M1", percentage=10, area_min_m2=25, area_max_m2=32),
            ProgramShare(type="M2", percentage=40, area_min_m2=38, area_max_m2=48),
            ProgramShare(type="M3", percentage=40, area_min_m2=58, area_max_m2=70),
            ProgramShare(type="M4", percentage=10, area_min_m2=72, area_max_m2=90),
        ]
    return _DEFAULT_PROBE_SHARES


def decide_access_modes(footprint, shares, corridor_width_m, num_cages,
                        weights, iterations, strategy="anneal", base_seed=0):
    """Porównaj warianty korytarzowy i punktowy pełnym (budżetowanym)
    przebiegiem silnika mieszkań; zwróć wynik lepszego. MVP: decyzja
    całobudynkowa (wszystkie strefy ten sam tryb); per-strefa mieszanie --
    następny krok po MVP (patrz plan, sekcja Deferred)."""
    from services.unit_mix import iterate_units

    shares = shares or _probe_shares()
    probe_budget = max(6, iterations // 2)
    candidates = []
    for mode in ("double", "point"):
        try:
            if mode == "point":
                # gałąź "point" jest deterministyczną enumeracją kotwic --
                # strategy/base_seed nie mają tam żadnego znaczenia (kontroler
                # Task 6 decyzja 5), więc ich nie przekazujemy.
                circ, metas, best = iterate_cage_placement(
                    footprint, corridor_width_m, num_cages, weights,
                    iterations=iterations, corridor_mode=mode,
                )
            else:
                circ, metas, best = iterate_cage_placement(
                    footprint, corridor_width_m, num_cages, weights,
                    iterations=iterations, strategy=strategy,
                    corridor_mode=mode, base_seed=base_seed,
                )
        except ValueError:
            continue  # np. strefa za mała na trzon
        point_cores = [circ.circulation_geometry] if mode == "point" else None
        _cells, umetas, _s, _t = iterate_units(
            circ.remainder, shares, iterations=probe_budget,
            footprint=footprint, circulation_geometry=circ.circulation_geometry,
            strategy=strategy, spine_segments=circ.spine_segments,
            base_seed=base_seed, point_cores=point_cores,
        )
        comm_share = circ.circulation_geometry.area / footprint.area
        composite = umetas[0].score + COMM_SHARE_WEIGHT * comm_share
        # tryb łamiący zakazy twarde przegrywa z czystym niezależnie od score
        rank = (0 if umetas[0].hard_valid else 1, composite)
        label = "corridor" if mode == "double" else "point"
        candidates.append((rank, label, circ, metas, best))
    if not candidates:
        raise ValueError("Auto: żaden tryb komunikacji nie da się zbudować")
    candidates.sort(key=lambda c: c[0])
    _rank, label, circ, metas, best = candidates[0]
    if not circ.zone_access_modes:
        circ.zone_access_modes = [label] * len(circ.zones)
    return circ, metas, best


@dataclass
class CageWeights:
    """5 wag scoringu lokalizacji klatek. `light_waste` (user 2026-07-15)
    zastąpił dawne `corners`: kara za marnowanie doświetlanej elewacji przez
    klatkę zamiast nagrody za dowolny narożnik."""

    egress: float = 1.0
    count: float = 0.5
    light_waste: float = 0.5
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
    footprint: Polygon, zones: list[Zone], num_cages: int = 1,
    spine_segments: list | None = None, corridor_half_m: float = 0.0,
) -> list[tuple[int, Polygon]]:
    """Pula kandydatów: (indeks_strefy, prostokąt klatki). Kotwice: narożniki
    bbox strefy, środki krawędzi bbox; obie orientacje klatki; oraz (plan
    2026-07-15 Task 10) kotwice PRZY SPINE -- klatka dosunięta do boku
    korytarza, żeby mogła stanąć wewnątrz budynku (nie tylko przy elewacji).
    Tylko kandydaci w całości wewnątrz obrysu (spec §3.1)."""
    fp = footprint.buffer(1e-9)
    candidates: list[tuple[int, Polygon]] = []

    def _add_cage(cage: Polygon) -> None:
        if not fp.contains(cage):
            return
        for zi2, z2 in enumerate(zones):
            if z2.polygon.buffer(1e-9).contains(cage):
                candidates.append((zi2, cage))
                return

    # Kotwice przy spine: co CANDIDATE_EDGE_STEP_M wzdłuż osi, klatka dosunięta
    # do KAŻDEGO boku korytarza (obie orientacje) -- klatka wewnętrzna przy
    # korytarzu, nie tylko na krawędziach stref (przyczyna "klatki zawsze
    # przy elewacji").
    if spine_segments:
        for (p1, p2) in spine_segments:
            seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if seg_len < 1e-6:
                continue
            horizontal = abs(p2[1] - p1[1]) <= abs(p2[0] - p1[0])
            axis = p1[1] if horizontal else p1[0]
            s = 0.0
            while s <= seg_len + 1e-9:
                t = s / seg_len
                sx = p1[0] + (p2[0] - p1[0]) * t
                sy = p1[1] + (p2[1] - p1[1]) * t
                for w, d in ((CAGE_WIDTH_M, CAGE_DEPTH_M), (CAGE_DEPTH_M, CAGE_WIDTH_M)):
                    if horizontal:
                        for sign in (1, -1):
                            y0 = axis + corridor_half_m if sign > 0 else axis - corridor_half_m - d
                            _add_cage(box(sx - w / 2, y0, sx + w / 2, y0 + d))
                    else:
                        for sign in (1, -1):
                            x0 = axis + corridor_half_m if sign > 0 else axis - corridor_half_m - w
                            _add_cage(box(x0, sy - d / 2, x0 + w, sy + d / 2))
                s += CANDIDATE_EDGE_STEP_M

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


def _arc_positions(points, spine_segments):
    """Pozycje punktów [0..1] wzdłuż łuku łamanej spine: rzut punktu na
    najbliższy segment + skumulowana długość poprzednich segmentów (plan
    2026-07-15 Task 6). Na L dwie klatki na końcach ramion są rozstawione
    wzdłuż KORYTARZA, nie rzutowane na jedną oś bbox."""
    from shapely.geometry import LineString, Point

    lines = [LineString([p1, p2]) for p1, p2 in spine_segments]
    lengths = [ln.length for ln in lines]
    total = sum(lengths) or 1.0
    prefix = [0.0]
    for ln_len in lengths[:-1]:
        prefix.append(prefix[-1] + ln_len)
    out = []
    for pt in points:
        p = Point(pt)
        i = min(range(len(lines)), key=lambda k: lines[k].distance(p))
        out.append((prefix[i] + lines[i].project(p)) / total)
    return out


def _light_waste_for_cage(cage: Polygon, footprint: Polygon) -> float:
    """Udział obwodu klatki sklejonego z elewacją NIE-północną (user
    2026-07-15: klatka ma nie marnować doświetlanej elewacji; północ i
    wnętrze/narożnik wewnętrzny są darmowe). Krawędź elewacji jest
    'północna', gdy jej zewnętrzna normalna ma składową +y > |składowej x|
    (konwencja solar.py: azymut 0 = N = +y)."""
    from shapely.geometry import LineString

    edge = footprint.exterior.buffer(0.01)
    contact = cage.boundary.intersection(edge)
    if contact.is_empty or contact.length <= 1e-9:
        return 0.0
    non_north = 0.0
    coords = list(footprint.exterior.coords)
    # CCW ring: zewnętrzna normalna krawędzi (dx,dy) to (dy,-dx)
    if not footprint.exterior.is_ccw:
        coords = coords[::-1]
    for a, b in zip(coords[:-1], coords[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        nx, ny = dy, -dx
        seg_contact = cage.boundary.intersection(LineString([a, b]).buffer(0.02))
        if seg_contact.is_empty:
            continue
        is_north = ny > abs(nx)
        if not is_north:
            non_north += seg_contact.length
    return min(1.0, non_north / max(contact.length, 1e-9))


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
    # light_waste: kara za sklejenie klatki z doświetlaną (nie-północną)
    # elewacją (user 2026-07-15); klatka wewnętrzna/przy północy = 0.
    light_waste = sum(_light_waste_for_cage(c, footprint) for c in cages) / k if k else 1.0

    # Pozycje klatek [0..1] wzdłuż komunikacji: wzdłuż ŁUKU spine (plan
    # 2026-07-15 Task 6) gdy dostępny, inaczej stary rzut na dłuższą oś bbox.
    spine = getattr(result, "spine_segments", None) or []
    if spine:
        ts = sorted(_arc_positions([(c.centroid.x, c.centroid.y) for c in cages], spine))
    else:
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

    components = {"egress": egress, "count": count, "light_waste": light_waste, "ends": ends, "spread": spread}
    active = {"egress": weights.egress, "count": weights.count, "light_waste": weights.light_waste,
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
        prefer_flush: bool = False,
    ) -> None:
        self.footprint = footprint
        self.zones = zones
        self.candidates = candidates
        self.num_cages = num_cages
        self.corridor_width_m = corridor_width_m
        self.max_dist_single_m = max_dist_single_m
        self.max_dist_multi_m = max_dist_multi_m
        self.prefer_flush = prefer_flush

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
            prefer_flush=self.prefer_flush,
        )


def _run_cage_hybrid(generator, evaluator, iterations: int, strategy: str, base_seed: int = 0) -> list:
    """Jeden przebieg hybrydy random+SA (plan 2026-07-14 Task 7), wydzielony
    żeby minimal-k (Task 10) mógł go uruchomić per k. `base_seed` (user
    2026-07-16): przesuwa wszystkie seedy -- inna baza = inna eksploracja,
    ta sama = wynik odtwarzalny."""
    from services.optimize import Budget, dedupe_and_rank, run_simulated_annealing

    n_seed = max(5, iterations // 3) if iterations >= 2 else iterations
    n_seed = min(n_seed, iterations)
    random_phase = [
        evaluate_genome(generator, evaluator, generator.random_genome(random.Random(base_seed + seed)))
        for seed in range(n_seed)
    ]
    if strategy == "random":
        n_seed = iterations
        random_phase += [
            evaluate_genome(generator, evaluator, generator.random_genome(random.Random(base_seed + seed)))
            for seed in range(len(random_phase), iterations)
        ]
    sa_budget = iterations - n_seed
    history = list(random_phase)
    if sa_budget > 0:
        starts = dedupe_and_rank([c for c in random_phase if c.payload is not None], limit=3)
        history += run_simulated_annealing(
            generator, evaluator, Budget(evaluations=sa_budget),
            seed_candidates=starts, restarts=min(3, len(starts)) or 1,
            rng_offset=base_seed,
        )
    return history


def _red_share(candidate) -> float:
    dots = candidate.payload.evacuation_dots
    return (sum(1 for d in dots if d.status == "red") / len(dots)) if dots else 1.0


def _place_point_variant(footprint: Polygon, corridor_width_m: float, anchor: str) -> "CirculationResult | None":
    """CirculationResult trybu punktowego z WYMUSZONĄ kotwicą anchor w KAŻDEJ
    strefie (zamiast najlepszej z anchor_candidates per strefa). Brak
    fallbacku: gdy anchor nie mieści się w którejś strefie, wywołujący ma
    pominąć ten wariant (kontroler Task 5, decyzja 4)."""
    from services.point_access import build_point_core, core_polygon

    zones = [Zone(name=f"P{i}", polygon=z) for i, z in enumerate(rectangle_decompose(footprint))]
    cages, cores = [], []
    for z in zones:
        built = build_point_core(z.polygon, anchor)
        if built is None:
            return None
        cage, hall = built
        cages.append(cage)
        cores.append(core_polygon(cage, hall))
    circulation = unary_union(cores)
    return CirculationResult(
        zones=zones, circulation_geometry=circulation, cage_polygons=cages,
        remainder=footprint.difference(circulation), centerline=[],
        evacuation_dots=[], spine_segments=[],
        zone_access_modes=["point"] * len(zones),
    )


def _meta_from_result(result: CirculationResult, score: float, components: dict | None = None) -> CageIterationMeta:
    return CageIterationMeta(
        seed=0, score=score, cages_count=len(result.cage_polygons),
        components=components if components is not None else {"light_waste": round(score, 4)},
        result=result,
    )


def iterate_cage_placement(
    footprint: Polygon,
    corridor_width_m: float,
    num_cages: int,
    weights: CageWeights,
    iterations: int = 10,
    max_dist_single_m: float = 20.0,
    max_dist_multi_m: float = 40.0,
    strategy: str = "anneal",
    corridor_mode: str = "double",
    base_seed: int = 0,
) -> tuple[CirculationResult, list[CageIterationMeta], int]:
    from services.circulation import NET_SHRINK_M
    from services.corridor_spine import build_spine
    from services.optimize import dedupe_and_rank

    if corridor_mode == "auto":
        return decide_access_modes(
            footprint, None, corridor_width_m, num_cages, weights,
            iterations, strategy=strategy, base_seed=base_seed,
        )

    if corridor_mode == "point":
        from services.point_access import anchor_candidates, anchor_coverage_gap

        # Deterministyczna enumeracja kotwic -- kotwica per wariant, jedna
        # kotwica we wszystkich strefach (Task 6 rozszerzy o kombinacje per
        # strefa przy auto). Strefy z rectangle_decompose bezpośrednio --
        # zones_probe z briefu przez place_circulation był zbędny (kontroler
        # decyzja 5). gap liczony na strefie [0] -- MVP jednostrefowy.
        zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
        anchors = anchor_candidates(zones[0].polygon)
        metas: list[CageIterationMeta] = []
        results: list[CirculationResult] = []
        for a in anchors:
            variant = _place_point_variant(footprint, corridor_width_m, a)
            if variant is None:
                continue
            gap = anchor_coverage_gap(zones[0].polygon, a)
            share = sum(
                _light_waste_for_cage(c, footprint) for c in variant.cage_polygons
            ) / max(1, len(variant.cage_polygons))
            score = 10.0 * gap + share
            results.append(variant)
            metas.append(_meta_from_result(
                variant, score=score,
                components={"coverage_gap": round(gap, 4), "light_waste": round(share, 4)},
            ))
        if not metas:
            raise ValueError("Strefa za mała na trzon klatkowy")
        order = sorted(range(len(metas)), key=lambda i: metas[i].score)
        metas = [metas[i] for i in order]
        for idx, m in enumerate(metas):
            m.seed = idx
        return results[order[0]], metas, 0

    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]
    prefer_flush = corridor_mode == "gallery"
    # Wstępny spine (bez klatek) -> kotwice kandydatów przy korytarzu, żeby
    # klatka mogła stanąć WEWNĄTRZ budynku (plan 2026-07-15 Task 10).
    prelim = build_spine([z.polygon for z in zones], {}, corridor_width_m, prefer_flush=prefer_flush)
    corridor_half = (corridor_width_m + 2 * NET_SHRINK_M) / 2.0
    candidates = _candidate_cages(
        footprint, zones, num_cages,
        spine_segments=[(s.p1, s.p2) for s in prelim], corridor_half_m=corridor_half,
    )
    if not candidates:
        raise ValueError("Obrys zbyt mały na klatkę schodową")

    # Minimal-k (plan 2026-07-15 Task 10): suwak = MAKSIMUM klatek. Próbujemy
    # k=1..num_cages; zwycięzca = najmniejsze k, którego najlepszy kandydat ma
    # zero czerwonych dojść. Gdy żadne k nie dowozi zera -> globalnie najlepszy
    # po (udział czerwonych, score). Metas = wszystkie kandydaci ze wszystkich k.
    per_k = max(6, iterations // max(1, num_cages))
    all_history: list = []
    best_per_k: dict[int, object] = {}
    for k in range(1, num_cages + 1):
        gen_k = _CageGenerator(
            footprint, zones, candidates, k,
            corridor_width_m, max_dist_single_m, max_dist_multi_m, prefer_flush=prefer_flush,
        )

        def eval_k(genome, payload, _k=k):
            if payload is None:
                return float("inf"), {}, ["nie udało się umieścić klatek"]
            score, components = _score_placement(payload, footprint, _k, weights)
            return score, components, []

        hist = _run_cage_hybrid(gen_k, eval_k, per_k, strategy, base_seed=base_seed)
        all_history += hist
        valid = [c for c in hist if c.payload is not None]
        if valid:
            best_per_k[k] = min(valid, key=lambda c: c.score)

    if not any(c.payload is not None for c in all_history):
        raise ValueError("Obrys zbyt mały na klatkę schodową")

    winner = None
    for k in range(1, num_cages + 1):
        if k in best_per_k and _red_share(best_per_k[k]) <= 1e-9:
            winner = best_per_k[k]
            break
    if winner is None:
        placed = [c for c in all_history if c.payload is not None]
        winner = min(placed, key=lambda c: (_red_share(c), c.score))

    ranked = [c for c in dedupe_and_rank(all_history, limit=iterations) if c.payload is not None]
    if all(c.genome != winner.genome for c in ranked):
        ranked = [winner] + ranked[: max(0, iterations - 1)]
    metas: list[CageIterationMeta] = [
        CageIterationMeta(
            seed=idx, score=c.score, cages_count=len(c.payload.cage_polygons),
            components=c.components, result=c.payload,
        )
        for idx, c in enumerate(ranked)
    ]
    best_seed = next(idx for idx, c in enumerate(ranked) if c.genome == winner.genome)
    winner.payload.zone_access_modes = ["corridor"] * len(winner.payload.zones)
    return winner.payload, metas, best_seed
