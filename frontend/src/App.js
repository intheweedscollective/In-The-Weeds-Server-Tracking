import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Dashboard from "./pages/Dashboard";
import EmployeeList from "./pages/EmployeeList";
import ReviewGeneration from "./pages/ReviewGeneration";
import Analytics from "./pages/Analytics";
import QuarterSettings from "./pages/QuarterSettings";
import FullRankings from "./pages/FullRankings";
import YodeckSlides from "./pages/YodeckSlides";
import Snapshots from "./pages/Snapshots";
import OnboardingGuide from "./components/OnboardingGuide";
import "./App.css";

function App() {
  return (
    <div className="min-h-screen bg-background">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/rankings" element={<FullRankings />} />
          <Route path="/employees" element={<EmployeeList />} />
          <Route path="/reviews" element={<ReviewGeneration />} />
          <Route path="/yodeck" element={<YodeckSlides />} />
          <Route path="/snapshots" element={<Snapshots />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/settings" element={<QuarterSettings />} />
        </Routes>
        <OnboardingGuide />
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </div>
  );
}

export default App;