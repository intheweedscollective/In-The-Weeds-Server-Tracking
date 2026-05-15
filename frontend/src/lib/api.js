import axios from "axios";
import { toast } from "sonner";

// Strip any trailing slash from REACT_APP_BACKEND_URL — production env vars
// occasionally drift to "https://app.example.com/" (with slash) which would
// otherwise make every API URL "//api/..." (double slash). Cloudflare/ingress
// treat "//api/..." as a frontend route and serve index.html, so the browser
// blows up with "Unexpected token '<'" on every fetch. Defensive normalize.
const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

// Create axios instance with cache-busting headers and credentials so the
// httpOnly session_token cookie set by /api/auth/session is sent on every
// API call. withCredentials=true is REQUIRED for cookie-based auth across
// the *.preview.emergentagent.com / *.emergent.host origins.
const api = axios.create({
  baseURL: `${BACKEND_URL}/api`,
  withCredentials: true,
  headers: {
    'Cache-Control': 'no-cache, no-store, must-revalidate',
    'Pragma': 'no-cache',
    'Expires': '0'
  }
});

// Add cache-busting timestamp to all GET requests
api.interceptors.request.use((config) => {
  if (config.method === 'get') {
    config.params = {
      ...config.params,
      _t: Date.now()
    };
  }
  return config;
});

// Response interceptor — surface auth errors clearly. 401 means "not signed
// in", 403 means "signed in but not on the whitelist". For mutations we
// toast and bounce the user to /login (preserving where they were).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const method = (error.config?.method || "get").toLowerCase();
    const isMutation = method !== "get";
    if (status === 401 && isMutation) {
      toast.error("Sign in required to make changes.");
      // Bounce to /login but only if we're not already there.
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        const next = window.location.pathname + window.location.search;
        window.location.href = `/login?next=${encodeURIComponent(next)}`;
      }
    } else if (status === 403 && isMutation) {
      toast.error(error.response?.data?.detail || "You're not authorized to make changes.");
    } else {
      console.error('API Error:', status, error.message);
    }
    return Promise.reject(error);
  }
);

export default api;
export { BACKEND_URL };
