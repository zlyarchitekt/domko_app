"use client";

import { CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { useSession } from "../state/SessionContext";
import { apartmentValidationByIndex } from "../lib/deriveStatus";

export default function IterationsSidebar() {
  const { state, selectCageIteration, activeCageSeed, selectUnitIteration, activeUnitSeed, selectApartment } =
    useSession();
  const { validation, layoutResult } = state;

  const hasCageIterations = (state.circulationResult?.cage_iterations?.length ?? 0) > 0;
  const hasUnitIterations = state.lastIterations.length > 0;
  const apartmentsById = apartmentValidationByIndex(layoutResult, validation);

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
        {/* Uwagi per mieszkanie — przeniesione z lewego panelu Walidacja
            (user 2026-07-11: "uwagi dotyczące mieszkań przerzuć do prawego
            paska"). Klik zaznacza mieszkanie na canvasie, jak wcześniej. */}
        {layoutResult && layoutResult.apartments.length > 0 && (
          <div className="space-y-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
              Uwagi mieszkań ({layoutResult.apartments.length})
            </div>
            <ul className="space-y-1 text-xs">
              {layoutResult.apartments.map((apt) => {
                const v = apartmentsById.get(apt.id);
                const isSelected = state.selectedApartmentId === apt.id;
                const hasError = v && v.errors.length > 0;
                const hasWarning = v && !hasError && v.warnings.length > 0;
                return (
                  <li key={apt.id}>
                    <button
                      onClick={() => selectApartment(isSelected ? null : apt.id)}
                      className={`flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-zinc-800/70 light:hover:bg-zinc-100 ${
                        isSelected ? "bg-zinc-800/70 ring-1 ring-inset ring-accent-500/50 light:bg-zinc-100" : ""
                      }`}
                    >
                      {hasError ? (
                        <XCircle size={14} className="shrink-0 text-red-400" />
                      ) : hasWarning ? (
                        <AlertCircle size={14} className="shrink-0 text-amber-400" />
                      ) : (
                        <CheckCircle2 size={14} className="shrink-0 text-emerald-500" />
                      )}
                      <span className="flex-1 text-zinc-300 light:text-zinc-700">
                        {apt.type} · <span className="font-mono">{apt.area_m2.toFixed(1)} m²</span>
                      </span>
                    </button>
                    {v && (v.errors.length > 0 || v.warnings.length > 0) && (
                      <div className="ml-6 space-y-0.5 py-1 text-[11px]">
                        {v.errors.map((e, i) => (
                          <div key={`e-${i}`} className="text-red-400">
                            {e}
                          </div>
                        ))}
                        {v.warnings.map((w, i) => (
                          <div key={`w-${i}`} className="text-amber-400">
                            {w}
                          </div>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </aside>
    </div>
  );
}
