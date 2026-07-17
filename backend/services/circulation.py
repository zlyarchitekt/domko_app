"""Etap 1 (docs/superpowers/specs/2026-07-02-layout-engine-redesign-design.md):
umieszczenie klatki schodowej i korytarza w każdej strefie zwróconej przez
services.bsp.rectangle_decompose(). Klatka i korytarz przeniesione z
layout.py bez zmian logiki — nigdy nie były zepsute, zepsute były strefy,
które dostawały na wejściu (patrz spec §1a)."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from services.bsp import Zone, rectangle_decompose
from services.wall_geometry import NET_SHRINK_M

CAGE_POSITION_MODES = ("1a", "1b", "2", "3", "auto")
"""plan.md §4.3: 1a=elewacja front, 1b=elewacja dziedziniec/tył, 2=środek traktu,
3=narożnik, auto=narożnik wklęsły jeśli istnieje inaczej narożnik obrysu."""

CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M = 20.0
CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M = 40.0
"""Progi kolorowania linii środkowej korytarza (spec §7) -- świadomie
osobne od wt_validation.py's DEFAULT_MAX_CORRIDOR_DISTANCE_M (inny moduł,
inny punkt cyklu życia layoutu; duplikacja dwóch float jest tańsza niż
sprzężenie Etapu 1 z walidacją post-Etap-2)."""

CAGE_WIDTH_M = 4.2
CAGE_DEPTH_M = 5.7
"""Rzeczywisty obrys klatki schodowej: WYMIARY W ŚWIETLE (4.0x5.5m, spec
2026-07-03 staircase-cage-rectangle) + 20cm ściany wewnętrznej z każdej
strony (spec 2026-07-04 wall-thickness §6) = 4.2x5.7m rozstaw osi, który te
funkcje faktycznie budują: 2 biegi 120x250 + winda 160x250 + spoczniki/
korytarz 150 na górze i dole, W ŚWIETLE, plus zapas na ściany."""


def concave_vertices_in_zone(polygon: Polygon) -> list[tuple[int, float, float]]:
    """Wykrywa wierzchołki wklęsłe w pojedynczej strefie."""
    from services.bsp import concave_vertices

    return concave_vertices(polygon)


def _build_cage(
    polygon: Polygon, corner_data: tuple[int, float, float], width: float, depth: float
) -> Polygon:
    """Buduje prostokątną klatkę w narożniku."""
    from services.bsp import corner_cage

    idx, x, y = corner_data
    return corner_cage(polygon, (x, y), width=width, depth=depth)


def _place_cage_by_mode(
    polygon: Polygon,
    mode: str,
    width: float,
    depth: float,
    preferred_corner: tuple[float, float] | None = None,
) -> Polygon | None:
    """Umieszcza klatkę wg trybu z plan.md §4.3.

    - "3"/"auto": narożnik wklęsły jeśli istnieje (jak dotychczas), inaczej
      narożnik bounding-boxa (naprawia przypadek obrysu wypukłego, który
      wcześniej nigdy nie dostawał klatki mimo `place_cage=True`).
    - "2": środek strefy (typowe dla punktowca).
    - "1a": wzdłuż najdłuższej krawędzi zewnętrznej (elewacja frontowa).
    - "1b": wzdłuż najkrótszej krawędzi zewnętrznej — uproszczony zamiennik
      "krawędzi od dziedzińca" (wykrywanie krawędzi wewnętrznej/dziedzińca
      wymagałoby modelu sąsiednich budynków, poza zakresem tego MVP).
    """
    if polygon.is_empty or polygon.area < 1e-6:
        return None

    if mode not in CAGE_POSITION_MODES:
        raise ValueError(f"Unknown cage_position mode '{mode}'. Valid: {CAGE_POSITION_MODES}")

    if mode in ("3", "auto"):
        cv = concave_vertices_in_zone(polygon)
        if cv:
            try:
                cage = _build_cage(polygon, cv[0], width, depth)
            except ValueError:
                return None
            return cage if cage.area > 1e-6 else None
        return _corner_cage_convex(polygon, width, depth, preferred=preferred_corner)

    if mode == "2":
        return _centered_cage(polygon, width, depth)

    # "1a" / "1b"
    return _edge_cage(polygon, width, depth, longest=(mode == "1a"))


def _corner_cage_convex(
    polygon: Polygon, width: float, depth: float, preferred: tuple[float, float] | None = None
) -> Polygon | None:
    """Klatka w narożniku bounding-boxa — dla stref bez własnego wierzchołka wklęsłego.

    Domyślnie narożnik (minx,miny). Jeśli `preferred` pokrywa się z jednym z
    czterech narożników bbox (patrz `place_circulation`'s `_find_preferred_
    corner` — strefa po `rectangle_decompose` traci swój wklęsły wierzchołek,
    ale ten wierzchołek staje się zwykłym narożnikiem JEDNEJ z sąsiadujących
    prostokątnych stref), użyj go zamiast (minx,miny) — przywraca sens trybu
    "3"/"auto" (klatka schowana w narożniku wewnętrznym) po dekompozycji."""
    minx, miny, maxx, maxy = polygon.bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    ax, ay = corners[0]
    if preferred is not None:
        for cx, cy in corners:
            if abs(cx - preferred[0]) < 1e-6 and abs(cy - preferred[1]) < 1e-6:
                ax, ay = cx, cy
                break
    sx = width if ax == minx else -width
    sy = depth if ay == miny else -depth
    candidate = Polygon([(ax, ay), (ax + sx, ay), (ax + sx, ay + sy), (ax, ay + sy)])
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _centered_cage(polygon: Polygon, width: float, depth: float) -> Polygon | None:
    """Klatka wyśrodkowana w strefie (tryb 2 — punktowiec)."""
    center = polygon.centroid
    half_w = width / 2.0
    half_d = depth / 2.0
    candidate = Polygon(
        [
            (center.x - half_w, center.y - half_d),
            (center.x + half_w, center.y - half_d),
            (center.x + half_w, center.y + half_d),
            (center.x - half_w, center.y + half_d),
        ]
    )
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


def _edge_cage(polygon: Polygon, width: float, depth: float, longest: bool) -> Polygon | None:
    """Klatka wzdłuż najdłuższej (tryb 1a) lub najkrótszej (tryb 1b) krawędzi, skierowana do wnętrza."""
    coords = list(polygon.exterior.coords)[:-1]
    n = len(coords)
    if n < 2:
        return None

    edges = []
    for i in range(n):
        p1, p2 = coords[i], coords[(i + 1) % n]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        edges.append((length, p1, p2))
    edges.sort(key=lambda e: e[0], reverse=longest)
    _, p1, p2 = edges[0]

    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    edge_len = math.hypot(dx, dy)
    if edge_len < 1e-9:
        return None
    ux, uy = dx / edge_len, dy / edge_len

    mid_x, mid_y = (p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0
    normal_x, normal_y = -uy, ux
    centroid = polygon.centroid
    if normal_x * (centroid.x - mid_x) + normal_y * (centroid.y - mid_y) < 0:
        normal_x, normal_y = -normal_x, -normal_y

    half = width / 2.0
    p_a = (mid_x - ux * half, mid_y - uy * half)
    p_b = (mid_x + ux * half, mid_y + uy * half)
    p_c = (p_b[0] + normal_x * depth, p_b[1] + normal_y * depth)
    p_d = (p_a[0] + normal_x * depth, p_a[1] + normal_y * depth)

    candidate = Polygon([p_a, p_b, p_c, p_d])
    clipped = candidate.intersection(polygon)
    return clipped if not clipped.is_empty and clipped.area > 1e-6 else None


MIN_TRAKT_DEPTH_M = 4.0
"""Minimalna głębokość traktu mieszkalnego między korytarzem a elewacją
(spec 2026-07-13 trakt-aware-corridor §A). Trakt płytszy niż to jest
architektonicznie martwy (pokoje < 2.4 m, proporcje > 1:3) -- korytarz ma
zostawić pas ~0 (jednotrakt) albo >= tej wartości."""
MAX_ONE_SIDED_TRAKT_M = 7.0
"""Maks. głębokość traktu doświetlanego jednostronnie (user 2026-07-15)."""
MIN_THROUGH_TRAKT_M = 10.0
"""Min. głębokość traktu mieszkań na przestrzał; zakres (7, 10) m jest
architektonicznie martwy -- ani jednostronne, ani przestrzałowe."""


def _band_depth_ok(depth: float) -> bool:
    """Dopuszczalna głębokość pasa mieszkalnego (user 2026-07-15): ~0 (brak
    pasa), [MIN_TRAKT_DEPTH_M, MAX_ONE_SIDED_TRAKT_M] (doświetlane
    jednostronnie) albo >= MIN_THROUGH_TRAKT_M (na przestrzał). Zakres
    (7, 10) m jest architektonicznie martwy."""
    return (
        depth <= 1e-6
        or MIN_TRAKT_DEPTH_M - 1e-9 <= depth <= MAX_ONE_SIDED_TRAKT_M + 1e-9
        or depth >= MIN_THROUGH_TRAKT_M - 1e-9
    )


def _corridor_axis_offset(
    lo: float, hi: float, half: float, cage_bounds: tuple[float, float] | None,
    prefer_flush: bool = False,
) -> float:
    """Pozycja osi korytarza na osi poprzecznej strefy [lo, hi].

    Reguła (user 2026-07-15): głębokości pasów mieszkalnych muszą przejść
    `_band_depth_ok` (~0 / [4,7] / >=10). `prefer_flush=True` (galeriowiec):
    korytarz przy krawędzi (jednotrakt), jedyny pas legalny. Inaczej
    (dwutrakt): oś możliwie blisko klatki, gdzie OBA pasy legalne -- korytarz
    NIGDY nie skleja się z elewacją w dwutrakcie, jeśli legalny dwutrakt
    istnieje. Warunek styku z klatką (przedział touch = bounds klatki +-
    half) jest wpleciony w KAŻDY etap szukania (fix 2026-07-16: wcześniej
    filtr styku ubijał legalne kandydaty PO skanie i spadaliśmy do clampu,
    który tworzył martwy pas 1.35 m przy klatce na krawędzi nogi L).
    Kolejność: legalny dwutrakt w touch -> legalny flush w touch ->
    najmniej-zły (minimalna suma odległości pasów od legalnych głębokości)
    w touch -> legacy clamp."""
    center = (lo + hi) / 2.0
    anchor = (cage_bounds[0] + cage_bounds[1]) / 2.0 if cage_bounds is not None else center
    legacy = max(lo + half, min(hi - half, anchor))
    if cage_bounds is not None:
        touch_lo, touch_hi = cage_bounds[0] - half, cage_bounds[1] + half
    else:
        touch_lo, touch_hi = float("-inf"), float("inf")

    def in_touch(mid: float) -> bool:
        return touch_lo - 1e-9 <= mid <= touch_hi + 1e-9

    def bands(mid: float) -> tuple[float, float]:
        return (mid - half) - lo, hi - (mid + half)

    def flush_candidates() -> list[float]:
        out = []
        for flush in (lo + half, hi - half):
            b1, b2 = bands(flush)
            if in_touch(flush) and _band_depth_ok(b1) and _band_depth_ok(b2):
                out.append(flush)
        return out

    candidates: list[float] = []
    if prefer_flush:
        # galeriowiec: korytarz przy krawędzi, jedyny trakt musi być legalny
        candidates = flush_candidates()
    if not candidates:
        # dwutrakt: oba pasy legalnej głębokości, oś możliwie blisko klatki.
        # Skan po siatce 0.1 m jest deterministyczny, tani i odporny na
        # nieciągłość przedziałów [4,7] u [10,inf).
        best = None
        mid = lo + half
        while mid <= hi - half + 1e-9:
            b1, b2 = bands(mid)
            if (in_touch(mid) and b1 > 1e-6 and b2 > 1e-6
                    and _band_depth_ok(b1) and _band_depth_ok(b2)):
                if best is None or abs(mid - anchor) < abs(best - anchor):
                    best = mid
            mid += 0.1
        if best is not None:
            candidates.append(best)
    if not candidates:
        # legalny dwutrakt niemożliwy w zasięgu klatki -> flush z legalnym
        # pojedynczym traktem bije martwe pasy 7-10 z centrowania.
        candidates = flush_candidates()
    if not candidates:
        # ostatnia deska przed legacy: pozycja w touch minimalizująca
        # "martwość" pasów (suma odległości od najbliższej legalnej
        # głębokości); przy remisie bliżej kotwicy klatki.
        def badness(depth: float) -> float:
            d = max(depth, 0.0)
            if _band_depth_ok(d):
                return 0.0
            if d < MIN_TRAKT_DEPTH_M:
                return min(d, MIN_TRAKT_DEPTH_M - d)
            return min(d - MAX_ONE_SIDED_TRAKT_M, MIN_THROUGH_TRAKT_M - d)

        best = None
        best_bad = None
        mid = lo + half
        while mid <= hi - half + 1e-9:
            if in_touch(mid):
                b1, b2 = bands(mid)
                bad = badness(b1) + badness(b2)
                if (best_bad is None or bad < best_bad - 1e-9
                        or (abs(bad - best_bad) <= 1e-9 and abs(mid - anchor) < abs(best - anchor))):
                    best, best_bad = mid, bad
            mid += 0.1
        if best is not None:
            candidates.append(best)
    if not candidates:
        return legacy
    return min(candidates, key=lambda c: abs(c - anchor))


def _build_corridor(
    polygon: Polygon, width: float, cage_polygon: Polygon | None = None,
    prefer_flush: bool = False,
) -> Polygon:
    """Buduje korytarz wzdłuż osi dłuższego boku prostokątnej (po
    rectangle_decompose) strefy, uwzględniając wyrównanie do pozycji klatki
    schodowej (F2-04). `prefer_flush` -> galeriowiec (korytarz przy elewacji).
    Uwaga: główny tor geometrii to teraz build_spine (Task 4); ta funkcja
    zostaje dla _cages_share_valid_corridor (feasibility, mode-agnostic)."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return Polygon()
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny

    if w >= h:
        half = (width + 2 * NET_SHRINK_M) / 2.0
        cage_bounds = (cage_polygon.bounds[1], cage_polygon.bounds[3]) if cage_polygon else None
        mid_y = _corridor_axis_offset(miny, maxy, half, cage_bounds, prefer_flush)
        corridor = Polygon(
            [(minx, mid_y - half), (maxx, mid_y - half), (maxx, mid_y + half), (minx, mid_y + half)]
        )
    else:
        half = (width + 2 * NET_SHRINK_M) / 2.0
        cage_bounds = (cage_polygon.bounds[0], cage_polygon.bounds[2]) if cage_polygon else None
        mid_x = _corridor_axis_offset(minx, maxx, half, cage_bounds, prefer_flush)
        corridor = Polygon(
            [(mid_x - half, miny), (mid_x + half, miny), (mid_x + half, maxy), (mid_x - half, maxy)]
        )

    return corridor.intersection(polygon)


def _corridor_centerline(
    polygon: Polygon, width: float, cage_polygon: Polygon | None = None,
    prefer_flush: bool = False,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Oś korytarza strefy jako 2-punktowy odcinek — ta sama oś, ten sam
    warunek wyrównania do klatki co _build_corridor(), tylko zwrócona jako
    linia zamiast wypełnionego prostokąta (spec §3.1). None gdy korytarz
    o zadanej szerokości nie mieści się w strefie."""
    bounds = polygon.bounds
    if len(bounds) != 4:
        return None
    minx, miny, maxx, maxy = bounds
    w = maxx - minx
    h = maxy - miny
    grown_width = width + 2 * NET_SHRINK_M
    half = grown_width / 2.0

    if w >= h:
        if grown_width >= h:
            return None
        cage_bounds = (cage_polygon.bounds[1], cage_polygon.bounds[3]) if cage_polygon else None
        mid_y = _corridor_axis_offset(miny, maxy, half, cage_bounds, prefer_flush)
        return ((minx, mid_y), (maxx, mid_y))
    else:
        if grown_width >= w:
            return None
        cage_bounds = (cage_polygon.bounds[0], cage_polygon.bounds[2]) if cage_polygon else None
        mid_x = _corridor_axis_offset(minx, maxx, half, cage_bounds, prefer_flush)
        return ((mid_x, miny), (mid_x, maxy))


def _split_segment_at_cage_positions(
    seg: tuple[tuple[float, float], tuple[float, float]],
    cages: list[Polygon],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Dzieli odcinek centerline strefy tak, żeby węzeł grafu (spec
    2026-07-04-evacuation-dots) wypadał DOKŁADNIE przy wejściu do każdej
    klatki w tej strefie -- nie tylko na końcach strefy.

    `_corridor_centerline()` zwraca ZAWSZE jeden odcinek rozciągnięty na całą
    długość strefy (dwa węzły na jej krańcach); wyrównuje tylko oś poprzeczną
    do klatki (mid_y/mid_x), nie jej pozycję wzdłuż strefy. Klatka umieszczona
    NIE na krańcu (np. pozycja "2: środek traktu", albo kandydat iteracyjny
    z kotwicy na środku boku strefy) nie ma wtedy żadnego węzła w promieniu
    `evacuation.CAGE_ENTRY_TOLERANCE_M` -- `_build_graph`/Dijkstra widzi ją
    jako całkowicie nieosiągalną (0 reachable -> WSZYSTKIE kropki na czerwono),
    mimo że korytarz fizycznie ją mija. Rzutujemy centroid każdej klatki na
    linię odcinka (bezpieczne: `_build_corridor`/`_corridor_centerline` już
    wyrównały oś poprzeczną do tego samego centroidu, więc rzut leży
    praktycznie na osi klatki) i dzielimy odcinek w tym punkcie -- dokładnie
    tak samo jak `_split_at_crossings` robi to dla przecięć w `evacuation.py`."""
    if not cages:
        return [seg]
    p1, p2 = seg
    line = LineString([p1, p2])
    length = line.length
    if length < 1e-9:
        return [seg]
    cuts = sorted(
        {
            t
            for t in (line.project(Point(c.centroid.x, c.centroid.y)) for c in cages)
            if 1e-6 < t < length - 1e-6
        }
    )
    if not cuts:
        return [seg]
    ts = [0.0] + cuts + [length]
    result: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for a, b in zip(ts, ts[1:]):
        pa = line.interpolate(a)
        pb = line.interpolate(b)
        result.append(((pa.x, pa.y), (pb.x, pb.y)))
    return result


def _join_centerlines(
    segments: list[tuple[tuple[float, float], tuple[float, float]]]
) -> list[tuple[float, float]]:
    """Łączy odcinki centerline sąsiednich stref w jedną łamaną (spec §3.2).
    Zachłanny nearest-neighbor: zaczyna od pierwszego segmentu, za każdym
    razem dołącza segment, którego bliższy koniec leży najbliżej ostatniego
    punktu ścieżki. NIE straight-skeleton (odrzucone jako zbyt kruche dla
    wklęsłych kształtów w tej sesji) -- niepotrzebne tu, bo rectangle_
    decompose() już daje prawie-prostokątne strefy."""
    if not segments:
        return []

    remaining = list(segments[1:])
    path: list[tuple[float, float]] = [segments[0][0], segments[0][1]]

    while remaining:
        last = path[-1]
        best_idx = None
        best_dist = None
        best_reversed = False
        for i, (p1, p2) in enumerate(remaining):
            d1 = math.hypot(p1[0] - last[0], p1[1] - last[1])
            d2 = math.hypot(p2[0] - last[0], p2[1] - last[1])
            if best_dist is None or d1 < best_dist:
                best_dist, best_idx, best_reversed = d1, i, False
            if d2 < best_dist:
                best_dist, best_idx, best_reversed = d2, i, True
        p1, p2 = remaining.pop(best_idx)
        if best_reversed:
            path.append(p1)
        else:
            path.append(p2)

    return path


def _classify_segment_loading(
    zone_polygon: Polygon, segment: tuple[tuple[float, float], tuple[float, float]], corridor_width: float
) -> str:
    """"single" albo "double" (spec §3.3) -- geometryczne, NIE zależne od
    danych Etapu 2 (mieszkania jeszcze nie istnieją, gdy place_circulation()
    działa). Sonduje obie strony odcinka na głębokość MIN_ROOM_WIDTH_M
    (wt_validation.py) poza pasem korytarza."""
    from services.wt_validation import MIN_ROOM_WIDTH_M

    (x1, y1), (x2, y2) = segment
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return "single"
    ux, uy = dx / length, dy / length
    normal_x, normal_y = -uy, ux

    half_corridor = corridor_width / 2.0
    depth = MIN_ROOM_WIDTH_M
    sides_with_room = 0
    for sign in (1.0, -1.0):
        near = (
            x1 + normal_x * half_corridor * sign,
            y1 + normal_y * half_corridor * sign,
        )
        far = (
            near[0] + normal_x * depth * sign,
            near[1] + normal_y * depth * sign,
        )
        far2 = (
            x2 + normal_x * (half_corridor + depth) * sign,
            y2 + normal_y * (half_corridor + depth) * sign,
        )
        near2 = (
            x2 + normal_x * half_corridor * sign,
            y2 + normal_y * half_corridor * sign,
        )
        probe = Polygon([near, far, far2, near2])
        if not probe.is_valid or probe.area < 1e-9:
            continue
        clipped = probe.intersection(zone_polygon)
        if clipped.area > probe.area * 0.9:
            sides_with_room += 1

    return "double" if sides_with_room >= 2 else "single"


def _distances_along_centerline(
    path: list[tuple[float, float]], cage_points: list[tuple[float, float]]
) -> list[float]:
    """Odległość (długość łuku wzdłuż `path`) każdego wierzchołka `path` do
    najbliższego punktu w `cage_points`, rzutowanego na najbliższy punkt na
    `path` (spec §3.4). float('inf') dla wszystkich gdy `cage_points` puste."""
    if len(path) < 2:
        return [float("inf")] * len(path)

    cumulative = [0.0]
    for i in range(1, len(path)):
        p1, p2 = path[i - 1], path[i]
        cumulative.append(cumulative[-1] + math.hypot(p2[0] - p1[0], p2[1] - p1[1]))

    if not cage_points:
        return [float("inf")] * len(path)

    line = LineString(path)
    cage_arc_positions = [line.project(Point(cp)) for cp in cage_points]

    result = []
    for i, point in enumerate(path):
        vertex_arc = cumulative[i]
        result.append(min(abs(vertex_arc - cage_arc) for cage_arc in cage_arc_positions))
    return result


def _find_matching_corner(
    zone_polygon: Polygon, candidates: list[tuple[float, float]]
) -> tuple[float, float] | None:
    """Zwraca pierwszy narożnik bbox strefy pokrywający się z jednym z
    `candidates` (wklęsłych wierzchołków oryginalnego obrysu), albo None."""
    if not candidates:
        return None
    minx, miny, maxx, maxy = zone_polygon.bounds
    corners = [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]
    for corner in corners:
        for cand in candidates:
            if abs(corner[0] - cand[0]) < 1e-6 and abs(corner[1] - cand[1]) < 1e-6:
                return corner
    return None


@dataclass
class CirculationResult:
    """Wynik Etapu 1: strefy (po rectangle_decompose), zunifikowana
    geometria komunikacji, klatki, i pozostałość na mieszkania (Etap 2)."""

    zones: list[Zone]
    circulation_geometry: Polygon | None
    cage_polygons: list[Polygon] = field(default_factory=list)
    remainder: Polygon = field(default_factory=Polygon)
    """Może być MultiPolygon w praktyce mimo adnotacji typu (patrz spec §9) —
    konsumenci muszą sprawdzać hasattr(geom, "geoms")."""
    centerline: list[CorridorCenterlineSegment] = field(default_factory=list)
    evacuation_dots: list = field(default_factory=list)
    """list[EvacuationDot] -- spec 2026-07-04-evacuation-dots. Typ `list`
    bez parametru, żeby uniknąć importu cyklicznego (evacuation.py importuje
    stałe z tego modułu)."""
    spine_segments: list = field(default_factory=list)
    """Segmenty spine (plan 2026-07-15) -- źródło kierunków cięcia traktów.
    list[tuple[tuple[float,float], tuple[float,float]]]; puste w wynikach
    sprzed spine'u (reshape/manual, które budują geometrię inaczej)."""
    zone_access_modes: list = field(default_factory=list)
    """Per strefa (indeks = zones): "point" | "corridor" (plan 2026-07-16).
    Puste w wynikach sprzed trybu klatkowego i w ścieżkach manual/reshape."""


@dataclass
class CorridorCenterlineSegment:
    """Jeden odcinek połączonej linii środkowej korytarza (spec §3.5)."""

    points: tuple[tuple[float, float], tuple[float, float]]
    loading: str  # "single" | "double"
    distance_start_m: float
    distance_end_m: float
    max_distance_m: float
    exceeds_max: bool


def _make_centerline_segment(
    p1: tuple[float, float],
    p2: tuple[float, float],
    loading: str,
    d_start: float,
    d_end: float,
) -> CorridorCenterlineSegment:
    """Buduje CorridorCenterlineSegment z odległości i klasyfikacji już policzonych
    przez wywołującego -- wspólne dla place_circulation() i reshape_circulation(),
    żeby uniknąć rozjazdu semantyki jak w naprawionym Finding 2 (final-review)."""
    max_dist = (
        CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M
        if loading == "double"
        else CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M
    )
    return CorridorCenterlineSegment(
        points=(p1, p2),
        loading=loading,
        distance_start_m=d_start,
        distance_end_m=d_end,
        max_distance_m=max_dist,
        exceeds_max=bool(max(d_start, d_end) > max_dist) if math.isfinite(max(d_start, d_end)) else False,
    )


def _assemble_with_cages(
    footprint: Polygon,
    zones: list[Zone],
    local_cages: dict[int, list[Polygon]],
    corridor_width_m: float,
    max_dist_single_m: float,
    max_dist_multi_m: float,
    prefer_flush: bool = False,
) -> CirculationResult:
    """Buduje korytarze, linię środkową i kropki ewakuacyjne dla zadanych klatek
    (wyznaczonych w place_circulation). Pobiera słownik local_cages (indeks strefy
    → lista wielokątów klatek w tej strefie, może być pusta lub >1 element) i
    zwraca CirculationResult z auto-umieszczoną geometrią (bez elementów ręcznych
    z Etapu 2).

    Używane w place_circulation() do budowy wyniku auto-placement, przed dodaniem
    ręcznych klatek i korytarzy."""
    all_cages = [c for cages in local_cages.values() for c in cages]
    circulation_geom = unary_union(all_cages) if all_cages else Polygon()
    cage_polygons = all_cages

    remainder_parts: list[Polygon] = []

    # Spine (plan 2026-07-15): segmenty per strefa liczone tą samą regułą
    # traktów co _build_corridor, ale ŁĄCZONE na szwach stref -- na L/U
    # korytarz jest jednym spójnym poligonem zamiast luźnych pasków.
    from services.corridor_spine import build_spine, spine_polygon  # lazy: cykl

    spine = build_spine(
        [z.polygon for z in zones],
        {i: local_cages.get(i, []) for i in range(len(zones))},
        corridor_width_m,
        prefer_flush=prefer_flush,
    )
    corridor_poly = spine_polygon(spine, corridor_width_m, footprint)
    if corridor_poly.area > 0:
        circulation_geom = unary_union([circulation_geom, corridor_poly])

    for i, zone in enumerate(zones):
        if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
            continue
        zone_cages = local_cages.get(i, [])
        cages_union = unary_union(zone_cages) if zone_cages else None
        zone_remaining = zone.polygon.difference(cages_union) if cages_union is not None else zone.polygon
        zone_remaining = zone_remaining.difference(corridor_poly)
        if not zone_remaining.is_empty and zone_remaining.area > 1e-6:
            remainder_parts.append(zone_remaining)

    remainder = unary_union(remainder_parts) if remainder_parts else Polygon()

    raw_segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for s in spine:
        zone_cages = local_cages.get(s.zone_index, [])
        raw_segments.extend(_split_segment_at_cage_positions((s.p1, s.p2), zone_cages))

    centerline_path = _join_centerlines(raw_segments)
    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]
    arc_distances = _distances_along_centerline(centerline_path, cage_points)

    centerline: list[CorridorCenterlineSegment] = []
    for i in range(len(centerline_path) - 1):
        p1, p2 = centerline_path[i], centerline_path[i + 1]
        midpoint = Point((p1[0] + p2[0]) / 2.0, (p1[1] + p2[1]) / 2.0)
        containing_zone = next(
            (z.polygon for z in zones if z.polygon.buffer(1e-6).contains(midpoint)),
            footprint,
        )
        loading = _classify_segment_loading(containing_zone, (p1, p2), corridor_width_m)
        d_start, d_end = arc_distances[i], arc_distances[i + 1]
        centerline.append(_make_centerline_segment(p1, p2, loading, d_start, d_end))

    # ── Kropki ewakuacyjne (spec 2026-07-04-evacuation-dots) ──
    from services.evacuation import compute_evacuation_dots

    all_segments = [seg.points for seg in centerline]
    evacuation_dots = compute_evacuation_dots(
        all_segments, cage_polygons,
        green_max_m=max_dist_single_m, gray_max_m=max_dist_multi_m,
    )

    return CirculationResult(
        zones=zones,
        circulation_geometry=circulation_geom,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
        evacuation_dots=evacuation_dots,
        spine_segments=[(s.p1, s.p2) for s in spine],
    )


def place_circulation(
    footprint: Polygon,
    corridor_width_m: float,
    stair_width_m: float,
    place_cage: bool,
    cage_size_m: float,
    cage_position: str,
    num_cages: int = 1,
    manual_cages: list[Polygon] | list[list[tuple[float, float]]] | None = None,
    manual_corridors: list[list[tuple[float, float]]] | None = None,
    max_dist_single_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M,
    max_dist_multi_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M,
    corridor_mode: str = "double",
) -> CirculationResult:
    """Etap 1: dzieli obrys na prawie-prostokątne strefy (rectangle_decompose),
    umieszcza klatkę i korytarz w każdej, zwraca zunifikowany wynik.

    `cage_size_m` jest przyjmowany dla zgodności API, ale geometria klatki
    używa stałych CAGE_WIDTH_M x CAGE_DEPTH_M (spec 2026-07-03 §6).

    `num_cages`: maksymalna liczba klatek do umieszczenia. Najpierw jedna na
    strefę (spec 2026-07-04-cage-corridor-placement-quality §3), potem —
    jeśli stref jest mniej niż `num_cages` — deterministyczne dopełnienie
    z puli kandydatów `_candidate_cages`, wiele klatek na strefę dozwolone
    o ile jeden korytarz strefy obsłuży wszystkie (user override 2026-07-11).
    Gdy kandydatów braknie, umieszczonych zostaje tyle, ile się zmieści --
    bez błędu (cichy cap, spec §3.1)."""
    zones = [Zone(name=f"Z{i}", polygon=p) for i, p in enumerate(rectangle_decompose(footprint))]

    if corridor_mode == "point":
        from services.point_access import best_anchor, build_point_core, core_polygon

        cages: list[Polygon] = []
        cores: list[Polygon] = []
        modes: list[str] = []
        for zone in zones:
            a = best_anchor(zone.polygon)
            if a is None:
                raise ValueError(
                    "Strefa za mała na trzon klatkowy -- zmień tryb korytarza"
                )
            cage, hall = build_point_core(zone.polygon, a)
            cages.append(cage)
            cores.append(core_polygon(cage, hall))
            modes.append("point")
        circulation = unary_union(cores)
        remainder = footprint.difference(circulation)
        return CirculationResult(
            zones=zones,
            circulation_geometry=circulation,
            cage_polygons=cages,
            remainder=remainder,
            centerline=[],
            evacuation_dots=[],
            spine_segments=[],
            zone_access_modes=modes,
        )

    # rectangle_decompose() rozwiązuje każdy wklęsły wierzchołek OBRYSU na
    # rzecz dwóch sąsiadujących prostokątnych stref — żadna pojedyncza strefa
    # nie ma już wierzchołka wklęsłego, więc _place_cage_by_mode's "3"/"auto"
    # (klatka w narożniku wklęsłym) nigdy by go nie znalazło. Wykrywamy
    # wklęsłe wierzchołki oryginalnego obrysu raz i dla każdej strefy
    # sprawdzamy, czy jeden z jej 4 narożników bbox się z którymś pokrywa —
    # jeśli tak, to jest to dokładnie ten sam punkt, tylko teraz jako zwykły
    # narożnik strefy (patrz _corner_cage_convex).
    original_concave = [(x, y) for _, x, y in concave_vertices_in_zone(footprint)]

    # Do num_cages klatek, jedna na strefę (spec 2026-07-04-cage-corridor-
    # placement-quality §3) — optimizer.py nadal buduje LayoutInput bez
    # num_cages (zawsze efektywnie 1), świadomie odłożone poza zakres tego
    # planu. Kolejność prób: jeśli tryb "3"/"auto", najpierw strefy, których
    # narożnik bbox pokrywa się z oryginalnym wklęsłym wierzchołkiem
    # (przywraca sens trybu po rectangle_decompose), potem zwykła kolejność
    # stref.
    cage_zone_order = list(range(len(zones)))
    if place_cage and cage_position in ("3", "auto") and original_concave:
        matching = [
            i for i in cage_zone_order if _find_matching_corner(zones[i].polygon, original_concave) is not None
        ]
        if matching:
            remaining = [i for i in cage_zone_order if i not in matching]
            cage_zone_order = matching + remaining

    local_cages: dict[int, list[Polygon]] = {}

    if place_cage:
        cage_polygons: list[Polygon] = []
        for i in cage_zone_order:
            if len(cage_polygons) >= num_cages:
                break
            zone = zones[i]
            if not zone.polygon.is_valid or zone.polygon.area < 1e-6:
                continue
            preferred_corner = _find_matching_corner(zone.polygon, original_concave)
            cage_polygon = _place_cage_by_mode(
                zone.polygon, cage_position, CAGE_WIDTH_M, CAGE_DEPTH_M, preferred_corner=preferred_corner
            )
            if cage_polygon is not None and cage_polygon.area > zone.polygon.area * 0.9:
                cage_polygon = None
            if cage_polygon is not None and cage_polygon.area > 0:
                cage_polygons.append(cage_polygon)
                local_cages[i] = [cage_polygon]

        # Dopełnienie do num_cages, gdy stref jest mniej niż żądanych klatek
        # (user override 2026-07-11: suwak "Liczba klatek" ma działać też w
        # klasycznym trybie na prostym prostokącie = 1 strefie, nie tylko w
        # iteracyjnym). Ta sama zachłanna reguła co iterate_cage_placement,
        # tylko deterministycznie (pula kandydatów w stałej kolejności, bez
        # rng): kandydat odpada gdy koliduje z już postawioną klatką albo gdy
        # jeden korytarz strefy nie umie obsłużyć wszystkich jej klatek.
        if len(cage_polygons) < num_cages:
            # import lokalny: cage_placement importuje z tego modułu
            # (_assemble_with_cages itd.), import na poziomie modułu byłby cyklem
            from services.cage_placement import _cages_share_valid_corridor, _candidate_cages

            for zi, cage in _candidate_cages(footprint, zones):
                if len(cage_polygons) >= num_cages:
                    break
                if any(cage.intersects(existing) for existing in cage_polygons):
                    continue
                zone_existing = local_cages.get(zi)
                if zone_existing:
                    candidate_list = zone_existing + [cage]
                    if not _cages_share_valid_corridor(zones[zi].polygon, corridor_width_m, candidate_list):
                        continue
                    local_cages[zi] = candidate_list
                else:
                    local_cages[zi] = [cage]
                cage_polygons.append(cage)

    result = _assemble_with_cages(
        footprint, zones, local_cages, corridor_width_m,
        max_dist_single_m, max_dist_multi_m,
        prefer_flush=(corridor_mode == "gallery"),
    )

    return _merge_manual_elements(
        result, footprint, corridor_width_m,
        manual_cages, manual_corridors,
        max_dist_single_m, max_dist_multi_m,
    )


def _merge_manual_elements(
    result: CirculationResult,
    footprint: Polygon,
    corridor_width_m: float,
    manual_cages: list[Polygon] | list[list[tuple[float, float]]] | None,
    manual_corridors: list[list[tuple[float, float]]] | None,
    max_dist_single_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M,
    max_dist_multi_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M,
) -> CirculationResult:
    """Dokłada ręcznie narysowane klatki/korytarze (spec 2026-07-04 manual-
    circulation-drawing §3) DO ISTNIEJĄCEGO `result` -- mutuje i zwraca go.

    Wydzielone z `place_circulation` (Etap 2b Task 3) żeby ten sam blok
    scalania mógł być wywołany także po `iterate_cage_placement` (tryb
    iteracyjny, spec 2026-07-04-cage-placement-iterations), nie tylko po
    auto-placement klasycznym z `_assemble_with_cages`. Manual przeżywa
    każde ponowne auto-rozmieszczenie (klasyczne i iteracyjne); znika tylko
    przez usunięcie z listy we froncie."""
    manual_cages = manual_cages or []
    manual_corridors = manual_corridors or []

    for idx, ring in enumerate(manual_cages):
        cage_poly = ring if isinstance(ring, Polygon) else Polygon(ring)
        if not cage_poly.is_valid or cage_poly.area < 1e-6:
            raise ValueError(f"Klatka {idx + 1}: nieprawidłowy wielokąt")
        if not footprint.buffer(1e-6).contains(cage_poly):
            raise ValueError(f"Klatka {idx + 1} wykracza poza obrys budynku")
        result.circulation_geometry = unary_union([result.circulation_geometry, cage_poly])
        result.cage_polygons.append(cage_poly)
        result.remainder = result.remainder.difference(cage_poly)

    half = (corridor_width_m + 2 * NET_SHRINK_M) / 2.0
    all_cage_points = [(c.centroid.x, c.centroid.y) for c in result.cage_polygons]
    for path in manual_corridors:
        if len(path) < 2:
            continue
        band = LineString(path).buffer(half, cap_style="flat").intersection(footprint)
        if band.is_empty:
            continue
        result.circulation_geometry = unary_union([result.circulation_geometry, band])
        result.remainder = result.remainder.difference(band)
        # Odległości liczone per manualna ścieżka (osobna od auto-ścieżki);
        # zasila CorridorCenterlineSegment.distance_start_m/distance_end_m/
        # exceeds_max (używane gdzie indziej). Etap 3 (evacuation-dots) NIE
        # zastąpił tego -- dodał compute_evacuation_dots() jako osobne,
        # dodatkowe liczenie na grafie całej sieci (zasila evacuation_dots/UI
        # kropek), obok tego istniejącego liczenia per-ścieżka.
        arc = _distances_along_centerline([tuple(p) for p in path], all_cage_points)
        for i in range(len(path) - 1):
            p1, p2 = tuple(path[i]), tuple(path[i + 1])
            loading = _classify_segment_loading(footprint, (p1, p2), corridor_width_m)
            result.centerline.append(_make_centerline_segment(p1, p2, loading, arc[i], arc[i + 1]))

    # ── Przeliczenie kropek ewakuacyjnych (spec 2026-07-04-evacuation-dots) ──
    # Po scaleniu manuali: `centerline` to już pełna lista auto+manual,
    # `cage_polygons` też pełna auto+manual -- inaczej kropki ignorowałyby
    # ręcznie dorysowane klatki/korytarze.
    from services.evacuation import compute_evacuation_dots

    all_segments = [seg.points for seg in result.centerline]
    result.evacuation_dots = compute_evacuation_dots(
        all_segments, result.cage_polygons,
        green_max_m=max_dist_single_m, gray_max_m=max_dist_multi_m,
    )

    # Konwersja circulation_geometry do None jeśli pusta (pattern z oryginalnego kodu)
    if result.circulation_geometry.is_empty:
        result.circulation_geometry = None

    return result


def reshape_circulation(
    footprint: Polygon,
    centerline_points: list[tuple[tuple[float, float], tuple[float, float]]],
    corridor_width_m: float,
    cage_polygons: list[Polygon],
    max_dist_single_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_SINGLE_LOADED_M,
    max_dist_multi_m: float = CORRIDOR_CENTERLINE_MAX_DISTANCE_DOUBLE_LOADED_M,
) -> CirculationResult:
    """Przelicza geometrię korytarza + klasyfikację/odległości segmentów po
    edycji linii środkowej przez użytkownika (spec §3.6). Buduje geometrię
    jako bufor (cap_style="flat") wokół każdego edytowanego odcinka, zamiast
    ponownie dzielić footprint na strefy -- edytowana linia już nie jest
    przywiązana do rectangle_decompose()'s stref."""
    half = (corridor_width_m + 2 * NET_SHRINK_M) / 2.0
    buffered_parts = [
        LineString([p1, p2]).buffer(half, cap_style="flat")
        for p1, p2 in centerline_points
    ]
    circulation_geom = unary_union(buffered_parts).intersection(footprint)
    circulation_geom = unary_union([circulation_geom] + cage_polygons)

    remainder = footprint.difference(circulation_geom)

    # Ścieżka edytowanych odcinków jest ciągła (koniec segmentu i = początek
    # segmentu i+1, patrz frontend), więc liczymy _distances_along_centerline()
    # RAZ na całej złączonej ścieżce (jak place_circulation()), zamiast per-
    # segment -- inaczej LineString.project() przycina rzut klatki do końców
    # pojedynczego segmentu i zaniża odległość na dalszych odcinkach (Finding 2,
    # final-review 2026-07-03).
    flat_path: list[tuple[float, float]] = [centerline_points[0][0]]
    for _, p2 in centerline_points:
        flat_path.append(p2)

    cage_points = [(c.centroid.x, c.centroid.y) for c in cage_polygons]
    arc_distances = _distances_along_centerline(flat_path, cage_points)

    centerline: list[CorridorCenterlineSegment] = []
    for i, (p1, p2) in enumerate(centerline_points):
        loading = _classify_segment_loading(remainder, (p1, p2), corridor_width_m)
        d_start, d_end = arc_distances[i], arc_distances[i + 1]
        centerline.append(_make_centerline_segment(p1, p2, loading, d_start, d_end))

    from services.evacuation import compute_evacuation_dots

    evacuation_dots = compute_evacuation_dots(
        centerline_points, cage_polygons,
        green_max_m=max_dist_single_m, gray_max_m=max_dist_multi_m,
    )

    return CirculationResult(
        zones=[],
        circulation_geometry=circulation_geom if not circulation_geom.is_empty else None,
        cage_polygons=cage_polygons,
        remainder=remainder,
        centerline=centerline,
        evacuation_dots=evacuation_dots,
    )
