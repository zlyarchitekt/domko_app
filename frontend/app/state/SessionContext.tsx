"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from "react";
import * as api from "../lib/api";

export type Point2D = { x: number; y: number };

export type EditorMode =
  | "idle"
  | "draw"
  | "edit-vertices"
  | "edit-lines"
  | "edit-circulation"
  | "edit-corridor-centerline"
  | "draw-cage"
  | "draw-corridor";

export interface ProgramRow {
  id: string;
  type: string;
  /** Udział w łącznej liczbie mieszkań (0-100), np. 40 = 40%. */
  percentage: number;
  area_min_m2: number;
  area_max_m2: number;
  /** Pochodne, przeliczane w reducerze z percentage/area_min/area_max/totalUnits
   * — nigdy nie edytowane bezpośrednio. Trzymane na ProgramRow (nie liczone
   * dopiero w komponencie), bo tak wyglądał kontrakt zanim doszła "struktura
   * mieszkań" (%/zakres) i wszystkie call sites (buildRequest, eksport,
   * optymalizator, walidacja) już czytają te dwie nazwy pól wprost. */
  target_count: number;
  min_area_m2: number;
  /** Min. styk mieszkań tego typu ze ścianą zewnętrzną [m] -- komponent
   * scoringu "daylight" w silniku iteracyjnym (spec §4). */
  min_facade_m: number;
}

/** Zaokrągla `percentage`% z `totalUnits` do liczby całkowitej mieszkań i
 * ustawia `min_area_m2` na środek zakresu [area_min_m2, area_max_m2] —
 * to jedyne miejsce, które liczy pochodne pola ProgramRow, wołane po
 * KAŻDEJ zmianie wierszy programu lub totalUnits, żeby te dwa źródła
 * prawdy (struktura % + zakres, kontrakt API płaski count+area) nigdy się
 * nie rozjechały. Odchył "kilka procent" dla liczby mieszkań jest
 * naturalnym skutkiem zaokrąglania (np. 17 mieszkań × 10% = 1.7 → 2, czyli
 * faktycznie 11.8% zamiast 10%) — nie ma osobnego parametru tolerancji.
 * Odchył dla metrażu to sam zakres [area_min_m2, area_max_m2] plus
 * istniejąca ±3% tolerancja dopasowania w unit_mix.py. */
function recomputeDerivedProgram(rows: ProgramRow[], totalUnits: number): ProgramRow[] {
  return rows.map((row) => ({
    ...row,
    target_count: Math.max(0, Math.round((totalUnits * row.percentage) / 100)),
    min_area_m2: (row.area_min_m2 + row.area_max_m2) / 2,
  }));
}

export interface ManualCage {
  id: string;
  ring: Point2D[];
}

export interface ManualCorridor {
  id: string;
  path: Point2D[];
}

interface SessionState {
  footprint: Point2D[] | null;
  drawingPoints: Point2D[];
  mode: EditorMode;
  program: ProgramRow[];
  totalUnits: number;
  unitWeights: api.UnitWeightsInput;
  lastIterations: api.IterationMeta[];
  derivedTotalUnits: number | null;
  netRemainderM2: number | null;
  circulation: api.CirculationSpecInput;
  circulationResult: api.CirculationResponse | null;
  manualCages: ManualCage[];
  manualCorridors: ManualCorridor[];
  hoveredManualId: string | null;
  layoutResult: api.LayoutGenerateResponse | null;
  validation: api.FullLayoutValidateResponse | null;
  typologySuggestion: api.TypologySuggestResponse | null;
  selectedTypology: string | null;
  selectedApartmentId: string | null;
  isLoading: boolean;
  error: string | null;
  solarResult: api.SolarAnalyzeResponse | null;
  gps: { lat: number; lng: number };
  analysisDate: string;
  isDowntown: boolean;
  optimizerVariants: api.OptimizerVariant[];
  activeVariantId: string | null;
  isOptimizing: boolean;
  theme: "dark" | "light";
  activeCageSeed: number | null;
  activeUnitSeed: number | null;
}

const initialCirculation: api.CirculationSpecInput = {
  corridor_width_m: 1.5,
  stair_width_m: 1.2,
  place_cage: true,
  cage_size_m: 2.5,
  cage_position: "auto",
  num_cages: 1,
  manual_cages: [],
  manual_corridors: [],
  max_dist_single_m: 20,
  max_dist_multi_m: 40,
  cage_iterations: 0,
  cage_weights: { egress: 1.0, count: 0.5, corners: 0.3, ends: 0.3, spread: 0.5 },
};

const INITIAL_TOTAL_UNITS = 10;

export const DEFAULT_UNIT_WEIGHTS: api.UnitWeightsInput = {
  size: 0.8,
  mix: 0.6,
  grid: 0.3,
  shape: 0.5,
  daylight: 0.7,
  squareness: 0.5,
  adjacency: 1.0,
};

