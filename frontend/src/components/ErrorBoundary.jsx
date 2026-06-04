import React from "react";
import { AlertTriangle } from "lucide-react";

/**
 * ErrorBoundary
 *
 * Wraps the main app route area so one broken page does not blank-screen
 * the demo. On any render-time exception:
 *   • The exception is logged to the browser console (so devtools still works).
 *   • A clean fallback UI is shown with "Refresh" and "Back to Dashboard" links.
 *
 * Usage in App.js:
 *   <ErrorBoundary>
 *     <SidebarLayout>
 *       <Routes>...</Routes>
 *     </SidebarLayout>
 *   </ErrorBoundary>
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // Surface to console so devtools / sentry can still see it.

    console.error("[ErrorBoundary] Render-time crash:", error, info);
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div
        className="flex flex-col items-center justify-center min-h-[70vh] px-6 text-center bg-slate-950 text-slate-200"
        data-testid="error-boundary-fallback"
      >
        <AlertTriangle className="w-14 h-14 text-amber-400 mb-4" />
        <h1 className="text-2xl font-semibold text-white mb-2">
          Something went wrong loading this page.
        </h1>
        <p className="text-slate-400 max-w-md mb-6">
          The rest of the app is still running. Refresh this page or head
          back to the dashboard.
        </p>
        <div className="flex flex-col sm:flex-row gap-3">
          <button
            type="button"
            onClick={() => {
              this.handleReset();
              window.location.reload();
            }}
            className="px-4 py-2 rounded-md bg-slate-700 hover:bg-slate-600 text-white text-sm"
            data-testid="error-boundary-refresh"
          >
            Refresh page
          </button>
          <a
            href="/"
            onClick={this.handleReset}
            className="px-4 py-2 rounded-md bg-emerald-700 hover:bg-emerald-600 text-white text-sm"
            data-testid="error-boundary-back"
          >
            Back to Dashboard
          </a>
        </div>
        {this.state.error && (
          <details className="mt-6 text-xs text-slate-500 max-w-lg">
            <summary className="cursor-pointer">Error details</summary>
            <pre className="mt-2 text-left whitespace-pre-wrap break-words">
              {String(this.state.error?.message || this.state.error)}
            </pre>
          </details>
        )}
      </div>
    );
  }
}
