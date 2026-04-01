import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { Users, FileText, TrendingUp, Award, Target, Fish, Settings, Camera, Download, X, AlertTriangle, Lock, CheckCircle2, Trophy, Star, BarChart3 } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import FinalizeQuarterModal from "../components/FinalizeQuarterModal";
import QRTopClicksCard from "../components/QRTopClicksCard";
import StoreHealthScore from "../components/StoreHealthScore";
import CoachingRadar from "../components/CoachingRadar";
import ReviewImpactTracker from "../components/ReviewImpactTracker";
import { formatNumber } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

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
  const [showFinalizeModal, setShowFinalizeModal] = useState(false);
  const [isQuarterFinalized, setIsQuarterFinalized] = useState(false);

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
      // Count servers below threshold as under performers (trainers/bartenders excluded)
      return score < bServerThreshold && (jobTitle === 'server' || jobTitle === '');
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
      const response = await api.get(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
      setQuarterSettings(response.data);
    } catch (error) {
      if (error.response?.status === 404) {
        setQuarterSettings(null);
      }
    }
  }, [selectedYear, selectedQuarter]);

  const fetchEmployeesForQuarter = useCallback(async () => {
    try {
      const response = await api.get(`/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      // Sort by total_score descending for display
      const sorted = (response.data || []).sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
      setEmployees(sorted);
    } catch (error) {
    }
  }, [selectedYear, selectedQuarter]);

  const fetchLatestSnapshot = useCallback(async () => {
    try {
      const response = await api.get(`/v2/snapshots?year=${selectedYear}`);
      const snapshots = response.data.filter(s => s.quarter === selectedQuarter);
      if (snapshots.length > 0) {
        // Get most recent snapshot
        setLatestSnapshot(snapshots[0]);
      } else {
        setLatestSnapshot(null);
      }
    } catch (error) {
    }
  }, [selectedYear, selectedQuarter]);

  const checkFinalizationStatus = useCallback(async () => {
    try {
      const response = await api.get(`/v2/finalization/${selectedYear}/${selectedQuarter}`);
      setIsQuarterFinalized(response.data.is_finalized || false);
    } catch (error) {
      setIsQuarterFinalized(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchQuarterSettings();
    fetchEmployeesForQuarter();
    fetchLatestSnapshot();
    checkFinalizationStatus();
  }, [fetchQuarterSettings, fetchEmployeesForQuarter, fetchLatestSnapshot, checkFinalizationStatus]);

  useEffect(() => {
    calculateStats();
  }, [employees, calculateStats]);

  const downloadTemplate = () => {
    window.open(`${BACKEND_URL}/api/v2/template`, '_blank');
    toast.success("Template downloaded!");
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Page Header */}
        <div className="mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-white" data-testid="main-title">
                Performance Dashboard
              </h1>
              <p className="text-slate-400 mt-1" data-testid="main-subtitle">
                {selectedQuarter} {selectedYear} Overview
              </p>
            </div>
            
            {/* Quarter Selector */}
            <div className="flex items-center gap-2">
              <select
                className="px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-primary/50"
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
              >
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
                <option value={2027}>2027</option>
              </select>
              <select
                className="px-3 py-2 bg-slate-800 border border-slate-600 rounded-lg text-sm font-medium text-white focus:outline-none focus:ring-2 focus:ring-primary/50"
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
        </div>

        {/* Bento Grid Layout */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {/* Hero Stat - Crew Count - Clickable to Employees page */}
          <Link to="/employees" className="block">
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-6 hover:border-blue-500/50 transition-colors cursor-pointer" data-testid="total-employees-card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400 uppercase tracking-wide">Crew Members</p>
                  <p className="text-4xl font-bold text-white mt-2">{stats.totalEmployees}</p>
                  <p className="text-xs text-slate-500 mt-1">Active this quarter</p>
                </div>
                <div className="w-12 h-12 rounded-xl bg-blue-500/20 flex items-center justify-center">
                  <Users className="w-6 h-6 text-blue-400" />
                </div>
              </div>
            </div>
          </Link>

          {/* Avg Score */}
          <Link to="/analytics" className="block">
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-6 hover:border-primary/50 transition-all cursor-pointer" data-testid="avg-score-card">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-slate-400 uppercase tracking-wide">Avg Score</p>
                  <p className="text-4xl font-bold text-white mt-2">{stats.avgTotalScore}</p>
                  <p className="text-xs text-slate-500 mt-1">Team average</p>
                </div>
                <div className="w-12 h-12 rounded-xl bg-cyan-500/20 flex items-center justify-center">
                  <BarChart3 className="w-6 h-6 text-cyan-400" />
                </div>
              </div>
            </div>
          </Link>

          {/* Top Performers */}
          <div 
            className="bg-emerald-900/30 rounded-2xl border border-emerald-700/50 p-6 hover:border-emerald-500/50 transition-colors cursor-pointer" 
            onClick={() => setShowTopPerformers(true)}
            data-testid="top-performers-card"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-emerald-400 uppercase tracking-wide">Top Performers</p>
                <p className="text-4xl font-bold text-white mt-2">{stats.topPerformers}</p>
                <p className="text-xs text-emerald-500 mt-1">10% above average</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                <Trophy className="w-6 h-6 text-emerald-400" />
              </div>
            </div>
          </div>

          {/* Under Performers */}
          <div 
            className="bg-red-900/30 rounded-2xl border border-red-700/50 p-6 hover:border-red-500/50 transition-colors cursor-pointer" 
            onClick={() => setShowUnderPerformers(true)}
            data-testid="under-performers-card"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium text-red-400 uppercase tracking-wide">Needs Coaching</p>
                <p className="text-4xl font-bold text-white mt-2">{stats.underPerformers}</p>
                <p className="text-xs text-red-500 mt-1">Below B-Server threshold</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center">
                <AlertTriangle className="w-6 h-6 text-red-400" />
              </div>
            </div>
          </div>
        </div>

        {/* Quick Actions Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
          <Link to="/snapshots" className="flex items-center gap-3 p-4 bg-slate-800 rounded-xl border border-slate-700 hover:border-primary/50 hover:bg-slate-750 transition-all">
            <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
              <Camera className="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p className="font-medium text-white text-sm">Upload Data</p>
              <p className="text-xs text-slate-500">New snapshot</p>
            </div>
          </Link>
          
          <Link to="/rankings" className="flex items-center gap-3 p-4 bg-slate-800 rounded-xl border border-slate-700 hover:border-primary/50 hover:bg-slate-750 transition-all">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
              <Trophy className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <p className="font-medium text-white text-sm">Rankings</p>
              <p className="text-xs text-slate-500">Full leaderboard</p>
            </div>
          </Link>
          
          <Link to="/review-tracker" className="flex items-center gap-3 p-4 bg-slate-800 rounded-xl border border-slate-700 hover:border-primary/50 hover:bg-slate-750 transition-all">
            <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
              <Star className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p className="font-medium text-white text-sm">Reviews</p>
              <p className="text-xs text-slate-500">Customer feedback</p>
            </div>
          </Link>
          
          <Link to="/yodeck" className="flex items-center gap-3 p-4 bg-slate-800 rounded-xl border border-slate-700 hover:border-primary/50 hover:bg-slate-750 transition-all">
            <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
              <FileText className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <p className="font-medium text-white text-sm">Reports</p>
              <p className="text-xs text-slate-500">PDFs & slides</p>
            </div>
          </Link>
        </div>

        {/* Finalize Quarter Banner */}
        {employees.length > 0 && (
          <div className={`mb-6 p-4 rounded-xl flex items-center justify-between ${
            isQuarterFinalized 
              ? 'bg-emerald-900/30 border border-emerald-700/50'
              : 'bg-slate-800 border border-slate-700'
          }`}>
            <div className="flex items-center gap-4">
              <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                isQuarterFinalized ? 'bg-emerald-500/20' : 'bg-slate-700'
              }`}>
                {isQuarterFinalized ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                ) : (
                  <Lock className="w-5 h-5 text-slate-400" />
                )}
              </div>
              <div>
                <h3 className="font-medium text-white">
                  {isQuarterFinalized ? 'Quarter Finalized' : 'Ready to Finalize?'}
                </h3>
                <p className="text-sm text-slate-400">
                  {isQuarterFinalized 
                    ? `${selectedQuarter} ${selectedYear} rankings are locked`
                    : 'Lock in final scores and prepare for next quarter'
                  }
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowFinalizeModal(true)}
              className={`px-4 py-2 rounded-lg font-medium text-sm transition-colors ${
                isQuarterFinalized 
                  ? 'bg-emerald-600 text-white hover:bg-emerald-500'
                  : 'bg-primary text-white hover:bg-primary/90'
              }`}
              data-testid="finalize-quarter-btn"
            >
              {isQuarterFinalized ? 'View Details' : 'Finalize Now'}
            </button>
          </div>
        )}

        {/* Executive Insights Section - Store Health, Coaching Radar, Review Impact */}
        <div className="mb-6">
          <div className="flex items-center gap-2 mb-4">
            <h2 className="text-lg font-bold text-white">Executive Insights</h2>
            <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-400 text-xs rounded-full">NEW</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <StoreHealthScore quarter={selectedQuarter} year={selectedYear} />
            <CoachingRadar quarter={selectedQuarter} year={selectedYear} />
            <ReviewImpactTracker quarter={selectedQuarter} year={selectedYear} />
          </div>
        </div>

        {/* Main Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Top Performers List - Takes 2 columns */}
          <div className="lg:col-span-2 bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
            <div className="p-5 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
                  <Award className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <h2 className="font-bold text-white">Top 5 Performers</h2>
                  <p className="text-xs text-slate-500">{selectedQuarter} {selectedYear}</p>
                </div>
              </div>
              <Link to="/rankings" className="text-sm text-primary font-medium hover:underline">
                View All →
              </Link>
            </div>
            
            <div className="divide-y divide-slate-700">
              {employees.length > 0 ? (
                employees.slice(0, 5).map((employee, idx) => {
                  const score = employee.total_score || 0;
                  const jobTitle = (employee.job_title || 'server').toLowerCase();
                  const aMin = quarterSettings?.a_server_min_score || 80;
                  const bMin = quarterSettings?.b_server_min_score || 70;
                  
                  let tierLabel, colorClass;
                  if (jobTitle.includes('trainer')) {
                    tierLabel = 'Trainer';
                    colorClass = 'bg-purple-500/20 text-purple-400';
                  } else if (jobTitle.includes('bartender')) {
                    tierLabel = 'Bartender';
                    colorClass = 'bg-blue-500/20 text-blue-400';
                  } else if (score >= aMin) {
                    tierLabel = 'A-Server';
                    colorClass = 'bg-emerald-500/20 text-emerald-400';
                  } else if (score >= bMin) {
                    tierLabel = 'B-Server';
                    colorClass = 'bg-cyan-500/20 text-cyan-400';
                  } else {
                    tierLabel = 'C-Server';
                    colorClass = 'bg-red-500/20 text-red-400';
                  }
                  
                  return (
                    <div 
                      key={employee.id} 
                      className="flex items-center justify-between p-4 hover:bg-slate-750 transition-colors"
                    >
                      <div className="flex items-center gap-4">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white ${
                          idx === 0 ? 'bg-amber-500' : idx === 1 ? 'bg-slate-400' : idx === 2 ? 'bg-amber-700' : 'bg-slate-600'
                        }`}>
                          {idx + 1}
                        </div>
                        <div>
                          <h3 className="font-semibold text-white">{employee.name}</h3>
                          <p className="text-xs text-slate-400 capitalize">{employee.job_title || 'Server'}</p>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${colorClass}`}>
                          {tierLabel}
                        </span>
                        <span className="text-lg font-bold text-primary">
                          {formatNumber(score)}
                        </span>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="p-8 text-center">
                  <Fish className="w-12 h-12 text-slate-600 mx-auto mb-3" />
                  <p className="text-slate-400">No data for {selectedQuarter} {selectedYear}</p>
                  <Link to="/snapshots" className="text-sm text-primary font-medium hover:underline mt-2 inline-block">
                    Upload your first snapshot →
                  </Link>
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Status & Actions */}
          <div className="space-y-4">
            {/* Latest Snapshot Status */}
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center">
                  <Camera className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="font-medium text-white">Latest Snapshot</h3>
                  <p className="text-xs text-slate-500">Bi-weekly data</p>
                </div>
              </div>
              
              {latestSnapshot ? (
                <div className="p-3 bg-emerald-900/30 border border-emerald-700/50 rounded-lg mb-4">
                  <div className="flex items-center gap-2 text-emerald-400 mb-1">
                    <CheckCircle2 className="w-4 h-4" />
                    <span className="font-medium text-sm">{latestSnapshot.snapshot_date}</span>
                  </div>
                  <p className="text-emerald-500 text-xs">
                    {latestSnapshot.employee_count} employees • {latestSnapshot.title || 'Snapshot'}
                  </p>
                </div>
              ) : (
                <div className="p-3 bg-amber-900/30 border border-amber-700/50 rounded-lg mb-4">
                  <p className="text-amber-400 text-sm font-medium">No snapshots yet</p>
                  <p className="text-amber-500 text-xs">Upload data to get started</p>
                </div>
              )}
              
              <Link to="/snapshots" className="block">
                <button className="w-full px-4 py-2.5 bg-primary text-white rounded-lg font-medium text-sm hover:bg-primary/90 transition-colors flex items-center justify-center gap-2">
                  <Camera className="w-4 h-4" />
                  Go to Snapshots
                </button>
              </Link>
              
              <button
                onClick={downloadTemplate}
                className="w-full mt-2 px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <Download className="w-4 h-4" />
                Download Template
              </button>
            </div>

            {/* Quarter Settings Status */}
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-slate-700 flex items-center justify-center">
                  <Settings className="w-5 h-5 text-slate-400" />
                </div>
                <div>
                  <h3 className="font-medium text-white">{selectedQuarter} {selectedYear} Settings</h3>
                  <p className="text-xs text-slate-500">Benchmarks & thresholds</p>
                </div>
              </div>
              
              {quarterSettings ? (
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-400">PPA Benchmark</span>
                    <span className="font-medium text-white">${quarterSettings.benchmark_ppa}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">LBW Benchmark</span>
                    <span className="font-medium text-white">${quarterSettings.benchmark_lbw}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">A-Server Min</span>
                    <span className="font-medium text-emerald-400">≥{quarterSettings.a_server_min_score}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">B-Server Min</span>
                    <span className="font-medium text-cyan-400">≥{quarterSettings.b_server_min_score}</span>
                  </div>
                </div>
              ) : (
                <div className="p-3 bg-amber-900/30 border border-amber-700/50 rounded-lg">
                  <p className="text-amber-400 text-sm font-medium">Not configured</p>
                  <p className="text-amber-500 text-xs">Set up benchmarks for this quarter</p>
                </div>
              )}
              
              <Link to="/settings" className="block mt-4">
                <button className="w-full px-4 py-2 border border-slate-600 text-slate-300 rounded-lg font-medium text-sm hover:bg-slate-700 transition-colors">
                  {quarterSettings ? 'Edit Settings' : 'Configure Now'}
                </button>
              </Link>
            </div>
          </div>
        </div>

        {/* ROI & Training Insights */}
        {employees.length > 0 && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
            {/* ROI Calculator */}
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5" data-testid="roi-calculator">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                </div>
                <div>
                  <h3 className="font-bold text-white">Revenue Impact</h3>
                  <p className="text-xs text-slate-500">Potential improvement opportunity</p>
                </div>
              </div>
              
              {(() => {
                const avgPPA = employees.reduce((sum, e) => sum + (e.ppa || 0), 0) / employees.length;
                const totalGuests = employees.reduce((sum, e) => sum + (e.guests || 0), 0);
                const totalLSC = employees.reduce((sum, e) => sum + (e.lsc_count || 0), 0);
                const ppaBenchmark = quarterSettings?.benchmark_ppa || 55;
                const lscBenchmark = quarterSettings?.benchmark_lsc || 10; // Target guests per LSC
                
                // Calculate current LSC rate (guests per sign-up)
                const currentGuestsPerLSC = totalLSC > 0 ? totalGuests / totalLSC : 999;
                const lscGap = Math.max(0, currentGuestsPerLSC - lscBenchmark);
                
                // Revenue calculations
                const ppaGap = Math.max(0, ppaBenchmark - avgPPA);
                const annualGuests = totalGuests * 26;
                const ppaRevenue = ppaGap * annualGuests;
                
                // LSC Value: Each loyalty member worth ~$25 in lifetime value
                const lscValuePerSignup = quarterSettings?.lsc_value || 25;
                const potentialExtraLSC = lscGap > 0 ? Math.round((totalGuests / lscBenchmark) - totalLSC) : 0;
                const annualExtraLSC = potentialExtraLSC * 26;
                const lscRevenue = annualExtraLSC * lscValuePerSignup;
                
                const totalPotential = ppaRevenue + lscRevenue;
                
                return (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="p-3 bg-slate-700/50 rounded-lg">
                        <p className="text-xs text-slate-400 uppercase">Avg PPA</p>
                        <p className="text-lg font-bold text-white">${avgPPA.toFixed(2)}</p>
                        <p className="text-xs text-slate-500">Target: ${ppaBenchmark}</p>
                      </div>
                      <div className="p-3 bg-slate-700/50 rounded-lg">
                        <p className="text-xs text-slate-400 uppercase">Guests/LSC</p>
                        <p className="text-lg font-bold text-white">{currentGuestsPerLSC.toFixed(1)}</p>
                        <p className="text-xs text-slate-500">Target: {lscBenchmark} (1 in {lscBenchmark})</p>
                      </div>
                    </div>
                    
                    {totalPotential > 0 ? (
                      <div className="space-y-2">
                        {ppaRevenue > 0 && (
                          <div className="p-3 bg-emerald-900/30 border border-emerald-700/50 rounded-lg">
                            <div className="flex justify-between items-center">
                              <div>
                                <p className="text-sm font-medium text-emerald-400">PPA Opportunity</p>
                                <p className="text-xs text-emerald-500">+${ppaGap.toFixed(2)}/guest to hit ${ppaBenchmark}</p>
                              </div>
                              <p className="text-xl font-bold text-emerald-300">${Math.round(ppaRevenue).toLocaleString()}</p>
                            </div>
                          </div>
                        )}
                        {lscRevenue > 0 && (
                          <div className="p-3 bg-amber-900/30 border border-amber-700/50 rounded-lg">
                            <div className="flex justify-between items-center">
                              <div>
                                <p className="text-sm font-medium text-amber-400">LSC Opportunity</p>
                                <p className="text-xs text-amber-500">+{annualExtraLSC.toLocaleString()} sign-ups @ ${lscValuePerSignup} each</p>
                              </div>
                              <p className="text-xl font-bold text-amber-300">${Math.round(lscRevenue).toLocaleString()}</p>
                            </div>
                          </div>
                        )}
                        <div className="p-3 bg-blue-900/30 border border-blue-700/50 rounded-lg">
                          <div className="flex justify-between items-center">
                            <p className="text-sm font-medium text-blue-400">Total Annual Potential</p>
                            <p className="text-2xl font-bold text-blue-300">${Math.round(totalPotential).toLocaleString()}</p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="p-3 bg-blue-900/30 border border-blue-700/50 rounded-lg text-center">
                        <p className="text-blue-300 font-medium">Team is meeting all benchmarks!</p>
                      </div>
                    )}
                  </div>
                );
              })()}
            </div>

            {/* Training Priorities */}
            <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5" data-testid="training-insights">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
                  <Target className="w-5 h-5 text-cyan-400" />
                </div>
                <div>
                  <h3 className="font-bold text-white">Training Priorities</h3>
                  <p className="text-xs text-slate-500">Focus areas for improvement</p>
                </div>
              </div>
              
              {(() => {
                const ppaBenchmark = quarterSettings?.benchmark_ppa || 55;
                const lbwBenchmark = quarterSettings?.benchmark_lbw || 8;
                const glassBenchmark = quarterSettings?.benchmark_glass || 1;
                
                const belowPPA = employees.filter(e => (e.ppa || 0) < ppaBenchmark).length;
                const belowLBW = employees.filter(e => (e.lbw_per_guest || 0) < lbwBenchmark).length;
                const belowGlass = employees.filter(e => (e.glassware_per_guest || 0) < glassBenchmark).length;
                
                const priorities = [
                  { metric: 'PPA', count: belowPPA, pct: Math.round(belowPPA / employees.length * 100), tip: 'Upselling appetizers & desserts' },
                  { metric: 'LBW', count: belowLBW, pct: Math.round(belowLBW / employees.length * 100), tip: 'LTO cocktails & premium spirits' },
                  { metric: 'Glassware', count: belowGlass, pct: Math.round(belowGlass / employees.length * 100), tip: 'Bar glassware add-ons' },
                ].filter(p => p.count > 0).sort((a, b) => b.pct - a.pct);
                
                return priorities.length > 0 ? (
                  <div className="space-y-2">
                    {priorities.slice(0, 3).map((p, idx) => (
                      <div key={p.metric} className={`p-3 rounded-lg ${idx === 0 ? 'bg-red-900/30 border border-red-700/50' : 'bg-amber-900/20 border border-amber-700/30'}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className={`font-medium text-sm ${idx === 0 ? 'text-red-400' : 'text-amber-400'}`}>
                            {p.metric}
                          </span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${idx === 0 ? 'bg-red-500/20 text-red-400' : 'bg-amber-500/20 text-amber-400'}`}>
                            {p.count} below ({p.pct}%)
                          </span>
                        </div>
                        <p className="text-xs text-slate-400">{p.tip}</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="p-4 bg-emerald-900/30 border border-emerald-700/50 rounded-lg text-center">
                    <p className="text-emerald-400 font-medium">No critical gaps!</p>
                    <p className="text-xs text-emerald-500">Team is performing well</p>
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* QR Top Clicks Section */}
        <div className="mt-6">
          <QRTopClicksCard showViewAll={true} limit={5} />
        </div>
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
                  <p className="text-green-100 text-sm">{selectedQuarter} {selectedYear} • Score ≥ {stats.topPerformerThreshold} (10% above avg of {stats.avgTotalScore})</p>
                </div>
              </div>
              <button onClick={() => setShowTopPerformers(false)} className="text-white hover:bg-white/20 rounded-full p-2 transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              {employees
                .filter(emp => (emp.total_score || 0) >= parseFloat(stats.topPerformerThreshold || 0))
                .map((emp, idx) => {
                  const score = emp.total_score || 0;
                  const avgScore = parseFloat(stats.avgTotalScore) || 0;
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
                  
                  // Calculate restaurant averages for comparison
                  const avgPpa = employees.reduce((sum, e) => sum + (e.ppa || 0), 0) / employees.length;
                  const avgLbw = employees.reduce((sum, e) => sum + (e.lbw_per_guest || 0), 0) / employees.length;
                  const avgGlass = employees.reduce((sum, e) => sum + (e.glassware_per_guest || 0), 0) / employees.length;
                  const avgLsc = employees.reduce((sum, e) => sum + (e.guests_per_lsc || 0), 0) / employees.length;
                  const avgCv = employees.reduce((sum, e) => sum + (e.cv_score || 0), 0) / employees.length;
                  
                  // Calculate performance vs benchmark/average for each metric (higher = better)
                  const metricPerformance = [
                    { 
                      name: 'PPA', 
                      value: ppa,
                      display: `$${ppa.toFixed(2)}`,
                      percentAbove: ppaBenchmark > 0 ? ((ppa - ppaBenchmark) / ppaBenchmark * 100) : 0,
                      vsAvg: avgPpa > 0 ? ((ppa - avgPpa) / avgPpa * 100) : 0
                    },
                    { 
                      name: 'LBW', 
                      value: lbw,
                      display: `$${lbw.toFixed(2)}/guest`,
                      percentAbove: lbwBenchmark > 0 ? ((lbw - lbwBenchmark) / lbwBenchmark * 100) : 0,
                      vsAvg: avgLbw > 0 ? ((lbw - avgLbw) / avgLbw * 100) : 0
                    },
                    { 
                      name: 'Glassware', 
                      value: glass,
                      display: `$${glass.toFixed(2)}/guest`,
                      percentAbove: glassBenchmark > 0 ? ((glass - glassBenchmark) / glassBenchmark * 100) : 0,
                      vsAvg: avgGlass > 0 ? ((glass - avgGlass) / avgGlass * 100) : 0
                    },
                    { 
                      name: 'LSC Ratio', 
                      value: lsc,
                      display: `${lsc.toFixed(0)} guests`,
                      // For LSC, lower is better, so invert the calculation
                      percentAbove: lscBenchmark > 0 ? ((lscBenchmark - lsc) / lscBenchmark * 100) : 0,
                      vsAvg: avgLsc > 0 ? ((avgLsc - lsc) / avgLsc * 100) : 0
                    },
                    { 
                      name: 'Customer Voice', 
                      value: cvScore,
                      display: `${cvScore >= 0 ? '+' : ''}${cvScore.toFixed(1)} pts`,
                      percentAbove: cvScore > 0 ? cvScore * 10 : cvScore * 5, // CV is already a score, weight it
                      vsAvg: avgCv !== 0 ? ((cvScore - avgCv) / Math.abs(avgCv) * 100) : (cvScore > 0 ? 100 : 0)
                    }
                  ];
                  
                  // Sort by performance vs average (highest first) to find top 2 drivers
                  const sortedMetrics = [...metricPerformance].sort((a, b) => b.vsAvg - a.vsAvg);
                  const top2Metrics = sortedMetrics.slice(0, 2).filter(m => m.vsAvg > 0);
                  
                  // Generate justification based on top 2 driving metrics
                  let justification = '';
                  if (top2Metrics.length >= 2) {
                    justification = `${emp.name}'s success is driven by ${top2Metrics[0].name} (${top2Metrics[0].display}, ${top2Metrics[0].vsAvg.toFixed(0)}% above avg) and ${top2Metrics[1].name} (${top2Metrics[1].display}, ${top2Metrics[1].vsAvg.toFixed(0)}% above avg).`;
                  } else if (top2Metrics.length === 1) {
                    justification = `${emp.name}'s success is driven by ${top2Metrics[0].name} (${top2Metrics[0].display}, ${top2Metrics[0].vsAvg.toFixed(0)}% above avg).`;
                  } else {
                    justification = `${emp.name} shows balanced performance across all metrics, scoring ${((score - avgScore) / avgScore * 100).toFixed(0)}% above the restaurant average.`;
                  }
                  
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
                            <h3 className="font-serif font-bold text-lg text-gray-900">{emp.name}</h3>
                            <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs font-bold rounded-full">
                              +{((score - avgScore) / avgScore * 100).toFixed(0)}% vs avg
                            </span>
                          </div>
                          <span className="text-xl font-bold text-green-600">{score.toFixed(1)}</span>
                        </div>
                        <p className="text-sm text-gray-600 capitalize mb-2">{emp.job_title || 'Server'}</p>
                        <p className="text-sm text-gray-700 italic">"{justification}"</p>
                        {top2Metrics.length > 0 && (
                          <div className="flex gap-2 mt-2">
                            {top2Metrics.map((metric, i) => (
                              <span key={i} className="px-2 py-1 bg-green-50 text-green-700 text-xs font-semibold rounded-full border border-green-200">
                                {metric.name}: {metric.display}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              {employees.filter(emp => (emp.total_score || 0) >= parseFloat(stats.topPerformerThreshold || 0)).length === 0 && (
                <p className="text-center text-gray-500 py-8">No employees scoring 10% above the restaurant average.</p>
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
                    <div key={emp.id} className="p-4 border-b border-gray-200 last:border-0 hover:bg-gray-50 transition-colors rounded-lg">
                      <div className="flex items-start gap-4">
                        <div className="w-12 h-12 rounded-full bg-red-600 flex items-center justify-center">
                          <span className="text-white font-bold text-lg">{emp.name.charAt(0)}</span>
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center justify-between mb-2">
                            <h3 className="font-serif font-bold text-lg text-gray-900">{emp.name}</h3>
                            <span className="text-xl font-bold text-red-600">{score.toFixed(1)}</span>
                          </div>
                          
                          {/* Mini Profile */}
                          <div className="grid grid-cols-4 gap-2 mb-3 text-center">
                            <div className="bg-slate-800 rounded p-2">
                              <div className="text-sm font-bold text-white">${ppa.toFixed(0)}</div>
                              <div className="text-xs text-slate-300">PPA</div>
                            </div>
                            <div className="bg-slate-800 rounded p-2">
                              <div className="text-sm font-bold text-white">${lbw.toFixed(2)}</div>
                              <div className="text-xs text-slate-300">LBW/G</div>
                            </div>
                            <div className="bg-slate-800 rounded p-2">
                              <div className="text-sm font-bold text-white">${(emp.glassware_per_guest || 0).toFixed(2)}</div>
                              <div className="text-xs text-slate-300">Glass</div>
                            </div>
                            <div className="bg-slate-800 rounded p-2">
                              <div className="text-sm font-bold text-white">{emp.cv_score || 0}</div>
                              <div className="text-xs text-slate-300">CV</div>
                            </div>
                          </div>
                          
                          <p className="text-sm text-gray-800 italic bg-amber-100 border border-amber-300 p-3 rounded-lg">"{justification}"</p>
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

      {/* Finalize Quarter Modal */}
      <FinalizeQuarterModal
        isOpen={showFinalizeModal}
        onClose={() => setShowFinalizeModal(false)}
        quarter={selectedQuarter}
        year={selectedYear}
        employees={employees}
        onFinalized={() => {
          setIsQuarterFinalized(true);
          setShowFinalizeModal(false);
        }}
      />
    </div>
  );
}
