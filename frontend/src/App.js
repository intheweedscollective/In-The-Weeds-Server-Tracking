import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ThemeProvider } from "./context/ThemeContext";
import { AuthProvider } from "./context/AuthContext";
import { StoreProvider } from "./contexts/StoreContext";
import { SidebarLayout } from "./components/SidebarLayout";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import EmployeeList from "./pages/EmployeeList";
import ReviewGeneration from "./pages/ReviewGeneration";
import ReviewTracker from "./pages/ReviewTracker";
import Analytics from "./pages/Analytics";
import QuarterSettings from "./pages/QuarterSettings";
import FullRankings from "./pages/FullRankings";
import LeaderboardRankings from "./pages/LeaderboardRankings";
import DataIntegrity from "./pages/DataIntegrity";
import ScoringAudit from "./pages/ScoringAudit";
import YodeckSlides from "./pages/YodeckSlides";
import Snapshots from "./pages/Snapshots";
import HelpCenter from "./pages/HelpCenter";
import DataUploads from "./pages/DataUploads";
import Reports from "./pages/Reports";
import QRDashboard from "./pages/QRDashboard";
import QRLeaderboard from "./pages/QRLeaderboard";
import QRDailyClicks from "./pages/QRDailyClicks";
import QREmployees from "./pages/QREmployees";
import QRSettings from "./pages/QRSettings";
import QRGhostHeal from "./pages/QRGhostHeal";
import StoreManagement from "./pages/StoreManagement";
import StoreLeaderboard from "./pages/StoreLeaderboard";
import StoreDetails from "./pages/StoreDetails";
import GlobalOverview from "./pages/GlobalOverview";
import CVAdjustment from "./pages/CVAdjustment";
import ScoringGuide from "./pages/ScoringGuide";
import DataUploadTutorial from "./pages/DataUploadTutorial";
import SnapshotWorkflow from "./pages/SnapshotWorkflow";
import SnapshotDetail from "./pages/SnapshotDetail";
import QuarterlySummary from "./pages/QuarterlySummary";
import DataReconciliation from "./pages/DataReconciliation";
import QRRecovery from "./pages/QRRecovery";
import OnboardingGuide from "./components/OnboardingGuide";
import ProtectedAdminRoute from "./components/ProtectedAdminRoute";
import ErrorBoundary from "./components/ErrorBoundary";
import "./App.css";

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <StoreProvider>
          <div className="min-h-screen bg-background">
            <BrowserRouter>
              <Routes>
                {/* Auth routes — outside the sidebar layout */}
                <Route path="/login" element={<Login />} />
                <Route path="/auth/callback" element={<AuthCallback />} />
                {/* Everything else uses the standard app shell */}
                <Route
                  path="/*"
                  element={
                    <ErrorBoundary>
                      <SidebarLayout>
                        <Routes>
                          <Route path="/" element={<Dashboard />} />
                          <Route path="/uploads" element={<ProtectedAdminRoute><DataUploads /></ProtectedAdminRoute>} />
                          <Route path="/data-uploads" element={<ProtectedAdminRoute><DataUploads /></ProtectedAdminRoute>} />
                          <Route path="/rankings" element={<FullRankings />} />
                          <Route path="/leaderboard" element={<LeaderboardRankings />} />
                          <Route path="/employees" element={<ProtectedAdminRoute><EmployeeList /></ProtectedAdminRoute>} />
                          <Route path="/reviews" element={<ReviewGeneration />} />
                          <Route path="/review-tracker" element={<ReviewTracker />} />
                          <Route path="/yodeck" element={<YodeckSlides />} />
                          <Route path="/snapshots" element={<Snapshots />} />
                          <Route path="/analytics" element={<Analytics />} />
                          <Route path="/settings" element={<ProtectedAdminRoute><QuarterSettings /></ProtectedAdminRoute>} />
                          <Route path="/data-integrity" element={<ProtectedAdminRoute><DataIntegrity /></ProtectedAdminRoute>} />
                          <Route path="/data-reconciliation" element={<ProtectedAdminRoute><DataReconciliation /></ProtectedAdminRoute>} />
                          <Route path="/scoring-audit" element={<ProtectedAdminRoute><ScoringAudit /></ProtectedAdminRoute>} />
                          <Route path="/cv-adjustment" element={<ProtectedAdminRoute><CVAdjustment /></ProtectedAdminRoute>} />
                          <Route path="/scoring-guide" element={<ScoringGuide />} />
                          <Route path="/upload-tutorial" element={<DataUploadTutorial />} />
                          <Route path="/help" element={<HelpCenter />} />
                          <Route path="/reports" element={<Reports />} />
                          <Route path="/quarterly-summary" element={<QuarterlySummary />} />
                          {/* QR Track Hub - Isolated Module */}
                          <Route path="/qr" element={<QRDashboard />} />
                          <Route path="/qr/leaderboard" element={<QRLeaderboard />} />
                          <Route path="/qr/daily" element={<QRDailyClicks />} />
                          <Route path="/qr/codes" element={<ProtectedAdminRoute><QREmployees /></ProtectedAdminRoute>} />
                          <Route path="/qr/settings" element={<ProtectedAdminRoute><QRSettings /></ProtectedAdminRoute>} />
                          <Route path="/qr/ghost-heal" element={<ProtectedAdminRoute><QRGhostHeal /></ProtectedAdminRoute>} />
                          <Route path="/qr/recovery" element={<ProtectedAdminRoute><QRRecovery /></ProtectedAdminRoute>} />
                          {/* Multi-Store Management */}
                          <Route path="/global" element={<GlobalOverview />} />
                          <Route path="/stores" element={<ProtectedAdminRoute><StoreManagement /></ProtectedAdminRoute>} />
                          <Route path="/stores/leaderboard" element={<StoreLeaderboard />} />
                          <Route path="/stores/:storeId" element={<StoreDetails />} />
                          {/* Snapshot Workflow */}
                          <Route path="/snapshot-workflow" element={<ProtectedAdminRoute><SnapshotWorkflow /></ProtectedAdminRoute>} />
                          <Route path="/snapshot-workflow/:snapshotId" element={<ProtectedAdminRoute><SnapshotDetail /></ProtectedAdminRoute>} />
                        </Routes>
                        <OnboardingGuide />
                      </SidebarLayout>
                    </ErrorBoundary>
                  }
                />
              </Routes>
            </BrowserRouter>
            <Toaster position="top-right" richColors />
          </div>
        </StoreProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;