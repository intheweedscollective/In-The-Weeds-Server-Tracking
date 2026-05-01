import { useState, useEffect, useCallback } from "react";
import { Star, Filter, MessageSquare, Award, AlertCircle, Ban, Undo2, Upload, Users, Download, Edit2, Save, X } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { toast } from "sonner";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { getDisplayFirstName } from "../utils/displayName";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function ReviewTracker() {
  const [cvFeedback, setCvFeedback] = useState([]);
  const [cvStats, setCvStats] = useState(null);
  const [rtStats, setRtStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const currentQ = getCurrentQuarter();
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [filterEmployee, setFilterEmployee] = useState("");
  const [activeTab, setActiveTab] = useState("rt"); // "rt", "cv", or "cv-edit"
  const [showExcluded, setShowExcluded] = useState(false);
  const [excludedCount, setExcludedCount] = useState(0);
  const [cvSentimentFilter, setCvSentimentFilter] = useState("all");
  const [employeeMentions, setEmployeeMentions] = useState([]);
  
  // Employee CV stats for editing
  const [employeeCvStats, setEmployeeCvStats] = useState([]);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editPromoters, setEditPromoters] = useState(0);
  const [editDetractors, setEditDetractors] = useState(0);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Fetch CV feedback
      try {
        const cvRes = await fetch(`${API_URL}/api/v2/cv/feedback?quarter=${selectedQuarter}&year=${selectedYear}&limit=100&include_excluded=${showExcluded}`);
        const cvData = await cvRes.json();
        setCvFeedback(cvData.feedback || []);
        setExcludedCount(cvData.excluded_count || 0);
        
        // Fetch CV stats (NPS data)
        const cvStatsRes = await fetch(`${API_URL}/api/v2/cv/stats?quarter=${selectedQuarter}&year=${selectedYear}`);
        const cvStatsData = await cvStatsRes.json();
        setCvStats(cvStatsData);
      } catch (error) {
        console.error('Failed to fetch CV data:', error);
        setCvFeedback([]);
        setCvStats(null);
      }
      
      // Fetch RT stats (employee mention counts)
      try {
        const rtStatsRes = await fetch(`${API_URL}/api/v2/reviews/stats?quarter=${selectedQuarter}&year=${selectedYear}`);
        const rtStatsData = await rtStatsRes.json();
        setRtStats(rtStatsData);
        setEmployeeMentions(rtStatsData?.top_mentioned || []);
      } catch (error) {
        console.error('Failed to fetch RT stats:', error);
        setRtStats(null);
        setEmployeeMentions([]);
      }
      
      // Fetch employee CV stats for editing
      try {
        const empRes = await fetch(`${API_URL}/api/v2/employees?quarter=${selectedQuarter}&year=${selectedYear}`);
        const empData = await empRes.json();
        setEmployeeCvStats(empData.map(emp => ({
          id: emp.id,
          name: emp.name,
          cv_promoters: emp.cv_promoters || 0,
          cv_detractors: emp.cv_detractors || 0,
          cv_score: emp.cv_score || 0,
          nps_score: emp.nps_score || 0
        })).sort((a, b) => a.name.localeCompare(b.name)));
      } catch (error) {
        console.error('Failed to fetch employee stats:', error);
        setEmployeeCvStats([]);
      }
      
    } catch (error) {
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [selectedQuarter, selectedYear, showExcluded]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Upload Customer Voice CSV
  const handleCVUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    if (!file.name.endsWith('.csv') && !file.name.endsWith('.xlsx')) {
      toast.error("Please upload a CSV or XLSX file");
      return;
    }
    
    toast.info("Uploading Customer Voice data...");
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(
        `${API_URL}/api/v2/cv/server-performance/upload?quarter=${selectedQuarter}&year=${selectedYear}`,
        { method: "POST", body: formData }
      );
      
      const data = await res.json();
      
      if (data.success) {
        toast.success(`Updated ${data.records_updated} server NPS records (${data.total_surveys} surveys)`);
        fetchData();
      } else {
        toast.error(data.message || data.detail || "Upload failed");
      }
    } catch (error) {
      toast.error("Customer Voice upload failed");
    }
    
    event.target.value = '';
  };

  // Upload Review Tracker XLSX/CSV
  const handleRTUpload = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    
    if (!file.name.endsWith('.xlsx') && !file.name.endsWith('.csv')) {
      toast.error("Please upload an XLSX or CSV file");
      return;
    }
    
    toast.info("Scanning reviews for employee mentions...");
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(
        `${API_URL}/api/v2/review-tracker/upload-feedback?quarter=${selectedQuarter}&year=${selectedYear}`,
        { method: "POST", body: formData }
      );
      
      const data = await res.json();
      
      if (data.success) {
        toast.success(`Found ${data.summary?.total_mentions || 0} mentions in ${data.summary?.reviews_with_mentions || 0} reviews`);
        fetchData();
      } else {
        toast.error(data.message || data.detail || "Upload failed");
      }
    } catch (error) {
      toast.error("Review Tracker upload failed");
    }
    
    event.target.value = '';
  };

  // Exclude CV feedback from rankings
  const handleExcludeFeedback = async (feedbackId) => {
    try {
      const res = await fetch(`${API_URL}/api/v2/cv/feedback/${feedbackId}/exclude`, {
        method: "POST"
      });
      
      const data = await res.json();
      
      if (data.success) {
        toast.success("Feedback excluded from rankings. NPS recalculated.");
        fetchData();
      } else {
        toast.error(data.message || "Failed to exclude feedback");
      }
    } catch (error) {
      toast.error("Error excluding feedback");
    }
  };

  // Include (undo exclude) CV feedback back into rankings
  const handleIncludeFeedback = async (feedbackId) => {
    try {
      const res = await fetch(`${API_URL}/api/v2/cv/feedback/${feedbackId}/include`, {
        method: "POST"
      });
      
      const data = await res.json();
      
      if (data.success) {
        toast.success("Feedback restored to rankings. NPS recalculated.");
        fetchData();
      } else {
        toast.error(data.message || "Failed to restore feedback");
      }
    } catch (error) {
      toast.error("Error restoring feedback");
    }
  };

  // Start editing an employee's CV stats
  const startEditing = (emp) => {
    setEditingEmployee(emp.id);
    setEditPromoters(emp.cv_promoters || 0);
    setEditDetractors(emp.cv_detractors || 0);
  };

  // Cancel editing
  const cancelEditing = () => {
    setEditingEmployee(null);
    setEditPromoters(0);
    setEditDetractors(0);
  };

  // Save employee CV stats
  const saveEmployeeCvStats = async (employeeId) => {
    try {
      const res = await fetch(`${API_URL}/api/v2/employees/${employeeId}/cv-stats`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cv_promoters: parseInt(editPromoters) || 0,
          cv_detractors: parseInt(editDetractors) || 0,
          quarter: selectedQuarter,
          year: selectedYear
        })
      });
      
      const data = await res.json();
      
      if (res.ok && data.success) {
        toast.success(`Updated CV stats for employee. New CV score: ${data.new_cv_score}`);
        cancelEditing();
        fetchData();
      } else {
        toast.error(data.detail || data.message || "Failed to update CV stats");
      }
    } catch (error) {
      toast.error("Error updating CV stats");
    }
  };

  // Filter mentions by employee name
  const filteredMentions = employeeMentions.filter(emp => 
    !filterEmployee || emp.name.toLowerCase().includes(filterEmployee.toLowerCase())
  );

  // Filter employee CV stats
  const filteredCvStats = employeeCvStats.filter(emp =>
    !filterEmployee || emp.name.toLowerCase().includes(filterEmployee.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-background p-3 md:p-8" data-testid="review-tracker-page">
      {/* Header */}
      <div className="mb-4 md:mb-6">
        <div className="flex flex-col gap-4">
          <div>
            <h1 className="text-xl md:text-3xl font-bold text-white flex items-center gap-2">
              <MessageSquare className="w-6 h-6 md:w-8 md:h-8 text-primary" />
              Review Tracker
            </h1>
            <p className="text-slate-300 text-sm mt-1">
              Manage employee review mentions and customer voice feedback
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            {/* RT Template Download */}
            <Button
              variant="outline"
              size="sm"
              className="border-green-500 text-green-500 hover:bg-green-500/10"
              onClick={() => window.open(`${API_URL}/api/v2/rt/template`, '_blank')}
              data-testid="rt-template-btn"
            >
              <Download className="w-4 h-4 mr-1 md:mr-2" />
              <span className="hidden sm:inline">RT Template</span>
              <span className="sm:hidden">RT</span>
            </Button>
            
            {/* RT Upload */}
            <label className="cursor-pointer">
              <input
                type="file"
                accept=".xlsx,.csv"
                onChange={handleRTUpload}
                className="hidden"
                data-testid="rt-upload-input"
              />
              <Button
                variant="outline"
                size="sm"
                className="border-blue-500 text-blue-500 hover:bg-blue-500/10 pointer-events-none"
                asChild
              >
                <span>
                  <Upload className="w-4 h-4 mr-1 md:mr-2" />
                  <span className="hidden sm:inline">Upload RT</span>
                  <span className="sm:hidden">RT</span>
                </span>
              </Button>
            </label>
            
            {/* CV Upload */}
            <label className="cursor-pointer">
              <input
                type="file"
                accept=".csv,.xlsx"
                onChange={handleCVUpload}
                className="hidden"
                data-testid="cv-upload-input"
              />
              <Button
                variant="outline"
                size="sm"
                className="border-orange-400 text-orange-400 hover:bg-orange-500/10 pointer-events-none"
                asChild
              >
                <span>
                  <Upload className="w-4 h-4 mr-1 md:mr-2" />
                  <span className="hidden sm:inline">Upload CV</span>
                  <span className="sm:hidden">CV</span>
                </span>
              </Button>
            </label>
          </div>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 md:gap-4 mb-4 md:mb-6">
        {/* Review Tracker Summary */}
        <div className="bg-slate-800 rounded-xl p-3 md:p-4 border border-blue-500/30" data-testid="rt-summary">
          <div className="flex items-center gap-2 mb-2 md:mb-3">
            <Users className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
            <h3 className="font-semibold text-white text-sm md:text-base">Review Tracker</h3>
            <span className="text-xs bg-blue-500/20 text-blue-300 px-2 py-0.5 rounded-full">
              {selectedQuarter} {selectedYear}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 md:gap-4">
            <div>
              <p className="text-2xl md:text-3xl font-bold text-blue-400">{rtStats?.total_mentions || 0}</p>
              <p className="text-xs text-slate-400">Mentions</p>
            </div>
            <div>
              <p className="text-2xl md:text-3xl font-bold text-white">{employeeMentions.length}</p>
              <p className="text-xs text-slate-400">Employees</p>
            </div>
          </div>
        </div>
        
        {/* Customer Voice Summary */}
        <div className="bg-slate-800 rounded-xl p-3 md:p-4 border border-orange-500/30" data-testid="cv-summary">
          <div className="flex items-center gap-2 mb-2 md:mb-3">
            <Star className="w-4 h-4 md:w-5 md:h-5 text-orange-400 fill-orange-400" />
            <h3 className="font-semibold text-white text-sm md:text-base">Customer Voice</h3>
            <span className="text-xs bg-orange-500/20 text-orange-300 px-2 py-0.5 rounded-full">
              {selectedQuarter} {selectedYear}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1 md:gap-2">
            <div>
              <p className="text-lg md:text-2xl font-bold text-orange-400">{cvStats?.avg_nps || 0}%</p>
              <p className="text-xs text-slate-400">NPS</p>
            </div>
            <div>
              <p className="text-lg md:text-2xl font-bold text-green-400">{cvStats?.promoter_count || 0}</p>
              <p className="text-xs text-slate-400">Prom</p>
            </div>
            <div>
              <p className="text-lg md:text-2xl font-bold text-yellow-400">{cvStats?.passive_count || 0}</p>
              <p className="text-xs text-slate-400">Pass</p>
            </div>
            <div>
              <p className="text-lg md:text-2xl font-bold text-red-400">{cvStats?.detractor_count || 0}</p>
              <p className="text-xs text-slate-400">Detr</p>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 md:gap-2 mb-4 md:mb-6 overflow-x-auto pb-1">
        <button
          onClick={() => setActiveTab("rt")}
          className={`px-3 md:px-4 py-2 rounded-lg text-xs md:text-sm font-medium transition-colors flex items-center gap-1 md:gap-2 whitespace-nowrap ${
            activeTab === "rt"
              ? "bg-blue-500 text-white"
              : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
          }`}
          data-testid="tab-rt"
        >
          <Users className="w-3.5 h-3.5 md:w-4 md:h-4" />
          RT ({employeeMentions.length})
        </button>
        <button
          onClick={() => setActiveTab("cv")}
          className={`px-3 md:px-4 py-2 rounded-lg text-xs md:text-sm font-medium transition-colors flex items-center gap-1 md:gap-2 whitespace-nowrap ${
            activeTab === "cv"
              ? "bg-gradient-to-r from-yellow-400 to-orange-500 text-white"
              : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
          }`}
          data-testid="tab-cv"
        >
          <Star className={`w-3.5 h-3.5 md:w-4 md:h-4 ${activeTab === "cv" ? "fill-white" : "fill-yellow-400 text-yellow-400"}`} />
          CV ({cvFeedback.length})
        </button>
        <button
          onClick={() => setActiveTab("cv-edit")}
          className={`px-3 md:px-4 py-2 rounded-lg text-xs md:text-sm font-medium transition-colors flex items-center gap-1 md:gap-2 whitespace-nowrap ${
            activeTab === "cv-edit"
              ? "bg-purple-500 text-white"
              : "bg-slate-800 text-slate-300 hover:bg-slate-700 border border-slate-700"
          }`}
          data-testid="tab-cv-edit"
        >
          <Edit2 className="w-3.5 h-3.5 md:w-4 md:h-4" />
          Edit CV
        </button>
      </div>

      {/* Filters */}
      <div className="bg-slate-800 rounded-xl p-3 md:p-4 border border-slate-700 mb-4 md:mb-6">
        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-slate-400" />
            <span className="text-xs md:text-sm font-medium text-slate-200">Filters:</span>
          </div>
          
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="px-2 md:px-3 py-1.5 border border-slate-600 rounded-lg text-xs md:text-sm bg-slate-700 text-slate-200"
            data-testid="filter-year"
          >
            <option value={2026}>2026</option>
            <option value={2025}>2025</option>
          </select>
          
          <select
            value={selectedQuarter}
            onChange={(e) => setSelectedQuarter(e.target.value)}
            className="px-2 md:px-3 py-1.5 border border-slate-600 rounded-lg text-xs md:text-sm bg-slate-700 text-slate-200"
            data-testid="filter-quarter"
          >
            <option value="Q1">Q1</option>
            <option value="Q2">Q2</option>
            <option value="Q3">Q3</option>
            <option value="Q4">Q4</option>
          </select>
          
          <Input
            placeholder="Filter employee..."
            value={filterEmployee}
            onChange={(e) => setFilterEmployee(e.target.value)}
            className="w-32 md:w-48 text-xs md:text-sm bg-slate-700 border-slate-600 text-slate-200 placeholder:text-slate-400"
            data-testid="filter-employee"
          />
        </div>
      </div>

      {/* Content based on active tab */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : activeTab === "rt" ? (
        /* Review Tracker - Employee Mentions Table */
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden" data-testid="rt-mentions-section">
          <div className="p-3 md:p-4 border-b border-slate-700">
            <h2 className="text-base md:text-lg font-bold text-white flex items-center gap-2">
              <Award className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
              Employee Mention Counts
            </h2>
            <p className="text-xs md:text-sm text-slate-400 mt-1">
              Each mention = +0.5 pts (capped at 15)
            </p>
          </div>
          
          {filteredMentions.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No employee mentions found</p>
              <p className="text-sm mt-2">Upload RT data using the template above</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-700/50">
                  <tr>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-left text-xs font-bold text-slate-300 uppercase">Rank</th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-left text-xs font-bold text-slate-300 uppercase">Employee</th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">Mentions</th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">RT Pts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {filteredMentions.map((emp, idx) => {
                    const rtPoints = Math.min((emp.mentions || 0) * 0.5, 15);
                    return (
                      <tr key={getDisplayFirstName(emp)} className="hover:bg-slate-700/30 transition-colors">
                        <td className="px-3 md:px-4 py-2 md:py-3">
                          <div className={`w-6 h-6 md:w-8 md:h-8 rounded-full flex items-center justify-center text-white font-bold text-xs md:text-sm ${
                            idx === 0 ? "bg-yellow-500" : idx === 1 ? "bg-gray-400" : idx === 2 ? "bg-amber-600" : "bg-slate-600"
                          }`}>
                            {idx + 1}
                          </div>
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3">
                          <span className="font-medium text-white text-sm">{getDisplayFirstName(emp)}</span>
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          <span className="text-lg md:text-xl font-bold text-blue-400">{emp.mentions || 0}</span>
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          <span className={`px-2 md:px-3 py-1 rounded-full text-xs md:text-sm font-bold ${
                            rtPoints >= 5.1 ? "bg-blue-500/20 text-blue-300" :
                            rtPoints >= 2.6 ? "bg-green-500/20 text-green-300" :
                            rtPoints >= 0.1 ? "bg-yellow-500/20 text-yellow-300" :
                            "bg-red-500/20 text-red-300"
                          }`}>
                            +{rtPoints.toFixed(1)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : activeTab === "cv-edit" ? (
        /* Employee CV Stats Editor */
        <div className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden" data-testid="cv-edit-section">
          <div className="p-3 md:p-4 border-b border-slate-700">
            <h2 className="text-base md:text-lg font-bold text-white flex items-center gap-2">
              <Edit2 className="w-4 h-4 md:w-5 md:h-5 text-purple-400" />
              Edit Employee CV Stats
            </h2>
            <p className="text-xs md:text-sm text-slate-400 mt-1">
              Manually adjust promoter and detractor counts per employee
            </p>
          </div>
          
          {filteredCvStats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No employees found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-slate-700/50">
                  <tr>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-left text-xs font-bold text-slate-300 uppercase">Employee</th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">
                      <span className="text-green-400">Promoters</span>
                    </th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">
                      <span className="text-red-400">Detractors</span>
                    </th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">Cust. Voice</th>
                    <th className="px-3 md:px-4 py-2 md:py-3 text-center text-xs font-bold text-slate-300 uppercase">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-700">
                  {filteredCvStats.map((emp) => {
                    const isEditing = editingEmployee === emp.id;
                    const currentPromoters = isEditing ? editPromoters : emp.cv_promoters;
                    const currentDetractors = isEditing ? editDetractors : emp.cv_detractors;
                    const calculatedScore = (currentPromoters * 0.5) - (currentDetractors * 1);
                    
                    return (
                      <tr key={emp.id} className={`transition-colors ${isEditing ? "bg-purple-900/20" : "hover:bg-slate-700/30"}`}>
                        <td className="px-3 md:px-4 py-2 md:py-3">
                          <span className="font-medium text-white text-sm">{getDisplayFirstName(emp)}</span>
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          {isEditing ? (
                            <Input
                              type="number"
                              min="0"
                              value={editPromoters}
                              onChange={(e) => setEditPromoters(e.target.value)}
                              className="w-16 md:w-20 text-center bg-slate-700 border-green-500 text-green-400 font-bold text-sm"
                            />
                          ) : (
                            <span className="text-lg font-bold text-green-400">{emp.cv_promoters}</span>
                          )}
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          {isEditing ? (
                            <Input
                              type="number"
                              min="0"
                              value={editDetractors}
                              onChange={(e) => setEditDetractors(e.target.value)}
                              className="w-16 md:w-20 text-center bg-slate-700 border-red-500 text-red-400 font-bold text-sm"
                            />
                          ) : (
                            <span className="text-lg font-bold text-red-400">{emp.cv_detractors}</span>
                          )}
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          <span className={`px-2 md:px-3 py-1 rounded-full text-xs md:text-sm font-bold ${
                            calculatedScore > 0 ? "bg-green-500/20 text-green-300" :
                            calculatedScore < 0 ? "bg-red-500/20 text-red-300" :
                            "bg-slate-500/20 text-slate-300"
                          }`}>
                            {calculatedScore > 0 ? "+" : ""}{calculatedScore.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-3 md:px-4 py-2 md:py-3 text-center">
                          {isEditing ? (
                            <div className="flex items-center justify-center gap-1">
                              <Button
                                size="sm"
                                className="bg-green-600 hover:bg-green-700 h-7 md:h-8 px-2"
                                onClick={() => saveEmployeeCvStats(emp.id)}
                              >
                                <Save className="w-3.5 h-3.5" />
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-slate-600 h-7 md:h-8 px-2"
                                onClick={cancelEditing}
                              >
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              className="border-purple-500 text-purple-400 hover:bg-purple-500/20 h-7 md:h-8"
                              onClick={() => startEditing(emp)}
                            >
                              <Edit2 className="w-3.5 h-3.5 mr-1" />
                              <span className="hidden md:inline">Edit</span>
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* Customer Voice Section */
        <div data-testid="cv-section">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-2">
              <Star className="w-4 h-4 md:w-5 md:h-5 fill-yellow-400 text-yellow-400" />
              <h2 className="text-base md:text-lg font-bold text-white">Customer Voice Feedback</h2>
              <span className="bg-gradient-to-r from-yellow-400 to-orange-500 text-white text-xs px-2 py-0.5 rounded-full font-semibold">
                {cvFeedback.filter(f => !f.excluded).length} ACTIVE
              </span>
            </div>
            
            {/* Sentiment Filter */}
            <div className="flex items-center gap-2">
              <select
                value={cvSentimentFilter}
                onChange={(e) => setCvSentimentFilter(e.target.value)}
                className="px-2 md:px-3 py-1.5 border border-slate-600 rounded-lg text-xs md:text-sm bg-slate-700 text-slate-200"
                data-testid="cv-sentiment-filter"
              >
                <option value="all">All</option>
                <option value="detractor">Detractors ({cvFeedback.filter(f => f.sentiment === "detractor").length})</option>
                <option value="passive">Passives ({cvFeedback.filter(f => f.sentiment === "passive").length})</option>
                <option value="promoter">Promoters ({cvFeedback.filter(f => f.sentiment === "promoter").length})</option>
              </select>
              
              {excludedCount > 0 && (
                <label className="flex items-center gap-1 md:gap-2 text-xs text-slate-400">
                  <input
                    type="checkbox"
                    checked={showExcluded}
                    onChange={(e) => setShowExcluded(e.target.checked)}
                    className="rounded border-slate-600 bg-slate-700"
                  />
                  Excluded ({excludedCount})
                </label>
              )}
            </div>
          </div>
          
          {/* Detractor Alert */}
          {cvFeedback.filter(f => f.sentiment === "detractor" && !f.excluded).length > 0 && cvSentimentFilter === "all" && (
            <div className="mb-4 p-2 md:p-3 bg-red-900/30 border border-red-500/50 rounded-lg flex flex-col sm:flex-row sm:items-center gap-2 md:gap-3">
              <AlertCircle className="w-4 h-4 md:w-5 md:h-5 text-red-400 shrink-0" />
              <div className="flex-1">
                <span className="font-semibold text-red-300 text-sm">
                  {cvFeedback.filter(f => f.sentiment === "detractor" && !f.excluded).length} Detractor(s)
                </span>
                <span className="text-red-400 text-xs md:text-sm ml-2">
                  - Click "Exclude" to remove invalid
                </span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setCvSentimentFilter("detractor")}
                className="border-red-500 text-red-400 hover:bg-red-500/20 text-xs"
              >
                View
              </Button>
            </div>
          )}
          
          {/* CV Feedback List */}
          <div className="space-y-2 md:space-y-3">
            {cvFeedback.length === 0 ? (
              <div className="bg-slate-800 rounded-xl p-8 text-center border border-slate-700">
                <Star className="w-12 h-12 mx-auto mb-3 text-slate-600" />
                <p className="text-slate-400">No customer voice feedback found</p>
                <p className="text-sm text-slate-500 mt-2">Upload CV data using the button above</p>
              </div>
            ) : (
              cvFeedback
                .filter(item => cvSentimentFilter === "all" || item.sentiment === cvSentimentFilter)
                .filter(item => showExcluded || !item.excluded)
                .filter(item => !filterEmployee || (item.server_name || '').toLowerCase().includes(filterEmployee.toLowerCase()))
                .sort((a, b) => {
                  const order = { detractor: 0, passive: 1, promoter: 2 };
                  return (order[a.sentiment] || 2) - (order[b.sentiment] || 2);
                })
                .map((item) => (
                  <div
                    key={item.id}
                    className={`bg-slate-800 rounded-xl p-3 md:p-4 border-2 transition-all relative ${
                      item.excluded 
                        ? "border-slate-600 opacity-60" 
                        : item.sentiment === "detractor"
                        ? "border-red-500/50"
                        : item.sentiment === "promoter"
                        ? "border-green-500/50"
                        : "border-yellow-500/50"
                    }`}
                    data-testid={`cv-feedback-${item.id}`}
                  >
                    <div className="flex items-start gap-2 md:gap-4">
                      <div className="flex-1 min-w-0">
                        {/* Rating & Attribution */}
                        <div className="flex items-center gap-2 mb-2 flex-wrap">
                          <span className={`px-2 md:px-3 py-0.5 md:py-1 rounded-full text-xs md:text-sm font-bold ${
                            item.sentiment === "promoter" 
                              ? "bg-green-100 text-green-700" 
                              : item.sentiment === "passive"
                              ? "bg-yellow-100 text-yellow-700"
                              : "bg-red-100 text-red-700"
                          }`}>
                            {item.rating}/10
                          </span>
                          <span className="text-xs text-slate-400">{item.date}</span>
                          {item.server_name && (
                            <span className={`px-2 py-0.5 rounded text-xs font-semibold ${
                              item.sentiment === "promoter"
                                ? "bg-green-900/50 text-green-300"
                                : item.sentiment === "detractor"
                                ? "bg-red-900/50 text-red-300"
                                : "bg-yellow-900/50 text-yellow-300"
                            }`}>
                              {item.server_name}
                            </span>
                          )}
                        </div>
                        
                        {/* Comment */}
                        <p className="text-slate-200 text-xs md:text-sm leading-relaxed mb-2 md:mb-3 line-clamp-3">
                          "{item.comment}"
                        </p>
                        
                        {/* Meta & Actions */}
                        <div className="flex items-center justify-between">
                          <div className="text-xs text-slate-400 truncate">
                            {item.shift || "No shift"} • {item.store}
                          </div>
                          
                          {item.excluded ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleIncludeFeedback(item.id)}
                              className="text-green-500 hover:bg-green-500/10 border-green-500/50 text-xs h-7"
                              data-testid={`restore-${item.id}`}
                            >
                              <Undo2 className="w-3 h-3 mr-1" />
                              Restore
                            </Button>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleExcludeFeedback(item.id)}
                              className="text-red-500 hover:bg-red-500/10 border-red-500/50 text-xs h-7"
                              data-testid={`exclude-${item.id}`}
                            >
                              <Ban className="w-3 h-3 mr-1" />
                              Exclude
                            </Button>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    {item.excluded && (
                      <div className="absolute top-2 right-2 bg-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded">
                        EXCLUDED
                      </div>
                    )}
                  </div>
                ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
