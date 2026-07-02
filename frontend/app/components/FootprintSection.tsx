"use client";

import { useRef, useState } from "react";
import { PenLine, MousePointer2, GitCommitHorizontal, UploadCloud, Check } from "lucide-react";
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
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3">
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Obrys</h2>

      <div className="flex gap-1.5">
        <button
          onClick={() => setMode(state.mode === "draw" ? "idle" : "draw")}
          className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${
            state.mode === "draw"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70"
          }`}
        >
          <PenLine size={13} />
          {state.mode === "draw" ? "Rysuję…" : "Rysuj obrys"}
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-vertices" ? "idle" : "edit-vertices")}
          disabled={!state.footprint}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "edit-vertices"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70"
          }`}
          title={!state.footprint ? "Wymaga narysowania obrysu" : "Edytuj węzły obrysu"}
        >
          <MousePointer2 size={13} />
          Węzły
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-lines" ? "idle" : "edit-lines")}
          disabled={!state.layoutResult}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "edit-lines"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70"
          }`}
          title={!state.layoutResult ? "Wymaga wygenerowanego układu z komunikacją" : "Przesuwaj linie podziału mieszkań"}
        >
          <GitCommitHorizontal size={13} />
          Linie
        </button>
      </div>

      {state.mode === "draw" && state.drawingPoints.length >= 3 && (
        <button
          onClick={() => void finishDrawing()}
          className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-600/90 px-2 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-500"
        >
          <Check size={13} />
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
        className={`flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed px-3 py-4 text-center text-[11px] transition-colors ${
          dragOver ? "border-accent-400 bg-accent-500/10 text-accent-200" : "border-zinc-700/70 text-zinc-500 hover:border-zinc-600 hover:text-zinc-400"
        }`}
      >
        <UploadCloud size={16} strokeWidth={1.5} />
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
        <div className="space-y-1.5 rounded-lg bg-zinc-900/70 px-3 py-2.5 text-xs text-zinc-400">
          <div className="flex justify-between font-medium text-zinc-100">
            <span>Powierzchnia</span>
            <span className="font-mono">{area.toFixed(1)} m²</span>
          </div>
          <div className="text-[10px] uppercase tracking-wide text-zinc-600">Boki</div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 font-mono text-[11px] text-zinc-400">
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
