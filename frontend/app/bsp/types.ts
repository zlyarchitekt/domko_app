export type BspAreaType = "stairwell" | "corridor" | "apartment";

export interface BspArea {
  id: string;
  type: BspAreaType;
  name: string;
  /** Polygon vertices in meters, ordered, Y pointing up in canvas world coords. */
  points: { x: number; y: number }[];
  apartmentType?: string;
}

export interface BspResult {
  footprint: { x: number; y: number }[];
  areas: BspArea[];
}

export const BSP_COLORS: Record<BspAreaType, { fill: string; stroke: string }> = {
  stairwell: { fill: "#808080", stroke: "#4a4a4a" }, // szary
  corridor: { fill: "#d3d3d3", stroke: "#999999" },  // jasnoszary
  apartment: { fill: "#60a5fa", stroke: "#2563eb" }, // domyślny niebieski dla mieszkań
};

export const APARTMENT_TYPE_COLORS: Record<string, string> = {
  "1": "#60a5fa", // 1-pokojowe - niebieski
  "2": "#4ade80", // 2-pokojowe - zielony
  "3": "#fbbf24", // 3-pokojowe - żółty
  "4": "#f87171", // 4-pokojowe - czerwony
  studio: "#c084fc", // kawalerka - fioletowy
  penthouse: "#fb923c", // penthouse - pomarańczowy
};

export function getApartmentFill(apartmentType?: string): string {
  if (!apartmentType) return BSP_COLORS.apartment.fill;
  return APARTMENT_TYPE_COLORS[apartmentType] ?? BSP_COLORS.apartment.fill;
}

export function getApartmentStroke(apartmentType?: string): string {
  const fill = getApartmentFill(apartmentType);
  // Return a 25 % darker variant of the fill for a clean border.
  return shadeColor(fill, -0.25);
}

function shadeColor(hex: string, percent: number): string {
  const num = parseInt(hex.replace("#", ""), 16);
  const amt = Math.round(255 * percent);
  const R = clampChannel(((num >> 16) & 0xff) + amt);
  const G = clampChannel(((num >> 8) & 0xff) + amt);
  const B = clampChannel((num & 0xff) + amt);
  return `#${((1 << 24) + (R << 16) + (G << 8) + B).toString(16).slice(1)}`;
}

function clampChannel(value: number): number {
  return Math.max(0, Math.min(255, value));
}
