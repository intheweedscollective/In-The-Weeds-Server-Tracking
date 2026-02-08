import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { Users, FileText, TrendingUp, Award, Target, Fish, Settings, Camera, Download, X, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import StatsCard from "../components/StatsCard";
import { formatNumber } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [employees, setEmployees] = useState([]);
  
  // Quarter selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [quarterSettings, setQuarterSettings] = useState(null);
  const [latestSnapshot, setLatestSnapshot] = useState(null);
  
  // Modal states
  const [showTopPerformers, setShowTopPerformers] = useState(false);
  const [showUnderPerformers, setShowUnderPerformers] = useState(false);

  const [stats, setStats] = useState({
    totalEmployees: 0,
    avgTotalScore: 0,
    topPerformers: 0,
    underPerformers: 0
  });

  const calculateStats = useCallback(() => {
    const total = employees.length;
    const avgScore = total > 0 ? employees.reduce((sum, emp) => sum + (emp.total_score || 0), 0) / total : 0;
    
    // Get thresholds from settings
    const aServerThreshold = quarterSettings?.a_server_min_score || 80;
    const bServerThreshold = quarterSettings?.b_server_min_score || 70;
    
    // Top performers: score >= A-Server threshold
    const topPerformers = employees.filter(emp => (emp.total_score || 0) >= aServerThreshold).length;
    
    // Under performers: score < B-Server threshold (C-Servers)
    const underPerformers = employees.filter(emp => {
      const score = emp.total_score || 0;
      const jobTitle = (emp.job_title || '').toLowerCase();
      // Only count servers as under performers (not trainers/bartenders)
      return score < bServerThreshold && jobTitle === 'server';
    }).length;

    setStats({
      totalEmployees: total,
      avgTotalScore: avgScore.toFixed(1),
      topPerformers,
      underPerformers
    });
  }, [employees, quarterSettings]);

  const fetchQuarterSettings = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
      setQuarterSettings(response.data);
    } catch (error) {
      if (error.response?.status === 404) {
        setQuarterSettings(null);
      }
    }
  }, [selectedYear, selectedQuarter]);

  const fetchEmployeesForQuarter = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      // Sort by total_score descending for display
      const sorted = (response.data || []).sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
      setEmployees(sorted);
    } catch (error) {
      console.error("Error fetching employees:", error);
    }
  }, [selectedYear, selectedQuarter]);

  const fetchLatestSnapshot = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/snapshots?year=${selectedYear}`);
      const snapshots = response.data.filter(s => s.quarter === selectedQuarter);
      if (snapshots.length > 0) {
        // Get most recent snapshot
        setLatestSnapshot(snapshots[0]);
      } else {
        setLatestSnapshot(null);
      }
    } catch (error) {
      console.error("Error fetching snapshots:", error);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchQuarterSettings();
    fetchEmployeesForQuarter();
    fetchLatestSnapshot();
  }, [fetchQuarterSettings, fetchEmployeesForQuarter, fetchLatestSnapshot]);

  useEffect(() => {
    calculateStats();
  }, [employees, calculateStats]);

  const downloadTemplate = () => {
    window.open(`${API}/v2/template`, '_blank');
    toast.success("Template downloaded!");
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Decorative splashes */}
      <div className="splash-red" style={{ top: '8%', right: '3%' }} />
      <div className="splash-blue" style={{ top: '20%', left: '2%' }} />
      <div className="splash-red" style={{ bottom: '15%', left: '5%', opacity: 0.4 }} />
      <div className="splash-blue" style={{ bottom: '8%', right: '8%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-5 mb-4">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump Logo" 
              className="w-24 h-24 rounded-full shadow-xl border-4 border-white"
              data-testid="bubba-gump-logo"
            />
            <div className="text-left">
              <h1 className="text-4xl md:text-5xl font-serif font-black text-primary tracking-tight" data-testid="main-title">
                Performance Hub
              </h1>
              <p className="text-lg text-secondary font-medium italic" data-testid="main-subtitle">
                {selectedQuarter} {selectedYear} • Quarterly Crew Reviews
              </p>
            </div>
          </div>
        </div>

        {/* Quarter Selector */}
        <div className="flex justify-center gap-4 mb-8">
          <div className="flex items-center gap-2 bg-white rounded-lg shadow-sm border px-4 py-2">
            <label className="text-sm font-medium text-gray-600">Year:</label>
            <select
              className="bg-transparent font-semibold text-primary focus:outline-none"
              value={selectedYear}
              onChange={(e) => setSelectedYear(parseInt(e.target.value))}
            >
              <option value={2025}>2025</option>
              <option value={2026}>2026</option>
              <option value={2027}>2027</option>
            </select>
          </div>
          <div className="flex items-center gap-2 bg-white rounded-lg shadow-sm border px-4 py-2">
            <label className="text-sm font-medium text-gray-600">Quarter:</label>
            <select
              className="bg-transparent font-semibold text-primary focus:outline-none"
              value={selectedQuarter}
              onChange={(e) => setSelectedQuarter(e.target.value)}
            >
              <option value="Q1">Q1</option>
              <option value="Q2">Q2</option>
              <option value="Q3">Q3</option>
              <option value="Q4">Q4</option>
            </select>
          </div>
        </div>

        {/* Stats Dashboard */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-10" data-testid="stats-dashboard">
          <StatsCard 
            icon={Users}
            title="Crew Members"
            value={stats.totalEmployees}
            color="bg-blue-500"
            testId="total-employees-card"
          />
          <StatsCard 
            icon={TrendingUp}
            title="Avg Score"
            value={stats.avgTotalScore}
            color="bg-green-500"
            testId="avg-score-card"
            linkTo="/analytics"
          />
          <StatsCard 
            icon={Award}
            title="A-Servers"
            value={stats.aServers}
            color="bg-yellow-500"
            testId="a-servers-card"
            linkTo="/rankings"
          />
          <StatsCard 
            icon={Target}
            title="Top Performers"
            value={stats.topPerformers}
            color="bg-purple-500"
            testId="top-performers-card"
          />
        </div>

        {/* Main Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
          {/* Upload CTA - Points to Snapshots */}
          <div className="bubba-card" data-testid="upload-cta-card">
            <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-2deg)' }} />
            
            <div className="p-6 pt-8">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                  <Camera className="w-6 h-6 text-secondary" />
                </div>
                <div>
                  <h2 className="text-lg font-serif font-bold text-foreground">
                    Bi-Weekly Data Upload
                  </h2>
                  <p className="text-sm text-gray-500">
                    Upload on the 1st & 15th of each month
                  </p>
                </div>
              </div>

              {/* Latest Snapshot Info */}
              {latestSnapshot ? (
                <div className="mb-4 p-4 bg-green-50 border border-green-200 rounded-lg">
                  <div className="flex items-center gap-2 text-green-800 mb-1">
                    <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                    <span className="font-semibold text-sm">Latest Upload: {latestSnapshot.snapshot_date}</span>
                  </div>
                  <p className="text-green-700 text-sm">
                    {latestSnapshot.employee_count} employees • {latestSnapshot.title || 'Bi-weekly snapshot'}
                  </p>
                </div>
              ) : (
                <div className="mb-4 p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-yellow-800 text-sm font-medium">
                    No snapshots for {selectedQuarter} {selectedYear} yet
                  </p>
                </div>
              )}

              <Link to="/snapshots" className="block">
                <button className="bubba-btn-primary w-full flex items-center justify-center gap-2">
                  <Camera className="w-5 h-5" />
                  Go to Snapshots to Upload
                </button>
              </Link>

              <div className="mt-4 text-center">
                <button
                  onClick={downloadTemplate}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-semibold text-secondary hover:text-primary transition-colors"
                  data-testid="download-template-btn"
                >
                  <Download className="w-4 h-4" />
                  Download CSV Template
                </button>
              </div>

              {/* Info Box */}
              <div className="mt-4 p-3 bg-blue-50 rounded-lg text-xs text-blue-800">
                <strong>How it works:</strong> Upload your bi-weekly data via Snapshots. 
                This automatically updates Dashboard, Rankings, Reviews & Yodeck slides.
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bubba-card" data-testid="quick-actions-card">
            <div className="tape tape-red" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(2deg)' }} />
            
            <div className="p-6 pt-8">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
                  <FileText className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-serif font-bold text-foreground">
                    Quick Actions
                  </h2>
                  <p className="text-sm text-gray-500">
                    Manage your crew
                  </p>
                </div>
              </div>
              
              <div className="space-y-3">
                <Link to="/employees" className="block" data-testid="view-employees-link">
                  <button className="bubba-btn-primary w-full flex items-center justify-center gap-2">
                    <Users className="w-5 h-5" />
                    View All Crew
                  </button>
                </Link>
                
                <Link to="/reviews" className="block" data-testid="generate-reviews-link">
                  <button className="bubba-btn-secondary w-full flex items-center justify-center gap-2">
                    <FileText className="w-5 h-5" />
                    Generate Reviews
                  </button>
                </Link>

                <Link to="/rankings" className="block" data-testid="rankings-link">
                  <button className="w-full flex items-center justify-center gap-2 px-4 py-2 border-2 border-gray-300 text-gray-700 rounded-full font-semibold hover:bg-gray-50 transition-colors">
                    <Award className="w-5 h-5" />
                    Full Rankings
                  </button>
                </Link>

                <Link to="/settings" className="block" data-testid="settings-link">
                  <button className="w-full flex items-center justify-center gap-2 px-4 py-2 border-2 border-gray-300 text-gray-700 rounded-full font-semibold hover:bg-gray-50 transition-colors">
                    <Settings className="w-5 h-5" />
                    Quarter Settings
                  </button>
                </Link>
              </div>

              {/* Settings Status */}
              <div className="mt-5 pt-4 border-t-2 border-dashed border-gray-200">
                <h4 className="font-serif font-bold text-foreground mb-2 flex items-center gap-2 text-sm">
                  <span className={`w-2 h-2 rounded-full ${quarterSettings ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
                  {selectedQuarter} {selectedYear} Status
                </h4>
                {quarterSettings ? (
                  <div className="text-xs text-gray-600">
                    <p>Benchmarks: PPA ${quarterSettings.benchmark_ppa}, LBW ${quarterSettings.benchmark_lbw}</p>
                    <p className="mt-1">A-Server: ≥{quarterSettings.a_server_min_score} pts, B-Server: ≥{quarterSettings.b_server_min_score} pts</p>
                  </div>
                ) : (
                  <div className="text-xs text-yellow-700">
                    <Link to="/settings" className="underline font-semibold">Create settings</Link> for {selectedQuarter} {selectedYear}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Recent Employees Preview */}
        {employees.length > 0 && (
          <div className="bubba-card" data-testid="recent-employees-card">
            <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
            
            <div className="p-6 pt-8">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
                    <Award className="w-5 h-5 text-yellow-600" />
                  </div>
                  <h2 className="text-lg font-serif font-bold text-foreground">
                    {selectedQuarter} {selectedYear} Top Performers
                  </h2>
                </div>
                <Link to="/rankings" className="text-sm text-primary font-semibold hover:underline">
                  View All →
                </Link>
              </div>
              
              <div className="space-y-3">
                {employees.slice(0, 5).map((employee, idx) => {
                  // Derive tier from score and job title
                  const score = employee.total_score || 0;
                  const jobTitle = (employee.job_title || 'server').toLowerCase();
                  const aMin = quarterSettings?.a_server_min_score || 80;
                  const bMin = quarterSettings?.b_server_min_score || 70;
                  
                  let tierLabel, colorClass;
                  if (jobTitle.includes('trainer')) {
                    tierLabel = 'Trainer';
                    colorClass = 'bg-purple-100 text-purple-800';
                  } else if (jobTitle.includes('bartender')) {
                    tierLabel = 'Bartender';
                    colorClass = 'bg-blue-100 text-blue-800';
                  } else if (score >= aMin) {
                    tierLabel = 'A-Server';
                    colorClass = 'bg-green-100 text-green-800';
                  } else if (score >= bMin) {
                    tierLabel = 'B-Server';
                    colorClass = 'bg-yellow-100 text-yellow-800';
                  } else {
                    tierLabel = 'C-Server';
                    colorClass = 'bg-red-100 text-red-800';
                  }
                  
                  return (
                    <div 
                      key={employee.id} 
                      className="flex items-center justify-between p-4 rounded-xl border-2 border-gray-200 bg-gray-50 hover:bg-white transition-colors"
                      data-testid={`ranking-card-${employee.id}`}
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center font-serif font-bold text-white ${
                          idx === 0 ? 'bg-yellow-500' : idx === 1 ? 'bg-gray-400' : idx === 2 ? 'bg-amber-600' : 'bg-blue-400'
                        }`}>
                          {idx + 1}
                        </div>
                        <div>
                          <h3 className="font-serif font-bold text-foreground">
                            {employee.name}
                          </h3>
                          <p className="text-gray-500 text-sm capitalize">{employee.job_title || 'Server'}</p>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-4">
                        <div className="text-right">
                          <div className="text-xl font-serif font-bold text-primary">
                            {formatNumber(score)}
                          </div>
                          <div className="text-xs text-gray-500">Total Score</div>
                        </div>
                        <span className={`px-3 py-1 rounded-full text-xs font-bold ${colorClass}`}>
                          {tierLabel}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
              
              {employees.length > 5 && (
                <div className="mt-6 text-center">
                  <Link to="/rankings">
                    <button className="bubba-btn-secondary">
                      View All {employees.length} Crew Members
                    </button>
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty State */}
        {employees.length === 0 && (
          <div className="bubba-card p-10 text-center">
            <Fish className="w-20 h-20 text-blue-200 mx-auto mb-4" />
            <p className="empty-state-quote">
              No data for {selectedQuarter} {selectedYear} yet.
            </p>
            <p className="text-sm text-gray-500 mt-4 mb-6">
              Upload your first bi-weekly snapshot to see your crew's performance
            </p>
            <Link to="/snapshots">
              <button className="bubba-btn-primary">
                <Camera className="w-5 h-5 mr-2 inline" />
                Go to Snapshots
              </button>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
