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
    const bServerThreshold = quarterSettings?.b_server_min_score || 70;
    
    // Top performers: score >= 10% above restaurant average
    const topPerformerThreshold = avgScore * 1.10;
    const topPerformers = employees.filter(emp => (emp.total_score || 0) >= topPerformerThreshold).length;
    
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
      underPerformers,
      topPerformerThreshold: topPerformerThreshold.toFixed(1)
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
            color="bg-yellow-500"
            testId="avg-score-card"
            linkTo="/analytics"
          />
          <StatsCard 
            icon={Award}
            title="Top Performers"
            value={stats.topPerformers}
            color="bg-green-500"
            testId="top-performers-card"
            onClick={() => setShowTopPerformers(true)}
          />
          <StatsCard 
            icon={AlertTriangle}
            title="Under Performers"
            value={stats.underPerformers}
            color="bg-red-500"
            testId="under-performers-card"
            onClick={() => setShowUnderPerformers(true)}
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

      {/* Top Performers Modal */}
      {showTopPerformers && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowTopPerformers(false)}>
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-green-500 to-green-600 p-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Award className="w-8 h-8 text-white" />
                <div>
                  <h2 className="text-2xl font-serif font-bold text-white">Top Performers</h2>
                  <p className="text-green-100 text-sm">{selectedQuarter} {selectedYear} • Top 10 by Total Score</p>
                </div>
              </div>
              <button onClick={() => setShowTopPerformers(false)} className="text-white hover:bg-white/20 rounded-full p-2 transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {employees
                .slice(0, 10)
                .map((emp, idx) => {
                  const score = emp.total_score || 0;
                  const aMin = quarterSettings?.a_server_min_score || 80;
                  const jobTitle = (emp.job_title || 'server').toLowerCase();
                  const ppa = emp.ppa || 0;
                  const lbw = emp.lbw_per_guest || 0;
                  const glass = emp.glassware_per_guest || 0;
                  const lsc = emp.guests_per_lsc || 0;
                  const cvScore = emp.cv_score || 0;
                  const ppaBenchmark = quarterSettings?.benchmark_ppa || 55;
                  const lbwBenchmark = quarterSettings?.benchmark_lbw || 8;
                  const glassBenchmark = quarterSettings?.benchmark_glass || 1;
                  const lscBenchmark = quarterSettings?.benchmark_lsc || 100;
                  
                  // Generate specific justification based on actual metrics
                  let justification = '';
                  const strengths = [];
                  const areas = [];
                  
                  if (ppa >= ppaBenchmark * 1.1) strengths.push(`exceptional PPA of $${ppa.toFixed(2)}`);
                  else if (ppa >= ppaBenchmark) strengths.push(`solid PPA of $${ppa.toFixed(2)}`);
                  else areas.push('PPA');
                  
                  if (lbw >= lbwBenchmark * 1.1) strengths.push(`strong LBW at $${lbw.toFixed(2)}/guest`);
                  else if (lbw >= lbwBenchmark) strengths.push(`consistent LBW at $${lbw.toFixed(2)}/guest`);
                  else areas.push('LBW');
                  
                  if (glass >= glassBenchmark * 1.2) strengths.push(`excellent glassware sales ($${glass.toFixed(2)}/guest)`);
                  
                  if (lsc <= lscBenchmark * 0.9 && lsc > 0) strengths.push(`efficient guest handling (${lsc.toFixed(0)} guests/LSC)`);
                  
                  if (cvScore > 3) strengths.push(`outstanding customer feedback (+${cvScore.toFixed(1)} CV)`);
                  else if (cvScore > 0) strengths.push(`positive customer voice (+${cvScore.toFixed(1)} CV)`);
                  
                  if (jobTitle.includes('trainer')) {
                    justification = `As a Trainer scoring ${score.toFixed(1)}, ${emp.name} leads by example with ${strengths.slice(0, 2).join(' and ')}.`;
                  } else if (jobTitle.includes('bartender')) {
                    justification = `Behind the bar, ${emp.name} delivers ${score.toFixed(1)} points through ${strengths.slice(0, 2).join(' and ')}.`;
                  } else if (strengths.length >= 3) {
                    justification = `${emp.name} excels with ${strengths.slice(0, 3).join(', ')}, earning a ${score.toFixed(1)} total score.`;
                  } else if (strengths.length >= 1) {
                    justification = `${emp.name} demonstrates ${strengths.join(' and ')}, achieving ${score.toFixed(1)} points this quarter.`;
                  } else {
                    justification = `${emp.name} maintains consistent performance with a ${score.toFixed(1)} score across all metrics.`;
                  }
                  
                  const isAServer = score >= aMin;
                  
                  return (
                    <div key={emp.id} className="flex items-start gap-4 p-4 border-b border-gray-100 last:border-0 hover:bg-green-50 transition-colors rounded-lg">
                      <div className={`w-10 h-10 rounded-full flex items-center justify-center font-bold text-white ${
                        idx === 0 ? 'bg-yellow-500' : idx === 1 ? 'bg-gray-400' : idx === 2 ? 'bg-amber-600' : 'bg-green-500'
                      }`}>
                        {idx + 1}
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <h3 className="font-serif font-bold text-lg">{emp.name}</h3>
                            {isAServer && <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-bold rounded-full">A-Server</span>}
                          </div>
                          <span className="text-xl font-bold text-green-600">{score.toFixed(1)}</span>
                        </div>
                        <p className="text-sm text-gray-500 capitalize mb-2">{emp.job_title || 'Server'}</p>
                        <p className="text-sm text-gray-700 italic">"{justification}"</p>
                        <div className="flex gap-3 mt-2 text-xs text-gray-500">
                          <span>PPA: ${ppa.toFixed(2)}</span>
                          <span>LBW: ${lbw.toFixed(2)}</span>
                          <span>Glass: ${glass.toFixed(2)}</span>
                          <span>LSC: {lsc.toFixed(0)}</span>
                          <span>CV: {cvScore >= 0 ? '+' : ''}{cvScore.toFixed(1)}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              {employees.length === 0 && (
                <p className="text-center text-gray-500 py-8">No employees found for this quarter.</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Under Performers Modal */}
      {showUnderPerformers && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowUnderPerformers(false)}>
          <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[80vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="bg-gradient-to-r from-red-500 to-red-600 p-6 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <AlertTriangle className="w-8 h-8 text-white" />
                <div>
                  <h2 className="text-2xl font-serif font-bold text-white">Under Performers</h2>
                  <p className="text-red-100 text-sm">{selectedQuarter} {selectedYear} • Score &lt; {quarterSettings?.b_server_min_score || 70}</p>
                </div>
              </div>
              <button onClick={() => setShowUnderPerformers(false)} className="text-white hover:bg-white/20 rounded-full p-2 transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {employees
                .filter(emp => {
                  const score = emp.total_score || 0;
                  const jobTitle = (emp.job_title || '').toLowerCase();
                  return score < (quarterSettings?.b_server_min_score || 70) && jobTitle === 'server';
                })
                .map((emp, idx) => {
                  const score = emp.total_score || 0;
                  const bMin = quarterSettings?.b_server_min_score || 70;
                  const ppa = emp.ppa || 0;
                  const lbw = emp.lbw_per_guest || 0;
                  const ppaBenchmark = quarterSettings?.benchmark_ppa || 55;
                  const lbwBenchmark = quarterSettings?.benchmark_lbw || 8;
                  
                  // Generate specific justification based on weak areas
                  let weakAreas = [];
                  if (ppa < ppaBenchmark * 0.8) weakAreas.push('PPA');
                  if (lbw < lbwBenchmark * 0.8) weakAreas.push('LBW');
                  if ((emp.glassware_per_guest || 0) < 1) weakAreas.push('Glassware');
                  if ((emp.cv_score || 0) < 0) weakAreas.push('Customer Voice');
                  
                  let justification = `${emp.name} scored ${score.toFixed(1)}, which is ${(bMin - score).toFixed(1)} points below the B-Server threshold. `;
                  if (weakAreas.length > 0) {
                    justification += `Key areas for improvement: ${weakAreas.join(', ')}. `;
                  }
                  justification += `Coaching focus: ${weakAreas[0] || 'overall upselling techniques'} and guest engagement.`;
                  
                  return (
                    <div key={emp.id} className="p-4 border-b border-gray-100 last:border-0 hover:bg-red-50 transition-colors rounded-lg">
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 rounded-full bg-red-100 flex items-center justify-center">
                          <span className="text-red-600 font-bold">{emp.name.charAt(0)}</span>
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="font-serif font-bold text-lg">{emp.name}</h3>
                            <span className="text-xl font-bold text-red-600">{score.toFixed(1)}</span>
                          </div>
                          
                          {/* Mini Profile */}
                          <div className="grid grid-cols-4 gap-2 mb-3 text-center">
                            <div className="bg-gray-100 rounded p-2">
                              <div className="text-sm font-bold">${ppa.toFixed(0)}</div>
                              <div className="text-xs text-gray-500">PPA</div>
                            </div>
                            <div className="bg-gray-100 rounded p-2">
                              <div className="text-sm font-bold">${lbw.toFixed(2)}</div>
                              <div className="text-xs text-gray-500">LBW/G</div>
                            </div>
                            <div className="bg-gray-100 rounded p-2">
                              <div className="text-sm font-bold">${(emp.glassware_per_guest || 0).toFixed(2)}</div>
                              <div className="text-xs text-gray-500">Glass</div>
                            </div>
                            <div className="bg-gray-100 rounded p-2">
                              <div className="text-sm font-bold">{emp.cv_score || 0}</div>
                              <div className="text-xs text-gray-500">CV</div>
                            </div>
                          </div>
                          
                          <p className="text-sm text-gray-700 italic bg-red-50 p-3 rounded-lg">"{justification}"</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              {employees.filter(emp => {
                const score = emp.total_score || 0;
                const jobTitle = (emp.job_title || '').toLowerCase();
                return score < (quarterSettings?.b_server_min_score || 70) && jobTitle === 'server';
              }).length === 0 && (
                <div className="text-center py-8">
                  <Award className="w-16 h-16 text-green-300 mx-auto mb-4" />
                  <p className="text-gray-500">Great news! No under performers this quarter.</p>
                  <p className="text-sm text-gray-400">All servers are meeting or exceeding expectations.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
