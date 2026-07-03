"""Silnik grubości ścian -- spec docs/superpowers/specs/2026-07-04-wall-
thickness-design.md. Czysto obliczeniowy: bierze już-gotową geometrię
(footprint, apartamenty, komunikację) i wyprowadza z niej powierzchnię
netto oraz pasy ścian do narysowania. NIE jest wywoływany w środku
generowania układu (place_circulation/subdivide_units) -- silnik istniejący
zostaje nietknięty (spec §2)."""

from __future__ import annotations

from shapely.geometry import MultiPolygon, Polygon
from shapely.ops import unary_union

WALL_EXTERIOR_THICKNESS_M = 0.40
WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M = 0.10
"""Oś ściany zewnętrznej 10cm od lica wewnętrznego -> 30cm od lica
zewnętrznego (0.40 - 0.10). Spec §1/§4."""
WALL_INTERIOR_THICKNESS_M = 0.20
"""Oś ściany wewnętrznej na środku -> 10cm z każdej strony. Spec §1/§4."""
NET_SHRINK_M = 0.10
"""Wspólna stała dla obu typów ścian (spec §3): każda własna krawędź
komórki (mieszkania/korytarza/klatki) jest dokładnie 10cm od osi do lica
wewnętrznego, niezależnie czy to ściana zewnętrzna czy wewnętrzna."""


def net_polygon(polygon: Polygon) -> Polygon:
    """Powierzchnia netto (w świetle ścian) -- spec §3. Zwraca pustą
    geometrię (nie None, nie wyjątek) dla komórek zbyt małych, żeby
    przetrwać skurczenie o NET_SHRINK_M z każdej strony."""
    if polygon.is_empty or polygon.area < 1e-9:
        return Polygon()
    net = polygon.buffer(-NET_SHRINK_M, join_style="mitre")
    if net.is_empty or not net.is_valid or net.area < 1e-9:
        return Polygon()
    return net


def exterior_wall_band(footprint: Polygon) -> Polygon:
    """Pas ściany zewnętrznej wzdłuż całego obrysu -- spec §3."""
    exterior_envelope = footprint.buffer(
        WALL_EXTERIOR_THICKNESS_M - WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre"
    )
    interior_envelope = footprint.buffer(-WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre")
    return exterior_envelope.difference(interior_envelope)


def interior_wall_bands(footprint: Polygon, cells: list[Polygon]) -> Polygon | MultiPolygon:
    """Pasy ścian wewnętrznych między wszystkimi podanymi komórkami (i
    między komórkami a licem wewnętrznym obrysu) -- spec §3. `cells`
    powinno zawierać wszystkie ApartmentCell.polygon + circulation_geometry,
    świadomie BEZ LayoutResult.leftover (spec §3). Z 3+ komórkami
    pozostała ramka ścian może być topologicznie rozłączona -- wtedy
    Shapely zwraca MultiPolygon, nie Polygon (zob. test poniżej)."""
    interior_envelope = footprint.buffer(-WALL_EXTERIOR_AXIS_TO_INTERIOR_FACE_M, join_style="mitre")
    nets = [net_polygon(c) for c in cells if c is not None and not c.is_empty]
    nets = [n for n in nets if not n.is_empty]
    if not nets:
        return interior_envelope
    covered = unary_union(nets)
    return interior_envelope.difference(covered)
