import { useState, useEffect, useCallback, useMemo } from "react";
import { Trophy, Calendar, Filter, ChevronDown, ChevronUp, Download, FileText, Medal, Award, Star, Users, Image, MessageCircle, RefreshCw, Edit3, Check, X, Search, TrendingUp, TrendingDown, Target, ArrowUp } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { formatNumber, formatCurrency } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Tier badge colors (professional, no gimmicks)
const TIER_STYLES = {
  "Trainer": { bg: "bg-purple-100", text: "text-purple-800", border: "border-purple-200" },
  "Bartender": { bg: "bg-blue-100", text: "text-blue-800", border: "border-blue-200" },
  "A-Server": { bg: "bg-green-100", text: "text-green-800", border: "border-green-200" },
  "B-Server": { bg: "bg-yellow-100", text: "text-yellow-800", border: "border-yellow-200" },
  "C-Server": { bg: "bg-red-100", text: "text-red-800", border: "border-red-200" }
};

// V2 Metrics Configuration for Top 10 sections
const V2_METRICS = {
  ppa: { label: 'PPA', format: 'currency', higherBetter: true },
  lbw_per_guest: { label: 'LBW/Guest', format: 'currency', higherBetter: true },
  glassware_per_guest: { label: 'Glass/Guest', format: 'currency', higherBetter: true },
  guests_per_lsc: { label: 'Guests/LSC', format: 'number', higherBetter: false },
  cv_score: { label: 'CV Score', format: 'number', higherBetter: true },
  pre_dar_score: { label: 'Total Score', format: 'number', higherBetter: true },
};

