"use client";

import dynamic from "next/dynamic";
import { sampleBspResult } from "./bsp/sampleData";

const CanvasEditor = dynamic(() => import("./CanvasEditor"), { ssr: false });

export default function Home() {
  return (
    <main className="h-screen w-screen overflow-hidden bg-neutral-900 text-white">
      <CanvasEditor bspResult={sampleBspResult} />
    </main>
  );
}
