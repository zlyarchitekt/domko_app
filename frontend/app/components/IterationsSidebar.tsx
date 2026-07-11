"use client";

import { useSession } from "../state/SessionContext";

export default function IterationsSidebar() {
  const { state, selectCageIteration, activeCageSeed, selectUnitIteration, activeUnitSeed } = useSession();

  const hasCageIterations = (state.circulationResult?.cage_iterations?.length ?? 0) > 0;
  const hasUnitIterations = state.lastIterations.length > 0;

  if (!hasCageIterations && !hasUnitIterations) return null;

  return (
    <div className="h-full shrink-0 p-3">
      <aside className="flex h-full w-[260px] flex-col gap-3 overflow-y-auto rounded-2xl border border-zinc-800/80 bg-zinc-900/70 p-3 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80 light:shadow-[0_1px_0_0_rgba(0,0,0,0.02)_inset,0_12px_32px_-12px_rgba(0,0,0,0.12)]">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 light:text-zinc-500">
          Iteracje
        </div>

        {hasCageIterations && (
          <div className="space-y-0.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Iteracje klatek ({state.circulationResult!.cage_iterations!.length})
            </div>
            <div className="text-[9px] text-zinc-600">niżej = lepiej, 0 = idealne dopasowanie do wag</div>
            {state.circulationResult!.cage_iterations!.map((m) => {
              const isBest = m.seed === (state.circulationResult!.cage_best_seed ?? -1);
              const isActive = activeCageSeed === m.seed || (activeCageSeed === null && isBest);
              return (
                <button
                  key={m.seed}
                  onClick={() => selectCageIteration(m.seed)}
                  className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                    isBest ? "text-accent-400" : "text-zinc-500"
                  } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
                >
                  <span>#{m.seed}{isBest ? " ★" : ""}</span>
                  <span>{m.cages_count} klatek</span>
                  <span>odchylenie {m.score.toFixed(3)}</span>
                </button>
              );
            })}
          </div>
        )}

        {hasUnitIterations && (
          <div className="space-y-0.5">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Iteracje mieszkań ({state.lastIterations.length})
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
      </aside>
    </div>
  );
}