export default function FullRankings() {
  const [rankings, setRankings] = useState([]);
  const [employees, setEmployees] = useState([]);
  const [quarterSettings, setQuarterSettings] = useState(null);
  const [npsData, setNpsData] = useState({});
  const [npsStats, setNpsStats] = useState(null);
  const [syncingNps, setSyncingNps] = useState(false);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const [downloadingPrintable, setDownloadingPrintable] = useState(false);
  const [downloadingReview, setDownloadingReview] = useState(null);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [tierFilter, setTierFilter] = useState("all");
  const [thresholds, setThresholds] = useState({ a_server_min: 85.1, b_server_min: 70.1 });
  const [totalEmployees, setTotalEmployees] = useState(0);
  const [expandedRow, setExpandedRow] = useState(null);
  const [backgrounds, setBackgrounds] = useState([]);
  const [selectedBackground, setSelectedBackground] = useState("dark");
  const [editingJobTitle, setEditingJobTitle] = useState(null); // employee_id being edited
  const [pendingJobTitle, setPendingJobTitle] = useState(""); // new job title value
  const [savingJobTitle, setSavingJobTitle] = useState(false);
  const [searchQuery, setSearchQuery] = useState(""); // Employee search

  // Filter rankings by search query
  const filteredRankings = useMemo(() => {
    if (!searchQuery.trim()) return rankings;
    const query = searchQuery.toLowerCase();
    return rankings.filter(emp => 
      emp.name.toLowerCase().includes(query) ||
      emp.job_title?.toLowerCase().includes(query) ||
      emp.tier_label?.toLowerCase().includes(query)
    );
  }, [rankings, searchQuery]);

  // Update employee job title
  const updateEmployeeJobTitle = async (employeeId, newJobTitle) => {
    setSavingJobTitle(true);
    try {
      await axios.put(`${API}/v2/employees/${employeeId}`, {
        job_title: newJobTitle
      });
      toast.success(`Updated to ${newJobTitle}`);
      setEditingJobTitle(null);
      // Refresh data to show updated tier
      fetchRankings();
    } catch (error) {
      console.error("Error updating job title:", error);
      toast.error("Failed to update job title");
    } finally {
      setSavingJobTitle(false);
    }
  };

  const fetchRankings = useCallback(async () => {
    setLoading(true);
    try {
      const tierParam = tierFilter !== "all" ? `&tier_filter=${tierFilter}` : "";
      const [rankingsRes, employeesRes, settingsRes, bgRes, npsRes] = await Promise.all([
        axios.get(`${API}/v2/full-rankings/${selectedYear}/${selectedQuarter}?${tierParam}`),
        axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`),
        axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`).catch(() => null),
        axios.get(`${API}/v2/snapshots/backgrounds`).catch(() => ({ data: [] })),
        axios.get(`${API}/v2/cv/nps?year=${selectedYear}&quarter=${selectedQuarter}`).catch(() => ({ data: { nps_records: [] } }))
      ]);
      
      setRankings(rankingsRes.data.rankings || []);
      setEmployees(employeesRes.data || []);
      setQuarterSettings(settingsRes?.data || null);
      setTotalEmployees(rankingsRes.data.total_employees || 0);
      setThresholds(rankingsRes.data.tier_thresholds || { a_server_min: 85.1, b_server_min: 70.1 });
      setBackgrounds(bgRes.data || []);
      
      // Build NPS lookup by employee_id
      const npsLookup = {};
      (npsRes.data.nps_records || []).forEach(record => {
        npsLookup[record.employee_id] = record;
      });
      setNpsData(npsLookup);
      
      // Also get NPS stats
      try {
        const statsRes = await axios.get(`${API}/v2/cv/stats?year=${selectedYear}&quarter=${selectedQuarter}`);
        setNpsStats(statsRes.data);
      } catch {
        setNpsStats(null);
      }
    } catch (error) {
      console.error("Error fetching rankings:", error);
      if (error.response?.status === 404) {
        toast.error(`No data found for ${selectedQuarter} ${selectedYear}`);
        setRankings([]);
      } else {
        toast.error("Error loading rankings");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter, tierFilter]);

  // Calculate metric rankings for all employees
  const getMetricRankings = useCallback(() => {
    if (!employees.length) return {};
    
    const metrics = {
      ppa: employees.map(e => ({ id: e.id, name: e.name, value: e.ppa || 0 })).sort((a, b) => b.value - a.value),
      lbw: employees.map(e => ({ id: e.id, name: e.name, value: e.lbw_per_guest || 0 })).sort((a, b) => b.value - a.value),
      glass: employees.map(e => ({ id: e.id, name: e.name, value: e.glassware_per_guest || 0 })).sort((a, b) => b.value - a.value),
      lsc: employees.map(e => ({ id: e.id, name: e.name, value: e.guests_per_lsc || 999 })).sort((a, b) => a.value - b.value), // Lower is better for LSC
      cv: employees.map(e => ({ id: e.id, name: e.name, value: e.cv_score || 0 })).sort((a, b) => b.value - a.value),
    };
    
    // Create lookup: employeeId -> { ppa: rank, lbw: rank, ... }
    const rankLookup = {};
    employees.forEach(e => {
      rankLookup[e.id] = {
        ppa: metrics.ppa.findIndex(m => m.id === e.id) + 1,
        lbw: metrics.lbw.findIndex(m => m.id === e.id) + 1,
        glass: metrics.glass.findIndex(m => m.id === e.id) + 1,
        lsc: metrics.lsc.findIndex(m => m.id === e.id) + 1,
        cv: metrics.cv.findIndex(m => m.id === e.id) + 1,
      };
    });
    
    return rankLookup;
  }, [employees]);
  
  const metricRankings = getMetricRankings();

  // Get employee details by ID
  const getEmployeeDetails = (employeeId) => {
    return employees.find(e => e.id === employeeId) || {};
  };

  // Get top employees for a specific metric
  const getTopEmployees = useCallback((metric, limit = 10) => {
    const config = V2_METRICS[metric];
    if (!config) return [];
    const valid = employees.filter((e) => e[metric] != null);

    const sorted = [...valid].sort((a, b) => {
      if (!config.higherBetter) return (a[metric] || 0) - (b[metric] || 0);
      return (b[metric] || 0) - (a[metric] || 0);
    });

    return sorted.slice(0, limit);
  }, [employees]);

  // Format metric value for display
  const formatMetricValue = (metric, value) => {
    if (value == null) return "N/A";
    const config = V2_METRICS[metric];
    if (!config) return formatNumber(value);
    
    switch (config.format) {
      case 'currency':
        return formatCurrency(value);
      default:
        return formatNumber(value);
    }
  };

  // Top 10 by each metric
  const topPerformers = useMemo(() => {
    const result = {};
    Object.keys(V2_METRICS).forEach(metric => {
      result[metric] = getTopEmployees(metric, 10);
    });
    return result;
  }, [getTopEmployees]);

  // Top 10 overall
  const topOverall = useMemo(() => {
    return getTopEmployees('pre_dar_score', 10);
  }, [getTopEmployees]);

  // Get icon for rank position
  const getMetricIcon = (rank) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-600" />;
    return <span className="text-sm font-bold text-slate-400">#{rank}</span>;
  };

  useEffect(() => {
    fetchRankings();
  }, [fetchRankings]);

  // Sync NPS from Loyalty Voice
  const handleSyncNps = async () => {
    setSyncingNps(true);
    toast.info("Syncing NPS from Loyalty Voice... This may take a minute.");
    try {
      const response = await axios.post(
        `${API}/v2/cv/sync?quarter=${selectedQuarter}&year=${selectedYear}`,
        {},
        { timeout: 180000 }  // 3 minute timeout for scraping
      );
      if (response.data.success) {
        toast.success(`Synced NPS for ${response.data.matched_count} employees`);
        // Refresh data
        fetchRankings();
      } else {
        toast.error(response.data.message || "NPS sync failed");
      }
    } catch (error) {
      console.error("Error syncing NPS:", error);
      if (error.code === 'ECONNABORTED') {
        toast.warning("NPS sync is taking longer than expected. It may still complete in the background.");
      } else {
        toast.error("Failed to sync NPS from Loyalty Voice");
      }
    } finally {
      setSyncingNps(false);
    }
  };

  // Get NPS for an employee
  const getEmployeeNps = (employeeId) => {
    const record = npsData[employeeId];
    return record ? record.nps_score : null;
  };

  // Format NPS with color coding
  const formatNps = (nps) => {
    if (nps === null || nps === undefined) return <span className="text-gray-400">—</span>;
    
    let colorClass = "text-slate-300";
    if (nps >= 50) colorClass = "text-green-600";
    else if (nps >= 0) colorClass = "text-yellow-600";
    else colorClass = "text-red-600";
    
    return <span className={`font-semibold ${colorClass}`}>{nps}%</span>;
  };

  const handleDownloadSlide = async () => {
    setDownloading(true);
    try {
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
      const filename = `rankings_${selectedQuarter}_${selectedYear}.png`;
      const url = `${API}/v2/yodeck/${selectedYear}/${selectedQuarter}/complete-rankings?format=16:9&background=${selectedBackground}`;
      
      if (isIOS) {
        // For iOS, open in new tab
        window.open(url, '_blank');
        toast.success("Rankings slide opened. Tap share to save.");
        setDownloading(false);
        return;
      }
      
      const response = await axios.get(url, { responseType: 'blob' });
      
      // Create download link
      const blob = new Blob([response.data], { type: 'image/png' });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      
      toast.success("Rankings slide downloaded!");
    } catch (error) {
      console.error("Error downloading slide:", error);
      toast.error("Failed to download slide");
    } finally {
      setDownloading(false);
    }
  };

  const handleDownloadPrintable = async () => {
    setDownloadingPrintable(true);
    try {
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
      const filename = `printable_rankings_${selectedQuarter}_${selectedYear}.png`;
      const url = `${API}/v2/yodeck/${selectedYear}/${selectedQuarter}/printable-rankings?format=16:9`;
      
      if (isIOS) {
        window.open(url, '_blank');
        toast.success("Printable rankings opened. Tap share to save.");
        setDownloadingPrintable(false);
        return;
      }
      
      const response = await axios.get(url, { responseType: 'blob' });
      
      const blob = new Blob([response.data], { type: 'image/png' });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      
      toast.success("Printable rankings downloaded!");
    } catch (error) {
      console.error("Error downloading printable rankings:", error);
      toast.error("Failed to download printable rankings");
    } finally {
      setDownloadingPrintable(false);
    }
  };

  const handleDownloadReview = async (employeeId, employeeName) => {
    setDownloadingReview(employeeId);
    try {
      const response = await axios.post(
        `${API}/v2/employees/${employeeId}/generate-review`,
        { quarter: selectedQuarter, year: selectedYear },
        { responseType: 'blob' }
      );
      
      const blob = new Blob([response.data], { type: 'application/pdf' });
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.setAttribute('download', `${employeeName.replace(/\s+/g, '_')}_Review_${selectedQuarter}_${selectedYear}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => window.URL.revokeObjectURL(objectUrl), 1000);
      
      toast.success(`Review downloaded for ${employeeName}`);
    } catch (error) {
      console.error("Error downloading review:", error);
      toast.error(`Failed to download review for ${employeeName}`);
    } finally {
      setDownloadingReview(null);
    }
  };

  const getTierStyle = (tier) => {
    return TIER_STYLES[tier] || { bg: "bg-slate-700", text: "text-gray-800", border: "border-gray-200" };
  };

  const renderPointsCell = (points) => {
    const earned = points?.earned ?? 0;
    const possible = points?.possible ?? 0;
    const percentage = possible > 0 ? (earned / possible) * 100 : 0;
    
    return (
      <div className="text-center">
        <div className="font-semibold text-sm">
          {formatNumber(earned)} / {possible}
        </div>
        <div className="w-full bg-gray-200 rounded-full h-1.5 mt-1">
          <div 
            className={`h-1.5 rounded-full ${percentage >= 80 ? 'bg-green-500' : percentage >= 50 ? 'bg-yellow-500' : 'bg-red-500'}`}
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      <div className="splash-red" style={{ top: '10%', right: '5%' }} />
      <div className="splash-blue" style={{ bottom: '15%', left: '3%', opacity: 0.5 }} />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Trophy className="w-8 h-8 text-secondary" />
              <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
                Full Rankings
              </h1>
            </div>
            <p className="text-slate-400" data-testid="page-subtitle">
              Complete team standings with hierarchy-based tiering
            </p>
          </div>
          
          {/* Download Slide with Background Selector */}
          <div className="flex items-center gap-3 flex-wrap">
            {/* Background selector */}
            {backgrounds.length > 0 && (
              <Select value={selectedBackground} onValueChange={setSelectedBackground}>
                <SelectTrigger className="w-44" data-testid="background-select">
                  <SelectValue placeholder="Background" />
                </SelectTrigger>
                <SelectContent>
                  {backgrounds.map((bg) => (
                    <SelectItem key={bg.key} value={bg.key}>
                      <div className="flex items-center gap-2">
                        {bg.preview ? (
                          <img src={bg.preview} alt="" className="w-6 h-4 rounded object-cover" />
                        ) : (
                          <div className="w-6 h-4 rounded bg-[#0f172a]" />
                        )}
                        <span>{bg.name}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            
            <Button
              onClick={handleDownloadSlide}
              disabled={downloading || rankings.length === 0}
              className="bg-primary hover:bg-primary/90 text-white flex items-center gap-2"
              data-testid="download-slide-btn"
            >
              {downloading ? (
                <>
                  <div className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                  Generating...
                </>
              ) : (
                <>
                  <Download className="w-4 h-4" />
                  Full Slide
                </>
              )}
            </Button>
            
            <Button
              onClick={handleDownloadPrintable}
              disabled={downloadingPrintable || rankings.length === 0}
              variant="outline"
              className="border-amber-500 text-amber-600 hover:bg-amber-50 flex items-center gap-2"
              data-testid="download-printable-btn"
            >
              {downloadingPrintable ? (
                <>
                  <div className="animate-spin h-4 w-4 border-2 border-amber-500 border-t-transparent rounded-full" />
                  Generating...
                </>
              ) : (
                <>
                  <Star className="w-4 h-4" />
                  Printable
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Filters Card */}
        <div className="bubba-card mb-6" data-testid="filters-card">
          <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <Filter className="w-5 h-5 text-secondary" />
              </div>
              <h2 className="text-lg font-serif font-bold text-foreground">Filters</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Quarter Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300 flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Quarter
                </label>
                <div className="flex gap-2">
                  <select 
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                    className="flex-1 h-10 px-3 border-2 border-slate-600 rounded-lg bg-slate-800 text-white focus:border-secondary"
                    data-testid="year-select"
                  >
                    <option value={2024}>2024</option>
                    <option value={2025}>2025</option>
                    <option value={2026}>2026</option>
                    <option value={2027}>2027</option>
                  </select>
                  <select
                    value={selectedQuarter}
                    onChange={(e) => setSelectedQuarter(e.target.value)}
                    className="flex-1 h-10 px-3 border-2 border-slate-600 rounded-lg bg-slate-800 text-white focus:border-secondary"
                    data-testid="quarter-select"
                  >
                    <option value="Q1">Q1</option>
                    <option value="Q2">Q2</option>
                    <option value="Q3">Q3</option>
                    <option value="Q4">Q4</option>
                  </select>
                </div>
              </div>
              
              {/* Tier Filter */}
              <div className="space-y-2">
                <label className="text-sm font-medium text-slate-300">Filter by Tier</label>
                <Select value={tierFilter} onValueChange={setTierFilter}>
                  <SelectTrigger data-testid="tier-filter" className="border-2 border-slate-600 bg-slate-800 text-white">
                    <SelectValue placeholder="All Tiers" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Tiers</SelectItem>
                    <SelectItem value="Trainer">Trainers</SelectItem>
                    <SelectItem value="Bartender">Bartenders</SelectItem>
                    <SelectItem value="A-Server">A-Servers</SelectItem>
                    <SelectItem value="B-Server">B-Servers</SelectItem>
                    <SelectItem value="C-Server">C-Servers</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Threshold Display */}
              <div className="space-y-2 md:col-span-2">
                <label className="text-sm font-medium text-slate-300">Score Thresholds (from Settings)</label>
                <div className="flex gap-4 text-sm">
                  <span className="px-3 py-2 bg-green-600 border border-green-500 rounded-lg">
                    <span className="font-medium text-white">A-Server:</span> <span className="text-green-100">≥ {thresholds.a_server_min}</span>
                  </span>
                  <span className="px-3 py-2 bg-yellow-600 border border-yellow-500 rounded-lg">
                    <span className="font-medium text-white">B-Server:</span> <span className="text-yellow-100">≥ {thresholds.b_server_min}</span>
                  </span>
                  <span className="px-3 py-2 bg-red-600 border border-red-500 rounded-lg">
                    <span className="font-medium text-white">C-Server:</span> <span className="text-red-100">&lt; {thresholds.b_server_min}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Search Bar - Mobile Friendly */}
        <div className="mb-4 flex flex-col sm:flex-row gap-4 items-stretch sm:items-center justify-between" data-testid="search-and-summary">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search employee name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-3 bg-slate-800 border-2 border-slate-600 rounded-xl text-white placeholder-slate-400 focus:border-primary focus:outline-none"
              data-testid="employee-search"
            />
            {searchQuery && (
              <button 
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
          <div className="flex items-center gap-3 text-sm">
            <p className="text-slate-400">
              Showing <span className="text-primary font-bold">{filteredRankings.length}</span> of {totalEmployees}
              {npsStats && npsStats.total_servers > 0 && (
                <span className="ml-2 hidden sm:inline">
                  • <MessageCircle className="w-3 h-3 inline" /> {npsStats.avg_nps}% NPS
                </span>
              )}
            </p>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSyncNps}
              disabled={syncingNps}
              className="flex items-center gap-2 text-xs border-blue-500 text-blue-400 hover:bg-blue-900/30"
              data-testid="sync-nps-btn"
            >
              {syncingNps ? (
                <div className="animate-spin h-3 w-3 border-2 border-blue-400 border-t-transparent rounded-full" />
              ) : (
                <RefreshCw className="w-3 h-3" />
              )}
              <span className="hidden sm:inline">Sync</span>
            </Button>
          </div>
        </div>

        {/* Rankings Table */}
        {filteredRankings.length === 0 ? (
          <div className="bubba-card p-12 text-center" data-testid="no-results">
            <Trophy className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-serif font-bold mb-2">
              {searchQuery ? "No matches found" : "No rankings found"}
            </h3>
            <p className="text-slate-400">
              {searchQuery 
                ? `No employees match "${searchQuery}". Try a different search.`
                : `No data for ${selectedQuarter} ${selectedYear}. Upload employee data on the Dashboard.`
              }
            </p>
          </div>
        ) : (
          <div className="bubba-card overflow-hidden" data-testid="rankings-table-container">
            <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
            <div className="overflow-x-auto pt-4 max-h-[70vh] overflow-y-auto">
              <table className="w-full" data-testid="rankings-table">
                <thead className="sticky top-0 z-10">
                  <tr className="bg-gradient-to-r from-secondary to-primary text-white shadow-lg">
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider">Position</th>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider">Employee</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider">Tier</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider">Total Score</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden md:table-cell">Customer Voice</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden lg:table-cell">Review Tracker</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden lg:table-cell">Metric Bonus</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell">PPA (25%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell">LBW (20%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell">LSC (25%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell">Glass (15%)</th>
                    <th className="px-2 py-3 text-center text-xs font-bold uppercase tracking-wider"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {filteredRankings.map((employee, index) => {
                    const tierStyle = getTierStyle(employee.tier_label);
                    const isExpanded = expandedRow === employee.employee_id;
                    
                    // Find the employee ranked just above this one for "To Pass" comparison
                    const employeeAbove = filteredRankings.find(e => e.peer_rank === (employee.peer_rank || 0) - 1);
                    
                    return (
                      <>
                        <tr 
                          key={employee.employee_id}
                          className={`${index % 2 === 0 ? 'bg-slate-800' : 'bg-background'} hover:bg-slate-700 transition-colors cursor-pointer`}
                          data-testid={`ranking-row-${employee.position}`}
                        >
                          {/* Position */}
                          <td className="px-4 py-4">
                            <div className="flex items-center gap-2">
                              <span className="text-2xl font-serif font-black text-gray-300">{employee.position}</span>
                              <span className={`inline-block w-10 text-center px-2 py-1 rounded text-xs font-bold ${tierStyle.bg} ${tierStyle.text} ${tierStyle.border} border`}>
                                {employee.position_label}
                              </span>
                            </div>
                          </td>
                          
                          {/* Employee Name */}
                          <td className="px-4 py-4">
                            <div>
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-foreground" data-testid={`employee-name-${employee.position}`}>
                                  {employee.name}
                                </span>
                                {(() => {
                                  const percentile = Math.round((1 - (employee.position - 1) / totalEmployees) * 100);
                                  if (percentile >= 90) return <span className="inline-flex items-center justify-center w-16 px-1.5 py-0.5 bg-green-600 text-white text-xs font-bold rounded">Top 10%</span>;
                                  if (percentile >= 75) return <span className="inline-flex items-center justify-center w-16 px-1.5 py-0.5 bg-blue-600 text-white text-xs font-bold rounded">Top 25%</span>;
                                  if (percentile >= 50) return <span className="inline-flex items-center justify-center w-16 px-1.5 py-0.5 bg-yellow-600 text-white text-xs font-bold rounded">Top 50%</span>;
                                  return <span className="inline-flex w-16"></span>; {/* Empty placeholder for alignment */}
                                })()}
                              </div>
                              <div className="text-xs text-slate-400">{employee.job_title}</div>
                            </div>
                          </td>
                          
                          {/* Tier Badge */}
                          <td className="px-4 py-4 text-center">
                            <span className={`inline-block w-20 text-center px-3 py-1 rounded-full text-xs font-bold ${tierStyle.bg} ${tierStyle.text}`}>
                              {employee.tier_label}
                            </span>
                          </td>
                          
                          {/* Total Score */}
                          <td className="px-4 py-4 text-center">
                            <span className="text-xl font-serif font-black text-primary" data-testid={`total-score-${employee.position}`}>
                              {formatNumber(employee.total_score)}
                            </span>
                          </td>
                          
                          {/* NPS Score */}
                          <td className="px-4 py-4 text-center" data-testid={`nps-score-${employee.position}`}>
                            {formatNps(getEmployeeNps(employee.employee_id))}
                          </td>
                          
                          {/* Review Bonus: RT mentions × 0.2 */}
                          <td className="px-4 py-4 text-center">
                            <span className="text-sm font-semibold text-green-600">
                              +{formatNumber(employee.review_bonus || 0)}
                            </span>
                          </td>
                          
                          {/* Metric Bonus: exceeding benchmarks */}
                          <td className="px-4 py-4 text-center">
                            <span className="text-sm font-semibold text-blue-600">
                              +{formatNumber(employee.metric_bonus || 0)}
                            </span>
                          </td>
                          
                          {/* PPA Points */}
                          <td className="px-4 py-4">
                            {renderPointsCell(employee.ppa_points)}
                          </td>
                          
                          {/* LBW Points */}
                          <td className="px-4 py-4">
                            {renderPointsCell(employee.lbw_points)}
                          </td>
                          
                          {/* LSC Points */}
                          <td className="px-4 py-4">
                            {renderPointsCell(employee.lsc_points)}
                          </td>
                          
                          {/* Glassware Points */}
                          <td className="px-4 py-4">
                            {renderPointsCell(employee.glassware_points)}
                          </td>
                          
                          {/* Actions: Download Review + Expand */}
                          <td className="px-2 py-4">
                            <div className="flex items-center gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDownloadReview(employee.employee_id, employee.name)}
                                disabled={downloadingReview === employee.employee_id}
                                className="p-1 text-primary hover:bg-primary/10"
                                title="Download Review PDF"
                                data-testid={`download-review-${employee.position}`}
                              >
                                {downloadingReview === employee.employee_id ? (
                                  <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                                ) : (
                                  <FileText className="w-4 h-4" />
                                )}
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setExpandedRow(isExpanded ? null : employee.employee_id)}
                                className="p-1"
                              >
                                {isExpanded ? (
                                  <ChevronUp className="w-4 h-4" />
                                ) : (
                                  <ChevronDown className="w-4 h-4" />
                                )}
                              </Button>
                            </div>
                          </td>
                        </tr>
                        
                        {/* Expanded Details Row */}
                        {isExpanded && (
                          <tr key={`${employee.employee_id}-details`} className="bg-slate-900">
                            <td colSpan={12} className="px-6 py-5">
                              {(() => {
                                const emp = getEmployeeDetails(employee.employee_id);
                                const ranks = metricRankings[employee.employee_id] || {};
                                const total = employees.length;
                                const benchmarks = quarterSettings || {};
                                
                                const metrics = [
                                  {
                                    label: 'PPA',
                                    value: `$${(emp.ppa || 0).toFixed(2)}`,
                                    benchmark: `Benchmark: $${benchmarks.benchmark_ppa || 55}`,
                                    rank: ranks.ppa,
                                    total,
                                    color: (emp.ppa || 0) >= (benchmarks.benchmark_ppa || 55) ? 'text-green-600' : 'text-red-600'
                                  },
                                  {
                                    label: 'LBW/Guest',
                                    value: `$${(emp.lbw_per_guest || 0).toFixed(2)}`,
                                    benchmark: `Benchmark: $${benchmarks.benchmark_lbw || 8}`,
                                    rank: ranks.lbw,
                                    total,
                                    color: (emp.lbw_per_guest || 0) >= (benchmarks.benchmark_lbw || 8) ? 'text-green-600' : 'text-red-600'
                                  },
                                  {
                                    label: 'Glassware/Guest',
                                    value: `$${(emp.glassware_per_guest || 0).toFixed(2)}`,
                                    benchmark: `Benchmark: $${benchmarks.benchmark_glass || 1.25}`,
                                    rank: ranks.glass,
                                    total,
                                    color: (emp.glassware_per_guest || 0) >= (benchmarks.benchmark_glass || 1.25) ? 'text-green-600' : 'text-red-600'
                                  },
                                  {
                                    label: 'Guests/LSC',
                                    value: (emp.guests_per_lsc || 0).toFixed(1),
                                    benchmark: `Benchmark: ≤${benchmarks.benchmark_lsc || 100}`,
                                    rank: ranks.lsc,
                                    total,
                                    color: (emp.guests_per_lsc || 999) <= (benchmarks.benchmark_lsc || 100) ? 'text-green-600' : 'text-red-600'
                                  },
                                  {
                                    label: 'Review Tracker',
                                    value: `+${(emp.review_tracker_bonus || 0).toFixed(1)}`,
                                    benchmark: `${emp.review_mentions || 0} mentions × 0.2`,
                                    rank: null,
                                    total: null,
                                    color: 'text-green-600'
                                  }
                                ];
                                
                                // Get NPS score for this employee
                                const empNps = getEmployeeNps(employee.employee_id);
                                
                                return (
                                  <div className="space-y-4">
                                    <div className="flex items-center gap-2 mb-3">
                                      <span className="text-lg font-serif font-bold text-slate-200">Metric Breakdown</span>
                                      <span className="text-sm text-slate-400">• {employee.name}</span>
                                    </div>
                                    
                                    <div className="grid grid-cols-6 gap-4">
                                      {metrics.map((m, i) => (
                                        <div key={i} className="bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-600">
                                          <div className="text-xs font-semibold text-slate-400 uppercase mb-2">{m.label}</div>
                                          <div className={`text-2xl font-bold ${m.color}`}>{m.value}</div>
                                          <div className="text-xs text-slate-400 mt-1">{m.benchmark}</div>
                                          <div className="mt-2 pt-2 border-t border-slate-600">
                                            {m.rank !== null ? (
                                              <span className="inline-flex items-center px-2 py-1 bg-blue-600 text-white rounded-full text-xs font-semibold">
                                                {m.rank}{m.rank === 1 ? 'st' : m.rank === 2 ? 'nd' : m.rank === 3 ? 'rd' : 'th'} of {m.total}
                                              </span>
                                            ) : (
                                              <span className="inline-flex items-center px-2 py-1 bg-green-600 text-white rounded-full text-xs font-semibold">
                                                Bonus Points
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                      
                                      {/* NPS Card */}
                                      <div className="bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-600">
                                        <div className="text-xs font-semibold text-slate-400 uppercase mb-2 flex items-center gap-1">
                                          <MessageCircle className="w-3 h-3" />
                                          NPS Score
                                        </div>
                                        <div className={`text-2xl font-bold ${empNps !== null ? (empNps >= 50 ? 'text-green-400' : empNps >= 0 ? 'text-yellow-400' : 'text-red-400') : 'text-gray-400'}`}>
                                          {empNps !== null ? `${empNps}%` : '—'}
                                        </div>
                                        <div className="text-xs text-slate-400 mt-1">Customer Voice</div>
                                        <div className="mt-2 pt-2 border-t border-slate-600">
                                          <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-semibold ${
                                            empNps !== null 
                                              ? (empNps >= 50 ? 'bg-green-600 text-white' : empNps >= 0 ? 'bg-yellow-600 text-white' : 'bg-red-600 text-white')
                                              : 'bg-slate-700 text-slate-400'
                                          }`}>
                                            {empNps !== null ? (empNps >= 50 ? 'Promoter' : empNps >= 0 ? 'Passive' : 'Detractor') : 'No Data'}
                                          </span>
                                        </div>
                                      </div>
                                    </div>
                                    
                                    {/* Summary Row with Editable Job Title */}
                                    <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-800 rounded-xl p-4 shadow-sm border border-slate-600 mt-4">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm text-slate-400">Job Title:</span>
                                        {editingJobTitle === employee.employee_id ? (
                                          <div className="flex items-center gap-2">
                                            <Select 
                                              value={pendingJobTitle} 
                                              onValueChange={setPendingJobTitle}
                                            >
                                              <SelectTrigger className="w-36 h-8 bg-slate-700 border-slate-500 text-white text-sm">
                                                <SelectValue />
                                              </SelectTrigger>
                                              <SelectContent>
                                                <SelectItem value="Trainer">Trainer</SelectItem>
                                                <SelectItem value="Bartender">Bartender</SelectItem>
                                                <SelectItem value="Server">Server</SelectItem>
                                              </SelectContent>
                                            </Select>
                                            <Button
                                              size="sm"
                                              variant="ghost"
                                              onClick={() => updateEmployeeJobTitle(employee.employee_id, pendingJobTitle)}
                                              disabled={savingJobTitle}
                                              className="h-8 w-8 p-0 text-green-400 hover:text-green-300 hover:bg-green-900/30"
                                              data-testid={`save-job-title-${employee.position}`}
                                            >
                                              {savingJobTitle ? (
                                                <div className="w-4 h-4 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
                                              ) : (
                                                <Check className="w-4 h-4" />
                                              )}
                                            </Button>
                                            <Button
                                              size="sm"
                                              variant="ghost"
                                              onClick={() => setEditingJobTitle(null)}
                                              className="h-8 w-8 p-0 text-red-400 hover:text-red-300 hover:bg-red-900/30"
                                            >
                                              <X className="w-4 h-4" />
                                            </Button>
                                          </div>
                                        ) : (
                                          <div className="flex items-center gap-2">
                                            <span className={`px-3 py-1 rounded-full text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
                                              {emp?.job_title || employee.job_title || 'Server'}
                                            </span>
                                            <Button
                                              size="sm"
                                              variant="ghost"
                                              onClick={() => {
                                                setEditingJobTitle(employee.employee_id);
                                                setPendingJobTitle(emp?.job_title || employee.job_title || 'Server');
                                              }}
                                              className="h-7 w-7 p-0 text-slate-400 hover:text-white hover:bg-slate-700"
                                              title="Edit job title"
                                              data-testid={`edit-job-title-${employee.position}`}
                                            >
                                              <Edit3 className="w-3.5 h-3.5" />
                                            </Button>
                                          </div>
                                        )}
                                      </div>
                                      <div>
                                        <span className="text-sm text-slate-400">Tier:</span>
                                        <span className={`ml-2 px-3 py-1 rounded-full text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
                                          {employee.tier_label}
                                        </span>
                                      </div>
                                      <div>
                                        <span className="text-sm text-slate-400">Total Bonus:</span>
                                        <span className="ml-2 text-lg font-bold text-green-400">+{formatNumber(employee.bonus_points)}</span>
                                      </div>
                                      <div>
                                        <span className="text-sm text-slate-400">Overall Rank:</span>
                                        <span className="ml-2 text-lg font-bold text-primary">#{employee.peer_rank || employee.position} of {totalEmployees}</span>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })()}
                            </td>
                          </tr>
                        )}
                      </>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Top 10 Performers Sections */}
        <div className="mt-10 space-y-8" data-testid="top-performers-section">
          {/* Section Header */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
              <Trophy className="w-5 h-5 text-yellow-600" />
            </div>
            <div>
              <h2 className="text-2xl font-serif font-bold text-foreground">Top 10 Performers</h2>
              <p className="text-sm text-slate-400">Excellence in each performance category</p>
            </div>
          </div>

          {/* Top 10 Overall */}
          <div className="bubba-card" data-testid="top-overall-card">
            <div className="tape tape-blue" style={{ top: '-8px', left: '30%', transform: 'rotate(-2deg)' }} />
            <div className="p-5 pt-8">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
                  <Trophy className="w-5 h-5 text-yellow-600" />
                </div>
                <div>
                  <h3 className="text-xl font-serif font-bold text-foreground">Top 10 Overall</h3>
                  <p className="text-sm text-slate-400">Highest performers by Total Score</p>
                </div>
              </div>
              
              <div className="space-y-3">
                {topOverall.map((employee, index) => (
                  <div
                    key={employee.id}
                    className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:bg-background transition-colors"
                    data-testid={`top-overall-${index + 1}`}
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex items-center justify-center w-10 h-10 bg-slate-700 rounded-full">
                        {getMetricIcon(index + 1)}
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground">{employee.name}</h4>
                        <p className="text-sm text-slate-400 capitalize">{employee.tier_label || employee.job_title || 'Server'}</p>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-2xl font-serif font-bold text-primary">
                        {formatNumber(employee.pre_dar_score)}
                      </div>
                      <div className="text-sm text-slate-400">Total Score</div>
                    </div>
                  </div>
                ))}
              </div>

              {topOverall.length === 0 && (
                <div className="text-center py-8 text-gray-400">
                  <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>No total score data available</p>
                </div>
              )}
            </div>
          </div>

          {/* Top 10 by Each Metric */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {Object.entries(V2_METRICS).filter(([key]) => key !== 'pre_dar_score').map(([metricKey, metricInfo]) => {
              const performers = topPerformers[metricKey] || [];
              
              return (
                <div key={metricKey} className="bubba-card" data-testid={`top-10-${metricKey}`}>
                  <div className="p-5">
                    <h3 className="text-lg font-serif font-bold text-foreground mb-1">
                      Top 10 - {metricInfo.label}
                    </h3>
                    <p className="text-sm text-slate-400 mb-4">
                      {!metricInfo.higherBetter 
                        ? `Best ${metricInfo.label} performers (lower is better)`
                        : `Highest ${metricInfo.label} performers`
                      }
                    </p>
                  
                    <div className="space-y-2">
                      {performers.map((employee, index) => (
                        <div 
                          key={employee.id} 
                          className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-background transition-colors"
                        >
                          <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-8 h-8 bg-slate-700 rounded-full text-sm font-bold text-primary">
                              {index + 1}
                            </div>
                            
                            <div>
                              <h4 className="font-semibold text-foreground text-sm">{employee.name}</h4>
                              <p className="text-xs text-slate-400 capitalize">{employee.tier_label || employee.job_title || 'Server'}</p>
                            </div>
                          </div>
                          
                          <div className="text-right">
                            <div className="text-lg font-serif font-bold text-primary">
                              {formatMetricValue(metricKey, employee[metricKey])}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                    
                    {performers.length === 0 && (
                      <div className="text-center py-8 text-gray-400">
                        <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                        <p>No performance data available for this metric</p>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Legend */}
        <div className="mt-6 bubba-card p-4">
          <div className="text-sm text-slate-300">
            <span className="font-semibold">Hierarchy Order:</span> Trainers → Bartenders → A-Servers → B-Servers → C-Servers
            <span className="ml-4">|</span>
            <span className="ml-4">Within each tier, employees are sorted by Total Score (highest first)</span>
          </div>
        </div>
      </div>
    </div>
  );
}
