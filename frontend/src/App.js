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
import OnboardingGuide from "./components/OnboardingGuide";
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
                    <SidebarLayout>
                      <Routes>
                        <Route path="/" element={<Dashboard />} />
                        <Route path="/uploads" element={<DataUploads />} />
                        <Route path="/data-uploads" element={<DataUploads />} />
                        <Route path="/rankings" element={<FullRankings />} />
                        <Route path="/leaderboard" element={<LeaderboardRankings />} />
                        <Route path="/employees" element={<EmployeeList />} />
                        <Route path="/reviews" element={<ReviewGeneration />} />
                        <Route path="/review-tracker" element={<ReviewTracker />} />
                        <Route path="/yodeck" element={<YodeckSlides />} />
                        <Route path="/snapshots" element={<Snapshots />} />
                        <Route path="/analytics" element={<Analytics />} />
                        <Route path="/settings" element={<QuarterSettings />} />
                        <Route path="/data-integrity" element={<DataIntegrity />} />
                        <Route path="/scoring-audit" element={<ScoringAudit />} />
                        <Route path="/cv-adjustment" element={<CVAdjustment />} />
                        <Route path="/scoring-guide" element={<ScoringGuide />} />
                        <Route path="/upload-tutorial" element={<DataUploadTutorial />} />
                        <Route path="/help" element={<HelpCenter />} />
                        <Route path="/reports" element={<Reports />} />
                        <Route path="/quarterly-summary" element={<QuarterlySummary />} />
                        {/* QR Track Hub - Isolated Module */}
                        <Route path="/qr" element={<QRDashboard />} />
                        <Route path="/qr/leaderboard" element={<QRLeaderboard />} />
                        <Route path="/qr/codes" element={<QREmployees />} />
                        <Route path="/qr/settings" element={<QRSettings />} />
                        <Route path="/qr/ghost-heal" element={<QRGhostHeal />} />
                        {/* Multi-Store Management */}
                        <Route path="/global" element={<GlobalOverview />} />
                        <Route path="/stores" element={<StoreManagement />} />
                        <Route path="/stores/leaderboard" element={<StoreLeaderboard />} />
                        <Route path="/stores/:storeId" element={<StoreDetails />} />
                        {/* Snapshot Workflow */}
                        <Route path="/snapshot-workflow" element={<SnapshotWorkflow />} />
                        <Route path="/snapshot-workflow/:snapshotId" element={<SnapshotDetail />} />
                      </Routes>
                      <OnboardingGuide />
                    </SidebarLayout>
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