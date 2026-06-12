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
  KEEP:        "keep_stored",
  ACCEPT:      "accept_snapshot",
  MANUAL:      "manual_override",
  DEFER:       "defer",
  REVOKE:      "revoke_alias",
  MERGE:       "merge_into",
  DELETE:      "delete_legacy",
  PROMOTE:     "promote_canonical",
  RELINK:      "relink_orphan",
  REMOVE:      "remove_orphan",
  SYNC_V2:     "sync_canonical_from_v2",
  KEEP_DRIFT:  "keep_canonical_drift",
  REVOKE_FROM: "revoke_alias_from",
  DEDUPE_ROWS: "dedupe_snapshot_rows",
  MERGE_CANON: "merge_canonical_into",
};

const ACTION_LABEL = {
  keep_stored:             "Keep stored value",
  accept_snapshot:         "Accept snapshot value",
  manual_override:         "Manual override",
  defer:                   "Defer",
  revoke_alias:            "Revoke alias",
  merge_into:              "Merge into canonical",
  delete_legacy:           "Delete legacy row",
  promote_canonical:       "Promote to new canonical",
  relink_orphan:           "Relink to canonical",
  remove_orphan:           "Remove orphan row",
  sync_canonical_from_v2:  "Sync canonical from v2",
  keep_canonical_drift:    "Keep canonical (silence)",
  revoke_alias_from:       "Revoke alias from…",
  dedupe_snapshot_rows:    "Dedupe snapshot rows",
  merge_canonical_into:    "Merge canonicals into…",
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
  const [queue, setQueue] = useState({ active: [], deferred: [], resolved: [], counts: {} });
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [confirmCard, setConfirmCard] = useState(null);
  const [confirmAction, setConfirmAction] = useState(null);
  const [overrideValue, setOverrideValue] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [canonicalList, setCanonicalList] = useState([]);
  const [targetCanonicalId, setTargetCanonicalId] = useState("");
  const [deletedEmployees, setDeletedEmployees] = useState([]);
  const [restoringId, setRestoringId] = useState(null);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [q, a, c, d] = await Promise.all([
        api.get("/v2/admin/reconciliation/queue"),
        api.get("/v2/admin/reconciliation/audit?limit=50"),
        // Active canonical employees for the merge_into dropdown.
        api.get("/v2/employees?status=active").catch(() => ({ data: [] })),
        api.get("/v2/admin/deleted-employees").catch(() => ({ data: { deleted_employees: [] } })),
      ]);
      setQueue(q.data || { active: [], deferred: [], resolved: [], counts: {} });
      setAudit(a.data?.entries || []);
      const list = Array.isArray(c.data) ? c.data : (c.data?.employees || c.data || []);
      setCanonicalList(
        list
          .filter((e) => e?.status === "active" && e?.id && e?.name)
          .map((e) => ({ id: e.id, name: e.name }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      );
      setDeletedEmployees(d.data?.deleted_employees || []);
    } catch (e) {
      toast.error(`Failed to load queue: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleRestoreDeleted = useCallback(async (entry) => {
    const name = entry.canonical_name || "this employee";
    if (!window.confirm(
      `Restore ${name}?\n\nThis will set the canonical back to ACTIVE and reactivate every soft-deleted v2 row (${entry.inactive_v2_count} quarter${entry.inactive_v2_count === 1 ? "" : "s"}). The action is logged in the audit ledger.`,
    )) {
      return;
    }
    setRestoringId(entry.canonical_id);
    try {
      const reason = window.prompt(
        `(optional) Reason for restoring ${name} — leave blank to skip:`,
        "",
      );
      const res = await api.post(
        `/v2/admin/restore-deleted-employee/${entry.canonical_id}` +
          (reason ? `?reason=${encodeURIComponent(reason)}` : ""),
      );
      const body = res.data || {};
      toast.success(
        `Restored ${body.canonical_name || name}` +
          (body.v2_rows_reactivated
            ? ` — reactivated ${body.v2_rows_reactivated} quarter row${
                body.v2_rows_reactivated === 1 ? "" : "s"
              }`
            : ""),
      );
      await fetchAll();
    } catch (e) {
      toast.error(
        `Restore failed: ${e?.response?.data?.detail || e.message}`,
      );
    } finally {
      setRestoringId(null);
    }
  }, [fetchAll]);

  const openConfirm = (card, action) => {
    setConfirmCard(card);
    setConfirmAction(action);
    setOverrideValue("");
    setReason("");
    // Pre-fill merge target with the suggested canonical when applicable.
    if (action === ACTIONS.MERGE) {
      setTargetCanonicalId(card?.source?.suggested_canonical_id || "");
    } else if (action === ACTIONS.REVOKE_FROM) {
      // Default to first claimant so the operator only has to override
      // when the wrong owner is preselected. They MUST review before
      // confirming — there is no auto-pick logic.
      const claimants = card?.raw_inputs?.claimants || [];
      setTargetCanonicalId(claimants[0]?.canonical_id || "");
    } else if (action === ACTIONS.MERGE_CANON) {
      // Same pattern as REVOKE_FROM — pre-populate to first claimant
      // (the "keeper") but force the operator to confirm.
      const claimants = card?.raw_inputs?.claimants || [];
      setTargetCanonicalId(claimants[0]?.canonical_id || "");
    } else {
      setTargetCanonicalId("");
    }
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
      if (confirmAction === ACTIONS.MERGE) {
        if (!targetCanonicalId) {
          toast.error("Pick a canonical employee to merge into.");
          setSubmitting(false);
          return;
        }
        body.target_canonical_id = targetCanonicalId;
      }
      if (confirmAction === ACTIONS.REVOKE_FROM) {
        if (!targetCanonicalId) {
          toast.error("Pick the canonical to strip the alias from.");
          setSubmitting(false);
          return;
        }
        body.target_canonical_id = targetCanonicalId;
      }
      if (confirmAction === ACTIONS.MERGE_CANON) {
        if (!targetCanonicalId) {
          toast.error("Pick a KEEPER canonical to merge the others into.");
          setSubmitting(false);
          return;
        }
        body.target_canonical_id = targetCanonicalId;
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

  const unresolve = async (conflict_id, name) => {
    try {
      await api.post(`/v2/admin/reconciliation/unresolve?conflict_id=${encodeURIComponent(conflict_id)}`);
      toast.success(`Re-opened ${name}`, {
        description: "Card moved back to the active queue.",
      });
      await fetchAll();
    } catch (e) {
      toast.error(`Failed to un-resolve: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const renderCard = (card, opts = {}) => {
    const isAlias = card.kind === "alias_collision";
    const isLegacy = card.kind === "legacy_duplicate";
    const isOrphan = card.kind === "orphan_snapshot_ref";
    const isCanonDrift = card.kind === "canonical_metrics_drift";
    const isAliasCross = card.kind === "alias_cross_assignment";
    const isDupRows = card.kind === "duplicate_snapshot_rows";
    const isNameDup = card.kind === "canonical_name_collision";
    const drifted = card?.raw_inputs?.drifted_fields || [];
    const claimants = card?.raw_inputs?.claimants || [];
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
              {!isLegacy && !isOrphan && !isCanonDrift && !isAliasCross && !isDupRows && !isNameDup && (
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
              )}
              {isDupRows && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-900/60 text-rose-200 border border-rose-700 font-semibold">
                  {card.raw_inputs?.duplicate_count || 0} duplicate rows
                </span>
              )}
              {isNameDup && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-900/60 text-rose-200 border border-rose-700 font-semibold">
                  {card.raw_inputs?.match_type === "nickname_prefix"
                    ? "nickname match"
                    : `${claimants.length} canonicals share name`}
                </span>
              )}
              {isCanonDrift && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-900/60 text-rose-200 border border-rose-700 font-semibold">
                  canonical drift · {drifted.length} field{drifted.length !== 1 ? "s" : ""}
                </span>
              )}
              {isAliasCross && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-rose-900/60 text-rose-200 border border-rose-700 font-semibold">
                  alias claimed by {claimants.length} canonicals
                </span>
              )}
              {isAlias && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-purple-900/50 text-purple-200 border border-purple-700">
                  alias collision
                </span>
              )}
              {isLegacy && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-orange-900/50 text-orange-200 border border-orange-700">
                  legacy duplicate
                </span>
              )}
              {isOrphan && (
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-fuchsia-900/50 text-fuchsia-200 border border-fuchsia-700">
                  orphan snapshot ref
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
                <div className="text-[11px] text-slate-400 uppercase tracking-wide">
                  {isLegacy ? "V2 record name" : isOrphan ? "Frozen display name" : "Stored (canonical)"}
                </div>
                <div className="text-rose-300 font-mono break-all" data-testid={`stored-${card.conflict_id}`}>
                  {formatValue(card.stored_value)}
                </div>
              </div>
              {!isAlias && !isLegacy && !isOrphan && (
                <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wide">Expected (from snapshot)</div>
                  <div className="text-emerald-300 font-mono break-all" data-testid={`snapshot-${card.conflict_id}`}>
                    {formatValue(card.snapshot_value)}
                  </div>
                </div>
              )}
              {(isLegacy || isOrphan) && (
                <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
                  <div className="text-[11px] text-slate-400 uppercase tracking-wide">Suggested canonical</div>
                  <div className="text-emerald-300 font-mono break-all" data-testid={`suggest-${card.conflict_id}`}>
                    {card.source?.suggested_canonical_name || <span className="text-slate-500">no good match</span>}
                  </div>
                  {card.source?.suggested_canonical_name && (
                    <div className="text-[10.5px] text-slate-500 mt-1">
                      You can change the target in the confirm dialog.
                    </div>
                  )}
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
                  ) : isLegacy ? (
                    <>
                      <div className="text-slate-400">{card.source?.reason}</div>
                      {card.raw_inputs && (
                        <div className="text-slate-500 mt-1 font-mono text-[10.5px]">
                          q: {card.raw_inputs.quarter}/{card.raw_inputs.year}
                          {' · guests:'} {formatValue(card.raw_inputs.guests)}
                          {' · ppa:'} {formatValue(card.raw_inputs.ppa)}
                          {' · lsc:'} {formatValue(card.raw_inputs.lsc_count)}
                        </div>
                      )}
                    </>
                  ) : isOrphan ? (
                    <>
                      <div>
                        <b>{card.raw_inputs?.snapshot_name || "—"}</b>
                        <span className="text-slate-500"> · {card.raw_inputs?.snapshot_quarter} {card.raw_inputs?.snapshot_year}</span>
                      </div>
                      <div className="text-slate-500 mt-1 text-[11px]">{card.source?.reason}</div>
                      <div className="text-slate-500 mt-1 font-mono text-[10.5px]">
                        dead id: {String(card.raw_inputs?.missing_employee_id || "").slice(0, 8)}…
                        {' · row score:'} {formatValue(card.raw_inputs?.row_total_score)}
                        {' · ppa:'} {formatValue(card.raw_inputs?.row_ppa)}
                      </div>
                      {!card.raw_inputs?.row_total_score && (
                        <div className="text-[10.5px] text-emerald-400/80 mt-1">
                          ✓ Row has no score data — safe to remove without losing historical numbers.
                        </div>
                      )}
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
            {isCanonDrift && (
              <div className="mt-2 rounded border border-rose-800/60 bg-rose-950/20 p-3 text-sm">
                <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-2">
                  Drifted scoring fields · canonical vs v2 ({card.source?.quarter}/{card.source?.year})
                </div>
                <table className="w-full text-xs" data-testid={`drift-table-${card.conflict_id}`}>
                  <thead className="text-slate-500">
                    <tr>
                      <th className="text-left py-1">Field</th>
                      <th className="text-right py-1">Canonical</th>
                      <th className="text-right py-1">v2 (truth)</th>
                      <th className="text-right py-1">Δ</th>
                      <th className="text-right py-1">%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {drifted.map((d) => (
                      <tr key={d.field} className="border-t border-slate-800">
                        <td className="py-1 font-mono text-slate-300">{d.field}</td>
                        <td className="py-1 text-right font-mono text-rose-300">{formatValue(d.canonical)}</td>
                        <td className="py-1 text-right font-mono text-emerald-300">{formatValue(d.v2)}</td>
                        <td className="py-1 text-right font-mono text-amber-300">{formatValue(d.abs_diff)}</td>
                        <td className="py-1 text-right font-mono text-amber-300">{d.rel_pct?.toFixed?.(1) ?? d.rel_pct}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <div className="text-[10.5px] text-slate-500 mt-2">
                  Sync action overwrites ONLY these scoring fields on
                  <code className="mx-1 font-mono">employees.current_metrics</code>.
                  CV / NPS / RT are untouched.
                </div>
              </div>
            )}
            {isAliasCross && (
              <div className="mt-2 rounded border border-rose-800/60 bg-rose-950/20 p-3 text-sm" data-testid={`claimants-${card.conflict_id}`}>
                <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-2">
                  Canonicals claiming alias <code className="font-mono text-rose-300">{card.stored_value}</code>
                </div>
                <ul className="space-y-1">
                  {claimants.map((c) => (
                    <li
                      key={c.canonical_id}
                      className="flex items-center justify-between gap-2 text-xs"
                      data-testid={`claimant-${card.conflict_id}-${c.canonical_id}`}
                    >
                      <span className="text-slate-200 font-semibold">{c.canonical_name}</span>
                      <span className="text-slate-500 font-mono text-[10.5px]">{String(c.canonical_id).slice(0, 8)}…</span>
                    </li>
                  ))}
                </ul>
                <div className="text-[10.5px] text-slate-500 mt-2">
                  Pick the canonical to strip the alias from in the confirm dialog. All others keep the alias.
                </div>
              </div>
            )}
            {isDupRows && (
              <div className="mt-2 rounded border border-rose-800/60 bg-rose-950/20 p-3 text-sm" data-testid={`dup-rows-${card.conflict_id}`}>
                <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-2">
                  Duplicate rows in snapshot
                  <code className="ml-2 font-mono text-rose-300">{card.raw_inputs?.snapshot_name}</code>
                </div>
                <div className="text-xs text-slate-200">
                  <code className="font-mono text-rose-300">{card.employee_name}</code> appears{" "}
                  <span className="text-rose-300 font-semibold">
                    {card.raw_inputs?.duplicate_count}
                  </span>{" "}
                  times at row indices{" "}
                  <code className="font-mono">{(card.raw_inputs?.duplicate_indices || []).join(", ")}</code>
                </div>
                <div className="text-[10.5px] text-slate-500 mt-2">
                  Dedupe keeps the first occurrence and removes the rest. We do NOT sum
                  guests/sales — duplicate rows almost always carry identical numbers.
                </div>
              </div>
            )}
            {isNameDup && (
              <div className="mt-2 rounded border border-rose-800/60 bg-rose-950/20 p-3 text-sm" data-testid={`name-dup-${card.conflict_id}`}>
                <div className="text-[11px] text-slate-400 uppercase tracking-wide mb-2">
                  Canonicals to merge
                  {card.raw_inputs?.match_type === "nickname_prefix" && (
                    <span className="ml-2 text-amber-400">· nickname/prefix match — verify these are the same person</span>
                  )}
                </div>
                <ul className="space-y-1">
                  {claimants.map((c) => (
                    <li
                      key={c.canonical_id}
                      className="flex items-center justify-between gap-2 text-xs"
                      data-testid={`name-dup-claimant-${card.conflict_id}-${c.canonical_id}`}
                    >
                      <span className="text-slate-200 font-semibold">{c.canonical_name}</span>
                      <span className="text-slate-500 text-[10.5px]">
                        {(c.aliases && c.aliases.length) ? `aliases: ${c.aliases.join(", ")}` : "no aliases"}
                      </span>
                      <span className="text-slate-500 font-mono text-[10.5px]">{String(c.canonical_id).slice(0, 8)}…</span>
                    </li>
                  ))}
                </ul>
                <div className="text-[10.5px] text-slate-500 mt-2">
                  Pick a KEEPER in the confirm dialog. Every other claimant becomes <code className="font-mono">status=merged</code>,
                  its aliases &amp; legacy ids fold into the keeper, and the keeper's display name stays untouched.
                </div>
              </div>
            )}
            {opts.deferred && card.defer_reason && (
              <div className="mt-2 text-xs text-blue-300 italic">
                Deferred: "{card.defer_reason}" · {formatTimestamp(card.deferred_at)}
              </div>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2 border-t border-slate-800">
          {!isOrphan && !isCanonDrift && !isAliasCross && !isDupRows && !isNameDup && (
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
          )}
          {!isAlias && !isLegacy && !isOrphan && !isCanonDrift && !isAliasCross && !isDupRows && !isNameDup && (
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
          {!isAlias && !isLegacy && !isOrphan && !isCanonDrift && !isAliasCross && !isDupRows && !isNameDup && (
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
          {isLegacy && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
                onClick={() => openConfirm(card, ACTIONS.MERGE)}
                data-testid={`btn-merge-${card.conflict_id}`}
              >
                <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
                Merge into…
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-blue-700 text-blue-200 hover:bg-blue-950/40"
                onClick={() => openConfirm(card, ACTIONS.PROMOTE)}
                data-testid={`btn-promote-${card.conflict_id}`}
              >
                <Pencil className="w-3.5 h-3.5 mr-1.5" />
                Promote to canonical
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-rose-700 text-rose-200 hover:bg-rose-950/40"
                onClick={() => openConfirm(card, ACTIONS.DELETE)}
                data-testid={`btn-delete-${card.conflict_id}`}
              >
                <X className="w-3.5 h-3.5 mr-1.5" />
                Delete legacy
              </Button>
            </>
          )}
          {isOrphan && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
                onClick={() => openConfirm(card, ACTIONS.RELINK)}
                data-testid={`btn-relink-${card.conflict_id}`}
                disabled={!card.source?.suggested_canonical_id}
                title={
                  card.source?.suggested_canonical_id
                    ? "Rewrite the snapshot row to point at the suggested canonical employee"
                    : "No canonical match found — use Remove orphan instead"
                }
              >
                <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
                Relink to canonical
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-rose-700 text-rose-200 hover:bg-rose-950/40"
                onClick={() => openConfirm(card, ACTIONS.REMOVE)}
                data-testid={`btn-remove-${card.conflict_id}`}
              >
                <X className="w-3.5 h-3.5 mr-1.5" />
                Remove orphan row
              </Button>
            </>
          )}
          {isCanonDrift && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
                onClick={() => openConfirm(card, ACTIONS.SYNC_V2)}
                data-testid={`btn-sync-v2-${card.conflict_id}`}
              >
                <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
                Sync canonical from v2
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                onClick={() => openConfirm(card, ACTIONS.KEEP_DRIFT)}
                data-testid={`btn-keep-drift-${card.conflict_id}`}
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Keep canonical (silence)
              </Button>
            </>
          )}
          {isAliasCross && (
            <Button
              variant="outline"
              size="sm"
              className="border-rose-700 text-rose-200 hover:bg-rose-950/40"
              onClick={() => openConfirm(card, ACTIONS.REVOKE_FROM)}
              data-testid={`btn-revoke-from-${card.conflict_id}`}
            >
              <X className="w-3.5 h-3.5 mr-1.5" />
              Revoke alias from…
            </Button>
          )}
          {isDupRows && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
                onClick={() => openConfirm(card, ACTIONS.DEDUPE_ROWS)}
                data-testid={`btn-dedupe-${card.conflict_id}`}
              >
                <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
                Dedupe rows
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                onClick={() => openConfirm(card, ACTIONS.KEEP)}
                data-testid={`btn-dup-keep-${card.conflict_id}`}
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Keep duplicates (silence)
              </Button>
            </>
          )}
          {isNameDup && (
            <>
              <Button
                variant="outline"
                size="sm"
                className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40"
                onClick={() => openConfirm(card, ACTIONS.MERGE_CANON)}
                data-testid={`btn-merge-canon-${card.conflict_id}`}
              >
                <ChevronRight className="w-3.5 h-3.5 mr-1.5" />
                Merge canonicals…
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-600 text-slate-300 hover:bg-slate-800"
                onClick={() => openConfirm(card, ACTIONS.KEEP)}
                data-testid={`btn-name-keep-${card.conflict_id}`}
              >
                <Check className="w-3.5 h-3.5 mr-1.5" />
                Keep separate (silence)
              </Button>
            </>
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
    const isCanonDrift = confirmCard.kind === "canonical_metrics_drift";
    const isAliasCross = confirmCard.kind === "alias_cross_assignment";
    const isDupRows = confirmCard.kind === "duplicate_snapshot_rows";
    const isNameDup = confirmCard.kind === "canonical_name_collision";

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
        case ACTIONS.SYNC_V2:
          return ["(canonical drift)", "(synced from v2 — see diff below)"];
        case ACTIONS.KEEP_DRIFT:
          return ["(canonical drift)", "(silenced until canonical changes)"];
        case ACTIONS.REVOKE_FROM: {
          const claimants = confirmCard.raw_inputs?.claimants || [];
          const t = claimants.find((c) => c.canonical_id === targetCanonicalId);
          return [
            `${confirmCard.stored_value} on ${t?.canonical_name || "—"}`,
            "(alias removed from this canonical)",
          ];
        }
        case ACTIONS.DEDUPE_ROWS:
          return [
            `${confirmCard.raw_inputs?.duplicate_count} copies`,
            "1 copy (first occurrence kept)",
          ];
        case ACTIONS.MERGE_CANON: {
          const claimants = confirmCard.raw_inputs?.claimants || [];
          const keeper = claimants.find((c) => c.canonical_id === targetCanonicalId);
          const losers = claimants.filter((c) => c.canonical_id !== targetCanonicalId);
          return [
            `${claimants.length} separate canonicals`,
            `Keep ${keeper?.canonical_name || "—"} · merge: ${losers.map((l) => l.canonical_name).join(", ") || "—"}`,
          ];
        }
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

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
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

        {confirmAction === ACTIONS.MERGE && (
          <label className="block space-y-1" data-testid="merge-target-selector">
            <span className="text-xs text-slate-400">
              Pick the canonical employee that will absorb this v2 record
            </span>
            <select
              autoFocus
              value={targetCanonicalId}
              onChange={(e) => setTargetCanonicalId(e.target.value)}
              className="w-full px-3 py-2 rounded border border-slate-600 bg-slate-800 text-slate-100"
              data-testid="merge-target-select"
            >
              <option value="">— Pick canonical —</option>
              {canonicalList.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slate-500 block">
              The v2 record's id will be added to{" "}
              <code className="font-mono">{`{canonical}.legacy_ids[]`}</code>{" "}
              and the misspelled name (if different) will be added to{" "}
              <code className="font-mono">aliases[]</code> so future POS uploads
              under this spelling route to the canonical automatically.
            </span>
          </label>
        )}

        {confirmAction === ACTIONS.REVOKE_FROM && (
          <label className="block space-y-1" data-testid="revoke-from-selector">
            <span className="text-xs text-slate-400">
              Pick the canonical to strip <code className="font-mono">{confirmCard.stored_value}</code> from
            </span>
            <select
              autoFocus
              value={targetCanonicalId}
              onChange={(e) => setTargetCanonicalId(e.target.value)}
              className="w-full px-3 py-2 rounded border border-slate-600 bg-slate-800 text-slate-100"
              data-testid="revoke-from-select"
            >
              <option value="">— Pick claimant to strip —</option>
              {(confirmCard.raw_inputs?.claimants || []).map((c) => (
                <option key={c.canonical_id} value={c.canonical_id}>
                  {c.canonical_name}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slate-500 block">
              The alias will be removed from this canonical's{" "}
              <code className="font-mono">aliases[]</code> only. All other
              claimants keep the alias. Resolve again to strip more if
              needed.
            </span>
          </label>
        )}

        {confirmAction === ACTIONS.SYNC_V2 && (
          <div className="rounded-md border border-emerald-800/60 bg-emerald-950/20 p-3 text-xs" data-testid="sync-preview">
            <div className="text-emerald-300 font-semibold mb-1">Fields about to be overwritten</div>
            <table className="w-full">
              <thead className="text-slate-500">
                <tr>
                  <th className="text-left py-1">Field</th>
                  <th className="text-right py-1">Canonical → v2</th>
                </tr>
              </thead>
              <tbody>
                {(confirmCard.raw_inputs?.drifted_fields || []).map((d) => (
                  <tr key={d.field} className="border-t border-slate-800">
                    <td className="py-1 font-mono">{d.field}</td>
                    <td className="py-1 text-right font-mono">
                      <span className="text-rose-300">{formatValue(d.canonical)}</span>
                      <span className="text-slate-500 mx-1">→</span>
                      <span className="text-emerald-300">{formatValue(d.v2)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="text-[10.5px] text-slate-500 mt-2">
              CV / NPS / RT and any other keys in <code className="font-mono">current_metrics</code> are NOT touched.
            </div>
          </div>
        )}

        {confirmAction === ACTIONS.MERGE_CANON && (
          <label className="block space-y-1" data-testid="merge-canon-selector">
            <span className="text-xs text-slate-400">
              Pick the KEEPER — the canonical to retain
            </span>
            <select
              autoFocus
              value={targetCanonicalId}
              onChange={(e) => setTargetCanonicalId(e.target.value)}
              className="w-full px-3 py-2 rounded border border-slate-600 bg-slate-800 text-slate-100"
              data-testid="merge-canon-select"
            >
              <option value="">— Pick keeper —</option>
              {(confirmCard.raw_inputs?.claimants || []).map((c) => (
                <option key={c.canonical_id} value={c.canonical_id}>
                  {c.canonical_name}
                  {c.aliases?.length ? ` (aliases: ${c.aliases.join(", ")})` : ""}
                </option>
              ))}
            </select>
            <span className="text-[11px] text-slate-500 block">
              The other claimants will be set to{" "}
              <code className="font-mono">status=merged</code>, their aliases &amp;{" "}
              <code className="font-mono">legacy_ids[]</code> fold into the keeper,
              and old v2 rows under their ids will still resolve via the FK-join.
              The keeper's display name is untouched.
            </span>
          </label>
        )}

        {confirmAction === ACTIONS.DEDUPE_ROWS && (
          <div className="rounded-md border border-emerald-800/60 bg-emerald-950/20 p-3 text-xs" data-testid="dedupe-preview">
            <div className="text-emerald-300 font-semibold mb-1">Snapshot edit preview</div>
            <div className="text-slate-200">
              Snapshot{" "}
              <code className="font-mono text-emerald-300">
                {confirmCard.raw_inputs?.snapshot_name}
              </code>
              's <code className="font-mono">rows[]</code> currently has{" "}
              <span className="text-rose-300 font-semibold">
                {confirmCard.raw_inputs?.duplicate_count}
              </span>{" "}
              entries for <code className="font-mono">{confirmCard.employee_name}</code>.
            </div>
            <div className="text-slate-200 mt-1">
              Keeping row at index{" "}
              <code className="font-mono">
                {(confirmCard.raw_inputs?.duplicate_indices || [])[0]}
              </code>
              ; removing{" "}
              <code className="font-mono">
                {(confirmCard.raw_inputs?.duplicate_indices || []).slice(1).join(", ")}
              </code>
              .
            </div>
            <div className="text-[10.5px] text-slate-500 mt-2">
              Guests / sales are NOT summed — duplicate rows almost always carry
              identical numbers and merging would inflate totals.
            </div>
          </div>
        )}

        {!isAlias && !isCanonDrift && !isAliasCross && !isDupRows && !isNameDup && confirmCard.raw_inputs && (
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
    <div className="space-y-6 p-4 md:p-6" data-testid="data-reconciliation-page">
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
            <div><b className="text-emerald-300">{queue.counts?.resolved ?? 0}</b> resolved</div>
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

      {/* Recently Deleted — restore accidentally removed employees.
          Render the panel header even when empty so the operator can
          confirm the new build is live (otherwise the section just
          vanishes and looks like the deploy didn't ship). */}
      <section data-testid="deleted-employees-panel">
        <div className="flex items-center gap-2 mb-3">
          <History className="w-5 h-5 text-rose-300" />
          <h2 className="text-xl font-serif font-bold text-foreground">
            Recently Deleted
          </h2>
          <span className="text-xs text-slate-500">
            Restore an employee that was removed via the recon portal.
            No data is destroyed — only flipped to inactive.
          </span>
        </div>
        {deletedEmployees.length === 0 ? (
          <div
            className="rounded-md border border-slate-800 bg-slate-900/40 px-4 py-3 text-xs text-slate-500"
            data-testid="deleted-employees-empty"
          >
            No soft-deleted employees right now — anyone removed via the
            portal will appear here with a one-click Restore button.
          </div>
        ) : (
          <div className="rounded-md border border-rose-900/40 bg-rose-950/10 divide-y divide-slate-800">
            {deletedEmployees.map((entry) => {
              const last = entry.last_audit;
              return (
                <div
                  key={entry.canonical_id}
                  className="flex items-center justify-between gap-3 px-4 py-3"
                  data-testid={`deleted-row-${entry.canonical_id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-slate-100 truncate">
                      {entry.canonical_name}
                      {entry.aliases?.length > 0 && (
                        <span className="ml-2 text-[11px] text-slate-500 font-normal">
                          aka {entry.aliases.slice(0, 3).join(", ")}
                          {entry.aliases.length > 3 && " …"}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-0.5">
                      canonical status:{" "}
                      <span className={
                        entry.canonical_status === "terminated"
                          ? "text-rose-300"
                          : entry.canonical_status === "merged"
                          ? "text-amber-300"
                          : "text-slate-300"
                      }>
                        {entry.canonical_status}
                      </span>
                      {entry.inactive_v2_count > 0 && (
                        <>
                          {" · "}
                          <span className="text-rose-300">
                            {entry.inactive_v2_count} inactive v2 row
                            {entry.inactive_v2_count === 1 ? "" : "s"}
                          </span>
                        </>
                      )}
                      {last && (
                        <>
                          {" · last action: "}
                          <span className="text-slate-300">{last.action}</span>
                          {last.actor && ` by ${last.actor}`}
                          {last.logged_at && ` (${formatTimestamp(last.logged_at)})`}
                        </>
                      )}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleRestoreDeleted(entry)}
                    disabled={restoringId === entry.canonical_id}
                    className="border-emerald-700 text-emerald-200 hover:bg-emerald-950/40 shrink-0"
                    data-testid={`btn-restore-${entry.canonical_id}`}
                  >
                    {restoringId === entry.canonical_id ? (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
                        Restoring…
                      </>
                    ) : (
                      <>
                        <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
                        Restore
                      </>
                    )}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </section>

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

      {/* Resolved (recently cleared) — gives the operator a way to recall a card */}
      {queue.resolved.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Check className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-serif font-bold text-foreground">Resolved (recently cleared)</h2>
            <span className="text-xs text-slate-500">
              Hidden from the active queue. Click "Un-resolve" to bring a card back if you changed your mind.
            </span>
          </div>
          <div className="rounded-md border border-slate-700 overflow-x-auto -mx-4 md:mx-0">
            <table className="w-full min-w-[820px] text-xs" data-testid="resolved-table">
              <thead className="bg-slate-800/60 text-slate-400">
                <tr>
                  <th className="text-left px-3 py-2">Resolved</th>
                  <th className="text-left px-3 py-2">Employee</th>
                  <th className="text-left px-3 py-2">Field</th>
                  <th className="text-left px-3 py-2">Action</th>
                  <th className="text-left px-3 py-2">Stored at resolution</th>
                  <th className="text-left px-3 py-2">Note</th>
                  <th className="text-right px-3 py-2">Recall</th>
                </tr>
              </thead>
              <tbody>
                {queue.resolved.map((r) => (
                  <tr
                    key={r.conflict_id}
                    className="border-t border-slate-800 hover:bg-slate-800/30"
                    data-testid={`resolved-row-${r.conflict_id}`}
                  >
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{formatTimestamp(r.resolved_at)}</td>
                    <td className="px-3 py-2 text-slate-200 font-semibold">{r.employee_name}</td>
                    <td className="px-3 py-2 text-slate-300 font-mono">{r.field}</td>
                    <td className="px-3 py-2 text-slate-300">{ACTION_LABEL[r.action] || r.action}</td>
                    <td className="px-3 py-2 font-mono text-emerald-300">{formatValue(r.post_stored)}</td>
                    <td className="px-3 py-2 text-slate-400">{r.reason || "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        className="border-slate-600 text-slate-200 hover:bg-slate-800"
                        onClick={() => unresolve(r.conflict_id, r.employee_name)}
                        data-testid={`btn-unresolve-${r.conflict_id}`}
                      >
                        <RefreshCw className="w-3 h-3 mr-1" />
                        Un-resolve
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
          <div className="rounded-md border border-slate-700 overflow-x-auto -mx-4 md:mx-0">
            <table className="w-full min-w-[920px] text-xs" data-testid="audit-log">
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
          className="max-w-xl bg-slate-900 border-slate-700 text-slate-100 max-h-[90vh] overflow-y-auto"
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
