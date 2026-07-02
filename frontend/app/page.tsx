"use client";

import dynamic from "next/dynamic";
import { SessionProvider } from "./state/SessionContext";
import Sidebar from "./components/Sidebar";

const CanvasEditor = dynamic(() => import("./CanvasEditor"), { ssr: false });

export default function Home() {
  return (
    <SessionProvider>
      <main className="flex h-screen w-screen overflow-hidden bg-neutral-900 text-white">
        <Sidebar />
        <div className="relative flex-1">
          <CanvasEditor />
        </div>
      </main>
    </SessionProvider>
  );
}
