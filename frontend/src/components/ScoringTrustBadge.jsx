import { useState, useEffect } from "react";
import { ShieldCheck, ShieldAlert, ShieldX, ChevronRight } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";

/**
 * ScoringTrustBadge
 *
 * Compact dashboard badge that polls /api/v2/admin/scoring-trust and
 * surfaces a green/amber/red shield indicating the health of the scoring
 * pipeline:
 *   • Quarter-settings drift vs canonical engine constants
 *   • Data-integrity validator (P0/P1/P2 counts)
 *   • Active alias collisions
 *
 * Click opens a detailed modal with remediation actions. Admin-only.
 */
export default function ScoringTrustBadge() {
  const { user } = useAuth();
  const [trust, setTrust] = useState(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [normalizing, setNormalizing] = useState(false);
  const [mergingId, setMergingId] = useState(null);

  useEffect(() => {
    if (!user?.is_admin) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get("/v2/admin/scoring-trust");
        if (!cancelled) setTrust(res.data);
      } catch {
        if (!cancelled) setTrust({ status: "unknown" });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  // Admin-only widget — silently hides for public viewers.
  if (!user?.is_admin) return null;
  if (loading || !trust) return null;

  const status = trust.status || "unknown";

  const palette =
    status === "green"
      ? "bg-emerald-900/30 border-emerald-700 text-emerald-300"
      : status === "amber"
      ? "bg-amber-900/40 border-amber-600 text-amber-200"
      : status === "red"
      ? "bg-rose-900/40 border-rose-600 text-rose-200"
      : "bg-slate-800/60 border-slate-600 text-slate-400";

  const Icon =
    status === "green" ? ShieldCheck : status === "red" ? ShieldX : ShieldAlert;

  const label =
    status === "green"
      ? "Scoring Verified"
      : status === "red"
      ? "Action Required"
      : status === "amber"
      ? "Minor Drift"
      : "Unknown";

  const headline = trust.headline || label;
  const issues = trust.issues || [];
  const warnings = trust.warnings || [];
  const details = trust.details || {};

  const refresh = async () => {
    setLoading(true);
    try {
      const res = await api.get("/v2/admin/scoring-trust");
      setTrust(res.data);
    } catch {
      setTrust({ status: "unknown" });
    } finally {
      setLoading(false);
    }
  };

  const runNormalize = async (apply) => {
    setNormalizing(true);
    try {
      const url = apply
        ? "/v2/admin/normalize-quarter-settings?apply=true"
        : "/v2/admin/normalize-quarter-settings";
      const res = await api.post(url);
      const summary = res.data;
      if (apply) {
        alert(
          `Normalized ${summary.quarters_applied} quarter(s) (${summary.field_writes_total} field writes). Re-checking trust…`,
        );
        await refresh();
      } else {
        alert(
          `Dry-run: ${summary.quarters_needing_change} quarter(s) need changes. ` +
            `Click "Apply Normalize" to commit.`,
        );
      }
    } catch (e) {
      alert(`Normalize failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setNormalizing(false);
    }
  };

  const mergeCollision = async (pair) => {
    if (!pair?.primary_id || !pair?.duplicate_id) return;
    const ok = window.confirm(
      `Merge "${pair.duplicate_name}" INTO "${pair.primary_name}"?\n\n` +
        `The duplicate's name will become an alias on the primary, and all\n` +
        `future POS / CV / RT uploads for either name will land on the primary record.\n` +
        `This action is not undoable from the UI.`,
    );
    if (!ok) return;
    setMergingId(pair.duplicate_id);
    try {
      const res = await api.post("/v2/employees/merge", {
        survivor_id: pair.primary_id,
        duplicate_id: pair.duplicate_id,
      });
      alert(res.data?.message || "Merge complete.");
      await refresh();
    } catch (e) {
      alert(`Merge failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setMergingId(null);
    }
  };

  return (
    <>
      <button
        type="button"
        className={`flex items-center gap-1.5 px-2.5 py-1 border rounded-md text-xs cursor-pointer hover:brightness-125 transition ${palette}`}
        data-testid="scoring-trust-badge"
        title={headline}
        onClick={() => setOpen(true)}
      >
        <Icon className="w-3.5 h-3.5" />
        <span className="font-medium">Trust: {label}</span>
        <ChevronRight className="w-3 h-3 opacity-60" />
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="max-w-2xl bg-slate-900 border-slate-700 text-slate-100"
          data-testid="scoring-trust-modal"
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Icon className="w-5 h-5" />
              Scoring Trust Score
            </DialogTitle>
            <DialogDescription className="text-slate-400">
              {headline}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 mt-2">
            {issues.length > 0 && (
              <div className="rounded-md border border-rose-700 bg-rose-950/40 p-3">
                <div className="text-xs font-semibold text-rose-300 mb-2">
                  Blockers
                </div>
                <ul className="text-sm text-rose-100 space-y-1 list-disc list-inside">
                  {issues.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {warnings.length > 0 && (
              <div className="rounded-md border border-amber-700 bg-amber-950/40 p-3">
                <div className="text-xs font-semibold text-amber-300 mb-2">
                  Advisory
                </div>
                <ul className="text-sm text-amber-100 space-y-1 list-disc list-inside">
                  {warnings.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {issues.length === 0 && warnings.length === 0 && (
              <div className="rounded-md border border-emerald-700 bg-emerald-950/40 p-3 text-sm text-emerald-200">
                All three checks pass — scoring engine is canonical, data
                integrity is clean, no alias collisions detected.
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
              <div className="rounded border border-slate-700 bg-slate-800/60 p-3">
                <div className="text-slate-400 mb-1">Quarter Settings</div>
                <div className="text-base font-semibold text-white">
                  {details.quarter_settings?.drift_count ?? 0} drift /{" "}
                  {details.quarter_settings?.total ?? 0} total
                </div>
                <div className="text-slate-500 mt-1">
                  Current: {details.quarter_settings?.current_quarter}
                </div>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/60 p-3">
                <div className="text-slate-400 mb-1">Data Integrity</div>
                <div className="text-base font-semibold text-white">
                  P0 {details.integrity?.p0_issues ?? 0} · P1{" "}
                  {details.integrity?.p1_issues ?? 0} · P2{" "}
                  {details.integrity?.p2_issues ?? 0}
                </div>
                <div className="text-slate-500 mt-1">
                  Gate: {details.integrity?.deploy_gate}
                </div>
              </div>
              <div className="rounded border border-slate-700 bg-slate-800/60 p-3">
                <div className="text-slate-400 mb-1">Alias Collisions</div>
                <div className="text-base font-semibold text-white">
                  {details.alias_collisions?.count ?? 0} active
                </div>
                {details.alias_collisions?.pairs?.length > 0 && (
                  <div className="text-slate-500 mt-1 text-[11px]">
                    one-click merge below ↓
                  </div>
                )}
              </div>
            </div>

            {details.alias_collisions?.pairs?.length > 0 && (
              <div className="rounded-md border border-rose-800/60 bg-rose-950/20 p-3">
                <div className="text-xs font-semibold text-rose-200 mb-2">
                  Resolve Alias Collisions
                </div>
                <div className="space-y-2">
                  {details.alias_collisions.pairs.map((pair) => (
                    <div
                      key={pair.duplicate_id || pair.duplicate_name}
                      className="flex items-center justify-between gap-3 rounded border border-slate-700 bg-slate-900/60 p-2 text-sm"
                      data-testid={`collision-pair-${pair.duplicate_id || pair.duplicate_name}`}
                    >
                      <div className="text-slate-200 truncate">
                        <span className="font-semibold">
                          {pair.duplicate_name}
                        </span>
                        <span className="text-slate-500 mx-2">→</span>
                        <span className="text-emerald-300 font-semibold">
                          {pair.primary_name}
                        </span>
                      </div>
                      <button
                        type="button"
                        className="px-2.5 py-1 rounded bg-rose-700 hover:bg-rose-600 text-white text-xs disabled:opacity-50 shrink-0"
                        onClick={() => mergeCollision(pair)}
                        disabled={mergingId !== null}
                        data-testid={`merge-collision-${pair.duplicate_id || pair.duplicate_name}`}
                      >
                        {mergingId === pair.duplicate_id ? "Merging…" : "Merge"}
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-md border border-slate-700 bg-slate-800/40 p-3 text-xs text-slate-300 space-y-1">
              <div className="font-semibold text-slate-200 mb-1">
                Remediation
              </div>
              <div>
                <b>Scoring drift:</b> Run "Apply Normalize" below (canonical
                weights, RT 0.33/cap 20, CV +1/-2).
              </div>
              <div>
                <b>Alias collisions:</b> Click the "Merge" button on each pair
                above (or open Nickname Manager for manual control).
              </div>
              <div>
                <b>Integrity issues:</b> See full report at{" "}
                <code className="text-slate-400">/api/v2/admin/integrity</code>.
              </div>
            </div>
          </div>

          <DialogFooter className="gap-2 mt-2">
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 text-sm"
              onClick={refresh}
              disabled={normalizing}
              data-testid="scoring-trust-refresh"
            >
              Refresh
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 text-sm"
              onClick={() => runNormalize(false)}
              disabled={normalizing}
              data-testid="scoring-trust-dry-run"
            >
              Dry-Run Normalize
            </button>
            <button
              type="button"
              className="px-3 py-1.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-sm disabled:opacity-50"
              onClick={() => runNormalize(true)}
              disabled={normalizing}
              data-testid="scoring-trust-apply-normalize"
            >
              {normalizing ? "Working…" : "Apply Normalize"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
