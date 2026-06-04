import { useEffect, useState, useCallback } from "react";
import { GitBranch, Clock, Copy, X, Check } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";

/**
 * Tiny build-version chip pinned bottom-right on every page. Solves
 * the chronic "did my deploy actually land?" question — operator can
 * redeploy, refresh, and check the chip; if the SHA hasn't changed
 * the deploy pipeline is stuck.
 *
 * Collapsed state: a 28×28 dot with the short SHA. One click expands
 * into a card showing SHA · branch · commit subject · committed time
 * · process start time · host · env. Card has a "Copy diagnostic"
 * button that puts everything on the clipboard formatted for a
 * support email — the exact text Emergent Support asks for.
 *
 * Polls /api/version every 5 minutes so a deploy that lands while
 * the page is open updates the chip without a manual reload.
 */
export default function VersionChip() {
  const [info, setInfo] = useState(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const [err, setErr] = useState(null);

  const fetchVersion = useCallback(async () => {
    try {
      const res = await api.get("/version");
      setInfo(res.data);
      setErr(null);
    } catch (e) {
      // Don't toast — the chip is purely diagnostic, failing silently
      // beats spamming the user. We DO surface the error inside the
      // expanded card so it's visible if someone clicks for details.
      setErr(e?.response?.status ? `HTTP ${e.response.status}` : (e?.message || "fetch failed"));
    }
  }, []);

  useEffect(() => {
    fetchVersion();
    const t = setInterval(fetchVersion, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetchVersion]);

  const fmtTime = (iso) => {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        year: "numeric", month: "short", day: "numeric",
        hour: "numeric", minute: "2-digit",
      });
    } catch { return iso; }
  };

  const copyDiagnostic = async () => {
    const lines = [
      `Build SHA:    ${info?.sha || "unknown"}  (${info?.branch || "?"})`,
      `Commit:       ${info?.subject || ""}`,
      `Committed:    ${info?.committed_at || "—"}`,
      `Started at:   ${info?.started_at || "—"}`,
      `Host:         ${info?.hostname || "—"}`,
      `Env:          ${info?.env || "—"}`,
      `Page URL:     ${typeof window !== "undefined" ? window.location.href : ""}`,
      `User agent:   ${typeof navigator !== "undefined" ? navigator.userAgent : ""}`,
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied(true);
      toast.success("Diagnostic info copied — paste into your support email.");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Clipboard blocked. Long-press the text and choose Copy.");
    }
  };

  // Always render — even when fetch fails, so the user has a
  // consistent place to click for diagnostics.
  const sha = info?.sha || (err ? "ERR" : "…");
  const envTone =
    info?.env === "production" ? "bg-emerald-600 text-emerald-50"
    : info?.env === "preview"  ? "bg-amber-500 text-amber-950"
    :                             "bg-slate-700 text-slate-100";

  return (
    <>
      {/* Collapsed pill */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          data-testid="version-chip"
          aria-label={`Build ${sha} — click for details`}
          className="fixed bottom-14 right-3 z-[60] inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10.5px] font-mono font-semibold backdrop-blur-md bg-slate-900/80 border border-slate-700 text-slate-200 hover:bg-slate-800 hover:border-slate-500 transition-colors shadow-lg"
          title={`Click for build details · committed ${fmtTime(info?.committed_at)}`}
        >
          <span className={`inline-block w-1.5 h-1.5 rounded-full ${
            info?.env === "production" ? "bg-emerald-400" :
            info?.env === "preview"    ? "bg-amber-400"    :
                                          "bg-slate-400"
          }`} />
          <GitBranch className="w-3 h-3 opacity-60" />
          {sha}
        </button>
      )}

      {/* Expanded card */}
      {open && (
        <div
          className="fixed bottom-14 right-3 z-[60] w-[320px] max-w-[calc(100vw-1.5rem)] rounded-xl border border-slate-700 bg-slate-900/95 backdrop-blur-xl shadow-2xl text-slate-100"
          data-testid="version-chip-expanded"
        >
          <div className="flex items-start justify-between px-3 py-2 border-b border-slate-800">
            <div className="flex items-center gap-2">
              <GitBranch className="w-4 h-4 text-amber-400" />
              <span className="text-xs uppercase tracking-wide text-slate-400">
                Build
              </span>
              <code className="text-xs font-mono font-bold text-slate-100">{sha}</code>
              <span className={`text-[9.5px] uppercase tracking-wider px-1.5 py-0.5 rounded-full font-bold ${envTone}`}>
                {info?.env || "?"}
              </span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="text-slate-400 hover:text-slate-100 -mr-1 -mt-1 p-1"
              aria-label="Close"
              data-testid="version-chip-close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <dl className="px-3 py-2 space-y-1.5 text-[11.5px]">
            <Row label="Branch" value={info?.branch || "—"} mono />
            {info?.subject && (
              <Row label="Commit" value={info.subject} />
            )}
            <Row
              label="Committed"
              value={fmtTime(info?.committed_at)}
              icon={<Clock className="w-3 h-3 opacity-60" />}
            />
            <Row
              label="Deployed"
              value={fmtTime(info?.started_at)}
              icon={<Clock className="w-3 h-3 opacity-60" />}
              hint="Process start — proxies the moment this build went live."
            />
            <Row label="Host" value={info?.hostname || "—"} mono small />
            {err && (
              <Row label="Error" value={err} tone="rose" />
            )}
          </dl>

          <div className="px-3 pb-3 pt-1 flex gap-2 border-t border-slate-800">
            <button
              onClick={copyDiagnostic}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-100 text-[11px] font-semibold py-1.5"
              data-testid="version-chip-copy"
            >
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied" : "Copy diagnostic"}
            </button>
            <button
              onClick={fetchVersion}
              className="inline-flex items-center justify-center rounded-md border border-slate-700 hover:bg-slate-800 text-slate-300 text-[11px] px-2 py-1.5"
              data-testid="version-chip-refresh"
              title="Re-fetch /api/version"
            >
              Refresh
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function Row({ label, value, mono, small, icon, tone, hint }) {
  const toneCls =
    tone === "rose" ? "text-rose-300" :
    "text-slate-200";
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-[68px] shrink-0 text-[10px] uppercase tracking-wider text-slate-500">
        {label}
      </dt>
      <dd className={`flex-1 min-w-0 ${toneCls} ${mono ? "font-mono" : ""} ${small ? "text-[10.5px] break-all" : ""}`}>
        <span className="inline-flex items-center gap-1.5">
          {icon}
          <span className="truncate">{value}</span>
        </span>
        {hint && (
          <span className="block text-[9.5px] text-slate-500 mt-0.5 leading-tight">
            {hint}
          </span>
        )}
      </dd>
    </div>
  );
}
