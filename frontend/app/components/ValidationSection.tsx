"use client";

import { useSession } from "../state/SessionContext";
import { apartmentValidationByIndex } from "../lib/deriveStatus";

export default function ValidationSection() {
  const { state, selectApartment } = useSession();
  const { validation, layoutResult } = state;

  if (!validation) {
    return (
      <section className="space-y-2 pb-4">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Walidacja</h2>
        <p className="text-xs text-neutral-500">Wygeneruj układ, żeby zobaczyć wynik walidacji.</p>
      </section>
    );
  }

  const byId = apartmentValidationByIndex(layoutResult, validation);

  return (
    <section className="space-y-2 pb-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Walidacja</h2>
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            validation.score >= 90
              ? "bg-green-900 text-green-300"
              : validation.score >= 60
                ? "bg-yellow-900 text-yellow-300"
                : "bg-red-900 text-red-300"
          }`}
        >
          {validation.score}/100
        </span>
      </div>

      <ul className="space-y-1 text-xs">
        {validation.wt_rules.map((rule, i) => (
          <li
            key={`${rule.code}-${i}`}
            className={`flex gap-1.5 rounded px-2 py-1 ${
              rule.passed ? "text-green-400" : "text-red-400 bg-red-950/40"
            }`}
          >
            <span>{rule.passed ? "✅" : "🔴"}</span>
            <span>
              <span className="font-medium">{rule.code}</span> {rule.detail}
            </span>
          </li>
        ))}

        {!validation.communication_all_connected &&
          validation.communication_issues.map((issue, i) => (
            <li key={`comm-${i}`} className="flex gap-1.5 rounded bg-red-950/40 px-2 py-1 text-red-400">
              <span>🔴</span>
              <span>{issue}</span>
            </li>
          ))}
      </ul>

      {layoutResult && layoutResult.apartments.length > 0 && (
        <div className="space-y-1">
          <h3 className="mt-2 text-[11px] uppercase tracking-wide text-neutral-500">Mieszkania</h3>
          <ul className="space-y-1 text-xs">
            {layoutResult.apartments.map((apt) => {
              const v = byId.get(apt.id);
              const isSelected = state.selectedApartmentId === apt.id;
              const icon = !v ? "✅" : v.errors.length > 0 ? "🔴" : v.warnings.length > 0 ? "⚠️" : "✅";
              return (
                <li key={apt.id}>
                  <button
                    onClick={() => selectApartment(isSelected ? null : apt.id)}
                    className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-neutral-700 ${
                      isSelected ? "bg-neutral-700 ring-1 ring-blue-500" : ""
                    }`}
                  >
                    <span>{icon}</span>
                    <span className="flex-1">
                      {apt.type} · {apt.area_m2.toFixed(1)} m²
                    </span>
                  </button>
                  {v && (v.errors.length > 0 || v.warnings.length > 0) && (
                    <div className="ml-6 space-y-0.5 text-[11px]">
                      {v.errors.map((e, i) => (
                        <div key={`e-${i}`} className="text-red-400">
                          {e}
                        </div>
                      ))}
                      {v.warnings.map((w, i) => (
                        <div key={`w-${i}`} className="text-yellow-400">
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
