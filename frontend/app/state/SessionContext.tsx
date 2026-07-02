"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useReducer } from "react";
import * as api from "../lib/api";

export type Point2D = { x: number; y: number };

export type EditorMode = "idle" | "draw" | "edit-vertices" | "edit-lines";

export interface ProgramRow {
  id: string;
  type: string;
  min_area_m2: number;
  target_count: number;
}

interface SessionState {
  footprint: Point2D[] | null;
  drawingPoints: Point2D[];
  mode: EditorMode;
  program: ProgramRow[];
  circulation: api.CirculationSpecInput;
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
}

const initialCirculation: api.CirculationSpecInput = {
  corridor_width_m: 1.5,
  stair_width_m: 1.2,
  place_cage: true,
  cage_size_m: 2.5,
  cage_position: "auto",
};

const initialState: SessionState = {
  footprint: null,
  drawingPoints: [],
  mode: "idle",
  program: [{ id: crypto.randomUUID(), type: "M2", min_area_m2: 45, target_count: 2 }],
  circulation: initialCirculation,
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
};

type Action =
  | { type: "SET_MODE"; mode: EditorMode }
  | { type: "ADD_DRAW_POINT"; point: Point2D }
  | { type: "REMOVE_LAST_DRAW_POINT" }
  | { type: "CLEAR_DRAWING" }
  | { type: "SET_FOOTPRINT"; footprint: Point2D[] }
  | { type: "UPDATE_VERTEX"; index: number; point: Point2D }
  | { type: "SET_PROGRAM"; program: ProgramRow[] }
  | { type: "ADD_PROGRAM_ROW" }
  | { type: "UPDATE_PROGRAM_ROW"; id: string; patch: Partial<ProgramRow> }
  | { type: "REMOVE_PROGRAM_ROW"; id: string }
  | { type: "SET_CIRCULATION"; patch: Partial<api.CirculationSpecInput> }
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
        drawingPoints: action.mode === "draw" || state.mode === "draw" ? [] : state.drawingPoints,
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
      };
    case "UPDATE_VERTEX": {
      if (!state.footprint) return state;
      const next = [...state.footprint];
      next[action.index] = action.point;
      return { ...state, footprint: next };
    }
    case "SET_PROGRAM":
      return { ...state, program: action.program };
    case "ADD_PROGRAM_ROW":
      return {
        ...state,
        program: [
          ...state.program,
          { id: crypto.randomUUID(), type: "M2", min_area_m2: 45, target_count: 1 },
        ],
      };
    case "UPDATE_PROGRAM_ROW":
      return {
        ...state,
        program: state.program.map((row) => (row.id === action.id ? { ...row, ...action.patch } : row)),
      };
    case "REMOVE_PROGRAM_ROW":
      return { ...state, program: state.program.filter((row) => row.id !== action.id) };
    case "SET_CIRCULATION":
      return { ...state, circulation: { ...state.circulation, ...action.patch } };
    case "SET_LAYOUT_RESULT":
      return { ...state, layoutResult: action.result };
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
    case "RESTORE_STATE": return { ...action.state, isLoading: false, error: null };
    default:
      return state;
  }
}

function footprintToPoints(footprint: Point2D[]): api.Point[] {
  return footprint.map((p) => [p.x, p.y] as api.Point);
}

function polygonFromGeoJson(geom: api.GeoJsonPolygon): Point2D[] {
  const ring = geom.coordinates[0] ?? [];
  return ring.slice(0, -1).map(([x, y]) => ({ x, y }));
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
  updateProgramRow: (id: string, patch: Partial<ProgramRow>) => void;
  addProgramRow: () => void;
  removeProgramRow: (id: string) => void;
  setCirculation: (patch: Partial<api.CirculationSpecInput>) => void;
  selectApartment: (id: string | null) => void;
  regenerate: () => Promise<void>;
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
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    const saved = localStorage.getItem("domko_session");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed) dispatch({ type: "RESTORE_STATE", state: parsed });
      } catch (err) {
        console.error("Nie udało się odtworzyć sesji z localStorage", err);
      }
    }
  }, []);

  useEffect(() => {
    const toSave = { ...state, isLoading: false, error: null };
    localStorage.setItem("domko_session", JSON.stringify(toSave));
  }, [state]);

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
  const updateProgramRow = useCallback(
    (id: string, patch: Partial<ProgramRow>) => dispatch({ type: "UPDATE_PROGRAM_ROW", id, patch }),
    []
  );
  const addProgramRow = useCallback(() => dispatch({ type: "ADD_PROGRAM_ROW" }), []);
  const removeProgramRow = useCallback((id: string) => dispatch({ type: "REMOVE_PROGRAM_ROW", id }), []);
  const setCirculation = useCallback(
    (patch: Partial<api.CirculationSpecInput>) => dispatch({ type: "SET_CIRCULATION", patch }),
    []
  );
  const selectApartment = useCallback((id: string | null) => dispatch({ type: "SELECT_APARTMENT", id }), []);

  const setGps = useCallback((gps: { lat: number; lng: number }) => dispatch({ type: "SET_GPS", gps }), []);
  const setAnalysisDate = useCallback((date: string) => dispatch({ type: "SET_ANALYSIS_DATE", date }), []);
  const setIsDowntown = useCallback((isDowntown: boolean) => dispatch({ type: "SET_IS_DOWNTOWN", isDowntown }), []);
  const setActiveVariant = useCallback((id: string | null) => dispatch({ type: "SET_ACTIVE_VARIANT", id }), []);

  const buildRequest = useCallback(
    (footprint: Point2D[]): api.LayoutGenerateRequest => ({
      footprint: footprintToPoints(footprint),
      circulation: state.circulation,
      apartments: state.program.map((row) => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
      })),
    }),
    [state.circulation, state.program]
  );

  const regenerate = useCallback(async () => {
    if (!state.footprint || state.footprint.length < 3) return;
    dispatch({ type: "SET_LOADING", loading: true });
    try {
      const req = buildRequest(state.footprint);
      const [layout, validation] = await Promise.all([
        api.generateLayout(req),
        api.validateFullLayout(req),
      ]);
      dispatch({ type: "SET_LAYOUT_RESULT", result: layout });
      dispatch({ type: "SET_VALIDATION", validation });
      dispatch({ type: "SET_ERROR", error: null });
    } catch (err) {
      dispatch({ type: "SET_ERROR", error: err instanceof api.ApiError ? err.message : String(err) });
    } finally {
      dispatch({ type: "SET_LOADING", loading: false });
    }
  }, [state.footprint, buildRequest]);

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
      updateProgramRow,
      addProgramRow,
      removeProgramRow,
      setCirculation,
      selectApartment,
      regenerate,
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
    }),
    [
      state,
      setMode,
      addDrawPoint,
      removeLastDrawPoint,
      finishDrawing,
      setFootprintFromDxf,
      updateVertex,
      updateProgramRow,
      addProgramRow,
      removeProgramRow,
      setCirculation,
      selectApartment,
      regenerate,
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
    ]
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
