import { useSession } from "../state/SessionContext";
import dynamic from "next/dynamic";

const SolarMap = dynamic(() => import("./SolarMap"), {
  ssr: false,
  loading: () => <div className="h-[120px] w-full rounded bg-neutral-800 animate-pulse flex items-center justify-center text-neutral-500 text-xs">Ładowanie mapy...</div>,
});

export default function SolarSection() {
  const { state, setGps, setAnalysisDate, setIsDowntown, runSolarAnalysis } = useSession();

  const hasResult = !!state.solarResult;
  const canAnalyze = !!state.layoutResult;

  return (
    <section className="space-y-3 border-b border-neutral-700 pb-4 mt-4">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-400">Analiza nasłonecznienia</h2>

      <div className="space-y-2 text-sm text-neutral-300">
        <div>
          <label className="mb-1 block text-xs">Lokalizacja (kliknij by zmienić):</label>
          <div className="h-[120px] w-full overflow-hidden rounded bg-neutral-800">
            <SolarMap lat={state.gps.lat} lng={state.gps.lng} onChange={setGps} />
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs">Data analizy:</label>
          <input
            type="date"
            className="w-full rounded border border-neutral-700 bg-neutral-800 px-2 py-1 text-xs text-white outline-none focus:border-blue-500"
            value={state.analysisDate}
            onChange={(e) => setAnalysisDate(e.target.value)}
          />
        </div>

        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={state.isDowntown}
            onChange={(e) => setIsDowntown(e.target.checked)}
            className="rounded border-neutral-700 bg-neutral-800"
          />
          Zabudowa śródmiejska (WT §13 wymóg 1.5h zamiast 3h)
        </label>
      </div>

      <button
        onClick={() => void runSolarAnalysis()}
        disabled={!canAnalyze || state.isLoading}
        className="w-full rounded bg-yellow-600 px-3 py-2 text-sm font-medium text-white hover:bg-yellow-500 disabled:opacity-40"
      >
        {state.isLoading ? "Analizuję..." : "▶ Analiza solarna (PVLib)"}
      </button>

      {hasResult && state.solarResult && (
        <div className="mt-2 max-h-[150px] overflow-y-auto rounded bg-neutral-800 p-2 text-xs text-neutral-300">
          <div className="grid grid-cols-4 gap-1 border-b border-neutral-700 pb-1 font-semibold text-neutral-400">
            <span>Apt</span>
            <span>Kier.</span>
            <span>Godz.</span>
            <span>WT</span>
          </div>
          {state.solarResult.facades.map((f, i) => (
            <div key={i} className="grid grid-cols-4 gap-1 border-b border-neutral-700/50 py-1 last:border-0">
              <span className="truncate" title={f.apartment_id}>{f.apartment_id}</span>
              <span>{f.orientation}</span>
              <span>{f.hours_total.toFixed(1)}h</span>
              <span className={f.meets_wt ? "text-green-400" : "text-red-400"}>
                {f.meets_wt ? "OK" : "❌"}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
