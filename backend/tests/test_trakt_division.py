"""Testy podziału traktowego (spec 2026-07-13 §B): cięcia wyłącznie
prostopadle do korytarza, komórka = pełna głębokość traktu."""

import random

from shapely.geometry import Polygon, box

from services.layout import ApartmentSpec
from services.trakt_division import slice_trakts


def _specs(*areas):
    return [ApartmentSpec(type=f"T{i}", min_area_m2=a, target_count=1) for i, a in enumerate(areas)]


def test_rect_trakt_full_depth_cells():
    """Trakt 30x6 nad poziomym korytarzem: 3 komórki po 60 m2 -> szer. 10 m,
    każda dotyka i korytarza (y=0), i elewacji (y=6)."""
    trakt = box(0, 0, 30, 6)
    corridor = box(0, -1.7, 30, 0)
    cells, leftover = slice_trakts(trakt, corridor, _specs(60, 60, 60), rng=None)
    assert len(cells) == 3
    for c in cells:
        assert abs(c.polygon.area - 60.0) < 0.5
        assert c.polygon.bounds[1] < 1e-6 and c.polygon.bounds[3] > 6 - 1e-6  # pełna głębokość
        assert c.polygon.distance(corridor) < 1e-6
    assert leftover is None or leftover.area < 0.5


def test_notched_trakt_stepped_cells():
    """Trakt z wcięciem (klatka) -> komórki schodkowe. Od fixu skalowania
    (2026-07-13, repro 68x12) cele są skalowane do PEŁNEGO pola komponentu
    (zero ogona -- stary kontrakt "pole == cel +-1m2" mergował ogon w jedną
    komórkę i łamał proporcje 1:3), więc asercja: proporcje celów zachowane,
    komponent pokryty w całości, każda komórka przy korytarzu."""
    trakt = Polygon([(0, 0), (20, 0), (20, 6), (12, 6), (12, 4), (8, 4), (8, 6), (0, 6)])
    corridor = box(0, -1.7, 20, 0)
    cells, leftover = slice_trakts(trakt, corridor, _specs(50, 54), rng=None)
    assert len(cells) == 2
    scale = trakt.area / (50.0 + 54.0)
    for c, target in zip(cells, (50.0, 54.0)):
        assert abs(c.polygon.area - target * scale) < 1.0
        assert c.polygon.distance(corridor) < 1e-6
    assert abs(sum(c.polygon.area for c in cells) - trakt.area) < 1e-6
    assert leftover is None or leftover.area < 0.5


def test_component_not_touching_corridor_becomes_leftover():
    far = box(100, 100, 110, 106)
    corridor = box(0, -1.7, 30, 0)
    cells, leftover = slice_trakts(far, corridor, _specs(60), rng=None)
    assert cells == []
    assert leftover is not None and abs(leftover.area - 60.0) < 1e-6


def test_deterministic_for_same_seed():
    trakt = box(0, 0, 30, 6)
    corridor = box(0, -1.7, 30, 0)
    a, _ = slice_trakts(trakt, corridor, _specs(60, 45, 70), rng=random.Random(3))
    b, _ = slice_trakts(trakt, corridor, _specs(60, 45, 70), rng=random.Random(3))
    assert [c.polygon.bounds for c in a] == [c.polygon.bounds for c in b]


def test_vertical_corridor_slices_horizontally():
    """Korytarz pionowy -> cięcia poziome (y), komórki na pełną szerokość traktu."""
    trakt = box(0, 0, 6, 30)
    corridor = box(-1.7, 0, 0, 30)
    cells, _ = slice_trakts(trakt, corridor, _specs(60, 60, 60), rng=None)
    assert len(cells) == 3
    for c in cells:
        assert c.polygon.bounds[0] < 1e-6 and c.polygon.bounds[2] > 6 - 1e-6  # pełna szerokość
