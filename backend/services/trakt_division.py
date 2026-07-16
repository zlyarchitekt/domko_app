"""Podział traktowy mieszkań (spec 2026-07-13 §B, user report "cienkie
prostokątne mieszkania"): komórki powstają WYŁĄCZNIE cięciami prostopadłymi
do przyległego korytarza, więc każda z definicji rozciąga się od korytarza
do elewacji. Zamiennik fit_program_to_rectangles dla przebiegów, które znają
geometrię komunikacji; resztki końcowe domyka istniejący zero-leftover merge
w iterate_units (_merge_leftover_into_cells) -- stąd naturalne "L" w
narożnikach.

Import ApartmentSpec/MIN_CELL_DIMENSION_M: brief tej specyfikacji sugerował
`from services.unit_mix import ...`, ale oba symbole są DEFINIOWANE w
services.layout (ApartmentSpec: layout.py:77, MIN_CELL_DIMENSION_M:
layout.py:296) -- unit_mix.py tylko je re-eksportuje przez własny import na
poziomie modułu. Cała reszta repo (test_unit_mix.py, test_wt_validation.py,
export_json.py, optimizer.py, endpoints/*.py) importuje je z services.layout
bezpośrednio, więc robimy tak samo tutaj dla spójności."""

from __future__ import annotations

import math
import random
import uuid

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from services.layout import MIN_CELL_DIMENSION_M, ApartmentSpec
from services.unit_mix import HARD_MAX_ASPECT_RATIO

_TOUCH_TOL_M = 0.05
"""Maks. odległość komponent-korytarz uznawana za styk (ściany działowe
w tym silniku są liniami osiowymi, geometrie stykają się na 0)."""

_AREA_TOL_M2 = 0.01
_BISECT_ITERS = 48

_SCALE_CAP = 1.25
"""Maksymalne rozciągnięcie komórki ponad bazowy metraż specyfikacji (user
2026-07-16): powyżej dokładamy POWTÓRKI wykonalnych typów zamiast pompować
istniejące komórki (M3 130 m2 przy targecie 64 "bez sensu")."""


def _polygons(geom) -> list[Polygon]:
    """Wyciąga poligony z dowolnego wyniku Shapely -- w tym zdegenerowanych
    przecięć na granicy (LineString/Point o zerowym polu) i
    GeometryCollection (przecięcie na krawędzi bywa mieszanką typów)."""
    if geom is None or geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if hasattr(geom, "geoms"):
        return [g for g in geom.geoms if isinstance(g, Polygon) and not g.is_empty]
    return []


def _clip_area(component: Polygon, horizontal: bool, lo: float, hi: float) -> float:
    minx, miny, maxx, maxy = component.bounds
    clip = (
        box(lo, miny - 1.0, hi, maxy + 1.0) if horizontal else box(minx - 1.0, lo, maxx + 1.0, hi)
    )
    return component.intersection(clip).area


def _clip(component: Polygon, horizontal: bool, lo: float, hi: float):
    minx, miny, maxx, maxy = component.bounds
    clip = (
        box(lo, miny - 1.0, hi, maxy + 1.0) if horizontal else box(minx - 1.0, lo, maxx + 1.0, hi)
    )
    return component.intersection(clip)


def typed_components(remainder, spine_segments=None, footprint=None) -> list:
    """Komponenty do cięcia jako (poligon, kierunek_cięcia|None).

    Kierunek pochodzi z segmentu spine dominującego w STREFIE, do której
    należy komponent. Fix 2026-07-15 (repro L z głęboką nogą): remainder to
    często JEDEN spójny poligon-L; cięty jednym kierunkiem robił długie
    "kiszki" w nodze. Tniemy per strefa obrysu (rectangle_decompose) --
    każde ramię dostaje kierunek prostopadły do SWOJEGO korytarza. Segment
    dominujący = ten o najdłuższym pokryciu w strefie (sam dystans daje
    remisy w narożniku).

    Wydzielone z slice_trakts (fix 2026-07-16): generator genomów liczył
    komponenty po _polygons(remainder) (np. 2), a slice_trakts budował typed
    per strefa (np. 4) -- component_order z guardem `i < len(typed)` wycinał
    resztę komponentów i cała noga L lądowała w leftover. Obie strony muszą
    liczyć komponenty TĄ SAMĄ funkcją."""

    def _seg_horizontal(s) -> bool:
        return abs(s[1][1] - s[0][1]) <= abs(s[1][0] - s[0][0])

    typed: list[tuple[Polygon, "bool | None"]] = []
    if footprint is not None and spine_segments:
        from services.bsp import rectangle_decompose
        for zone in rectangle_decompose(footprint):
            zr = remainder.intersection(zone)
            zparts = _polygons(zr)
            if not zparts:
                continue
            zbuf = zone.buffer(0.01)
            best = max(spine_segments, key=lambda s: LineString([s[0], s[1]]).intersection(zbuf).length)
            horiz = _seg_horizontal(best)
            for poly in zparts:
                if poly.area > _AREA_TOL_M2:
                    typed.append((poly, horiz))
    else:
        for poly in _polygons(remainder):
            typed.append((poly, None))
    return typed


