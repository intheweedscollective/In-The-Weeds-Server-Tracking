import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Dashboard from "./pages/Dashboard";
import EmployeeList from "./pages/EmployeeList";
import ReviewGeneration from "./pages/ReviewGeneration";
import TopPerformers from "./pages/TopPerformers";
import Analytics from "./pages/Analytics";
import "./App.css";

function App() {
  return (
    <div className="min-h-screen bg-paper-bg">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/employees" element={<EmployeeList />} />
          <Route path="/reviews" element={<ReviewGeneration />} />
          <Route path="/top-performers" element={<TopPerformers />} />
          <Route path="/analytics" element={<Analytics />} />
        </Routes>
      </BrowserRouter>
      <Toaster position="top-right" richColors />
    </div>
  );
}

export default App;