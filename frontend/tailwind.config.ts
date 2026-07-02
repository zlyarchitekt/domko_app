import type { Config } from "tailwindcss";
import plugin from "tailwindcss/plugin";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        accent: {
          DEFAULT: "#5b8def",
          50: "#eef4ff",
          400: "#7fa8f5",
          500: "#5b8def",
          600: "#3f6fd6",
          700: "#3258ac",
        },
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 12px 32px -12px rgba(0,0,0,0.6)",
        glow: "0 0 0 1px rgba(91,141,239,0.4), 0 0 24px -4px rgba(91,141,239,0.35)",
      },
    },
  },
  plugins: [
    // Default theme is dark (existing unprefixed classes, unchanged).
    // `light:` overrides apply when an ancestor carries the `.light` class,
    // toggled by SessionContext's theme state — see app/state/SessionContext.tsx.
    plugin(({ addVariant }) => {
      addVariant("light", ":where(.light, .light *) &");
    }),
  ],
};

export default config;
