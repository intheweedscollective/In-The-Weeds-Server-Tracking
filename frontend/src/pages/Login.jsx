import { useEffect, useMemo, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { LogIn, Copy, AlertTriangle, Share2, Check } from "lucide-react";
import { toast } from "sonner";
import { detectWebView, openInSystemBrowser } from "../utils/webviewDetect";

/**
 * Splash / login page. Shown to anyone hitting /login.
 *
 * Layout: dark cinematic backdrop, two logos side-by-side (In the Weeds
 * Collective + Bubba Gump shrimp), a single "Sign in with Google" button,
 * and a small note explaining what auth gates.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
 * THIS BREAKS THE AUTH (use window.location.origin only).
 */
export default function Login() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // Detect once on mount — UA doesn't change after page load.
  const webview = useMemo(() => detectWebView(), []);
  const [showWebViewWarn, setShowWebViewWarn] = useState(webview.isWebView);

  // If they're already signed in, send them straight to wherever they wanted.
  useEffect(() => {
    if (!loading && user) {
      const params = new URLSearchParams(location.search);
      const next = params.get("next") || "/";
      navigate(next, { replace: true });
    }
  }, [user, loading, navigate, location.search]);

  const handleSignIn = () => {
    // If we're inside a known webview, intercept and force the user
    // out to their real browser — Google will 403 the OAuth handshake
    // with `disallowed_useragent` otherwise. We give them a one-tap
    // escape AND a copyable link as a fallback.
    if (webview.isWebView) {
      setShowWebViewWarn(true);
      return;
    }
    // Preserve the destination (next param) so AuthCallback can route back.
    const params = new URLSearchParams(location.search);
    const next = params.get("next") || "/";
    const redirectUrl = `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const escapeUrl = window.location.href;
  const [copied, setCopied] = useState(false);

  const handleEscape = () => {
    // Try a real popup first — most embedded webviews surface this as
    // a native "Open in Safari / Open in Chrome" system prompt instead
    // of trying to handle a custom URL scheme themselves. The previous
    // approach used `x-safari-https://` which Apple has restricted in
    // iOS 14+ — the user reported a "Failed to load" page when their
    // webview tried to navigate to that scheme directly.
    const res = openInSystemBrowser(escapeUrl);
    if (!res.attempted) {
      toast.error(
        "Couldn't open a new tab. Tap the share icon (↑) at the top, then 'Open in Safari'.",
        { duration: 8000 },
      );
    }
  };

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(escapeUrl);
      setCopied(true);
      toast.success("Link copied. Now open Safari or Chrome and paste.");
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Some webviews (including Emergent's own preview viewer) block
      // clipboard access for security. Fall back to a prompt the user
      // can long-press and copy from.
      try {
        // eslint-disable-next-line no-alert
        window.prompt("Long-press to select, then Copy:", escapeUrl);
      } catch {
        toast.error("Long-press the URL below and choose Copy.");
      }
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-950 via-slate-900 to-amber-950/40 px-4 py-12 relative overflow-hidden">
      {/* subtle grain / glow */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.06]" style={{
        backgroundImage: "radial-gradient(circle at 20% 20%, #fbbf24 0px, transparent 600px), radial-gradient(circle at 80% 80%, #ef4444 0px, transparent 600px)"
      }} />

      <div className="relative w-full max-w-xl">
        <div className="rounded-3xl border border-slate-700/60 bg-slate-900/80 backdrop-blur-xl shadow-2xl p-10 md:p-12">
          {/* Logos */}
          <div className="flex items-center justify-center gap-6 md:gap-8 mb-10" data-testid="login-logos">
            <div className="rounded-2xl bg-[#f5efe4] px-4 py-3 shadow-md ring-1 ring-black/5">
              <img
                src="/images/in-the-weeds-collective-logo.png"
                alt="In the Weeds Collective"
                className="h-20 md:h-24 w-auto object-contain"
              />
            </div>

            <div className="text-slate-600 font-light text-2xl select-none" aria-hidden>
              ×
            </div>

            <div className="rounded-2xl bg-white px-3 py-2 shadow-md ring-1 ring-black/5">
              <img
                src="/images/itw-collective-badge.png"
                alt="In the Weeds Collective badge"
                className="h-20 md:h-24 w-auto object-contain"
              />
            </div>
          </div>

          <div className="text-center mb-8">
            <h1 className="text-2xl md:text-3xl font-bold text-white tracking-tight">
              Eatery Performance Reports
            </h1>
            <p className="mt-2 text-sm text-slate-400">
              Sign in to manage snapshots, scores, and uploads.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Public ranking pages stay viewable without an account.
            </p>
          </div>

          <button
            data-testid="google-signin-btn"
            onClick={handleSignIn}
            className="w-full flex items-center justify-center gap-3 rounded-full bg-white text-slate-900 font-semibold py-3.5 px-6 hover:bg-slate-100 active:scale-[0.99] transition-all shadow-lg"
          >
            <GoogleMark />
            <span>Sign in with Google</span>
          </button>

          {/* In-app webview warning: Google refuses OAuth from FB / IG /
              SFSafariViewController / Emergent's preview viewer etc.
              Without this, the user hits a "disallowed_useragent" or
              "Failed to load" error. iOS deep-link schemes proved
              unreliable in v1 — Copy-Link is now the primary path,
              with the system share-sheet as the explicit fallback. */}
          {showWebViewWarn && (
            <div
              data-testid="webview-warning"
              className="mt-5 rounded-2xl border border-amber-500/40 bg-amber-950/30 p-4 text-left"
            >
              <div className="flex items-start gap-3 mb-3">
                <AlertTriangle className="w-5 h-5 text-amber-300 mt-0.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-amber-100">
                    You're inside {webview.vendor || "an in-app browser"}.
                  </p>
                  <p className="text-xs text-amber-200/80 mt-1 leading-relaxed">
                    Google blocks sign-in from here. Use one of the two paths below to
                    open this page in {webview.isIOS ? "Safari" : webview.isAndroid ? "Chrome" : "your real browser"} and sign in there.
                  </p>
                </div>
              </div>

              {/* Path A — primary, most reliable */}
              <div className="rounded-xl bg-slate-900/60 border border-amber-500/30 p-3 mb-2">
                <div className="text-[10.5px] uppercase tracking-wider text-amber-300/80 font-semibold mb-1.5">
                  Path A · Copy + paste (most reliable)
                </div>
                <button
                  data-testid="webview-copy-link-btn"
                  onClick={handleCopyLink}
                  className="w-full inline-flex items-center justify-center gap-2 rounded-full bg-amber-400 text-amber-950 text-sm font-bold py-3 px-4 hover:bg-amber-300 active:scale-[0.99] transition-all"
                >
                  {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                  {copied ? "Copied — now open Safari" : "Copy login link"}
                </button>
                <p className="text-[11px] text-amber-200/70 mt-2 leading-relaxed">
                  After tapping, open <b>{webview.isIOS ? "Safari" : webview.isAndroid ? "Chrome" : "your browser"}</b>, paste into the address bar, and sign in.
                </p>
              </div>

              {/* Path B — iOS-specific share-sheet hint */}
              {webview.isIOS && (
                <div className="rounded-xl bg-slate-900/40 border border-slate-700 p-3 mb-2">
                  <div className="text-[10.5px] uppercase tracking-wider text-slate-300/80 font-semibold mb-1.5 flex items-center gap-1.5">
                    <Share2 className="w-3 h-3" />
                    Path B · Use the share menu
                  </div>
                  <p className="text-[11.5px] text-slate-200 leading-relaxed">
                    Tap the <b>share icon (↑)</b> at the top of this preview, then choose
                    <b> "Open in Safari"</b> from the system menu. That opens this exact
                    page in real Safari where Google sign-in will work.
                  </p>
                </div>
              )}

              {/* Path C — best-effort programmatic, kept as a fallback. */}
              <button
                data-testid="webview-open-external-btn"
                onClick={handleEscape}
                className="w-full inline-flex items-center justify-center gap-2 rounded-full border border-slate-600 text-slate-200 text-xs font-medium py-2 px-4 hover:bg-slate-800 transition-all"
              >
                Or try: open in a new tab
              </button>

              {/* Always show the URL so the user can long-press → Copy as a manual fallback. */}
              <p className="text-[10.5px] text-amber-300/60 mt-3 font-mono break-all leading-tight select-all">
                {escapeUrl}
              </p>
            </div>
          )}

          <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-500">
            <LogIn className="w-3.5 h-3.5" />
            <span>Only whitelisted accounts can edit data.</span>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-slate-600">
          © {new Date().getFullYear()} In the Weeds Collective · Eatery Reports
        </p>
      </div>
    </div>
  );
}

function GoogleMark() {
  return (
    <svg className="w-5 h-5" viewBox="0 0 24 24" aria-hidden="true">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.99.66-2.25 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A10.99 10.99 0 0 0 12 23z"/>
      <path fill="#FBBC05" d="M5.84 14.1A6.6 6.6 0 0 1 5.5 12c0-.73.13-1.44.34-2.1V7.07H2.18A10.99 10.99 0 0 0 1 12c0 1.78.43 3.46 1.18 4.94l3.66-2.84z"/>
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.07.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"/>
    </svg>
  );
}
