import type { Point2D } from "../state/SessionContext";

/** Pole wielokąta (shoelace) w m² — punkty bez duplikatu pierwszego na końcu. */
export function polygonArea(points: Point2D[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}
