"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import { useSession } from "../state/SessionContext";

export default function ValidationSection() {
  const { state } = useSession();
  const { validation } = state;

  if (!validation) {
    return (
      <section className="space-y-2 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
        <h2 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">Walidacja</h2>
        <p className="text-xs text-zinc-600">Wygeneruj układ, żeby zobaczyć wynik walidacji.</p>
      </section>
    );
  }

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

      {/* Per-mieszkaniowe uwagi (błędy/ostrzeżenia + lista mieszkań) przeniesione
          do prawego paska (IterationsSidebar) -- user 2026-07-11. */}
    </section>
  );
}
