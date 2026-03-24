import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { ThemeProvider } from "./context/ThemeContext";
import { SidebarLayout } from "./components/SidebarLayout";
import Dashboard from "./pages/Dashboard";
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
import StoreManagement from "./pages/StoreManagement";
import StoreLeaderboard from "./pages/StoreLeaderboard";
import StoreDetails from "./pages/StoreDetails";
import CVAdjustment from "./pages/CVAdjustment";
import ScoringGuide from "./pages/ScoringGuide";
import OnboardingGuide from "./components/OnboardingGuide";
import "./App.css";

function App() {
  return (
    <ThemeProvider>
      <div className="min-h-screen bg-background">
        <BrowserRouter>
          <SidebarLayout>
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/uploads" element={<DataUploads />} />
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
              <Route path="/help" element={<HelpCenter />} />
              <Route path="/reports" element={<Reports />} />
              {/* QR Track Hub - Isolated Module */}
              <Route path="/qr" element={<QRDashboard />} />
              <Route path="/qr/leaderboard" element={<QRLeaderboard />} />
              <Route path="/qr/codes" element={<QREmployees />} />
              <Route path="/qr/settings" element={<QRSettings />} />
              {/* Multi-Store Management */}
              <Route path="/stores" element={<StoreManagement />} />
              <Route path="/stores/leaderboard" element={<StoreLeaderboard />} />
              <Route path="/stores/:storeId" element={<StoreDetails />} />
            </Routes>
          </SidebarLayout>
          <OnboardingGuide />
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </div>
    </ThemeProvider>
  );
}

export default App;