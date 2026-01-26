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
            <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-auto shadow-2xl">
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-serif font-black text-primary">{selectedEmployee.name}</h2>
                    <p className="text-gray-500">{selectedEmployee.position}</p>
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
                {/* Detailed KPIs */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                  {[
                    { label: 'Cumulative Score', value: formatNumber(selectedEmployee.cumulative_score), color: 'text-primary', bg: 'bg-red-50' },
                    { label: 'PPA', value: formatCurrency(selectedEmployee.ppa), color: 'text-secondary', bg: 'bg-blue-50' },
                    { label: 'GPG', value: formatCurrency(selectedEmployee.gpg), color: 'text-gray-700', bg: 'bg-gray-50' },
                    { label: 'PPLBW', value: formatCurrency(selectedEmployee.pplbw), color: 'text-gray-700', bg: 'bg-gray-50' },
                    { label: 'LSC Ratio', value: formatLSCRatio(selectedEmployee.lsc_ratio), color: 'text-gray-700', bg: 'bg-gray-50' },
                    { label: 'Bonus Points', value: formatNumber(selectedEmployee.metric_bonus_points), color: 'text-yellow-600', bg: 'bg-yellow-50' },
                  ].map((kpi, i) => (
                    <div key={i} className={`text-center p-4 ${kpi.bg} rounded-xl`}>
                      <div className={`text-2xl font-serif font-bold ${kpi.color} mb-1`}>{kpi.value}</div>
                      <div className="text-xs text-gray-500 font-semibold uppercase">{kpi.label}</div>
                    </div>
                  ))}
                </div>
                
                {/* Additional Data */}
                {Object.keys(selectedEmployee.additional_data || {}).length > 0 && (
                  <div>
                    <h4 className="font-serif font-bold text-foreground mb-3">Additional Information</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {Object.entries(selectedEmployee.additional_data || {})
                        .filter(([key]) => key !== "metric_tiers")
                        .map(([key, value]) => (
                          <div key={key} className="flex justify-between py-2 px-3 bg-gray-50 rounded-lg text-sm">
                            <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                            <span className="font-medium">{String(value)}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
