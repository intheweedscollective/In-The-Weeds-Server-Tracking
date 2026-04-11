import { useState, useEffect, useCallback, useMemo } from "react";
import { useLocation } from "react-router-dom";
import { Trophy, Calendar, Filter, ChevronDown, ChevronUp, Download, FileText, Medal, Award, Star, Users, Image, MessageCircle, RefreshCw, Edit3, Check, X, Search, TrendingUp, TrendingDown, Target, ArrowUp, Info } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "../components/ui/tooltip";
import { formatNumber, formatCurrency } from "../utils/formatters";
import { TrendIndicator } from "../components/TrendIndicator";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

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
  cv_score: { label: 'Customer Voice', format: 'number', higherBetter: true },
  pre_dar_score: { label: 'Total Score', format: 'number', higherBetter: true },
  rt_mentions: { label: 'Review Mentions', format: 'number', higherBetter: true },
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
  const [selectedBackground, setSelectedBackground] = useState("rainbow_bubbles");
  const [editingJobTitle, setEditingJobTitle] = useState(null); // employee_id being edited
  const [pendingJobTitle, setPendingJobTitle] = useState(""); // new job title value
  const [savingJobTitle, setSavingJobTitle] = useState(false);
  const [searchQuery, setSearchQuery] = useState(""); // Employee search
  const [momentumData, setMomentumData] = useState({}); // Momentum/trend data for all employees
  
  // Use location to detect route changes
  const location = useLocation();

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
      await api.put(`/v2/snapshot-workflow/employees/${employeeId}`, {
        job_title: newJobTitle
      });
      toast.success(`Updated to ${newJobTitle}`);
      setEditingJobTitle(null);
      // Refresh data to show updated tier
      fetchRankings();
    } catch (error) {
      toast.error("Failed to update job title");
    } finally {
      setSavingJobTitle(false);
    }
  };

  const fetchRankings = useCallback(async () => {
    setLoading(true);
    try {
      const tierParam = tierFilter !== "all" ? `&tier_filter=${tierFilter}` : "";
      const [rankingsRes, snapshotRes, settingsRes, bgRes, npsRes, momentumRes] = await Promise.all([
        api.get(`/v2/full-rankings/${selectedYear}/${selectedQuarter}?${tierParam}`),
        api.get(`/v2/snapshot-workflow/current-rankings?year=${selectedYear}&quarter=${selectedQuarter}`),
        api.get(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}`).catch(() => null),
        api.get(`/v2/snapshots/backgrounds`).catch(() => ({ data: [] })),
        api.get(`/v2/cv/nps?year=${selectedYear}&quarter=${selectedQuarter}`).catch(() => ({ data: { nps_records: [] } })),
        api.get(`/v2/trends/momentum/${selectedYear}/${selectedQuarter}`).catch(() => ({ data: {} }))
      ]);
      
      setRankings(rankingsRes.data.rankings || []);
      // Use snapshot employees for consistency across all pages
      setEmployees(snapshotRes.data?.employees || []);
      setQuarterSettings(settingsRes?.data || null);
      setTotalEmployees(rankingsRes.data.total_employees || 0);
      setThresholds(rankingsRes.data.tier_thresholds || { a_server_min: 85.1, b_server_min: 70.1 });
      setBackgrounds(bgRes.data || []);
      setMomentumData(momentumRes.data || {});
      
      // Build NPS lookup by employee_id
      const npsLookup = {};
      (npsRes.data.nps_records || []).forEach(record => {
        npsLookup[record.employee_id] = record;
      });
      setNpsData(npsLookup);
      
      // Also get NPS stats
      try {
        const statsRes = await api.get(`/v2/cv/stats?year=${selectedYear}&quarter=${selectedQuarter}`);
        setNpsStats(statsRes.data);
      } catch {
        setNpsStats(null);
      }
    } catch (error) {
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

  // Refresh when navigating to this page or when window gains focus
  useEffect(() => {
    fetchRankings();
    
    const handleFocus = () => {
      fetchRankings();
    };
    
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [location.key, fetchRankings]);

  // Sync NPS from Loyalty Voice
  const handleSyncNps = async () => {
    setSyncingNps(true);
    toast.info("Syncing NPS from Loyalty Voice... This may take a minute.");
    try {
      const response = await api.post(
        `/v2/cv/sync?quarter=${selectedQuarter}&year=${selectedYear}`,
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
      const apiPath = `/v2/yodeck/${selectedYear}/${selectedQuarter}/complete-rankings?format=16:9&background=${selectedBackground}`;
      
      if (isIOS) {
        // For iOS, open in new tab with full URL
        window.open(`${BACKEND_URL}/api${apiPath}`, '_blank');
        toast.success("Rankings slide opened. Tap share to save.");
        setDownloading(false);
        return;
      }
      
      const response = await api.get(apiPath, { responseType: 'blob' });
      
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
      const apiPath = `/v2/yodeck/${selectedYear}/${selectedQuarter}/printable-rankings?format=16:9`;
      
      if (isIOS) {
        window.open(`${BACKEND_URL}/api${apiPath}`, '_blank');
        toast.success("Printable rankings opened. Tap share to save.");
        setDownloadingPrintable(false);
        return;
      }
      
      const response = await api.get(apiPath, { responseType: 'blob' });
      
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
      toast.error("Failed to download printable rankings");
    } finally {
      setDownloadingPrintable(false);
    }
  };

  const handleDownloadReview = async (employeeId, employeeName) => {
    setDownloadingReview(employeeId);
    try {
      const response = await api.post(
        `/v2/employees/${employeeId}/generate-review`,
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
                  <tr className="bg-gradient-to-r from-secondary to-primary shadow-lg" style={{ color: 'white' }}>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-white">Position</th>
                    <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-white">Employee</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-white">Tier</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-white">Total Score</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden md:table-cell text-white">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger className="flex items-center justify-center gap-1 cursor-help">
                            Cust. Voice <Info className="w-3 h-3 opacity-60" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-800 text-white p-3 max-w-xs">
                            <div className="text-xs space-y-1">
                              <div className="font-bold mb-1">Customer Voice (Combined Total):</div>
                              <div className="font-semibold text-primary">Promoter/Detractor Points:</div>
                              <div>• Each Promoter (9-10) = +0.5 pt</div>
                              <div>• Each Detractor (≤6) = -1 pt</div>
                              <div className="mt-2 text-green-400 font-semibold">No cap on CV points!</div>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden lg:table-cell text-white">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger className="flex items-center justify-center gap-1 cursor-help">
                            RT Bonus <Info className="w-3 h-3 opacity-60" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-800 text-white p-3 max-w-xs">
                            <div className="text-xs space-y-1">
                              <div className="font-bold mb-1">Review Tracker Bonus:</div>
                              <div>• Each mention = +0.5 pts</div>
                              <div>• Capped at 15 pts max</div>
                              <div className="mt-1 text-slate-400">From ReviewTrackers.com</div>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden lg:table-cell text-white">Metric Bonus</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden md:table-cell text-white">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger className="flex items-center justify-center gap-1 cursor-help">
                            Trend <Info className="w-3 h-3 opacity-60" />
                          </TooltipTrigger>
                          <TooltipContent className="bg-slate-800 text-white p-3 max-w-xs">
                            <div className="text-xs space-y-1">
                              <div className="font-bold mb-1">Momentum Indicator:</div>
                              <div>Compares current score to rolling average</div>
                              <div className="mt-1 text-green-400">↑ = Improving</div>
                              <div className="text-red-400">↓ = Declining</div>
                              <div className="text-slate-400">— = Stable</div>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell text-white">PPA (25%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell text-white">LBW (20%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell text-white">LSC (25%)</th>
                    <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider hidden xl:table-cell text-white">Glass (15%)</th>
                    <th className="px-2 py-3 text-center text-xs font-bold uppercase tracking-wider text-white"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {filteredRankings.map((employee, index) => {
                    const tierStyle = getTierStyle(employee.tier_label);
                    const isExpanded = expandedRow === employee.employee_id;
                    
                    // Find the employee ranked just above this one for "To Pass" comparison
                    // Use original rankings to ensure we find them even when filtered
                    const employeeAbove = rankings.find(e => e.peer_rank === (employee.peer_rank || 0) - 1);
                    
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
                              <span className="text-2xl font-serif font-black text-foreground">{employee.position}</span>
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
                          
                          {/* Customer Voice - Combined Total (Promoters/Detractors) */}
                          <td className="px-4 py-4 text-center hidden md:table-cell" data-testid={`cv-score-${employee.position}`}>
                            {(() => {
                              const promoters = employee.cv_promoters || 0;
                              const detractors = employee.cv_detractors || 0;
                              const cvScore = employee.cv_score || 0;
                              
                              return (
                                <TooltipProvider>
                                  <Tooltip>
                                    <TooltipTrigger className="cursor-help">
                                      <div className="flex flex-col items-center">
                                        <span className={`text-sm font-semibold ${cvScore > 0 ? 'text-green-400' : cvScore < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                                          {cvScore > 0 ? '+' : ''}{cvScore} pts
                                        </span>
                                        <span className="text-xs text-slate-500">
                                          {promoters}P / {detractors}D
                                        </span>
                                      </div>
                                    </TooltipTrigger>
                                    <TooltipContent className="bg-slate-800 text-white p-3 max-w-xs border border-slate-600">
                                      <div className="text-xs space-y-1">
                                        <div className="font-bold text-primary mb-2">{employee.name}'s Customer Voice</div>
                                        {promoters > 0 && (
                                          <div className="flex justify-between">
                                            <span>Promoters ({promoters} × +0.5):</span>
                                            <span className="text-green-400">+{(promoters * 0.5).toFixed(1)} pts</span>
                                          </div>
                                        )}
                                        {detractors > 0 && (
                                          <div className="flex justify-between">
                                            <span>Detractors ({detractors} × -1):</span>
                                            <span className="text-red-400">-{detractors} pts</span>
                                          </div>
                                        )}
                                        <div className="border-t border-slate-600 pt-1 mt-1 flex justify-between font-bold">
                                          <span>Total:</span>
                                          <span className={cvScore >= 0 ? "text-primary" : "text-red-400"}>{cvScore} pts</span>
                                        </div>
                                      </div>
                                    </TooltipContent>
                                  </Tooltip>
                                </TooltipProvider>
                              );
                            })()}
                          </td>
                          
                          {/* RT Bonus - Review Tracker Mentions */}
                          <td className="px-4 py-4 text-center hidden lg:table-cell" data-testid={`rt-bonus-${employee.position}`}>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger className="cursor-help">
                                  <div className="flex flex-col items-center">
                                    <span className="text-sm font-semibold text-purple-400">
                                      +{formatNumber(employee.review_bonus || 0)}
                                    </span>
                                    <span className="text-xs text-slate-500">
                                      {employee.review_mentions || 0} mentions
                                    </span>
                                  </div>
                                </TooltipTrigger>
                                <TooltipContent className="bg-slate-800 text-white p-3 max-w-xs border border-slate-600">
                                  <div className="text-xs">
                                    <div className="font-bold text-primary mb-1">Review Tracker</div>
                                    <div>{employee.review_mentions || 0} mentions × 0.5 pts = +{formatNumber(employee.review_bonus || 0)} pts (max 15)</div>
                                  </div>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </td>
                          
                          {/* Metric Bonus: exceeding benchmarks */}
                          <td className="px-4 py-4 text-center hidden lg:table-cell">
                            <span className="text-sm font-semibold text-blue-400">
                              +{formatNumber(employee.metric_bonus || 0)}
                            </span>
                          </td>
                          
                          {/* Trend/Momentum Indicator */}
                          <td className="px-4 py-4 text-center hidden md:table-cell" data-testid={`trend-${employee.position}`}>
                            {(() => {
                              const momentum = momentumData[employee.employee_id] || momentumData[employee.name] || {};
                              return (
                                <TrendIndicator
                                  direction={momentum.direction || "stable"}
                                  change={momentum.change || 0}
                                  rollingAvg={momentum.rolling_avg}
                                  snapshotsUsed={momentum.snapshots_used || 0}
                                  size="sm"
                                />
                              );
                            })()}
                          </td>
                          
                          {/* PPA Points */}
                          <td className="px-4 py-4 hidden xl:table-cell">
                            {renderPointsCell(employee.ppa_points)}
                          </td>
                          
                          {/* LBW Points */}
                          <td className="px-4 py-4 hidden xl:table-cell">
                            {renderPointsCell(employee.lbw_points)}
                          </td>
                          
                          {/* LSC Points */}
                          <td className="px-4 py-4 hidden xl:table-cell">
                            {renderPointsCell(employee.lsc_points)}
                          </td>
                          
                          {/* Glassware Points */}
                          <td className="px-4 py-4 hidden xl:table-cell">
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
                            <td colSpan={12} className="p-0 relative">
                              <div className="sticky left-0 px-3 sm:px-6 py-4 w-screen sm:w-full max-w-full overflow-hidden">
                              {(() => {
                                const emp = getEmployeeDetails(employee.employee_id);
                                const ranks = metricRankings[employee.employee_id] || {};
                                const total = employees.length;
                                const benchmarks = quarterSettings || {};
                                
                                const metrics = [
                                  {
                                    label: 'PPA',
                                    value: `$${(emp.ppa || 0).toFixed(0)}`,
                                    benchmark: `Target: $${benchmarks.benchmark_ppa || 55}`,
                                    rank: ranks.ppa,
                                    total,
                                    color: (emp.ppa || 0) >= (benchmarks.benchmark_ppa || 55) ? 'text-green-400' : 'text-red-400'
                                  },
                                  {
                                    label: 'LBW',
                                    value: `$${(emp.lbw_per_guest || 0).toFixed(2)}`,
                                    benchmark: `Target: $${benchmarks.benchmark_lbw || 8}`,
                                    rank: ranks.lbw,
                                    total,
                                    color: (emp.lbw_per_guest || 0) >= (benchmarks.benchmark_lbw || 8) ? 'text-green-400' : 'text-red-400'
                                  },
                                  {
                                    label: 'Glass',
                                    value: `$${(emp.glassware_per_guest || 0).toFixed(2)}`,
                                    benchmark: `Target: $${benchmarks.benchmark_glass || 1.25}`,
                                    rank: ranks.glass,
                                    total,
                                    color: (emp.glassware_per_guest || 0) >= (benchmarks.benchmark_glass || 1.25) ? 'text-green-400' : 'text-red-400'
                                  },
                                  {
                                    label: 'LSC',
                                    value: (emp.guests_per_lsc || 0).toFixed(0),
                                    benchmark: `Target: ≤${benchmarks.benchmark_lsc || 100}`,
                                    rank: ranks.lsc,
                                    total,
                                    color: (emp.guests_per_lsc || 999) <= (benchmarks.benchmark_lsc || 100) ? 'text-green-400' : 'text-red-400'
                                  },
                                  {
                                    label: 'RT',
                                    value: `+${(emp.review_tracker_bonus || 0).toFixed(1)}`,
                                    benchmark: `${emp.review_mentions || 0} mentions`,
                                    rank: null,
                                    total: null,
                                    color: 'text-green-400'
                                  }
                                ];
                                
                                return (
                                  <div className="space-y-4">
                                    <div className="flex items-center gap-2 mb-3">
                                      <span className="text-lg font-serif font-bold text-slate-200">Metric Breakdown</span>
                                      <span className="text-sm text-slate-400">• {employee.name}</span>
                                    </div>
                                    
                                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                                      {metrics.map((m) => (
                                        <div key={m.label} className="bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-600 min-w-0">
                                          <div className="text-xs font-semibold text-slate-400 uppercase mb-1 truncate">{m.label}</div>
                                          <div className={`text-xl sm:text-2xl font-bold ${m.color} truncate`}>{m.value}</div>
                                          <div className="text-xs text-slate-400 mt-1 truncate">{m.benchmark}</div>
                                          <div className="mt-2 pt-2 border-t border-slate-600">
                                            {m.rank !== null ? (
                                              <span className="inline-flex items-center px-2 py-0.5 bg-blue-600 text-white rounded-full text-xs font-semibold whitespace-nowrap">
                                                {m.rank}{m.rank === 1 ? 'st' : m.rank === 2 ? 'nd' : m.rank === 3 ? 'rd' : 'th'}/{m.total}
                                              </span>
                                            ) : (
                                              <span className="inline-flex items-center px-2 py-0.5 bg-green-600 text-white rounded-full text-xs font-semibold">
                                                Bonus
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      ))}
                                      
                                      {/* Customer Voice Card - Combined Total */}
                                      <div className="bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-600 min-w-0">
                                        <div className="text-xs font-semibold text-slate-400 uppercase mb-1 flex items-center gap-1">
                                          <MessageCircle className="w-3 h-3 flex-shrink-0" />
                                          <span className="truncate">Cust. Voice</span>
                                        </div>
                                        {(() => {
                                          const cvScore = emp.cv_score || 0;
                                          return (
                                            <>
                                              <div className={`text-xl sm:text-2xl font-bold ${cvScore > 0 ? 'text-green-400' : cvScore < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                                                {cvScore > 0 ? '+' : ''}{cvScore.toFixed(1)}
                                              </div>
                                              <div className="text-xs text-slate-400 mt-1 truncate">Combined pts</div>
                                              <div className="mt-2 pt-2 border-t border-slate-600">
                                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                                                  cvScore > 0 ? 'bg-green-600 text-white' : cvScore < 0 ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-400'
                                                }`}>
                                                  {cvScore > 0 ? 'Positive' : cvScore < 0 ? 'Negative' : 'Neutral'}
                                                </span>
                                              </div>
                                            </>
                                          );
                                        })()}
                                      </div>
                                    </div>
                                    
                                    {/* Summary Row with Editable Job Title */}
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-800 rounded-xl p-3 sm:p-4 shadow-sm border border-slate-600 mt-4">
                                      <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
                                        <span className="text-xs sm:text-sm text-slate-400">Job Title:</span>
                                        {editingJobTitle === employee.employee_id ? (
                                          <div className="flex items-center gap-1">
                                            <Select 
                                              value={pendingJobTitle} 
                                              onValueChange={setPendingJobTitle}
                                            >
                                              <SelectTrigger className="w-24 sm:w-32 h-7 sm:h-8 bg-slate-700 border-slate-500 text-white text-xs sm:text-sm">
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
                                              className="h-7 w-7 p-0 text-green-400 hover:text-green-300 hover:bg-green-900/30"
                                              data-testid={`save-job-title-${employee.position}`}
                                            >
                                              {savingJobTitle ? (
                                                <div className="w-3 h-3 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
                                              ) : (
                                                <Check className="w-3 h-3" />
                                              )}
                                            </Button>
                                            <Button
                                              size="sm"
                                              variant="ghost"
                                              onClick={() => setEditingJobTitle(null)}
                                              className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-900/30"
                                            >
                                              <X className="w-3 h-3" />
                                            </Button>
                                          </div>
                                        ) : (
                                          <div className="flex items-center gap-1">
                                            <span className={`px-2 py-0.5 rounded-full text-xs sm:text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
                                              {emp?.job_title || employee.job_title || 'Server'}
                                            </span>
                                            <Button
                                              size="sm"
                                              variant="ghost"
                                              onClick={() => {
                                                setEditingJobTitle(employee.employee_id);
                                                setPendingJobTitle(emp?.job_title || employee.job_title || 'Server');
                                              }}
                                              className="h-6 w-6 p-0 text-slate-400 hover:text-white hover:bg-slate-700"
                                              title="Edit job title"
                                              data-testid={`edit-job-title-${employee.position}`}
                                            >
                                              <Edit3 className="w-3 h-3" />
                                            </Button>
                                          </div>
                                        )}
                                      </div>
                                      <div className="flex flex-col sm:flex-row sm:items-center gap-1">
                                        <span className="text-xs sm:text-sm text-slate-400">Tier:</span>
                                        <span className={`px-2 py-0.5 rounded-full text-xs sm:text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
                                          {employee.tier_label}
                                        </span>
                                      </div>
                                      <div className="flex flex-col sm:flex-row sm:items-center gap-1">
                                        <span className="text-xs sm:text-sm text-slate-400">Bonus:</span>
                                        <span className="text-base sm:text-lg font-bold text-green-400">+{formatNumber(employee.bonus_points)}</span>
                                      </div>
                                      <div className="flex flex-col sm:flex-row sm:items-center gap-1">
                                        <span className="text-xs sm:text-sm text-slate-400">Rank:</span>
                                        <span className="text-base sm:text-lg font-bold text-primary">#{employee.peer_rank || employee.position}/{totalEmployees}</span>
                                      </div>
                                    </div>
                                    
                                    {/* Improvement Plan Section */}
                                    <div className="mt-6 bg-slate-800 rounded-xl p-5 border border-slate-600 shadow-sm">
                                      <div className="flex items-center gap-2 mb-4">
                                        <Target className="w-5 h-5 text-blue-400" />
                                        <span className="text-lg font-serif font-bold text-white">Improvement Plan</span>
                                      </div>
                                      
                                      {/* Gap Analysis vs Benchmarks */}
                                      <div className="mb-5">
                                        <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                                          <TrendingUp className="w-4 h-4" />
                                          Gap Analysis vs Benchmarks
                                        </h4>
                                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                                          {(() => {
                                            const gaps = [
                                              { 
                                                label: 'PPA', 
                                                current: emp.ppa || 0, 
                                                target: benchmarks.benchmark_ppa || 55,
                                                format: v => `$${v.toFixed(2)}`
                                              },
                                              { 
                                                label: 'LBW', 
                                                current: emp.lbw_per_guest || 0, 
                                                target: benchmarks.benchmark_lbw || 8,
                                                format: v => `$${v.toFixed(2)}`
                                              },
                                              { 
                                                label: 'Glass', 
                                                current: emp.glassware_per_guest || 0, 
                                                target: benchmarks.benchmark_glass || 1.25,
                                                format: v => `$${v.toFixed(2)}`
                                              },
                                              { 
                                                label: 'LSC', 
                                                current: emp.guests_per_lsc || 999, 
                                                target: benchmarks.benchmark_lsc || 100,
                                                format: v => v.toFixed(0),
                                                inverse: true // Lower is better
                                              }
                                            ];
                                            return gaps.map((g) => {
                                              const diff = g.inverse 
                                                ? g.target - g.current 
                                                : g.current - g.target;
                                              const isGood = diff >= 0;
                                              return (
                                                <div key={g.label} className={`p-3 rounded-lg ${isGood ? 'bg-green-900/40 border border-green-500/50' : 'bg-red-900/40 border border-red-500/50'}`}>
                                                  <div className="text-xs text-slate-300 mb-1">{g.label}</div>
                                                  <div className={`text-lg font-bold ${isGood ? 'text-green-400' : 'text-red-400'}`}>
                                                    {isGood ? '+' : '-'}{g.format(Math.abs(diff))}
                                                  </div>
                                                  <div className="text-xs text-slate-400">
                                                    {isGood ? 'Above target' : `Need ${g.format(Math.abs(diff))} more`}
                                                  </div>
                                                </div>
                                              );
                                            });
                                          })()}
                                        </div>
                                      </div>
                                      
                                      {/* To Pass Next Employee */}
                                      {employeeAbove && (employee.peer_rank || 0) > 1 && (
                                        <div className="border-t border-slate-600 pt-4">
                                          <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                                            <ArrowUp className="w-4 h-4 text-blue-400" />
                                            <span className="truncate">To Pass #{(employee.peer_rank || 0) - 1} ({employeeAbove.name})</span>
                                          </h4>
                                          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3">
                                            <div className="bg-blue-900/40 rounded-lg p-2 sm:p-3 border border-blue-500/50">
                                              <div className="text-xs text-slate-300">Gap</div>
                                              <div className="text-base sm:text-lg font-bold text-blue-400">
                                                +{((employeeAbove.total_score || 0) - (employee.total_score || 0)).toFixed(1)}
                                              </div>
                                              <div className="text-xs text-slate-400 hidden sm:block">pts needed</div>
                                            </div>
                                            <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
                                              <div className="text-xs text-slate-400">PPA</div>
                                              <div className="text-sm font-semibold text-white">
                                                ${(employeeAbove.ppa || getEmployeeDetails(employeeAbove.employee_id)?.ppa || 0).toFixed(0)}
                                              </div>
                                            </div>
                                            <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
                                              <div className="text-xs text-slate-400">LBW</div>
                                              <div className="text-sm font-semibold text-white">
                                                ${(employeeAbove.lbw_per_guest || getEmployeeDetails(employeeAbove.employee_id)?.lbw_per_guest || 0).toFixed(2)}
                                              </div>
                                            </div>
                                            <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
                                              <div className="text-xs text-slate-400">Glass</div>
                                              <div className="text-sm font-semibold text-white">
                                                ${(employeeAbove.glassware_per_guest || getEmployeeDetails(employeeAbove.employee_id)?.glassware_per_guest || 0).toFixed(2)}
                                              </div>
                                            </div>
                                            <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
                                              <div className="text-xs text-slate-400">LSC</div>
                                              <div className="text-sm font-semibold text-white">
                                                {(employeeAbove.guests_per_lsc || getEmployeeDetails(employeeAbove.employee_id)?.guests_per_lsc || 0).toFixed(0)}
                                              </div>
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}
                              </div>
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
            {Object.entries(V2_METRICS).filter(([key]) => key !== 'pre_dar_score' && key !== 'rt_mentions').map(([metricKey, metricInfo]) => {
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

          {/* Top 10 ReviewTracker - Detailed View */}
          <div className="mt-6 bubba-card" data-testid="top-10-reviewtracker-detailed">
            <div className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-lg font-serif font-bold text-foreground flex items-center gap-2">
                    <MessageCircle className="w-5 h-5 text-yellow-500" />
                    Top 10 - ReviewTracker Mentions
                  </h3>
                  <p className="text-sm text-slate-400">
                    Employees mentioned most frequently in public reviews (Google, Yelp, TripAdvisor)
                  </p>
                </div>
              </div>
              
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700">
                      <th className="text-left py-2 px-2 text-slate-400 font-medium">Rank</th>
                      <th className="text-left py-2 px-2 text-slate-400 font-medium">Employee</th>
                      <th className="text-center py-2 px-2 text-slate-400 font-medium">Total Mentions</th>
                      <th className="text-center py-2 px-2 text-slate-400 font-medium">Positive</th>
                      <th className="text-center py-2 px-2 text-slate-400 font-medium">RT Bonus</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(topPerformers['rt_mentions'] || []).map((employee, index) => (
                      <tr key={employee.id} className="border-b border-slate-700/50 hover:bg-slate-800/30">
                        <td className="py-3 px-2">
                          <div className="flex items-center justify-center w-7 h-7 bg-yellow-500/20 rounded-full text-sm font-bold text-yellow-400">
                            {index + 1}
                          </div>
                        </td>
                        <td className="py-3 px-2">
                          <div className="font-semibold text-foreground">{employee.name}</div>
                          <div className="text-xs text-slate-400 capitalize">{employee.tier_label || employee.job_title || 'Server'}</div>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span className="text-lg font-bold text-primary">{employee.rt_mentions || 0}</span>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span className="text-green-400 font-medium">{employee.rt_positive || 0}</span>
                        </td>
                        <td className="py-3 px-2 text-center">
                          <span className="text-amber-400 font-medium">+{formatNumber(employee.review_tracker_bonus || 0)}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {(!topPerformers['rt_mentions'] || topPerformers['rt_mentions'].length === 0) && (
                <div className="text-center py-8 text-gray-400">
                  <MessageCircle className="w-12 h-12 mx-auto mb-2 opacity-50" />
                  <p>No ReviewTracker data available</p>
                  <p className="text-xs mt-1">Upload ReviewTracker CSV in Data Uploads</p>
                </div>
              )}
            </div>
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
