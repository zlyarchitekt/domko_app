"use client";

import { useRef, useState } from "react";
import { useSession } from "../state/SessionContext";

function polygonArea(points: { x: number; y: number }[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

function edgeLengths(points: { x: number; y: number }[]): number[] {
  return points.map((p, i) => {
    const next = points[(i + 1) % points.length];
    return Math.hypot(next.x - p.x, next.y - p.y);
  });
}

export default function FootprintSection() {
  const { state, setMode, finishDrawing, setFootprintFromDxf } = useSession();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const area = state.footprint ? polygonArea(state.footprint) : 0;
  const lengths = state.footprint ? edgeLengths(state.footprint) : [];

  const handleFile = async (file: File | undefined | null) => {
    if (!file) return;
    await setFootprintFromDxf(file);
  };

  return (
    <section className="space-y-2 border-b border-neutral-700 pb-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Obrys</h2>

      <div className="flex gap-2">
        <button
          onClick={() => setMode(state.mode === "draw" ? "idle" : "draw")}
          className={`flex-1 rounded px-2 py-1.5 text-sm ${
            state.mode === "draw" ? "bg-blue-600 text-white" : "bg-neutral-700 text-neutral-100 hover:bg-neutral-600"
          }`}
        >
          {state.mode === "draw" ? "Rysuję… (dwuklik = zamknij)" : "Rysuj obrys"}
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-vertices" ? "idle" : "edit-vertices")}
          disabled={!state.footprint}
          className={`rounded px-2 py-1.5 text-sm disabled:opacity-40 ${
            state.mode === "edit-vertices" ? "bg-blue-600 text-white" : "bg-neutral-700 text-neutral-100 hover:bg-neutral-600"
          }`}
          title={!state.footprint ? "Wymaga narysowania obrysu" : "Edytuj węzły obrysu"}
        >
          Węzły
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-lines" ? "idle" : "edit-lines")}
          disabled={!state.layoutResult}
          className={`rounded px-2 py-1.5 text-sm disabled:opacity-40 ${
            state.mode === "edit-lines" ? "bg-blue-600 text-white" : "bg-neutral-700 text-neutral-100 hover:bg-neutral-600"
          }`}
          title={!state.layoutResult ? "Wymaga wygenerowanego układu z komunikacją" : "Przesuwaj linie podziału mieszkań"}
        >
          Linie
        </button>
      </div>

      {state.mode === "draw" && state.drawingPoints.length >= 3 && (
        <button
          onClick={() => void finishDrawing()}
          className="w-full rounded bg-green-700 px-2 py-1.5 text-sm text-white hover:bg-green-600"
        >
          Zamknij obrys ({state.drawingPoints.length} pkt)
        </button>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          void handleFile(e.dataTransfer.files?.[0]);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`cursor-pointer rounded border border-dashed px-3 py-4 text-center text-xs ${
          dragOver ? "border-blue-400 bg-blue-950/30 text-blue-200" : "border-neutral-600 text-neutral-400"
        }`}
      >
        Upuść plik .dxf lub kliknij, aby wybrać
        <input
          ref={fileInputRef}
          type="file"
          accept=".dxf"
          className="hidden"
          onChange={(e) => void handleFile(e.target.files?.[0])}
        />
      </div>

      {state.footprint && (
        <div className="space-y-1 rounded bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
          <div className="flex justify-between font-medium text-neutral-100">
            <span>Powierzchnia</span>
            <span>{area.toFixed(1)} m²</span>
          </div>
          <div className="text-neutral-400">Boki:</div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5">
            {lengths.map((len, i) => (
              <span key={i}>
                #{i + 1}: {len.toFixed(2)} m
              </span>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
