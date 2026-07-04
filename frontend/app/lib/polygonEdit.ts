/** Czyste funkcje edycji obrysu budynku (spec 2026-07-04 footprint-editing-ux
 *  §2). Zero zależności od Konvy/Reacta — operują na ringu Point2D[]
 *  (otwartym: bez zduplikowanego pierwszego punktu; segment i łączy
 *  points[i] z points[(i+1) % n]). */

import type { Point2D } from "../state/SessionContext";

export const SNAP_M = 0.5; // snap do siatki co 0.5m (rysowanie, wierzchołki, linie podziału)

export function snap(value: number): number {
  return Math.round(value / SNAP_M) * SNAP_M;
}

export type Delta = { dx: number; dy: number };

const EPS = 1e-6;

function samePoint(a: Point2D, b: Point2D): boolean {
  return Math.abs(a.x - b.x) < EPS && Math.abs(a.y - b.y) < EPS;
}

/** Wstawia punkt (po snapie) za wierzchołkiem segmentIndex. Zwraca null,
 *  gdy punkt po snapie pokrywa się z którymś końcem segmentu — ten sam
 *  guard co przy wstawianiu punktu osi korytarza. */
export function insertVertexAt(
  points: Point2D[],
  segmentIndex: number,
  point: Point2D
): Point2D[] | null {
  const n = points.length;
  const snapped = { x: snap(point.x), y: snap(point.y) };
  const a = points[segmentIndex];
  const b = points[(segmentIndex + 1) % n];
  if (samePoint(snapped, a) || samePoint(snapped, b)) return null;
  return [...points.slice(0, segmentIndex + 1), snapped, ...points.slice(segmentIndex + 1)];
}

/** Usuwa wierzchołek. Zwraca null przy 3 punktach — obrys nie może
 *  zdegenerować się poniżej trójkąta (spec §4). */
export function removeVertexAt(points: Point2D[], index: number): Point2D[] | null {
  if (points.length <= 3) return null;
  return [...points.slice(0, index), ...points.slice(index + 1)];
}

/** Rzut delty na jednostkową normalną segmentu p1→p2 — zostaje tylko
 *  składowa prostopadła do ściany (drag z Shiftem). */
export function projectDeltaOnNormal(p1: Point2D, p2: Point2D, delta: Delta): Delta {
  const ex = p2.x - p1.x;
  const ey = p2.y - p1.y;
  const len = Math.hypot(ex, ey);
  if (len < EPS) return delta;
  const nx = -ey / len;
  const ny = ex / len;
  const dot = delta.dx * nx + delta.dy * ny;
  return { dx: dot * nx, dy: dot * ny };
}

/** Efektywna delta draga segmentu: opcjonalny rzut na normalną (Shift),
 *  potem snap OBU składowych do SNAP_M — końce leżące na siatce zostają na
 *  siatce. Dla ścian ukośnych snap może zejść z idealnej normalnej o <SNAP_M
 *  (świadomy trade-off: siatka ważniejsza niż idealna prostopadłość; dla
 *  ścian osiowych — dominujący przypadek — prostopadłość jest dokładna). */
export function constrainSegmentDelta(
  p1: Point2D,
  p2: Point2D,
  delta: Delta,
  perpendicular: boolean
): Delta {
  const d = perpendicular ? projectDeltaOnNormal(p1, p2, delta) : delta;
  return { dx: snap(d.dx), dy: snap(d.dy) };
}

/** Przesuwa oba końce segmentu o deltę (ze snapem końców). Zwraca null,
 *  gdy przesunięty koniec pokryłby się z sąsiednim wierzchołkiem
 *  (degeneracja obrysu — spec §4). */
export function translateSegment(
  points: Point2D[],
  segmentIndex: number,
  delta: Delta
): Point2D[] | null {
  const n = points.length;
  const i1 = segmentIndex;
  const i2 = (segmentIndex + 1) % n;
  const next = points.map((p, i) =>
    i === i1 || i === i2 ? { x: snap(p.x + delta.dx), y: snap(p.y + delta.dy) } : p
  );
  const prev = (i1 - 1 + n) % n;
  const after = (i2 + 1) % n;
  if (samePoint(next[i1], next[prev]) || samePoint(next[i2], next[after])) return null;
  return next;
}
