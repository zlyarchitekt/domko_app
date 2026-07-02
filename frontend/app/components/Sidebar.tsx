"use client";

import { useState } from "react";
import { useSession } from "../state/SessionContext";
import FootprintSection from "./FootprintSection";
import ProgramSection from "./ProgramSection";
import CirculationSection from "./CirculationSection";
import ValidationSection from "./ValidationSection";
import SolarSection from "./SolarSection";
import OptimizerSection from "./OptimizerSection";
import { ExportSection } from "./ExportSection";

export default function Sidebar() {
  const { state, regenerate } = useSession();
  const [activeTab, setActiveTab] = useState("layout");

  return (
    <aside className="flex h-full w-[360px] shrink-0 flex-col overflow-y-auto border-r border-neutral-800 bg-neutral-900 px-4 py-4">
      <h1 className="mb-2 text-sm font-bold tracking-wide text-white">DOMKO_APP</h1>

      <div className="flex gap-4 border-b border-neutral-700 pb-2 mb-4 overflow-x-auto text-xs shrink-0">
        <button onClick={() => setActiveTab("layout")} className={`pb-1 whitespace-nowrap ${activeTab === "layout" ? "text-blue-400 border-b-2 border-blue-400 font-bold" : "text-gray-400"}`}>Warianty układu</button>
        <button onClick={() => setActiveTab("solar")} className={`pb-1 whitespace-nowrap ${activeTab === "solar" ? "text-orange-400 border-b-2 border-orange-400 font-bold" : "text-gray-400"}`}>Słońce</button>
        <button onClick={() => setActiveTab("optimizer")} className={`pb-1 whitespace-nowrap ${activeTab === "optimizer" ? "text-purple-400 border-b-2 border-purple-400 font-bold" : "text-gray-400"}`}>Optymalizacja</button>
        <button onClick={() => setActiveTab("export")} className={`pb-1 whitespace-nowrap ${activeTab === "export" ? "text-green-400 border-b-2 border-green-400 font-bold" : "text-gray-400"}`}>Eksport</button>
      </div>

      {activeTab === "layout" && (
        <div className="flex flex-col gap-2 pb-10">
          <FootprintSection />
          <ProgramSection />
          <CirculationSection />
          <SolarSection />
          <OptimizerSection />

          <button
            onClick={() => void regenerate()}
            disabled={!state.footprint || state.isLoading || state.mode === "draw"}
            className="my-3 w-full rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
            title={state.mode === "draw" ? "Zakończ rysowanie obrysu zanim wygenerujesz układ" : !state.footprint ? "Narysuj lub wgraj obrys DXF, by wygenerować podział" : "Kliknij, aby przeliczyć i wygenerować układ na rzucie"}
          >
            {state.isLoading ? "Generuję…" : "▶ Generuj układ"}
          </button>

          {state.error && (
            <div className="mb-3 rounded bg-red-950/60 px-3 py-2 text-xs text-red-300">{state.error}</div>
          )}

          <ValidationSection />
        </div>
      )}

      {activeTab === "solar" && <div className="pb-10"><SolarSection /></div>}
      {activeTab === "optimizer" && <div className="pb-10"><OptimizerSection /></div>}
      {activeTab === "export" && <div className="pb-10"><ExportSection /></div>}
    </aside>
  );
}
