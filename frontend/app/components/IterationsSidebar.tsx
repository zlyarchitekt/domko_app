"use client";

import { useSession } from "../state/SessionContext";

export default function IterationsSidebar() {
  const { state, selectCageIteration, activeCageSeed, selectUnitIteration, activeUnitSeed } = useSession();

  const hasCageIterations = (state.circulationResult?.cage_iterations?.length ?? 0) > 0;
  const hasUnitIterations = state.lastIterations.length > 0;

  return (
    <div className="h-full shrink-0 p-3">
      <aside className="flex h-full w-[260px] flex-col gap-3 overflow-y-auto rounded-2xl border border-zinc-800/80 bg-zinc-900/70 p-3 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80 light:shadow-[0_1px_0_0_rgba(0,0,0,0.02)_inset,0_12px_32px_-12px_rgba(0,0,0,0.12)]">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400 light:text-zinc-500">
          Iteracje
        </div>

        {!hasCageIterations && !hasUnitIterations && (
          <div className="text-[11px] leading-relaxed text-zinc-600">
            Brak iteracji. Użyj <span className="text-zinc-400">Rozmieść iteracyjnie</span> (klatki) lub{" "}
            <span className="text-zinc-400">Podziel na mieszkania</span> (mieszkania), żeby zobaczyć tu warianty
            do porównania.
          </div>
        )}

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
            {(() => {
              // Ta sama reguła co backend (pick_best_iteration): najlepsza
              // WAŻNA iteracja (hard_valid), fallback najlepsza w ogóle.
              const anyValid = state.lastIterations.some((o) => o.hard_valid !== false);
              const pool = state.lastIterations.filter((o) => !anyValid || o.hard_valid !== false);
              const bestSeed = pool.reduce((a, b) => (b.score < a.score ? b : a)).seed;
              return (
                <>
                  {!anyValid && (
                    <div className="rounded bg-amber-500/10 px-2 py-1 text-[10px] leading-snug text-amber-400">
                      Żadna iteracja nie spełnia zakazów (styk z komunikacją i elewacją, proporcje ≤ 1:3).
                      Pokazano najlepszą mimo naruszeń.
                    </div>
                  )}
                  {state.lastIterations.map((m) => {
                    const isBest = m.seed === bestSeed;
                    const isActive = activeUnitSeed === m.seed || (activeUnitSeed === null && isBest);
                    const invalid = m.hard_valid === false;
                    return (
                      <button
                        key={m.seed}
                        onClick={() => selectUnitIteration(m.seed)}
                        title={
                          invalid
                            ? `Narusza zakaz: ${(m.hard_violations ?? []).join("; ") || "mieszkanie bez styku z komunikacją/elewacją lub proporcje > 1:3"}`
                            : undefined
                        }
                        className={`flex w-full items-center justify-between rounded px-2 py-0.5 font-mono text-[11px] transition-colors ${
                          isBest ? "text-accent-400" : "text-zinc-500"
                        } ${isActive ? "bg-accent-500/15 ring-1 ring-inset ring-accent-500/40" : "hover:bg-zinc-800/50"}`}
                      >
                        <span>#{m.seed}{isBest ? " ★" : ""}{invalid ? <span className="text-amber-400"> ⚠</span> : ""}</span>
                        <span>{m.units_count} szt.</span>
                        <span>odchylenie {m.score.toFixed(3)}</span>
                      </button>
                    );
                  })}
                </>
              );
            })()}
          </div>
        )}
      </aside>
    </div>
  );
}