// Domyślna struktura mieszkań: M1 10% (25-32m²) / M2 40% (38-48m²) /
// M3 40% (58-70m²) / M4 10% (72-90m²) — przy 10 mieszkaniach daje dokładnie
// 1/4/4/1 bez zaokrągleń.
const initialState: SessionState = {
  footprint: null,
  drawingPoints: [],
  mode: "idle",
  program: recomputeDerivedProgram(
    [
      { id: crypto.randomUUID(), type: "M1", percentage: 10, area_min_m2: 25, area_max_m2: 32, target_count: 0, min_area_m2: 0, min_facade_m: 3.0 },
      { id: crypto.randomUUID(), type: "M2", percentage: 40, area_min_m2: 38, area_max_m2: 48, target_count: 0, min_area_m2: 0, min_facade_m: 3.0 },
      { id: crypto.randomUUID(), type: "M3", percentage: 40, area_min_m2: 58, area_max_m2: 70, target_count: 0, min_area_m2: 0, min_facade_m: 3.0 },
      { id: crypto.randomUUID(), type: "M4", percentage: 10, area_min_m2: 72, area_max_m2: 90, target_count: 0, min_area_m2: 0, min_facade_m: 3.0 },
    ],
    INITIAL_TOTAL_UNITS
  ),
  totalUnits: INITIAL_TOTAL_UNITS,
  unitWeights: DEFAULT_UNIT_WEIGHTS,
  lastIterations: [],
  derivedTotalUnits: null,
  netRemainderM2: null,
  circulation: initialCirculation,
  circulationResult: null,
  manualCages: [],
  manualCorridors: [],
  hoveredManualId: null,
  layoutResult: null,
  validation: null,
  typologySuggestion: null,
  selectedTypology: null,
  selectedApartmentId: null,
  isLoading: false,
  error: null,
  solarResult: null,
  gps: { lat: 52.2297, lng: 21.0122 }, // Wwa
  analysisDate: new Date(new Date().getFullYear(), 2, 21).toISOString().split('T')[0], // 21 marca
  isDowntown: false,
  optimizerVariants: [],
  activeVariantId: null,
  isOptimizing: false,
  theme: "dark",
  activeCageSeed: null,
  activeUnitSeed: null,
};

type Action =
  | { type: "SET_MODE"; mode: EditorMode }
  | { type: "ADD_DRAW_POINT"; point: Point2D }
  | { type: "REMOVE_LAST_DRAW_POINT" }
  | { type: "CLEAR_DRAWING" }
  | { type: "SET_FOOTPRINT"; footprint: Point2D[] }
  | { type: "UPDATE_VERTEX"; index: number; point: Point2D }
  | { type: "SET_FOOTPRINT_POINTS"; points: Point2D[] }
  | { type: "SET_PROGRAM"; program: ProgramRow[] }
  | { type: "ADD_PROGRAM_ROW" }
  | { type: "UPDATE_PROGRAM_ROW"; id: string; patch: Partial<ProgramRow> }
  | { type: "REMOVE_PROGRAM_ROW"; id: string }
  | { type: "SET_TOTAL_UNITS"; totalUnits: number }
  | { type: "SET_UNIT_WEIGHT"; key: keyof api.UnitWeightsInput; value: number }
  | { type: "SET_ITERATION_RESULTS"; iterations: api.IterationMeta[]; derivedTotalUnits: number; netRemainderM2: number }
  | { type: "SET_CIRCULATION"; patch: Partial<api.CirculationSpecInput> }
  | { type: "SET_CIRCULATION_RESULT"; result: api.CirculationResponse | null }
  | { type: "ADD_MANUAL_CAGE"; ring: Point2D[] }
  | { type: "ADD_MANUAL_CORRIDOR"; path: Point2D[] }
  | { type: "REMOVE_MANUAL_ELEMENT"; id: string }
  | { type: "SET_HOVERED_MANUAL"; id: string | null }
  | { type: "SET_LAYOUT_RESULT"; result: api.LayoutGenerateResponse | null }
  | { type: "SET_VALIDATION"; validation: api.FullLayoutValidateResponse | null }
  | { type: "SET_TYPOLOGY_SUGGESTION"; suggestion: api.TypologySuggestResponse | null }
  | { type: "SET_SELECTED_TYPOLOGY"; typology: string | null }
  | { type: "SELECT_APARTMENT"; id: string | null }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "UPDATE_APARTMENTS"; apartments: api.ApartmentResult[] }
  | { type: "SET_SOLAR_RESULT"; result: api.SolarAnalyzeResponse | null }
  | { type: "SET_GPS"; gps: { lat: number; lng: number } }
  | { type: "SET_ANALYSIS_DATE"; date: string }
  | { type: "SET_IS_DOWNTOWN"; isDowntown: boolean }
  | { type: "SET_OPTIMIZER_VARIANTS"; variants: api.OptimizerVariant[] }
  | { type: "SET_ACTIVE_VARIANT"; id: string | null }
  | { type: "SET_IS_OPTIMIZING"; isOptimizing: boolean }
  | { type: "SET_THEME"; theme: "dark" | "light" }
  | { type: "TRANSLATE_CIRCULATION"; dx: number; dy: number }
  | { type: "RESHAPE_CIRCULATION"; result: api.ReshapeCirculationResponse }
  | { type: "SET_EVACUATION_DOTS"; dots: api.EvacuationDot[] }
  | { type: "SELECT_CAGE_ITERATION"; seed: number }
  | { type: "SELECT_UNIT_ITERATION"; seed: number }
  | { type: "RESTORE_STATE"; state: SessionState };

