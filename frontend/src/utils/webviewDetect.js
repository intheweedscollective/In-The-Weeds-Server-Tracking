/**
 * Detect whether the current page is being rendered inside a known
 * in-app browser ("webview"). Google strictly blocks OAuth from these
 * environments — the user sees a cryptic 403 `disallowed_useragent`
 * page after tapping "Sign in with Google". The only fix is to bounce
 * them into their real Safari / Chrome before they ever see the
 * Google sign-in screen.
 *
 * Returns `{ isWebView, vendor, isIOS, isAndroid, ua }`.
 *
 * Heuristics (battle-tested against real production UAs):
 *   • iOS: `iPhone|iPad|iPod` present AND `Safari/` token MISSING
 *     (real iOS Safari always sends `Safari/` somewhere in the UA;
 *     SFSafariViewController and WKWebView strip it). Also flags
 *     known apps by their app-specific tokens (Facebook FBAN/FBAV,
 *     Instagram, LinkedIn, Line, TikTok, KakaoTalk, etc.).
 *   • Android: presence of `; wv)` token (the official "I am a
 *     WebView" marker Google requires every Chrome-based webview to
 *     emit), OR matches a specific in-app browser token.
 */
const KNOWN_WEBVIEW_TOKENS = [
  { vendor: "Facebook", re: /\b(FBAN|FBAV|FB_IAB|FBIOS)\b/i },
  { vendor: "Messenger", re: /\bMessenger\b/i },
  { vendor: "Instagram", re: /\bInstagram\b/i },
  { vendor: "LinkedIn", re: /\bLinkedIn(App)?\b/i },
  { vendor: "Line", re: /\bLine\//i },
  { vendor: "TikTok", re: /\b(BytedanceWebview|musical_ly|TikTok)\b/i },
  { vendor: "KakaoTalk", re: /\bKAKAOTALK\b/i },
  { vendor: "WeChat", re: /\bMicroMessenger\b/i },
  { vendor: "Twitter / X", re: /\bTwitter\b/i },
  { vendor: "Snapchat", re: /\bSnapchat\b/i },
  { vendor: "Pinterest", re: /\bPinterest\b/i },
  { vendor: "Slack", re: /\bSlack\b/i },
  // Emergent's own preview viewer renders inside a wrapped webview
  // when opened from the platform's mobile app. We don't currently
  // detect this by UA — there isn't a reliable token — but we DO
  // flag it heuristically via the iOS generic check below.
];

/**
 * Best-effort "open this URL in the real browser" launcher. iOS deep
 * links like `x-safari-https://` were unreliable from iOS 14 onward
 * and now flat-out fail inside many embedded webviews (including
 * Emergent's own preview app — the user hit a "Failed to load" page).
 *
 * Modern approach: try in this order, stopping on first success:
 *   1. window.open(href, '_blank', 'noopener,noreferrer')
 *      Most webviews surface this as a system "Open in…" prompt.
 *   2. window.open() with no target — last-ditch.
 *
 * No more custom-scheme URIs by default. We return a status object so
 * the UI can advise the user to use the share-sheet if the popup
 * approach doesn't navigate them out.
 */
export function openInSystemBrowser(href) {
  if (typeof window === "undefined" || !href) {
    return { attempted: false, method: null };
  }
  try {
    const w = window.open(href, "_blank", "noopener,noreferrer");
    if (w) return { attempted: true, method: "window.open(_blank)" };
  } catch { /* fall through */ }
  try {
    window.open(href);
    return { attempted: true, method: "window.open()" };
  } catch { /* fall through */ }
  return { attempted: false, method: null };
}

export function detectWebView() {
  const ua = (typeof navigator !== "undefined" ? navigator.userAgent : "") || "";
  const isIOS = /iPhone|iPad|iPod/i.test(ua);
  const isAndroid = /Android/i.test(ua);

  // Match against the explicit vendor list first — gives us a friendly
  // name for the warning copy ("You're inside Instagram's browser…").
  for (const { vendor, re } of KNOWN_WEBVIEW_TOKENS) {
    if (re.test(ua)) {
      return { isWebView: true, vendor, isIOS, isAndroid, ua };
    }
  }

  // Generic heuristics.
  if (isIOS) {
    // Real iOS Safari always has "Safari/" in the UA. SFSafariViewController
    // and WKWebView don't. The exception: Chrome on iOS has "CriOS" + "Safari/".
    const hasSafariToken = /\bSafari\//i.test(ua);
    const hasChromeIOS = /\bCriOS\b/i.test(ua);
    const hasFirefoxIOS = /\bFxiOS\b/i.test(ua);
    const hasEdgeIOS = /\bEdgiOS\b/i.test(ua);
    if (!hasSafariToken && !hasChromeIOS && !hasFirefoxIOS && !hasEdgeIOS) {
      return { isWebView: true, vendor: "iOS in-app browser", isIOS, isAndroid, ua };
    }
  }

  if (isAndroid) {
    // The `; wv)` token is the official Android WebView marker.
    if (/;\s*wv\)/i.test(ua)) {
      return { isWebView: true, vendor: "Android WebView", isIOS, isAndroid, ua };
    }
  }

  return { isWebView: false, vendor: null, isIOS, isAndroid, ua };
}

/**
 * Build the best "open in real browser" URL we can given the platform.
 *   - iOS Safari supports `x-safari-https://...` to force-open in Safari.
 *   - Android Chrome supports the `intent://...#Intent;scheme=https;...`
 *     URI. Most webviews honour this and bounce out to Chrome.
 *   - Falls back to the raw URL otherwise.
 */
export function buildEscapeUrl(currentHref, { isIOS, isAndroid } = {}) {
  if (!currentHref) return currentHref;
  if (isIOS) {
    // strip scheme so x-safari-https:// can wrap it.
    return currentHref.replace(/^https?:\/\//i, "x-safari-https://");
  }
  if (isAndroid) {
    const stripped = currentHref.replace(/^https?:\/\//i, "");
    return (
      `intent://${stripped}#Intent;scheme=https;` +
      `package=com.android.chrome;end`
    );
  }
  return currentHref;
}
