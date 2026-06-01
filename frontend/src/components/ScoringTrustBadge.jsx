import { useState, useEffect, useCallback, useRef } from "react";
import { ShieldCheck, ShieldAlert, ShieldX, ChevronRight, Wand2 } from "lucide-react";
import { toast } from "sonner";
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

const AUTO_HEAL_PREF_KEY = "scoring_trust_auto_heal";
const AUTO_HEAL_COOLDOWN_KEY = "scoring_trust_auto_heal_last_run";
const AUTO_HEAL_COOLDOWN_MS = 60 * 60 * 1000; // 1 hour

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
  const [autoHealEnabled, setAutoHealEnabled] = useState(() => {
    if (typeof window === "undefined") return true;
    const v = localStorage.getItem(AUTO_HEAL_PREF_KEY);
    return v === null ? true : v === "true";
  });
  const autoHealRanRef = useRef(false);

  const fetchTrust = useCallback(async () => {
    try {
      const res = await api.get("/v2/admin/scoring-trust");
      return res.data;
    } catch {
      return { status: "unknown" };
    }
  }, []);

  // Silent auto-heal: runs at most once per mount, throttled to 1/hour.
  // Triggers only when: (a) user is admin, (b) feature enabled,
  // (c) trust is red/amber AND has fixable signals (drift or collisions).
  const runAutoHeal = useCallback(async (currentTrust) => {
    const details = currentTrust?.details || {};
    const drift = details.quarter_settings?.drift_count || 0;
    const collisions = details.alias_collisions?.count || 0;
    if (drift === 0 && collisions === 0) return null;

    const toastId = toast.loading("Auto-healing scoring engine…");
    try {
      const normRes = await api.post(
        "/v2/admin/normalize-quarter-settings?apply=true",
      );
      const normCount = normRes.data?.quarters_applied || 0;

      const pairs = details.alias_collisions?.pairs || [];
      let merged = 0;
      for (const p of pairs) {
        if (!p?.primary_id || !p?.duplicate_id) continue;
        try {
          await api.post("/v2/employees/merge", {
            survivor_id: p.primary_id,
            duplicate_id: p.duplicate_id,
          });
          merged += 1;
        } catch {
          // Skip; surfaced later by refresh().
        }
      }

      if (normCount === 0 && merged === 0) {
        toast.dismiss(toastId);
        return null;
      }
      toast.success("Scoring engine auto-healed.", {
        id: toastId,
        description: `Normalized ${normCount} quarter(s) · Merged ${merged} collision(s).`,
      });
      return { normCount, merged };
    } catch (e) {
      toast.error(
        `Auto-heal failed: ${e?.response?.data?.detail || e.message}`,
        { id: toastId },
      );
      return null;
    }
  }, []);

  useEffect(() => {
    if (!user?.is_admin) return;
    let cancelled = false;
    (async () => {
      const data = await fetchTrust();
      if (cancelled) return;
      setTrust(data);
      setLoading(false);

      // Silent auto-heal — bounded by cooldown + per-mount guard.
      if (autoHealEnabled && !autoHealRanRef.current) {
        const last = parseInt(
          localStorage.getItem(AUTO_HEAL_COOLDOWN_KEY) || "0",
          10,
        );
        const now = Date.now();
        if (now - last > AUTO_HEAL_COOLDOWN_MS) {
          autoHealRanRef.current = true;
          const result = await runAutoHeal(data);
          if (result) {
            localStorage.setItem(AUTO_HEAL_COOLDOWN_KEY, String(now));
            const refreshed = await fetchTrust();
            if (!cancelled) setTrust(refreshed);
          }
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user, fetchTrust, autoHealEnabled, runAutoHeal]);

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
    const data = await fetchTrust();
    setTrust(data);
    setLoading(false);
  };

  const runNormalize = async (apply) => {
    setNormalizing(true);
    const toastId = toast.loading(
      apply ? "Applying canonical scoring constants…" : "Checking scoring drift…",
    );
    try {
      const url = apply
        ? "/v2/admin/normalize-quarter-settings?apply=true"
        : "/v2/admin/normalize-quarter-settings";
      const res = await api.post(url);
      const s = res.data;
      if (apply) {
        toast.success(
          s.quarters_applied > 0
            ? `Normalized ${s.quarters_applied} quarter(s) · ${s.field_writes_total} field writes.`
            : "Already canonical — no changes needed.",
          { id: toastId },
        );
        await refresh();
      } else {
        toast.message(
          s.quarters_needing_change > 0
            ? `${s.quarters_needing_change} quarter(s) need changes — click "Apply Normalize".`
            : "Already canonical — no drift detected.",
          { id: toastId },
        );
      }
      return s;
    } catch (e) {
      toast.error(`Normalize failed: ${e?.response?.data?.detail || e.message}`, {
        id: toastId,
      });
    } finally {
      setNormalizing(false);
    }
  };

  const mergeCollision = async (pair, opts = {}) => {
    if (!pair?.primary_id || !pair?.duplicate_id) return;
    setMergingId(pair.duplicate_id);
    const toastId =
      opts.silent ? null : toast.loading(`Merging ${pair.duplicate_name}…`);
    try {
      const res = await api.post("/v2/employees/merge", {
        survivor_id: pair.primary_id,
        duplicate_id: pair.duplicate_id,
      });
      if (!opts.silent) {
        toast.success(
          `${pair.duplicate_name} → ${pair.primary_name}`,
          { id: toastId, description: res.data?.message },
        );
      }
      if (!opts.skipRefresh) await refresh();
      return true;
    } catch (e) {
      if (!opts.silent) {
        toast.error(
          `Merge failed: ${e?.response?.data?.detail || e.message}`,
          { id: toastId },
        );
      }
      return false;
    } finally {
      setMergingId(null);
    }
  };

  const autoFix = async () => {
    setNormalizing(true);
    const toastId = toast.loading("Auto-fixing scoring engine…");
    try {
      // 1. Normalize quarter settings.
      const normRes = await api.post(
        "/v2/admin/normalize-quarter-settings?apply=true",
      );
      const normCount = normRes.data?.quarters_applied || 0;

      // 2. Merge every alias collision in series.
      const pairs = details.alias_collisions?.pairs || [];
      let merged = 0;
      for (const p of pairs) {
        const ok = await mergeCollision(p, { silent: true, skipRefresh: true });
        if (ok) merged += 1;
      }

      toast.success("Auto-fix complete.", {
        id: toastId,
        description: `Normalized ${normCount} quarter(s) · Merged ${merged}/${pairs.length} collision(s).`,
      });
      await refresh();
    } catch (e) {
      toast.error(`Auto-fix failed: ${e?.response?.data?.detail || e.message}`, {
        id: toastId,
      });
    } finally {
      setNormalizing(false);
    }
  };

  const runDemoPrep = async () => {
    // Pull current dashboard quarter from the snapshot details if available.
    const details = trust?.details || {};
    const cq = details.quarter_settings?.current_quarter || "";
    // Try to parse "2026 Q2" → year + quarter
    const m = /^(\d{4})\s+(Q[1-4])$/.exec(cq);
    if (!m) {
      toast.error("Could not detect current quarter. Try refreshing.");
      return;
    }
    const [, year, quarter] = m;
    setNormalizing(true);
    const toastId = toast.loading(`Demo-prep running for ${year} ${quarter}…`);
    try {
      const res = await api.post(
        `/v2/admin/demo-prep?quarter=${quarter}&year=${year}&apply=true`,
      );
      const d = res.data;
      const fixes = d.display_name_fixes?.length || 0;
      const aliasDedup = d.v2_dedup_actions?.length || 0;
      const sameNameDedup = d.same_name_dedup_actions?.length || 0;
      const rescored = d.rescore?.rescored || 0;
      const snapSync = d.snapshot?.ok;
      toast.success("Demo-prep complete.", {
        id: toastId,
        description:
          `Renamed ${fixes} · Merged ${aliasDedup} alias + ${sameNameDedup} same-name dup(s) · ` +
          `Rescored ${rescored} · Snapshot ${snapSync ? "synced" : "skipped"}.`,
      });
      await refresh();
    } catch (e) {
      toast.error(
        `Demo-prep failed: ${e?.response?.data?.detail || e.message}`,
        { id: toastId },
      );
    } finally {
      setNormalizing(false);
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

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
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
              <div className="rounded border border-slate-700 bg-slate-800/60 p-3" data-testid="scoring-trust-metric-integrity">
                <div className="text-slate-400 mb-1">Metric Integrity</div>
                <div className="text-base font-semibold text-white">
                  {details.metric_integrity?.count ?? 0} mismatch
                  {(details.metric_integrity?.count ?? 0) === 1 ? "" : "es"}
                </div>
                <div className="text-slate-500 mt-1 text-[11px]">
                  tol ±{details.metric_integrity?.tolerance_pct ?? 2}%
                </div>
                {(details.metric_integrity?.suppressed_by_reconciliation ?? 0) > 0 && (
                  <div className="text-emerald-400 mt-1 text-[11px]" data-testid="trust-suppressed-count">
                    {details.metric_integrity.suppressed_by_reconciliation} cleared via Reconciliation
                  </div>
                )}
              </div>
            </div>

            {details.metric_integrity?.mismatches?.length > 0 && (
              <div className="rounded-md border border-amber-800/60 bg-amber-950/20 p-3" data-testid="scoring-trust-metric-mismatches">
                <div className="text-xs font-semibold text-amber-200 mb-2">
                  Metric Drift — derived ratios don't match raw inputs
                </div>
                <div className="space-y-1 max-h-44 overflow-y-auto">
                  {details.metric_integrity.mismatches.map((m, idx) => (
                    <div
                      key={`${m.employee_id || m.name}-${m.metric}-${idx}`}
                      className="flex items-center justify-between gap-3 rounded border border-slate-700 bg-slate-900/60 px-2 py-1.5 text-[12px]"
                    >
                      <div className="truncate">
                        <span className="font-semibold text-slate-100">{m.name}</span>
                        <span className="text-slate-500 mx-2">·</span>
                        <span className="text-slate-400">{m.metric}</span>
                      </div>
                      <div className="shrink-0 text-right">
                        <span className="text-rose-300 font-mono">{m.stored}</span>
                        <span className="text-slate-500 mx-1">→</span>
                        <span className="text-emerald-300 font-mono">{m.expected}</span>
                        <span className="text-slate-500 ml-2 text-[10px]">
                          ({m.rel_diff_pct}%)
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="text-[11px] text-slate-500 mt-2">
                  Fix the raw inputs in Data Uploads → POS Review. The engine
                  recomputes derived ratios on save.
                </div>
              </div>
            )}

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
                <b>One-click fix:</b> Tap <b>"Auto-Fix All"</b> below — it
                normalizes every quarter's scoring constants and merges any
                outstanding alias collisions in one go.
              </div>
              <div>
                <b>Integrity issues:</b> Orphan snapshot refs and blocklist
                violations need separate cleanup — see{" "}
                <code className="text-slate-400">/api/v2/admin/integrity</code>.
              </div>
            </div>

            <label
              className="flex items-start gap-2 rounded-md border border-slate-700 bg-slate-800/30 p-3 text-xs text-slate-300 cursor-pointer"
              data-testid="scoring-trust-auto-heal-toggle"
            >
              <input
                type="checkbox"
                className="mt-0.5 accent-emerald-500"
                checked={autoHealEnabled}
                onChange={(e) => {
                  const v = e.target.checked;
                  setAutoHealEnabled(v);
                  localStorage.setItem(AUTO_HEAL_PREF_KEY, String(v));
                  if (v) {
                    // Re-arm: clear cooldown so the next dashboard load re-runs.
                    localStorage.removeItem(AUTO_HEAL_COOLDOWN_KEY);
                    autoHealRanRef.current = false;
                    toast.success("Self-healing enabled.");
                  } else {
                    toast.message("Self-healing disabled.");
                  }
                }}
              />
              <span>
                <b className="text-slate-200">Self-healing dashboard</b> — when
                enabled (default), drift and alias collisions are auto-fixed
                silently on dashboard load (≤ once/hour). You'll get a toast
                summary. Disable if you'd rather review changes manually.
              </span>
            </label>
          </div>

          <DialogFooter className="flex-col sm:flex-row gap-2 mt-2">
            <button
              type="button"
              className="px-3 py-2 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 text-sm w-full sm:w-auto"
              onClick={refresh}
              disabled={normalizing}
              data-testid="scoring-trust-refresh"
            >
              Refresh
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 text-sm w-full sm:w-auto"
              onClick={() => runNormalize(false)}
              disabled={normalizing}
              data-testid="scoring-trust-dry-run"
            >
              Dry-Run Normalize
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded border border-slate-600 text-slate-200 hover:bg-slate-800 text-sm w-full sm:w-auto"
              onClick={() => runNormalize(true)}
              disabled={normalizing}
              data-testid="scoring-trust-apply-normalize"
            >
              {normalizing ? "Working…" : "Apply Normalize"}
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-sm disabled:opacity-50 flex items-center justify-center gap-1.5 w-full sm:w-auto"
              onClick={autoFix}
              disabled={normalizing}
              data-testid="scoring-trust-auto-fix"
            >
              <Wand2 className="w-3.5 h-3.5" />
              {normalizing ? "Working…" : "Auto-Fix All"}
            </button>
            <button
              type="button"
              className="px-3 py-2 rounded bg-indigo-700 hover:bg-indigo-600 text-white text-sm disabled:opacity-50 flex items-center justify-center gap-1.5 w-full sm:w-auto"
              onClick={runDemoPrep}
              disabled={normalizing}
              data-testid="scoring-trust-demo-prep"
              title="Consolidate v2 alias-named rows + same-name duplicates, fix single-word display names, resync the current snapshot, and rescore everything."
            >
              <Wand2 className="w-3.5 h-3.5" />
              {normalizing ? "Working…" : "Demo Prep"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
