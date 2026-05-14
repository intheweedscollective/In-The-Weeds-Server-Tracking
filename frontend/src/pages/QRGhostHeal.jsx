import { useEffect, useState, useMemo } from "react";
import { toast } from "sonner";
import { Loader2, Ghost, CheckCircle2, AlertTriangle, ArrowLeft } from "lucide-react";
import api from "../lib/api";
import { Link } from "react-router-dom";

/**
 * QRGhostHeal
 *
 * Admin page that re-attributes QR scans recorded against employee UUIDs
 * that no longer exist in `qr_employees` (i.e. cards laminated before a
 * collection wipe). Loads suggestions from
 * `/api/qr/admin/suggest-ghost-mappings`, lets the admin confirm /
 * override the canonical target per row, then calls
 * `/api/qr/admin/heal-ghost-ids` which back-fills the dashboard counters
 * from the immutable log.
 */
export default function QRGhostHeal() {
  const [loading, setLoading] = useState(true);
  const [suggestions, setSuggestions] = useState([]);
  const [qrEmployees, setQrEmployees] = useState([]);
  const [selections, setSelections] = useState({});
  const [healing, setHealing] = useState(false);
  const [applyingInventory, setApplyingInventory] = useState(false);
  const [result, setResult] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const [sugg, emps] = await Promise.all([
        api.get("/qr/admin/suggest-ghost-mappings"),
        api.get("/qr/employees"),
      ]);
      const s = sugg.data?.suggestions || [];
      setSuggestions(s);
      setQrEmployees(emps.data || []);
      // Pre-seed selections from suggestions.
      const seed = {};
      for (const row of s) {
        if (row.suggested_canonical_id) seed[row.printed_id] = row.suggested_canonical_id;
      }
      setSelections(seed);
    } catch (e) {
      toast.error("Failed to load ghost-ID list");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const sortedEmps = useMemo(
    () => [...qrEmployees].sort((a, b) => (a.name || "").localeCompare(b.name || "")),
    [qrEmployees]
  );

  const mapped = suggestions.filter((s) => selections[s.printed_id]).length;
  const totalScans = suggestions.reduce((acc, s) => acc + (s.scan_count || 0), 0);
  const mappedScans = suggestions
    .filter((s) => selections[s.printed_id])
    .reduce((acc, s) => acc + (s.scan_count || 0), 0);

  const onApplyInventory = async () => {
    setApplyingInventory(true);
    try {
      const res = await api.post("/qr/admin/apply-printed-inventory", {});
      setResult(res.data);
      const matched = res.data?.matched_count ?? 0;
      const reattributed = res.data?.heal?.events_reattributed ?? 0;
      toast.success(
        `Inventory applied: ${matched} servers mapped, ${reattributed} scans re-attributed`
      );
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Inventory apply failed");
    } finally {
      setApplyingInventory(false);
    }
  };

  const onHeal = async (dryRun = false) => {
    const mappings = Object.entries(selections)
      .filter(([, cid]) => !!cid)
      .map(([printed_id, canonical_id]) => ({ printed_id, canonical_id }));
    if (!mappings.length) {
      toast.error("Pick at least one mapping first.");
      return;
    }
    setHealing(true);
    try {
      const res = await api.post("/qr/admin/heal-ghost-ids", { mappings, dry_run: dryRun });
      setResult(res.data);
      toast.success(
        dryRun
          ? `Dry run: ${res.data.events_reattributed} events would be re-attributed`
          : `Healed: ${res.data.events_reattributed} scans re-attributed to ${res.data.employees_updated} employees`
      );
      if (!dryRun) await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Heal failed");
    } finally {
      setHealing(false);
    }
  };

  return (
    <div className="p-6 max-w-6xl mx-auto" data-testid="qr-ghost-heal-page">
      <div className="flex items-center justify-between mb-6">
        <div>
          <Link to="/qr" className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 mb-2">
            <ArrowLeft className="w-3 h-3" /> Back to QR Dashboard
          </Link>
          <h1 className="text-3xl font-bold text-slate-100 flex items-center gap-2">
            <Ghost className="w-7 h-7 text-amber-400" /> Ghost QR Card Healing
          </h1>
          <p className="text-sm text-slate-400 mt-2 max-w-3xl">
            Physical QR cards printed before a collection wipe carry UUIDs that no longer
            exist. Scans from those cards land in the immutable audit log but don't
            increment any dashboard counter. Map each ghost UUID to its current
            employee and we'll back-fill every prior scan.
          </p>
          <div className="mt-3 p-3 bg-emerald-900/20 border border-emerald-700/40 rounded text-xs text-emerald-200 max-w-3xl">
            <b>Fastest path:</b> click <b>Apply Known Inventory</b> below — it loads the
            33-card inventory decoded from the uploaded ZIP, auto-matches names against
            your current roster, and back-fills counters in one shot.
          </div>
        </div>
        <div className="text-right text-xs text-slate-300">
          <div><span className="text-slate-500">Ghost IDs:</span> <b>{suggestions.length}</b></div>
          <div><span className="text-slate-500">Mapped:</span> <b>{mapped}</b> / {suggestions.length}</div>
          <div><span className="text-slate-500">Unattributed scans:</span> <b>{totalScans}</b></div>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400"><Loader2 className="w-4 h-4 animate-spin" /> Loading…</div>
      ) : suggestions.length === 0 ? (
        <div className="p-8 text-center bg-emerald-900/20 border border-emerald-700/40 rounded-lg" data-testid="no-ghosts-message">
          <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
          <p className="text-emerald-200 font-medium">No ghost QR IDs detected.</p>
          <p className="text-emerald-300/70 text-sm mt-1">
            Every scanned UUID resolves to an active employee or an existing alias.
          </p>
          <button
            className="mt-4 px-4 py-2 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-xs"
            data-testid="apply-inventory-no-ghosts"
            onClick={onApplyInventory}
            disabled={applyingInventory}
          >
            {applyingInventory ? <Loader2 className="w-3 h-3 inline-block animate-spin mr-1" /> : null}
            Re-apply Known Inventory (safe, idempotent)
          </button>
          {result && (
            <pre className="mt-4 p-3 bg-slate-900 border border-slate-700 rounded text-xs text-slate-200 overflow-auto text-left" data-testid="heal-result-empty">
{JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      ) : (
        <>
          <div className="overflow-x-auto border border-slate-700 rounded-lg" data-testid="ghost-table">
            <table className="w-full text-sm">
              <thead className="bg-slate-800/60 text-slate-300">
                <tr>
                  <th className="text-left p-3">Printed ID (on card)</th>
                  <th className="text-left p-3">Historical Name</th>
                  <th className="text-right p-3">Scans</th>
                  <th className="text-left p-3">Date Range</th>
                  <th className="text-left p-3">Map to Current Employee</th>
                  <th className="text-left p-3">Confidence</th>
                </tr>
              </thead>
              <tbody>
                {suggestions.map((s) => {
                  const conf = s.confidence;
                  const confColor = conf === "high"
                    ? "text-emerald-400" : conf === "medium"
                    ? "text-amber-300" : "text-slate-500";
                  return (
                    <tr key={s.printed_id} className="border-t border-slate-700/60 hover:bg-slate-800/30" data-testid={`ghost-row-${s.printed_id}`}>
                      <td className="p-3 font-mono text-xs text-slate-400">{s.printed_id.slice(0, 13)}…</td>
                      <td className="p-3 text-slate-200">
                        {(s.historical_names && s.historical_names[0]) || s.suggested_name || <span className="text-slate-500 italic">unknown</span>}
                      </td>
                      <td className="p-3 text-right text-slate-100 font-medium">{s.scan_count}</td>
                      <td className="p-3 text-slate-400 text-xs">
                        {(s.earliest_scan || "").slice(0, 10)} → {(s.latest_scan || "").slice(0, 10)}
                      </td>
                      <td className="p-3">
                        <select
                          className="bg-slate-800 border border-slate-600 text-slate-100 text-sm rounded px-2 py-1 min-w-[220px]"
                          data-testid={`select-${s.printed_id}`}
                          value={selections[s.printed_id] || ""}
                          onChange={(e) => setSelections((p) => ({ ...p, [s.printed_id]: e.target.value }))}
                        >
                          <option value="">— skip —</option>
                          {sortedEmps.map((emp) => (
                            <option key={emp.id} value={emp.id}>{emp.name}</option>
                          ))}
                        </select>
                      </td>
                      <td className={`p-3 text-xs uppercase ${confColor}`}>{conf}{s.source ? ` · ${s.source.replace(/_/g, " ")}` : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="mt-4 p-3 bg-slate-800/40 border border-slate-700/60 rounded text-xs text-slate-300 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
            <div>
              About to re-attribute <b className="text-amber-300">{mappedScans}</b> scans across <b>{mapped}</b> mapped UUIDs.
              This writes to <code className="text-amber-200">qr_employee_id_aliases</code> and increments per-employee counters.
              Idempotent — safe to re-run.
            </div>
          </div>

          <div className="flex gap-2 mt-4 flex-wrap">
            <button
              className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded text-sm font-medium disabled:opacity-50"
              data-testid="apply-inventory-button"
              disabled={applyingInventory || healing}
              onClick={onApplyInventory}
            >
              {applyingInventory ? <Loader2 className="w-4 h-4 inline-block animate-spin mr-1" /> : null}
              Apply Known Inventory (33 cards)
            </button>
            <button
              className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-100 rounded text-sm disabled:opacity-50"
              data-testid="dry-run-button"
              disabled={healing || mapped === 0}
              onClick={() => onHeal(true)}
            >
              Preview manual mapping (dry-run)
            </button>
            <button
              className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded text-sm font-medium disabled:opacity-50"
              data-testid="heal-button"
              disabled={healing || mapped === 0}
              onClick={() => onHeal(false)}
            >
              {healing ? <Loader2 className="w-4 h-4 inline-block animate-spin mr-1" /> : null}
              Heal {mapped} manual mapping{mapped === 1 ? "" : "s"}
            </button>
          </div>

          {result && (
            <pre className="mt-4 p-3 bg-slate-900 border border-slate-700 rounded text-xs text-slate-200 overflow-auto" data-testid="heal-result">
{JSON.stringify(result, null, 2)}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
