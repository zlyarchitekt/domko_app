import { useSession } from "../state/SessionContext";
import { Download, FileJson, FileType2, FileText } from "lucide-react";
import * as api from "../lib/api";
import { useState } from "react";

export function ExportSection() {
  const { state } = useSession();
  const [loading, setLoading] = useState<string | null>(null);

  const canExport = !!state.layoutResult;

  const buildExportReq = () => {
    if (!state.footprint) return null;
    return {
      footprint: state.footprint.map(p => [p.x, p.y] as api.Point),
      circulation: state.circulation,
      apartments: state.program.map(row => ({
        type: row.type,
        min_area_m2: row.min_area_m2,
        target_count: row.target_count,
      })),
      location: { lat: state.gps.lat, lon: state.gps.lng },
      analysis_date: state.analysisDate,
      optimizer_results: state.optimizerVariants.length > 0 ? state.optimizerVariants : undefined,
      layout: state.layoutResult ? {
        footprint: state.footprint.map(p => [p.x, p.y] as api.Point),
        circulation_geometry: state.layoutResult.circulation_parts[0] || null,
        cage_geometries: state.layoutResult.cage_geometries,
        corridor_width_m: state.circulation.corridor_width_m,
        stair_width_m: state.circulation.stair_width_m,
        apartments: state.layoutResult.apartments.map((a) => ({
          id: a.id,
          type: a.type,
          geometry: a.geometry,
        })),
      } : null
    };
  };

  const handleExportJson = async () => {
    const req = buildExportReq();
    if (!req) return;
    setLoading("json");
    try {
      const res = await api.exportJsonSnapshot(req as any);
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `domko_export_${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Błąd eksportu JSON");
    } finally {
      setLoading(null);
    }
  };

  const handleExportDxf = async () => {
    const req = buildExportReq();
    if (!req) return;
    setLoading("dxf");
    try {
      const blob = await api.exportDxf(req as any);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `domko_export_${new Date().toISOString().split('T')[0]}.dxf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Błąd eksportu DXF");
    } finally {
      setLoading(null);
    }
  };

  const handleExportPdf = async () => {
    const req = buildExportReq();
    if (!req) return;
    setLoading("pdf");
    try {
      const blob = await api.exportPdf(req);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `domko_raport_${new Date().toISOString().split('T')[0]}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert("Błąd eksportu PDF");
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold">Eksport i Raportowanie</h3>
      <p className="text-sm text-gray-500">Zapisz wyniki pracy lokalnie lub wygeneruj raport PDF.</p>
      
      <div className="grid grid-cols-1 gap-2">
        <button
          onClick={handleExportJson}
          disabled={!canExport || loading !== null}
          className="flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded disabled:opacity-50"
        >
          <FileJson className="w-4 h-4" />
          {loading === "json" ? "Trwa..." : "Pobierz projekt (JSON)"}
        </button>
        <button
          onClick={handleExportDxf}
          disabled={!canExport || loading !== null}
          className="flex items-center justify-center gap-2 px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-800 rounded disabled:opacity-50"
        >
          <FileType2 className="w-4 h-4" />
          {loading === "dxf" ? "Trwa..." : "Eksportuj obrysy (DXF)"}
        </button>
        <button
          onClick={handleExportPdf}
          disabled={!canExport || loading !== null}
          className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
        >
          <FileText className="w-4 h-4" />
          {loading === "pdf" ? "Trwa generowanie..." : "Generuj Raport (PDF)"}
        </button>
      </div>
    </div>
  );
}
