import { ApartmentValidationItem, LayoutGenerateResponse, FullLayoutValidateResponse } from "./api";

export type ApartmentStatus = "ok" | "warning" | "error";

/**
 * /layout/generate i /validate/full-layout wołane są niezależnie (dwa osobne
 * wywołania backendu — patrz SessionContext.regenerate) i każde generuje
 * WŁASNE losowe id mieszkań (uuid4 w generate_layout). Backend nie daje
 * stabilnego klucza łączącego oba wyniki, ale algorytm jest deterministyczny
 * dla tych samych parametrów wejściowych — więc kolejność (indeks w tablicy)
 * jest tym, po czym łączymy oba wyniki. F2-12/F3-06.
 */
export function deriveApartmentStatuses(
  layout: LayoutGenerateResponse | null,
  validation: FullLayoutValidateResponse | null
): Map<string, ApartmentStatus> {
  const map = new Map<string, ApartmentStatus>();
  if (!layout) return map;
  layout.apartments.forEach((apt, index) => {
    const v: ApartmentValidationItem | undefined = validation?.apartments[index];
    if (!v) {
      map.set(apt.id, "ok");
      return;
    }
    if (v.errors.length > 0) map.set(apt.id, "error");
    else if (v.warnings.length > 0) map.set(apt.id, "warning");
    else map.set(apt.id, "ok");
  });
  return map;
}

export function apartmentValidationByIndex(
  layout: LayoutGenerateResponse | null,
  validation: FullLayoutValidateResponse | null
): Map<string, ApartmentValidationItem> {
  const map = new Map<string, ApartmentValidationItem>();
  if (!layout || !validation) return map;
  layout.apartments.forEach((apt, index) => {
    const v = validation.apartments[index];
    if (v) map.set(apt.id, v);
  });
  return map;
}
