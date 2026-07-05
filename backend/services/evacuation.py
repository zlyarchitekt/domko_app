"""Kropki ewakuacyjne co 1m wzdłuż osi korytarzy (spec 2026-07-04-
evacuation-dots). Czyste funkcje: shapely + stdlib. Progi 20/40m to robocze
heurystyki projektu (wartości usera) -- celowo BEZ przypisania § WT."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass

from shapely.geometry import LineString, Point, Polygon

from services.circulation import (
    CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M as GRAY_MAX_M,
    CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M as GREEN_MAX_M,
)

SAMPLE_STEP_M = 1.0
CAGE_ENTRY_TOLERANCE_M = 0.25
_NODE_TOL = 1e-6


@dataclass
class EvacuationDot:
    x: float
    y: float
    status: str  # "green" | "gray" | "red"
    distance_m: float | None


def _node_key(p: tuple[float, float]) -> tuple[float, float]:
    # deduplikacja węzłów z tolerancją: klucz po zaokrągleniu do 1e-6
    return (round(p[0], 6), round(p[1], 6))


def _split_at_crossings(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Dzieli segmenty w punktach wzajemnych przecięć (skrzyżowania bez
    wspólnego końca), żeby graf miał węzeł na każdym skrzyżowaniu."""
    result: list[tuple[tuple[float, float], tuple[float, float]]] = []
    lines = [LineString([p1, p2]) for p1, p2 in segments]
    for i, (p1, p2) in enumerate(segments):
        cuts: list[float] = []
        me = lines[i]
        if me.length < _NODE_TOL:
            continue
        for j, other in enumerate(lines):
            if i == j:
                continue
            inter = me.intersection(other)
            if inter.is_empty:
                continue
            pts = []
            if inter.geom_type == "Point":
                pts = [inter]
            elif hasattr(inter, "geoms"):
                pts = [g for g in inter.geoms if g.geom_type == "Point"]
            for pt in pts:
                t = me.project(pt)
                if _NODE_TOL < t < me.length - _NODE_TOL:
                    cuts.append(t)
        ts = sorted(set([0.0] + cuts + [me.length]))
        for a, b in zip(ts, ts[1:]):
            pa = me.interpolate(a)
            pb = me.interpolate(b)
            result.append(((pa.x, pa.y), (pb.x, pb.y)))
    return result


def _build_graph(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
) -> tuple[list[tuple[float, float]], list[tuple[int, int, float]]]:
    """Zwraca (nodes, edges); edges = (u, v, length)."""
    nodes: list[tuple[float, float]] = []
    index: dict[tuple[float, float], int] = {}

    def _add(p: tuple[float, float]) -> int:
        k = _node_key(p)
        if k not in index:
            index[k] = len(nodes)
            nodes.append((float(p[0]), float(p[1])))
        return index[k]

    edges: list[tuple[int, int, float]] = []
    for p1, p2 in segments:
        u, v = _add(p1), _add(p2)
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        if u != v and length > _NODE_TOL:
            edges.append((u, v, length))
    return nodes, edges


def _dijkstra(
    n_nodes: int, adj: dict[int, list[tuple[int, float]]], sources: list[int]
) -> list[float]:
    dist = [math.inf] * n_nodes
    heap: list[tuple[float, int]] = []
    for s in sources:
        dist[s] = 0.0
        heapq.heappush(heap, (0.0, s))
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u] + _NODE_TOL:
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist[v] - _NODE_TOL:
                dist[v] = nd
                heapq.heappush(heap, (nd, v))
    return dist


def compute_evacuation_dots(
    segments: list[tuple[tuple[float, float], tuple[float, float]]],
    cage_polygons: list[Polygon],
    green_max_m: float = GREEN_MAX_M,
    gray_max_m: float = GRAY_MAX_M,
) -> list[EvacuationDot]:
    if not segments:
        return []
    split = _split_at_crossings(segments)
    nodes, edges = _build_graph(split)
    if not edges:
        return []

    adj: dict[int, list[tuple[int, float]]] = {}
    for u, v, w in edges:
        adj.setdefault(u, []).append((v, w))
        adj.setdefault(v, []).append((u, w))

    # wejścia do klatek: węzły w odległości <= tolerancji od poligonu klatki
    dist_per_cage: list[list[float]] = []
    for cage in cage_polygons:
        sources = [i for i, p in enumerate(nodes) if cage.distance(Point(p)) <= CAGE_ENTRY_TOLERANCE_M]
        dist_per_cage.append(_dijkstra(len(nodes), adj, sources) if sources else [math.inf] * len(nodes))

    def _status(dists: list[float]) -> tuple[str, float | None]:
        reachable = [d for d in dists if math.isfinite(d)]
        if not reachable:
            return "red", None
        d = min(reachable)
        if len(reachable) >= 2:
            return ("gray" if d < gray_max_m else "red"), d
        return ("green" if d < green_max_m else "red"), d

    dots: list[EvacuationDot] = []
    seen: set[tuple[float, float]] = set()
    for u, v, w in edges:
        n_samples = max(1, int(math.floor(w / SAMPLE_STEP_M)))
        for k in range(n_samples + 1):
            t = min(w, k * SAMPLE_STEP_M)
            x = nodes[u][0] + (nodes[v][0] - nodes[u][0]) * (t / w)
            y = nodes[u][1] + (nodes[v][1] - nodes[u][1]) * (t / w)
            key = _node_key((x, y))
            if key in seen:
                continue
            seen.add(key)
            # spec §5: oś wewnątrz klatki nie dostaje kropek
            if any(c.contains(Point((x, y))) for c in cage_polygons):
                continue
            sample_dists = [
                min(dc[u] + t, dc[v] + (w - t)) for dc in dist_per_cage
            ] if dist_per_cage else []
            status, d = _status(sample_dists)
            dots.append(EvacuationDot(x=x, y=y, status=status, distance_m=d))
    return dots
