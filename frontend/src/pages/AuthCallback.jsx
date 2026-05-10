import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { toast } from "sonner";
import { useAuth } from "../context/AuthContext";

/**
 * Handles the redirect from auth.emergentagent.com.
 *
 * The Emergent OAuth service appends `#session_id=...` to the redirect URL
 * AFTER the Google login completes. We grab that one-shot id, exchange it
 * server-side for a 7-day session_token cookie, then bounce into the app.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH (use window.location.origin only).
 */
export default function AuthCallback() {
  const navigate = useNavigate();
  const { refresh } = useAuth();
  // useRef (not useState) so React StrictMode's double-mount doesn't double-call
  // the one-shot session exchange.
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    const sessionId = match ? decodeURIComponent(match[1]) : null;

    // Where the user wanted to go before we yanked them through Google.
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next") || "/";

    if (!sessionId) {
      toast.error("Login flow returned no session id. Please try again.");
      navigate("/login", { replace: true });
      return;
    }

    (async () => {
      try {
        const r = await api.post("/auth/session", { session_id: sessionId });
        if (!r.data?.is_admin) {
          toast.warning(
            `${r.data?.email || "Signed in"}. Your account isn't on the editor whitelist — you can view but not change anything.`,
            { duration: 6000 }
          );
        } else {
          toast.success(`Welcome back, ${r.data?.name || r.data?.email}`);
        }
        // Pull the freshly-set cookie into AuthContext.user — without this,
        // the sidebar / protected pages still see `user = null` even though
        // the session cookie is set, because AuthProvider only ran /auth/me
        // once on initial mount and we explicitly skipped it during the
        // OAuth-callback hash phase.
        await refresh();
        // Strip the #session_id from history and continue.
        navigate(next, { replace: true });
      } catch (err) {
        toast.error(err.response?.data?.detail || "Login failed. Please try again.");
        navigate("/login", { replace: true });
      }
    })();
  }, [navigate, refresh]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">
      <div className="text-center text-slate-300">
        <div className="w-12 h-12 border-4 border-slate-700 border-t-amber-400 rounded-full animate-spin mx-auto mb-4" />
        <p className="text-sm tracking-wide">Signing you in…</p>
      </div>
    </div>
  );
}
