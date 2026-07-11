"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Line, Rect, Text, Circle, Group, Path } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";
import { Stage as StageType } from "konva/lib/Stage";
import { Maximize2, RotateCcw } from "lucide-react";
import { useSession, Point2D, DEFAULT_TYPE_COLORS } from "./state/SessionContext";
import { deriveApartmentStatuses } from "./lib/deriveStatus";
import { GeoJsonPolygon } from "./lib/api";
import * as api from "./lib/api";
import {
  snap,
  insertVertexAt,
  removeVertexAt,
  constrainSegmentDelta,
  translateSegment,
  type Delta,
} from "./lib/polygonEdit";
const METER_PX = 50; // base scale: 1m = 50px

/** Krok snapowania przy przesuwaniu komunikacji/klatek [m] (user 2026-07-11). */
const CIRCULATION_SNAP_M = 0.1;
const CIRCULATION_SNAP_PX = CIRCULATION_SNAP_M * METER_PX;
/** Przyciąga pozycję node'a (w px warstwy = px świata) do siatki 0.1m.
 * Wywoływane w onDragMove — node.x()/y() są w układzie rodzica (warstwy),
 * więc transformacja stage'a (zoom/pan) nie wpływa na krok. */
const snapNodeToGrid = (node: { x: () => number; y: () => number; position: (p: { x: number; y: number }) => void }) => {
  node.position({
    x: Math.round(node.x() / CIRCULATION_SNAP_PX) * CIRCULATION_SNAP_PX,
    y: Math.round(node.y() / CIRCULATION_SNAP_PX) * CIRCULATION_SNAP_PX,
  });
};

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function ringToPoints(geom: GeoJsonPolygon): Point2D[] {
  const ring = geom.coordinates[0] ?? [];
  return ring.slice(0, -1).map(([x, y]) => ({ x, y }));
}

/** #rrggbb (jak z <input type="color">) -> rgba() z zadaną alfą. Wypełnienie
 * mieszkania per typ musi być pół-przezroczyste (etykieta + pasy ścian pod
 * spodem czytelne) -- spec 2026-07-06 apartment-type-colors §2.3. */
