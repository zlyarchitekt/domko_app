"use client";

import { useEffect } from "react";
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
    <section className="space-y-2 border-b border-neutral-700 pb-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Komunikacja</h2>

      {state.typologySuggestion && (
        <div className="rounded bg-neutral-800 px-3 py-2 text-xs text-neutral-300">
          <div className="mb-1 text-neutral-400">
            Sugerowana typologia:{" "}
            <span className="font-medium text-blue-300">
              {TYPOLOGY_LABELS[state.typologySuggestion.typology] ?? state.typologySuggestion.typology}
            </span>
          </div>
          <div className="text-[11px] text-neutral-500">{state.typologySuggestion.rationale}</div>
        </div>
      )}

      <select
        value={state.selectedTypology ?? ""}
        onChange={(e) => e.target.value && void applyTypologyPreset(e.target.value)}
        className="w-full rounded bg-neutral-800 px-2 py-1.5 text-xs text-neutral-100"
      >
        <option value="">— wybierz typologię (opcjonalnie) —</option>
        {Object.entries(TYPOLOGY_LABELS).map(([key, label]) => (
          <option key={key} value={key}>
            {label}
            {state.typologySuggestion?.typology === key ? " (sugerowana)" : ""}
          </option>
        ))}
      </select>

      <label className="flex items-center justify-between text-xs text-neutral-300">
        Pozycja klatki
        <select
          value={state.circulation.cage_position}
          onChange={(e) => setCirculation({ cage_position: e.target.value as CagePosition })}
          className="rounded bg-neutral-800 px-2 py-1 text-neutral-100"
        >
          {CAGE_MODES.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2 text-xs text-neutral-300">
        <input
          type="checkbox"
          checked={state.circulation.place_cage}
          onChange={(e) => setCirculation({ place_cage: e.target.checked })}
        />
        Umieść klatkę schodową
      </label>

      <label className="flex items-center justify-between text-xs text-neutral-300">
        Wymiar klatki (m)
        <input
          type="number"
          step={0.1}
          min={1}
          value={state.circulation.cage_size_m}
          onChange={(e) => setCirculation({ cage_size_m: Number(e.target.value) })}
          className="w-16 rounded bg-neutral-800 px-2 py-1 text-neutral-100"
        />
      </label>

      <label className="flex items-center justify-between text-xs text-neutral-300">
        Szerokość korytarza (m)
        <input
          type="number"
          step={0.1}
          min={0.9}
          value={state.circulation.corridor_width_m}
          onChange={(e) => setCirculation({ corridor_width_m: Number(e.target.value) })}
          className="w-16 rounded bg-neutral-800 px-2 py-1 text-neutral-100"
        />
      </label>

      <div className="flex flex-col gap-2 pt-1">
        <button
          onClick={() => void runPlaceCirculation()}
          disabled={!state.footprint || state.isLoading}
          className="w-full rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-40"
        >
          {state.isLoading ? "Umieszczam..." : "1. Umieść korytarz i klatkę"}
        </button>
        <button
          onClick={() => void runSubdivideUnits()}
          disabled={!state.circulationResult || state.isLoading}
          className="w-full rounded bg-blue-700 px-3 py-2 text-sm font-medium text-white hover:bg-blue-600 disabled:opacity-40"
        >
          {state.isLoading ? "Dzielę..." : "2. Podziel na mieszkania"}
        </button>
        <button
          onClick={() => setMode(state.mode === "edit-circulation" ? "idle" : "edit-circulation")}
          disabled={!state.circulationResult}
          className={`rounded px-2 py-1.5 text-sm disabled:opacity-40 ${
            state.mode === "edit-circulation" ? "bg-blue-600 text-white" : "bg-neutral-700 text-neutral-100 hover:bg-neutral-600"
          }`}
          title={!state.circulationResult ? "Wymaga umieszczenia korytarza/klatki" : "Przeciągnij korytarz/klatkę"}
        >
          Przesuń komunikację
        </button>
      </div>
    </section>
  );
}
