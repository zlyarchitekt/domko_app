"use client";

import { Plus, X } from "lucide-react";
import { useSession } from "../state/SessionContext";

const APARTMENT_TYPES = ["M1", "M2", "M3", "M4", "M5"];

function polygonArea(points: { x: number; y: number }[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

export default function ProgramSection() {
  const { state, updateProgramRow, addProgramRow, removeProgramRow } = useSession();

  const footprintArea = state.footprint ? polygonArea(state.footprint) : 0;
  const programArea = state.program.reduce((sum, row) => sum + row.min_area_m2 * row.target_count, 0);
  const balance = footprintArea > 0 ? (programArea / footprintArea) * 100 : 0;

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Program mieszkań</h2>

      <div className="space-y-1.5">
        {state.program.map((row) => (
          <div key={row.id} className="flex items-center gap-1.5">
            <select
              value={row.type}
              onChange={(e) => updateProgramRow(row.id, { type: e.target.value })}
              className="rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
            >
              {APARTMENT_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={0}
              value={row.target_count}
              onChange={(e) => updateProgramRow(row.id, { target_count: Number(e.target.value) })}
              title="Liczba"
              className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
            />
            <span className="text-xs text-zinc-600">×</span>
            <input
              type="number"
              min={1}
              value={row.min_area_m2}
              onChange={(e) => updateProgramRow(row.id, { min_area_m2: Number(e.target.value) })}
              title="Docelowa powierzchnia m²"
              className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
            />
            <span className="text-xs text-zinc-600">m²</span>
            <button
              onClick={() => removeProgramRow(row.id)}
              className="ml-auto rounded-lg p-1.5 text-zinc-600 transition-colors hover:bg-red-500/10 hover:text-red-400"
              aria-label="Usuń"
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>

      <button
        onClick={addProgramRow}
        className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-zinc-800/70 px-2 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
      >
        <Plus size={13} />
        Dodaj typ mieszkania
      </button>

      <div className="space-y-1 rounded-lg bg-zinc-900/70 px-3 py-2.5 text-xs light:bg-zinc-100">
        <div className="flex justify-between text-zinc-400">
          <span>Program</span>
          <span className="font-mono text-zinc-200 light:text-zinc-800">{programArea.toFixed(1)} m²</span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Obrys</span>
          <span className="font-mono text-zinc-200 light:text-zinc-800">{footprintArea.toFixed(1)} m²</span>
        </div>
        <div
          className={`flex justify-between border-t border-zinc-800 pt-1 font-medium light:border-zinc-300 ${
            balance > 95 ? "text-red-400" : balance > 80 ? "text-amber-400" : "text-emerald-400"
          }`}
        >
          <span>Bilans</span>
          <span className="font-mono">{balance.toFixed(0)}%</span>
        </div>
      </div>
    </section>
  );
}
