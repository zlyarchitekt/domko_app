"use client";

import { useEffect } from "react";
import { Move } from "lucide-react";
import { useSession } from "../state/SessionContext";
import { CagePosition } from "../lib/api";

const CAGE_MODES: { value: CagePosition; label: string }[] = [
  { value: "1a", label: "1A: elewacja front" },
  { value: "1b", label: "1B: elewacja tył/dziedziniec" },
  { value: "2", label: "2: środek traktu" },
  { value: "3", label: "3: narożnik" },
  { value: "auto", label: "Auto" },
];

const TYPOLOGY_LABELS: Record<string, string> = {
  klatkowiec_wzdluzny: "Klatkowiec wzdłużny",
  punktowiec: "Punktowiec",
  galeriowiec: "Galeriowiec",
  klatkowiec_narozny: "Klatkowiec narożny",
  szeregowiec: "Szeregowiec",
};

export default function CirculationSection() {
  const {
    state,
    setCirculation,
    refreshTypologySuggestion,
    applyTypologyPreset,
    runPlaceCirculation,
    runSubdivideUnits,
    setMode,
  } = useSession();

  useEffect(() => {
    if (state.footprint && state.footprint.length >= 3) {
      void refreshTypologySuggestion();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.footprint]);

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Komunikacja</h2>

      {state.typologySuggestion && (
        <div className="rounded-lg bg-zinc-900/70 px-3 py-2 text-xs text-zinc-400 light:bg-zinc-100">
          <div className="mb-1">
            Sugerowana typologia:{" "}
            <span className="font-medium text-accent-400">
              {TYPOLOGY_LABELS[state.typologySuggestion.typology] ?? state.typologySuggestion.typology}
            </span>
          </div>
          <div className="text-[11px] text-zinc-600">{state.typologySuggestion.rationale}</div>
        </div>
      )}

      <select
        value={state.selectedTypology ?? ""}
        onChange={(e) => e.target.value && void applyTypologyPreset(e.target.value)}
        className="w-full rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1.5 text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
      >
        <option value="">— wybierz typologię (opcjonalnie) —</option>
        {Object.entries(TYPOLOGY_LABELS).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
            {state.typologySuggestion?.typology === key ? " (sugerowana)" : ""}
          </option>
        ))}
      </select>

      <label className="flex items-center justify-between text-xs text-zinc-400">
        Pozycja klatki
        <select
          value={state.circulation.cage_position}
          onChange={(e) => setCirculation({ cage_position: e.target.value as CagePosition })}
          className="rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        >
          {CAGE_MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center justify-between text-xs text-zinc-400">
        Liczba klatek: {state.circulation.num_cages}
        <input
          type="range"
          min={1}
          max={8}
          step={1}
          value={state.circulation.num_cages}
          onChange={(e) => setCirculation({ num_cages: Number(e.target.value) })}
          className="ml-2 w-24 accent-accent-500"
        />
      </label>

      <label className="flex items-center gap-2 text-xs text-zinc-400">
        <input
          type="checkbox"
          checked={state.circulation.place_cage}
          onChange={(e) => setCirculation({ place_cage: e.target.checked })}
          className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-800 text-accent-500 focus:ring-accent-500/40 focus:ring-offset-0"
        />
        Umieść klatkę schodową
      </label>

      <label
        className="flex items-center justify-between text-xs text-zinc-400"
        title="Klatka schodowa ma teraz stały rozmiar 4.0×5.5m (spec 2026-07-03) — to pole nie wpływa na geometrię."
      >
        Wymiar klatki: 4.0×5.5m (stałe)
        <input
          type="number"
          step={0.1}
          min={1}
          value={state.circulation.cage_size_m}
          onChange={(e) => setCirculation({ cage_size_m: Number(e.target.value) })}
          disabled
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none disabled:cursor-not-allowed disabled:opacity-40 light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>

      <label className="flex items-center justify-between text-xs text-zinc-400">
        Szerokość korytarza (w świetle, m)
        <input
          type="number"
          step={0.1}
          min={0.9}
          value={state.circulation.corridor_width_m}
          onChange={(e) => setCirculation({ corridor_width_m: Number(e.target.value) })}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>

      <div className="flex flex-col gap-1.5 pt-1">
        <button
          onClick={() => void runPlaceCirculation()}
          disabled={!state.footprint || state.isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-500 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-accent-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/20 text-[10px]">1</span>
          {state.isLoading ? "Umieszczam..." : "Umieść korytarz i klatkę"}
        </button>
        <button
          onClick={() => void runSubdivideUnits()}
          disabled={!state.circulationResult || state.isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-500 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-accent-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
        >
          <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/20 text-[10px]">2</span>
          {state.isLoading ? "Dzielę..." : "Podziel na mieszkania"}
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-circulation" ? "idle" : "edit-circulation")}
          disabled={!state.circulationResult}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "edit-circulation"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.circulationResult ? "Wymaga umieszczenia korytarza/klatki" : "Przeciągnij korytarz/klatkę"}
        >
          <Move size={13} />
          Przesuń komunikację
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-corridor-centerline" ? "idle" : "edit-corridor-centerline")}
          disabled={!state.circulationResult}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "edit-corridor-centerline"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.circulationResult ? "Wymaga umieszczenia korytarza/klatki" : "Przeciągnij punkty linii korytarza"}
        >
          <Move size={13} />
          Edytuj linię korytarza
        </button>
      </div>
    </section>
  );
}