function reducer(state: SessionState, action: Action): SessionState {
  switch (action.type) {
    case "SET_MODE":
      // Clear in-progress drawing points whenever entering OR leaving draw mode.
      // Without this, canceling out of draw mode (clicking "Rysuj obrys" again, or
      // switching to another tool) left the un-committed dashed polygon rendered on
      // the canvas forever — idle/edit modes never read drawingPoints, so it became
      // inert visual debris rather than actually going away.
      return {
        ...state,
        mode: action.mode,
        drawingPoints:
          ["draw", "draw-cage", "draw-corridor"].includes(action.mode) ||
          ["draw", "draw-cage", "draw-corridor"].includes(state.mode)
            ? []
            : state.drawingPoints,
      };
    case "ADD_DRAW_POINT":
      return { ...state, drawingPoints: [...state.drawingPoints, action.point] };
    case "REMOVE_LAST_DRAW_POINT":
      return { ...state, drawingPoints: state.drawingPoints.slice(0, -1) };
    case "CLEAR_DRAWING":
      return { ...state, drawingPoints: [] };
    case "SET_FOOTPRINT":
      return {
        ...state,
        footprint: action.footprint,
        drawingPoints: [],
        mode: "idle",
        layoutResult: null,
        validation: null,
        circulationResult: null,
      };
    case "UPDATE_VERTEX": {
      if (!state.footprint) return state;
      const next = [...state.footprint];
      next[action.index] = action.point;
      // Mirror SET_FOOTPRINT: layoutResult/validation were computed from the old
      // outline shape, so they (and anything derived from them) are now stale.
      // Without this, "Analiza solarna"/"Uruchom Optymalizator" stayed enabled
      // (they only check layoutResult !== null) and silently sent the new
      // footprint alongside apartment geometry that no longer matches it —
      // the backend can't line facades up with apartments and returns empty
      // results with no error, which looks like "re-analysis doesn't work".
      return { ...state, footprint: next, layoutResult: null, validation: null, circulationResult: null };
    }
    case "SET_FOOTPRINT_POINTS":
      // Jak UPDATE_VERTEX wyżej: wyniki pochodne liczone ze starego obrysu
      // (layout, walidacja, komunikacja) są po tej podmianie nieaktualne.
      return {
        ...state,
        footprint: action.points,
        layoutResult: null,
        validation: null,
        circulationResult: null,
      };
    case "SET_PROGRAM":
      return { ...state, program: recomputeDerivedProgram(action.program, state.totalUnits) };
    case "ADD_PROGRAM_ROW":
      return {
        ...state,
        // 0% domyślnie, żeby nowy wiersz nie zaburzył istniejącej struktury
        // dopóki użytkownik sam nie ustawi udziału.
        program: recomputeDerivedProgram(
          [
            ...state.program,
            { id: crypto.randomUUID(), type: "M2", percentage: 0, area_min_m2: 38, area_max_m2: 48, target_count: 0, min_area_m2: 0, min_facade_m: 3.0 },
          ],
          state.totalUnits
        ),
      };
    case "UPDATE_PROGRAM_ROW":
      return {
        ...state,
        program: recomputeDerivedProgram(
          state.program.map((row) => (row.id === action.id ? { ...row, ...action.patch } : row)),
          state.totalUnits
        ),
      };
    case "REMOVE_PROGRAM_ROW":
      return {
        ...state,
        program: recomputeDerivedProgram(state.program.filter((row) => row.id !== action.id), state.totalUnits),
      };
    case "SET_TOTAL_UNITS":
      return { ...state, totalUnits: action.totalUnits, program: recomputeDerivedProgram(state.program, action.totalUnits) };
    case "SET_UNIT_WEIGHT":
      return { ...state, unitWeights: { ...state.unitWeights, [action.key]: action.value } };
    case "SET_ITERATION_RESULTS":
      return {
        ...state,
        lastIterations: action.iterations,
        derivedTotalUnits: action.derivedTotalUnits,
        netRemainderM2: action.netRemainderM2,
        // liczba pochodna zasila dotychczasowy mechanizm ≈sztuk w wierszach
        totalUnits: action.derivedTotalUnits,
        program: recomputeDerivedProgram(state.program, action.derivedTotalUnits),
      };
    case "SET_CIRCULATION":
      return { ...state, circulation: { ...state.circulation, ...action.patch } };
    case "SET_CIRCULATION_RESULT":
      return { ...state, circulationResult: action.result, activeCageSeed: null };
    case "SELECT_CAGE_ITERATION": {
      if (!state.circulationResult?.cage_iterations) return state;
      const meta = state.circulationResult.cage_iterations.find((m) => m.seed === action.seed);
      if (!meta) return state;
      return {
        ...state,
        activeCageSeed: action.seed,
        circulationResult: {
          ...state.circulationResult,
          cage_geometries: meta.cage_geometries ?? state.circulationResult.cage_geometries,
          circulation_geometry: meta.circulation_geometry ?? state.circulationResult.circulation_geometry,
          centerline: meta.centerline ?? state.circulationResult.centerline,
          evacuation_dots: meta.evacuation_dots ?? state.circulationResult.evacuation_dots,
          remainder: meta.remainder ?? state.circulationResult.remainder,
        },
        // wybór innej iteracji unieważnia ewentualny wcześniejszy podział na
        // mieszkania (ten sam wzorzec co ADD_MANUAL_CAGE/REMOVE_MANUAL_ELEMENT)
        layoutResult: null,
        validation: null,
      };
    }
    case "SELECT_UNIT_ITERATION": {
      // state.lastIterations (nie state.layoutResult.iterations) -- to jest
      // dokładnie ta tablica którą renderuje ProgramSection.tsx, więc klik w
      // wiersz zawsze trafia w meta z tej samej listy co user widzi.
      if (!state.layoutResult) return state;
      const meta = state.lastIterations.find((m) => m.seed === action.seed);
      if (!meta || !meta.apartments) return state;
      return {
        ...state,
        activeUnitSeed: action.seed,
        layoutResult: {
          ...state.layoutResult,
          apartments: meta.apartments,
          wall_bands: meta.wall_bands ?? state.layoutResult.wall_bands,
          leftover: null,
        },
      };
    }
    case "ADD_MANUAL_CAGE":
      return {
        ...state,
        manualCages: [...state.manualCages, { id: crypto.randomUUID(), ring: action.ring }],
        drawingPoints: [],
        mode: "idle",
        // jak UPDATE_VERTEX: wyniki pochodne są nieaktualne do czasu przeliczenia
        layoutResult: null, validation: null,
      };
    case "ADD_MANUAL_CORRIDOR":
      return {
        ...state,
        manualCorridors: [...state.manualCorridors, { id: crypto.randomUUID(), path: action.path }],
        drawingPoints: [],
        mode: "idle",
        layoutResult: null, validation: null,
      };
    case "REMOVE_MANUAL_ELEMENT":
      return {
        ...state,
        manualCages: state.manualCages.filter((c) => c.id !== action.id),
        manualCorridors: state.manualCorridors.filter((c) => c.id !== action.id),
        layoutResult: null, validation: null,
      };
    case "SET_HOVERED_MANUAL":
      return { ...state, hoveredManualId: action.id };
    case "SET_LAYOUT_RESULT":
      // Every dispatch site (regenerate, runPlaceCirculation, runSubdivideUnits,
      // apply-optimizer-variant) means the apartment geometry/IDs just changed --
      // any solarResult computed against the previous apartments is now stale
      // and must not linger on the canvas looking current.
      return { ...state, layoutResult: action.result, solarResult: null, activeUnitSeed: null };
    case "SET_VALIDATION":
      return { ...state, validation: action.validation };
    case "SET_TYPOLOGY_SUGGESTION":
      return { ...state, typologySuggestion: action.suggestion };
    case "SET_SELECTED_TYPOLOGY":
      return { ...state, selectedTypology: action.typology };
    case "SELECT_APARTMENT":
      return { ...state, selectedApartmentId: action.id };
    case "SET_LOADING":
      return { ...state, isLoading: action.loading };
    case "SET_ERROR":
      return { ...state, error: action.error };
    case "UPDATE_APARTMENTS":
      if (!state.layoutResult) return state;
      return {
        ...state,
        layoutResult: {
          ...state.layoutResult,
          apartments: action.apartments,
        },
      };
    case "SET_SOLAR_RESULT": return { ...state, solarResult: action.result };
    case "SET_GPS": return { ...state, gps: action.gps };
    case "SET_ANALYSIS_DATE": return { ...state, analysisDate: action.date };
    case "SET_IS_DOWNTOWN": return { ...state, isDowntown: action.isDowntown };
    case "SET_OPTIMIZER_VARIANTS": return { ...state, optimizerVariants: action.variants };
    case "SET_ACTIVE_VARIANT": return { ...state, activeVariantId: action.id };
    case "SET_IS_OPTIMIZING": return { ...state, isOptimizing: action.isOptimizing };
    case "SET_THEME": return { ...state, theme: action.theme };
    case "TRANSLATE_CIRCULATION": {
      if (!state.circulationResult) return state;
      const { dx, dy } = action;
      return {
        ...state,
        circulationResult: {
          ...state.circulationResult,
          circulation_geometry: state.circulationResult.circulation_geometry
            ? translateGeoJson(state.circulationResult.circulation_geometry, dx, dy)
            : null,
          cage_geometries: state.circulationResult.cage_geometries.map((g) => translateGeoJson(g, dx, dy)),
          // remainder is NOT recomputed client-side here (real polygon.difference
          // needs a real geometry library) — runSubdivideUnits always uses the
          // last server-computed remainder from the most recent
          // runPlaceCirculation call, not a client-recomputed one. Documented
          // limitation, see runSubdivideUnits below and Task 16 commit message.
        },
      };
    }
    case "RESHAPE_CIRCULATION": {
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: {
          ...state.circulationResult,
          circulation_geometry: action.result.circulation_geometry,
          remainder: action.result.remainder,
          centerline: action.result.centerline,
          evacuation_dots: action.result.evacuation_dots,
        },
      };
    }
    case "SET_EVACUATION_DOTS":
      if (!state.circulationResult) return state;
      return {
        ...state,
        circulationResult: { ...state.circulationResult, evacuation_dots: action.dots },
      };
    case "RESTORE_STATE": return { ...action.state, isLoading: false, error: null };
    default:
      return state;
  }
}

