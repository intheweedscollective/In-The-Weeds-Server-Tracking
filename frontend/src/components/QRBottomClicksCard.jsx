import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, QrCode, Users } from "lucide-react";
import api from "../lib/api";
import { getDisplayFirstName } from "../utils/displayName";

/**
 * QR Bottom Clicks — surfaces ACTIVE employees with the lowest QR
 * engagement so management can spot coaching opportunities.
 *
 * - Pulled from /api/qr/stats `bottom_10` (already filtered to active
 *   employees on the backend).
 * - Each row flagged with an "engagement warning" when total clicks
 *   are below `engagement_warning_threshold` (default 5).
 */
export default function QRBottomClicksCard({ showViewAll = true, limit = 10 }) {
  const [rows, setRows] = useState([]);
  const [threshold, setThreshold] = useState(5);
  const [activeCount, setActiveCount] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const res = await api.get("/qr/stats");
        if (cancelled) return;
        setRows((res.data.bottom_10 || []).slice(0, limit));
        setThreshold(res.data.engagement_warning_threshold ?? 5);
        setActiveCount(res.data.active_employees || 0);
      } catch (err) {
        console.error("Failed to load QR bottom clicks:", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [limit]);

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5 animate-pulse" data-testid="qr-bottom-clicks-loading">
        <div className="h-6 bg-slate-700 rounded w-1/2 mb-4"></div>
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={`skeleton-${i}`} className="h-12 bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="bg-slate-800 rounded-2xl border border-amber-500/30 overflow-hidden"
      data-testid="qr-bottom-clicks-card"
    >
      <div className="p-5 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h2 className="font-bold text-white">Engagement Warning</h2>
            <p className="text-xs text-slate-500">
              Lowest QR engagement · {activeCount} active employees
            </p>
          </div>
        </div>
        {showViewAll && (
          <Link
            to="/qr/leaderboard"
            className="text-sm text-amber-400 font-medium hover:underline"
            data-testid="qr-bottom-view-all"
          >
            View All →
          </Link>
        )}
      </div>

      <div className="px-4 py-2 bg-amber-500/5 border-b border-slate-700 text-xs text-amber-300/80 flex items-start gap-2">
        <Users className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        <span>
          These active staff have the fewest review-page scans. Anyone under <strong>{threshold}</strong> clicks may benefit from a coaching nudge on asking guests for reviews.
        </span>
      </div>

      <div className="divide-y divide-slate-700">
        {rows.length > 0 ? (
          rows.map((emp, idx) => {
            const flagged = (emp.total || 0) < threshold;
            return (
              <div
                key={`${emp.name}-${idx}`}
                className={`flex items-center justify-between p-4 transition-colors ${
                  flagged ? "hover:bg-amber-900/10" : "hover:bg-slate-750"
                }`}
                data-testid={`qr-bottom-row-${idx}`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                    flagged ? "bg-amber-500/30 text-amber-200" : "bg-slate-600 text-slate-300"
                  }`}>
                    {idx + 1}
                  </div>
                  <div className="min-w-0">
                    <p className="font-medium text-white truncate">{getDisplayFirstName(emp)}</p>
                    <p className="text-xs text-slate-500">
                      {emp.days_since_last_scan == null
                        ? "No scans yet"
                        : emp.days_since_last_scan === 0
                          ? "Last scan today"
                          : `Last scan ${emp.days_since_last_scan}d ago`}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <div className="flex items-center gap-1 text-xs">
                    <span className="text-red-400">{emp.yelp_clicks}</span>
                    <span className="text-slate-500">/</span>
                    <span className="text-blue-400">{emp.google_clicks}</span>
                    <span className="text-slate-500">/</span>
                    <span className="text-emerald-400">{emp.tripadvisor_clicks || 0}</span>
                  </div>
                  <div className={`flex items-center gap-1 px-2 py-1 rounded-full ${
                    flagged ? "bg-amber-500/20" : "bg-slate-700"
                  }`}>
                    {flagged && <AlertTriangle className="w-3 h-3 text-amber-400" />}
                    <span className={`text-xs font-bold ${flagged ? "text-amber-300" : "text-slate-300"}`}>
                      {emp.total}
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        ) : (
          <div className="p-6 text-center">
            <QrCode className="w-10 h-10 text-slate-600 mx-auto mb-2" />
            <p className="text-slate-400 text-sm">No active employees with QR data</p>
          </div>
        )}
      </div>
    </div>
  );
}
