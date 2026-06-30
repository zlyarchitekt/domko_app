"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Stage, Layer, Line, Rect, Text } from "react-konva";
import { Stage as StageType } from "konva/lib/Stage";
import { BSP_COLORS, BspResult, getApartmentFill, getApartmentStroke } from "./bsp/types";

const METER_PX = 50; // base scale: 1m = 50px

function clamp(n: number, min: number, max: number) {
  return Math.max(min, Math.min(max, n));
}

interface CanvasEditorProps {
  bspResult?: BspResult;
}

export default function CanvasEditor({ bspResult }: CanvasEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<StageType>(null);

  const [size, setSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);

  // Set initial position to center of a 20x20m drawing area.
  const drawingAreaMeters = { width: 20, height: 20 };
  const originPx = {
    x: drawingAreaMeters.width * METER_PX,
    y: drawingAreaMeters.height * METER_PX,
  };

  const footprint = bspResult?.footprint;
  const areas = bspResult?.areas ?? [];

  const dataBounds = useMemo(() => {
    const allPoints: { x: number; y: number }[] = [];
    if (footprint) allPoints.push(...footprint);
    areas.forEach((a) => allPoints.push(...a.points));
    if (allPoints.length === 0) return null;
    const xs = allPoints.map((p) => p.x * METER_PX);
    const ys = allPoints.map((p) => -p.y * METER_PX);
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    };
  }, [footprint, areas]);

  const boundsCenter = useMemo(() => {
    if (!dataBounds) return { x: originPx.x, y: originPx.y };
    return {
      x: (dataBounds.minX + dataBounds.maxX) / 2,
      y: (dataBounds.minY + dataBounds.maxY) / 2,
    };
  }, [dataBounds]);

  useEffect(() => {
    const update = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setSize({ width: Math.max(1, rect.width), height: Math.max(1, rect.height) });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const initialCentered = useMemo(() => {
    const x = size.width / 2 - boundsCenter.x;
    const y = size.height / 2 - boundsCenter.y;
    return { x, y };
  }, [size.width, size.height, boundsCenter.x, boundsCenter.y]);

  // Center on first mount / when container size becomes known.
  useEffect(() => {
    setPosition(initialCentered);
  }, [initialCentered.x, initialCentered.y]);

  const onWheel = (e: {
    evt: { preventDefault: () => void; deltaY: number; clientX: number; clientY: number };
  }) => {
    e.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;

    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const oldScale = scale;
    const newScale = clamp(oldScale * (e.evt.deltaY < 0 ? 1.1 : 0.9), 0.1, 20);

    const mousePointTo = {
      x: (pointer.x - position.x) / oldScale,
      y: (pointer.y - position.y) / oldScale,
    };

    setScale(newScale);
    setPosition({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    });
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
    setPosition({
      x: size.width / 2 - boundsCenter.x * newScale,
      y: size.height / 2 - boundsCenter.y * newScale,
    });
  };

  const resetView = () => {
    setScale(1);
    setPosition(initialCentered);
  };

  const worldSize = 2000;
  const gridLines = useMemo(() => {
    const lines: number[][] = [];
    const step = METER_PX;
    const half = worldSize / 2;
    for (let i = -half; i <= half; i += step) {
      lines.push([-half, i, half, i]); // horizontal
      lines.push([i, -half, i, half]); // vertical
    }
    return lines;
  }, []);

  const axisLines = [
    [-worldSize / 2, 0, worldSize / 2, 0],
    [0, -worldSize / 2, 0, worldSize / 2],
  ];

  const footprintPoints = useMemo(() => {
    if (!footprint || footprint.length < 3) return [];
    return footprint.flatMap((p) => [p.x * METER_PX, -p.y * METER_PX]);
  }, [footprint]);

  const areaRenderData = useMemo(
    () =>
      areas.map((area) => {
        const pts = area.points.flatMap((p) => [p.x * METER_PX, -p.y * METER_PX]);
        return {
          ...area,
          points: pts,
          fill:
            area.type === "apartment"
              ? getApartmentFill(area.apartmentType)
              : BSP_COLORS[area.type].fill,
          stroke:
            area.type === "apartment"
              ? getApartmentStroke(area.apartmentType)
              : BSP_COLORS[area.type].stroke,
        };
      }),
    [areas]
  );

  const labelCenter = (points: number[]) => {
    const xs = points.filter((_, i) => i % 2 === 0);
    const ys = points.filter((_, i) => i % 2 === 1);
    if (xs.length === 0 || ys.length === 0) return null;
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    return { x: (minX + maxX) / 2, y: (minY + maxY) / 2 };
  };

  return (
    <div ref={containerRef} className="relative h-full w-full">
      <div className="pointer-events-none absolute left-4 top-4 z-10 flex flex-col gap-1 text-xs text-neutral-300">
        <div>scale: {scale.toFixed(2)}x</div>
        <div>pan: drag</div>
        <div>zoom: mouse wheel</div>
      </div>

      <div className="absolute right-4 top-4 z-10 flex gap-2">
        <button
          onClick={fitToScreen}
          className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-white hover:bg-neutral-600 active:bg-neutral-500"
        >
          Fit to screen
        </button>
        <button
          onClick={resetView}
          className="rounded bg-neutral-700 px-3 py-1.5 text-sm text-white hover:bg-neutral-600 active:bg-neutral-500"
        >
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
        draggable
        onWheel={onWheel}
        onDragStart={() => setIsDragging(true)}
        onDragEnd={(e) => {
          setIsDragging(false);
          setPosition({ x: e.target.x(), y: e.target.y() });
        }}
        style={{ cursor: isDragging ? "grabbing" : "grab" }}
      >
        <Layer>
          <Rect
            x={-worldSize / 2}
            y={-worldSize / 2}
            width={worldSize}
            height={worldSize}
            fill="#171717"
          />
        </Layer>

        <Layer>
          {gridLines.map((points, i) => (
            <Line key={`g-${i}`} points={points} stroke="#333333" strokeWidth={1 / scale} />
          ))}
        </Layer>

        <Layer>
          {axisLines.map((points, i) => (
            <Line key={`a-${i}`} points={points} stroke="#666666" strokeWidth={2 / scale} />
          ))}
          <Text x={8 / scale} y={4 / scale} text="0,0" fontSize={12 / scale} fill="#999" />
          <Text x={worldSize / 2 - 30 / scale} y={4 / scale} text="x" fontSize={14 / scale} fill="#999" />
          <Text x={8 / scale} y={-worldSize / 2 + 4 / scale} text="y" fontSize={14 / scale} fill="#999" />
        </Layer>

        <Layer>
          {footprintPoints.length > 0 && (
            <Line
              points={footprintPoints}
              closed
              stroke="#ffffff"
              strokeWidth={2 / scale}
              fill="rgba(255,255,255,0.05)"
            />
          )}
          {areaRenderData.map((area) => (
            <Line
              key={area.id}
              points={area.points}
              closed
              fill={area.fill}
              stroke={area.stroke}
              strokeWidth={1.5 / scale}
            />
          ))}
          {areaRenderData.map((area) => {
            const center = labelCenter(area.points);
            if (!center) return null;
            return (
              <Text
                key={`label-${area.id}`}
                x={center.x}
                y={center.y - 6 / scale}
                text={area.name}
                align="center"
                width={0}
                offsetX={0}
                fontSize={10 / scale}
                fill="#111827"
                listening={false}
              />
            );
          })}
        </Layer>
      </Stage>
    </div>
  );
}
