"use client";

import { CheckCircle2, XCircle, AlertCircle } from "lucide-react";
import { useSession } from "../state/SessionContext";
import { apartmentValidationByIndex } from "../lib/deriveStatus";

export default function ValidationSection() {
  const { state, selectApartment } = useSession();
  const { validation, layoutResult } = state;

  if (!validation) {
    return (
      <section className="space-y-2 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Walidacja</h2>
        <p className="text-xs text-zinc-600">Wygeneruj układ, żeby zobaczyć wynik walidacji.</p>
      </section>
    );
  }

  const byId = apartmentValidationByIndex(layoutResult, validation);

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <div className="flex items-center justify-between">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Walidacja</h2>
        <span
          className={`rounded-md px-2 py-0.5 font-mono text-xs font-medium ${
            validation.score >= 90
              ? "bg-emerald-500/15 text-emerald-400"
              : validation.score >= 60
                ? "bg-amber-500/15 text-amber-400"
                : "bg-red-500/15 text-red-400"
          }`}
        >
          {validation.score}/100
        </span>
      </div>

      <ul className="space-y-1 text-xs">
        {validation.wt_rules.map((rule, i) => (
          <li
            key={`${rule.code}-${i}`}
            className={`flex gap-1.5 rounded-lg px-2 py-1.5 ${
              rule.passed ? "text-zinc-500" : "bg-red-500/10 text-red-300 light:text-red-700"
            }`}
          >
            {rule.passed ? (
              <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-500" />
            ) : (
              <XCircle size={14} className="mt-0.5 shrink-0 text-red-400" />
            )}
            <span>
              <span className="font-medium text-zinc-400">{rule.code}</span> {rule.detail}
            </span>
          </li>
        ))}

        {!validation.communication_all_connected &&
          validation.communication_issues.map((issue, i) => (
            <li key={`comm-${i}`} className="flex gap-1.5 rounded-lg bg-red-500/10 px-2 py-1.5 text-red-300 light:text-red-700">
              <XCircle size={14} className="mt-0.5 shrink-0 text-red-400" />
              <span>{issue}</span>
            </li>
          ))}
      </ul>

      {layoutResult && layoutResult.apartments.length > 0 && (
        <div className="space-y-1">
          <h3 className="mt-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Mieszkania</h3>
          <ul className="space-y-1 text-xs">
            {layoutResult.apartments.map((apt) => {
              const v = byId.get(apt.id);
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
    </section>
  );
}
