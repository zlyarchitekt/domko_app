import { useSession } from "../state/SessionContext";

export default function OptimizerSection() {
  const { state, runOptimizer, setActiveVariant, applyVariant } = useSession();

  const hasVariants = state.optimizerVariants.length > 0;
  const canOptimize = !!state.footprint && state.program.length > 0;

  return (
    <section className="space-y-3 border-b border-neutral-700 pb-4 mt-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Optymalizator Układu</h2>

      <div className="space-y-2 text-sm text-neutral-300">
        <p className="text-xs text-neutral-400">
          Automatycznie znajduje wariant o najlepszym nasłonecznieniu (algorytm genetyczny).
        </p>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => void runOptimizer()}
          disabled={!canOptimize || state.isOptimizing}
          className="flex-1 rounded bg-purple-600 px-3 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:opacity-40"
        >
          {state.isOptimizing ? "Optymalizuję..." : "▶ Uruchom Optymalizator"}
        </button>
      </div>

      {hasVariants && !state.isOptimizing && (
        <div className="mt-3 space-y-2">
          <h3 className="text-xs font-semibold text-neutral-300">Top {state.optimizerVariants.length} warianty:</h3>
          <div className="grid grid-cols-1 gap-2">
            {state.optimizerVariants.map((v) => {
              const isActive = state.activeVariantId === v.id;
              return (
                <div
                  key={v.id}
                  onClick={() => setActiveVariant(v.id)}
                  className={`cursor-pointer rounded border p-2 text-xs transition-colors ${
                    isActive
                      ? "border-purple-500 bg-purple-900/30 text-purple-100"
                      : "border-neutral-700 bg-neutral-800 text-neutral-300 hover:border-neutral-500"
                  }`}
                >
                  <div className="flex justify-between font-medium">
                    <span>Wariant #{v.rank}</span>
                    <span className={v.metrics.communication_ok ? "text-green-400" : "text-red-400"}>
                      WT: {(v.metrics.wt_compliance * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between text-neutral-400">
                    <span>Apt: {v.metrics.total_apartments}</span>
                    <span>Słońce: {v.metrics.solar_score.toFixed(1)}h</span>
                  </div>
                  {!v.metrics.communication_ok && (
                    <div className="mt-1 text-red-400">⚠ problem z dostępem do klatki</div>
                  )}
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      applyVariant(v.id);
                    }}
                    className="mt-2 w-full rounded bg-neutral-700 px-2 py-1 text-xs text-white hover:bg-neutral-600"
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