function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  if ([r, g, b].some(Number.isNaN)) return `rgba(148, 163, 184, ${alpha})`;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Corridor centerline segments are stored as a list of [p1,p2] pairs where
 *  consecutive segments share an endpoint (seg[i][1] === seg[i+1][0]) --
 *  same continuity `reshape_circulation()` assumes server-side (circulation.py
 *  §_join_centerlines). `points` is `[api.Point, api.Point]` where
 *  `api.Point = [number, number]` (a tuple, NOT a `{x,y}` object — see
 *  `frontend/app/lib/api.ts`'s `Point` type). Flattening to a plain
 *  `Point2D[]` list and rebuilding segments from it is the shared primitive
 *  both insert and remove need. */
function flattenCenterline(centerline: api.CorridorCenterlineSegment[]): Point2D[] {
  if (centerline.length === 0) return [];
  const toPt = ([x, y]: api.Point): Point2D => ({ x, y });
  const flat: Point2D[] = [toPt(centerline[0].points[0])];
  for (const seg of centerline) {
    flat.push(toPt(seg.points[1]));
  }
  return flat;
}

function segmentsFromFlatPath(flat: Point2D[]): [Point2D, Point2D][] {
  const segs: [Point2D, Point2D][] = [];
  for (let i = 0; i < flat.length - 1; i++) {
    segs.push([flat[i], flat[i + 1]]);
  }
  return segs;
}

/** Konva's <Line> only ever draws a single ring, so it can't represent a
 *  polygon with holes. wall_bands can legitimately have holes: the exterior
 *  band is `footprint.buffer(+0.30).difference(buffer(-0.10))` -- an annulus
 *  by construction -- and interior bands can equally end up with a hole
 *  wherever unallocated `leftover` space (or any cell) is fully enclosed by
 *  wall material. Rendering only coordinates[0] (as ringToPoints does) would
 *  fill that hole solid, painting all of `leftover` as fake wall -- exactly
 *  the bug the backend's multi-round wall_bands/leftover fix (Task 4,
 *  2026-07-04) was written to prevent, just reintroduced on the frontend.
 *  Building one `M...Z` SVG subpath per ring and filling with fillRule=
 *  "evenodd" (see <Path> usage below) punches holes correctly regardless of
 *  a ring's winding direction -- verified against a live /layout/generate
 *  response during Task 5 manual QA, where wall_bands[0] came back as a
 *  2-ring GeoJSON Polygon (exterior + 1 hole). */
function geomToSvgPath(geom: GeoJsonPolygon): string {
  return geom.coordinates
    .map((ring) => {
      const pts = ring.slice(0, -1);
      if (pts.length === 0) return "";
      const [x0, y0] = pts[0];
      const rest = pts
        .slice(1)
        .map(([x, y]) => `L ${x * METER_PX} ${-y * METER_PX}`)
        .join(" ");
      return `M ${x0 * METER_PX} ${-y0 * METER_PX} ${rest} Z`;
    })
    .join(" ");
}

/** Dekoracyjny podział klatki schodowej (spec 2026-07-03 staircase-cage-rectangle §3/§4.3):
 *  rzędy od strony minY ("strona wejścia/korytarza"): spocznik+korytarz (150/550),
 *  2 biegi 120x250 + winda 160x250 (250/550), spocznik 240x150 + szacht 160x150 (150/550).
 *  Frakcje liczone z bbox konkretnego poligonu, nie zahardkodowane w px. Czysto
 *  wizualne -- zero wpływu na geometrię/WT, listening=false na wszystkim. */
function cageSubdivisionShapes(
  geom: GeoJsonPolygon,
  keyPrefix: string,
  scale: number,
  lineColor: string,
  textColor: string
): React.ReactNode[] {
  const ring = ringToPoints(geom);
  if (ring.length < 3) return [];
  const xs = ring.map((p) => p.x);
  const ys = ring.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const w = maxX - minX;
  const h = maxY - minY;
  if (w < 1e-6 || h < 1e-6) return [];

  // Zone fractions of the approved 400(width)x550(depth) layout, authored
  // assuming a PORTRAIT cage (depth = long axis = world Y). `_edge_cage`
  // (modes "1a"/"1b") can legitimately place a LANDSCAPE cage instead (long
  // axis horizontal) -- detect which world axis is actually longer and map
  // width/depth fractions onto *that* one, instead of hardcoding
  // width=X/depth=Y. "Entrance side" stays a simplification: the min-value
  // end of the depth axis, same convention as before, just generalized to
  // whichever world axis that now is (spec 2026-07-03 §4.3 already accepts
  // this as an approximation, not exact).
  const isPortrait = h >= w;
  // Scalar accessors along whichever world axis width/depth ended up on.
  // Canvas Y is flipped (screen Y grows downward); canvas X is not -- the
  // flip must follow the accessor that maps to true world Y in each branch.
  const depthCoord = (f: number) => (isPortrait ? -(minY + f * h) * METER_PX : (minX + f * w) * METER_PX);
  const widthCoord = (f: number) => (isPortrait ? (minX + f * w) * METER_PX : -(minY + f * h) * METER_PX);
  // A layout-space point (width-fraction, depth-fraction) always resolves to
  // a canvas [x, y] pair -- which accessor lands in which slot flips with
  // orientation, so every shape built from `pt()` re-orients as a rigid
  // transform instead of stretching.
  const pt = (wf: number, df: number): [number, number] =>
    isPortrait ? [widthCoord(wf), depthCoord(df)] : [depthCoord(df), widthCoord(wf)];

  const X_FLIGHT1 = 120 / 400;
  const X_FLIGHTS = 240 / 400;
  const Y_BOTTOM = 150 / 550; // landing+corridor strip (entrance side = min end of depth axis)
  const Y_MID_TOP = 400 / 550; // top of flights/elevator band

  const sw = 1 / scale;
  const nodes: React.ReactNode[] = [];

  // Row separators (full width) + column separators.
  nodes.push(
    <Line key={`${keyPrefix}-row-b`} points={[...pt(0, Y_BOTTOM), ...pt(1, Y_BOTTOM)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-row-t`} points={[...pt(0, Y_MID_TOP), ...pt(1, Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-col-f`} points={[...pt(X_FLIGHT1, Y_BOTTOM), ...pt(X_FLIGHT1, Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-col-e`} points={[...pt(X_FLIGHTS, Y_BOTTOM), ...pt(X_FLIGHTS, 1)]} stroke={lineColor} strokeWidth={sw} listening={false} />
  );

  // Stair-flight tread hatching: 6 lines per flight across both flights' band.
  for (let i = 1; i <= 6; i++) {
    const t = Y_BOTTOM + (i / 7) * (Y_MID_TOP - Y_BOTTOM);
    nodes.push(
      <Line key={`${keyPrefix}-tread-${i}`} points={[...pt(0, t), ...pt(X_FLIGHTS, t)]} stroke={lineColor} strokeWidth={sw} listening={false} />
    );
  }

  // Direction arrows: left flight up, right flight down (shaft + head marks).
  const arrow = (key: string, xf: number, fromT: number, toT: number) => {
    const head = 0.03 * (toT > fromT ? 1 : -1);
    return [
      <Line key={`${key}-shaft`} points={[...pt(xf, fromT), ...pt(xf, toT)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
      <Line
        key={`${key}-head`}
        points={[...pt(xf - 0.02, toT - head), ...pt(xf, toT), ...pt(xf + 0.02, toT - head)]}
        stroke={lineColor}
        strokeWidth={sw}
        listening={false}
      />,
    ];
  };
  nodes.push(...arrow(`${keyPrefix}-arr-l`, X_FLIGHT1 / 2, Y_BOTTOM + 0.03, Y_MID_TOP - 0.03));
  nodes.push(...arrow(`${keyPrefix}-arr-r`, (X_FLIGHT1 + X_FLIGHTS) / 2, Y_MID_TOP - 0.03, Y_BOTTOM + 0.03));

  // Elevator X (diagonals across the elevator cell only).
  nodes.push(
    <Line key={`${keyPrefix}-el-1`} points={[...pt(X_FLIGHTS, Y_BOTTOM), ...pt(1, Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />,
    <Line key={`${keyPrefix}-el-2`} points={[...pt(1, Y_BOTTOM), ...pt(X_FLIGHTS, Y_MID_TOP)]} stroke={lineColor} strokeWidth={sw} listening={false} />
  );

  // Labels (tiny, theme-following).
  const label = (key: string, xf: number, yf: number, text: string) => {
    const [x, y] = pt(xf, yf);
    return (
      <Text
        key={key}
        x={x}
        y={y}
        text={text}
        fontSize={10 / scale}
        fill={textColor}
        listening={false}
        offsetX={14 / scale}
        offsetY={5 / scale}
      />
    );
  };
  nodes.push(
    label(`${keyPrefix}-lb-sp`, X_FLIGHTS / 2, (Y_MID_TOP + 1) / 2, "spocznik"),
    label(`${keyPrefix}-lb-sz`, (X_FLIGHTS + 1) / 2, (Y_MID_TOP + 1) / 2, "szacht"),
    label(`${keyPrefix}-lb-wd`, (X_FLIGHTS + 1) / 2, (Y_BOTTOM + Y_MID_TOP) / 2, "winda"),
    label(`${keyPrefix}-lb-ko`, 0.5, Y_BOTTOM / 2, "korytarz")
  );

  return nodes;
}

interface Bounds {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
}

function computeBounds(points: Point2D[]): Bounds | null {
  if (points.length === 0) return null;
  const xs = points.map((p) => p.x * METER_PX);
  const ys = points.map((p) => -p.y * METER_PX);
  return { minX: Math.min(...xs), maxX: Math.max(...xs), minY: Math.min(...ys), maxY: Math.max(...ys) };
}

function centerOf(bounds: Bounds | null): Point2D {
  if (!bounds) return { x: 0, y: 0 };
  return { x: (bounds.minX + bounds.maxX) / 2, y: (bounds.minY + bounds.maxY) / 2 };
}

const STATUS_COLORS: Record<string, { fill: string; stroke: string }> = {
  ok: { fill: "rgba(74, 222, 128, 0.35)", stroke: "#22c55e" },
  warning: { fill: "rgba(250, 204, 21, 0.35)", stroke: "#eab308" },
  error: { fill: "rgba(248, 113, 113, 0.4)", stroke: "#ef4444" },
};

interface SharedLine {
  id: string;
  aptAId: string;
  aptBId: string;
  p1: Point2D;
  p2: Point2D;
  orientation: "vertical" | "horizontal";
}

function findSharedLines(apartments: any[]): SharedLine[] {
  const list: SharedLine[] = [];
  const processed = new Set<string>();

  for (let i = 0; i < apartments.length; i++) {
    for (let j = i + 1; j < apartments.length; j++) {
      const aptA = apartments[i];
      const aptB = apartments[j];
      
      const ringA = (aptA.geometry.coordinates[0] ?? []).slice(0, -1).map(([x, y]: any) => ({ x, y }));
      const ringB = (aptB.geometry.coordinates[0] ?? []).slice(0, -1).map(([x, y]: any) => ({ x, y }));

      for (let idxA = 0; idxA < ringA.length; idxA++) {
        const pA1 = ringA[idxA];
        const pA2 = ringA[(idxA + 1) % ringA.length];

        for (let idxB = 0; idxB < ringB.length; idxB++) {
          const pB1 = ringB[idxB];
          const pB2 = ringB[(idxB + 1) % ringB.length];

          const dist1 = Math.hypot(pA1.x - pB2.x, pA1.y - pB2.y) + Math.hypot(pA2.x - pB1.x, pA2.y - pB1.y);
          const dist2 = Math.hypot(pA1.x - pB1.x, pA1.y - pB1.y) + Math.hypot(pA2.x - pB2.x, pA2.y - pB2.y);
          
          if (dist1 < 0.1 || dist2 < 0.1) {
            const dx = Math.abs(pA1.x - pA2.x);
            const dy = Math.abs(pA1.y - pA2.y);
            const orientation = dx < dy ? "vertical" : "horizontal";

            const key = [aptA.id, aptB.id, pA1.x.toFixed(2), pA1.y.toFixed(2), pA2.x.toFixed(2), pA2.y.toFixed(2)].sort().join("-");
            if (!processed.has(key)) {
              processed.add(key);
              list.push({
                id: key,
                aptAId: aptA.id,
                aptBId: aptB.id,
                p1: pA1,
                p2: pA2,
                orientation,
              });
            }
          }
        }
      }
    }
  }
  return list;
}

function moveSharedLine(
  sharedLine: SharedLine,
  newValue: number,
  apartments: any[]
): any[] {
  return apartments.map((apt) => {
    if (apt.id !== sharedLine.aptAId && apt.id !== sharedLine.aptBId) {
      return apt;
    }

    const ring = (apt.geometry.coordinates[0] ?? []).slice(0, -1).map(([x, y]: any) => ({ x, y }));
    const updatedRing = ring.map((p: Point2D) => {
      if (sharedLine.orientation === "vertical") {
        const closeX = Math.abs(p.x - sharedLine.p1.x) < 0.05;
        const inY = p.y >= Math.min(sharedLine.p1.y, sharedLine.p2.y) - 0.05 && p.y <= Math.max(sharedLine.p1.y, sharedLine.p2.y) + 0.05;
        if (closeX && inY) {
          return { x: newValue, y: p.y };
        }
      } else {
        const closeY = Math.abs(p.y - sharedLine.p1.y) < 0.05;
        const inX = p.x >= Math.min(sharedLine.p1.x, sharedLine.p2.x) - 0.05 && p.x <= Math.max(sharedLine.p1.x, sharedLine.p2.x) + 0.05;
        if (closeY && inX) {
          return { x: p.x, y: newValue };
        }
      }
      return p;
    });

    const coords = updatedRing.map((p: Point2D) => [p.x, p.y]);
    coords.push([coords[0][0], coords[0][1]]);

    return {
      ...apt,
      geometry: {
        ...apt.geometry,
        coordinates: [coords],
      },
    };
  });
}

export default function CanvasEditor() {
  const { state, addDrawPoint, removeLastDrawPoint, finishDrawing, updateVertex, setFootprintPoints, selectApartment, updateApartmentsAndValidate, runReshapeCirculation, addManualCage, addManualCorridor, runMoveCage, runAddManualElement, dispatch } = useSession();
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<StageType>(null);

  const [size, setSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  
  // Stan do tooltipa
  const [hoveredFacade, setHoveredFacade] = useState<{ x: number, y: number, text: string } | null>(null);
  const [hoveredOutlineSegment, setHoveredOutlineSegment] = useState<number | null>(null);
  const [hoveredOutlineVertex, setHoveredOutlineVertex] = useState<number | null>(null);
  // Podgląd przeciąganego segmentu obrysu: delta już po constrainie
  // (Shift-rzut na normalną + snap 0.5m) — render liczy translateSegment
  // z aktualnego footprint, commit robi to samo w onDragEnd.
  const [segmentDrag, setSegmentDrag] = useState<{ index: number; delta: Delta } | null>(null);

  // Konva shape fills/strokes are literal hex props, not Tailwind classes, so
  // theme-following them needs its own small palette instead of `light:`.
  const canvasColors =
    state.theme === "light"
      ? {
          bg: "#f4f4f5",
          grid: "#c8c8cd",
          axis: "#a1a1aa",
          axisText: "#71717a",
          outline: "#18181b",
          outlineFill: "rgba(24,24,27,0.04)",
          // Ściany w pełni kryjące (user 2026-07-11: "ściany wgle nieprzezroczyste")
          wallFill: "rgb(82,82,91)",
        }
      : {
          bg: "#0c0c10",
          grid: "#3a3a42",
          axis: "#52525b",
          axisText: "#71717a",
          outline: "#ffffff",
          outlineFill: "rgba(255,255,255,0.05)",
          // Ściany w pełni kryjące (user 2026-07-11: "ściany wgle nieprzezroczyste")
          wallFill: "rgb(161,161,170)",
        };

  const footprint = state.footprint;
  const apartments = useMemo(() => state.layoutResult?.apartments ?? [], [state.layoutResult]);
  // Korytarz renderuje się w świetle ścian (net), z fallbackiem na surową
  // geometrię gdy backend nie przysłał netto (stara sesja / zbyt cienki
  // pas) -- spec 2026-07-06 corridor-net-shrink §1, ten sam wzorzec co
  // apt.net_geometry ?? apt.geometry dla mieszkań.
  const circulationParts = useMemo(() => {
    if (state.layoutResult) {
      const net = state.layoutResult.circulation_parts_net ?? [];
      return net.length > 0 ? net : state.layoutResult.circulation_parts ?? [];
    }
    if (state.circulationResult) {
      if (state.circulationResult.circulation_geometry_net) {
        return [state.circulationResult.circulation_geometry_net];
      }
      if (state.circulationResult.circulation_geometry) {
        return [state.circulationResult.circulation_geometry];
      }
    }
    return [];
  }, [state.layoutResult, state.circulationResult]);
  const cageGeometries = useMemo(() => {
    if (state.layoutResult) return state.layoutResult.cage_geometries ?? [];
    if (state.circulationResult) return state.circulationResult.cage_geometries;
    return [];
  }, [state.layoutResult, state.circulationResult]);

  const apartmentStatuses = useMemo(
    () => deriveApartmentStatuses(state.layoutResult, state.validation),
    [state.layoutResult, state.validation]
  );
  const sharedLines = useMemo(() => findSharedLines(apartments), [apartments]);

  // Segmenty obrysu jako pary punktów; segment i łączy footprint[i] z
  // footprint[(i+1) % n] — ostatni domyka wielokąt (konwencja polygonEdit.ts).
  const footprintSegments = useMemo<[Point2D, Point2D][]>(() => {
    if (!footprint || footprint.length < 2) return [];
    return footprint.map((p, i) => [p, footprint[(i + 1) % footprint.length]] as [Point2D, Point2D]);
  }, [footprint]);

  const worldToMeters = (canvasX: number, canvasY: number): Point2D => {
    const worldPxX = (canvasX - position.x) / scale;
    const worldPxY = (canvasY - position.y) / scale;
    return { x: snap(worldPxX / METER_PX), y: snap(-worldPxY / METER_PX) };
  };

  // Combined bounds (committed footprint + in-progress drawing points) — used only for
  // the manual "Fit to screen" button, which is allowed to jump the view on demand.
  const dataBounds = useMemo(() => {
    const allPoints: Point2D[] = [];
    if (footprint) allPoints.push(...footprint);
    if (state.drawingPoints.length) allPoints.push(...state.drawingPoints);
    return computeBounds(allPoints);
  }, [footprint, state.drawingPoints]);

  const boundsCenter = useMemo(() => centerOf(dataBounds), [dataBounds]);

  // The view is centered on the world origin exactly once, right after the container's
  // real size is first measured. It deliberately does NOT react to footprint/layout
  // changes afterward — auto-recentering on every edit was disorienting (it moved the
  // view out from under whatever the user was doing) and is redundant with the explicit
  // "Fit to screen" button below, which the user can invoke whenever they actually want
  // the view to jump.
  const hasCenteredRef = useRef(false);
  useEffect(() => {
    const update = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      setSize({ width, height });
      if (!hasCenteredRef.current) {
        hasCenteredRef.current = true;
        setPosition({ x: width / 2, y: height / 2 });
      }
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const onWheel = (e: KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const oldScale = scale;
    const newScale = clamp(oldScale * (e.evt.deltaY < 0 ? 1.1 : 0.9), 0.1, 20);
    const mousePointTo = { x: (pointer.x - position.x) / oldScale, y: (pointer.y - position.y) / oldScale };

    setScale(newScale);
    setPosition({ x: pointer.x - mousePointTo.x * newScale, y: pointer.y - mousePointTo.y * newScale });
  };

  const fitToScreen = () => {
    if (!dataBounds) {
      resetView();
      return;
    }
    const padding = 40;
    const availW = size.width - padding * 2;
    const availH = size.height - padding * 2;
    const boundsW = dataBounds.maxX - dataBounds.minX;
    const boundsH = dataBounds.maxY - dataBounds.minY;
    if (boundsW <= 0 || boundsH <= 0) {
      resetView();
      return;
    }
    const newScale = clamp(Math.min(availW / boundsW, availH / boundsH), 0.05, 20);
    setScale(newScale);
    setPosition({ x: size.width / 2 - boundsCenter.x * newScale, y: size.height / 2 - boundsCenter.y * newScale });
  };

  const resetView = () => {
    setScale(1);
    setPosition({ x: size.width / 2, y: size.height / 2 });
  };

  // Siatka i osie liczone względem aktualnie widocznego obszaru (position/scale/size),
  // nie stałego rozmiaru świata -- dzięki temu "ciągną się w nieskończoność" przy
  // panning/zoom zamiast kończyć się na sztywnej granicy.
  const viewBounds = useMemo(() => {
    const pad = METER_PX * 4; // margines, żeby kropki nie znikały tuż przed re-renderem
    return {
      minX: -position.x / scale - pad,
      maxX: (size.width - position.x) / scale + pad,
      minY: -position.y / scale - pad,
      maxY: (size.height - position.y) / scale + pad,
    };
  }, [position, scale, size]);

  const gridDots = useMemo(() => {
    const rangeX = viewBounds.maxX - viewBounds.minX;
    const rangeY = viewBounds.maxY - viewBounds.minY;
    // Odstęp kropek to 1m, ale przy bardzo dużym oddaleniu (mały scale) liczba
    // kropek w widoku eksploduje -- pogrubiamy siatkę (5m/10m/...) tylko wtedy,
    // żeby utrzymać rozsądną liczbę węzłów Konva do wyrenderowania.
    const levelsM = [1, 2, 5, 10, 20, 50, 100];
    let stepM = levelsM[levelsM.length - 1];
    for (const lvl of levelsM) {
      const count = (rangeX / (lvl * METER_PX)) * (rangeY / (lvl * METER_PX));
      if (count <= 4000) {
        stepM = lvl;
        break;
      }
    }
    const step = stepM * METER_PX;
    const startX = Math.floor(viewBounds.minX / step) * step;
    const startY = Math.floor(viewBounds.minY / step) * step;
    const dots: { x: number; y: number }[] = [];
    for (let x = startX; x <= viewBounds.maxX; x += step) {
      for (let y = startY; y <= viewBounds.maxY; y += step) {
        dots.push({ x, y });
      }
    }
    return dots;
  }, [viewBounds]);

  const axisExtent = Math.max(
    Math.abs(viewBounds.minX),
    Math.abs(viewBounds.maxX),
    Math.abs(viewBounds.minY),
    Math.abs(viewBounds.maxY)
  );
  const axisLines = [
    [-axisExtent, 0, axisExtent, 0],
    [0, -axisExtent, 0, axisExtent],
  ];

  const toCanvasPoints = (points: Point2D[]) => points.flatMap((p) => [p.x * METER_PX, -p.y * METER_PX]);

  const footprintCanvasPoints = footprint ? toCanvasPoints(footprint) : [];
  const drawingCanvasPoints = toCanvasPoints(state.drawingPoints);

  // (przeniesione wyżej)

  // "draw" (obrys budynku), "draw-cage" (klatka) i "draw-corridor" (korytarz)
  // dzielą ten sam mechanizm zbierania punktów w state.drawingPoints — patrz
  // handleStageClick/handleStageDblClick i podgląd łamanej niżej.
  const isDrawingMode = state.mode === "draw" || state.mode === "draw-cage" || state.mode === "draw-corridor";

  const handleStageClick = () => {
    if (!isDrawingMode) return;
    const stage = stageRef.current;
    const pointer = stage?.getPointerPosition();
    if (!pointer) return;
    const rawPx = worldToMeters(pointer.x, pointer.y);
    const px = { x: snap(rawPx.x), y: snap(rawPx.y) };

    // Ignoruj kolejne punkty z-snapowane w tym samym miejscu
    if (state.drawingPoints.length > 0) {
      const last = state.drawingPoints[state.drawingPoints.length - 1];
      if (last.x === px.x && last.y === px.y) {
         return;
      }
    }

    // Klik blisko pierwszego punktu domyka WYŁĄCZNIE obrys budynku — finishDrawing()
    // jest specyficzny dla footprint (wywołuje footprintFromPoints + SET_FOOTPRINT).
    // Klatkę/korytarz kończy tylko dblclick (handleStageDblClick niżej); korytarz
    // i tak nigdy nie jest zamkniętym poligonem, więc "domykanie po bliskości"
    // nie miałoby dla niego sensu.
    if (state.mode === "draw" && state.drawingPoints.length >= 3) {
      const p0 = state.drawingPoints[0];
      const dist = Math.hypot(p0.x - px.x, p0.y - px.y);
      if (dist < 1.5) {
        void finishDrawing();
        return;
      }
    }

    addDrawPoint(px);
  };

  const handleStageDblClick = () => {
    if (state.mode === "draw") {
      // Ponieważ kliknięcie w to samo miejsce jest odrzucane przez handleStageClick,
      // drugi klik nie stwarza zduplikowanego węzła po użyciu 'snap'. Nie usuwamy już węzłów.
      void finishDrawing();
      return;
    }
    if (state.mode === "draw-cage") {
      if (state.drawingPoints.length < 3) return; // ring potrzebuje min. 3 wierzchołków
      const ring = [...state.drawingPoints];
      // runAddManualElement dokłada TYLKO ten nowy element do aktualnie
      // wyświetlanego wyniku (auto/iteracyjny/wybrany z listy/przesunięty) bez
      // przeliczania placementu od zera — patrz jego komentarz w
      // SessionContext.tsx (fix "rysowanie klatki resetuje układ komunikacji").
      // Kolejność ma znaczenie: addManualCage() dopiero PO potwierdzeniu przez
      // backend (await) — inaczej klatka odrzucona jako 422 (np. poza obrysem)
      // zostawałaby w state.manualCages mimo że request się nie powiódł
      // (weryfikacja ręczna Etap 2 §5 pkt 5).
      void runAddManualElement("cage", ring).then((ok) => {
        if (ok) addManualCage(ring);
      });
      return;
    }
    if (state.mode === "draw-corridor") {
      if (state.drawingPoints.length < 2) return; // ścieżka potrzebuje min. 2 punktów
      const path = [...state.drawingPoints];
      void runAddManualElement("corridor", path).then((ok) => {
        if (ok) addManualCorridor(path);
      });
      return;
    }
  };

  const cursor = isDrawingMode
    ? "crosshair"
    : state.mode === "edit-vertices" || state.mode === "edit-corridor-centerline"
      ? "pointer"
      : state.mode === "edit-lines" || state.mode === "edit-circulation"
        ? "move"
        : isPanning
          ? "grabbing"
          : "grab";

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full"
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDrop={(e) => {
        e.preventDefault();
        const file = e.dataTransfer.files?.[0];
        if (!file || !file.name.toLowerCase().endsWith(".dxf")) {
          dispatch({ type: "SET_ERROR", error: "Przeciągnij poprawny plik .dxf" });
          return;
        }
        dispatch({ type: "SET_LOADING", loading: true });
        api.footprintImportDxf(file)
          .then((res) => {
            if (res.valid && res.polygon) {
              const ring = res.polygon.coordinates[0];
              const points = ring.slice(0, -1).map(([x, y]) => ({ x, y }));
              dispatch({ type: "SET_FOOTPRINT", footprint: points });
              dispatch({ type: "SET_ERROR", error: null });
            } else {
              dispatch({
                type: "SET_ERROR",
                error: "Błąd importu DXF: " + res.errors.map((err) => err.message).join(", "),
              });
            }
          })
          .catch((err) => {
            dispatch({ type: "SET_ERROR", error: "Błąd sieci: " + (err as Error).message });
          })
          .finally(() => {
            dispatch({ type: "SET_LOADING", loading: false });
          });
      }}
    >
      <div className="pointer-events-none absolute left-4 top-4 z-10 flex items-center gap-2 rounded-xl border border-zinc-800/80 bg-zinc-900/70 px-3 py-2 text-[11px] text-zinc-400 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80">
        <span className="rounded-md bg-zinc-800/80 px-1.5 py-0.5 font-mono text-zinc-300 light:bg-zinc-100 light:text-zinc-700">{scale.toFixed(2)}x</span>
        <span className="h-3 w-px bg-zinc-700 light:bg-zinc-300" />
        <span>
          {state.mode === "draw"
            ? "rysowanie · klik = punkt, dwuklik = zamknij"
            : state.mode === "draw-cage"
              ? "rysowanie klatki · klik = punkt (min. 3), dwuklik = zatwierdź"
              : state.mode === "draw-corridor"
                ? "rysowanie korytarza · klik = punkt (min. 2), dwuklik = zatwierdź"
                : state.mode === "edit-vertices"
                  ? "edycja wierzchołków obrysu"
                  : state.mode === "edit-lines"
                    ? "przeciąganie linii podziału mieszkań"
                    : state.mode === "edit-circulation"
                      ? "przeciąganie korytarza/klatki"
                      : "przesuń: drag · zoom: kółko"}
        </span>
      </div>

      <div className="absolute right-4 top-4 z-10 flex gap-1.5 rounded-xl border border-zinc-800/80 bg-zinc-900/70 p-1.5 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80">
        <button
          onClick={fitToScreen}
          title="Fit to screen"
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800 light:text-zinc-700 light:hover:bg-zinc-100"
        >
          <Maximize2 size={13} />
          Fit
        </button>
        <button
          onClick={resetView}
          title="Reset"
          className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800 light:text-zinc-700 light:hover:bg-zinc-100"
        >
          <RotateCcw size={13} />
          Reset
        </button>
      </div>

      <Stage
        ref={stageRef}
        width={size.width}
        height={size.height}
        scaleX={scale}
        scaleY={scale}
        x={position.x}
        y={position.y}
        draggable={!isDrawingMode}
        onWheel={onWheel}
        onClick={handleStageClick}
        onDblClick={handleStageDblClick}
        onDragStart={() => setIsPanning(true)}
        onDragEnd={(e) => {
          setIsPanning(false);
          setPosition({ x: e.target.x(), y: e.target.y() });
        }}
        style={{ cursor }}
      >
        <Layer>
          <Rect
            x={viewBounds.minX}
            y={viewBounds.minY}
            width={viewBounds.maxX - viewBounds.minX}
            height={viewBounds.maxY - viewBounds.minY}
            fill={canvasColors.bg}
          />
        </Layer>

        <Layer listening={false}>
          {gridDots.map((d, i) => (
            <Circle key={`gd-${i}`} x={d.x} y={d.y} radius={1.2 / scale} fill={canvasColors.grid} />
          ))}
        </Layer>

        <Layer>
          {axisLines.map((points, i) => (
            <Line key={`a-${i}`} points={points} stroke={canvasColors.axis} strokeWidth={1.5 / scale} />
          ))}
          <Text x={8 / scale} y={4 / scale} text="0,0" fontSize={12 / scale} fill={canvasColors.axisText} />
        </Layer>

        <Layer>
          {/* Obrys */}
          {footprintCanvasPoints.length > 0 && (
            <Line
              points={footprintCanvasPoints}
              closed
              stroke={canvasColors.outline}
              strokeWidth={2 / scale}
              fill={apartments.length === 0 ? canvasColors.outlineFill : undefined}
            />
          )}

          {/* Podświetlenie ściany obrysu pod myszą (tryb edycji) */}
          {state.mode === "edit-vertices" &&
            hoveredOutlineSegment !== null &&
            footprintSegments[hoveredOutlineSegment] && (
              <Line
                points={toCanvasPoints([...footprintSegments[hoveredOutlineSegment]])}
                stroke="#60a5fa"
                strokeWidth={4 / scale}
                listening={false}
              />
            )}

          {/* Podgląd obrysu podczas draga ściany (dashed, jak rysowanie) */}
          {state.mode === "edit-vertices" &&
            segmentDrag &&
            footprint &&
            (() => {
              const preview = translateSegment(footprint, segmentDrag.index, segmentDrag.delta);
              if (!preview) return null;
              return (
                <Line
                  points={toCanvasPoints(preview)}
                  closed
                  stroke="#60a5fa"
                  strokeWidth={2 / scale}
                  dash={[6 / scale, 4 / scale]}
                  listening={false}
                />
              );
            })()}

          {/* Niewidoczne hitboxy segmentów obrysu: hover (Task 4),
              dblclick-wstaw (Task 5), drag ściany (Task 6) */}
          {state.mode === "edit-vertices" &&
            footprintSegments.map(([a, b], i) => (
              <Line
                key={`outline-hit-${i}`}
                points={toCanvasPoints([a, b])}
                stroke="#000000"
                opacity={0}
                strokeWidth={2 / scale}
                hitStrokeWidth={14 / scale}
                draggable
                onMouseEnter={() => setHoveredOutlineSegment(i)}
                onMouseLeave={() => setHoveredOutlineSegment(null)}
                onDblClick={(e) => {
                  e.cancelBubble = true;
                  if (!footprint) return;
                  const stage = stageRef.current;
                  const pointer = stage?.getPointerPosition();
                  if (!pointer) return;
                  const clicked = worldToMeters(pointer.x, pointer.y);
                  const next = insertVertexAt(footprint, i, clicked);
                  if (next) setFootprintPoints(next);
                }}
                onDragStart={(e) => {
                  e.cancelBubble = true;
                }}
                onDragMove={(e) => {
                  const node = e.target;
                  const [a, b] = footprintSegments[i];
                  // node.x/y to translacja w px świata (Stage skaluje potomków)
                  const raw: Delta = { dx: node.x() / METER_PX, dy: -node.y() / METER_PX };
                  const d = constrainSegmentDelta(a, b, raw, e.evt.shiftKey);
                  setSegmentDrag({ index: i, delta: d });
                }}
                onDragEnd={(e) => {
                  // cancelBubble: patrz komentarz przy onDragEnd wierzchołków —
                  // bez tego Stage czyta surowe współrzędne node'a i „odlatuje".
                  e.cancelBubble = true;
                  const node = e.target;
                  const [a, b] = footprintSegments[i];
                  const raw: Delta = { dx: node.x() / METER_PX, dy: -node.y() / METER_PX };
                  node.position({ x: 0, y: 0 });
                  setSegmentDrag(null);
                  if (!footprint) return;
                  const d = constrainSegmentDelta(a, b, raw, e.evt.shiftKey);
                  const next = translateSegment(footprint, i, d);
                  if (next) setFootprintPoints(next);
                }}
              />
            ))}

          {/* Ściany -- pasy zewn./wewn., spec 2026-07-04 wall-thickness.
              <Path fillRule="evenodd"> (not <Line>): the exterior band is an
              annulus (has a hole) by construction -- see geomToSvgPath's
              docstring above. */}
          {(state.layoutResult?.wall_bands ?? []).map((geom, i) => (
            <Path
              key={`wall-${i}`}
              data={geomToSvgPath(geom)}
              fillRule="evenodd"
              fill={canvasColors.wallFill}
              listening={false}
            />
          ))}

          {/* Rysowanie w toku */}

          {drawingCanvasPoints.length > 0 && (
            <Line
              points={drawingCanvasPoints}
              closed={state.mode !== "draw-corridor" && state.drawingPoints.length >= 3}
              stroke="#60a5fa"
              strokeWidth={2 / scale}
              dash={[6 / scale, 4 / scale]}
            />
          )}
          {state.drawingPoints.map((p, i) => (
            <Circle key={`draw-pt-${i}`} x={p.x * METER_PX} y={-p.y * METER_PX} radius={4 / scale} fill="#60a5fa" />
          ))}

          {/* Podgląd pasa korytarza przy rysowaniu osi (draw-corridor) */}
          {state.mode === "draw-corridor" && drawingCanvasPoints.length >= 4 && (
            <Line
              points={drawingCanvasPoints}
              stroke="#60a5fa"
              opacity={0.25}
              strokeWidth={(state.circulation.corridor_width_m + 0.2) * METER_PX}
              lineCap="butt"
              lineJoin="round"
              listening={false}
            />
          )}

          {/* Korytarz (jasnoszary) */}
          {circulationParts.map((geom, i) => (
            <Line
              key={`corridor-${i}`}
              points={toCanvasPoints(ringToPoints(geom))}
              closed
              fill="rgba(211,211,211,0.5)"
              stroke="#999999"
              strokeWidth={1 / scale}
            />
          ))}

          {/* Klatka (szary) */}
          {cageGeometries.map((geom, i) => (
            <Line
              key={`cage-${i}`}
              points={toCanvasPoints(ringToPoints(geom))}
              closed
              fill="rgba(128,128,128,0.7)"
              stroke="#4a4a4a"
              strokeWidth={1.5 / scale}
            />
          ))}

          {/* Highlight elementu manualnego wskazanego w liście panelu (Task 4) */}
          {state.hoveredManualId &&
            state.manualCages
              .filter((c) => c.id === state.hoveredManualId)
              .map((c) => (
                <Line
                  key={`manual-hl-${c.id}`}
                  points={toCanvasPoints(c.ring)}
                  closed
                  stroke="#60a5fa"
                  strokeWidth={3 / scale}
                  listening={false}
                />
              ))}
          {state.hoveredManualId &&
            state.manualCorridors
              .filter((c) => c.id === state.hoveredManualId)
              .map((c) => (
                <Line
                  key={`manual-hl-${c.id}`}
                  points={toCanvasPoints(c.path)}
                  stroke="#60a5fa"
                  strokeWidth={4 / scale}
                  listening={false}
                />
              ))}

          {/* Podział klatki: biegi/spoczniki/winda/szacht (dekoracja, spec 2026-07-03) */}
          {cageGeometries.flatMap((geom, i) =>
            cageSubdivisionShapes(geom, `cage-sub-${i}`, scale, canvasColors.axis, canvasColors.axisText)
          )}

          {/* Linia środkowa korytarza — kolor wg progu odległości do klatki (F2-04-bis) */}
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke="#60a5fa"
              strokeWidth={3 / scale}
              listening={state.mode === "edit-corridor-centerline"}
              onDblClick={(e) => {
                if (state.mode !== "edit-corridor-centerline" || !state.circulationResult) return;
                e.cancelBubble = true;
                const stage = stageRef.current;
                const pointer = stage?.getPointerPosition();
                if (!pointer) return;
                const clicked = worldToMeters(pointer.x, pointer.y);
                const flat = flattenCenterline(state.circulationResult.centerline);
                // Insert the new point between this segment's two endpoints
                // (index i in the flat path, since flat[i]/flat[i+1] are
                // exactly seg.points[0]/seg.points[1] by construction).
                const newFlat = [...flat.slice(0, i + 1), clicked, ...flat.slice(i + 1)];
                void runReshapeCirculation(segmentsFromFlatPath(newFlat));
              }}
            />
          ))}

          {/* Wierzchołki linii korytarza — edytowalne (F2-04-bis) */}
          {state.mode === "edit-corridor-centerline" &&
            state.circulationResult?.centerline &&
            (() => {
              // Flatten segment endpoints into a de-duplicated vertex list so shared
              // endpoints between adjacent segments render (and drag) as one point.
              const verts: { x: number; y: number }[] = [];
              for (const seg of state.circulationResult.centerline) {
                for (const [x, y] of seg.points) {
                  if (!verts.some((v) => Math.abs(v.x - x) < 1e-6 && Math.abs(v.y - y) < 1e-6)) {
                    verts.push({ x, y });
                  }
                }
              }
              return verts.map((v, i) => (
                <Circle
                  key={`centerline-vertex-${i}`}
                  x={v.x * METER_PX}
                  y={-v.y * METER_PX}
                  radius={6 / scale}
                  fill="#ffffff"
                  stroke="#22c55e"
                  strokeWidth={2 / scale}
                  draggable
                  onDblClick={(e) => {
                    e.cancelBubble = true;
                    if (!state.circulationResult) return;
                    const flat = flattenCenterline(state.circulationResult.centerline);
                    // Guard: 2 points = 1 segment = the minimum viable
                    // centerline. Removing one would leave 0 or 1 points and
                    // no geometry -- no-op instead (spec §4.1).
                    if (flat.length <= 2) return;
                    const idx = flat.findIndex(
                      (p) => Math.abs(p.x - v.x) < 1e-6 && Math.abs(p.y - v.y) < 1e-6
                    );
                    if (idx === -1) return;
                    const newFlat = [...flat.slice(0, idx), ...flat.slice(idx + 1)];
                    void runReshapeCirculation(segmentsFromFlatPath(newFlat));
                  }}
                  onDragStart={(e) => {
                    e.cancelBubble = true;
                  }}
                  onDragMove={(e) => {
                    const node = e.target;
                    const snapped = worldToMeters(
                      node.x() * scale + position.x,
                      node.y() * scale + position.y
                    );
                    node.x(snapped.x * METER_PX);
                    node.y(-snapped.y * METER_PX);
                  }}
                  onDragEnd={(e) => {
                    // Same Konva bubbling issue as every other draggable node in this
                    // Stage (footprint vertices, shared lines, edit-circulation Group)
                    // — without cancelBubble the Stage's own onDragEnd reads this
                    // node's raw coordinates and snaps the whole pannable view.
                    e.cancelBubble = true;
                    const snapped = worldToMeters(
                      e.target.x() * scale + position.x,
                      e.target.y() * scale + position.y
                    );
                    const movedFrom = v;
                    const newSegments: [Point2D, Point2D][] = state.circulationResult!.centerline.map((seg) => {
                      const [p1, p2] = seg.points;
                      const newP1 =
                        Math.abs(p1[0] - movedFrom.x) < 1e-6 && Math.abs(p1[1] - movedFrom.y) < 1e-6
                          ? { x: snapped.x, y: snapped.y }
                          : { x: p1[0], y: p1[1] };
                      const newP2 =
                        Math.abs(p2[0] - movedFrom.x) < 1e-6 && Math.abs(p2[1] - movedFrom.y) < 1e-6
                          ? { x: snapped.x, y: snapped.y }
                          : { x: p2[0], y: p2[1] };
                      return [newP1, newP2];
                    });
                    void runReshapeCirculation(newSegments);
                  }}
                />
              ));
            })()}

          {/* Kropki ewakuacyjne co 1m (spec 2026-07-04-evacuation-dots §4).
              Zawsze widoczne gdy są w wyniku -- informacja projektowa, nie
              narzędzie edycji; listening=false, żeby nie łapały myszy. */}
          {(() => {
            const dots =
              state.circulationResult?.evacuation_dots ??
              state.layoutResult?.evacuation_dots ??
              [];
            const fill = { green: "#22c55e", gray: "#9ca3af", red: "#ef4444" } as const;
            return dots.map((d, i) => (
              <Circle
                key={`evac-dot-${i}`}
                x={d.x * METER_PX}
                y={-d.y * METER_PX}
                radius={3 / scale}
                fill={fill[d.status]}
                listening={false}
              />
            ));
          })()}

          {/* Przesuwanie CAŁEJ komunikacji jako sztywnej bryły (edit-circulation) */}
          {state.mode === "edit-circulation" && state.circulationResult && (
            <Group
              draggable
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragMove={(e) => {
                snapNodeToGrid(e.target);
              }}
              onDragEnd={(e) => {
                // See the edit-lines Group's onDragEnd above — same Konva
                // event-bubbling issue: without cancelBubble, the Stage's own
                // onDragEnd fires afterward with the already-reset (0,0)
                // position and snaps the whole pannable view to the origin.
                e.cancelBubble = true;
                const node = e.target;
                // Zaokrąglenie do kroku snapu ucina szum float po onDragMove.
                const dxM = Math.round(node.x() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                const dyM = -Math.round(node.y() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                node.position({ x: 0, y: 0 });
                dispatch({ type: "TRANSLATE_CIRCULATION", dx: dxM, dy: dyM });
              }}
            >
              {circulationParts.map((geom, i) => (
                <Line
                  key={`edit-corridor-${i}`}
                  points={toCanvasPoints(ringToPoints(geom))}
                  closed
                  fill="rgba(211,211,211,0.5)"
                  stroke="#60a5fa"
                  strokeWidth={2 / scale}
                />
              ))}
            </Group>
          )}
          {/* Przesuwanie KAŻDEJ klatki osobno (spec 2026-07-05 §2) */}
          {state.mode === "edit-circulation" && state.circulationResult && cageGeometries.map((geom, i) => (
            <Group
              key={`edit-cage-group-${i}`}
              draggable
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragMove={(e) => {
                snapNodeToGrid(e.target);
              }}
              onDragEnd={(e) => {
                e.cancelBubble = true;
                const node = e.target;
                const dxM = Math.round(node.x() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                const dyM = -Math.round(node.y() / METER_PX / CIRCULATION_SNAP_M) * CIRCULATION_SNAP_M;
                node.position({ x: 0, y: 0 });
                void runMoveCage(i, dxM, dyM);
              }}
            >
              <Line
                points={toCanvasPoints(ringToPoints(geom))}
                closed
                fill="rgba(128,128,128,0.7)"
                stroke="#60a5fa"
                strokeWidth={2 / scale}
              />
              {cageSubdivisionShapes(geom, `edit-cage-sub-${i}`, scale, canvasColors.axis, canvasColors.axisText)}
            </Group>
          ))}

          {/* Mieszkania — wypełnienie wg TYPU (spec 2026-07-06 §2.3),
              obramowanie wg statusu walidacji, geometria NETTO (§3.2). */}
          {apartments.map((apt) => {
            // W trybie Słońce (state.solarResult) fill/stroke zostają wg
            // logiki słonecznej; kolor per typ tylko w widoku domyślnym
            // (spec §2.3 "Decyzja: tryb Słońce"). Zmiana geometrii na netto
            // (niżej) obowiązuje w OBU widokach -- usterka §B jest
            // geometryczna, nie zależy od trybu koloru.
            let fill: string;
            let stroke: string;
            const hasSolarData = !!state.solarResult;
            if (hasSolarData) {
              const solFa = state.solarResult!.facades.filter(f => f.apartment_id === apt.id);
              if (solFa.length > 0) {
                const isPassing = solFa.some(f => f.meets_wt);
                fill = isPassing ? "rgba(249, 115, 22, 0.3)" : "rgba(75, 85, 99, 0.3)";
                stroke = isPassing ? "#f97316" : "#4b5563";
              } else {
                fill = "rgba(255,255,255,0.1)";
                stroke = "#666";
              }
            } else {
              const status = apartmentStatuses.get(apt.id) ?? "ok";
              stroke = STATUS_COLORS[status].stroke;
              const hex = state.typeColors?.[apt.type] ?? DEFAULT_TYPE_COLORS[apt.type] ?? "#9ca3af";
              // ~20% przezroczystości (user 2026-07-11), reszta pełne wypełnienie
              fill = hexToRgba(hex, 0.8);
            }

            const isSelected = state.selectedApartmentId === apt.id;
            // Geometria NETTO (w świetle ścian) -- strefa kończy się na licu
            // ściany, nie na osi (spec 2026-07-06 §3.2). Fallback do surowej,
            // gdy backend nie przysłał netto (stara sesja / komórka zbyt mała).
            const ring = ringToPoints(apt.net_geometry ?? apt.geometry);
            const pts = toCanvasPoints(ring);
            // Divide by ring.length (the true vertex count), NOT
            // apt.geometry.coordinates[0].length -- the latter includes
            // GeoJSON's closing duplicate vertex (N+1 points for an N-vertex
            // polygon), which was silently pulling `center` ~1/(N+1) of the
            // way toward the world origin (e.g. 20% for a rectangle). Found
            // during Task 5 QA: it visibly displaced the new net-area label
            // (below) off of far-from-origin apartments and into whatever
            // neighboring zone sat between them and (0,0).
            const center = ring.reduce(
              (acc, p) => ({ x: acc.x + p.x / ring.length, y: acc.y + p.y / ring.length }),
              { x: 0, y: 0 }
            );
            return (
              <Group key={apt.id}>
                <Line
                  points={pts}
                  closed
                  fill={fill}
                  stroke={isSelected ? "#3b82f6" : stroke}
                  strokeWidth={(isSelected ? 3 : 1.5) / scale}
                  onClick={(e) => {
                    e.cancelBubble = true;
                    selectApartment(isSelected ? null : apt.id);
                  }}
                  onMouseEnter={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = "pointer";
                  }}
                  onMouseLeave={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = cursor;
                  }}
                  data-center-x={center.x}
                  data-center-y={center.y}
                />
                {isSelected && apt.net_area_m2 > 0 && (
                  <Text
                    x={center.x * METER_PX}
                    y={-center.y * METER_PX}
                    text={`${apt.net_area_m2.toFixed(1)} m² netto`}
                    fontSize={11 / scale}
                    fill="#ffffff"
                    fontStyle="bold"
                    shadowColor="#000000"
                    shadowBlur={4}
                    listening={false}
                    offsetX={30 / scale}
                  />
                )}
              </Group>
            );
          })}

          {/* Etykiety mieszkań: ID, typ, m² (F2-12) */}
          {apartments.map((apt) => {
            const ring = ringToPoints(apt.geometry);
            const xs = ring.map((p) => p.x * METER_PX);
            const ys = ring.map((p) => -p.y * METER_PX);
            const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
            const cy = (Math.min(...ys) + Math.max(...ys)) / 2;
            const hasSolarData = !!state.solarResult;
            let labelText = `${apt.type}\n${apt.area_m2.toFixed(1)} m²`;
            if (hasSolarData) {
              const maxHours = Math.max(...state.solarResult!.facades.filter(f => f.apartment_id === apt.id).map(f => f.hours_total), 0);
              labelText = `${apt.type}\nSłońce: ${maxHours.toFixed(1)}h`;
            }

            return (
              <Text
                key={`label-${apt.id}`}
                x={cx}
                y={cy - 12 / scale}
                text={labelText}
                align="center"
                fontSize={10 / scale}
                fill="#111827"
                listening={false}
                offsetX={20}
              />
            );
          })}

          {/* Krawędzie zewnętrzne ze słońcem — rysowane bezpośrednio z facade.edge
              (backend już wybrał właściwy, wyłącznie zewnętrzny odcinek ściany;
              nie zgadujemy go tu ponownie po azymucie, bo poligon mieszkania
              często ma nadmiarowy współliniowy wierzchołek na tej samej ścianie
              — dopasowanie po samym azymucie kolorowało wtedy też odcinek
              wewnętrzny o tym samym kierunku, patrz test_solar.py regression). */}
          {!!state.solarResult && state.solarResult.facades.map((facade, i) => {
            const x1 = facade.edge[0][0] * METER_PX;
            const y1 = -facade.edge[0][1] * METER_PX;
            const x2 = facade.edge[1][0] * METER_PX;
            const y2 = -facade.edge[1][1] * METER_PX;
            const ratio = Math.min(1, Math.max(0, facade.hours_total / facade.required_hours));
            const hue = Math.floor(ratio * 120);
            const strokeColor = `hsl(${hue}, 80%, 45%)`;
            const cx = ((facade.edge[0][0] + facade.edge[1][0]) / 2) * METER_PX;
            const cy = -((facade.edge[0][1] + facade.edge[1][1]) / 2) * METER_PX;

            return (
              <Group key={`facade-${facade.apartment_id}-${i}`}>
                <Line
                  points={[x1, y1, x2, y2]}
                  stroke={strokeColor}
                  strokeWidth={6 / scale}
                  onMouseEnter={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = "help";
                    const tooltipText = `Orientacja: ${facade.orientation}\nDługość: ${facade.length_m.toFixed(1)}m\nSłońce: ${facade.hours_total.toFixed(1)}h\nWT: ${facade.meets_wt ? 'OK' : 'Brak'}`;
                    const stage = e.target.getStage();
                    const pointer = stage?.getPointerPosition();
                    if (pointer) {
                      setHoveredFacade({ x: (pointer.x - position.x) / scale, y: (pointer.y - position.y) / scale, text: tooltipText });
                    }
                  }}
                  onMouseMove={(e) => {
                    const stage = e.target.getStage();
                    const pointer = stage?.getPointerPosition();
                    if (pointer) {
                      const tooltipText = `Orientacja: ${facade.orientation}\nDługość: ${facade.length_m.toFixed(1)}m\nSłońce: ${facade.hours_total.toFixed(1)}h\nWT: ${facade.meets_wt ? 'OK' : 'Brak'}`;
                      setHoveredFacade({ x: (pointer.x - position.x) / scale, y: (pointer.y - position.y) / scale, text: tooltipText });
                    }
                  }}
                  onMouseLeave={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = cursor;
                    setHoveredFacade(null);
                  }}
                />
                <Text
                  x={cx}
                  y={cy}
                  text={`${facade.hours_total.toFixed(1)}h`}
                  fontSize={12 / scale}
                  fill="#ffffff"
                  fontStyle="bold"
                  shadowColor="#000000"
                  shadowBlur={4}
                  shadowOffsetX={1/scale}
                  shadowOffsetY={1/scale}
                  listening={false}
                  offsetX={6/scale}
                  offsetY={6/scale}
                />
              </Group>
            );
          })}

          {/* Współdzielone linie podziału mieszkań — draggable (F2-08) */}
          {state.mode === "edit-lines" &&
            sharedLines.map((line) => {
              const x1 = line.p1.x * METER_PX;
              const y1 = -line.p1.y * METER_PX;
              const x2 = line.p2.x * METER_PX;
              const y2 = -line.p2.y * METER_PX;
              return (
                <Line
                  key={line.id}
                  points={[x1, y1, x2, y2]}
                  stroke="#60a5fa"
                  strokeWidth={6 / scale}
                  hitStrokeWidth={20}
                  opacity={0.8}
                  draggable
                  onDragStart={(e) => {
                    e.cancelBubble = true;
                  }}
                  onMouseEnter={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = line.orientation === "vertical" ? "ew-resize" : "ns-resize";
                  }}
                  onMouseLeave={(e) => {
                    const container = e.target.getStage()?.container();
                    if (container) container.style.cursor = cursor;
                  }}
                  onDragMove={(e) => {
                    const node = e.target;
                    if (line.orientation === "vertical") {
                      node.y(0);
                      const deltaX = node.x() / METER_PX;
                      const newValue = snap(line.p1.x + deltaX);
                      const updated = moveSharedLine(line, newValue, apartments);
                      dispatch({ type: "UPDATE_APARTMENTS", apartments: updated });
                    } else {
                      node.x(0);
                      const deltaY = -node.y() / METER_PX;
                      const newValue = snap(line.p1.y + deltaY);
                      const updated = moveSharedLine(line, newValue, apartments);
                      dispatch({ type: "UPDATE_APARTMENTS", apartments: updated });
                    }
                  }}
                  onDragEnd={(e) => {
                    // See the edit-circulation Group's onDragEnd for why this
                    // matters: without cancelBubble, this dragend bubbles up
                    // to the Stage and snaps the whole pannable view.
                    e.cancelBubble = true;
                    const node = e.target;
                    let newValue = 0;
                    if (line.orientation === "vertical") {
                      const deltaX = node.x() / METER_PX;
                      newValue = snap(line.p1.x + deltaX);
                      node.x(0);
                    } else {
                      const deltaY = -node.y() / METER_PX;
                      newValue = snap(line.p1.y + deltaY);
                      node.y(0);
                    }
                    const updated = moveSharedLine(line, newValue, apartments);
                    void updateApartmentsAndValidate(updated);
                  }}
                />
              );
            })}

          {/* Wierzchołki obrysu — edytowalne (F1-06) */}
          {state.mode === "edit-vertices" &&
            footprint?.map((p, i) => (
              <Circle
                key={`vertex-${i}`}
                x={p.x * METER_PX}
                y={-p.y * METER_PX}
                radius={(hoveredOutlineVertex === i ? 9 : 6) / scale}
                fill={hoveredOutlineVertex === i ? "#60a5fa" : "#ffffff"}
                stroke="#2563eb"
                strokeWidth={2 / scale}
                draggable
                onMouseEnter={() => setHoveredOutlineVertex(i)}
                onMouseLeave={() => setHoveredOutlineVertex(null)}
                onDragStart={(e) => {
                  e.cancelBubble = true;
                }}
                onDragMove={(e) => {
                  const node = e.target;
                  const snapped = worldToMeters(
                    node.x() * scale + position.x,
                    node.y() * scale + position.y
                  );
                  node.x(snapped.x * METER_PX);
                  node.y(-snapped.y * METER_PX);
                }}
                onDragEnd={(e) => {
                  // Same Konva bubbling issue as the other draggable nodes in
                  // this Stage: without this, dragging a footprint vertex
                  // bubbles dragend to the Stage's own onDragEnd, which reads
                  // e.target.x()/y() — the VERTEX's raw screen coordinates,
                  // not the Stage's — and snaps the whole pannable view
                  // there. This was likely the dominant cause of the reported
                  // "wyśrodkowanie" complaint, since vertex-dragging is the
                  // most common canvas interaction.
                  e.cancelBubble = true;
                  const snapped = worldToMeters(
                    e.target.x() * scale + position.x,
                    e.target.y() * scale + position.y
                  );
                  updateVertex(i, snapped);
                }}
                onDblClick={(e) => {
                  e.cancelBubble = true;
                  if (!footprint) return;
                  const next = removeVertexAt(footprint, i);
                  if (next) setFootprintPoints(next);
                }}
              />
            ))}

          {/* Tooltip Render */}
          {hoveredFacade && (
            <Group x={hoveredFacade.x + 10 / scale} y={hoveredFacade.y + 10 / scale}>
              <Rect
                width={120 / scale}
                height={60 / scale}
                fill="rgba(0,0,0,0.8)"
                cornerRadius={4 / scale}
              />
              <Text
                text={hoveredFacade.text}
                fill="#fff"
                fontSize={10 / scale}
                padding={6 / scale}
              />
            </Group>
          )}
        </Layer>
      </Stage>
    </div>
  );
}
