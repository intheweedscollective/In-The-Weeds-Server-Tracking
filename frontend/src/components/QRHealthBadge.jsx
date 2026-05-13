import { useState, useEffect } from "react";
import { Activity, AlertTriangle, CheckCircle2 } from "lucide-react";
import api from "../lib/api";

/**
 * QRHealthBadge
 *
 * Compact dashboard badge that polls /api/qr/admin/health and shows:
 *  - Green if no long gaps in the immutable click log.
 *  - Amber/red if a gap > 14 days was detected (tracking might be broken).
 *
 * Lives in the dashboard header so a silent QR-tracking outage gets
 * surfaced within a page-load instead of weeks later.
 */
export default function QRHealthBadge() {
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get("/qr/admin/health");
        if (!cancelled) setHealth(res.data);
      } catch (e) {
        if (!cancelled) setHealth({ status: "unknown" });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading || !health) {
    return null;
  }

  const last7d = health?.last_7d?.qr_click_log_immutable ?? 0;
  const gaps = health?.long_gaps_in_immutable_log || [];
  const isAlert = health?.status === "alert";
  const isUnknown = health?.status === "unknown";

  const palette = isUnknown
    ? "bg-slate-800/60 border-slate-600 text-slate-400"
    : isAlert
    ? "bg-amber-900/40 border-amber-600 text-amber-200"
    : "bg-emerald-900/30 border-emerald-700 text-emerald-300";

  const Icon = isUnknown ? Activity : isAlert ? AlertTriangle : CheckCircle2;

  const lastGap = gaps.length > 0 ? gaps[gaps.length - 1] : null;
  const tooltip = isUnknown
    ? "QR health endpoint unreachable"
    : isAlert && lastGap
    ? `Last silent gap: ${lastGap.from} → ${lastGap.to} (${lastGap.days_silent} days). ${last7d} scans in last 7 days.`
    : `${last7d} scans in last 7 days • no tracking gaps detected`;

  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1 border rounded-md text-xs ${palette}`}
      data-testid="qr-health-badge"
      title={tooltip}
    >
      <Icon className="w-3.5 h-3.5" />
      <span className="font-medium">
        QR Tracking: {isUnknown ? "—" : isAlert ? "Gap Detected" : "Healthy"}
      </span>
      <span className="opacity-70 hidden sm:inline">· {last7d}/7d</span>
    </div>
  );
}
