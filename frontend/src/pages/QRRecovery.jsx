import { useEffect, useState, useCallback } from "react";
import {
  Upload, FileJson, AlertTriangle, CheckCircle2, Database,
  ArrowRight, Trash2, RefreshCw, History, Eye, Layers,
} from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";

/**
 * QR Click Recovery — admin-only file-upload UI for re-importing
 * pre-March QR scan events that were lost when the v1 tracking
 * pipeline was wiped. Atlas backup retention couldn't reach back far
 * enough, so this is the catch-all path for any data the operator
 * later sources from POS reports / external exports / etc.
 *
 * Flow:
 *   1. Drop / pick a .json file (array of scan events).
 *   2. Choose mode — `staging` parks rows in `qr_scans_pre_march_recovered`
 *      for inspection; `merge` writes straight into qr_scans +
 *      qr_click_log_immutable (deduped on `id`).
 *   3. Hit "Dry-run" — shows accepted / skipped / malformed counts
 *      WITHOUT writing anything.
 *   4. Confirm by hitting "Import" — runs the same operation for real.
 *   5. For staging, "Promote to live" pushes from staging into the
 *      live collections; "Clear staging" wipes the staging copy.
 *   6. Audit log section shows every action with actor + timestamp.
 */
export default function QRRecovery() {
  const [file, setFile] = useState(null);
  const [mode, setMode] = useState("staging");
  const [dryRunResult, setDryRunResult] = useState(null);
  const [importResult, setImportResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [staging, setStaging] = useState(null);
  const [audit, setAudit] = useState([]);
  const [dragOver, setDragOver] = useState(false);

  const fetchSidePanels = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([
        api.get("/v2/admin/qr-recovery/staging-summary"),
        api.get("/v2/admin/qr-recovery/audit?limit=50"),
      ]);
      setStaging(s.data || null);
      setAudit(a.data?.entries || []);
    } catch (e) {
      toast.error(`Couldn't refresh: ${e?.response?.data?.detail || e.message}`);
    }
  }, []);

  useEffect(() => { fetchSidePanels(); }, [fetchSidePanels]);

  const submitImport = async (isDryRun) => {
    if (!file) {
      toast.error("Pick a JSON file first.");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("mode", mode);
      fd.append("dry_run", isDryRun ? "true" : "false");
      const res = await api.post(
        "/v2/admin/qr-recovery/import", fd,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      if (isDryRun) {
        setDryRunResult(res.data);
        toast.success("Dry-run complete — review below before importing.");
      } else {
        setImportResult(res.data);
        setDryRunResult(null);
        toast.success(
          `Imported ${res.data?.accepted ?? 0} rows into ${res.data?.target || mode}`,
        );
        await fetchSidePanels();
      }
    } catch (e) {
      toast.error(`Import failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const promote = async () => {
    if (!confirm(
      "Promote every staging row into qr_scans + qr_click_log_immutable?\n\nDuplicates (by id) will be skipped. The staging collection is NOT cleared — use 'Clear staging' afterwards."
    )) return;
    setBusy(true);
    try {
      const res = await api.post("/v2/admin/qr-recovery/promote-staging");
      toast.success(
        `Promoted: ${res.data?.written_to_qr_scans ?? 0} → qr_scans, ${res.data?.written_to_immutable ?? 0} → immutable`,
      );
      await fetchSidePanels();
    } catch (e) {
      toast.error(`Promote failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const clearStaging = async () => {
    if (!confirm(
      "Delete every row from qr_scans_pre_march_recovered?\n\nThis cannot be undone — your audit log will still show the row counts."
    )) return;
    setBusy(true);
    try {
      const res = await api.post("/v2/admin/qr-recovery/clear-staging");
      toast.success(`Cleared ${res.data?.deleted ?? 0} staging rows`);
      await fetchSidePanels();
    } catch (e) {
      toast.error(`Clear failed: ${e?.response?.data?.detail || e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const onDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) {
      setFile(f);
      setDryRunResult(null);
      setImportResult(null);
    }
  };

  const fmtCount = (n) => (n ?? 0).toLocaleString();
  const Result = ({ data, isDry }) => data ? (
    <div className="mt-4 rounded-lg border border-slate-700 bg-slate-800/40 p-4 space-y-2 text-sm">
      <div className="flex items-center gap-2">
        {isDry ? <Eye className="w-4 h-4 text-amber-400" /> : <CheckCircle2 className="w-4 h-4 text-emerald-400" />}
        <span className="font-semibold text-slate-100">
          {isDry ? "Dry-run result" : "Import complete"} — mode: <code className="font-mono">{data.mode}</code>
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2">
        <Stat label="In file" value={fmtCount(data.total_in_file)} />
        <Stat label={isDry ? "Would write" : "Written"} value={fmtCount(data.accepted)} tone="emerald" />
        <Stat label="Skipped (dupes)" value={fmtCount(data.skipped_duplicates)} tone="amber" />
        <Stat label="Malformed" value={fmtCount(data.malformed_count)} tone={data.malformed_count ? "rose" : "slate"} />
      </div>
      {data.target && (
        <div className="text-xs text-slate-400">
          Target: <code className="font-mono text-slate-200">{data.target}</code>
        </div>
      )}
      {data.malformed?.length > 0 && (
        <details className="mt-2">
          <summary className="text-xs text-rose-300 cursor-pointer">
            Show {data.malformed.length} malformed rows (sampled)
          </summary>
          <pre className="text-[10.5px] text-rose-200/80 font-mono max-h-48 overflow-auto bg-slate-900/60 rounded p-2 mt-1">
            {data.malformed.map((m, i) =>
              `[#${m.index}] ${m.reason}\n  ${JSON.stringify(m.row).slice(0, 240)}`,
            ).join("\n\n")}
          </pre>
        </details>
      )}
    </div>
  ) : null;

  return (
    <div className="space-y-6 p-4 md:p-6" data-testid="qr-recovery-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-serif font-bold text-foreground flex items-center gap-2">
            <Database className="w-7 h-7 text-purple-400" />
            QR Click Recovery
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-3xl">
            Re-import pre-March QR scan events from a JSON file. Every action
            is logged. Atlas backups did not reach pre-2026-03-31, so this is
            the only path back — recover events from POS reports, external
            analytics, or any other source.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchSidePanels}
          disabled={busy}
          className="border-slate-600"
          data-testid="qr-recovery-refresh"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${busy ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Drop zone + mode + actions */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-4">
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
            dragOver
              ? "border-amber-400 bg-amber-950/30"
              : "border-slate-600 bg-slate-800/30 hover:border-slate-500"
          }`}
          data-testid="qr-recovery-dropzone"
        >
          <Upload className="w-7 h-7 text-slate-400 mx-auto mb-2" />
          <p className="text-sm text-slate-200">
            Drop a <code className="font-mono text-amber-300">.json</code> file here, or
          </p>
          <label className="inline-block mt-2">
            <span className="px-3 py-1.5 rounded-full bg-slate-700 hover:bg-slate-600 text-sm cursor-pointer text-slate-100 inline-flex items-center gap-2">
              <FileJson className="w-4 h-4" />
              Choose file
            </span>
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              data-testid="qr-recovery-file-input"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  setFile(f);
                  setDryRunResult(null);
                  setImportResult(null);
                }
              }}
            />
          </label>
          {file && (
            <div className="text-xs text-emerald-300 mt-3" data-testid="qr-recovery-file-name">
              Selected: <b>{file.name}</b> · {(file.size / 1024).toFixed(1)} KB
            </div>
          )}
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <span className="text-xs uppercase tracking-wide text-slate-400">Mode</span>
          <div className="inline-flex rounded-full border border-slate-700 bg-slate-800 p-1 text-xs">
            <button
              onClick={() => setMode("staging")}
              className={`px-3 py-1.5 rounded-full ${mode === "staging" ? "bg-amber-500 text-amber-950 font-semibold" : "text-slate-300"}`}
              data-testid="qr-recovery-mode-staging"
            >
              Staging (recommended)
            </button>
            <button
              onClick={() => setMode("merge")}
              className={`px-3 py-1.5 rounded-full ${mode === "merge" ? "bg-rose-600 text-white font-semibold" : "text-slate-300"}`}
              data-testid="qr-recovery-mode-merge"
            >
              Direct merge
            </button>
          </div>
          <span className="text-[11px] text-slate-500 leading-tight">
            {mode === "staging"
              ? "Writes to qr_scans_pre_march_recovered only — review before promoting."
              : "Writes directly to qr_scans + qr_click_log_immutable. Deduped on id."}
          </span>
        </div>

        <div className="flex flex-wrap gap-2 border-t border-slate-800 pt-3">
          <Button
            variant="outline"
            onClick={() => submitImport(true)}
            disabled={busy || !file}
            className="border-amber-700 text-amber-200 hover:bg-amber-950/40"
            data-testid="qr-recovery-dry-run"
          >
            <Eye className="w-4 h-4 mr-1.5" />
            Dry-run
          </Button>
          <Button
            onClick={() => submitImport(false)}
            disabled={busy || !file}
            className="bg-emerald-700 hover:bg-emerald-600 text-white"
            data-testid="qr-recovery-import"
          >
            <ArrowRight className="w-4 h-4 mr-1.5" />
            Import (real)
          </Button>
        </div>

        <Result data={dryRunResult} isDry />
        <Result data={importResult} />
      </section>

      {/* Staging panel */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Layers className="w-5 h-5 text-amber-400" />
          <h2 className="text-xl font-serif font-bold text-foreground">Staging Collection</h2>
          <span className="text-xs text-slate-500">
            qr_scans_pre_march_recovered · rows here aren't live yet
          </span>
        </div>
        {staging == null ? (
          <div className="text-slate-400 text-sm">Loading…</div>
        ) : staging.total === 0 ? (
          <div className="rounded-md border border-slate-700 bg-slate-800/40 p-3 text-sm text-slate-400">
            Staging is empty.
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <Stat label="Rows in staging" value={fmtCount(staging.total)} />
              <Stat label="Would skip on promote" value={fmtCount(staging.would_skip_on_promote)} tone="amber" />
              <Stat label="Earliest" value={staging.earliest?.slice(0, 10) || "—"} />
              <Stat label="Latest" value={staging.latest?.slice(0, 10) || "—"} />
            </div>
            <div className="text-xs text-slate-400">
              By platform:&nbsp;
              {Object.entries(staging.by_platform || {}).map(([p, n]) => (
                <span key={p} className="inline-block px-2 py-0.5 rounded-full bg-slate-800 mr-1">
                  <code className="font-mono">{p}</code>: <b>{fmtCount(n)}</b>
                </span>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 pt-3 border-t border-slate-800">
              <Button
                onClick={promote}
                disabled={busy}
                className="bg-emerald-700 hover:bg-emerald-600 text-white"
                data-testid="qr-recovery-promote"
              >
                <ArrowRight className="w-4 h-4 mr-1.5" />
                Promote staging → live
              </Button>
              <Button
                variant="outline"
                onClick={clearStaging}
                disabled={busy}
                className="border-rose-700 text-rose-300 hover:bg-rose-950/40"
                data-testid="qr-recovery-clear-staging"
              >
                <Trash2 className="w-4 h-4 mr-1.5" />
                Clear staging
              </Button>
            </div>
          </div>
        )}
      </section>

      {/* Audit log */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
        <div className="flex items-center gap-2 mb-3">
          <History className="w-5 h-5 text-slate-400" />
          <h2 className="text-xl font-serif font-bold text-foreground">Recovery Audit</h2>
          <span className="text-xs text-slate-500">Last 50 actions · append-only</span>
        </div>
        {audit.length === 0 ? (
          <div className="text-slate-500 text-sm">No actions logged yet.</div>
        ) : (
          <div className="rounded-md border border-slate-700 overflow-x-auto -mx-4 md:mx-0">
            <table className="w-full min-w-[700px] text-xs" data-testid="qr-recovery-audit-table">
              <thead className="bg-slate-800/60 text-slate-400">
                <tr>
                  <th className="text-left px-3 py-2">When</th>
                  <th className="text-left px-3 py-2">Actor</th>
                  <th className="text-left px-3 py-2">Action</th>
                  <th className="text-left px-3 py-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((e, i) => (
                  <tr key={`${e.id || i}`} className="border-t border-slate-800 hover:bg-slate-800/30">
                    <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                      {e.logged_at ? new Date(e.logged_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-slate-200">{e.actor}</td>
                    <td className="px-3 py-2 text-slate-300 font-mono">{e.action}</td>
                    <td className="px-3 py-2 text-slate-400 font-mono text-[11px]">
                      {Object.entries(e)
                        .filter(([k]) => !["id", "actor", "action", "logged_at"].includes(k))
                        .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
                        .join(" · ")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Schema reference */}
      <section className="rounded-xl border border-slate-700 bg-slate-900/60 p-4">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-5 h-5 text-amber-400" />
          <h3 className="text-base font-semibold text-foreground">Expected JSON shape</h3>
        </div>
        <p className="text-xs text-slate-400 mb-2">
          File must be a top-level JSON array. Each row needs at minimum:
          <code className="font-mono mx-1">id</code> (UUID, dedupe key),
          <code className="font-mono mx-1">employee_id</code>,
          <code className="font-mono mx-1">platform</code> (yelp | google | tripadvisor), and
          <code className="font-mono mx-1">scanned_at</code> (ISO 8601).
        </p>
        <pre className="text-[11px] text-slate-300 font-mono bg-slate-950/60 rounded p-3 overflow-auto">
{`[
  {
    "id": "f4d2c9b6-0b3e-4f1a-9a7c-2e0d18f4a000",
    "employee_id": "4ca7e834-721b-4d8b-8217-253f2f1bc510",
    "employee_name": "Robert Mckinnon",
    "platform": "google",
    "scanned_at": "2026-02-14T17:42:03+00:00"
  }
]`}
        </pre>
      </section>
    </div>
  );
}

function Stat({ label, value, tone = "slate" }) {
  const map = {
    slate:   "bg-slate-800 text-slate-100 border-slate-700",
    emerald: "bg-emerald-950/40 text-emerald-200 border-emerald-700/60",
    amber:   "bg-amber-950/40 text-amber-200 border-amber-700/60",
    rose:    "bg-rose-950/40 text-rose-200 border-rose-700/60",
  };
  return (
    <div className={`rounded-md border p-2 ${map[tone] || map.slate}`}>
      <div className="text-[10.5px] uppercase tracking-wide opacity-70">{label}</div>
      <div className="text-base font-bold font-mono mt-0.5">{value}</div>
    </div>
  );
}
