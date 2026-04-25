import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Edit2, Check, X, Database } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "./ui/button";

/**
 * SnapshotLiveEdit
 * ----------------
 * Displays the active snapshot's POS / NPS / RT data inline with edit-in-place
 * controls. Used on the Data Uploads page so spot-fixes don't require running
 * the full Snapshot Workflow wizard again.
 *
 * Edits go through PUT /v2/employees/{id} which already handles the
 * snapshot-UUID fallback we wired in earlier this session.
 */

const FIELDS = [
  { key: "guest_count", label: "Guests", type: "int", color: "text-slate-200" },
  { key: "ppa", label: "PPA", type: "float", color: "text-blue-300", prefix: "$" },
  { key: "liquor_sales", label: "Liquor", type: "float", color: "text-amber-400", prefix: "$" },
  { key: "beer_sales", label: "Beer", type: "float", color: "text-amber-300", prefix: "$" },
  { key: "wine_sales", label: "Wine", type: "float", color: "text-rose-300", prefix: "$" },
  { key: "bar_glassware_sales", label: "Glass", type: "float", color: "text-purple-300", prefix: "$" },
  { key: "loyalty_sales", label: "LSC", type: "float", color: "text-emerald-300", prefix: "$" },
  { key: "rt_mentions", label: "RT", type: "int", color: "text-yellow-300" },
  { key: "nps_score", label: "NPS", type: "float", color: "text-teal-300" },
];

export default function SnapshotLiveEdit({ quarter, year }) {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [saving, setSaving] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get(
        `/v2/snapshot-workflow/current-rankings?year=${year}&quarter=${quarter}`
      );
      setEmployees(res.data?.employees || []);
    } catch (e) {
      toast.error("Could not load active snapshot data");
      setEmployees([]);
    } finally {
      setLoading(false);
    }
  }, [quarter, year]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const startEdit = (emp) => {
    setEditingId(emp.id);
    const initial = {};
    FIELDS.forEach((f) => {
      initial[f.key] = emp[f.key] ?? 0;
    });
    setEditForm(initial);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm({});
  };

  const saveEdit = async (emp) => {
    setSaving(true);
    try {
      // Coerce types
      const payload = {};
      FIELDS.forEach((f) => {
        const raw = editForm[f.key];
        if (raw === "" || raw == null) return;
        const num = f.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
        if (!Number.isNaN(num)) payload[f.key] = num;
      });
      // Recompute LBW total + per-guest derived fields client-side so the
      // table reflects the change instantly even before the snapshot rebuilds.
      const lbw = (payload.liquor_sales ?? emp.liquor_sales ?? 0)
        + (payload.beer_sales ?? emp.beer_sales ?? 0)
        + (payload.wine_sales ?? emp.wine_sales ?? 0);
      payload.lbw = lbw;
      payload.lbw_total = lbw;
      const guests = payload.guest_count ?? emp.guest_count ?? 0;
      if (guests > 0) {
        payload.lbw_per_guest = +(lbw / guests).toFixed(2);
        if (payload.bar_glassware_sales != null) {
          payload.glassware_per_guest = +(payload.bar_glassware_sales / guests).toFixed(2);
        }
        if (payload.ppa == null && payload.net_sales != null) {
          payload.ppa = +(payload.net_sales / guests).toFixed(2);
        }
      }

      await api.put(`/v2/employees/${emp.id}`, payload);
      toast.success(`Saved ${emp.display_name || emp.name}`);
      cancelEdit();
      fetchData();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const fmt = (val, field) => {
    if (val == null) return "—";
    const num = Number(val);
    if (Number.isNaN(num)) return "—";
    if (field.type === "int") return num.toLocaleString();
    const fixed = num.toLocaleString(undefined, { maximumFractionDigits: 2 });
    return field.prefix ? `${field.prefix}${fixed}` : fixed;
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700/50 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between p-3 md:p-4 border-b border-slate-700/50">
        <div className="flex items-center gap-2">
          <Database className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
          <h3 className="font-semibold text-white text-sm md:text-base">
            Active Snapshot — {quarter} {year}
          </h3>
          {!loading && (
            <span className="text-xs text-slate-400">{employees.length} employees</span>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          onClick={fetchData}
          disabled={loading}
          className="border-slate-600 text-slate-300"
          data-testid="refresh-snapshot-data"
        >
          <RefreshCw className={`w-3.5 h-3.5 mr-1 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="p-8 text-center text-slate-400 text-sm">Loading active snapshot…</div>
      ) : employees.length === 0 ? (
        <div className="p-8 text-center text-slate-400 text-sm">
          No active snapshot for {quarter} {year}.
          {" "}
          <a href="/snapshot-workflow" className="text-blue-400 hover:underline">Start one</a>.
        </div>
      ) : (
        <div className="max-h-[500px] overflow-auto">
          <table className="w-full text-xs md:text-sm">
            <thead className="bg-slate-900/60 sticky top-0">
              <tr className="text-slate-400">
                <th className="text-left px-2 md:px-3 py-2 font-medium">Name</th>
                {FIELDS.map((f) => (
                  <th key={f.key} className={`text-right px-2 py-2 font-medium ${f.color}`}>
                    {f.label}
                  </th>
                ))}
                <th className="text-center px-2 py-2 font-medium">Edit</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/50">
              {employees.map((emp) => {
                const isEditing = editingId === emp.id;
                return (
                  <tr key={emp.id} className={`text-slate-300 hover:bg-slate-800/40 ${isEditing ? "bg-blue-900/20" : ""}`}>
                    <td className="px-2 md:px-3 py-2 text-white whitespace-nowrap">
                      {emp.display_name || emp.name}
                    </td>
                    {FIELDS.map((f) => (
                      <td key={f.key} className={`px-2 py-1 text-right ${f.color}`}>
                        {isEditing ? (
                          <input
                            type="number"
                            step={f.type === "int" ? 1 : 0.01}
                            value={editForm[f.key] ?? ""}
                            onChange={(e) =>
                              setEditForm({ ...editForm, [f.key]: e.target.value })
                            }
                            className="w-20 bg-slate-700 border border-slate-600 rounded px-1.5 py-0.5 text-right text-white text-xs"
                            data-testid={`live-edit-${f.key}-${emp.id}`}
                          />
                        ) : (
                          fmt(emp[f.key], f)
                        )}
                      </td>
                    ))}
                    <td className="px-2 py-1 text-center whitespace-nowrap">
                      {isEditing ? (
                        <div className="flex items-center justify-center gap-1">
                          <button
                            onClick={() => saveEdit(emp)}
                            disabled={saving}
                            className="text-green-400 hover:text-green-300 disabled:opacity-50"
                            data-testid={`live-save-${emp.id}`}
                            title="Save"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                          <button
                            onClick={cancelEdit}
                            className="text-slate-400 hover:text-slate-200"
                            title="Cancel"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => startEdit(emp)}
                          className="text-blue-400 hover:text-blue-300"
                          data-testid={`live-edit-btn-${emp.id}`}
                          title="Edit"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
