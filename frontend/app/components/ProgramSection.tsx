"use client";

import { Plus, X } from "lucide-react";
import { useSession, DEFAULT_TYPE_COLORS } from "../state/SessionContext";
import * as api from "../lib/api";

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
  const {
    state,
    updateProgramRow,
    addProgramRow,
    removeProgramRow,
    setUnitWeight,
    setTypeColor,
    selectUnitIteration,
    activeUnitSeed,
  } = useSession();

  const footprintArea = state.footprint ? polygonArea(state.footprint) : 0;
  // min_area_m2/target_count są pochodne (środek zakresu × zaokrąglony udział %
  // z totalUnits — patrz recomputeDerivedProgram w SessionContext.tsx), więc ta
  // suma automatycznie odzwierciedla aktualną strukturę %.
  const programArea = state.program.reduce((sum, row) => sum + row.min_area_m2 * row.target_count, 0);
  const balance = footprintArea > 0 ? (programArea / footprintArea) * 100 : 0;
  const percentageSum = state.program.reduce((sum, row) => sum + row.percentage, 0);
  const totalPlacedUnits = state.program.reduce((sum, row) => sum + row.target_count, 0);

  // Orientacyjny szacunek PRZED umieszczeniem komunikacji/podziałem (który
  // jedyny liczy prawdziwe derivedTotalUnits z net_remainder_m2) — user chce
  // widzieć liczbę mieszkań od razu po narysowaniu/imporcie obrysu i po każdej
  // korekcie węzłów, nie dopiero po "Umieść korytarz i klatkę"+"Podziel na
  // mieszkania". Sprawność budynku ~70% (footprintArea*0.7) jako przybliżenie
  // net_remainder_m2 zanim komunikacja jest w ogóle policzona.
  const totalPctForEstimate = state.program.reduce((sum, row) => sum + row.percentage, 0);
  const avgUnitSizeM2 =
    totalPctForEstimate > 0
      ? state.program.reduce(
          (sum, row) => sum + (row.percentage / totalPctForEstimate) * ((row.area_min_m2 + row.area_max_m2) / 2),
          0
        )
      : 0;
  const estimatedTotalUnits =
    footprintArea > 0 && avgUnitSizeM2 > 0 ? Math.max(1, Math.floor((footprintArea * 0.7) / avgUnitSizeM2)) : null;

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Struktura mieszkań</h2>

      <div className="flex items-center justify-between text-xs text-zinc-400">
        Liczba mieszkań (z powierzchni)
        <span className="font-mono text-zinc-200 light:text-zinc-800">
          {state.derivedTotalUnits !== null
            ? `≈ ${state.derivedTotalUnits}${state.netRemainderM2 !== null ? ` (${state.netRemainderM2.toFixed(0)} m² netto)` : ""}`
            : estimatedTotalUnits !== null
              ? `~${estimatedTotalUnits} (szacunek)`
              : "—"}
        </span>
      </div>

      <div className="space-y-1.5">
        {state.program.map((row) => (
          <div key={row.id} className="rounded-lg border border-zinc-800/60 p-2 light:border-zinc-200">
            <div className="flex items-center gap-1.5">
              <label
                className="relative h-6 w-6 shrink-0 cursor-pointer rounded-full border border-zinc-600/60 light:border-zinc-300"
                style={{ backgroundColor: state.typeColors?.[row.type] ?? DEFAULT_TYPE_COLORS[row.type] ?? "#9ca3af" }}
                title={`Kolor mieszkań typu ${row.type} na rysunku`}
              >
                <input
                  type="color"
                  value={state.typeColors?.[row.type] ?? DEFAULT_TYPE_COLORS[row.type] ?? "#9ca3af"}
                  onChange={(e) => setTypeColor(row.type, e.target.value)}
                  className="absolute inset-0 h-full w-full cursor-pointer opacity-0"
                  aria-label={`Kolor typu ${row.type}`}
                />
              </label>
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
                max={100}
                value={row.percentage}
                onChange={(e) => updateProgramRow(row.id, { percentage: Number(e.target.value) })}
                title="Udział w łącznej liczbie mieszkań"
                className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
              />
              <span className="text-xs text-zinc-600">%</span>
              <span
                className="ml-auto shrink-0 rounded-md bg-accent-500/15 px-1.5 py-0.5 font-mono text-[11px] text-accent-400"
                title="Wyliczona liczba mieszkań tego typu (udział% × łączna liczba, zaokrąglone)"
              >
                ≈{row.target_count} szt.
              </span>
              <button
                onClick={() => removeProgramRow(row.id)}
                className="shrink-0 rounded-lg p-1 text-zinc-600 transition-colors hover:bg-red-500/10 hover:text-red-400"
                aria-label="Usuń"
              >
                <X size={13} />
              </button>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-xs text-zinc-500">
              <span className="shrink-0">Metraż</span>
              <input
                type="number"
                min={1}
                value={row.area_min_m2}
                onChange={(e) => updateProgramRow(row.id, { area_min_m2: Number(e.target.value) })}
                title="Metraż od (m²)"
                className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
              />
              <span>–</span>
              <input
                type="number"
                min={1}
                value={row.area_max_m2}
                onChange={(e) => updateProgramRow(row.id, { area_max_m2: Number(e.target.value) })}
                title="Metraż do (m²)"
                className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
              />
              <span>m²</span>
            </div>
            <div className="mt-1.5 flex items-center gap-1.5 text-xs text-zinc-500">
              <span className="shrink-0">Min. styk z elewacją</span>
              <input
                type="number"
                step={0.5}
                min={0}
                value={row.min_facade_m}
                onChange={(e) => updateProgramRow(row.id, { min_facade_m: Number(e.target.value) })}
                title="Minimalny styk mieszkań tego typu ze ścianą zewnętrzną (komponent Daylight)"
                className="w-14 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
              />
              <span>m</span>
            </div>
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
          <span>Suma udziałów</span>
          <span className={`font-mono ${Math.round(percentageSum) === 100 ? "text-zinc-200 light:text-zinc-800" : "text-amber-400"}`}>
            {percentageSum.toFixed(0)}%{Math.round(percentageSum) !== 100 && " ⚠"}
          </span>
        </div>
        <div className="flex justify-between text-zinc-400">
          <span>Mieszkania (wyliczone)</span>
          <span className="font-mono text-zinc-200 light:text-zinc-800">
            {totalPlacedUnits} / {state.totalUnits}
          </span>
        </div>
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

      <div className="space-y-1.5 pt-1">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Wagi układu</div>
        {(
          [
            ["size", "Wielkość m²"],
            ["mix", "Struktura mieszkań"],
            ["grid", "Siatka 0.5m"],
            ["shape", "Prostokątność"],
            ["daylight", "Dostęp do elewacji"],
            ["squareness", "Proporcje boków"],
            ["adjacency", "Dostęp do komunikacji"],
          ] as [keyof api.UnitWeightsInput, string][]
        ).map(([key, label]) => (
          <label key={key} className="flex items-center justify-between text-xs text-zinc-400">
            <span>{label} ({state.unitWeights[key].toFixed(2)})</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={state.unitWeights[key]}
              onChange={(e) => setUnitWeight(key, Number(e.target.value))}
              className="ml-2 w-24 accent-accent-500"
            />
          </label>
        ))}
      </div>

      {state.lastIterations.length > 0 && (
        <div className="space-y-0.5 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
            Iteracje ({state.lastIterations.length})
          </div>
          <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
          {state.lastIterations.map((m) => {
            const isBest = state.lastIterations.every((o) => m.score <= o.score);
            const isActive = activeUnitSeed === m.seed || (activeUnitSeed === null && isBest);
            return (
              <button
                key={m.seed}
                onClick={() => selectUnitIteration(m.seed)}
                className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                  isBest ? "text-accent-400" : "text-zinc-500"
                } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
              >
                <span>#{m.seed}{isBest ? " ★" : ""}</span>
                <span>{m.units_count} szt.</span>
                <span>odchylenie {m.score.toFixed(3)}</span>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
}
