import { useState, useEffect, useCallback } from "react";
import { Trash2, Eye, FileText, Search, Filter, Users, X, Calendar } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { formatCurrency, formatLSCRatio, formatNumber } from "../utils/formatters";
import ConfirmDialog from "../components/ConfirmDialog";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function EmployeeList() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [performanceFilter, setPerformanceFilter] = useState("all");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [employeeToDelete, setEmployeeToDelete] = useState(null);
  
  // V2 Quarter Selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      // Use V2 API with quarter selection
      const response = await axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
      toast.error("Error loading employees");
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  const deleteEmployee = async () => {
    if (!employeeToDelete) return;
    try {
      await axios.delete(`${API}/v2/employees/${employeeToDelete}`);
      toast.success("Employee deleted successfully");
      fetchEmployees();
    } catch (error) {
      console.error("Error deleting employee:", error);
      toast.error("Error deleting employee");
    } finally {
      setConfirmDeleteOpen(false);
      setEmployeeToDelete(null);
    }
  };

  // V2 Performance tier mapping
  const getPerformanceLevelLocal = (tier, score) => {
    if (tier) {
      const tierMap = {
        "Top Performer": { text: "Top Performer", class: "performance-excellent" },
        "Above Average": { text: "Above Average", class: "performance-above-average" },
        "Below Average": { text: "Below Average", class: "performance-satisfactory" },
        "Needs Immediate Improvement": { text: "Needs Improvement", class: "performance-below" }
      };
      return tierMap[tier] || { text: tier, class: "performance-satisfactory" };
    }
    // Fallback for legacy data
    if (!score) return { text: "Not Assessed", class: "performance-below" };
    if (score >= 90) return { text: "Excellent", class: "performance-excellent" };
    if (score >= 80) return { text: "Above Average", class: "performance-above-average" };
    if (score >= 70) return { text: "Satisfactory", class: "performance-satisfactory" };
    if (score >= 60) return { text: "Needs Improvement", class: "performance-needs-improvement" };
    return { text: "Below Expectations", class: "performance-below" };
  };

  const filteredEmployees = employees.filter(employee => {
    const matchesSearch = employee.name.toLowerCase().includes(searchTerm.toLowerCase());
    const performance = getPerformanceLevelLocal(employee.performance_tier, employee.total_score || employee.cumulative_score);
    const matchesPerformance = performanceFilter === "all" || 
                              performance.text.toLowerCase().includes(performanceFilter.toLowerCase());
    return matchesSearch && matchesPerformance;
  });

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
      <div className="splash-blue" style={{ top: '15%', right: '5%' }} />
      <div className="splash-red" style={{ bottom: '20%', left: '3%', opacity: 0.5 }} />
      
      <ConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title="Delete crew member?"
        description="This will permanently delete this employee record."
        confirmText="Delete"
        cancelText="Cancel"
        onConfirm={deleteEmployee}
        variant="destructive"
      />
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Users className="w-8 h-8 text-secondary" />
            <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
              Crew Management
            </h1>
          </div>
          <p className="text-gray-500" data-testid="page-subtitle">
            View and manage all crew performance data
          </p>
        </div>

        {/* Filters */}
        <div className="bubba-card mb-8" data-testid="filters-card">
          <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <Filter className="w-5 h-5 text-secondary" />
              </div>
              <h2 className="text-lg font-serif font-bold text-foreground">Filters & Search</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              {/* Quarter Selection */}
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <Calendar className="w-4 h-4" />
                  Quarter
                </label>
                <div className="flex gap-2">
                  <select 
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                    className="flex-1 h-10 px-3 border-2 border-gray-200 rounded-lg focus:border-secondary"
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
                    className="flex-1 h-10 px-3 border-2 border-gray-200 rounded-lg focus:border-secondary"
                    data-testid="quarter-select"
                  >
                    <option value="Q1">Q1</option>
                    <option value="Q2">Q2</option>
                    <option value="Q3">Q3</option>
                    <option value="Q4">Q4</option>
                  </select>
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Search</label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                  <Input
                    placeholder="Search by name..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9 border-2 border-gray-200 rounded-lg focus:border-secondary"
                    data-testid="search-input"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Performance Tier</label>
                <Select value={performanceFilter} onValueChange={setPerformanceFilter}>
                  <SelectTrigger data-testid="performance-filter" className="border-2 border-gray-200">
                    <SelectValue placeholder="All Tiers" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Tiers</SelectItem>
                    <SelectItem value="top performer">Top Performer</SelectItem>
                    <SelectItem value="above average">Above Average</SelectItem>
                    <SelectItem value="below average">Below Average</SelectItem>
                    <SelectItem value="needs improvement">Needs Improvement</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">&nbsp;</label>
                <div className="h-10 flex items-center">
                  <span className="text-sm text-gray-500">
                    {selectedQuarter} {selectedYear}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Results Summary */}
        <div className="mb-6" data-testid="results-summary">
          <p className="text-gray-500 font-medium">
            Showing <span className="text-primary font-bold">{filteredEmployees.length}</span> of {employees.length} crew members
          </p>
        </div>

        {/* Employee Grid */}
        {filteredEmployees.length === 0 ? (
          <div className="bubba-card p-12 text-center" data-testid="no-results">
            <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-serif font-bold mb-2">No crew members found</h3>
            <p className="text-gray-500">
              {employees.length === 0 
                ? `No data for ${selectedQuarter} ${selectedYear}. Upload a file on the Dashboard.` 
                : "Try adjusting your search or filters"}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6" data-testid="employee-grid">
            {filteredEmployees.map((employee) => {
              const performance = getPerformanceLevelLocal(employee.performance_tier, employee.total_score || employee.pre_dar_score);
              // Use V2 fields with fallbacks to V1
              const score = employee.pre_dar_score || employee.total_score || employee.cumulative_score || 0;
              const ppa = employee.ppa || 0;
              const lbwPerGuest = employee.lbw_per_guest || employee.pplbw || 0;
              const glassPerGuest = employee.glassware_per_guest || employee.gpg || 0;
              const guestsPerLsc = employee.guests_per_lsc;
              const cvScore = employee.cv_score || 0;
              
              return (
                <div key={employee.id} className="bubba-card" data-testid={`employee-card-${employee.id}`}>
                  <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
                  <div className="p-5 pt-7">
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-serif font-bold text-foreground" data-testid={`employee-name-${employee.id}`}>
                          {employee.name}
                        </h3>
                        <p className="text-gray-500 text-sm" data-testid={`employee-rank-${employee.id}`}>
                          Rank: #{employee.peer_rank || '-'} of {employees.length}
                        </p>
                      </div>
                      <span className={`performance-badge ${performance.class}`} data-testid={`employee-performance-${employee.id}`}>
                        {performance.text}
                      </span>
                    </div>
                    
                    {/* All 6 Metrics Grid - V2 Fields */}
                    <div className="grid grid-cols-3 gap-2 mb-4">
                      <div className="text-center p-2 bg-red-50 rounded-lg border border-red-100">
                        <div className="text-lg font-serif font-bold text-primary">{formatNumber(score)}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">Score</div>
                      </div>
                      <div className="text-center p-2 bg-blue-50 rounded-lg border border-blue-100">
                        <div className="text-sm font-serif font-bold text-secondary">{formatCurrency(ppa)}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">PPA</div>
                      </div>
                      <div className="text-center p-2 bg-purple-50 rounded-lg border border-purple-100">
                        <div className="text-sm font-serif font-bold text-purple-700">{formatCurrency(lbwPerGuest)}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">LBW/G</div>
                      </div>
                      <div className="text-center p-2 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="text-sm font-serif font-bold text-gray-700">{formatCurrency(glassPerGuest)}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">Glass/G</div>
                      </div>
                      <div className="text-center p-2 bg-green-50 rounded-lg border border-green-100">
                        <div className="text-sm font-serif font-bold text-green-700">{guestsPerLsc ? formatNumber(guestsPerLsc) : 'N/A'}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">G/LSC</div>
                      </div>
                      <div className="text-center p-2 bg-yellow-50 rounded-lg border border-yellow-100">
                        <div className="text-sm font-serif font-bold text-yellow-700">{cvScore > 0 ? '+' : ''}{formatNumber(cvScore)}</div>
                        <div className="text-[10px] text-gray-500 font-semibold uppercase">CV</div>
                      </div>
                    </div>
                    
                    {/* Actions */}
                    <div className="flex gap-2">
                      <Button 
                        onClick={() => {
                          setSelectedEmployee(employee);
                          setShowDetails(true);
                        }}
                        variant="outline" 
                        size="sm" 
                        className="flex-1 border-2"
                        data-testid={`view-details-btn-${employee.id}`}
                      >
                        <Eye className="w-4 h-4 mr-2" />
                        Details
                      </Button>
                      
                      <Button 
                        onClick={() => {
                          setEmployeeToDelete(employee.id);
                          setConfirmDeleteOpen(true);
                        }}
                        variant="destructive" 
                        size="sm"
                        data-testid={`delete-employee-btn-${employee.id}`}
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Employee Details Modal */}
        {showDetails && selectedEmployee && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" data-testid="employee-details-modal">
            <div className="bg-white rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-auto shadow-2xl">
              <div className="p-6 border-b border-gray-200 sticky top-0 bg-white z-10">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-serif font-black text-primary">{selectedEmployee.name}</h2>
                    <p className="text-gray-500">
                      Rank #{selectedEmployee.peer_rank || '-'} of {employees.length} • {selectedEmployee.performance_tier || 'Not Assessed'}
                    </p>
                  </div>
                  <Button 
                    onClick={() => setShowDetails(false)}
                    variant="outline"
                    size="sm"
                    className="border-2"
                    data-testid="close-modal-btn"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </div>
              
              <div className="p-6">
                {/* Total Score Summary */}
                <div className="mb-6 p-4 bg-gradient-to-r from-red-50 to-blue-50 rounded-xl border-2 border-gray-200">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-serif font-bold text-foreground">Total Score</h3>
                      <p className="text-sm text-gray-500">Weighted score + bonuses</p>
                    </div>
                    <div className="text-right">
                      <div className="text-4xl font-serif font-black text-primary">
                        {formatNumber(selectedEmployee.pre_dar_score || selectedEmployee.total_score || 0)}
                      </div>
                      <div className="text-sm text-gray-500">points</div>
                    </div>
                  </div>
                </div>

                {/* Scoring Breakdown by Category */}
                <div className="mb-6">
                  <h4 className="font-serif font-bold text-foreground mb-4 flex items-center gap-2">
                    <Target className="w-5 h-5 text-secondary" />
                    Scoring Breakdown by Category
                  </h4>
                  
                  <div className="space-y-3">
                    {/* PPA - 25% */}
                    <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-foreground">PPA (Per Person Average)</span>
                          <span className="ml-2 text-xs bg-blue-200 text-blue-800 px-2 py-0.5 rounded-full">25% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-secondary">{formatNumber(((selectedEmployee.score_ppa || 0) * 0.25))}</span>
                          <span className="text-gray-500 text-sm"> / 25 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-gray-600">Value: {formatCurrency(selectedEmployee.ppa || 0)}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-600">Score: {formatNumber(selectedEmployee.score_ppa || 0)}%</span>
                        {(selectedEmployee.bonus_ppa || 0) > 0 && (
                          <>
                            <span className="text-gray-400">|</span>
                            <span className="text-green-600 font-medium">+{formatNumber(selectedEmployee.bonus_ppa)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-secondary rounded-full transition-all" 
                          style={{ width: `${Math.min(100, (selectedEmployee.score_ppa || 0))}%` }}
                        />
                      </div>
                    </div>

                    {/* LSC - 25% */}
                    <div className="p-4 bg-green-50 rounded-lg border border-green-100">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-foreground">LSC (Guests per Signup)</span>
                          <span className="ml-2 text-xs bg-green-200 text-green-800 px-2 py-0.5 rounded-full">25% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-green-700">{formatNumber(((selectedEmployee.score_lsc || 0) * 0.25))}</span>
                          <span className="text-gray-500 text-sm"> / 25 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-gray-600">Value: {selectedEmployee.guests_per_lsc ? formatNumber(selectedEmployee.guests_per_lsc) + ' G/LSC' : 'N/A'}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-600">Score: {formatNumber(selectedEmployee.score_lsc || 0)}%</span>
                        {(selectedEmployee.bonus_lsc || 0) > 0 && (
                          <>
                            <span className="text-gray-400">|</span>
                            <span className="text-green-600 font-medium">+{formatNumber(selectedEmployee.bonus_lsc)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-green-600 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, (selectedEmployee.score_lsc || 0))}%` }}
                        />
                      </div>
                    </div>

                    {/* LBW - 20% */}
                    <div className="p-4 bg-purple-50 rounded-lg border border-purple-100">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-foreground">LBW per Guest</span>
                          <span className="ml-2 text-xs bg-purple-200 text-purple-800 px-2 py-0.5 rounded-full">20% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-purple-700">{formatNumber(((selectedEmployee.score_lbw || 0) * 0.20))}</span>
                          <span className="text-gray-500 text-sm"> / 20 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-gray-600">Value: {formatCurrency(selectedEmployee.lbw_per_guest || 0)}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-600">Score: {formatNumber(selectedEmployee.score_lbw || 0)}%</span>
                        {(selectedEmployee.bonus_lbw || 0) > 0 && (
                          <>
                            <span className="text-gray-400">|</span>
                            <span className="text-green-600 font-medium">+{formatNumber(selectedEmployee.bonus_lbw)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-purple-600 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, (selectedEmployee.score_lbw || 0))}%` }}
                        />
                      </div>
                    </div>

                    {/* Glassware - 15% */}
                    <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-foreground">Glassware per Guest</span>
                          <span className="ml-2 text-xs bg-gray-200 text-gray-700 px-2 py-0.5 rounded-full">15% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-gray-700">{formatNumber(((selectedEmployee.score_glass || 0) * 0.15))}</span>
                          <span className="text-gray-500 text-sm"> / 15 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-gray-600">Value: {formatCurrency(selectedEmployee.glassware_per_guest || 0)}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-600">Score: {formatNumber(selectedEmployee.score_glass || 0)}%</span>
                        {(selectedEmployee.bonus_glass || 0) > 0 && (
                          <>
                            <span className="text-gray-400">|</span>
                            <span className="text-green-600 font-medium">+{formatNumber(selectedEmployee.bonus_glass)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gray-600 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, (selectedEmployee.score_glass || 0))}%` }}
                        />
                      </div>
                    </div>

                    {/* Customer Voice - 15% */}
                    <div className="p-4 bg-yellow-50 rounded-lg border border-yellow-100">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-foreground">Customer Voice & Reviews</span>
                          <span className="ml-2 text-xs bg-yellow-200 text-yellow-800 px-2 py-0.5 rounded-full">15% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-yellow-700">{formatNumber(((selectedEmployee.score_cv || 0) * 0.15))}</span>
                          <span className="text-gray-500 text-sm"> / 15 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm flex-wrap">
                        <span className="text-gray-600">CV Score: {selectedEmployee.cv_score > 0 ? '+' : ''}{formatNumber(selectedEmployee.cv_score || 0)}</span>
                        <span className="text-gray-400">|</span>
                        <span className="text-gray-600">Normalized: {formatNumber(selectedEmployee.score_cv || 0)}%</span>
                        {(selectedEmployee.review_tracker_bonus || 0) > 0 && (
                          <>
                            <span className="text-gray-400">|</span>
                            <span className="text-green-600 font-medium">+{formatNumber(selectedEmployee.review_tracker_bonus)} review bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-gray-200 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-yellow-500 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, (selectedEmployee.score_cv || 0))}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Score Summary Table */}
                <div className="mb-6 p-4 bg-gray-50 rounded-xl border border-gray-200">
                  <h4 className="font-serif font-bold text-foreground mb-3">Score Summary</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between py-1 border-b border-gray-200">
                      <span className="text-gray-600">Weighted Score (base)</span>
                      <span className="font-medium">{formatNumber(selectedEmployee.weighted_score || 0)}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-200">
                      <span className="text-gray-600">Metric Bonuses</span>
                      <span className="font-medium text-green-600">+{formatNumber(selectedEmployee.total_metric_bonus || 0)}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-200">
                      <span className="text-gray-600">Review Tracker Bonus</span>
                      <span className="font-medium text-green-600">+{formatNumber(selectedEmployee.review_tracker_bonus || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 font-bold text-base">
                      <span className="text-foreground">Final Score</span>
                      <span className="text-primary">{formatNumber(selectedEmployee.pre_dar_score || selectedEmployee.total_score || 0)}</span>
                    </div>
                  </div>
                </div>

                {/* Customer Voice Breakdown */}
                {(selectedEmployee.cv_promoters > 0 || selectedEmployee.cv_passives > 0 || selectedEmployee.cv_detractors > 0) && (
                  <div className="mb-6">
                    <h4 className="font-serif font-bold text-foreground mb-3">Customer Voice Breakdown</h4>
                    <div className="grid grid-cols-3 gap-2">
                      <div className="text-center p-3 bg-green-50 rounded-lg border border-green-100">
                        <div className="text-xl font-bold text-green-700">{selectedEmployee.cv_promoters || 0}</div>
                        <div className="text-xs text-gray-500">Promoters</div>
                        <div className="text-xs text-green-600 font-medium">+{(selectedEmployee.cv_promoters || 0) * 1} pts</div>
                      </div>
                      <div className="text-center p-3 bg-gray-100 rounded-lg border border-gray-200">
                        <div className="text-xl font-bold text-gray-600">{selectedEmployee.cv_passives || 0}</div>
                        <div className="text-xs text-gray-500">Passives</div>
                        <div className="text-xs text-gray-500">0 pts</div>
                      </div>
                      <div className="text-center p-3 bg-red-50 rounded-lg border border-red-100">
                        <div className="text-xl font-bold text-red-700">{selectedEmployee.cv_detractors || 0}</div>
                        <div className="text-xs text-gray-500">Detractors</div>
                        <div className="text-xs text-red-600 font-medium">{(selectedEmployee.cv_detractors || 0) * -2} pts</div>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Raw Data Section */}
                <div>
                  <h4 className="font-serif font-bold text-foreground mb-3">Raw Input Data</h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">Guests</span>
                      <span className="font-medium">{formatNumber(selectedEmployee.guests || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">Net Sales</span>
                      <span className="font-medium">{formatCurrency(selectedEmployee.net_sales || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">LBW Total</span>
                      <span className="font-medium">{formatCurrency(selectedEmployee.lbw || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">Glassware</span>
                      <span className="font-medium">{formatCurrency(selectedEmployee.glassware_sales || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">LSC Count</span>
                      <span className="font-medium">{formatNumber(selectedEmployee.lsc_count || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                      <span className="text-gray-500">Review Mentions</span>
                      <span className="font-medium">{formatNumber(selectedEmployee.review_mentions || 0)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
