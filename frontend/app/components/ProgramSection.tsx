"use client";

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
    <section className="space-y-2 border-b border-neutral-700 pb-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Program mieszkań</h2>

      <div className="space-y-1.5">
        {state.program.map((row) => (
          <div key={row.id} className="flex items-center gap-1.5">
            <select
              value={row.type}
              onChange={(e) => updateProgramRow(row.id, { type: e.target.value })}
              className="rounded bg-neutral-800 px-1.5 py-1 text-xs text-neutral-100"
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
              className="w-14 rounded bg-neutral-800 px-1.5 py-1 text-xs text-neutral-100"
            />
            <span className="text-xs text-neutral-500">×</span>
            <input
              type="number"
              min={1}
              value={row.min_area_m2}
              onChange={(e) => updateProgramRow(row.id, { min_area_m2: Number(e.target.value) })}
              title="Docelowa powierzchnia m²"
              className="w-16 rounded bg-neutral-800 px-1.5 py-1 text-xs text-neutral-100"
            />
            <span className="text-xs text-neutral-500">m²</span>
            <button
              onClick={() => removeProgramRow(row.id)}
              className="ml-auto rounded px-1.5 py-1 text-xs text-neutral-500 hover:bg-neutral-700 hover:text-red-400"
              aria-label="Usuń"
            >
              ✕
            </button>
          </div>
        ))}
      </div>

      <button
        onClick={addProgramRow}
        className="w-full rounded bg-neutral-700 px-2 py-1 text-xs text-neutral-100 hover:bg-neutral-600"
      >
        + Dodaj typ mieszkania
      </button>

      <div className="rounded bg-neutral-800 px-3 py-2 text-xs">
        <div className="flex justify-between text-neutral-300">
          <span>Program</span>
          <span>{programArea.toFixed(1)} m²</span>
        </div>
        <div className="flex justify-between text-neutral-300">
          <span>Obrys</span>
          <span>{footprintArea.toFixed(1)} m²</span>
        </div>
        <div
          className={`mt-1 flex justify-between font-medium ${
            balance > 95 ? "text-red-400" : balance > 80 ? "text-yellow-400" : "text-green-400"
          }`}
        >
          <span>Bilans</span>
          <span>{balance.toFixed(0)}%</span>
        </div>
      </div>
    </section>
  );
}
