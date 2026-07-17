"""Tryb klatkowy (plan 2026-07-16): trzon = klatka schodowa + hol wejściowy,
mieszkania wchodzą bezpośrednio z holu -- zero korytarza. Wiedza domenowa:
docs/references/typologia-klatkowa.md (komunikacja 9-13%, trzon centralnie
bez okien albo przy północnej elewacji, każde mieszkanie dotyka trzonu)."""

from __future__ import annotations

from shapely.geometry import Polygon

from services.circulation import CAGE_DEPTH_M, CAGE_WIDTH_M

HALL_DEPTH_M = 1.8
"""Głębokość holu wejściowego doklejonego do klatki od strony wnętrza
(referencje: hol 15-25 m2; 1.8 m x szerokość klatki 4.2 = 7.6 m2 + podest)."""

_ANCHORS = ("north", "center", "south", "east", "west")


def build_point_core(zone: Polygon, anchor: str) -> tuple[Polygon, Polygon] | None:
    """(klatka, hol) dla kotwicy w strefie-prostokącie; None gdy nie mieści.

    north/south: klatka flush do krawędzi, wyśrodkowana w x, hol od wnętrza.
    east/west: analogicznie na osi x (klatka obrócona: szerokość wzdłuż y).
    center: klatka w środku strefy, hol od południa."""
    minx, miny, maxx, maxy = zone.bounds
    w, h = maxx - minx, maxy - miny
    cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0

    def rect(x0, y0, x1, y1):
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    if anchor in ("north", "south", "center"):
        need_w, need_h = CAGE_WIDTH_M, CAGE_DEPTH_M + HALL_DEPTH_M
        if need_w > w + 1e-9 or need_h > h + 1e-9:
            return None
        x0 = cx - CAGE_WIDTH_M / 2.0
        if anchor == "north":
            cage = rect(x0, maxy - CAGE_DEPTH_M, x0 + CAGE_WIDTH_M, maxy)
            hall = rect(x0, cage.bounds[1] - HALL_DEPTH_M, x0 + CAGE_WIDTH_M, cage.bounds[1])
        elif anchor == "south":
            cage = rect(x0, miny, x0 + CAGE_WIDTH_M, miny + CAGE_DEPTH_M)
            hall = rect(x0, cage.bounds[3], x0 + CAGE_WIDTH_M, cage.bounds[3] + HALL_DEPTH_M)
        else:  # center
            y0 = cy - (CAGE_DEPTH_M - HALL_DEPTH_M) / 2.0
            cage = rect(x0, y0, x0 + CAGE_WIDTH_M, y0 + CAGE_DEPTH_M)
            hall = rect(x0, y0 - HALL_DEPTH_M, x0 + CAGE_WIDTH_M, y0)
    else:  # east / west -- klatka obrócona 90 stopni
        need_w, need_h = CAGE_DEPTH_M + HALL_DEPTH_M, CAGE_WIDTH_M
        if need_w > w + 1e-9 or need_h > h + 1e-9:
            return None
        y0 = cy - CAGE_WIDTH_M / 2.0
        if anchor == "east":
            cage = rect(maxx - CAGE_DEPTH_M, y0, maxx, y0 + CAGE_WIDTH_M)
            hall = rect(cage.bounds[0] - HALL_DEPTH_M, y0, cage.bounds[0], y0 + CAGE_WIDTH_M)
        else:
            cage = rect(minx, y0, minx + CAGE_DEPTH_M, y0 + CAGE_WIDTH_M)
            hall = rect(cage.bounds[2], y0, cage.bounds[2] + HALL_DEPTH_M, y0 + CAGE_WIDTH_M)

    core = cage.union(hall)
    if not core.within(zone.buffer(1e-6)):
        return None
    return cage, hall


def core_polygon(cage: Polygon, hall: Polygon) -> Polygon:
    return cage.union(hall)


def anchor_candidates(zone: Polygon) -> list[str]:
    """Kotwice mieszczące trzon, rosnąco po marnowaniu doświetlanej elewacji
    (center nie dotyka elewacji -> 0.0). Remis rozstrzyga kolejność _ANCHORS
    (north przed center: preferuj klatkę z oknami, gdy oba darmowe)."""
    from services.cage_placement import _light_waste_for_cage

    scored = []
    for rank, a in enumerate(_ANCHORS):
        core = build_point_core(zone, a)
        if core is None:
            continue
        cage, hall = core
        scored.append((_light_waste_for_cage(cage, zone), rank, a))
    scored.sort()
    return [a for _, _, a in scored]
