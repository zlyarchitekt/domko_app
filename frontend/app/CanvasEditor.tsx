"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Line, Rect, Text, Circle, Group } from "react-konva";
import type { KonvaEventObject } from "konva/lib/Node";
import { Stage as StageType } from "konva/lib/Stage";
import { Maximize2, RotateCcw } from "lucide-react";
import { useSession, Point2D } from "./state/SessionContext";
import { deriveApartmentStatuses } from "./lib/deriveStatus";
import { GeoJsonPolygon } from "./lib/api";
import * as api from "./lib/api";
const METER_PX = 50; // base scale: 1m = 50px
const SNAP_M = 0.5; // snap do siatki co 0.5m (rysowanie, wierzchołki, linie podziału)

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

function snap(value: number): number {
  return Math.round(value / SNAP_M) * SNAP_M;
}

function ringToPoints(geom: GeoJsonPolygon): Point2D[] {
  const ring = geom.coordinates[0] ?? [];
  return ring.slice(0, -1).map(([x, y]) => ({ x, y }));
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
  const { state, addDrawPoint, removeLastDrawPoint, finishDrawing, updateVertex, selectApartment, updateApartmentsAndValidate, runReshapeCirculation, dispatch } = useSession();
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<StageType>(null);

  const [size, setSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  
  // Stan do tooltipa
  const [hoveredFacade, setHoveredFacade] = useState<{ x: number, y: number, text: string } | null>(null);

  // Konva shape fills/strokes are literal hex props, not Tailwind classes, so
  // theme-following them needs its own small palette instead of `light:`.
  const canvasColors =
    state.theme === "light"
      ? {
          bg: "#f4f4f5",
          grid: "#e4e4e7",
          axis: "#a1a1aa",
          axisText: "#71717a",
          outline: "#18181b",
          outlineFill: "rgba(24,24,27,0.04)",
        }
      : {
          bg: "#0c0c10",
          grid: "#232329",
          axis: "#52525b",
          axisText: "#71717a",
          outline: "#ffffff",
          outlineFill: "rgba(255,255,255,0.05)",
        };

  const footprint = state.footprint;
  const apartments = useMemo(() => state.layoutResult?.apartments ?? [], [state.layoutResult]);
  const circulationParts = useMemo(() => {
    if (state.layoutResult) return state.layoutResult.circulation_parts ?? [];
    if (state.circulationResult?.circulation_geometry) return [state.circulationResult.circulation_geometry];
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

  const worldSize = 2000;
  const gridLines = useMemo(() => {
    const lines: number[][] = [];
    const step = METER_PX;
    const half = worldSize / 2;
    for (let i = -half; i <= half; i += step) {
      lines.push([-half, i, half, i]);
      lines.push([i, -half, i, half]);
    }
    return lines;
  }, []);

  const axisLines = [
    [-worldSize / 2, 0, worldSize / 2, 0],
    [0, -worldSize / 2, 0, worldSize / 2],
  ];

  const toCanvasPoints = (points: Point2D[]) => points.flatMap((p) => [p.x * METER_PX, -p.y * METER_PX]);

  const footprintCanvasPoints = footprint ? toCanvasPoints(footprint) : [];
  const drawingCanvasPoints = toCanvasPoints(state.drawingPoints);

  // (przeniesione wyżej)

  const handleStageClick = () => {
    if (state.mode !== "draw") return;
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

    if (state.drawingPoints.length >= 3) {
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
    if (state.mode !== "draw") return;
    // Ponieważ kliknięcie w to samo miejsce jest odrzucane przez handleStageClick, 
    // drugi klik nie stwarza zduplikowanego węzła po użyciu 'snap'. Nie usuwamy już węzłów.
    void finishDrawing();
  };

  const cursor =
    state.mode === "draw"
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
        draggable={state.mode !== "draw"}
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
          <Rect x={-worldSize / 2} y={-worldSize / 2} width={worldSize} height={worldSize} fill={canvasColors.bg} />
        </Layer>

        <Layer>
          {gridLines.map((points, i) => (
            <Line key={`g-${i}`} points={points} stroke={canvasColors.grid} strokeWidth={1 / scale} />
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

          {/* Rysowanie w toku */}

          {drawingCanvasPoints.length > 0 && (
            <Line 
              points={drawingCanvasPoints} 
              closed={state.drawingPoints.length >= 3} 
              stroke="#60a5fa" 
              strokeWidth={2 / scale} 
              dash={[6 / scale, 4 / scale]} 
            />
          )}
          {state.drawingPoints.map((p, i) => (
            <Circle key={`draw-pt-${i}`} x={p.x * METER_PX} y={-p.y * METER_PX} radius={4 / scale} fill="#60a5fa" />
          ))}

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

          {/* Linia środkowa korytarza — kolor wg progu odległości do klatki (F2-04-bis) */}
          {state.circulationResult?.centerline?.map((seg, i) => (
            <Line
              key={`centerline-${i}`}
              points={toCanvasPoints(seg.points.map(([x, y]) => ({ x, y })))}
              stroke={seg.exceeds_max ? "#ef4444" : "#22c55e"}
              strokeWidth={3 / scale}
              listening={false}
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

          {/* Przesuwanie korytarza/klatki jako sztywnej bryły (edit-circulation) */}
          {state.mode === "edit-circulation" && state.circulationResult && (
            <Group
              draggable
              onDragStart={(e) => {
                e.cancelBubble = true;
              }}
              onDragEnd={(e) => {
                // See the edit-lines Group's onDragEnd above — same Konva
                // event-bubbling issue: without cancelBubble, the Stage's own
                // onDragEnd fires afterward with the already-reset (0,0)
                // position and snaps the whole pannable view to the origin.
                e.cancelBubble = true;
                const node = e.target;
                const dxM = node.x() / METER_PX;
                const dyM = -node.y() / METER_PX;
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
              {cageGeometries.map((geom, i) => (
                <Line
                  key={`edit-cage-${i}`}
                  points={toCanvasPoints(ringToPoints(geom))}
                  closed
                  fill="rgba(128,128,128,0.7)"
                  stroke="#60a5fa"
                  strokeWidth={2 / scale}
                />
              ))}
            </Group>
          )}

          {/* Mieszkania — kolor wg statusu walidacji (F3-06) lub Solara (F4) */}
          {apartments.map((apt) => {
            let colors;
            const hasSolarData = !!state.solarResult;
            if (hasSolarData) {
              const solFa = state.solarResult!.facades.filter(f => f.apartment_id === apt.id);
              if (solFa.length > 0) {
                const isPassing = solFa.some(f => f.meets_wt);
                colors = isPassing ? { fill: "rgba(249, 115, 22, 0.3)", stroke: "#f97316" } : { fill: "rgba(75, 85, 99, 0.3)", stroke: "#4b5563" };
              } else {
                colors = { fill: "rgba(255,255,255,0.1)", stroke: "#666" };
              }
            } else {
              const status = apartmentStatuses.get(apt.id) ?? "ok";
              colors = STATUS_COLORS[status];
            }
            
            const isSelected = state.selectedApartmentId === apt.id;
            const pts = toCanvasPoints(ringToPoints(apt.geometry));
            const center = ringToPoints(apt.geometry).reduce(
              (acc, p) => ({ x: acc.x + p.x / apt.geometry.coordinates[0].length, y: acc.y + p.y / apt.geometry.coordinates[0].length }),
              { x: 0, y: 0 }
            );
            return (
              <Line
                key={apt.id}
                points={pts}
                closed
                fill={colors.fill}
                stroke={isSelected ? "#3b82f6" : colors.stroke}
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
                radius={6 / scale}
                fill="#ffffff"
                stroke="#2563eb"
                strokeWidth={2 / scale}
                draggable
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
