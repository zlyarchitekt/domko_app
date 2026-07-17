"""Tryb klatkowy (plan 2026-07-16): trzon = klatka schodowa + hol wejściowy,
mieszkania wchodzą bezpośrednio z holu -- zero korytarza. Wiedza domenowa:
docs/references/typologia-klatkowa.md (komunikacja 9-13%, trzon centralnie
bez okien albo przy północnej elewacji, każde mieszkanie dotyka trzonu)."""

from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon

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


def _parts(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return [g for g in geom.geoms if isinstance(g, Polygon) and g.area > 1e-6]
    return []


def point_zone_components(zone: Polygon, core: Polygon) -> list[tuple[Polygon, bool]]:
    """Remainder strefy pocięty na pas zachodni / środkowy (nad+pod trzonem)
    / wschodni wzdłuż krawędzi trzonu (core.minx, core.maxx); kierunek cięcia
    zwracany per pas jest PROSTOPADŁY do krawędzi styku z trzonem, żeby każda
    komórka po cięciu zachowała ten styk (konwencja slice_trakts,
    zweryfikowana testem styku: `horizontal=True` => kursor idzie po x =>
    cięcia PIONOWE; `horizontal=False` => kursor po y => cięcia POZIOME).
    Pas zachodni/wschodni styka się PIONOWĄ krawędzią trzonu -> potrzebuje
    cięć POZIOMYCH -> horizontal=False. Pas nad/pod trzonem styka się
    POZIOMĄ krawędzią trzonu -> potrzebuje cięć PIONOWYCH -> horizontal=True.
    """
    minx, miny, maxx, maxy = zone.bounds
    cminx, cminy, cmaxx, cmaxy = core.bounds
    remainder = zone.difference(core)

    def band(x0, y0, x1, y1):
        if x1 - x0 < 1e-6 or y1 - y0 < 1e-6:
            return None
        return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])

    out: list[tuple[Polygon, bool]] = []
    for rect, horiz in (
        (band(minx, miny, cminx, maxy), False),   # zachód: styk pionowy -> tnij po y
        (band(cmaxx, miny, maxx, maxy), False),   # wschód: styk pionowy -> tnij po y
        (band(cminx, cmaxy, cmaxx, maxy), True),  # nad trzonem: styk poziomy -> tnij po x
        (band(cminx, miny, cmaxx, cminy), True),  # pod trzonem (hol): styk poziomy -> tnij po x
    ):
        if rect is None:
            continue
        for poly in _parts(remainder.intersection(rect)):
            if poly.area > 1.0:
                out.append((poly, horiz))
    return out


def slice_point_zone(zone, core, specs, rng, queue_override=None, component_order=None):
    """Cienki adapter na `slice_trakts` -- trzon wiatraczka nie jest
    podłużnym korytarzem, więc `slice_trakts` nie może wywnioskować kierunku
    cięcia z samej geometrii korytarza (per komponent). Budujemy więc
    SZTUCZNE `spine_segments`: po jednym odcinku na środku każdego pasa z
    `point_zone_components`, zorientowanym tak, by nearest-segment w
    `slice_trakts` (gałąź `elif spine_segments:`) odczytał żądany
    `horizontal` per komponent. Wołamy z `footprint=None`, żeby `slice_trakts`
    poszedł ścieżką "jeden poligon = jeden typed wpis z kierunkiem None" i
    dociągnął kierunek z nearest-segment zamiast per-strefa typed_components
    (ta druga ścieżka wymaga prawdziwego footprintu z rectangle_decompose,
    czego trzon nie ma).

    UWAGA (odstępstwo od brief-owego szkicu, patrz task-2-brief.md Step 3):
    pasy z `point_zone_components` stykają się ze sobą wzdłuż krawędzi
    trzonu (np. pas zachodni i pas "nad trzonem" dzielą odcinek x=core.minx),
    więc `unary_union` dogładza je w JEDEN spójny poligon-pierścień (dokładnie
    `zone.difference(core)`) -- `typed_components`/`_polygons` widzi wtedy 1
    komponent z `horiz=None` zamiast 4 pasów, i CAŁA informacja o kierunku
    per pas ginie (test dawał `len(cells) == 0`, wszystko leciało jednym
    cięciem bez trafionego kierunku). `MultiPolygon` (bez union) trzyma pasy
    rozłącznie mimo stykających się krawędzi -- `_polygons` iteruje po
    `.geoms` i zwraca 4 osobne wpisy, każdy dopasowywany do WŁASNEGO segmentu
    ze `spine_segments` (dystans ~0), więc kierunek trafia poprawnie."""
    from services.trakt_division import slice_trakts

    comps = point_zone_components(zone, core)
    if component_order is not None:
        comps = [comps[i] for i in component_order if i < len(comps)]
    remainder = MultiPolygon([p for p, _ in comps])
    segs = []
    for poly, horiz in comps:
        x0, y0, x1, y1 = poly.bounds
        if horiz:  # cięcia pionowe -> segment "poziomy" (dx>=dy)
            segs.append(((x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)))
        else:      # cięcia poziome -> segment "pionowy" (dy>dx)
            segs.append((((x0 + x1) / 2, y0), ((x0 + x1) / 2, y1)))
    return slice_trakts(
        remainder, core, specs, rng,
        queue_override=queue_override, spine_segments=segs, footprint=None,
    )
