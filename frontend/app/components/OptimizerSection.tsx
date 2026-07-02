import { Sparkles, AlertTriangle } from "lucide-react";
import { useSession } from "../state/SessionContext";

export default function OptimizerSection() {
  const { state, runOptimizer, setActiveVariant, applyVariant } = useSession();

  const hasVariants = state.optimizerVariants.length > 0;
  const canOptimize = !!state.footprint && state.program.length > 0;

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <h2 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        <Sparkles size={12} className="text-violet-400" />
        Optymalizator układu
      </h2>

      <p className="text-xs text-zinc-500">
        Automatycznie znajduje wariant o najlepszym nasłonecznieniu (algorytm genetyczny).
      </p>

      <button
        onClick={() => void runOptimizer()}
        disabled={!canOptimize || state.isOptimizing}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-violet-600/90 px-3 py-2 text-xs font-medium text-white transition-all hover:bg-violet-500 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
      >
        <Sparkles size={13} />
        {state.isOptimizing ? "Optymalizuję..." : "Uruchom optymalizator"}
      </button>

      {hasVariants && !state.isOptimizing && (
        <div className="space-y-2">
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">
            Top {state.optimizerVariants.length} warianty
          </h3>
          <div className="grid grid-cols-1 gap-1.5">
            {state.optimizerVariants.map((v) => {
              const isActive = state.activeVariantId === v.id;
              return (
                <div
                  key={v.id}
                  onClick={() => setActiveVariant(v.id)}
                  className={`cursor-pointer rounded-lg border p-2.5 text-xs transition-colors ${
                    isActive
                      ? "border-violet-500/40 bg-violet-500/10 text-violet-100 light:text-violet-800"
                      : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 light:border-zinc-200 light:bg-zinc-50 light:hover:border-zinc-300"
                  }`}
                >
                  <div className="flex justify-between font-medium">
                    <span>Wariant #{v.rank}</span>
                    <span className={`font-mono ${v.metrics.communication_ok ? "text-emerald-400" : "text-red-400"}`}>
                      WT: {(v.metrics.wt_compliance * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between font-mono text-zinc-500">
                    <span>Apt: {v.metrics.total_apartments}</span>
                    <span>Słońce: {v.metrics.solar_score.toFixed(1)}h</span>
                  </div>
                  {!v.metrics.communication_ok && (
                    <div className="mt-1 flex items-center gap-1 text-red-400">
                      <AlertTriangle size={11} />
                      problem z dostępem do klatki
                    </div>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      applyVariant(v.id);
                    }}
                    className="mt-2 w-full rounded-md bg-zinc-800/80 px-2 py-1 text-xs text-zinc-200 transition-colors hover:bg-zinc-700 light:bg-white light:text-zinc-700 light:hover:bg-zinc-100"
                  >
                    Zastosuj ten układ
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
