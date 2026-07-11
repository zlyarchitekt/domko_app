"use client";

import dynamic from "next/dynamic";
import { SessionProvider } from "./state/SessionContext";
import Sidebar from "./components/Sidebar";
import IterationsSidebar from "./components/IterationsSidebar";

const CanvasEditor = dynamic(() => import("./CanvasEditor"), { ssr: false });

export default function Home() {
  return (
    <SessionProvider>
      <main className="flex h-screen w-screen overflow-hidden bg-zinc-950 text-white light:bg-zinc-100 light:text-zinc-900">
        <Sidebar />
        <div className="relative flex-1 bg-[radial-gradient(circle_at_top_left,rgba(91,141,239,0.06),transparent_45%)]">
          <CanvasEditor />
        </div>
        <IterationsSidebar />
      </main>
    </SessionProvider>
  );
}
