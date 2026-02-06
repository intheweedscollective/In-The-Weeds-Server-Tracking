import { useState, useEffect, useCallback } from "react";
import { FileText, Download, Clock, User, Anchor, Ship, Calendar, TrendingUp, ChevronDown, ChevronUp } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import LineGraphUpload from "../components/LineGraphUpload";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { formatNumber } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function ReviewGeneration() {
  const [employees, setEmployees] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState({});
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [selectedYear, setSelectedYear] = useState("2026");
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
  const [selectedGraphKind, setSelectedGraphKind] = useState("quarter");
  const [expandedTrends, setExpandedTrends] = useState({}); // Track which employee trend charts are expanded
  const [trendData, setTrendData] = useState({}); // Store trend data per employee

  const fetchEmployees = useCallback(async () => {
    try {
      // Use V2 API with quarter filter
      const response = await axios.get(`${API}/v2/employees`, {
        params: { year: parseInt(selectedYear), quarter: selectedQuarter }
      });
      // Sort by peer_rank
      const sorted = (response.data || []).sort((a, b) => (a.peer_rank || 999) - (b.peer_rank || 999));
      setEmployees(sorted);
    } catch (error) {
      console.error("Error fetching employees:", error);
      toast.error("Error loading employees");
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  const fetchReviews = async () => {
    try {
      const response = await axios.get(`${API}/reviews`);
      setReviews(response.data);
    } catch (error) {
      console.error("Error fetching reviews:", error);
    }
  };

  useEffect(() => {
    fetchEmployees();
    fetchReviews();
  }, [fetchEmployees]);

  const generateReview = async (employeeId) => {
    setGenerating(prev => ({ ...prev, [employeeId]: true }));
    try {
      const employee = employees.find(e => e.id === employeeId);
      const filename = `${employee?.name.replace(/[^a-zA-Z0-9]/g, '_') || 'Employee'}_${selectedQuarter}_${selectedYear}_Review.pdf`;
      
      // iOS/Safari compatible download
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);
      if (isIOS) {
        toast.info("Generating review... Please wait");
      }
      
      // Use V2 API endpoint - returns JSON with pdf_base64
      const response = await axios.post(
        `${API}/v2/employees/${employeeId}/generate-review`,
        { quarter: selectedQuarter, year: parseInt(selectedYear) }
      );
      
      if (!response.data.success || !response.data.pdf_base64) {
        throw new Error(response.data.message || "Failed to generate review");
      }
      
      // Convert base64 to blob
      const byteCharacters = atob(response.data.pdf_base64);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: 'application/pdf' });
      const url = window.URL.createObjectURL(blob);
      
      if (isIOS) {
        // For iOS, open in new tab
        window.open(url, '_blank');
        toast.success(`Review opened for ${employee?.name || 'employee'}. Tap share to save.`);
      } else {
        // Standard download for desktop
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        link.remove();
        toast.success(`Review generated for ${employee?.name || 'employee'}`);
      }
      
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
      fetchReviews();
    } catch (error) {
      console.error("Error generating review:", error);
      toast.error("Error generating review: " + (error.response?.data?.message || error.message));
    } finally {
      setGenerating(prev => ({ ...prev, [employeeId]: false }));
    }
  };

  const hasRecentReview = (employeeId) => {
    return reviews.some(review => 
      review.employee_id === employeeId && 
      review.quarter === selectedQuarter && 
      review.year === parseInt(selectedYear)
    );
  };

  const getEmployeeReview = (employeeId) => {
    return reviews.find(review => 
      review.employee_id === employeeId && 
      review.quarter === selectedQuarter && 
      review.year === parseInt(selectedYear)
    );
  };

  // Get tier classification based on score
  const getTierLabel = (employee) => {
    const score = employee.pre_dar_score || employee.total_score || 0;
    if (score >= 85.1) return { label: "A-Server", color: "bg-green-100 text-green-800" };
    if (score >= 70.1) return { label: "B-Server", color: "bg-yellow-100 text-yellow-800" };
    return { label: "C-Server", color: "bg-red-100 text-red-800" };
  };

  // Toggle trend chart visibility for an employee
  const toggleTrend = async (employeeId) => {
    const isExpanded = expandedTrends[employeeId];
    
    if (!isExpanded && !trendData[employeeId]) {
      // Fetch trend data when expanding for the first time
      try {
        const response = await axios.get(`${API}/v2/trends/${selectedYear}/${selectedQuarter}/employee/${employeeId}/data`);
        setTrendData(prev => ({ ...prev, [employeeId]: response.data }));
      } catch (error) {
        console.error("Error fetching trend data:", error);
        // Still allow expansion even if data fetch fails
      }
    }
    
    setExpandedTrends(prev => ({ ...prev, [employeeId]: !isExpanded }));
  };

  // Get change indicator
  const getChangeIndicator = (change, higherBetter = true) => {
    if (change === 0 || change === null || change === undefined) {
      return { icon: '−', color: 'text-gray-500', bg: 'bg-gray-100' };
    }
    const isPositive = higherBetter ? change > 0 : change < 0;
    return isPositive 
      ? { icon: '↑', color: 'text-green-600', bg: 'bg-green-100' }
      : { icon: '↓', color: 'text-red-600', bg: 'bg-red-100' };
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Decorative splashes */}
      <div className="splash-red" style={{ top: '10%', right: '5%' }} />
      <div className="splash-blue" style={{ bottom: '15%', left: '3%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Ship className="w-8 h-8 text-primary" />
            <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
              Review Generation
            </h1>
          </div>
          <p className="text-gray-500 italic" data-testid="page-subtitle">
            Generate quarterly performance reviews for your crew
          </p>
        </div>

        {/* Review Settings */}
        <div className="bubba-card mb-8" data-testid="review-settings-card">
          <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-2deg)' }} />
          <div className="p-6 pt-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                <FileText className="w-5 h-5 text-primary" />
              </div>
              <div>
                <h2 className="text-lg font-serif font-bold text-foreground">Review Settings</h2>
                <p className="text-sm text-gray-500">Configure the review period</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-medium">Quarter</label>
                <Select value={selectedQuarter} onValueChange={setSelectedQuarter}>
                  <SelectTrigger data-testid="quarter-select" className="border-2 border-gray-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Q1">Q1 (January - March)</SelectItem>
                    <SelectItem value="Q2">Q2 (April - June)</SelectItem>
                    <SelectItem value="Q3">Q3 (July - September)</SelectItem>
                    <SelectItem value="Q4">Q4 (October - December)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Year</label>
                <Select value={selectedYear} onValueChange={setSelectedYear}>
                  <SelectTrigger data-testid="year-select" className="border-2 border-gray-200">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="2025">2025</SelectItem>
                    <SelectItem value="2026">2026</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <div className="mt-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
              <h4 className="font-serif font-bold text-foreground mb-2">Review Features</h4>
              <ul className="text-sm text-gray-500 space-y-1">
                <li>• AI-powered content generation using GPT-5.2</li>
                <li>• Human-like, HR-defensible review language</li>
                <li>• Professional PDF with Bubba Gump branding</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Line Graph Upload Section */}
        <div className="bubba-card mb-8" data-testid="line-graph-upload-card">
          <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
          <div className="p-6 pt-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <Anchor className="w-5 h-5 text-secondary" />
              </div>
              <div>
                <h2 className="text-lg font-serif font-bold text-foreground">Crew Line Graph</h2>
                <p className="text-sm text-gray-500">Upload quarterly chart for page 2</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Crew Member</label>
                <select
                  className="w-full h-10 rounded-lg border-2 border-gray-200 bg-white px-3 text-sm focus:border-primary transition-colors"
                  value={selectedEmployeeId}
                  onChange={(e) => setSelectedEmployeeId(e.target.value)}
                  data-testid="line-graph-employee-select"
                >
                  <option value="">Select a crew member</option>
                  {employees.map((e) => (
                    <option key={e.id} value={e.id}>{e.name}</option>
                  ))}
                </select>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">Graph Type</label>
                <select
                  className="w-full h-10 rounded-lg border-2 border-gray-200 bg-white px-3 text-sm focus:border-primary transition-colors"
                  value={selectedGraphKind}
                  onChange={(e) => setSelectedGraphKind(e.target.value)}
                  data-testid="line-graph-kind-select"
                >
                  <option value="quarter">Quarterly</option>
                  <option value="ytd">Year-to-date</option>
                </select>
              </div>
            </div>

            <LineGraphUpload
              employeeId={selectedEmployeeId}
              quarter={selectedQuarter}
              year={parseInt(selectedYear)}
              graphKind={selectedGraphKind}
              onUploadSuccess={() => toast.success("Line graph uploaded successfully!")}
            />
          </div>
        </div>

        {/* Employee List */}
        {employees.length === 0 ? (
          <div className="bubba-card p-12 text-center" data-testid="no-employees">
            <User className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-serif font-bold mb-2">No crew members for {selectedQuarter} {selectedYear}</h3>
            <p className="text-gray-500 mb-6">
              Upload employee data from the dashboard for this quarter to start generating reviews
            </p>
            <a href="/" className="bubba-btn-primary inline-block" data-testid="go-to-dashboard-btn">
              Go to Dashboard
            </a>
          </div>
        ) : (
          <div className="space-y-4" data-testid="employee-review-list">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-serif font-bold text-foreground">
                Reviews for {selectedQuarter} {selectedYear}
              </h2>
              <span className="px-3 py-1 bg-gray-100 rounded-full text-sm font-semibold text-gray-600">
                {employees.length} crew members
              </span>
            </div>
            
            {employees.map((employee) => {
              const hasReview = hasRecentReview(employee.id);
              const review = getEmployeeReview(employee.id);
              const isGenerating = generating[employee.id];
              const tier = getTierLabel(employee);
              const isExpanded = expandedTrends[employee.id];
              const employeeTrend = trendData[employee.id];
              
              return (
                <div key={employee.id} className="bubba-card" data-testid={`employee-review-card-${employee.id}`}>
                  <div className="p-5">
                    <div className="flex items-center justify-between flex-wrap gap-4">
                      <div className="flex items-center gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-lg font-serif font-bold text-foreground" data-testid={`employee-name-${employee.id}`}>
                              {employee.name}
                            </h3>
                            <span className={`px-2 py-0.5 rounded text-xs font-bold ${tier.color}`}>
                              {tier.label}
                            </span>
                          </div>
                          <p className="text-gray-500 text-sm" data-testid={`employee-position-${employee.id}`}>
                            {employee.job_title || "Server"} • Rank #{employee.peer_rank || 'N/A'}
                          </p>
                        </div>
                        
                        {/* KPI Summary - V2 Metrics */}
                        <div className="hidden md:flex gap-3 ml-4">
                          {[
                            { label: 'Score', value: formatNumber(employee.pre_dar_score || employee.total_score), color: 'text-primary' },
                            { label: 'PPA', value: `$${(employee.ppa || 0).toFixed(0)}`, color: 'text-secondary' },
                            { label: 'LBW/G', value: `$${(employee.lbw_per_guest || 0).toFixed(2)}`, color: 'text-gray-600' },
                          ].map((kpi, i) => (
                            <div key={i} className="text-center px-3 py-1 bg-gray-50 rounded-lg">
                              <div className={`text-sm font-serif font-bold ${kpi.color}`}>{kpi.value}</div>
                              <div className="text-[10px] text-gray-500 uppercase font-semibold">{kpi.label}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        {/* Trend Toggle Button */}
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => toggleTrend(employee.id)}
                          className="flex items-center gap-1"
                          data-testid={`trend-toggle-${employee.id}`}
                        >
                          <TrendingUp className="w-4 h-4" />
                          Trends
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </Button>
                        
                        {hasReview && (
                          <div className="flex items-center gap-2 text-green-600">
                            <Clock className="w-4 h-4" />
                            <span className="text-sm font-medium">
                              {new Date(review.created_at).toLocaleDateString()}
                            </span>
                          </div>
                        )}
                        
                        <Button
                          onClick={() => generateReview(employee.id)}
                          disabled={isGenerating}
                          className={hasReview ? "bubba-btn-secondary" : "bubba-btn-primary"}
                          data-testid={`generate-review-btn-${employee.id}`}
                        >
                          {isGenerating ? (
                            <div className="flex items-center gap-2">
                              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                              Generating...
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Download className="w-4 h-4" />
                              {hasReview ? "Regenerate" : "Generate"}
                            </div>
                          )}
                        </Button>
                      </div>
                    </div>
                    
                    {/* Expandable Trend Section */}
                    {isExpanded && (
                      <div className="mt-4 pt-4 border-t border-gray-200" data-testid={`trend-section-${employee.id}`}>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                          {/* Trend Chart */}
                          <div className="bg-gray-50 rounded-lg p-4">
                            <h4 className="text-sm font-semibold text-gray-700 mb-3">
                              📊 Quarter Comparison Chart
                            </h4>
                            <img 
                              src={`${API}/v2/trends/${selectedYear}/${selectedQuarter}/employee/${employee.id}?chart_type=comparison`}
                              alt={`${employee.name} trend chart`}
                              className="w-full rounded-lg"
                              data-testid={`trend-chart-${employee.id}`}
                            />
                          </div>
                          
                          {/* Metric Changes */}
                          <div className="bg-gray-50 rounded-lg p-4">
                            <h4 className="text-sm font-semibold text-gray-700 mb-3">
                              📈 Metric Changes ({employeeTrend?.previous_quarter || 'Prev'} → {selectedQuarter})
                            </h4>
                            
                            {!employeeTrend?.has_previous_data && (
                              <div className="text-sm text-gray-500 italic mb-3">
                                No previous quarter data available for comparison
                              </div>
                            )}
                            
                            <div className="grid grid-cols-2 gap-3">
                              {[
                                { key: 'ppa', label: 'PPA', format: '$', higherBetter: true },
                                { key: 'lbw_per_guest', label: 'LBW/Guest', format: '$', higherBetter: true },
                                { key: 'glassware_per_guest', label: 'Glass/Guest', format: '$', higherBetter: true },
                                { key: 'guests_per_lsc', label: 'Guests/LSC', format: '', higherBetter: false },
                                { key: 'cv_score', label: 'CV Score', format: '', higherBetter: true },
                                { key: 'pre_dar_score', label: 'Total Score', format: '', higherBetter: true },
                              ].map(metric => {
                                const currentVal = employeeTrend?.current?.[metric.key] || employee[metric.key] || 0;
                                const prevVal = employeeTrend?.previous?.[metric.key] || 0;
                                const change = employeeTrend?.changes?.[metric.key] || 0;
                                const indicator = getChangeIndicator(change, metric.higherBetter);
                                
                                return (
                                  <div 
                                    key={metric.key}
                                    className={`p-2 rounded-lg border ${indicator.bg} border-gray-200`}
                                  >
                                    <div className="text-xs text-gray-500 font-medium">{metric.label}</div>
                                    <div className="flex items-center justify-between">
                                      <span className="text-sm font-bold text-foreground">
                                        {metric.format}{currentVal?.toFixed(2) || '0'}
                                      </span>
                                      <span className={`text-xs font-semibold ${indicator.color}`}>
                                        {indicator.icon} {Math.abs(change).toFixed(1)}%
                                      </span>
                                    </div>
                                    {employeeTrend?.has_previous_data && (
                                      <div className="text-xs text-gray-400">
                                        was {metric.format}{prevVal?.toFixed(2) || '0'}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
