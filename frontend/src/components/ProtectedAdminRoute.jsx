import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { ShieldOff } from "lucide-react";

/**
 * ProtectedAdminRoute
 *
 * Wraps any admin-only page. Behavior:
 *   • Auth still loading  → spinner placeholder
 *   • No session          → redirect to /login
 *   • Signed in, not admin → "Access Denied" screen with link back to /
 *   • Admin               → render children
 *
 * Use:
 *   <Route path="/uploads" element={
 *     <ProtectedAdminRoute><DataUploads /></ProtectedAdminRoute>
 *   } />
 */
export default function ProtectedAdminRoute({ children }) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div
        className="flex items-center justify-center min-h-[40vh] text-slate-400 text-sm"
        data-testid="admin-route-loading"
      >
        Checking access…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!user.is_admin) {
    return (
      <div
        className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center"
        data-testid="admin-route-access-denied"
      >
        <ShieldOff className="w-12 h-12 text-rose-500 mb-4" />
        <h1 className="text-2xl font-semibold text-white mb-2">
          Admin access required
        </h1>
        <p className="text-slate-400 max-w-md mb-6">
          This page is only available to administrators. You're signed in as{" "}
          <span className="text-slate-200">{user.email || user.name}</span>.
          Contact the owner to be added to the admin list.
        </p>
        <a
          href="/"
          className="px-4 py-2 rounded-md bg-emerald-700 hover:bg-emerald-600 text-white text-sm"
          data-testid="admin-route-back-to-dashboard"
        >
          Back to Dashboard
        </a>
      </div>
    );
  }

  return children;
}
