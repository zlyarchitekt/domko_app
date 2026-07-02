"use client";

import { useState } from "react";
import { LayoutGrid, Sun, Sparkles, Download, Play, AlertTriangle, Boxes, Moon } from "lucide-react";
import { useSession } from "../state/SessionContext";
import FootprintSection from "./FootprintSection";
import ProgramSection from "./ProgramSection";
import CirculationSection from "./CirculationSection";
import ValidationSection from "./ValidationSection";
import SolarSection from "./SolarSection";
import OptimizerSection from "./OptimizerSection";
import { ExportSection } from "./ExportSection";

const TABS = [
  { key: "layout", label: "Układ", icon: LayoutGrid },
  { key: "solar", label: "Słońce", icon: Sun },
  { key: "optimizer", label: "Optymalizacja", icon: Sparkles },
  { key: "export", label: "Eksport", icon: Download },
] as const;

export default function Sidebar() {
  const { state, regenerate, toggleTheme } = useSession();
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]["key"]>("layout");

  return (
    <div className="h-full shrink-0 p-3">
      <aside className="flex h-full w-[344px] flex-col overflow-hidden rounded-2xl border border-zinc-800/80 bg-zinc-900/70 shadow-panel backdrop-blur-xl light:border-zinc-200 light:bg-white/80 light:shadow-[0_1px_0_0_rgba(0,0,0,0.02)_inset,0_12px_32px_-12px_rgba(0,0,0,0.12)]">
        <div className="flex shrink-0 items-center gap-2 border-b border-zinc-800/80 px-4 py-3.5 light:border-zinc-200">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-500/15 text-accent-400">
            <Boxes size={16} strokeWidth={2} />
          </div>
          <div className="flex-1">
            <h1 className="text-[13px] font-semibold leading-tight tracking-tight text-zinc-100 light:text-zinc-900">DOMKO</h1>
            <p className="text-[10px] leading-tight text-zinc-500">generator kondygnacji</p>
          </div>
          <button
            onClick={toggleTheme}
            title={state.theme === "dark" ? "Przełącz na tryb jasny" : "Przełącz na tryb ciemny"}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-zinc-800/70 hover:text-zinc-200 light:text-zinc-500 light:hover:bg-zinc-100 light:hover:text-zinc-700"
          >
            {state.theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
          </button>
        </div>

        <nav className="flex shrink-0 gap-1 border-b border-zinc-800/80 p-2 light:border-zinc-200">
          {TABS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`flex flex-1 flex-col items-center gap-1 rounded-lg px-1.5 py-1.5 text-[10px] font-medium transition-colors ${
                activeTab === key
                  ? "bg-accent-500/15 text-accent-400"
                  : "text-zinc-500 hover:bg-zinc-800/60 hover:text-zinc-300 light:hover:bg-zinc-100 light:hover:text-zinc-700"
              }`}
            >
              <Icon size={15} strokeWidth={2} />
              <span className="whitespace-nowrap">{label}</span>
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-y-auto px-3.5 py-3.5">
          {activeTab === "layout" && (
            <div className="flex flex-col gap-3 pb-6">
              <FootprintSection />
              <ProgramSection />
              <CirculationSection />
              <SolarSection />
              <OptimizerSection />

              <button
                onClick={() => void regenerate()}
                disabled={!state.footprint || state.isLoading || state.mode === "draw"}
                className="group flex w-full items-center justify-center gap-2 rounded-xl bg-accent-500 px-3 py-2.5 text-[13px] font-medium text-white shadow-glow transition-all hover:bg-accent-400 active:scale-[0.98] disabled:cursor-not-allowed disabled:bg-zinc-800 disabled:text-zinc-500 disabled:shadow-none light:disabled:bg-zinc-200 light:disabled:text-zinc-400"
                title={
                  state.mode === "draw"
                    ? "Zakończ rysowanie obrysu zanim wygenerujesz układ"
                    : !state.footprint
                      ? "Narysuj lub wgraj obrys DXF, by wygenerować podział"
                      : "Kliknij, aby przeliczyć i wygenerować układ na rzucie"
                }
              >
                <Play size={14} strokeWidth={2.5} className="transition-transform group-active:scale-90" />
                {state.isLoading ? "Generuję…" : "Generuj układ"}
              </button>

              {state.error && (
                <div className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-3 py-2.5 text-xs text-red-300 light:text-red-700">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                  <span>{state.error}</span>
                </div>
              )}

              <ValidationSection />
            </div>
          )}

          {activeTab === "solar" && (
            <div className="pb-6">
              <SolarSection />
            </div>
          )}
          {activeTab === "optimizer" && (
            <div className="pb-6">
              <OptimizerSection />
            </div>
          )}
          {activeTab === "export" && (
            <div className="pb-6">
              <ExportSection />
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
