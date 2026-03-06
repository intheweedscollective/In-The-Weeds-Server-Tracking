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
import YodeckSlides from "./pages/YodeckSlides";
import Snapshots from "./pages/Snapshots";
import HelpCenter from "./pages/HelpCenter";
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
              <Route path="/rankings" element={<FullRankings />} />
              <Route path="/leaderboard" element={<LeaderboardRankings />} />
              <Route path="/employees" element={<EmployeeList />} />
              <Route path="/reviews" element={<ReviewGeneration />} />
              <Route path="/review-tracker" element={<ReviewTracker />} />
              <Route path="/yodeck" element={<YodeckSlides />} />
              <Route path="/snapshots" element={<Snapshots />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/settings" element={<QuarterSettings />} />
              <Route path="/help" element={<HelpCenter />} />
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