def slice_trakts(
    remainder,
    circulation_geometry,
    specs: list[ApartmentSpec],
    rng: random.Random | None,
    queue_override: list[ApartmentSpec] | None = None,
    component_order: list[int] | None = None,
    spine_segments: list | None = None,
    footprint=None,
):
    """(cells, leftover) -- kontrakt zwrotu jak fit_program_to_rectangles.

    Komponenty remainder to naturalne trakty (korytarz już je rozciął).
    Dla komponentu przylegającego do poziomego korytarza tniemy pionowo
    (kursor po x), do pionowego -- poziomo. Pole komórki trafia w cel
    bisekcją granicy (radzi sobie z wcięciami klatek: komórka wychodzi
    schodkowa, jak na referencyjnym rzucie usera). Komponenty bez styku
    z korytarzem w całości idą do leftover.

    `queue_override`/`component_order` (plan 2026-07-14 Etap 2, Task 5):
    genom permutacyjny podaje JUŻ przetasowaną kolejkę specyfikacji
    (`queue_override`, dokładna lista -- nie ekspandujemy `specs` ponownie)
    i/lub kolejność indeksów komponentów remainder (`component_order`) --
    stosowane deterministycznie ZAMIAST losowego `rng.shuffle`, dokładnie
    tak jak przy `rng=None` (brak tasowania), tylko z jawnym porządkiem."""
    from services.layout import ApartmentCell  # deferred: cykl layout->unit_mix (Zadanie 3 spina moduły)

    if queue_override is not None:
        queue: list[ApartmentSpec] = list(queue_override)
    else:
        queue = []
        for spec in specs:
            queue.extend([spec] * spec.target_count)
    typed = typed_components(remainder, spine_segments, footprint)

    if component_order is not None:
        typed = [typed[i] for i in component_order if i < len(typed)]
    corridor_parts = _polygons(circulation_geometry)
    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(typed)

    # Fix 2026-07-16 (repro L): komponenty o NAJPŁYTSZYM trakcie mają
    # najmniejsze max_cell_area, więc muszą wybierać specyfikacje z kolejki
    # PIERWSZE -- inaczej wcześniejsze głębokie komponenty zjadają wszystkie
    # małe typy i płytki pas zostaje w całości w leftover (206 m2 pustki,
    # bo w kolejce zostały same M3/M4 > 48 m2). Sort stabilny: w ramach tej
    # samej głębokości porządek genomu (shuffle/component_order) zostaje.
    def _component_depth(item):
        poly, horiz = item
        minx, miny, maxx, maxy = poly.bounds
        if horiz is None:
            return min(maxx - minx, maxy - miny)
        return (maxy - miny) if horiz else (maxx - minx)

    typed.sort(key=_component_depth)

    cells: list = []
    leftover_parts: list[Polygon] = []

    for component, precomputed_horiz in typed:
        part = next((p for p in corridor_parts if component.distance(p) < _TOUCH_TOL_M), None)
        # Pusta kolejka NIE wysyła komponentu do leftover (fix 2026-07-16):
        # selekcja niżej ma fallback powtórek spoza kolejki -- lepiej dołożyć
        # mieszkanie ponad zadane liczby niż zostawić pusty komponent.
        if part is None:
            leftover_parts.append(component)
            continue
        if precomputed_horiz is not None:
            horizontal = precomputed_horiz
        elif spine_segments:
            best = min(spine_segments, key=lambda s: LineString([s[0], s[1]]).distance(component))
            horizontal = abs(best[1][1] - best[0][1]) <= abs(best[1][0] - best[0][0])
        else:
            pminx, pminy, pmaxx, pmaxy = part.bounds
            horizontal = (pmaxx - pminx) >= (pmaxy - pminy)

        minx, miny, maxx, maxy = component.bounds
        cursor = minx if horizontal else miny
        end = maxx if horizontal else maxy
        # Głębokość TRAKTU (komponentu), nie korytarza -- korytarz bywa
        # dużo płytszy (np. 1.7 m) niż trakt (np. 6 m); użycie głębokości
        # korytarza tu zawyżałoby poszerzenie o wcięcie o rząd wielkości.
        component_depth = (maxy - miny) if horizontal else (maxx - minx)

        # FAZA 1 (fix 2026-07-13, repro 68x12): selekcja specyfikacji
        # WYKONALNYCH przy tej głębokości traktu. Komórka o polu A w trakcie
        # głębokości D ma szerokość A/D i proporcje (A/D)/D -- pole powyżej
        # HARD_MAX_ASPECT_RATIO*D^2 ŁAMIE zakaz 1:3 z definicji (M4 81 m2 w
        # trakcie 4 m -> ratio 5). Cele są potem SKALOWANE do pełnego pola
        # komponentu, więc komponent nie zostawia ogona (stary kod mergował
        # ogon w ostatnią komórkę -> 102.7 m2, ratio 6.4).
        max_cell_area = HARD_MAX_ASPECT_RATIO * component_depth * component_depth
        # Dolny limit pola z DWÓCH ograniczeń: minimalny wymiar komórki ORAZ
        # zakaz 1:3 od dołu (fix 2026-07-16, repro L z traktem 12.2 m: komórka
        # A w trakcie D ma szerokość A/D, więc A < D^2/3 daje proporcje D/(A/D)
        # > 3 -- M2 43 m2 w trakcie 12.2 m wychodziła 3.5 m szeroka, ratio 3.5).
        min_cell_area = max(
            MIN_CELL_DIMENSION_M,
            component_depth / HARD_MAX_ASPECT_RATIO,
        ) * component_depth

        selected: list[int] = []
        total = 0.0
        for i, spec in enumerate(queue):
            # Za duży NA ten trakt (ratio od góry) LUB za mały (fix 2026-07-16:
            # M1 28.5 w trakcie 12.2 m to szerokość 2.3, ratio 5.2 -- a wybrany
            # kotwiczył skalę i blokował cap powtórek, stąd komórki 141 m2).
            if spec.min_area_m2 > max_cell_area or spec.min_area_m2 < min_cell_area - 1e-9:
                continue
            selected.append(i)
            total += spec.min_area_m2
            if total >= component.area:
                break
        # korekta dolna: skala < 1 nie może zwęzić żadnej komórki poniżej
        # MIN_CELL_DIMENSION_M -- odrzucaj ostatnią wybraną, aż się mieści
        while len(selected) > 1:
            scale = component.area / total
            if all(queue[i].min_area_m2 * scale >= min_cell_area - 1e-9 for i in selected):
                break
            total -= queue[selected.pop()].min_area_m2
        # korekta górna: skala > 1 nie może rozciągnąć komórki ponad limit
        # proporcji -- dobieraj kolejne wykonalne specyfikacje (rośnie suma,
        # maleje skala), póki są
        next_i = (selected[-1] + 1) if selected else 0
        while selected:
            scale = component.area / total
            if max(queue[i].min_area_m2 for i in selected) * scale <= max_cell_area + 1e-9:
                break
            addable = next(
                (i for i in range(next_i, len(queue))
                 if i not in selected and queue[i].min_area_m2 <= max_cell_area),
                None,
            )
            if addable is None:
                break
            selected.append(addable)
            total += queue[addable].min_area_m2
            next_i = addable + 1

        # Plan cięć = (typ, bazowe_pole) z wybranych specyfikacji. Gdy
        # komponent jest tak duży, że przy tej liczbie komórek któraś
        # przekroczyłaby limit proporcji (component.area / n > max_cell_area),
        # dopychamy dodatkowe cięcia POWTARZAJĄC typy (fix L 2026-07-15:
        # wąskie głębokie skrzydło dostawało 1 specyfikację z współdzielonej
        # kolejki i robiło jedną komórkę 6.3x20 ratio>3). Zakaz 1:3 jest
        # twardy, więc wolimy więcej mniejszych legalnych mieszkań niż jedno
        # nielegalne.
        plan: list[tuple[str, float]] = [(queue[i].type, queue[i].min_area_m2) for i in selected]
        if not plan:
            # Kolejka nie ma już specyfikacji wykonalnych przy tej głębokości
            # (np. M1/M2 zostały, a trakt 12 m wymaga >=D^2/3 ~ 50 m2).
            # Powtórki SPOZA kolejki (user 2026-07-16: "niech robi powtórki"):
            # bierzemy wykonalny typ z pełnego programu -- przekroczenie
            # zadanych liczb typów to miękka kara (mix), pusty komponent to
            # zakaz twardy (leftover >10%).
            feasible = [
                s for s in specs
                if min_cell_area - 1e-9 <= s.min_area_m2 <= max_cell_area
            ]
            if not feasible:
                leftover_parts.append(component)
                continue
            base = max(feasible, key=lambda s: (s.target_count, -s.min_area_m2))
            plan = [(base.type, base.min_area_m2)]
        min_cells = math.ceil(component.area / max_cell_area - 1e-9) if max_cell_area > 1e-9 else 1
        while len(plan) < min_cells:
            plan.append(plan[len(plan) % max(1, len(plan))])
        base_cycle = list(plan)
        total = sum(area for _, area in plan)

        # Cap skali (user 2026-07-16, "kloce" w nodze L): bez niego 2 sztuki
        # M3 z końca kolejki rozciągały się do 130 m2 (2x max programu),
        # zamiast dołożyć POWTÓRKI wykonalnego typu. Dokładamy powtórki
        # cyklicznie, aż komórki wracają w okolice targetu -- chyba że
        # kolejna powtórka zwęziłaby najmniejszą komórkę poniżej
        # min_cell_area (wtedy lekkie rozciągnięcie legalne > nielegalne
        # wąskie cięcie).
        while component.area / total > _SCALE_CAP:
            candidate = base_cycle[len(plan) % len(base_cycle)]
            new_total = total + candidate[1]
            new_scale = component.area / new_total
            smallest = min(a for _, a in plan + [candidate])
            if smallest * new_scale < min_cell_area - 1e-9:
                break
            plan.append(candidate)
            total = new_total

        # FAZA 2: cięcie prostopadłe z celami przeskalowanymi do pełnego
        # pola komponentu; ostatnia komórka domyka do końca (zero ogona).
        scale = component.area / total
        for order, (cell_type, base_area) in enumerate(plan):
            target = base_area * scale
            if order == len(plan) - 1:
                hi = end
            else:
                lo_b, hi_b = cursor, end
                for _ in range(_BISECT_ITERS):
                    mid = (lo_b + hi_b) / 2.0
                    if _clip_area(component, horizontal, cursor, mid) < target:
                        lo_b = mid
                    else:
                        hi_b = mid
                hi = hi_b
            if hi - cursor < MIN_CELL_DIMENSION_M:
                hi = min(cursor + MIN_CELL_DIMENSION_M, end)
            piece = _clip(component, horizontal, cursor, hi)
            piece_polys = _polygons(piece)
            if not piece_polys:
                break
            main = max(piece_polys, key=lambda p: p.area)
            for extra in piece_polys:
                if extra is not main:
                    leftover_parts.append(extra)
            if main.area < target * 0.5 and hi < end - 1e-9:
                # wcięcie zjadło pole -- poszerz o brakującą powierzchnię raz
                hi2 = min(end, hi + (target - main.area) / max(1e-6, component_depth))
                piece2 = _clip(component, horizontal, cursor, hi2)
                polys2 = _polygons(piece2)
                if polys2:
                    main = max(polys2, key=lambda p: p.area)
                    hi = hi2
            cells.append(ApartmentCell(id=str(uuid.uuid4()), type=cell_type, polygon=main))
            cursor = hi

        for i in sorted(selected, reverse=True):
            queue.pop(i)

        tail = _clip(component, horizontal, cursor, end)
        for t in _polygons(tail):
            if t.area > _AREA_TOL_M2:
                leftover_parts.append(t)

    leftover = unary_union([p for p in leftover_parts if p.area > _AREA_TOL_M2]) if leftover_parts else None
    if leftover is not None and (leftover.is_empty or leftover.area <= _AREA_TOL_M2):
        leftover = None
    return cells, leftover
