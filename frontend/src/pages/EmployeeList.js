import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { Trash2, Eye, FileText, Search, Filter, Users, X, Calendar, Target, Plus, Pencil, Save, CheckSquare, Square, XSquare } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import { formatCurrency, formatLSCRatio, formatNumber } from "../utils/formatters";
import ConfirmDialog from "../components/ConfirmDialog";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

// Default values for new employee form
const emptyEmployee = {
  name: "",
  display_name: "",  // Custom name for dashboards/reports
  report_name: "",   // Original POS name for matching
  job_title: "server",
  aliases: "",  // Comma-separated aliases
  guests: 0,
  net_sales: 0,
  lbw: 0,
  glassware_sales: 0,
  lsc_count: 0,
  nps_score: 0,
  cv_promoters: 0,
  cv_passives: 0,
  cv_detractors: 0,
  review_mentions: 0
};

export default function EmployeeList() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [performanceFilter, setPerformanceFilter] = useState("all");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [employeeToDelete, setEmployeeToDelete] = useState(null);
  
  // Multi-select state
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [confirmBulkDeleteOpen, setConfirmBulkDeleteOpen] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  
  // Edit/Add modal state
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [formData, setFormData] = useState(emptyEmployee);
  const [saving, setSaving] = useState(false);
  
  // V2 Quarter Selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  
  // Use location to detect route changes and refresh data
  const location = useLocation();

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      // Use V2 API with quarter selection
      const response = await api.get(`/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      setEmployees(response.data);
    } catch (error) {
      toast.error("Error loading employees");
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  // Refresh when navigating to this page or when window gains focus
  useEffect(() => {
    // Refresh on route change to this page
    fetchEmployees();
    
    // Refresh when window gains focus (user returns to tab)
    const handleFocus = () => {
      fetchEmployees();
    };
    
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [location.key, fetchEmployees]);

  const deleteEmployee = async () => {
    if (!employeeToDelete) return;
    try {
      await api.delete(`/v2/employees/${employeeToDelete}`);
      toast.success("Employee deleted successfully");
      fetchEmployees();
    } catch (error) {
      toast.error("Error deleting employee");
    } finally {
      setConfirmDeleteOpen(false);
      setEmployeeToDelete(null);
    }
  };

  // Multi-select handlers
  const toggleSelectMode = () => {
    setSelectMode(!selectMode);
    setSelectedIds(new Set());
  };

  const toggleEmployeeSelection = (empId) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(empId)) {
      newSelected.delete(empId);
    } else {
      newSelected.add(empId);
    }
    setSelectedIds(newSelected);
  };

  const selectAll = () => {
    const allIds = new Set(filteredEmployees.map(emp => emp.id));
    setSelectedIds(allIds);
  };

  const deselectAll = () => {
    setSelectedIds(new Set());
  };

  const bulkDeleteEmployees = async () => {
    if (selectedIds.size === 0) return;
    
    setBulkDeleting(true);
    try {
      const response = await api.post('/v2/employees/cleanup/delete', {
        employee_ids: Array.from(selectedIds)
      });
      
      if (response.data.success) {
        toast.success(`Deleted ${response.data.deleted_count} employees`);
        setSelectedIds(new Set());
        setSelectMode(false);
        fetchEmployees();
      } else {
        toast.error("Some employees could not be deleted");
      }
    } catch (error) {
      toast.error("Error deleting employees");
    } finally {
      setBulkDeleting(false);
      setConfirmBulkDeleteOpen(false);
    }
  };

  // Open modal for new employee
  const openNewEmployeeModal = () => {
    setEditingEmployee(null);
    setFormData({ ...emptyEmployee });
    setShowEditModal(true);
  };

  // Open modal for editing existing employee
  const openEditModal = (employee) => {
    setEditingEmployee(employee);
    setFormData({
      name: employee.name || "",
      display_name: employee.display_name || employee.name || "",
      report_name: employee.report_name || "",
      job_title: employee.job_title || "server",
      aliases: (employee.aliases || []).join(", "),  // Convert array to comma-separated string
      guests: employee.guests || 0,
      net_sales: employee.net_sales || 0,
      lbw: employee.lbw || 0,
      glassware_sales: employee.glassware_sales || 0,
      lsc_count: employee.lsc_count || 0,
      nps_score: employee.nps_score || 0,
      cv_promoters: employee.cv_promoters || 0,
      cv_passives: employee.cv_passives || 0,
      cv_detractors: employee.cv_detractors || 0,
      review_mentions: employee.review_mentions || 0
    });
    setShowEditModal(true);
  };

  // Handle form field changes
  const handleFormChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  // Save employee (create or update)
  const saveEmployee = async () => {
    if (!formData.name.trim()) {
      toast.error("Display name is required");
      return;
    }
    
    // Convert aliases string to array
    const aliasesArray = formData.aliases 
      ? formData.aliases.split(",").map(a => a.trim()).filter(a => a)
      : [];
    
    // Add report_name to aliases for better matching
    const reportName = formData.report_name?.trim();
    if (reportName && !aliasesArray.includes(reportName)) {
      aliasesArray.push(reportName);
    }
    
    const dataToSave = {
      ...formData,
      display_name: formData.name,  // Display name = main name field
      aliases: aliasesArray
    };
    
    setSaving(true);
    try {
      if (editingEmployee) {
        // Update existing
        await api.put(`/v2/employees/${editingEmployee.id}`, dataToSave);
        toast.success(`Updated ${formData.name}`);
      } else {
        // Create new
        await api.post(`/v2/employees`, {
          ...dataToSave,
          year: selectedYear,
          quarter: selectedQuarter
        });
        toast.success(`Created ${formData.name}`);
      }
      setShowEditModal(false);
      fetchEmployees();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Error saving employee");
    } finally {
      setSaving(false);
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

  // Tier hierarchy for sorting (lower number = higher rank)
  const TIER_ORDER = {
    'trainer': 1,
    'bartender': 2,
    'a-server': 3,
    'b-server': 4,
    'c-server': 5,
    'server': 6  // Default/unclassified servers
  };

  const getTierOrder = (jobTitle) => {
    if (!jobTitle) return 99;
    const normalized = jobTitle.toLowerCase().trim();
    return TIER_ORDER[normalized] || 99;
  };

  const filteredEmployees = employees
    .filter(employee => {
      const matchesSearch = employee.name.toLowerCase().includes(searchTerm.toLowerCase());
      const performance = getPerformanceLevelLocal(employee.performance_tier, employee.total_score || employee.cumulative_score);
      const matchesPerformance = performanceFilter === "all" || 
                                performance.text.toLowerCase().includes(performanceFilter.toLowerCase());
      return matchesSearch && matchesPerformance;
    })
    .sort((a, b) => {
      // Sort alphabetically by name
      const nameA = (a.name || '').toLowerCase();
      const nameB = (b.name || '').toLowerCase();
      return nameA.localeCompare(nameB);
    });

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
      
      {/* Bulk Delete Confirm Dialog */}
      <ConfirmDialog
        open={confirmBulkDeleteOpen}
        onOpenChange={setConfirmBulkDeleteOpen}
        title={`Delete ${selectedIds.size} crew members?`}
        description="This will permanently delete all selected employee records. This action cannot be undone."
        confirmText={bulkDeleting ? "Deleting..." : `Delete ${selectedIds.size} Employees`}
        cancelText="Cancel"
        onConfirm={bulkDeleteEmployees}
        variant="destructive"
      />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center gap-3 mb-2">
              <Users className="w-8 h-8 text-secondary" />
              <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
                Crew Management
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <Button
                onClick={toggleSelectMode}
                variant={selectMode ? "default" : "outline"}
                className={selectMode ? "bg-blue-600 hover:bg-blue-700 text-white" : "border-slate-600 hover:bg-slate-700"}
                data-testid="select-mode-btn"
              >
                {selectMode ? <XSquare className="w-4 h-4 mr-2" /> : <CheckSquare className="w-4 h-4 mr-2" />}
                {selectMode ? "Cancel Selection" : "Select Multiple"}
              </Button>
              <Button
                onClick={openNewEmployeeModal}
                className="bg-green-600 hover:bg-green-700 text-white"
                data-testid="add-employee-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                New Employee
              </Button>
            </div>
          </div>
          <p className="text-slate-400" data-testid="page-subtitle">
            View and manage all crew performance data
          </p>
        </div>

        {/* Bulk Action Bar - Only visible in select mode */}
        {selectMode && (
          <div className="bubba-card mb-4 bg-blue-900/30 border-blue-500/30" data-testid="bulk-action-bar">
            <div className="p-4 flex items-center justify-between flex-wrap gap-3">
              <div className="flex items-center gap-4">
                <span className="text-slate-200 font-medium">
                  {selectedIds.size} of {filteredEmployees.length} selected
                </span>
                <div className="flex gap-2">
                  <Button
                    onClick={selectAll}
                    variant="outline"
                    size="sm"
                    className="border-slate-500 text-slate-200 hover:bg-slate-700"
                    data-testid="select-all-btn"
                  >
                    Select All
                  </Button>
                  <Button
                    onClick={deselectAll}
                    variant="outline"
                    size="sm"
                    className="border-slate-500 text-slate-200 hover:bg-slate-700"
                    data-testid="deselect-all-btn"
                  >
                    Deselect All
                  </Button>
                </div>
              </div>
              <Button
                onClick={() => setConfirmBulkDeleteOpen(true)}
                disabled={selectedIds.size === 0}
                variant="destructive"
                className="bg-red-600 hover:bg-red-700"
                data-testid="bulk-delete-btn"
              >
                <Trash2 className="w-4 h-4 mr-2" />
                Delete Selected ({selectedIds.size})
              </Button>
            </div>
          </div>
        )}

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
                    className="flex-1 h-10 px-3 border-2 border-slate-600 rounded-lg focus:border-secondary bg-slate-700 text-slate-200"
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
                    className="flex-1 h-10 px-3 border-2 border-slate-600 rounded-lg focus:border-secondary bg-slate-700 text-slate-200"
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
                  <span className="text-sm text-slate-400">
                    {selectedQuarter} {selectedYear}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Results Summary */}
        <div className="mb-6" data-testid="results-summary">
          <p className="text-slate-400 font-medium">
            Showing <span className="text-primary font-bold">{filteredEmployees.length}</span> of {employees.length} crew members
          </p>
        </div>

        {/* Employee Grid */}
        {filteredEmployees.length === 0 ? (
          <div className="bubba-card p-12 text-center" data-testid="no-results">
            <FileText className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-serif font-bold mb-2">No crew members found</h3>
            <p className="text-slate-400">
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
                <div 
                  key={employee.id} 
                  className={`bubba-card relative ${selectMode && selectedIds.has(employee.id) ? 'ring-2 ring-blue-500 bg-blue-900/20' : ''}`} 
                  data-testid={`employee-card-${employee.id}`}
                  onClick={selectMode ? () => toggleEmployeeSelection(employee.id) : undefined}
                  style={selectMode ? { cursor: 'pointer' } : {}}
                >
                  {/* Checkbox overlay in select mode */}
                  {selectMode && (
                    <div className="absolute top-2 left-2 z-10">
                      <div 
                        className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-colors ${
                          selectedIds.has(employee.id) 
                            ? 'bg-blue-600 border-blue-600 text-white' 
                            : 'bg-slate-700 border-slate-500 hover:border-blue-400'
                        }`}
                        data-testid={`employee-checkbox-${employee.id}`}
                      >
                        {selectedIds.has(employee.id) && (
                          <CheckSquare className="w-4 h-4" />
                        )}
                      </div>
                    </div>
                  )}
                  <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
                  <div className={`p-5 pt-7 ${selectMode ? 'pl-10' : ''}`}>
                    <div className="flex items-start justify-between mb-4">
                      <div>
                        <h3 className="text-lg font-serif font-bold text-foreground" data-testid={`employee-name-${employee.id}`}>
                          {employee.name}
                        </h3>
                        <p className="text-sm text-slate-400 capitalize" data-testid={`employee-job-title-${employee.id}`}>
                          {employee.job_title || 'Server'}
                        </p>
                        <p className="text-slate-500 text-xs" data-testid={`employee-rank-${employee.id}`}>
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
                        <div className="text-[10px] text-slate-400 font-semibold uppercase">Score</div>
                      </div>
                      <div className="text-center p-2 bg-blue-50 rounded-lg border border-blue-100">
                        <div className="text-sm font-serif font-bold text-secondary">{formatCurrency(ppa)}</div>
                        <div className="text-[10px] text-slate-400 font-semibold uppercase">PPA</div>
                      </div>
                      <div className="text-center p-2 bg-purple-50 rounded-lg border border-purple-100">
                        <div className="text-sm font-serif font-bold text-purple-700">{formatCurrency(lbwPerGuest)}</div>
                        <div className="text-[10px] text-slate-400 font-semibold uppercase">LBW/G</div>
                      </div>
                      <div className="text-center p-2 bg-slate-600 rounded-lg border border-slate-500">
                        <div className="text-sm font-serif font-bold text-slate-100">{formatCurrency(glassPerGuest)}</div>
                        <div className="text-[10px] text-slate-300 font-semibold uppercase">Glass/G</div>
                      </div>
                      <div className="text-center p-2 bg-green-50 rounded-lg border border-green-100">
                        <div className="text-sm font-serif font-bold text-green-700">{guestsPerLsc ? formatNumber(guestsPerLsc) : 'N/A'}</div>
                        <div className="text-[10px] text-slate-400 font-semibold uppercase">G/LSC</div>
                      </div>
                      <div className="text-center p-2 bg-yellow-50 rounded-lg border border-yellow-100">
                        <div className="text-sm font-serif font-bold text-yellow-700">{cvScore > 0 ? '+' : ''}{formatNumber(cvScore)}</div>
                        <div className="text-[10px] text-slate-400 font-semibold uppercase">CV</div>
                      </div>
                    </div>
                    
                    {/* Actions - hidden in select mode */}
                    {!selectMode && (
                      <div className="flex gap-2">
                        <Button 
                          onClick={(e) => { e.stopPropagation(); openEditModal(employee); }}
                          variant="outline" 
                          size="sm" 
                          className="flex-1 border-2 border-blue-200 hover:bg-blue-50"
                          data-testid={`edit-employee-btn-${employee.id}`}
                        >
                          <Pencil className="w-4 h-4 mr-2" />
                          Edit
                        </Button>
                        <Button 
                          onClick={(e) => {
                            e.stopPropagation();
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
                          onClick={(e) => {
                            e.stopPropagation();
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
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Employee Details Modal */}
        {showDetails && selectedEmployee && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" data-testid="employee-details-modal">
            <div className="bg-slate-800 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-auto shadow-2xl">
              <div className="p-6 border-b border-gray-200 sticky top-0 bg-slate-800 z-10">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-2xl font-serif font-black text-primary">{selectedEmployee.name}</h2>
                    <p className="text-slate-400">
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
                <div className="mb-6 p-4 bg-slate-700 rounded-xl border-2 border-slate-600">
                  <div className="flex items-center justify-between">
                    <div>
                      <h3 className="text-lg font-serif font-bold text-white">Total Score</h3>
                      <p className="text-sm text-slate-300">Weighted score + bonuses</p>
                    </div>
                    <div className="text-right">
                      <div className="text-4xl font-serif font-black text-green-400">
                        {formatNumber(selectedEmployee.pre_dar_score || selectedEmployee.total_score || 0)}
                      </div>
                      <div className="text-sm text-slate-300">points</div>
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
                    {/* PPA - 25% weight, max 30 pts */}
                    <div className="p-4 bg-slate-700/50 rounded-lg border border-blue-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-white">PPA (Per Person Average)</span>
                          <span className="ml-2 text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">25% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-blue-400 text-lg">{formatNumber(Math.min((selectedEmployee.score_ppa || 0), 100) * 0.25 + (selectedEmployee.bonus_ppa || 0))}</span>
                          <span className="text-slate-400 text-sm"> / 30 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-slate-200">Value: {formatCurrency(selectedEmployee.ppa || 0)}</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-slate-200">Score: {formatNumber(selectedEmployee.score_ppa || 0)}%</span>
                        {(selectedEmployee.bonus_ppa || 0) > 0 && (
                          <>
                            <span className="text-slate-500">|</span>
                            <span className="text-green-400 font-medium">+{formatNumber(selectedEmployee.bonus_ppa)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-slate-600 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-blue-500 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, ((Math.min((selectedEmployee.score_ppa || 0), 100) * 0.25 + (selectedEmployee.bonus_ppa || 0)) / 30) * 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* LSC - 25% weight, max 30 pts */}
                    <div className="p-4 bg-slate-700/50 rounded-lg border border-green-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-white">LSC (Guests per Signup)</span>
                          <span className="ml-2 text-xs bg-green-600 text-white px-2 py-0.5 rounded-full">25% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-green-400 text-lg">{formatNumber(Math.min((selectedEmployee.score_lsc || 0), 100) * 0.25 + (selectedEmployee.bonus_lsc || 0))}</span>
                          <span className="text-slate-400 text-sm"> / 30 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-slate-200">Value: {selectedEmployee.guests_per_lsc ? formatNumber(selectedEmployee.guests_per_lsc) + ' G/LSC' : 'N/A'}</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-slate-200">Score: {formatNumber(selectedEmployee.score_lsc || 0)}%</span>
                        {(selectedEmployee.bonus_lsc || 0) > 0 && (
                          <>
                            <span className="text-slate-500">|</span>
                            <span className="text-green-400 font-medium">+{formatNumber(selectedEmployee.bonus_lsc)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-slate-600 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-green-500 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, ((Math.min((selectedEmployee.score_lsc || 0), 100) * 0.25 + (selectedEmployee.bonus_lsc || 0)) / 30) * 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* LBW - 20% weight, max 25 pts */}
                    <div className="p-4 bg-slate-700/50 rounded-lg border border-purple-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-white">LBW per Guest</span>
                          <span className="ml-2 text-xs bg-purple-600 text-white px-2 py-0.5 rounded-full">20% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-purple-400 text-lg">{formatNumber(Math.min((selectedEmployee.score_lbw || 0), 100) * 0.20 + (selectedEmployee.bonus_lbw || 0))}</span>
                          <span className="text-slate-400 text-sm"> / 25 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-slate-200">Value: {formatCurrency(selectedEmployee.lbw_per_guest || 0)}</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-slate-200">Score: {formatNumber(selectedEmployee.score_lbw || 0)}%</span>
                        {(selectedEmployee.bonus_lbw || 0) > 0 && (
                          <>
                            <span className="text-slate-500">|</span>
                            <span className="text-green-400 font-medium">+{formatNumber(selectedEmployee.bonus_lbw)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-slate-600 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-purple-500 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, ((Math.min((selectedEmployee.score_lbw || 0), 100) * 0.20 + (selectedEmployee.bonus_lbw || 0)) / 25) * 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Glassware - 15% weight, max 20 pts */}
                    <div className="p-4 bg-slate-700/50 rounded-lg border border-slate-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-white">Glassware per Guest</span>
                          <span className="ml-2 text-xs bg-slate-600 text-white px-2 py-0.5 rounded-full">15% weight</span>
                        </div>
                        <div className="text-right">
                          <span className="font-bold text-slate-300 text-lg">{formatNumber(Math.min((selectedEmployee.score_glass || 0), 100) * 0.15 + (selectedEmployee.bonus_glass || 0))}</span>
                          <span className="text-slate-400 text-sm"> / 20 pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <span className="text-slate-200">Value: {formatCurrency(selectedEmployee.glassware_per_guest || 0)}</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-slate-200">Score: {formatNumber(selectedEmployee.score_glass || 0)}%</span>
                        {(selectedEmployee.bonus_glass || 0) > 0 && (
                          <>
                            <span className="text-slate-500">|</span>
                            <span className="text-green-400 font-medium">+{formatNumber(selectedEmployee.bonus_glass)} bonus</span>
                          </>
                        )}
                      </div>
                      <div className="mt-2 h-2 bg-slate-600 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-slate-400 rounded-full transition-all" 
                          style={{ width: `${Math.min(100, ((Math.min((selectedEmployee.score_glass || 0), 100) * 0.15 + (selectedEmployee.bonus_glass || 0)) / 20) * 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Customer Voice - Direct Points (not weighted) */}
                    <div className="p-4 bg-slate-700/50 rounded-lg border border-yellow-500/30">
                      <div className="flex items-center justify-between mb-2">
                        <div>
                          <span className="font-semibold text-white">Customer Voice</span>
                          <span className="ml-2 text-xs bg-yellow-600 text-white px-2 py-0.5 rounded-full">Direct Points</span>
                        </div>
                        <div className="text-right">
                          <span className={`font-bold text-lg ${(selectedEmployee.cv_score || 0) >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
                            {(selectedEmployee.cv_score || 0) >= 0 ? '+' : ''}{formatNumber(selectedEmployee.cv_score || 0)}
                          </span>
                          <span className="text-slate-400 text-sm"> pts</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4 text-sm flex-wrap">
                        <span className="text-cyan-400">NPS {selectedEmployee.nps_score || 0}% = {((selectedEmployee.nps_score || 0) / 10).toFixed(1)} pts</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-green-400">{selectedEmployee.cv_promoters || 0} promoters (+{((selectedEmployee.cv_promoters || 0) * 0.5).toFixed(1)} pts)</span>
                        <span className="text-slate-500">|</span>
                        <span className="text-red-400">{selectedEmployee.cv_detractors || 0} detractors ({(selectedEmployee.cv_detractors || 0) * -1} pts)</span>
                      </div>
                      <div className="mt-2 text-xs text-slate-400">
                        Formula: NPS%÷10 + Promoters×0.5 + Detractors×-1
                      </div>
                    </div>

                    {/* Review Tracker Bonus */}
                    {(selectedEmployee.review_tracker_bonus || 0) > 0 && (
                      <div className="p-4 bg-slate-700/50 rounded-lg border border-green-500/30">
                        <div className="flex items-center justify-between mb-2">
                          <div>
                            <span className="font-semibold text-white">Review Tracker Bonus</span>
                            <span className="ml-2 text-xs bg-green-600 text-white px-2 py-0.5 rounded-full">+0.2 per mention</span>
                          </div>
                          <div className="text-right">
                            <span className="font-bold text-green-400 text-lg">+{formatNumber(selectedEmployee.review_tracker_bonus || 0)}</span>
                            <span className="text-slate-400 text-sm"> pts</span>
                          </div>
                        </div>
                        <div className="text-sm text-slate-300">
                          {selectedEmployee.review_mentions || selectedEmployee.rt_mentions || 0} mentions × 0.2 pts each
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Score Summary Table */}
                <div className="mb-6 p-4 bg-slate-700/50 rounded-xl border border-slate-600">
                  <h4 className="font-serif font-bold text-white mb-3">Score Summary</h4>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between py-1 border-b border-slate-600">
                      <span className="text-slate-300">Weighted POS Score (PPA+LSC+LBW+Glass)</span>
                      <span className="font-medium text-white">{formatNumber(selectedEmployee.weighted_score || 0)}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-600">
                      <span className="text-slate-300">Customer Voice Score</span>
                      <span className={`font-medium ${(selectedEmployee.cv_score || 0) >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
                        {(selectedEmployee.cv_score || 0) >= 0 ? '+' : ''}{formatNumber(selectedEmployee.cv_score || 0)}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-600">
                      <span className="text-slate-300">Metric Bonuses</span>
                      <span className="font-medium text-green-400">+{formatNumber(selectedEmployee.total_metric_bonus || 0)}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-600">
                      <span className="text-slate-300">Review Tracker Bonus</span>
                      <span className="font-medium text-green-400">+{formatNumber(selectedEmployee.review_tracker_bonus || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 font-bold text-base">
                      <span className="text-white">Final Score</span>
                      <span className="text-green-400">{formatNumber(selectedEmployee.pre_dar_score || selectedEmployee.total_score || 0)}</span>
                    </div>
                  </div>
                </div>

                {/* Customer Voice Breakdown */}
                {(selectedEmployee.cv_promoters > 0 || selectedEmployee.cv_passives > 0 || selectedEmployee.cv_detractors > 0 || selectedEmployee.nps_score > 0) && (
                  <div className="mb-6">
                    <h4 className="font-serif font-bold text-white mb-3">Customer Voice Breakdown</h4>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div className="text-center p-3 bg-cyan-900/30 rounded-lg border border-cyan-500/30">
                        <div className="text-xl font-bold text-cyan-400">{selectedEmployee.nps_score || 0}%</div>
                        <div className="text-xs text-slate-300">NPS Score</div>
                        <div className="text-xs text-cyan-400 font-medium">+{((selectedEmployee.nps_score || 0) / 10).toFixed(1)} pts</div>
                      </div>
                      <div className="text-center p-3 bg-green-900/30 rounded-lg border border-green-500/30">
                        <div className="text-xl font-bold text-green-400">{selectedEmployee.cv_promoters || 0}</div>
                        <div className="text-xs text-slate-300">Promoters</div>
                        <div className="text-xs text-green-400 font-medium">+{((selectedEmployee.cv_promoters || 0) * 0.5).toFixed(1)} pts</div>
                      </div>
                      <div className="text-center p-3 bg-slate-700/50 rounded-lg border border-slate-600">
                        <div className="text-xl font-bold text-slate-300">{selectedEmployee.cv_passives || 0}</div>
                        <div className="text-xs text-slate-400">Passives</div>
                        <div className="text-xs text-slate-400">0 pts</div>
                      </div>
                      <div className="text-center p-3 bg-red-900/30 rounded-lg border border-red-500/30">
                        <div className="text-xl font-bold text-red-400">{selectedEmployee.cv_detractors || 0}</div>
                        <div className="text-xs text-slate-300">Detractors</div>
                        <div className="text-xs text-red-400 font-medium">{(selectedEmployee.cv_detractors || 0) * -1} pts</div>
                      </div>
                    </div>
                  </div>
                )}
                
                {/* Raw Data Section */}
                <div>
                  <h4 className="font-serif font-bold text-white mb-3">Raw Input Data</h4>
                  <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">Guests</span>
                      <span className="font-medium text-white">{formatNumber(selectedEmployee.guests || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">Net Sales</span>
                      <span className="font-medium text-white">{formatCurrency(selectedEmployee.net_sales || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">LBW Total</span>
                      <span className="font-medium text-white">{formatCurrency(selectedEmployee.lbw || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">Glassware</span>
                      <span className="font-medium text-white">{formatCurrency(selectedEmployee.glassware_sales || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">LSC Count</span>
                      <span className="font-medium text-white">{formatNumber(selectedEmployee.lsc_count || 0)}</span>
                    </div>
                    <div className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
                      <span className="text-slate-300">Review Mentions</span>
                      <span className="font-medium text-white">{formatNumber(selectedEmployee.review_mentions || 0)}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Edit/Add Employee Modal */}
        {showEditModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setShowEditModal(false)}>
            <div className="bg-slate-800 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
              <div className="bg-gradient-to-r from-blue-600 to-blue-700 p-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {editingEmployee ? <Pencil className="w-6 h-6 text-white" /> : <Plus className="w-6 h-6 text-white" />}
                  <h2 className="text-xl font-serif font-bold text-white">
                    {editingEmployee ? `Edit ${editingEmployee.name}` : 'Add New Employee'}
                  </h2>
                </div>
                <button onClick={() => setShowEditModal(false)} className="text-white hover:bg-slate-800/20 rounded-full p-2">
                  <X className="w-5 h-5" />
                </button>
              </div>
              
              <div className="p-6 overflow-y-auto max-h-[70vh]">
                {/* Basic Info */}
                <div className="mb-6">
                  <h3 className="font-semibold text-slate-200 mb-3">Basic Information</h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Display Name *</label>
                      <Input
                        value={formData.name}
                        onChange={(e) => handleFormChange('name', e.target.value)}
                        placeholder="Name shown in dashboards"
                        className="w-full"
                      />
                      <p className="text-xs text-slate-500 mt-1">Shown in reports & leaderboards</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Job Title</label>
                      <select
                        value={formData.job_title}
                        onChange={(e) => handleFormChange('job_title', e.target.value)}
                        className="w-full px-3 py-2 border border-slate-600 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 bg-slate-700 text-slate-200"
                      >
                        <option value="server">Server</option>
                        <option value="bartender">Bartender</option>
                        <option value="trainer">Trainer</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Report Name (POS)</label>
                      <Input
                        value={formData.report_name}
                        onChange={(e) => handleFormChange('report_name', e.target.value)}
                        placeholder="Name in POS system"
                        className="w-full bg-slate-800"
                      />
                      <p className="text-xs text-slate-500 mt-1">Used for matching uploads</p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Aliases (Nicknames)</label>
                      <Input
                        type="text"
                        value={formData.aliases}
                        onChange={(e) => handleFormChange('aliases', e.target.value)}
                        placeholder="Trey, T.Q. (comma-separated)"
                        className="w-full"
                      />
                      <p className="text-xs text-slate-500 mt-1">Additional names for matching</p>
                    </div>
                  </div>
                </div>

                {/* Sales Data */}
                <div className="mb-6">
                  <h3 className="font-semibold text-slate-200 mb-3">Sales Data</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Guests</label>
                      <Input
                        type="number"
                        value={formData.guests}
                        onChange={(e) => handleFormChange('guests', parseFloat(e.target.value) || 0)}
                        placeholder="0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Net Sales ($)</label>
                      <Input
                        type="number"
                        value={formData.net_sales}
                        onChange={(e) => handleFormChange('net_sales', parseFloat(e.target.value) || 0)}
                        placeholder="0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">LBW ($)</label>
                      <Input
                        type="number"
                        value={formData.lbw}
                        onChange={(e) => handleFormChange('lbw', parseFloat(e.target.value) || 0)}
                        placeholder="0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">Glassware ($)</label>
                      <Input
                        type="number"
                        value={formData.glassware_sales}
                        onChange={(e) => handleFormChange('glassware_sales', parseFloat(e.target.value) || 0)}
                        placeholder="0"
                      />
                    </div>
                  </div>
                </div>

                {/* LSC Count */}
                <div className="mb-6">
                  <h3 className="font-semibold text-slate-200 mb-3">LSC (Loyalty Signups)</h3>
                  <div className="w-1/2">
                    <label className="block text-sm font-medium text-slate-300 mb-1">LSC Count</label>
                    <Input
                      type="number"
                      value={formData.lsc_count}
                      onChange={(e) => handleFormChange('lsc_count', parseInt(e.target.value) || 0)}
                      placeholder="0"
                    />
                  </div>
                </div>

                {/* Customer Voice */}
                <div className="mb-6">
                  <h3 className="font-semibold text-slate-200 mb-3">Customer Voice & Reviews</h3>
                  
                  {/* NPS Score - Full width at top */}
                  <div className="mb-4">
                    <label className="block text-sm font-medium text-cyan-400 mb-1">NPS Score % (0-100)</label>
                    <Input
                      type="number"
                      min="0"
                      max="100"
                      value={formData.nps_score}
                      onChange={(e) => handleFormChange('nps_score', Math.min(100, Math.max(0, parseFloat(e.target.value) || 0)))}
                      placeholder="0"
                      className="border-cyan-200 focus:border-cyan-500 max-w-xs"
                    />
                    <p className="text-xs text-slate-500 mt-1">NPS% ÷ 10 = points (e.g., 80% = 8 pts)</p>
                  </div>
                  
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-green-600 mb-1">CV Promoters (+0.5 pt each)</label>
                      <Input
                        type="number"
                        value={formData.cv_promoters}
                        onChange={(e) => handleFormChange('cv_promoters', parseInt(e.target.value) || 0)}
                        placeholder="0"
                        className="border-green-200 focus:border-green-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-slate-300 mb-1">CV Passives (0 pt)</label>
                      <Input
                        type="number"
                        value={formData.cv_passives}
                        onChange={(e) => handleFormChange('cv_passives', parseInt(e.target.value) || 0)}
                        placeholder="0"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-red-600 mb-1">CV Detractors (-1 pt each)</label>
                      <Input
                        type="number"
                        value={formData.cv_detractors}
                        onChange={(e) => handleFormChange('cv_detractors', parseInt(e.target.value) || 0)}
                        placeholder="0"
                        className="border-red-200 focus:border-red-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-blue-600 mb-1">RT Mentions (+0.5 pt each)</label>
                      <Input
                        type="number"
                        value={formData.review_mentions}
                        onChange={(e) => handleFormChange('review_mentions', parseInt(e.target.value) || 0)}
                        placeholder="0"
                        className="border-blue-200 focus:border-blue-500"
                      />
                    </div>
                  </div>
                </div>

                {/* Preview */}
                <div className="p-4 bg-background rounded-lg border">
                  <h4 className="font-medium text-slate-200 mb-2">CV Preview</h4>
                  <div className="text-sm text-slate-300">
                    <span>CV Points: </span>
                    <span className="font-bold">
                      {((formData.nps_score || 0) / 10 + (formData.cv_promoters * 0.5) - (formData.cv_detractors * 1)).toFixed(1)}
                    </span>
                    <span className="text-gray-400 ml-2">
                      (NPS {formData.nps_score || 0}%÷10 + {formData.cv_promoters}×0.5 - {formData.cv_detractors}×1)
                    </span>
                  </div>
                </div>
              </div>
              
              <div className="p-6 border-t bg-background flex gap-3 justify-end">
                <Button variant="outline" onClick={() => setShowEditModal(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={saveEmployee} 
                  disabled={saving}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  {saving ? (
                    <>Saving...</>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-2" />
                      {editingEmployee ? 'Update Employee' : 'Create Employee'}
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
