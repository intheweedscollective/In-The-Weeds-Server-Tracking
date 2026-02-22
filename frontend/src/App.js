import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { SidebarLayout } from "./components/SidebarLayout";
import Dashboard from "./pages/Dashboard";
import EmployeeList from "./pages/EmployeeList";
import ReviewGeneration from "./pages/ReviewGeneration";
import ReviewTracker from "./pages/ReviewTracker";
import Analytics from "./pages/Analytics";
import QuarterSettings from "./pages/QuarterSettings";
import FullRankings from "./pages/FullRankings";
import YodeckSlides from "./pages/YodeckSlides";
import Snapshots from "./pages/Snapshots";
import HelpCenter from "./pages/HelpCenter";
import PalettePreview from "./pages/PalettePreview";
import OnboardingGuide from "./components/OnboardingGuide";
import "./App.css";

function App() {
  return (
    <div className="min-h-screen bg-background">
      <BrowserRouter>
        <Routes>
          {/* Palette preview without sidebar */}
          <Route path="/palette-preview" element={<PalettePreview />} />
          
          {/* Main app with sidebar */}
          <Route path="/*" element={
            <SidebarLayout>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/rankings" element={<FullRankings />} />
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
          } />
        </Routes>
        <OnboardingGuide />
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </div>
  );
}

export default App;