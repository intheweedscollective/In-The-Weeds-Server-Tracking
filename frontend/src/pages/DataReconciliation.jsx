import { useState, useEffect, useCallback } from "react";
import {
  AlertTriangle,
  RefreshCw,
  Clock,
  Check,
  X,
  Pencil,
  ChevronRight,
  Database,
  FileWarning,
  History,
} from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";

const ACTIONS = {
  KEEP:    "keep_stored",
  ACCEPT:  "accept_snapshot",
  MANUAL:  "manual_override",
  DEFER:   "defer",
  REVOKE:  "revoke_alias",
};

const ACTION_LABEL = {
  keep_stored:      "Keep stored value",
  accept_snapshot:  "Accept snapshot value",
  manual_override:  "Manual override",
  defer:            "Defer",
  revoke_alias:     "Revoke alias",
};

const formatValue = (v) => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    // Heuristic: dollars get $ prefix when >= 1000.
    if (Math.abs(v) >= 1000) return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  return String(v);
};

const formatTimestamp = (iso) => {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
};

export default function DataReconciliation() {
  const [queue, setQueue] = useState({ active: [], deferred: [], counts: {} });
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmCard, setConfirmCard] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);
  const [overrideValue, setOverrideValue] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [q, a] = await Promise.all([
        api.get("/v2/admin/reconciliation/queue"),
        api.get("/v2/admin/reconciliation/audit?limit=50"),
      ]);
      setQueue(q.data || { active: [], deferred: [], counts: {} });
      setAudit(a.data?.entries || []);
    } catch (e) {
      toast.error(`Failed to load queue: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const openConfirm = (card, action) => {
    setConfirmCard(card);
    setConfirmAction(action);
    setOverrideValue("");
    setReason("");
  };

  const closeConfirm = () => {
    if (submitting) return;
    setConfirmCard(null);
    setConfirmAction(null);
    setOverrideValue("");
    setReason("");
  };

  const submitResolution = async () => {
    if (!confirmCard || !confirmAction) return;
    setSubmitting(true);
    try {
      const body = {
        conflict_id: confirmCard.conflict_id,
        action: confirmAction,
        reason: reason || null,
      };
      if (confirmAction === ACTIONS.MANUAL) {
        if (overrideValue === "" || isNaN(parseFloat(overrideValue))) {
          toast.error("Manual override requires a numeric value.");
          setSubmitting(false);
          return;
        }
        body.value_override = parseFloat(overrideValue);
      }
      const res = await api.post("/v2/admin/reconciliation/resolve", body);
      toast.success(
        `${ACTION_LABEL[confirmAction]} applied for ${confirmCard.employee_name}`,
        { description: res.data?.value != null ? `New value: ${formatValue(res.data.value)}` : undefined },
      );
      closeConfirm();
      await fetchAll();
    } catch (e) {
      toast.error(`Resolution failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const renderCard = (card, opts = {}) => {
    const isAlias = card.kind === "alias_collision";
    return (
      <div
        key={card.conflict_id}
        className="rounded-lg border border-slate-700 bg-slate-900/60 p-4 space-y-3"
        data-testid={`reconcile-card-${card.conflict_id}`}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-base font-serif font-bold text-white">
                {card.employee_name || "Unknown"}
              </span>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-700/70 text-slate-300 font-mono">
                {card.field}
              </span>
              <span
                className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${
                  card.severity_pct >= 50
                    ? "bg-rose-900/60 text-rose-200 border border-rose-700"
                    : card.severity_pct >= 10
                    ? "bg-amber-900/50 text-amber-200 border border-amber-700"
                    : "bg-slate-700/70 text-slate-300 border border-slate-600"
                }`}
              >
                {card.severity_pct?.toFixed?.(2) ?? card.severity_pct}% drift
              </span>
              {isAlias && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-900/50 text-purple-200 border border-purple-700">
                  alias collision
                </span>
              )}
              {opts.deferred && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-blue-900/50 text-blue-200 border border-blue-700">
                  deferred
                </span>
              )}
            </div>
            <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-3 text-sm">
              <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
                <div className="text-[11px] text-slate-400 uppercase tracking-wide">Stored (canonical)</div>
                <div className="text-rose-300 font-mono break-all" data-testid={`stored-${card.conflict_id}`}>
                  {formatValue(card.stored_value)}
                </div>
              </div>
              {!isAlias && (
                <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wide">Expected (from snapshot)</div>
                  <div className="text-emerald-300 font-mono break-all" data-testid={`snapshot-${card.conflict_id}`}>
                    {formatValue(card.snapshot_value)}
                  </div>
                </div>
              )}
              <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
                <div className="text-[11px] text-slate-400 uppercase tracking-wide">Source</div>
                <div className="text-slate-300 text-xs">
                  {isAlias ? (
                    <>
                      <div>Owned by: <b>{card.source?.owner_name || "—"}</b></div>
                      <div className="text-slate-500 mt-1">{card.source?.reason}</div>
                    </>
                  ) : (
                    <>
                      <div>{card.source?.snapshot_name || "—"}</div>
                      <div className="text-slate-500">{card.source?.quarter} {card.source?.year}</div>
                      {card.raw_inputs && (
                        <div className="text-slate-500 mt-1 font-mono text-[10.5px]">
                          {Object.entries(card.raw_inputs).map(([k, v]) => (
                            <div key={k}>{k}: {formatValue(v)}</div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
            {opts.deferred && card.defer_reason && (
              <div className="mt-2 text-xs text-blue-300 italic">
                Deferred: "{card.defer_reason}" · {formatTimestamp(card.deferred_at)}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
          <Button
            variant="outline"
            size="sm"
            className="border-slate-600 text-slate-200 hover:bg-slate-800"
            onClick={() => openConfirm(card, ACTIONS.KEEP)}
            data-testid={`btn-keep-${card.conflict_id}`}
          >
            <Check className="w-3.5 h-3.5 mr-1.5" />
            Keep Stored
          </Button>
          {!isAlias && (
            <Button
              variant="outline"
              size="sm"
              className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
              onClick={() => openConfirm(card, ACTIONS.ACCEPT)}
              data-testid={`btn-accept-${card.conflict_id}`}
            >
              <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
              Accept Snapshot
            </Button>
          )}
          {!isAlias && (
            <Button
              variant="outline"
              size="sm"
              className="border-blue-700 text-blue-200 hover:bg-blue-950/40"
              onClick={() => openConfirm(card, ACTIONS.MANUAL)}
              data-testid={`btn-manual-${card.conflict_id}`}
            >
              <Pencil className="w-3.5 h-3.5 mr-1.5" />
              Manual Override
            </Button>
          )}
          {isAlias && (
            <Button
              variant="outline"
              size="sm"
              className="border-rose-700 text-rose-200 hover:bg-rose-950/40"
              onClick={() => openConfirm(card, ACTIONS.REVOKE)}
              data-testid={`btn-revoke-${card.conflict_id}`}
            >
              <X className="w-3.5 h-3.5 mr-1.5" />
              Revoke Alias
            </Button>
          )}
          {!opts.deferred && (
            <Button
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-400 hover:bg-slate-800"
              onClick={() => openConfirm(card, ACTIONS.DEFER)}
              data-testid={`btn-defer-${card.conflict_id}`}
            >
              <Clock className="w-3.5 h-3.5 mr-1.5" />
              Defer
            </Button>
          )}
        </div>
      </div>
    );
  };

  // ----- Confirmation dialog content -----
  const renderConfirmBody = () => {
    if (!confirmCard || !confirmAction) return null;
    const isAlias = confirmCard.kind === "alias_collision";

    const beforeAfter = () => {
      switch (confirmAction) {
        case ACTIONS.KEEP:
          return [confirmCard.stored_value, confirmCard.stored_value];
        case ACTIONS.ACCEPT:
          return [confirmCard.stored_value, confirmCard.snapshot_value];
        case ACTIONS.MANUAL:
          return [
            confirmCard.stored_value,
            overrideValue === "" ? "(enter below)" : overrideValue,
          ];
        case ACTIONS.DEFER:
          return [confirmCard.stored_value, "(no change — moved to deferred)"];
        case ACTIONS.REVOKE:
          return [confirmCard.stored_value, "(alias removed)"];
        default:
          return [null, null];
      }
    };

    const [before, after] = beforeAfter();
    return (
      <div className="space-y-4">
        <div className="rounded-md border border-amber-800/60 bg-amber-950/30 p-3 text-sm text-amber-200">
          You are about to <b>{ACTION_LABEL[confirmAction]}</b> for{" "}
          <b>{confirmCard.employee_name}</b> · field <code className="font-mono">{confirmCard.field}</code>.
          This action will be logged with your email and timestamp.
        </div>

        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
            <div className="text-[11px] text-slate-400 uppercase">Before</div>
            <div className="text-rose-300 font-mono break-all">{formatValue(before)}</div>
          </div>
          <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
            <div className="text-[11px] text-slate-400 uppercase">After</div>
            <div className="text-emerald-300 font-mono break-all">{typeof after === "number" ? formatValue(after) : after}</div>
          </div>
        </div>

        {confirmAction === ACTIONS.MANUAL && (
          <label className="block space-y-1">
            <span className="text-xs text-slate-400">
              New value for <code className="font-mono">{confirmCard.field}</code>
            </span>
            <input
              type="number"
              step="any"
              autoFocus
              value={overrideValue}
              onChange={(e) => setOverrideValue(e.target.value)}
              placeholder="Type the correct value"
              className="w-full px-3 py-2 rounded border border-slate-600 bg-slate-800 text-slate-100 font-mono"
              data-testid="override-input"
            />
            <span className="text-[11px] text-slate-500 block">
              This value is written directly to <code>employees.current_metrics.{confirmCard.field}</code>
              {" "}and mirrored to <code>employees_v2</code>. Existing derived ratios are not auto-recalculated;
              fix related raw inputs in Data Uploads if needed.
            </span>
          </label>
        )}

        {!isAlias && confirmCard.raw_inputs && (
          <div className="rounded-md border border-slate-700 bg-slate-800/30 p-2 text-[11px] text-slate-400">
            Snapshot says: {Object.entries(confirmCard.raw_inputs)
              .map(([k, v]) => `${k}=${formatValue(v)}`).join(" · ")}
          </div>
        )}

        <label className="block space-y-1">
          <span className="text-xs text-slate-400">
            Note (optional — saved to audit log)
          </span>
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Confirmed with manager — POS export had a digit-concatenation typo"
            className="w-full px-3 py-2 rounded border border-slate-600 bg-slate-800 text-slate-100"
            data-testid="reason-input"
          />
        </label>
      </div>
    );
  };

  return (
    <div className="space-y-6 p-6" data-testid="data-reconciliation-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground flex items-center gap-2">
            <Database className="w-7 h-7 text-amber-400" />
            Data Reconciliation
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Manual adjudication queue for canonical-vs-snapshot data drift.
            Every resolution is explicit, logged, and reversible by editing
            the raw input in Data Uploads. Nothing auto-resolves.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-xs text-slate-400 rounded border border-slate-700 bg-slate-800/40 px-3 py-2">
            <div><b className="text-rose-300">{queue.counts?.active ?? 0}</b> active</div>
            <div><b className="text-blue-300">{queue.counts?.deferred ?? 0}</b> deferred</div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={fetchAll}
            disabled={loading}
            className="border-slate-600"
            data-testid="reconcile-refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Active queue */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <FileWarning className="w-5 h-5 text-amber-400" />
          <h2 className="text-xl font-serif font-bold text-foreground">Active Queue</h2>
          <span className="text-xs text-slate-500">
            Sorted by drift severity (worst first)
          </span>
        </div>
        {loading ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : queue.active.length === 0 ? (
          <div className="rounded-md border border-emerald-700 bg-emerald-950/30 p-4 text-sm text-emerald-200">
            <Check className="w-4 h-4 inline-block mr-2" />
            No active conflicts — every employee's stored ratios match their raw inputs and no alias collisions detected.
          </div>
        ) : (
          <div className="space-y-3">{queue.active.map((c) => renderCard(c))}</div>
        )}
      </section>

      {/* Deferred queue */}
      {queue.deferred.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-5 h-5 text-blue-400" />
            <h2 className="text-xl font-serif font-bold text-foreground">Deferred (Review Later)</h2>
            <span className="text-xs text-slate-500">Persisted across sessions until you resolve them</span>
          </div>
          <div className="space-y-3">{queue.deferred.map((c) => renderCard(c, { deferred: true }))}</div>
        </section>
      )}

      {/* Audit log */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <History className="w-5 h-5 text-slate-400" />
          <h2 className="text-xl font-serif font-bold text-foreground">Audit Log</h2>
          <span className="text-xs text-slate-500">Last 50 resolutions · append-only</span>
        </div>
        {audit.length === 0 ? (
          <div className="text-slate-500 text-sm">No resolutions yet.</div>
        ) : (
          <div className="rounded-md border border-slate-700 overflow-hidden">
            <table className="w-full text-xs" data-testid="audit-log">
              <thead className="bg-slate-800/60 text-slate-400">
                <tr>
                  <th className="text-left px-3 py-2">Timestamp</th>
                  <th className="text-left px-3 py-2">Actor</th>
                  <th className="text-left px-3 py-2">Employee</th>
                  <th className="text-left px-3 py-2">Field</th>
                  <th className="text-left px-3 py-2">Action</th>
                  <th className="text-left px-3 py-2">Before → After</th>
                  <th className="text-left px-3 py-2">Note</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e, idx) => (
                  <tr
                    key={`${e.conflict_id}-${e.logged_at}-${idx}`}
                    className="border-t border-slate-800 hover:bg-slate-800/30"
                    data-testid={`audit-row-${idx}`}
                  >
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{formatTimestamp(e.logged_at)}</td>
                    <td className="px-3 py-2 text-slate-300">{e.actor}</td>
                    <td className="px-3 py-2 text-slate-200 font-semibold">{e.employee_name}</td>
                    <td className="px-3 py-2 text-slate-300 font-mono">{e.field}</td>
                    <td className="px-3 py-2 text-slate-300">{ACTION_LABEL[e.action] || e.action}</td>
                    <td className="px-3 py-2 font-mono whitespace-nowrap">
                      <span className="text-rose-300">{formatValue(e.before)}</span>
                      <span className="text-slate-600 mx-1">→</span>
                      <span className="text-emerald-300">{formatValue(e.after)}</span>
                    </td>
                    <td className="px-3 py-2 text-slate-400">{e.reason || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Confirmation dialog */}
      <Dialog open={!!confirmCard} onOpenChange={(o) => !o && closeConfirm()}>
        <DialogContent
          className="max-w-xl bg-slate-900 border-slate-700 text-slate-100"
          data-testid="reconcile-confirm-modal"
        >
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              Confirm resolution
            </DialogTitle>
            <DialogDescription className="text-slate-400">
              This action will write to the canonical record and the audit log.
            </DialogDescription>
          </DialogHeader>
          {renderConfirmBody()}
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              className="border-slate-600 text-slate-200"
              onClick={closeConfirm}
              disabled={submitting}
              data-testid="reconcile-cancel"
            >
              Cancel
            </Button>
            <Button
              className="bg-amber-700 hover:bg-amber-600 text-white"
              onClick={submitResolution}
              disabled={submitting}
              data-testid="reconcile-confirm"
            >
              {submitting ? "Working…" : `Confirm ${confirmAction ? ACTION_LABEL[confirmAction] : ""}`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
