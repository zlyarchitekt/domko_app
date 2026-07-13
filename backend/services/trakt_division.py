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

import random
import uuid

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from services.layout import MIN_CELL_DIMENSION_M, ApartmentSpec

_TOUCH_TOL_M = 0.05
"""Maks. odległość komponent-korytarz uznawana za styk (ściany działowe
w tym silniku są liniami osiowymi, geometrie stykają się na 0)."""

_AREA_TOL_M2 = 0.01
_BISECT_ITERS = 48


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


def slice_trakts(remainder, circulation_geometry, specs: list[ApartmentSpec], rng: random.Random | None):
    """(cells, leftover) -- kontrakt zwrotu jak fit_program_to_rectangles.

    Komponenty remainder to naturalne trakty (korytarz już je rozciął).
    Dla komponentu przylegającego do poziomego korytarza tniemy pionowo
    (kursor po x), do pionowego -- poziomo. Pole komórki trafia w cel
    bisekcją granicy (radzi sobie z wcięciami klatek: komórka wychodzi
    schodkowa, jak na referencyjnym rzucie usera). Komponenty bez styku
    z korytarzem w całości idą do leftover."""
    from services.layout import ApartmentCell  # deferred: cykl layout->unit_mix (Zadanie 3 spina moduły)

    queue: list[ApartmentSpec] = []
    for spec in specs:
        queue.extend([spec] * spec.target_count)
    components = _polygons(remainder)
    corridor_parts = _polygons(circulation_geometry)
    if rng is not None:
        rng.shuffle(queue)
        rng.shuffle(components)

    cells: list = []
    leftover_parts: list[Polygon] = []

    for component in components:
        part = next((p for p in corridor_parts if component.distance(p) < _TOUCH_TOL_M), None)
        if part is None or not queue:
            leftover_parts.append(component)
            continue
        pminx, pminy, pmaxx, pmaxy = part.bounds
        horizontal = (pmaxx - pminx) >= (pmaxy - pminy)

        minx, miny, maxx, maxy = component.bounds
        cursor = minx if horizontal else miny
        end = maxx if horizontal else maxy
        # Głębokość TRAKTU (komponentu), nie korytarza -- korytarz bywa
        # dużo płytszy (np. 1.7 m) niż trakt (np. 6 m); użycie głębokości
        # korytarza tu zawyżałoby poszerzenie o wcięcie o rząd wielkości.
        component_depth = (maxy - miny) if horizontal else (maxx - minx)
        remaining_area = component.area

        while queue and remaining_area > _AREA_TOL_M2:
            spec = queue[0]
            target = spec.min_area_m2
            if remaining_area < target * 0.6:
                break
            if remaining_area <= target:
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
            queue.pop(0)
            cells.append(ApartmentCell(id=str(uuid.uuid4()), type=spec.type, polygon=main))
            cursor = hi
            tail = _clip(component, horizontal, cursor, end)
            remaining_area = tail.area

        tail = _clip(component, horizontal, cursor, end)
        for t in _polygons(tail):
            if t.area > _AREA_TOL_M2:
                leftover_parts.append(t)

    leftover = unary_union([p for p in leftover_parts if p.area > _AREA_TOL_M2]) if leftover_parts else None
    if leftover is not None and (leftover.is_empty or leftover.area <= _AREA_TOL_M2):
        leftover = None
    return cells, leftover
