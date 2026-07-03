"""Walidacja Warunków Technicznych (WT) dla wygenerowanego układu.

Podstawa prawna: Rozporządzenie Ministra Infrastruktury z dnia 12 kwietnia 2002 r.
w sprawie warunków technicznych, jakim powinny odpowiadać budynki i ich
usytuowanie (Dz.U. 2022 poz. 1225 z późn. zm.) — patrz plan.md §4.6.

Zakres tego modułu: reguły geometryczne mieszkania i komunikacji (§94, §64,
§68, §58). Nasłonecznienie (§13) jest liczone osobno przez
`services/solar_analysis.py` (pvlib) — nie jest tu duplikowane ani
przybliżane, żeby uniknąć dwóch rozbieżnych źródeł prawdy o tym samym
wymogu.

Odległość do klatki schodowej (§58) liczona jest jako odległość korytarzowa
(Dijkstra po siatce 0.5m nałożonej na geometrię komunikacji), nie odległość
euklidesowa — patrz plan.md §4.4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
from shapely.geometry import Point, Polygon
from shapely.ops import nearest_points

from services.layout import ApartmentCell, LayoutResult

# Wartości graniczne z WT (patrz plan.md §4.6)
MIN_APARTMENT_AREA_M2 = 25.0  # §94 ust. 1 — kawalerka / bezwzględne minimum
MIN_ROOM_WIDTH_M = 2.4  # §94 ust. 2
MIN_CORRIDOR_WIDTH_M = 1.4  # §64 (przy drzwiach; 1.2m w prześwitach — nie modelowane osobno)
MIN_STAIR_WIDTH_M = 1.2  # §68 ust. 1 — bieg schodowy / szerokość klatki w tym uproszczonym modelu

MIN_CAGE_FACADE_CONTACT_M = 2.4
"""Styk klatki z elewacją zewnętrzną (dla naturalnego doświetlenia) —
UWAGA: to NIE jest wymóg WT, żaden paragraf WT nie wymaga styku klatki z
elewacją. Czysto opcjonalna heurystyka jakościowa — sprawdzana tylko gdy
wywołujący jawnie o to poprosi (validate_layout_wt(require_cage_facade_
contact=True)), domyślnie wyłączona i zawsze traktowana jako "nie dotyczy"."""
DEFAULT_MAX_CORRIDOR_DISTANCE_M = 20.0  # §58 ust. 4 — komunikacja jednostronna (single-loaded); patrz spec 2026-07-03 §7 dla wartości dwustronnej (40.0, tylko w circulation.py -- ta reguła nie klasyfikuje jedno/dwutraktowo, patrz spec §7 "świadomie poza zakresem")
CORRIDOR_GRID_STEP_M = 0.5  # plan.md §4.4 — siatka do Dijkstry

# Adjacency (plan.md §4.2 + Moduł C): min. długość styku mieszkanie<->komunikacja.
MIN_CONTACT_LENGTH_M = 1.2  # zalecane (Moduł C)
MIN_DOOR_CONTACT_LENGTH_M = 0.9  # bezwzględne minimum na drzwi (plan.md §4.2 pseudokod)
DEFAULT_MIN_CAGE_SPACING_M = 12.0  # typologies.md staircase_spacing_min


@dataclass
class WTRule:
    """Wynik jednej reguły WT (lub heurystyki nie-statutowej, oznaczonej code='heurystyka')."""

    code: str
    description: str
    passed: bool
    detail: str


@dataclass
class WTValidationResult:
    passed: bool
    score: int  # 0-100, udział reguł spełnionych
    rules: list[WTRule] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    """Opisy nie-spełnionych reguł — zachowane dla zgodności z dotychczasowymi konsumentami."""


def validate_layout_wt(
    layout: LayoutResult,
    local_law: str | None = None,
    max_corridor_distance_m: float | None = None,
    require_cage_facade_contact: bool = False,
) -> WTValidationResult:
    """Sprawdza układ pod kątem reguł WT §94/§64/§68/§58.

    `local_law` pozwala na lokalne złagodzenie niektórych progów (placeholder —
    dziś nie ma udokumentowanych w planie wyjątków lokalnych dla tych
    konkretnych paragrafów, w przeciwieństwie do §13 ust.2 dla zabudowy
    śródmiejskiej, obsługiwanego w solar_analysis.py).

    `require_cage_facade_contact` włącza opcjonalną (nie-WT) heurystykę
    styku klatki z elewacją — domyślnie wyłączona, patrz
    MIN_CAGE_FACADE_CONTACT_M.
    """
    max_distance = max_corridor_distance_m or DEFAULT_MAX_CORRIDOR_DISTANCE_M

    rules: list[WTRule] = []
    rules.append(_rule_apartment_area(layout))
    rules.append(_rule_room_width(layout))
    rules.append(_rule_corridor_width(layout))
    rules.append(_rule_stair_width(layout))
    rules.append(_rule_max_corridor_distance(layout, max_distance))
    rules.append(_rule_circulation_utilization(layout))
    rules.append(_rule_cage_facade_contact(layout, require_cage_facade_contact))

    issues = [r.detail for r in rules if not r.passed]
    passed_count = sum(1 for r in rules if r.passed)
    score = round((passed_count / len(rules)) * 100) if rules else 100

    return WTValidationResult(
        passed=all(r.passed for r in rules),
        score=score,
        rules=rules,
        issues=issues,
    )


def _rule_apartment_area(layout: LayoutResult) -> WTRule:
    """§94 ust. 1 — bezwzględne minimum powierzchni mieszkania (kawalerka: 25 m2)."""
    failing = [
        f"{apt.id} ({apt.type}): {apt.polygon.area:.2f} m2 < {MIN_APARTMENT_AREA_M2} m2"
        for apt in layout.apartments
        if apt.polygon.area < MIN_APARTMENT_AREA_M2
    ]
    passed = not failing
    detail = (
        "Wszystkie mieszkania spełniają minimum §94 ust. 1 (25 m2)."
        if passed
        else "Mieszkania poniżej minimum §94 ust. 1: " + "; ".join(failing)
    )
    return WTRule(code="§94 ust.1", description="Min. powierzchnia mieszkania", passed=passed, detail=detail)


def _apartment_min_width(apt: ApartmentCell) -> float:
    minx, miny, maxx, maxy = apt.polygon.bounds
    return min(maxx - minx, maxy - miny)


def _rule_room_width(layout: LayoutResult) -> WTRule:
    """§94 ust. 2 — min. szerokość pokoju (przybliżana mniejszym wymiarem bbox komórki)."""
    failing = [
        f"{apt.id}: {_apartment_min_width(apt):.2f} m < {MIN_ROOM_WIDTH_M} m"
        for apt in layout.apartments
        if _apartment_min_width(apt) < MIN_ROOM_WIDTH_M
    ]
    passed = not failing
    detail = (
        "Wszystkie mieszkania spełniają minimum §94 ust. 2 (2.4 m)."
        if passed
        else "Mieszkania poniżej minimum §94 ust. 2: " + "; ".join(failing)
    )
    return WTRule(code="§94 ust.2", description="Min. szerokość pokoju", passed=passed, detail=detail)


def _rule_corridor_width(layout: LayoutResult) -> WTRule:
    """§64 — min. szerokość korytarza wewnętrznego budynku (1.4m przy drzwiach).

    Szerokość korytarza jest parametrem wejściowym algorytmu BSP i jest
    dokładna z konstrukcji (`_build_corridor` tnie prostokąt o dokładnie tej
    szerokości) — nie jest re-mierzona z geometrii, żeby uniknąć błędów
    numerycznych po unii z klatką.
    """
    width = layout.corridor_width_m
    passed = width <= 0 or width >= MIN_CORRIDOR_WIDTH_M
    detail = (
        f"Szerokość korytarza {width:.2f} m spełnia minimum §64 ({MIN_CORRIDOR_WIDTH_M} m)."
        if passed
        else f"Szerokość korytarza {width:.2f} m < {MIN_CORRIDOR_WIDTH_M} m (WT §64)."
    )
    return WTRule(code="§64", description="Min. szerokość korytarza", passed=passed, detail=detail)


def _rule_stair_width(layout: LayoutResult) -> WTRule:
    """§68 ust. 1 — min. szerokość biegu schodowego / klatki (uproszczony model prostokątnej klatki)."""
    if not layout.cage_polygons:
        return WTRule(
            code="§68 ust.1",
            description="Min. szerokość klatki schodowej",
            passed=True,
            detail="Brak klatki schodowej w układzie — reguła nie dotyczy.",
        )
    width = layout.stair_width_m
    passed = width >= MIN_STAIR_WIDTH_M
    detail = (
        f"Szerokość klatki {width:.2f} m spełnia minimum §68 ({MIN_STAIR_WIDTH_M} m)."
        if passed
        else f"Szerokość klatki {width:.2f} m < {MIN_STAIR_WIDTH_M} m (WT §68 ust. 1)."
    )
    return WTRule(code="§68 ust.1", description="Min. szerokość klatki schodowej", passed=passed, detail=detail)


def _rule_cage_facade_contact(layout: LayoutResult, required: bool) -> WTRule:
    """Opcjonalna (NIE-WT) heurystyka: styk klatki z elewacją zewnętrzną dla
    naturalnego doświetlenia. Sprawdzana tylko gdy `required=True` — inaczej
    zawsze "nie dotyczy", żeby nie sugerować nieistniejącego wymogu prawnego."""
    description = "Styk klatki z elewacją (opcjonalne doświetlenie, nie WT)"
    if not required:
        return WTRule(
            code="heurystyka",
            description=description,
            passed=True,
            detail="Opcja doświetlenia klatki nie została włączona — reguła nie dotyczy.",
        )
    if not layout.cage_polygons:
        return WTRule(
            code="heurystyka",
            description=description,
            passed=True,
            detail="Brak klatki schodowej w układzie — reguła nie dotyczy.",
        )
    failing: list[str] = []
    for i, cage in enumerate(layout.cage_polygons):
        contact = cage.boundary.intersection(layout.footprint.boundary)
        length = 0.0 if contact.is_empty else contact.length
        if length < MIN_CAGE_FACADE_CONTACT_M:
            failing.append(f"klatka #{i + 1}: styk {length:.2f} m < {MIN_CAGE_FACADE_CONTACT_M} m")
    passed = not failing
    detail = (
        f"Wszystkie klatki stykają się z elewacją na min. {MIN_CAGE_FACADE_CONTACT_M} m (opcja doświetlenia)."
        if passed
        else "Niewystarczający styk z elewacją (opcja doświetlenia): " + "; ".join(failing)
    )
    return WTRule(code="heurystyka", description=description, passed=passed, detail=detail)


def _rule_max_corridor_distance(layout: LayoutResult, max_distance_m: float) -> WTRule:
    """§58 ust. 4 — max. dojście do klatki schodowej, liczone odległością korytarzową (Dijkstra)."""
    if not layout.apartments:
        return WTRule(
            code="§58 ust.4",
            description="Max. dojście do klatki (odległość korytarzowa)",
            passed=True,
            detail="Brak mieszkań w układzie — reguła nie dotyczy.",
        )
    if not layout.cage_polygons or layout.circulation_geometry is None:
        return WTRule(
            code="§58 ust.4",
            description="Max. dojście do klatki (odległość korytarzowa)",
            passed=False,
            detail="Brak klatki schodowej lub geometrii komunikacji — żadne mieszkanie nie ma dostępu do klatki.",
        )

    graph, nodes = _build_corridor_graph(layout.circulation_geometry, CORRIDOR_GRID_STEP_M)
    cage_targets = [poly.centroid for poly in layout.cage_polygons]

    failing: list[str] = []
    unreachable: list[str] = []
    for apt in layout.apartments:
        distance = _corridor_distance_to_nearest_cage(
            apt, layout.circulation_geometry, graph, nodes, cage_targets
        )
        if distance is None:
            unreachable.append(apt.id)
            continue
        if distance > max_distance_m:
            failing.append(f"{apt.id}: {distance:.1f} m > {max_distance_m:.0f} m")

    passed = not failing and not unreachable
    details = []
    if failing:
        details.append("Przekroczone dojście: " + "; ".join(failing))
    if unreachable:
        details.append(
            "Brak ścieżki korytarzowej do klatki (mieszkanie niepołączone z komunikacją): "
            + ", ".join(unreachable)
        )
    detail = (
        f"Wszystkie mieszkania w zasięgu {max_distance_m:.0f} m (WT §58 ust. 4)."
        if passed
        else " ".join(details)
    )
    return WTRule(code="§58 ust.4", description="Max. dojście do klatki (odległość korytarzowa)", passed=passed, detail=detail)


def _rule_circulation_utilization(layout: LayoutResult) -> WTRule:
    """Heurystyka praktyczna (nie paragraf WT): komunikacja nie powinna zjadać całej powierzchni."""
    if layout.footprint_area_m2 <= 0:
        return WTRule(code="heurystyka", description="Udział komunikacji w obrysie", passed=True, detail="Brak powierzchni obrysu.")
    utilization = layout.usable_area_m2 / layout.footprint_area_m2
    passed = utilization <= 0.92
    detail = (
        f"Udział powierzchni użytkowej {utilization:.1%} w normie (<=92%)."
        if passed
        else f"Udział powierzchni użytkowej {utilization:.1%} przekracza praktyczne 92% (zbyt mało miejsca na ściany/komunikację)."
    )
    return WTRule(code="heurystyka", description="Udział komunikacji w obrysie", passed=passed, detail=detail)


# ═══════════════════════════════════════════════════════════════════
# Odległość korytarzowa: siatka 0.5m + Dijkstra (plan.md §4.4)
# ═══════════════════════════════════════════════════════════════════


def _build_corridor_graph(
    circulation: Polygon, grid_step: float = CORRIDOR_GRID_STEP_M
) -> tuple[nx.Graph, dict[tuple[int, int], tuple[float, float]]]:
    """Buduje graf siatki nad geometrią komunikacji — węzły tylko wewnątrz poligonu."""
    minx, miny, maxx, maxy = circulation.bounds
    n_i = int((maxx - minx) / grid_step) + 2
    n_j = int((maxy - miny) / grid_step) + 2

    buffered = circulation.buffer(1e-6)
    nodes: dict[tuple[int, int], tuple[float, float]] = {}
    for i in range(n_i):
        for j in range(n_j):
            x = minx + i * grid_step
            y = miny + j * grid_step
            if buffered.covers(Point(x, y)):
                nodes[(i, j)] = (x, y)

    graph: nx.Graph = nx.Graph()
    for key, pos in nodes.items():
        graph.add_node(key, pos=pos)

    neighbor_offsets = ((1, 0), (0, 1), (1, 1), (1, -1))
    for (i, j) in nodes:
        for di, dj in neighbor_offsets:
            neighbor = (i + di, j + dj)
            if neighbor in nodes:
                (x1, y1), (x2, y2) = nodes[(i, j)], nodes[neighbor]
                weight = math.hypot(x2 - x1, y2 - y1)
                graph.add_edge((i, j), neighbor, weight=weight)

    return graph, nodes


def _nearest_node(
    nodes: dict[tuple[int, int], tuple[float, float]], point: Point
) -> tuple[int, int] | None:
    if not nodes:
        return None
    return min(
        nodes.keys(),
        key=lambda key: (nodes[key][0] - point.x) ** 2 + (nodes[key][1] - point.y) ** 2,
    )


def _corridor_distance_to_nearest_cage(
    apt: ApartmentCell,
    circulation: Polygon,
    graph: nx.Graph,
    nodes: dict[tuple[int, int], tuple[float, float]],
    cage_targets: list[Point],
) -> float | None:
    """Odległość korytarzowa: drzwi mieszkania (najbliższy punkt na granicy z komunikacją) -> najbliższa klatka."""
    apt_side, door_point = nearest_points(apt.polygon.boundary, circulation)
    if apt_side.distance(door_point) > 0.5:
        # Mieszkanie realnie nie styka się z komunikacją — nie da się wyznaczyć drzwi.
        return None

    start = _nearest_node(nodes, door_point)
    if start is None:
        return None

    best: float | None = None
    for cage_point in cage_targets:
        end = _nearest_node(nodes, cage_point)
        if end is None:
            continue
        try:
            length = nx.shortest_path_length(graph, start, end, weight="weight")
        except nx.NetworkXNoPath:
            continue
        if best is None or length < best:
            best = length
    return best


# ═══════════════════════════════════════════════════════════════════
# Walidacja komunikacji: adjacency + zasięg klatek + rozstaw klatek
# (plan.md §4.2, F3-03)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class CommunicationIssue:
    apartment_id: str | None
    """None dla problemów dotyczących całego układu (np. brak klatki, zbyt bliskie klatki)."""
    error: str


@dataclass
class CommunicationValidationResult:
    all_connected: bool
    issues: list[CommunicationIssue] = field(default_factory=list)


def _apartment_circulation_contact_length(apt: ApartmentCell, circulation: Polygon) -> float:
    """Długość wspólnej granicy mieszkania i geometrii komunikacji (korytarz+klatka)."""
    contact = apt.polygon.boundary.intersection(circulation.boundary)
    return 0.0 if contact.is_empty else contact.length


def validate_communication(
    layout: LayoutResult,
    min_contact_length_m: float = MIN_CONTACT_LENGTH_M,
    max_corridor_distance_m: float = DEFAULT_MAX_CORRIDOR_DISTANCE_M,
    min_cage_spacing_m: float = DEFAULT_MIN_CAGE_SPACING_M,
) -> CommunicationValidationResult:
    """Waliduje styk mieszkań z komunikacją, zasięg do klatki i rozstaw klatek.

    Odpowiednik plan.md §4.2 `validate_adjacency()` + §4.4 `validate_staircase_coverage()`,
    ale operujący na już wygenerowanym `LayoutResult` zamiast osobnych poligonów
    apartment/corridor/staircase — te są tu ujednolicone w `circulation_geometry`.
    """
    issues: list[CommunicationIssue] = []

    if layout.circulation_geometry is None or layout.circulation_geometry.is_empty:
        if layout.apartments:
            return CommunicationValidationResult(
                all_connected=False,
                issues=[
                    CommunicationIssue(
                        apartment_id=None,
                        error="Brak geometrii komunikacji (korytarz/klatka) w układzie.",
                    )
                ],
            )
        return CommunicationValidationResult(all_connected=True, issues=[])

    circulation = layout.circulation_geometry

    # 1. Adjacency — każde mieszkanie musi stykać się z komunikacją na min. długości.
    for apt in layout.apartments:
        contact = _apartment_circulation_contact_length(apt, circulation)
        if contact < MIN_DOOR_CONTACT_LENGTH_M:
            issues.append(
                CommunicationIssue(
                    apartment_id=apt.id,
                    error=(
                        f"Brak wystarczającego styku z komunikacją: {contact:.2f} m "
                        f"< {MIN_DOOR_CONTACT_LENGTH_M} m (drzwi niemożliwe)."
                    ),
                )
            )
        elif contact < min_contact_length_m:
            issues.append(
                CommunicationIssue(
                    apartment_id=apt.id,
                    error=(
                        f"Styk z komunikacją {contact:.2f} m poniżej zalecanego "
                        f"{min_contact_length_m} m (drzwi zmieszczą się, ale styk jest wąski)."
                    ),
                )
            )

    # 2. Zasięg do najbliższej klatki (odległość korytarzowa, nie euklidesowa).
    if not layout.cage_polygons:
        if layout.apartments:
            issues.append(
                CommunicationIssue(apartment_id=None, error="Brak klatki schodowej w układzie.")
            )
    else:
        graph, nodes = _build_corridor_graph(circulation, CORRIDOR_GRID_STEP_M)
        cage_targets = [poly.centroid for poly in layout.cage_polygons]
        for apt in layout.apartments:
            distance = _corridor_distance_to_nearest_cage(apt, circulation, graph, nodes, cage_targets)
            if distance is None:
                issues.append(
                    CommunicationIssue(
                        apartment_id=apt.id,
                        error="Brak ścieżki korytarzowej do klatki schodowej (mieszkanie niepołączone z komunikacją).",
                    )
                )
            elif distance > max_corridor_distance_m:
                issues.append(
                    CommunicationIssue(
                        apartment_id=apt.id,
                        error=f"Dojście do klatki {distance:.1f} m > {max_corridor_distance_m:.0f} m (WT §58 ust. 4).",
                    )
                )

    # 3. Min. rozstaw między klatkami, gdy jest ich więcej niż jedna.
    if len(layout.cage_polygons) > 1:
        centroids = [poly.centroid for poly in layout.cage_polygons]
        for i in range(len(centroids)):
            for j in range(i + 1, len(centroids)):
                spacing = centroids[i].distance(centroids[j])
                if spacing < min_cage_spacing_m:
                    issues.append(
                        CommunicationIssue(
                            apartment_id=None,
                            error=(
                                f"Klatki #{i + 1} i #{j + 1} zbyt blisko siebie: "
                                f"{spacing:.1f} m < {min_cage_spacing_m:.0f} m."
                            ),
                        )
                    )

    return CommunicationValidationResult(all_connected=not issues, issues=issues)
