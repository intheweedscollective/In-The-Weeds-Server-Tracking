import { useState, useEffect, useCallback } from "react";
import { UserPlus, Trash2, RefreshCw, Lightbulb, Search, Plus, X } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { getCurrentQuarter } from "../lib/quarterUtils";

/**
 * NicknameManager
 * ----------------
 * Lets the operator manage nickname → formal-name mappings used by the
 * snapshot CV/RT merge to route shortened review names ("Keisha") to the
 * right employee ("Lakeisha"). Defaults are read-only; user-created
 * entries can be added or removed.
 */
export default function NicknameManager() {
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [defaults, setDefaults] = useState([]);
  const [userAliases, setUserAliases] = useState([]);
  const [nickname, setNickname] = useState("");
  const [formal, setFormal] = useState("");
  // Auto-suggest panel (RT-based) state
  const [suggestions, setSuggestions] = useState([]);
  const [snapshotEmployees, setSnapshotEmployees] = useState([]);
  const [dismissedNames, setDismissedNames] = useState([]);
  const [resolvingName, setResolvingName] = useState(null); // unmatched name being mapped
  const [resolveTarget, setResolveTarget] = useState(""); // employee first-name selected
  const { quarter, year } = getCurrentQuarter();

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [aliasesRes, sugRes] = await Promise.all([
        api.get("/v2/snapshot-workflow/nicknames"),
        api.get(`/v2/snapshot-workflow/nicknames/unmatched-suggestions?quarter=${quarter}&year=${year}`),
      ]);
      setDefaults(aliasesRes.data?.defaults || []);
      setUserAliases(aliasesRes.data?.user || []);
      setSuggestions(sugRes.data?.unmatched || []);
      setSnapshotEmployees(sugRes.data?.employees || []);
      setDismissedNames(sugRes.data?.dismissed || []);
    } catch (e) {
      toast.error("Could not load nicknames");
    } finally {
      setLoading(false);
    }
  }, [quarter, year]);

  useEffect(() => {
    fetchAll();
  }, [fetchAll]);

  const handleAdd = async () => {
    const nick = nickname.trim().toLowerCase();
    const form = formal.trim().toLowerCase();
    if (!nick || !form) {
      toast.error("Both nickname and formal name are required");
      return;
    }
    setAdding(true);
    try {
      const res = await api.post("/v2/snapshot-workflow/nicknames", {
        nickname: nick,
        formal: form,
      });
      toast.success(
        res.data?.updated
          ? `Updated: ${nick} → ${form}`
          : `Added: ${nick} → ${form}`
      );
      setNickname("");
      setFormal("");
      fetchAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add alias");
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id, label) => {
    try {
      await api.delete(`/v2/snapshot-workflow/nicknames/${id}`);
      toast.success(`Removed ${label}`);
      fetchAll();
    } catch (e) {
      toast.error("Delete failed");
    }
  };

  const handleResolveSuggestion = async (suggestionName, formalFirstName) => {
    // Map an unmatched RT name → existing employee's first name as alias.
    if (!formalFirstName) {
      toast.error("Pick an employee to map this nickname to");
      return;
    }
    try {
      await api.post("/v2/snapshot-workflow/nicknames", {
        nickname: suggestionName.toLowerCase(),
        formal: formalFirstName.toLowerCase(),
      });
      toast.success(`${suggestionName} → ${formalFirstName} added`);
      setResolvingName(null);
      setResolveTarget("");
      fetchAll();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to add alias");
    }
  };

  const handleDismissSuggestion = async (suggestionName) => {
    // Persistent dismissal — survives RT re-uploads. Used for former
    // employees and review-text false-positives the stop-word list
    // missed. Reverse via the Dismissed list section if needed.
    try {
      await api.post("/v2/snapshot-workflow/nicknames/dismissals", {
        name: suggestionName.toLowerCase(),
      });
      toast.success(`${suggestionName} hidden permanently`);
      fetchAll();
    } catch (e) {
      toast.error("Could not dismiss");
    }
  };

  const handleRestoreDismissal = async (name) => {
    try {
      await api.delete(`/v2/snapshot-workflow/nicknames/dismissals/${encodeURIComponent(name)}`);
      toast.success(`${name} restored to suggestions`);
      fetchAll();
    } catch (e) {
      toast.error("Restore failed");
    }
  };

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-5 md:p-6">
      <div className="flex items-start justify-between flex-wrap gap-3 mb-4">
        <div>
          <h2 className="text-lg md:text-xl font-bold text-gray-900 flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-blue-600" />
            Nickname Aliases
          </h2>
          <p className="text-sm text-gray-600 mt-1 max-w-2xl">
            Map nicknames customers/reviewers use ("Keisha", "Trey", "TK") to
            the formal first name on the POS report so CV &amp; Review Tracker
            mentions land on the right employee.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={fetchAll}
          disabled={loading}
          className="text-gray-600"
          data-testid="nicknames-refresh"
        >
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* Auto-suggestions from latest RT upload */}
      {suggestions.length > 0 && (
        <div className="bg-amber-50 border border-amber-300 rounded-lg p-4 mb-5" data-testid="unmatched-suggestions-panel">
          <p className="text-xs text-amber-900 font-semibold uppercase tracking-wide mb-2 flex items-center gap-1.5">
            <Search className="w-3.5 h-3.5" />
            Unmatched Names from {quarter} {year} Reviews ({suggestions.length})
          </p>
          <p className="text-xs text-amber-800 mb-3">
            These names appeared in customer reviews but didn't match any employee. Map each one to a real
            server so future uploads route the credit correctly.
          </p>
          <div className="space-y-2">
            {suggestions.map((sug) => (
              <div
                key={sug.name}
                className="flex items-center gap-2 bg-white border border-amber-200 rounded-md px-3 py-2"
                data-testid={`suggestion-${sug.name.toLowerCase()}`}
              >
                <span className="font-semibold text-gray-900 min-w-[90px]">{sug.name}</span>
                <span className="text-xs text-gray-500 flex-shrink-0">
                  {sug.mentions} mention{sug.mentions !== 1 ? "s" : ""}
                </span>
                {resolvingName === sug.name ? (
                  <>
                    <select
                      value={resolveTarget}
                      onChange={(e) => setResolveTarget(e.target.value)}
                      className="flex-1 text-sm border border-gray-300 rounded px-2 py-1 bg-white"
                      data-testid={`resolve-select-${sug.name.toLowerCase()}`}
                    >
                      <option value="">Map to…</option>
                      {snapshotEmployees.map((emp) => (
                        <option key={emp.id} value={emp.first_name}>
                          {emp.name}
                        </option>
                      ))}
                    </select>
                    <Button
                      size="sm"
                      onClick={() => handleResolveSuggestion(sug.name, resolveTarget)}
                      className="bg-green-600 hover:bg-green-700 text-white h-8 px-3"
                      disabled={!resolveTarget}
                      data-testid={`resolve-confirm-${sug.name.toLowerCase()}`}
                    >
                      Save
                    </Button>
                    <button
                      onClick={() => { setResolvingName(null); setResolveTarget(""); }}
                      className="text-gray-400 hover:text-gray-600 p-1"
                      title="Cancel"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </>
                ) : (
                  <div className="flex items-center gap-1 ml-auto">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => { setResolvingName(sug.name); setResolveTarget(""); }}
                      className="text-amber-700 hover:bg-amber-100 h-8 px-2 text-xs"
                      data-testid={`map-suggestion-${sug.name.toLowerCase()}`}
                    >
                      <Plus className="w-3.5 h-3.5 mr-1" />
                      Map to employee
                    </Button>
                    <button
                      onClick={() => handleDismissSuggestion(sug.name)}
                      className="text-gray-400 hover:text-gray-600 p-1"
                      title="Dismiss (will reappear on next RT upload if still unmatched)"
                      data-testid={`dismiss-suggestion-${sug.name.toLowerCase()}`}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Add new alias */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mb-5">
        <p className="text-xs text-blue-900 font-medium uppercase tracking-wide mb-2 flex items-center gap-1.5">
          <Lightbulb className="w-3.5 h-3.5" />
          Add Custom Alias
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
          <Input
            placeholder="Nickname (e.g. keisha)"
            value={nickname}
            onChange={(e) => setNickname(e.target.value)}
            disabled={adding}
            data-testid="nickname-input"
            className="bg-white"
          />
          <Input
            placeholder="Formal name (e.g. lakeisha)"
            value={formal}
            onChange={(e) => setFormal(e.target.value)}
            disabled={adding}
            onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            data-testid="formal-input"
            className="bg-white"
          />
          <Button
            onClick={handleAdd}
            disabled={adding || !nickname.trim() || !formal.trim()}
            className="bg-blue-600 hover:bg-blue-700 text-white"
            data-testid="add-nickname-btn"
          >
            {adding ? "Adding…" : "Add"}
          </Button>
        </div>
      </div>

      {/* User-managed aliases */}
      <div className="mb-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Your Aliases ({userAliases.length})
        </h3>
        {userAliases.length === 0 ? (
          <p className="text-xs text-gray-500 italic">
            No custom aliases yet. Defaults below are always active.
          </p>
        ) : (
          <div className="border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100">
            {userAliases.map((a) => (
              <div
                key={a.id}
                className="flex items-center justify-between px-3 py-2 hover:bg-gray-50"
                data-testid={`user-alias-${a.id}`}
              >
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-mono text-gray-900 font-semibold">{a.nickname}</span>
                  <span className="text-gray-400">→</span>
                  <span className="font-mono text-blue-700 font-semibold">{a.formal}</span>
                </div>
                <button
                  onClick={() => handleDelete(a.id, `${a.nickname} → ${a.formal}`)}
                  className="text-red-500 hover:text-red-700 p-1 rounded hover:bg-red-50 transition-colors"
                  data-testid={`delete-alias-${a.id}`}
                  title="Remove"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Dismissed names (former employees, etc.) */}
      {dismissedNames.length > 0 && (
        <div className="mb-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Dismissed ({dismissedNames.length})
          </h3>
          <p className="text-xs text-gray-500 mb-2 italic">
            Names that won't appear in suggestions again. Click "Restore" to add back.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {dismissedNames.map((name) => (
              <div
                key={name}
                className="inline-flex items-center gap-1 bg-gray-100 border border-gray-300 rounded-full px-2.5 py-1 text-xs"
                data-testid={`dismissed-${name}`}
              >
                <span className="font-mono text-gray-700">{name}</span>
                <button
                  onClick={() => handleRestoreDismissal(name)}
                  className="text-blue-500 hover:text-blue-700 ml-1 font-medium"
                  title={`Restore ${name} to suggestions`}
                  data-testid={`restore-${name}`}
                >
                  restore
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Defaults (read-only) */}
      <div>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">
          Built-in Defaults ({defaults.length})
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-1.5 text-xs">
          {defaults.map((d) => (
            <div
              key={d.nickname}
              className="bg-gray-50 border border-gray-200 rounded px-2 py-1 flex items-center gap-1 font-mono"
            >
              <span className="text-gray-700">{d.nickname}</span>
              <span className="text-gray-400">→</span>
              <span className="text-gray-900 font-semibold truncate">{d.formal}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
