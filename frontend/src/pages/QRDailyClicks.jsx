import { useState, useEffect, useRef, useMemo } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertCircle, ArrowLeft, RefreshCw } from "lucide-react";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { getDisplayFirstName } from "../utils/displayName";

// Poll interval (ms) — keep modest so 22 stores hitting prod don't
// hammer Mongo. 15s is plenty "live" for QR scans.
const POLL_MS = 15000;

const WINDOW_OPTIONS = [
  { value: "7", label: "Last 7 days" },
  { value: "14", label: "Last 14 days" },
  { value: "30", label: "Last 30 days" },
  { value: "60", label: "Last 60 days" },
];

function formatDayShort(iso) {
  // "2026-05-14" → "May 14"
  const [, m, d] = iso.split("-");
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(m, 10) - 1]} ${parseInt(d, 10)}`;
}

function dayOfWeekShort(iso) {
  const dt = new Date(`${iso}T12:00:00Z`);
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][dt.getUTCDay()];
}

function heatColor(value, peak) {
  if (!value) return "bg-slate-800/40";
  if (peak <= 0) return "bg-slate-700";
  const ratio = Math.min(1, value / peak);
  if (ratio >= 0.75) return "bg-violet-500/80";
  if (ratio >= 0.5) return "bg-violet-500/55";
  if (ratio >= 0.25) return "bg-violet-500/30";
  return "bg-violet-500/15";
}

export default function QRDailyClicks() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState("30");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [pulse, setPulse] = useState(false);
  const lastTotalRef = useRef(0);
  const intervalRef = useRef(null);
  const inflightRef = useRef(false);

  const fetchData = async (silent = false) => {
    if (inflightRef.current) return;
    inflightRef.current = true;
    try {
      if (!silent) setLoading(true);
      const res = await api.get(`/qr/clicks-by-day?days=${days}`);
      const newGrand = res.data?.grand_total ?? 0;
      // Animate a quick pulse when new scans arrive between polls
      if (silent && newGrand > lastTotalRef.current) {
        setPulse(true);
        setTimeout(() => setPulse(false), 1200);
      }
      lastTotalRef.current = newGrand;
      setData(res.data);
      setError(null);
    } catch (err) {
      console.error(err);
      setError(err?.response?.data?.detail || "Failed to load daily clicks");
    } finally {
      setLoading(false);
      inflightRef.current = false;
    }
  };

  // Fetch + poll. Re-establish whenever `days` changes.
  useEffect(() => {
    lastTotalRef.current = 0;
    fetchData(false);
    if (intervalRef.current) clearInterval(intervalRef.current);
    intervalRef.current = setInterval(() => fetchData(true), POLL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  const peak = useMemo(() => {
    if (!data?.rows) return 0;
    let p = 0;
    for (const r of data.rows) {
      for (const v of r.by_day) if (v > p) p = v;
    }
    return p;
  }, [data]);

  const totalsByDay = data?.totals_by_day || [];
  const dayLabels = data?.days || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-3 sm:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 sm:mb-6">
          <div className="flex items-center gap-3 min-w-0">
            <Button asChild variant="ghost" size="sm" className="text-slate-300 hover:bg-slate-800" data-testid="qr-daily-back">
              <Link to="/qr/leaderboard">
                <ArrowLeft className="w-4 h-4 mr-1" />
                Leaderboard
              </Link>
            </Button>
            <div className="hidden sm:block w-px h-6 bg-slate-700" />
            <div className="flex items-center gap-2 min-w-0">
              <Activity className={`w-6 h-6 text-violet-400 ${pulse ? "animate-ping-fast" : ""}`} />
              <div className="min-w-0">
                <h1 className="text-xl sm:text-2xl font-bold text-white">QR Clicks by Day</h1>
                <p className="text-xs text-slate-400">
                  Live updates · refreshes every {POLL_MS / 1000}s
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-[160px] bg-slate-800 border-slate-700 text-slate-100" data-testid="qr-daily-window-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700 text-slate-100">
                {WINDOW_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-200 hover:bg-slate-800"
              onClick={() => fetchData(false)}
              disabled={loading}
              data-testid="qr-daily-refresh"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>

        {/* Live indicator + summary */}
        <div className="flex flex-wrap items-center gap-3 mb-4">
          <div className="flex items-center gap-2 bg-slate-800/60 border border-slate-700 rounded-full px-3 py-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400"></span>
            </span>
            <span className="text-xs text-emerald-300 font-medium">LIVE</span>
            {data?.generated_at && (
              <span className="text-xs text-slate-500">
                · updated {new Date(data.generated_at).toLocaleTimeString()}
              </span>
            )}
          </div>
          {data && (
            <div className="text-xs sm:text-sm text-slate-400">
              <span className="text-white font-semibold">{data.grand_total}</span> scans across{" "}
              <span className="text-white font-semibold">{data.rows.length}</span> staff in the last{" "}
              <span className="text-white font-semibold">{data.window_days}</span> days
            </div>
          )}
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-300 rounded-lg p-3 mb-4 flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            {error}
          </div>
        )}

        {/* Matrix */}
        <div className="bg-slate-800/50 border border-slate-700 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto" data-testid="qr-daily-matrix">
            <table className="min-w-full text-xs sm:text-sm">
              <thead className="bg-slate-800 sticky top-0 z-10">
                <tr>
                  <th className="text-left text-slate-300 font-semibold p-3 sticky left-0 bg-slate-800 z-20 min-w-[160px]">
                    Server
                  </th>
                  <th className="text-right text-slate-300 font-semibold p-3 min-w-[60px]">Total</th>
                  {dayLabels.map((d, i) => {
                    const dow = dayOfWeekShort(d);
                    const isWeekend = dow === "Sat" || dow === "Sun";
                    return (
                      <th
                        key={d}
                        className={`text-center font-medium p-2 min-w-[44px] ${
                          isWeekend ? "text-amber-300/70" : "text-slate-400"
                        }`}
                        title={d}
                        data-testid={`qr-daily-day-${i}`}
                      >
                        <div className="leading-tight">
                          <div className="text-[10px] uppercase tracking-wide">{dow}</div>
                          <div className="text-[10px]">{formatDayShort(d)}</div>
                        </div>
                      </th>
                    );
                  })}
                </tr>
                {/* Totals row */}
                <tr className="bg-slate-800/60 border-t border-slate-700">
                  <th className="text-left text-slate-400 font-medium p-2 sticky left-0 bg-slate-800/60 z-20">
                    Daily total
                  </th>
                  <th className="text-right text-slate-300 font-semibold p-2">
                    {totalsByDay.reduce((a, b) => a + b, 0)}
                  </th>
                  {totalsByDay.map((v, i) => (
                    <th key={i} className="text-center font-semibold text-slate-200 p-2">
                      {v || ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {loading && !data && (
                  <tr>
                    <td colSpan={dayLabels.length + 2} className="text-center p-8 text-slate-400">
                      Loading…
                    </td>
                  </tr>
                )}
                {data?.rows?.length === 0 && (
                  <tr>
                    <td colSpan={dayLabels.length + 2} className="text-center p-8 text-slate-400">
                      No scans recorded in this window.
                    </td>
                  </tr>
                )}
                {data?.rows?.map((row) => (
                  <tr
                    key={row.employee_id || row.name}
                    className="border-t border-slate-700/60 hover:bg-slate-700/30"
                    data-testid={`qr-daily-row-${row.employee_id || row.name}`}
                  >
                    <td className="p-3 sticky left-0 bg-slate-800/80 z-10 min-w-[160px]">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-white truncate">{getDisplayFirstName(row)}</span>
                        {!row.active && (
                          <span className="text-[10px] uppercase tracking-wide bg-slate-700 text-slate-400 px-1.5 py-0.5 rounded">
                            inactive
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5">
                        <span className="text-red-400">{row.totals.yelp}</span>
                        {" / "}
                        <span className="text-blue-400">{row.totals.google}</span>
                        {" / "}
                        <span className="text-emerald-400">{row.totals.tripadvisor}</span>
                      </div>
                    </td>
                    <td className="p-2 text-right">
                      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-violet-500/20 text-violet-300 font-bold">
                        {row.total}
                      </span>
                    </td>
                    {row.by_day.map((v, i) => (
                      <td
                        key={i}
                        className="p-1 text-center"
                        title={`${dayLabels[i]}: ${v} scan${v === 1 ? "" : "s"}`}
                      >
                        <div
                          className={`mx-auto h-7 w-9 rounded flex items-center justify-center text-[11px] font-semibold ${heatColor(v, peak)} ${
                            v ? "text-white" : "text-slate-600"
                          }`}
                        >
                          {v || ""}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="border-t border-slate-700 px-4 py-3 flex flex-wrap items-center gap-4 text-xs text-slate-400">
            <span>Scan intensity:</span>
            <div className="flex items-center gap-1">
              <span className="inline-block w-4 h-4 rounded bg-slate-800/40"></span> 0
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-4 h-4 rounded bg-violet-500/15"></span> low
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-4 h-4 rounded bg-violet-500/30"></span> medium
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-4 h-4 rounded bg-violet-500/55"></span> high
            </div>
            <div className="flex items-center gap-1">
              <span className="inline-block w-4 h-4 rounded bg-violet-500/80"></span> peak
              {peak > 0 && <span className="text-slate-500">({peak})</span>}
            </div>
            <span className="ml-auto text-slate-500">
              Source: <code className="text-slate-400">qr_click_log_immutable</code>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