function footprintToPoints(footprint: Point2D[]): api.Point[] {
  return footprint.map((p) => [p.x, p.y] as api.Point);
}

function polygonAreaFromPoints(points: Point2D[]): number {
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    sum += a.x * b.y - b.x * a.y;
  }
  return Math.abs(sum) / 2;
}

function polygonFromGeoJson(geom: api.GeoJsonPolygon): Point2D[] {
  const ring = geom.coordinates[0] ?? [];
  return ring.slice(0, -1).map(([x, y]) => ({ x, y }));
}

function snapToGrid(v: number): number {
  return Math.round(v / 0.5) * 0.5;
}

function translateGeoJson(geom: api.GeoJsonPolygon, dx: number, dy: number): api.GeoJsonPolygon {
  return {
    type: geom.type,
    coordinates: geom.coordinates.map((ring) =>
      ring.map(([x, y]) => [snapToGrid(x + dx), snapToGrid(y + dy)])
    ),
  } as api.GeoJsonPolygon;
}

interface SessionContextValue {
  state: SessionState;
  dispatch: React.Dispatch<Action>;
  setMode: (mode: EditorMode) => void;
  addDrawPoint: (point: Point2D) => void;
  removeLastDrawPoint: () => void;
  finishDrawing: () => Promise<void>;
  setFootprintFromDxf: (file: File) => Promise<void>;
  updateVertex: (index: number, point: Point2D) => void;
  setFootprintPoints: (points: Point2D[]) => void;
  updateProgramRow: (id: string, patch: Partial<ProgramRow>) => void;
  addProgramRow: () => void;
  removeProgramRow: (id: string) => void;
  setTotalUnits: (totalUnits: number) => void;
  setUnitWeight: (key: keyof api.UnitWeightsInput, value: number) => void;
  setCirculation: (patch: Partial<api.CirculationSpecInput>) => void;
  selectApartment: (id: string | null) => void;
  addManualCage: (ring: Point2D[]) => void;
  addManualCorridor: (path: Point2D[]) => void;
  removeManualElement: (id: string) => void;
  setHoveredManualId: (id: string | null) => void;
  selectCageIteration: (seed: number) => void;
  selectUnitIteration: (seed: number) => void;
  activeCageSeed: number | null;
  activeUnitSeed: number | null;
  regenerate: () => Promise<void>;
  runPlaceCirculation: (overrides?: {
    manualCages?: ManualCage[];
    manualCorridors?: ManualCorridor[];
    circulationOverride?: Partial<api.CirculationSpecInput>;
  }) => Promise<boolean>;
  runSubdivideUnits: () => Promise<void>;
  runReshapeCirculation: (segments: [Point2D, Point2D][]) => Promise<void>;
  runRecomputeEvacuation: () => Promise<void>;
  refreshTypologySuggestion: () => Promise<void>;
  applyTypologyPreset: (key: string) => Promise<void>;
  updateApartmentsAndValidate: (apartments: api.ApartmentResult[]) => Promise<void>;
  runSolarAnalysis: () => Promise<void>;
  setGps: (gps: { lat: number; lng: number }) => void;
  setAnalysisDate: (date: string) => void;
  setIsDowntown: (isDowntown: boolean) => void;
  runOptimizer: () => Promise<void>;
  setActiveVariant: (id: string | null) => void;
  applyVariant: (id: string) => void;
  toggleTheme: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    const saved = localStorage.getItem("domko_session");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Backfill: sesje zapisane w localStorage przed dodaniem
        // cage_iterations/cage_weights (Etap 2b) nie mają tych pól w
        // parsed.circulation. Bez tego merge'a suwaki wag odczytujące
        // state.circulation.cage_weights[key].toFixed(2) rzucają
        // TypeError na undefined przy pierwszym renderze po wgraniu tej
        // zmiany -- w przeciwieństwie do starszych pól (liczby proste),
        // które w gorszym razie dają tylko "uncontrolled input".
        if (parsed) {
          dispatch({
            type: "RESTORE_STATE",
            state: { ...parsed, circulation: { ...initialCirculation, ...parsed.circulation } },
          });
        }
      } catch (err) {
        console.error("Nie udało się odtworzyć sesji z localStorage", err);
      }
    }
  }, []);

  useEffect(() => {
    const toSave = { ...state, isLoading: false, error: null };
    localStorage.setItem("domko_session", JSON.stringify(toSave));
  }, [state]);

  // Drives the `light:` Tailwind variant (see tailwind.config.ts) via a
  // `.light` class on <html> — layout.tsx is a server component so it
  // can't read the persisted theme itself, hence the client-side sync here.
  useEffect(() => {
    document.documentElement.classList.toggle("light", state.theme === "light");
  }, [state.theme]);

  const setMode = useCallback((mode: EditorMode) => dispatch({ type: "SET_MODE", mode }), []);
  const addDrawPoint = useCallback((point: Point2D) => dispatch({ type: "ADD_DRAW_POINT", point }), []);
  const removeLastDrawPoint = useCallback(() => dispatch({ type: "REMOVE_LAST_DRAW_POINT" }), []);

  const finishDrawing = useCallback(async () => {
    if (state.drawingPoints.length < 3) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const res = await api.footprintFromPoints(state.drawingPoints, true);
      if (!res.valid || !res.boundary) {
        dispatch({
          type: "SET_ERROR",
          error: res.errors.map((e) => e.message).join("; ") || "Obrys nieprawidłowy.",
        });
        return;
      }
      const pts = res.boundary.slice(0, -1).map(([x, y]) => ({ x, y }));
      dispatch({ type: "SET_FOOTPRINT", footprint: pts });
      dispatch({ type: "SET_MODE", mode: "idle" });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.drawingPoints]);

  const setFootprintFromDxf = useCallback(async (file: File) => {
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const res = await api.footprintImportDxf(file);
      if (!res.valid || !res.polygon) {
        dispatch({
          type: "SET_ERROR",
          error: res.errors.map((e) => e.message).join("; ") || "Nie udało się zaimportować pliku DXF.",
        });
        return;
      }
      dispatch({ type: "SET_FOOTPRINT", footprint: polygonFromGeoJson(res.polygon) });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, []);

  const updateVertex = useCallback(
    (index: number, point: Point2D) => dispatch({ type: "UPDATE_VERTEX", index, point }),
    []
  );
  const setFootprintPoints = useCallback(
    (points: Point2D[]) => dispatch({ type: "SET_FOOTPRINT_POINTS", points }),
    []
  );
  const updateProgramRow = useCallback(
    (id: string, patch: Partial<ProgramRow>) => dispatch({ type: "UPDATE_PROGRAM_ROW", id, patch }),
    []
  );
  const addProgramRow = useCallback(() => dispatch({ type: "ADD_PROGRAM_ROW" }), []);
  const removeProgramRow = useCallback((id: string) => dispatch({ type: "REMOVE_PROGRAM_ROW", id }), []);
  const setTotalUnits = useCallback((totalUnits: number) => dispatch({ type: "SET_TOTAL_UNITS", totalUnits }), []);
  const setUnitWeight = useCallback(
    (key: keyof api.UnitWeightsInput, value: number) => dispatch({ type: "SET_UNIT_WEIGHT", key, value }),
    []
  );
  const setCirculation = useCallback(
    (patch: Partial<api.CirculationSpecInput>) => dispatch({ type: "SET_CIRCULATION", patch }),
    []
  );
  const selectApartment = useCallback((id: string | null) => dispatch({ type: "SELECT_APARTMENT", id }), []);
  const addManualCage = useCallback((ring: Point2D[]) => dispatch({ type: "ADD_MANUAL_CAGE", ring }), []);
  const addManualCorridor = useCallback((path: Point2D[]) => dispatch({ type: "ADD_MANUAL_CORRIDOR", path }), []);
  const removeManualElement = useCallback((id: string) => dispatch({ type: "REMOVE_MANUAL_ELEMENT", id }), []);
  const setHoveredManualId = useCallback((id: string | null) => dispatch({ type: "SET_HOVERED_MANUAL", id }), []);
  const selectCageIteration = useCallback((seed: number) => {
    dispatch({ type: "SELECT_CAGE_ITERATION", seed });
  }, []);
  const selectUnitIteration = useCallback((seed: number) => {
    dispatch({ type: "SELECT_UNIT_ITERATION", seed });
  }, []);

  const setGps = useCallback((gps: { lat: number; lng: number }) => dispatch({ type: "SET_GPS", gps }), []);
  const setAnalysisDate = useCallback((date: string) => dispatch({ type: "SET_ANALYSIS_DATE", date }), []);
  const setIsDowntown = useCallback((isDowntown: boolean) => dispatch({ type: "SET_IS_DOWNTOWN", isDowntown }), []);
  const setActiveVariant = useCallback((id: string | null) => dispatch({ type: "SET_ACTIVE_VARIANT", id }), []);
  const toggleTheme = useCallback(() => {
    dispatch({ type: "SET_THEME", theme: state.theme === "dark" ? "light" : "dark" });
  }, [state.theme]);

  const buildRequest = useCallback(
    (footprint: Point2D[]): api.LayoutGenerateRequest => ({
      footprint: footprintToPoints(footprint),
      circulation: state.circulation,
      apartments: state.program.map((row) => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
        percentage: row.percentage,
        area_min_m2: row.area_min_m2,
        area_max_m2: row.area_max_m2,
        min_facade_m: row.min_facade_m,
      })),
    }),
    [state.circulation, state.program]
  );

  const regenerate = useCallback(async () => {
    if (!state.footprint || state.footprint.length < 3) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const req: api.LayoutGenerateRequest = {
        ...buildRequest(state.footprint),
        // Same dual-surface fix as runPlaceCirculation: the one-shot
        // /layout/generate path must also carry the current manual
        // cages/corridors, otherwise they silently vanish on "Generuj układ"
        // (see gotcha_dual_layout_api_surface.md).
        circulation: {
          ...state.circulation,
          manual_cages: state.manualCages.map((c) => c.ring.map((p) => [p.x, p.y] as api.Point)),
          manual_corridors: state.manualCorridors.map((c) => c.path.map((p) => [p.x, p.y] as api.Point)),
        },
        iterations: 10,
        weights: state.unitWeights,
      };
      const [layout, validation] = await Promise.all([
        api.generateLayout(req),
        api.validateFullLayout(req),
      ]);
      dispatch({ type: "SET_LAYOUT_RESULT", result: layout });
      dispatch({ type: "SET_VALIDATION", validation });
      dispatch({
        type: "SET_ITERATION_RESULTS",
        iterations: layout.iterations ?? [],
        derivedTotalUnits: layout.derived_total_units ?? 0,
        netRemainderM2: layout.net_remainder_m2 ?? 0,
      });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.footprint, buildRequest, state.circulation, state.manualCages, state.manualCorridors, state.unitWeights]);

  const runPlaceCirculation = useCallback(
    async (overrides?: {
      manualCages?: ManualCage[];
      manualCorridors?: ManualCorridor[];
      circulationOverride?: Partial<api.CirculationSpecInput>;
    }): Promise<boolean> => {
      if (!state.footprint || state.footprint.length < 3) return false;
      // overrides: handler po dispatch(ADD_/REMOVE_) ma świeżą listę wcześniej
      // niż state z closure — bez tego pierwszy przelicz po dodaniu elementu
      // wysyłałby listę sprzed dodania.
      const cages = overrides?.manualCages ?? state.manualCages;
      const corridors = overrides?.manualCorridors ?? state.manualCorridors;
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const result = await api.placeCirculation(footprintToPoints(state.footprint), {
          ...state.circulation,
          ...(overrides?.circulationOverride ?? {}),
          // manual_cages/manual_corridors zawsze na końcu — circulationOverride
          // (np. { cage_iterations: 10 } z przycisku "Rozmieść iteracyjnie")
          // nigdy nie może po cichu nadpisać świeżej listy elementów ręcznych.
          manual_cages: cages.map((c) => c.ring.map((p) => [p.x, p.y] as api.Point)),
          manual_corridors: corridors.map((c) => c.path.map((p) => [p.x, p.y] as api.Point)),
        });
        dispatch({ type: "SET_CIRCULATION_RESULT", result });
        dispatch({ type: "SET_LAYOUT_RESULT", result: null });
        dispatch({ type: "SET_VALIDATION", validation: null });
        dispatch({ type: "SET_ERROR", error: null });
        return true;
      } catch (err) {
        dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
        return false;
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [state.footprint, state.circulation, state.manualCages, state.manualCorridors]
  );

  const runReshapeCirculation = useCallback(
    async (segments: [Point2D, Point2D][]) => {
      if (!state.footprint || !state.circulationResult) return;
      dispatch({ type: "SET_LOADING", loading: true });
      try {
        const result = await api.reshapeCirculation({
          footprint: footprintToPoints(state.footprint),
          centerline: segments.map(([p1, p2]) => ({
            points: [
              [p1.x, p1.y],
              [p2.x, p2.y],
            ] as [api.Point, api.Point],
          })),
          corridor_width_m: state.circulation.corridor_width_m,
          cage_geometries: state.circulationResult.cage_geometries,
          max_dist_single_m: state.circulation.max_dist_single_m,
          max_dist_multi_m: state.circulation.max_dist_multi_m,
        });
        dispatch({ type: "RESHAPE_CIRCULATION", result });
        dispatch({ type: "SET_ERROR", error: null });
      } catch (err) {
        dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
      } finally {
        dispatch({ type: "SET_LOADING", loading: false });
      }
    },
    [
      state.footprint,
      state.circulationResult,
      state.circulation.corridor_width_m,
      state.circulation.max_dist_single_m,
      state.circulation.max_dist_multi_m,
    ]
  );

  const runRecomputeEvacuation = useCallback(async () => {
    if (!state.circulationResult?.centerline?.length) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const res = await api.recomputeEvacuation({
        centerline: state.circulationResult.centerline.map((seg) => ({ points: seg.points })),
        cage_geometries: state.circulationResult.cage_geometries,
        max_dist_single_m: state.circulation.max_dist_single_m,
        max_dist_multi_m: state.circulation.max_dist_multi_m,
      });
      dispatch({ type: "SET_EVACUATION_DOTS", dots: res.evacuation_dots });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.circulationResult, state.circulation.max_dist_single_m, state.circulation.max_dist_multi_m]);

  const runSubdivideUnits = useCallback(async () => {
    if (!state.circulationResult) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const unitsReq = state.program.map((row) => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
        percentage: row.percentage,
        area_min_m2: row.area_min_m2,
        area_max_m2: row.area_max_m2,
        min_facade_m: row.min_facade_m,
      }));
      const unitsRes = await api.subdivideUnits(
        state.circulationResult.remainder,
        unitsReq,
        state.footprint ? footprintToPoints(state.footprint) : undefined,
        state.circulationResult.circulation_geometry,
        10,
        state.unitWeights
      );
      const layoutResult: api.LayoutGenerateResponse = {
        footprint_area_m2: state.footprint ? polygonAreaFromPoints(state.footprint) : 0,
        circulation_area_m2: 0,
        usable_area_m2: unitsRes.apartments.reduce((sum, a) => sum + a.area_m2, 0),
        apartments: unitsRes.apartments,
        leftover: unitsRes.leftover,
        wt_validation: { passed: true, score: 0, rules: [], issues: [] },
        zones: [],
        circulation_parts: state.circulationResult.circulation_geometry
          ? [state.circulationResult.circulation_geometry]
          : [],
        cage_geometries: state.circulationResult.cage_geometries,
        wall_bands: unitsRes.wall_bands,
        derived_total_units: unitsRes.derived_total_units,
        net_remainder_m2: unitsRes.net_remainder_m2,
        iterations: unitsRes.iterations,
        best_seed: unitsRes.best_seed,
      };
      dispatch({ type: "SET_LAYOUT_RESULT", result: layoutResult });
      dispatch({
        type: "SET_ITERATION_RESULTS",
        iterations: unitsRes.iterations ?? [],
        derivedTotalUnits: unitsRes.derived_total_units ?? 0,
        netRemainderM2: unitsRes.net_remainder_m2 ?? 0,
      });
      dispatch({ type: "SET_ERROR", error: null });
      // Fetch real WT validation for the combined result (score/rules were
      // left as placeholders above since /layout/units doesn't compute WT).
      if (state.footprint) {
        const req = {
          footprint: footprintToPoints(state.footprint),
          circulation: state.circulation,
          apartments: unitsReq,
        };
        const validation = await api.validateFullLayout(req);
        dispatch({ type: "SET_VALIDATION", validation });
      }
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.circulationResult, state.program, state.footprint, state.circulation, state.unitWeights]);

  const refreshTypologySuggestion = useCallback(async () => {
    if (!state.footprint || state.footprint.length < 3) return;
    try {
      const suggestion = await api.suggestTypology(footprintToPoints(state.footprint));
      dispatch({ type: "SET_TYPOLOGY_SUGGESTION", suggestion });
    } catch {
      // Non-critical — suggestion is a nice-to-have, don't surface as a blocking error.
    }
  }, [state.footprint]);

  const applyTypologyPreset = useCallback(async (key: string) => {
    dispatch({ type: "SET_SELECTED_TYPOLOGY", typology: key });
    try {
      const { presets } = await api.listTypologyPresets();
      const preset = presets.find((p) => p.key === key);
      if (!preset) return;
      const cageSize = (preset.staircase_dims_m[0] + preset.staircase_dims_m[1]) / 2;
      dispatch({
        type: "SET_CIRCULATION",
        patch: {
          corridor_width_m: preset.corridor_width_m > 0 ? preset.corridor_width_m : 1.2,
          cage_size_m: cageSize,
          place_cage: preset.corridor_width_m > 0,
        },
      });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof Error ? err.message : String(err) });
    }
  }, []);

  const updateApartmentsAndValidate = useCallback(async (apartments: api.ApartmentResult[]) => {
    dispatch({ type: "UPDATE_APARTMENTS", apartments });
    if (!state.footprint || !state.layoutResult) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const req = buildRequest(state.footprint);
      const footprintPts = footprintToPoints(state.footprint);
      const layoutInput: api.LayoutDataInput = {
        footprint: footprintPts,
        circulation_geometry: state.layoutResult.circulation_parts.length > 0 ? state.layoutResult.circulation_parts[0] : null,
        cage_geometries: state.layoutResult.cage_geometries,
        corridor_width_m: state.circulation.corridor_width_m,
        stair_width_m: state.circulation.stair_width_m,
        apartments: apartments.map((a) => ({
          id: a.id,
          type: a.type,
          geometry: a.geometry,
        })),
      };
      const validation = await api.validateFullLayout({
        ...req,
        layout: layoutInput,
      });
      dispatch({ type: "SET_VALIDATION", validation });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.footprint, state.layoutResult, state.circulation, buildRequest]);

  const runSolarAnalysis = useCallback(async () => {
    if (!state.footprint || !state.layoutResult) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const footprintPts = footprintToPoints(state.footprint);
      const layoutInput: api.LayoutDataInput = {
        footprint: footprintPts,
        circulation_geometry: state.layoutResult.circulation_parts.length > 0 ? state.layoutResult.circulation_parts[0] : null,
        cage_geometries: state.layoutResult.cage_geometries,
        corridor_width_m: state.circulation.corridor_width_m,
        stair_width_m: state.circulation.stair_width_m,
        apartments: state.layoutResult.apartments.map((a) => ({
          id: a.id,
          type: a.type,
          geometry: a.geometry,
        })),
      };
      
      const req: api.SolarAnalyzeRequest = {
        footprint: footprintPts,
        circulation: state.circulation,
        apartments: state.program.map(row => ({
          type: row.type,
          min_area_m2: row.min_area_m2,
          target_count: row.target_count,
          percentage: row.percentage,
          area_min_m2: row.area_min_m2,
          area_max_m2: row.area_max_m2,
          min_facade_m: row.min_facade_m,
        })),
        latitude: state.gps.lat,
        longitude: state.gps.lng,
        analysis_date: state.analysisDate,
        required_hours: state.isDowntown ? 1.5 : 3.0,
        layout: layoutInput,
      };
      
      const result = await api.analyzeSolar(req);
      dispatch({ type: "SET_SOLAR_RESULT", result });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.footprint, state.layoutResult, state.circulation, state.program, state.gps, state.analysisDate, state.isDowntown]);

  const runOptimizer = useCallback(async () => {
    if (!state.footprint) return;
    dispatch({ type: "SET_IS_OPTIMIZING", isOptimizing: true });
    try {
      const req: api.OptimizerRunRequest = {
        footprint: footprintToPoints(state.footprint),
        apartments: state.program.map(row => ({
          type: row.type,
          min_area_m2: row.min_area_m2,
          target_count: row.target_count,
          percentage: row.percentage,
          area_min_m2: row.area_min_m2,
          area_max_m2: row.area_max_m2,
          min_facade_m: row.min_facade_m,
        })),
        latitude: state.gps.lat,
        longitude: state.gps.lng,
        analysis_date: state.analysisDate,
        required_hours: state.isDowntown ? 1.5 : 3.0,
        corridor_width_m: state.circulation.corridor_width_m,
        stair_width_m: state.circulation.stair_width_m,
        cage_size_m: state.circulation.cage_size_m,
      };
      const res = await api.runOptimizer(req);
      dispatch({ type: "SET_OPTIMIZER_VARIANTS", variants: res.variants });
      if (res.variants.length > 0) {
        dispatch({ type: "SET_ACTIVE_VARIANT", id: res.variants[0].id });
      }
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_IS_OPTIMIZING", isOptimizing: false });
    }
  }, [state.footprint, state.circulation, state.program, state.gps, state.analysisDate, state.isDowntown]);

  const applyVariant = useCallback((id: string) => {
    const variant = state.optimizerVariants.find((v) => v.id === id);
    if (!variant) return;
    dispatch({ type: "SET_ACTIVE_VARIANT", id });
    dispatch({ type: "SET_LAYOUT_RESULT", result: variant.layout });
    // A staged circulationResult (from an earlier runPlaceCirculation call)
    // no longer corresponds to this freshly-applied variant's layout —
    // stale state, same class of bug as the UPDATE_VERTEX/SET_FOOTPRINT fix.
    dispatch({ type: "SET_CIRCULATION_RESULT", result: null });
  }, [state.optimizerVariants]);

  const value = useMemo<SessionContextValue>(
    () => ({
      state,
      dispatch,
      setMode,
      addDrawPoint,
      removeLastDrawPoint,
      finishDrawing,
      setFootprintFromDxf,
      updateVertex,
      setFootprintPoints,
      updateProgramRow,
      addProgramRow,
      removeProgramRow,
      setTotalUnits,
      setUnitWeight,
      setCirculation,
      selectApartment,
      addManualCage,
      addManualCorridor,
      removeManualElement,
      setHoveredManualId,
      selectCageIteration,
      selectUnitIteration,
      activeCageSeed: state.activeCageSeed,
      activeUnitSeed: state.activeUnitSeed,
      regenerate,
      runPlaceCirculation,
      runSubdivideUnits,
      runReshapeCirculation,
      runRecomputeEvacuation,
      refreshTypologySuggestion,
      applyTypologyPreset,
      updateApartmentsAndValidate,
      runSolarAnalysis,
      setGps,
      setAnalysisDate,
      setIsDowntown,
      runOptimizer,
      setActiveVariant,
      applyVariant,
      toggleTheme,
    }),
    [
      state,
      setMode,
      addDrawPoint,
      removeLastDrawPoint,
      finishDrawing,
      setFootprintFromDxf,
      updateVertex,
      setFootprintPoints,
      updateProgramRow,
      addProgramRow,
      removeProgramRow,
      setTotalUnits,
      setUnitWeight,
      setCirculation,
      selectApartment,
      addManualCage,
      addManualCorridor,
      removeManualElement,
      setHoveredManualId,
      selectCageIteration,
      selectUnitIteration,
      regenerate,
      runPlaceCirculation,
      runSubdivideUnits,
      runReshapeCirculation,
      runRecomputeEvacuation,
      refreshTypologySuggestion,
      applyTypologyPreset,
      updateApartmentsAndValidate,
      runSolarAnalysis,
      setGps,
      setAnalysisDate,
      setIsDowntown,
      runOptimizer,
      setActiveVariant,
      applyVariant,
      toggleTheme,
    ]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
