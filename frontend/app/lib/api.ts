/**
 * Cienki klient HTTP nad backendem FastAPI (F2-15).
 *
 * Zastępuje sampleBspResult prawdziwymi wywołaniami API — to jest warstwa,
 * której brak blokował całą resztę frontendu (patrz zadania-kanban.md F2-15).
 *
 * Base URL: NEXT_PUBLIC_API_URL, domyślnie http://localhost:8000/api/v1
 * (backend uruchamiany lokalnie przez `uvicorn main:app` — bez Docker Compose,
 * które jeszcze nie istnieje, patrz F0-04).
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers:
        init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json", ...init.headers }
          : init?.headers,
    });
  } catch {
    throw new ApiError(
      `Nie udało się połączyć z backendem pod ${API_BASE}. Czy uvicorn działa?`,
      0
    );
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = await response.json();
    } catch {
      detail = await response.text();
    }
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `Żądanie nie powiodło się (${response.status})`;
    throw new ApiError(message, response.status, detail);
  }

  return response.json() as Promise<T>;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

// ── Typy współdzielone ──────────────────────────────────────────────

export type Point = [number, number];

export interface GeoJsonPolygon {
  type: "Polygon";
  coordinates: number[][][];
}

// ── Footprint (F1-01, F1-02) ────────────────────────────────────────

export interface FootprintValidationError {
  field: string;
  message: string;
}

export interface FootprintFromPointsResponse {
  valid: boolean;
  closed: boolean;
  self_intersecting: boolean;
  errors: FootprintValidationError[];
  area_m2?: number;
  boundary?: Point[];
}

export function footprintFromPoints(
  points: { x: number; y: number }[],
  close = true
): Promise<FootprintFromPointsResponse> {
  return postJson("/footprint/from-points", { points, close });
}

export interface FootprintImportDxfResponse {
  valid: boolean;
  errors: FootprintValidationError[];
  polygon?: GeoJsonPolygon;
  area_m2?: number;
  dimensions?: { width_m: number; height_m: number };
  source_entity_type?: string;
  source_layer?: string;
  candidate_count: number;
}

export async function footprintImportDxf(file: File): Promise<FootprintImportDxfResponse> {
  const form = new FormData();
  form.append("file", file);
  return request("/footprint/import-dxf", { method: "POST", body: form });
}

// ── Layout generation (F2-04) ────────────────────────────────────────

export type CagePosition = "1a" | "1b" | "2" | "3" | "auto";

export interface ApartmentProgramInput {
  type: string;
  min_area_m2: number;
  target_count: number;
  width_m?: number | null;
  depth_m?: number | null;
}

export interface CirculationSpecInput {
  corridor_width_m: number;
  stair_width_m: number;
  place_cage: boolean;
  cage_size_m: number;
  cage_position: CagePosition;
}

export interface LayoutGenerateRequest {
  footprint: Point[];
  circulation: CirculationSpecInput;
  apartments: ApartmentProgramInput[];
  local_law?: string | null;
}

export interface ApartmentResult {
  id: string;
  type: string;
  area_m2: number;
  net_area_m2: number;
  geometry: GeoJsonPolygon;
}

export interface WTRuleResult {
  code: string;
  description: string;
  passed: boolean;
  detail: string;
}

export interface WTResult {
  passed: boolean;
  score: number;
  rules: WTRuleResult[];
  issues: string[];
}

export interface LayoutGenerateResponse {
  footprint_area_m2: number;
  circulation_area_m2: number;
  usable_area_m2: number;
  apartments: ApartmentResult[];
  leftover?: GeoJsonPolygon | null;
  wt_validation: WTResult;
  zones: { name: string; geometry: GeoJsonPolygon }[];
  circulation_parts: GeoJsonPolygon[];
  cage_geometries: GeoJsonPolygon[];
  wall_bands: GeoJsonPolygon[];
}

export function generateLayout(req: LayoutGenerateRequest): Promise<LayoutGenerateResponse> {
  return postJson("/layout/generate", req);
}

// ── Circulation / Units (Etap 1 / Etap 2 osobno, redesign 2026-07-02) ──

export interface CorridorCenterlineSegment {
  points: [Point, Point];
  loading: "single" | "double";
  // null gdy nie ma klatki schodowej (backend zamienia float('inf') na null,
  // patrz backend/api/v1/endpoints/layout.py's _finite_or_none) -- final-review
  // Finding 1, 2026-07-03.
  distance_start_m: number | null;
  distance_end_m: number | null;
  max_distance_m: number;
  exceeds_max: boolean;
}

export interface CirculationResponse {
  circulation_geometry: GeoJsonPolygon | null;
  cage_geometries: GeoJsonPolygon[];
  remainder: GeoJsonPolygon; // może być Polygon lub MultiPolygon (patrz backend CirculationResult.remainder)
  centerline: CorridorCenterlineSegment[];
}

export function placeCirculation(
  footprint: Point[],
  circulation: CirculationSpecInput
): Promise<CirculationResponse> {
  return postJson("/layout/circulation", { footprint, circulation });
}

export interface ReshapeCirculationRequest {
  footprint: Point[];
  centerline: { points: [Point, Point] }[];
  corridor_width_m: number;
  cage_geometries: GeoJsonPolygon[];
}

export interface ReshapeCirculationResponse {
  circulation_geometry: GeoJsonPolygon | null;
  remainder: GeoJsonPolygon;
  centerline: CorridorCenterlineSegment[];
}

export function reshapeCirculation(req: ReshapeCirculationRequest): Promise<ReshapeCirculationResponse> {
  return postJson("/layout/circulation/reshape", req);
}

export interface UnitsResponse {
  apartments: ApartmentResult[];
  leftover: GeoJsonPolygon | null;
}

export function subdivideUnits(
  remainder: GeoJsonPolygon,
  apartments: ApartmentProgramInput[]
): Promise<UnitsResponse> {
  return postJson("/layout/units", { remainder, apartments });
}

export interface SplitResponse {
  polygons: GeoJsonPolygon[];
  areas: number[];
}

export function splitPolygon(footprint: Point[], splitLine: [Point, Point]): Promise<SplitResponse> {
  return postJson("/layout/split", { footprint, split_line: splitLine });
}

// ── Validation (F3-02/03/04) ─────────────────────────────────────────

export interface ApartmentValidationItem {
  apartment_id: string;
  type: string;
  passed: boolean;
  area_m2: number;
  min_width_m: number;
  errors: string[];
  warnings: string[];
}

export interface FullLayoutValidateResponse {
  passed: boolean;
  score: number;
  apartments: ApartmentValidationItem[];
  wt_rules: WTRuleResult[];
  communication_all_connected: boolean;
  communication_issues: string[];
  errors: string[];
  warnings: string[];
}

export interface ApartmentCellData {
  id: string;
  type: string;
  geometry: GeoJsonPolygon;
}

export interface LayoutDataInput {
  footprint: Point[];
  circulation_geometry: GeoJsonPolygon | null;
  cage_geometries: GeoJsonPolygon[];
  corridor_width_m: number;
  stair_width_m: number;
  apartments: ApartmentCellData[];
}

export function validateFullLayout(
  req: LayoutGenerateRequest & { max_corridor_distance_m?: number; layout?: LayoutDataInput | null }
): Promise<FullLayoutValidateResponse> {
  return postJson("/validate/full-layout", req);
}

export interface CommunicationIssueItem {
  apartment_id: string | null;
  error: string;
}

export interface CommunicationValidateResponse {
  all_connected: boolean;
  issues: CommunicationIssueItem[];
}

export function validateCommunication(
  req: LayoutGenerateRequest & {
    min_contact_length_m?: number;
    max_corridor_distance_m?: number;
    min_cage_spacing_m?: number;
  }
): Promise<CommunicationValidateResponse> {
  return postJson("/validate/communication", req);
}

// ── Typologie (F2-13/F2-14) ──────────────────────────────────────────

export interface TypologyPresetItem {
  key: string;
  label: string;
  staircase_position: string;
  corridor_width_m: number;
  staircase_dims_m: [number, number];
  double_loaded: boolean;
  takt_m: [number, number];
  staircase_spacing_m: [number, number] | null;
  max_arm_length_m: number | null;
  staircase_per_apt: number | null;
  apts_per_staircase: [number, number] | null;
}

export function listTypologyPresets(): Promise<{ presets: TypologyPresetItem[] }> {
  return request("/typology/presets");
}

export interface TypologySuggestResponse {
  typology: string;
  bbox_ratio: number;
  concave_vertex_count: number;
  rationale: string;
  suggested_cage_count: number;
  alternative: string | null;
}

export function suggestTypology(points: Point[]): Promise<TypologySuggestResponse> {
  return postJson("/typology/suggest", { points });
}

// ── Solar Analysis (F4) ──────────────────────────────────────────

export interface SunStatusHourModel {
  time_iso: string;
  elevation_deg: number;
  sun_azimuth_deg: number;
  cos_incidence: number;
  status: string;
}

export interface FacadeAnalysisModel {
  apartment_id: string;
  apartment_type: string;
  orientation: string;
  azimuth_deg: number;
  edge: [Point, Point];
  length_m: number;
  hours_total: number;
  hours_status: Record<string, number>;
  hourly: SunStatusHourModel[];
  meets_wt: boolean;
  required_hours: number;
}

export interface SolarAnalyzeResponse {
  latitude: number;
  longitude: number;
  analysis_date: string;
  timezone: string;
  required_hours: number;
  building_azimuth_deg: number | null;
  building_orientation: string | null;
  facades: FacadeAnalysisModel[];
  apartments: Record<string, any>[];
  summary: Record<string, any>;
}

export interface SolarAnalyzeRequest extends LayoutGenerateRequest {
  latitude: number;
  longitude: number;
  analysis_date?: string | null;
  timezone?: string;
  required_hours?: number;
  layout?: LayoutDataInput | null;
}

export function analyzeSolar(req: SolarAnalyzeRequest): Promise<SolarAnalyzeResponse> {
  return postJson("/solar/analyze", req);
}

// ── Optimizer (F5) ───────────────────────────────────────────────

export interface OptimizerRunRequest {
  footprint: Point[];
  apartments: ApartmentProgramInput[];
  latitude: number;
  longitude: number;
  analysis_date?: string | null;
  timezone?: string;
  required_hours?: number;
  cage_mode?: "auto" | "single" | "multiple";
  corridor_width_m?: number;
  stair_width_m?: number;
  cage_size_m?: number;
  local_law?: string | null;
  max_variants?: number;
}

export interface OptimizerVariantMetrics {
  solar_score: number;
  wt_compliance: number;
  total_apartments: number;
  total_facades: number;
  facades_meeting_wt: number;
  wt_rules_passed: number;
  wt_rules_total: number;
  communication_ok: boolean;
  communication_issues: string[];
}

export interface OptimizerVariant {
  id: string;
  rank: number;
  config: Record<string, any>;
  metrics: OptimizerVariantMetrics;
  building_azimuth_deg: number | null;
  building_orientation: string | null;
  apartments: Record<string, any>[];
  solar_summary: Record<string, any>;
  wt_passed: boolean;
  wt_issues: string[];
  layout: LayoutGenerateResponse;
}

export interface OptimizerRunResponse {
  method: string;
  footprint_is_concave: boolean;
  requested_cage_mode: string;
  effective_cage_mode: string;
  variants: OptimizerVariant[];
}

export function runOptimizer(req: OptimizerRunRequest): Promise<OptimizerRunResponse> {
  return postJson("/optimizer/run", req);
}

// ── Export (F6) ──────────────────────────────────────────────────

export interface ExportJsonRequest extends LayoutGenerateRequest {
  project_id?: string | null;
  project_name?: string | null;
  parcel_id?: string | null;
  location: {
    lat: number;
    lon: number;
    address?: string | null;
    city?: string | null;
  };
  analysis_date?: string | null;
  optimizer_results?: OptimizerVariant[];
}

export function exportJsonSnapshot(req: ExportJsonRequest): Promise<any> {
  return postJson("/export/json", req);
}

export function exportDxf(req: ExportJsonRequest): Promise<Blob> {
  return fetch(`${API_BASE}/export/dxf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  }).then(res => res.blob());
}

export function exportPdf(req: any): Promise<Blob> {
  return fetch(`${API_BASE}/export/pdf`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  }).then(res => res.blob());
}
