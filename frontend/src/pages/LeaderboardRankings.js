import { useState, useEffect, useCallback, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Trophy, TrendingUp, TrendingDown, Minus, Flame, Star, Crown, Award, Download, ChevronDown, ChevronUp, Search, RefreshCw, Info } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Design System Colors
const COLORS = {
  background: "#0F172A",
  backgroundAlt: "#1E293B",
  backgroundRow: "#162032",
  backgroundRowAlt: "#1A2744",
  textPrimary: "#F9FAFB",
  textSecondary: "#9CA3AF",
  textMuted: "#6B7280",
  gold: "#FBBF24",
  silver: "#94A3B8",
  bronze: "#CD7F32",
  green: "#22C55E",
  blue: "#3B82F6",
  orange: "#F97316",
  red: "#EF4444",
  purple: "#A855F7",
};

// Momentum Indicator Component
const MomentumIndicator = ({ trend, change }) => {
  if (trend === "hot") {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="flex items-center gap-1 text-orange-500">
              <Flame className="w-5 h-5 animate-pulse" />
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>On Fire! +{change?.toFixed(1)} pts</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  if (trend === "up") {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="flex items-center gap-1 text-green-500">
              <TrendingUp className="w-5 h-5" />
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>Improving +{change?.toFixed(1)} pts</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  if (trend === "down") {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="flex items-center gap-1 text-red-500">
              <TrendingDown className="w-5 h-5" />
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>Declining {change?.toFixed(1)} pts</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  if (trend === "new") {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="flex items-center gap-1 text-blue-400">
              <Star className="w-4 h-4" />
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>New to leaderboard</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  return (
    <span className="flex items-center gap-1 text-slate-500">
      <Minus className="w-5 h-5" />
    </span>
  );
};

// Review Recognition Badge Component
const RecognitionBadge = ({ mentions }) => {
  if (mentions >= 20) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400 text-xs font-bold">
              <Crown className="w-3 h-3" /> Leader
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>Hospitality Leader - {mentions} review mentions!</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  if (mentions >= 10) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-500/20 text-purple-400 text-xs font-bold">
              <Award className="w-3 h-3" /> Top Reviewed
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>Top Reviewed - {mentions} review mentions!</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  if (mentions >= 5) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger>
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 text-xs font-bold">
              <Star className="w-3 h-3" /> Star
            </span>
          </TooltipTrigger>
          <TooltipContent className="bg-slate-800 text-white">
            <p>Review Star - {mentions} review mentions!</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }
  return null;
};

// Score Progress Bar Component
const ScoreBar = ({ value, max, benchmark, color = "blue" }) => {
  const percentage = Math.min((value / max) * 100, 100);
  const benchmarkPct = benchmark ? Math.min((benchmark / max) * 100, 100) : null;
  
  const barColor = value >= (benchmark || max) 
    ? "bg-green-500" 
    : value >= (benchmark || max) * 0.8 
      ? "bg-blue-500" 
      : "bg-orange-500";
  
  return (
    <div className="relative w-full h-3 bg-slate-600 rounded-full overflow-hidden">
      <div 
        className={`absolute left-0 top-0 h-full ${barColor} transition-all duration-500`}
        style={{ width: `${percentage}%` }}
      />
      {benchmarkPct && (
        <div 
          className="absolute top-0 h-full w-1 bg-yellow-400"
          style={{ left: `${benchmarkPct}%` }}
        />
      )}
    </div>
  );
};

// Rank Badge Component
const RankBadge = ({ position, tier }) => {
  let bgColor = "bg-slate-700";
  let textColor = "text-white";
  let borderColor = "border-transparent";
  
  if (position === 1) {
    bgColor = "bg-gradient-to-br from-yellow-400 to-yellow-600";
    textColor = "text-yellow-900";
    borderColor = "border-yellow-300";
  } else if (position === 2) {
    bgColor = "bg-gradient-to-br from-slate-300 to-slate-500";
    textColor = "text-slate-900";
    borderColor = "border-slate-200";
  } else if (position === 3) {
    bgColor = "bg-gradient-to-br from-amber-600 to-amber-800";
    textColor = "text-amber-100";
    borderColor = "border-amber-400";
  } else if (position <= 5) {
    bgColor = "bg-green-600/30";
    textColor = "text-green-400";
    borderColor = "border-green-500/50";
  }
  
  return (
    <div className={`flex items-center justify-center w-12 h-12 rounded-lg ${bgColor} border-2 ${borderColor} font-bold text-xl ${textColor}`}>
      {position}
    </div>
  );
};

// Category Leader Card Component
const CategoryLeaderCard = ({ title, leader, value, format, icon: Icon }) => {
  const formatValue = () => {
    if (!value && value !== 0) return "N/A";
    if (format === "currency") return `$${value?.toFixed(2) || "0.00"}`;
    if (format === "ratio") return `1 in ${Math.round(value)}`;
    if (format === "number") return Math.round(value);
    return value?.toFixed(1) || "0";
  };
  
  return (
    <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50">
      <div className="flex items-center gap-2 mb-2 text-slate-400 text-sm">
        <Icon className="w-4 h-4" />
        <span>{title}</span>
      </div>
      <div className="font-bold text-white truncate">{leader || "N/A"}</div>
      <div className="text-2xl font-bold text-green-400">
        {formatValue()}
      </div>
    </div>
  );
};

export default function LeaderboardRankings() {
  const [rankings, setRankings] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [snapshots, setSnapshots] = useState([]);
  const [previousScores, setPreviousScores] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [searchQuery, setSearchQuery] = useState("");
  const [downloading, setDownloading] = useState(false);
  
  // Use location to detect route changes
  const location = useLocation();

  // Filter rankings by search
  const filteredRankings = useMemo(() => {
    if (!searchQuery.trim()) return rankings;
    const query = searchQuery.toLowerCase();
    return rankings.filter(emp => 
      emp.name?.toLowerCase().includes(query) ||
      emp.job_title?.toLowerCase().includes(query)
    );
  }, [rankings, searchQuery]);

  // Calculate category leaders
  const categoryLeaders = useMemo(() => {
    if (!employees.length) return {};
    
    const findLeader = (metric, higherBetter = true) => {
      const sorted = [...employees].filter(e => {
        const val = e[metric];
        return val !== null && val !== undefined && val > 0;
      }).sort((a, b) => {
        const aVal = a[metric] || 0;
        const bVal = b[metric] || 0;
        return higherBetter ? bVal - aVal : aVal - bVal;
      });
      return sorted[0];
    };
    
    // LSC Champion: person with most LSC cards sold (highest lsc_count)
    const findLscLeader = () => {
      const sorted = [...employees].filter(e => (e.lsc_count || 0) > 0).sort((a, b) => {
        return (b.lsc_count || 0) - (a.lsc_count || 0);
      });
      return sorted[0];
    };
    
    return {
      ppa: findLeader("ppa"),
      lbw: findLeader("lbw_per_guest"),
      lsc: findLscLeader(),
      reviews: findLeader("rt_mentions") || findLeader("review_mentions"),
    };
  }, [employees]);

  // Calculate momentum (trend) based on snapshots - uses multiple name matching strategies
  const calculateMomentum = useCallback((employeeName, currentScore, reportName = null) => {
    const nameLower = employeeName?.toLowerCase().trim();
    const firstName = nameLower?.split(' ')[0];
    const reportLower = reportName?.toLowerCase().trim();
    
    // Try multiple matching strategies
    let prevScore = previousScores[nameLower];
    if (prevScore === undefined && firstName) prevScore = previousScores[firstName];
    if (prevScore === undefined && reportLower) prevScore = previousScores[reportLower];
    
    if (prevScore === undefined) return { trend: "new", change: 0 };
    
    const change = currentScore - prevScore;
    
    if (change >= 5) return { trend: "hot", change };
    if (change > 0) return { trend: "up", change };
    if (change < -2) return { trend: "down", change };
    return { trend: "stable", change };
  }, [previousScores]);

  // Fetch data
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      // Use snapshot-workflow current-rankings endpoint
      const [rankingsRes, snapshotsRes] = await Promise.all([
        api.get(`/v2/snapshot-workflow/current-rankings?year=${selectedYear}&quarter=${selectedQuarter}`),
        api.get(`/v2/snapshot-workflow/snapshots?year=${selectedYear}&quarter=${selectedQuarter}&status=completed`),
      ]);
      
      // Get employees from the current snapshot
      const snapshotEmployees = rankingsRes.data?.employees || [];
      
      // Define tier order for sorting
      const tierOrder = {
        "Trainer": 0, "Bartender": 1, "A-Server": 2, "B-Server": 3, "C-Server": 4, "Server": 5
      };
      
      // Sort employees by tier first, then by score within tier (highest to lowest)
      const sortedEmployees = snapshotEmployees.sort((a, b) => {
        const tierA = tierOrder[a.tier_label] ?? 5;
        const tierB = tierOrder[b.tier_label] ?? 5;
        if (tierA !== tierB) return tierA - tierB;
        const scoreA = a.total_score || a.pre_dar_score || 0;
        const scoreB = b.total_score || b.pre_dar_score || 0;
        return scoreB - scoreA;
      });
      
      // Transform to rankings format with position
      const leaderboardRankings = sortedEmployees.map((emp, idx) => ({
        position: idx + 1,
        position_label: `#${idx + 1}`,
        tier_label: emp.tier_label || emp.job_title || "Server",
        tier_rank: emp.tier_rank || idx + 1,
        employee_id: emp.id || emp.name,
        name: emp.name,
        display_name: emp.display_name || emp.name,
        report_name: emp.report_name || emp.name,
        job_title: emp.job_title || "Server",
        total_score: emp.total_score || emp.pre_dar_score || 0,
        base_score: emp.weighted_score || 0,
        bonus_points: (emp.total_metric_bonus || 0) + (emp.review_tracker_bonus || 0),
        review_bonus: emp.review_tracker_bonus || 0,
        metric_bonus: emp.total_metric_bonus || 0,
        combined_review_bonus: (emp.cv_score || 0) + (emp.review_tracker_bonus || 0),
        ppa: emp.ppa || 0,
        lbw_per_guest: emp.lbw_per_guest || 0,
        glassware_per_guest: emp.glassware_per_guest || 0,
        guests_per_lsc: emp.guests_per_lsc || 0,
        guest_count: emp.guest_count || emp.guests || 0,
        net_sales: emp.net_sales || 0,
        ppa_percentage: emp.score_ppa || 0,
        lbw_percentage: emp.score_lbw || 0,
        glassware_percentage: emp.score_glass || 0,
        lsc_percentage: emp.score_lsc || 0,
        nps_score: emp.nps_score || 0,
        nps_points: emp.nps_score_pts || emp.cv_score || 0,
        cv_score: emp.cv_score || 0,
        cv_promoters: emp.cv_promoters || 0,
        cv_detractors: emp.cv_detractors || 0,
        review_mentions: emp.rt_mentions || emp.review_mentions || 0,
      }));
      
      setRankings(leaderboardRankings);
      setEmployees(sortedEmployees);
      setSnapshots(snapshotsRes.data || []);
      
      // Build previous scores from second-latest snapshot for momentum/trend
      // Match by multiple keys: name, display_name, report_name, first name
      if (snapshotsRes.data?.length > 1) {
        const prevSnapshot = snapshotsRes.data[1]; // Second most recent snapshot
        const prevScoresMap = {};
        const prevEmployees = prevSnapshot.employees || prevSnapshot.employees_data || [];
        prevEmployees.forEach(emp => {
          const score = emp.total_score || emp.pre_dar_score || 0;
          
          // Add multiple keys for flexible matching
          const name = emp.name?.toLowerCase().trim();
          const displayName = emp.display_name?.toLowerCase().trim();
          const reportName = emp.report_name?.toLowerCase().trim();
          const firstName = name?.split(' ')[0];
          
          if (name) prevScoresMap[name] = score;
          if (displayName && displayName !== name) prevScoresMap[displayName] = score;
          if (reportName && reportName !== name) prevScoresMap[reportName] = score;
          if (firstName && firstName !== name) prevScoresMap[firstName] = score;
        });
        setPreviousScores(prevScoresMap);
      }
    } catch (error) {
      toast.error("Failed to load rankings");
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Refresh when navigating to this page or when window gains focus
  useEffect(() => {
    fetchData();
    
    const handleFocus = () => {
      fetchData();
    };
    
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [location.key, fetchData]);

  // Get employee details
  const getEmployeeDetails = (employeeId) => {
    return employees.find(e => e.id === employeeId) || {};
  };

  // Download leaderboard slide
  const downloadLeaderboardSlide = async () => {
    setDownloading(true);
    try {
      const response = await api.get(
        `/v2/yodeck/${selectedYear}/${selectedQuarter}/leaderboard-slide?format=16:9`,
        { responseType: "blob" }
      );
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", `leaderboard_${selectedQuarter}_${selectedYear}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      
      toast.success("Leaderboard slide downloaded!");
    } catch (error) {
      toast.error("Failed to download slide");
    } finally {
      setDownloading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: COLORS.background }}>
        <div className="flex flex-col items-center gap-4">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
          <p className="text-slate-400">Loading leaderboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ backgroundColor: COLORS.background }}>
      {/* Header */}
      <div className="border-b border-slate-700/50 px-6 py-4">
        <div className="max-w-[1800px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Trophy className="w-8 h-8 text-yellow-500" />
            <div>
              <h1 className="text-2xl font-bold text-white">Performance Leaderboard</h1>
              <p className="text-slate-400">{selectedQuarter} {selectedYear} Rankings</p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            {/* Quarter/Year Selector */}
            <Select value={selectedQuarter} onValueChange={setSelectedQuarter}>
              <SelectTrigger className="w-24 bg-slate-800 border-slate-700 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="Q1" className="text-white">Q1</SelectItem>
                <SelectItem value="Q2" className="text-white">Q2</SelectItem>
                <SelectItem value="Q3" className="text-white">Q3</SelectItem>
                <SelectItem value="Q4" className="text-white">Q4</SelectItem>
              </SelectContent>
            </Select>
            
            <Select value={String(selectedYear)} onValueChange={(v) => setSelectedYear(Number(v))}>
              <SelectTrigger className="w-24 bg-slate-800 border-slate-700 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-slate-800 border-slate-700">
                <SelectItem value="2026" className="text-white">2026</SelectItem>
                <SelectItem value="2025" className="text-white">2025</SelectItem>
              </SelectContent>
            </Select>
            
            <Button
              onClick={downloadLeaderboardSlide}
              disabled={downloading}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              <Download className="w-4 h-4 mr-2" />
              {downloading ? "Downloading..." : "Download Slide"}
            </Button>
          </div>
        </div>
      </div>

      <div className="max-w-[1800px] mx-auto p-6">
        <div className="grid grid-cols-12 gap-6">
          {/* Main Leaderboard - 9 columns */}
          <div className="col-span-12 lg:col-span-9">
            {/* Search */}
            <div className="mb-4 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-500" />
              <input
                type="text"
                placeholder="Search employees..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Leaderboard Table */}
            <div className="rounded-xl overflow-hidden border border-slate-600" style={{ backgroundColor: COLORS.backgroundAlt }}>
              {/* Table Header - Desktop */}
              <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-3 bg-slate-900 text-sm font-semibold uppercase tracking-wider text-slate-300 border-b border-slate-600">
                <div className="col-span-1 text-center">Rank</div>
                <div className="col-span-3">Employee</div>
                <div className="col-span-2 text-center">Base Score</div>
                <div className="col-span-2 text-center">Reviews</div>
                <div className="col-span-1 text-center">Bonuses</div>
                <div className="col-span-2 text-center">Total</div>
                <div className="col-span-1 text-center">Trend</div>
              </div>
              
              {/* Table Header - Mobile */}
              <div className="md:hidden grid grid-cols-5 gap-1 px-2 py-2 bg-slate-900 text-xs font-semibold uppercase tracking-wider text-slate-300 border-b border-slate-600">
                <div className="col-span-1 text-center">#</div>
                <div className="col-span-2">Name</div>
                <div className="col-span-1 text-center">Base</div>
                <div className="col-span-1 text-center">Total</div>
              </div>

              {/* Table Body */}
              <div className="divide-y divide-slate-600/50">
                {filteredRankings.map((employee, idx) => {
                  const empData = getEmployeeDetails(employee.employee_id);
                  const isTop5 = employee.position <= 5;
                  const reviewMentions = empData.review_mentions || 0;
                  
                  // Score breakdown that adds up:
                  // Total = Base (weighted POS) + Reviews (CV + RT) + Bonuses (metric)
                  const baseScore = empData.weighted_score || 0;  // POS metrics weighted
                  const cvScore = empData.cv_score || 0;          // Customer Voice points
                  const rtBonus = empData.review_tracker_bonus || 0; // RT mentions bonus
                  const reviewScore = cvScore + rtBonus;          // Total review points
                  const metricBonus = empData.total_metric_bonus || 0; // Benchmark bonuses
                  const finalScore = empData.pre_dar_score || empData.total_score || employee.total_score || 0;
                  
                  // Calculate trend/momentum based on previous snapshot (match by name or report_name)
                  const reportName = empData.report_name || employee.report_name;
                  const momentum = calculateMomentum(employee.name, finalScore, reportName);
                  
                  return (
                    <div 
                      key={employee.employee_id}
                      className={`transition-all duration-200 hover:bg-slate-600/40 ${
                        idx % 2 === 0 ? "bg-slate-800/50" : "bg-slate-700/30"
                      } ${isTop5 ? "border-l-4 border-green-400" : ""}`}
                      data-testid={`leaderboard-row-${employee.position}`}
                    >
                      {/* Desktop Layout */}
                      <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-4 items-center">
                        {/* Rank */}
                        <div className="col-span-1 flex justify-center">
                          <RankBadge position={employee.position} tier={employee.tier_label} />
                        </div>
                        
                        {/* Employee Name & Recognition */}
                        <div className="col-span-3">
                          <div className="flex items-center gap-3">
                            <div>
                              <div className="font-bold text-white text-lg">{employee.name}</div>
                              <div className="flex items-center gap-2 mt-1">
                                <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${
                                  employee.tier_label?.includes("Trainer") ? "bg-purple-600/30 text-purple-300 border-purple-500/50" :
                                  employee.tier_label?.includes("Bartender") ? "bg-blue-600/30 text-blue-300 border-blue-500/50" :
                                  employee.tier_label?.includes("A-") ? "bg-green-600/30 text-green-300 border-green-500/50" :
                                  employee.tier_label?.includes("B-") ? "bg-yellow-600/30 text-yellow-300 border-yellow-500/50" :
                                  "bg-red-600/30 text-red-300 border-red-500/50"
                                }`}>
                                  {employee.tier_label || employee.job_title}
                                </span>
                                <RecognitionBadge mentions={reviewMentions} />
                              </div>
                            </div>
                          </div>
                        </div>
                        
                        {/* Base Score (Weighted POS) */}
                        <div className="col-span-2 text-center">
                          <div className="text-white font-semibold text-lg">{baseScore.toFixed(1)}</div>
                          <ScoreBar value={baseScore} max={75} benchmark={75} />
                          <div className="text-xs text-slate-400 mt-1">POS metrics</div>
                        </div>
                        
                        {/* Reviews (CV + RT) */}
                        <div className="col-span-2 text-center">
                          <div className={`font-semibold text-lg ${reviewScore >= 0 ? 'text-white' : 'text-red-400'}`}>
                            {reviewScore >= 0 ? '+' : ''}{reviewScore.toFixed(1)}
                          </div>
                          <div className="text-xs text-slate-400 mt-1">
                            CV: {cvScore >= 0 ? '+' : ''}{cvScore.toFixed(1)} | RT: +{rtBonus.toFixed(1)}
                          </div>
                        </div>
                        
                        {/* Metric Bonuses */}
                        <div className="col-span-1 text-center">
                          <div className={`font-medium ${metricBonus > 0 ? "text-green-400" : "text-slate-500"}`}>
                            {metricBonus > 0 ? `+${metricBonus.toFixed(1)}` : "0"}
                          </div>
                        </div>
                        
                        {/* Total Score */}
                        <div className="col-span-2 text-center">
                          <div className={`text-3xl font-bold ${
                            employee.position === 1 ? "text-yellow-400" :
                            employee.position <= 3 ? "text-slate-300" :
                            isTop5 ? "text-green-400" :
                            "text-white"
                          }`}>
                            {finalScore.toFixed(1)}
                          </div>
                          <div className="text-xs text-slate-500 mt-1">
                            = {baseScore.toFixed(0)} + {reviewScore.toFixed(0)} + {metricBonus.toFixed(0)}
                          </div>
                        </div>
                        
                        {/* Momentum */}
                        <div className="col-span-1 flex justify-center">
                          <MomentumIndicator trend={momentum.trend} change={momentum.change} />
                        </div>
                      </div>
                      
                      {/* Mobile Layout */}
                      <div className="md:hidden grid grid-cols-5 gap-1 px-2 py-3 items-center">
                        {/* Rank */}
                        <div className="col-span-1 flex justify-center">
                          <RankBadge position={employee.position} tier={employee.tier_label} />
                        </div>
                        
                        {/* Employee Name */}
                        <div className="col-span-2">
                          <div className="font-bold text-white text-sm truncate">{employee.name}</div>
                          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${
                            employee.tier_label?.includes("Trainer") ? "bg-purple-600/30 text-purple-300" :
                            employee.tier_label?.includes("Bartender") ? "bg-blue-600/30 text-blue-300" :
                            employee.tier_label?.includes("A-") ? "bg-green-600/30 text-green-300" :
                            employee.tier_label?.includes("B-") ? "bg-yellow-600/30 text-yellow-300" :
                            "bg-red-600/30 text-red-300"
                          }`}>
                            {employee.tier_label || employee.job_title}
                          </span>
                        </div>
                        
                        {/* Base Score */}
                        <div className="col-span-1 text-center">
                          <div className="text-white font-semibold text-sm">{baseScore.toFixed(1)}</div>
                          <ScoreBar value={baseScore} max={75} benchmark={75} />
                        </div>
                        
                        {/* Total Score */}
                        <div className="col-span-1 text-center">
                          <div className={`text-lg font-bold ${
                            employee.position === 1 ? "text-yellow-400" :
                            employee.position <= 3 ? "text-slate-300" :
                            isTop5 ? "text-green-400" :
                            "text-white"
                          }`}>
                            {finalScore.toFixed(1)}
                          </div>
                          <MomentumIndicator trend={momentum.trend} change={momentum.change} />
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Category Leaders Sidebar - 3 columns */}
          <div className="col-span-12 lg:col-span-3 space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Trophy className="w-5 h-5 text-yellow-500" />
              Category Leaders
            </h2>
            
            <CategoryLeaderCard
              title="PPA Leader"
              leader={categoryLeaders.ppa?.name}
              value={categoryLeaders.ppa?.ppa}
              format="currency"
              icon={TrendingUp}
            />
            
            <CategoryLeaderCard
              title="LBW Leader"
              leader={categoryLeaders.lbw?.name}
              value={categoryLeaders.lbw?.lbw_per_guest}
              format="currency"
              icon={TrendingUp}
            />
            
            <CategoryLeaderCard
              title="LSC Champion"
              leader={categoryLeaders.lsc?.name}
              value={categoryLeaders.lsc?.guests_per_lsc}
              format="ratio"
              icon={Star}
            />
            
            <CategoryLeaderCard
              title="Review Leader"
              leader={categoryLeaders.reviews?.name}
              value={categoryLeaders.reviews?.rt_mentions || categoryLeaders.reviews?.review_mentions}
              format="number"
              icon={Award}
            />
            
            {/* Scoring Legend */}
            <div className="bg-slate-800/50 rounded-lg p-4 border border-slate-700/50 mt-6">
              <h3 className="font-bold text-white mb-3 flex items-center gap-2">
                <Info className="w-4 h-4" />
                Scoring Guide
              </h3>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between text-slate-400">
                  <span>Metrics (75 max)</span>
                  <span className="text-blue-400">PPA, LSC, LBW, Glass</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Reviews (25 max)</span>
                  <span className="text-green-400">CV + RT</span>
                </div>
                <div className="flex justify-between text-slate-400">
                  <span>Metric Bonus</span>
                  <span className="text-yellow-400">+20 max</span>
                </div>
              </div>
              
              <div className="mt-4 pt-4 border-t border-slate-700/50">
                <h4 className="font-semibold text-white mb-2">Recognition Levels</h4>
                <div className="space-y-1 text-xs">
                  <div className="flex items-center gap-2">
                    <Star className="w-3 h-3 text-blue-400" />
                    <span className="text-slate-400">5+ mentions = Star</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Award className="w-3 h-3 text-purple-400" />
                    <span className="text-slate-400">10+ mentions = Top Reviewed</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Crown className="w-3 h-3 text-yellow-400" />
                    <span className="text-slate-400">20+ mentions = Leader</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
