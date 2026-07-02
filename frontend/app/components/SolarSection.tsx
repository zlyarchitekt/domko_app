import { Sun, MapPin, CalendarDays, Check, X } from "lucide-react";
import { useSession } from "../state/SessionContext";
import dynamic from "next/dynamic";

const SolarMap = dynamic(() => import("./SolarMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[120px] w-full animate-pulse items-center justify-center rounded-lg bg-zinc-900/70 text-xs text-zinc-600 light:bg-zinc-100">
      Ładowanie mapy...
    </div>
  ),
});

export default function SolarSection() {
  const { state, setGps, setAnalysisDate, setIsDowntown, runSolarAnalysis } = useSession();

  const hasResult = !!state.solarResult;
  const canAnalyze = !!state.layoutResult;

  return (
    <section className="space-y-2.5 rounded-xl border border-zinc-800/70 bg-zinc-950/40 p-3 light:border-zinc-200 light:bg-white">
      <h2 className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
        <Sun size={12} className="text-amber-400" />
        Analiza nasłonecznienia
      </h2>

      <div className="space-y-2.5 text-sm text-zinc-300">
        <div>
          <label className="mb-1 flex items-center gap-1 text-[11px] text-zinc-500">
            <MapPin size={11} />
            Lokalizacja (kliknij by zmienić)
          </label>
          <div className="h-[120px] w-full overflow-hidden rounded-lg border border-zinc-800">
            <SolarMap lat={state.gps.lat} lng={state.gps.lng} onChange={setGps} />
          </div>
        </div>

        <div>
          <label className="mb-1 flex items-center gap-1 text-[11px] text-zinc-500">
            <CalendarDays size={11} />
            Data analizy
          </label>
          <input
            type="date"
            className="w-full rounded-lg border border-zinc-700/50 bg-zinc-800/70 px-2 py-1.5 text-xs text-white outline-none focus:border-accent-500/60 light:border-zinc-300 light:bg-white light:text-zinc-900"
            value={state.analysisDate}
            onChange={(e) => setAnalysisDate(e.target.value)}
          />
        </div>

        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <input
            type="checkbox"
            checked={state.isDowntown}
            onChange={(e) => setIsDowntown(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-zinc-600 bg-zinc-800 text-accent-500 focus:ring-accent-500/40 focus:ring-offset-0"
          />
          Zabudowa śródmiejska (WT §13 wymóg 1.5h zamiast 3h)
        </label>
      </div>

      <button
        onClick={() => void runSolarAnalysis()}
        disabled={!canAnalyze || state.isLoading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-amber-500/90 px-3 py-2 text-xs font-medium text-zinc-950 transition-all hover:bg-amber-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
      >
        <Sun size={13} strokeWidth={2.5} />
        {state.isLoading ? "Analizuję..." : "Analiza solarna (PVLib)"}
      </button>

      {hasResult && state.solarResult && (
        <div className="max-h-[150px] overflow-y-auto rounded-lg bg-zinc-900/70 p-2 text-xs text-zinc-400 light:bg-zinc-100">
          <div className="grid grid-cols-4 gap-1 border-b border-zinc-800 pb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600 light:border-zinc-300">
            <span>Apt</span>
            <span>Kier.</span>
            <span>Godz.</span>
            <span>WT</span>
          </div>
          {state.solarResult.facades.map((f, i) => (
            <div key={i} className="grid grid-cols-4 gap-1 border-b border-zinc-800/50 py-1 font-mono text-[11px] last:border-0 light:border-zinc-200">
              <span className="truncate" title={f.apartment_id}>
                {f.apartment_id}
              </span>
              <span>{f.orientation}</span>
              <span>{f.hours_total.toFixed(1)}h</span>
              <span className={f.meets_wt ? "flex items-center text-emerald-400" : "flex items-center text-red-400"}>
                {f.meets_wt ? <Check size={12} /> : <X size={12} />}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
