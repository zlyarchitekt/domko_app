"use client";

import { useEffect } from "react";
import { Move } from "lucide-react";
import { useSession } from "../state/SessionContext";
import * as api from "../lib/api";
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
    runRecomputeEvacuation,
    runResizeCage,
    setIterationsCount,
    setMode,
    removeManualElement,
    setHoveredManualId,
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

      <label
        className="flex items-center justify-between text-xs text-zinc-400"
        title="Budżet prób silnika iteracyjnego (klatki i mieszkania). Więcej = lepsze wyniki, dłuższe liczenie. Backend przyjmuje max 50."
      >
        Liczba iteracji (1-50)
        <input
          type="number"
          step={1}
          min={1}
          max={50}
          value={state.iterationsCount}
          onChange={(e) => setIterationsCount(Number(e.target.value))}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>

      <label
        className="flex items-center justify-between text-xs text-zinc-400"
        title="Wyżarzanie: 1/3 budżetu losowo, reszta doskonali najlepsze warianty mutacjami (zalecane). Losowa: wszystkie próby niezależne (debug/porównania)."
      >
        Strategia szukania
        <select
          value={state.circulation.strategy ?? "anneal"}
          onChange={(e) => setCirculation({ strategy: e.target.value as "anneal" | "random" })}
          className="rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        >
          <option value="anneal">Wyżarzanie (zalecane)</option>
          <option value="random">Losowa</option>
        </select>
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

      <label className="flex items-center justify-between text-xs text-zinc-400">
        Dojście do 1 klatki ≤ (m)
        <input
          type="number" step={1} min={1}
          value={state.circulation.max_dist_single_m}
          onChange={(e) => setCirculation({ max_dist_single_m: Number(e.target.value) })}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>
      <label className="flex items-center justify-between text-xs text-zinc-400">
        Dojście do ≥2 klatek ≤ (m)
        <input
          type="number" step={1} min={1}
          value={state.circulation.max_dist_multi_m}
          onChange={(e) => setCirculation({ max_dist_multi_m: Number(e.target.value) })}
          className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1 font-mono text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
        />
      </label>

      <details className="pt-1">
        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
          Wagi klatek
        </summary>
        <div className="space-y-1.5 pt-1.5">
          {(
            [
              ["egress", "Minimalizuj złe dojścia"],
              ["count", "Dowieź żądaną liczbę klatek"],
              ["corners", "Klatki w narożnikach"],
              ["ends", "Klatki na końcach"],
              ["spread", "Równomierne rozmieszczenie"],
            ] as [keyof api.CageWeightsInput, string][]
          ).map(([key, label]) => (
            <label key={key} className="flex items-center justify-between text-xs text-zinc-400">
              <span>{label} ({state.circulation.cage_weights[key].toFixed(2)})</span>
              <input
                type="range" min={0} max={1} step={0.05}
                value={state.circulation.cage_weights[key]}
                onChange={(e) =>
                  setCirculation({
                    cage_weights: { ...state.circulation.cage_weights, [key]: Number(e.target.value) },
                  })
                }
                className="ml-2 w-24 accent-accent-500"
              />
            </label>
          ))}
        </div>
      </details>

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
          onClick={() => void runPlaceCirculation({ circulationOverride: { cage_iterations: state.iterationsCount } })}
          disabled={!state.footprint || state.isLoading}
          className="flex w-full items-center justify-center gap-2 rounded-lg bg-accent-500 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-accent-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
          title={`${state.iterationsCount} iteracji lokalizacji klatek, wygrywa najlepszy score wg wag`}
        >
          {state.isLoading ? "Iteruję..." : "Rozmieść iteracyjnie"}
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
        <button
          onClick={() => void runRecomputeEvacuation()}
          disabled={!state.circulationResult || state.isLoading}
          className="flex items-center justify-center gap-1.5 rounded-lg bg-zinc-800/70 px-2 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700/70 disabled:opacity-30 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          title="Przelicz kropki dojść po zmianie progów — bez ruszania geometrii"
        >
          PRZELICZ dojścia
        </button>
        <button
          onClick={() => setMode(state.mode === "draw-cage" ? "idle" : "draw-cage")}
          disabled={!state.footprint}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "draw-cage"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.footprint ? "Najpierw narysuj obrys" : "Klikaj punkty, dblclick zamyka klatkę"}
        >
          Rysuj klatkę
        </button>
        <button
          onClick={() => setMode(state.mode === "draw-corridor" ? "idle" : "draw-corridor")}
          disabled={!state.footprint}
          className={`flex items-center justify-center gap-1.5 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors disabled:opacity-30 ${
            state.mode === "draw-corridor"
              ? "bg-accent-500/20 text-accent-400 ring-1 ring-inset ring-accent-500/30"
              : "bg-zinc-800/70 text-zinc-300 hover:bg-zinc-700/70 light:bg-zinc-100 light:text-zinc-700 light:hover:bg-zinc-200"
          }`}
          title={!state.footprint ? "Najpierw narysuj obrys" : "Klikaj punkty osi, dblclick kończy korytarz"}
        >
          Rysuj korytarz
        </button>
      </div>

      {(state.manualCages.length > 0 || state.manualCorridors.length > 0) && (
        <div className="space-y-1 pt-1">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Elementy ręczne</div>
          {state.manualCages.map((c, i) => (
            <div
              key={c.id}
              onMouseEnter={() => setHoveredManualId(c.id)}
              onMouseLeave={() => setHoveredManualId(null)}
              className="flex items-center justify-between rounded-lg bg-zinc-900/70 px-2 py-1 text-xs text-zinc-300 light:bg-zinc-100 light:text-zinc-700"
            >
              <span>Klatka {i + 1}</span>
              <button
                onClick={() => {
                  removeManualElement(c.id);
                  void runPlaceCirculation({ manualCages: state.manualCages.filter((x) => x.id !== c.id) });
                }}
                className="text-zinc-500 hover:text-red-400"
                title="Usuń"
              >
                ✕
              </button>
            </div>
          ))}
          {state.manualCorridors.map((c, i) => (
            <div
              key={c.id}
              onMouseEnter={() => setHoveredManualId(c.id)}
              onMouseLeave={() => setHoveredManualId(null)}
              className="flex items-center justify-between rounded-lg bg-zinc-900/70 px-2 py-1 text-xs text-zinc-300 light:bg-zinc-100 light:text-zinc-700"
            >
              <span>Korytarz {i + 1}</span>
              <button
                onClick={() => {
                  removeManualElement(c.id);
                  void runPlaceCirculation({ manualCorridors: state.manualCorridors.filter((x) => x.id !== c.id) });
                }}
                className="text-zinc-500 hover:text-red-400"
                title="Usuń"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Wymiary klatek per sztuka (user 2026-07-14) -- zwijane <details>,
          żeby nie zaśmiecać panelu. Zmiana wymiaru = box zakotwiczony w
          dotychczasowym min-narożniku -> /circulation/move-cage przelicza
          korytarz (walidacja obrysu/kolizji po stronie backendu). */}
      {(state.circulationResult?.cage_geometries?.length ?? 0) > 0 && (
        <details className="rounded-lg border border-zinc-800/60 light:border-zinc-200">
          <summary className="cursor-pointer select-none px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500 hover:text-zinc-300">
            Wymiary klatek ({state.circulationResult!.cage_geometries.length})
          </summary>
          <div className="space-y-1.5 px-2 pb-2">
            <div className="text-[9px] text-zinc-600">wymiary w osiach ścian [m]; Enter lub Zastosuj przelicza korytarz</div>
            {state.circulationResult!.cage_geometries.map((g, i) => {
              const xs = g.coordinates[0].map(([x]) => x);
              const ys = g.coordinates[0].map(([, y]) => y);
              const w = Math.max(...xs) - Math.min(...xs);
              const d = Math.max(...ys) - Math.min(...ys);
              const wId = `cage-w-${i}`;
              const dId = `cage-d-${i}`;
              const apply = () => {
                const wEl = document.getElementById(wId) as HTMLInputElement | null;
                const dEl = document.getElementById(dId) as HTMLInputElement | null;
                const newW = Number(wEl?.value);
                const newD = Number(dEl?.value);
                if (newW > 0 && newD > 0) void runResizeCage(i, newW, newD);
              };
              return (
                <div key={`cage-dim-${i}`} className="flex items-center gap-1.5 text-xs text-zinc-300 light:text-zinc-700">
                  <span className="w-16 shrink-0">Klatka {i + 1}</span>
                  <input
                    id={wId}
                    key={`w-${i}-${w.toFixed(2)}`}
                    type="number"
                    step={0.1}
                    min={1}
                    defaultValue={w.toFixed(1)}
                    onKeyDown={(e) => e.key === "Enter" && apply()}
                    className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
                  />
                  <span className="text-zinc-600">×</span>
                  <input
                    id={dId}
                    key={`d-${i}-${d.toFixed(2)}`}
                    type="number"
                    step={0.1}
                    min={1}
                    defaultValue={d.toFixed(1)}
                    onKeyDown={(e) => e.key === "Enter" && apply()}
                    className="w-16 rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-1.5 py-1 font-mono text-xs text-zinc-100 focus:border-accent-500/60 focus:outline-none light:border-zinc-300 light:bg-white light:text-zinc-900"
                  />
                  <button
                    onClick={apply}
                    disabled={state.isLoading}
                    className="ml-auto rounded bg-accent-500/15 px-2 py-1 text-[10px] font-medium text-accent-400 transition-colors hover:bg-accent-500/25 disabled:opacity-50"
                  >
                    Zastosuj
                  </button>
                </div>
              );
            })}
          </div>
        </details>
      )}

      {(state.circulationResult?.warnings?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-300 light:text-amber-700">
          {state.circulationResult!.warnings!.map((w, i) => (
            <div key={i}>{w}</div>
          ))}
        </div>
      )}

      {(() => {
        const dots = state.circulationResult?.evacuation_dots ?? [];
        if (dots.length === 0) return null;
        const reds = dots.filter((d) => d.status === "red").length;
        return (
          <div
            className={`rounded-lg px-2 py-1.5 text-[11px] ${
              reds > 0
                ? "border border-red-500/20 bg-red-500/10 text-red-300 light:text-red-700"
                : "border border-emerald-500/20 bg-emerald-500/10 text-emerald-300 light:text-emerald-700"
            }`}
          >
            {reds > 0
              ? `Dojścia: ${reds} pkt poza limitem (${state.circulation.max_dist_single_m}/${state.circulation.max_dist_multi_m}m)`
              : `Dojścia: OK (limity ${state.circulation.max_dist_single_m}/${state.circulation.max_dist_multi_m}m)`}
          </div>
        );
      })()}
    </section>
  );
}
