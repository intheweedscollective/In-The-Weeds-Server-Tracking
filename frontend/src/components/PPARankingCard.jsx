/**
 * PPARankingCard
 *
 * Expandable card on the Reports landing page that lists every active
 * employee ranked by PPA top-to-bottom for the active quarter, with
 * +/- vs the LOCATION average (mean PPA across all scored employees).
 *
 * Hits:
 *   GET  /api/v2/reports/ppa-ranking
 *   GET  /api/v2/reports/ppa-ranking/pdf
 */

import { useState, useEffect, useCallback } from "react";
import { DollarSign, ChevronDown, ChevronUp, FileText, Image as ImageIcon } from "lucide-react";
import { Button } from "./ui/button";
import api from "../lib/api";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

export default function PPARankingCard() {
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [downloading, setDownloading] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/v2/reports/ppa-ranking");
      setData(r.data);
    } catch (e) {
      console.error("PPA ranking fetch failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (expanded && !data) load();
  }, [expanded, data, load]);

  const downloadAsset = async (kind) => {
    // kind = "pdf" | "slide"
    setDownloading(kind);
    try {
      const ext = kind === "pdf" ? "pdf" : "png";
      const res = await fetch(
        `${BACKEND_URL}/api/v2/reports/ppa-ranking/${kind}`,
      );
      if (!res.ok) throw new Error(`${kind} generation failed`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ppa_ranking_${data?.quarter || "current"}_${data?.year || ""}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (e) {
      console.error(e);
      alert(`${kind.toUpperCase()} download failed. Try again.`);
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div
      className="bg-slate-800 rounded-2xl border border-slate-700 p-5"
      data-testid="ppa-ranking-card"
    >
      <button
        type="button"
        className="w-full flex items-center justify-between gap-3 group"
        onClick={() => setExpanded((v) => !v)}
        data-testid="ppa-ranking-toggle"
      >
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center shrink-0">
            <DollarSign className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="text-left min-w-0">
            <h2 className="font-bold text-white truncate">PPA Ranking</h2>
            <p className="text-xs text-slate-500 truncate">
              Every server ranked by PPA · current quarter · ± vs location avg
            </p>
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="w-5 h-5 text-slate-400 shrink-0" />
        ) : (
          <ChevronDown className="w-5 h-5 text-slate-400 shrink-0" />
        )}
      </button>

      {expanded && (
        <div className="mt-4 space-y-3" data-testid="ppa-ranking-body">
          {/* Summary + PDF button */}
          <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-700">
            <div className="text-sm text-slate-300">
              {loading ? (
                <span className="text-slate-500">Loading ranking…</span>
              ) : data ? (
                <>
                  <span className="font-semibold text-white">
                    {data.quarter} {data.year}
                  </span>
                  <span className="mx-2 text-slate-600">·</span>
                  <span>{data.count} servers ranked</span>
                  <span className="mx-2 text-slate-600">·</span>
                  <span>
                    Location avg{" "}
                    <span className="text-amber-400 font-semibold">
                      ${data.location_average_ppa?.toFixed(2)}
                    </span>
                  </span>
                </>
              ) : (
                <span className="text-slate-500">No data</span>
              )}
            </div>
            <div className="flex gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                className="border-amber-700 text-amber-200 hover:bg-amber-950/40"
                onClick={() => downloadAsset("slide")}
                disabled={!data || downloading === "slide" || !data?.rows?.length}
                data-testid="ppa-ranking-download-slide"
              >
                <ImageIcon className="w-3.5 h-3.5 mr-1.5" />
                {downloading === "slide" ? "Building…" : "Yodeck Slide"}
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="border-red-700 text-red-200 hover:bg-red-950/40"
                onClick={() => downloadAsset("pdf")}
                disabled={!data || downloading === "pdf" || !data?.rows?.length}
                data-testid="ppa-ranking-download-pdf"
              >
                <FileText className="w-3.5 h-3.5 mr-1.5" />
                {downloading === "pdf" ? "Building PDF…" : "PDF"}
              </Button>
            </div>
          </div>

          {/* Table */}
          {data && data.rows.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-slate-700">
              <table className="w-full text-sm" data-testid="ppa-ranking-table">
                <thead className="bg-slate-900 text-slate-400 text-xs uppercase tracking-wide">
                  <tr>
                    <th className="px-3 py-2 text-left">#</th>
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">Tier</th>
                    <th className="px-3 py-2 text-right">PPA</th>
                    <th className="px-3 py-2 text-right">vs Location</th>
                    <th className="px-3 py-2 text-right">%</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {data.rows.map((r) => {
                    const positive = r.vs_location > 0;
                    const negative = r.vs_location < 0;
                    return (
                      <tr
                        key={r.employee_id || r.rank}
                        className="hover:bg-slate-900/60"
                        data-testid={`ppa-row-${r.rank}`}
                      >
                        <td className="px-3 py-2 text-slate-400 font-mono">
                          {r.rank}
                        </td>
                        <td className="px-3 py-2 text-white font-medium">
                          {r.name}
                        </td>
                        <td className="px-3 py-2 text-slate-400 text-xs">
                          {r.tier || "—"}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-slate-200">
                          ${r.ppa.toFixed(2)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono ${
                            positive
                              ? "text-emerald-400"
                              : negative
                              ? "text-rose-400"
                              : "text-slate-500"
                          }`}
                        >
                          {positive ? "+" : negative ? "−" : ""}$
                          {Math.abs(r.vs_location).toFixed(2)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right font-mono text-xs ${
                            positive
                              ? "text-emerald-400"
                              : negative
                              ? "text-rose-400"
                              : "text-slate-500"
                          }`}
                        >
                          {positive ? "+" : negative ? "−" : ""}
                          {Math.abs(r.vs_location_pct).toFixed(1)}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {data && data.rows.length === 0 && !loading && (
            <div className="rounded-lg border border-slate-700 bg-slate-900/40 px-4 py-6 text-center text-sm text-slate-400">
              No PPA data found for the active quarter.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
