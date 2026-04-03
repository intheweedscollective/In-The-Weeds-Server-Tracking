import { useState, useEffect, useCallback } from "react";
import { useLocation } from "react-router-dom";
import { Users, Search, Filter, Calendar, Plus, CheckSquare, XSquare, FileText } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import ConfirmDialog from "../components/ConfirmDialog";
import { EmployeeDetailsModal } from "../components/EmployeeDetailsModal";
import { EmployeeEditModal } from "../components/EmployeeEditModal";
import { EmployeeCard } from "../components/EmployeeCard";

// Default values for new employee form
const emptyEmployee = {
  name: "",
  display_name: "",
  report_name: "",
  job_title: "server",
  aliases: "",
  guests: 0,
  net_sales: 0,
  ppa: 0,
  liquor_sales: 0,
  beer_sales: 0,
  wine_sales: 0,
  lbw: 0,
  glassware_sales: 0,
  loyalty_sales: 0,
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
  
  const location = useLocation();

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      // Fetch both snapshot employees and QR data in parallel
      const [snapshotResponse, qrResponse] = await Promise.all([
        api.get(`/v2/snapshot-workflow/current-rankings?year=${selectedYear}&quarter=${selectedQuarter}`),
        api.get('/qr/employees').catch(() => ({ data: [] })) // QR data is optional
      ]);
      
      const snapshotEmployees = snapshotResponse.data?.employees || [];
      const qrEmployees = qrResponse.data || [];
      
      // Create a map of QR data by employee name (case-insensitive)
      const qrDataMap = {};
      qrEmployees.forEach(qr => {
        const nameLower = (qr.name || '').toLowerCase().trim();
        qrDataMap[nameLower] = {
          yelp_clicks: qr.yelp_clicks || 0,
          google_clicks: qr.google_clicks || 0
        };
      });
      
      const transformedEmployees = snapshotEmployees.map(emp => {
        // Match QR data by name (try full name, then first name)
        const empNameLower = (emp.name || '').toLowerCase().trim();
        const empFirstNameLower = empNameLower.split(' ')[0];
        const qrData = qrDataMap[empNameLower] || qrDataMap[empFirstNameLower] || { yelp_clicks: 0, google_clicks: 0 };
        
        return {
          id: emp.id || emp.name,
          name: emp.name,
          display_name: emp.display_name || emp.name,
          report_name: emp.report_name || "",
          job_title: emp.job_title || "Server",
          tier_label: emp.tier_label || "Server",
          guests: emp.guest_count || emp.guests || 0,
          guest_count: emp.guest_count || emp.guests || 0,
          net_sales: emp.net_sales || 0,
          ppa: emp.ppa || 0,
          liquor_sales: emp.liquor_sales || 0,
          beer_sales: emp.beer_sales || 0,
          wine_sales: emp.wine_sales || 0,
          lbw: emp.lbw || 0,
          glassware_sales: emp.bar_glassware_sales || emp.glassware_sales || 0,
          loyalty_sales: emp.loyalty_sales || 0,
          lsc_count: emp.lsc_count || 0,
          lbw_per_guest: emp.lbw_per_guest || 0,
          glassware_per_guest: emp.glassware_per_guest || 0,
          guests_per_lsc: emp.guests_per_lsc || 0,
          nps_score: emp.nps_score || 0,
          cv_promoters: emp.cv_promoters || 0,
          cv_passives: emp.cv_passives || 0,
          cv_detractors: emp.cv_detractors || 0,
          cv_score: emp.cv_score || 0,
          review_mentions: emp.rt_mentions || emp.review_mentions || 0,
          review_tracker_bonus: emp.review_tracker_bonus || 0,
          total_score: emp.total_score || 0,
          pre_dar_score: emp.total_score || emp.pre_dar_score || 0,
          weighted_score: emp.weighted_score || 0,
          total_metric_bonus: emp.total_metric_bonus || 0,
          score_ppa: emp.score_ppa || 0,
          score_lbw: emp.score_lbw || 0,
          score_glass: emp.score_glass || 0,
          score_lsc: emp.score_lsc || 0,
          aliases: emp.aliases || [],
          peer_rank: emp.peer_rank,
          performance_tier: emp.performance_tier,
          quarter: selectedQuarter,
          year: selectedYear,
          // QR scan data
          yelp_clicks: qrData.yelp_clicks,
          google_clicks: qrData.google_clicks,
          _source: "snapshot"
        };
      });
      
      setEmployees(transformedEmployees);
    } catch (error) {
      console.error("Error loading from snapshot, falling back to employees_v2:", error);
      try {
        const response = await api.get(`/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
        setEmployees(response.data);
      } catch (fallbackError) {
        toast.error("Error loading employees");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  useEffect(() => {
    fetchEmployees();
    const handleFocus = () => fetchEmployees();
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [location.key, fetchEmployees]);

  // Delete single employee
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

  const selectAll = () => setSelectedIds(new Set(filteredEmployees.map(emp => emp.id)));
  const deselectAll = () => setSelectedIds(new Set());

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

  // Modal handlers
  const openNewEmployeeModal = () => {
    setEditingEmployee(null);
    setFormData({ ...emptyEmployee });
    setShowEditModal(true);
  };

  const openEditModal = (employee) => {
    setEditingEmployee(employee);
    const originalRt = employee.review_mentions || employee.rt_mentions || 0;
    setFormData({
      name: employee.name || "",
      display_name: employee.display_name || employee.name || "",
      report_name: employee.report_name || "",
      job_title: employee.job_title || "server",
      aliases: (employee.aliases || []).join(", "),
      guests: employee.guests || employee.guest_count || 0,
      net_sales: employee.net_sales || 0,
      ppa: employee.ppa || 0,
      liquor_sales: employee.liquor_sales || 0,
      beer_sales: employee.beer_sales || 0,
      wine_sales: employee.wine_sales || 0,
      lbw: employee.lbw || 0,
      glassware_sales: employee.glassware_sales || employee.bar_glassware_sales || 0,
      loyalty_sales: employee.loyalty_sales || 0,
      lsc_count: employee.lsc_count || 0,
      nps_score: employee.nps_score || 0,
      cv_promoters: employee.cv_promoters || 0,
      cv_passives: employee.cv_passives || 0,
      cv_detractors: employee.cv_detractors || 0,
      review_mentions: originalRt,
      _original_rt: originalRt
    });
    setShowEditModal(true);
  };

  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const saveEmployee = async () => {
    if (!formData.name.trim()) {
      toast.error("Display name is required");
      return;
    }
    
    const aliasesArray = formData.aliases 
      ? formData.aliases.split(",").map(a => a.trim()).filter(a => a)
      : [];
    
    const reportName = formData.report_name?.trim();
    if (reportName && !aliasesArray.includes(reportName)) {
      aliasesArray.push(reportName);
    }
    
    const dataToSave = {
      name: formData.name,
      display_name: formData.name,
      report_name: formData.report_name,
      job_title: formData.job_title,
      aliases: aliasesArray,
      guests: formData.guests,
      guest_count: formData.guests,
      net_sales: formData.net_sales,
      ppa: formData.ppa,
      liquor_sales: formData.liquor_sales,
      beer_sales: formData.beer_sales,
      wine_sales: formData.wine_sales,
      lbw: formData.lbw,
      glassware_sales: formData.glassware_sales,
      bar_glassware_sales: formData.glassware_sales,
      loyalty_sales: formData.loyalty_sales,
      lsc_count: formData.lsc_count,
      nps_score: formData.nps_score,
      cv_promoters: formData.cv_promoters,
      cv_passives: formData.cv_passives,
      cv_detractors: formData.cv_detractors,
      rt_mentions: formData.review_mentions,
      review_mentions: formData.review_mentions
    };
    
    setSaving(true);
    try {
      if (editingEmployee) {
        await api.put(`/v2/snapshot-workflow/employees/${editingEmployee.id}`, dataToSave);
        toast.success(`Updated ${formData.name}`);
      } else {
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

  // Performance level helper (for filtering)
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
    if (!score) return { text: "Not Assessed", class: "performance-below" };
    if (score >= 90) return { text: "Excellent", class: "performance-excellent" };
    if (score >= 80) return { text: "Above Average", class: "performance-above-average" };
    if (score >= 70) return { text: "Satisfactory", class: "performance-satisfactory" };
    if (score >= 60) return { text: "Needs Improvement", class: "performance-needs-improvement" };
    return { text: "Below Expectations", class: "performance-below" };
  };

  // Filter and sort employees
  const filteredEmployees = employees
    .filter(employee => {
      const matchesSearch = employee.name.toLowerCase().includes(searchTerm.toLowerCase());
      const performance = getPerformanceLevelLocal(employee.performance_tier, employee.total_score || employee.cumulative_score);
      const matchesPerformance = performanceFilter === "all" || 
                                performance.text.toLowerCase().includes(performanceFilter.toLowerCase());
      return matchesSearch && matchesPerformance;
    })
    .sort((a, b) => (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase()));

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
      
      {/* Delete Confirm Dialogs */}
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

        {/* Bulk Action Bar */}
        {selectMode && (
          <BulkActionBar
            selectedCount={selectedIds.size}
            totalCount={filteredEmployees.length}
            onSelectAll={selectAll}
            onDeselectAll={deselectAll}
            onBulkDelete={() => setConfirmBulkDeleteOpen(true)}
          />
        )}

        {/* Filters */}
        <FiltersCard
          selectedYear={selectedYear}
          setSelectedYear={setSelectedYear}
          selectedQuarter={selectedQuarter}
          setSelectedQuarter={setSelectedQuarter}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          performanceFilter={performanceFilter}
          setPerformanceFilter={setPerformanceFilter}
        />

        {/* Results Summary */}
        <div className="mb-4" data-testid="results-summary">
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
            {filteredEmployees.map((employee) => (
              <EmployeeCard
                key={employee.id}
                employee={employee}
                selectMode={selectMode}
                isSelected={selectedIds.has(employee.id)}
                onToggleSelection={() => toggleEmployeeSelection(employee.id)}
                onEdit={() => openEditModal(employee)}
                onViewDetails={() => {
                  setSelectedEmployee(employee);
                  setShowDetails(true);
                }}
                onDelete={() => {
                  setEmployeeToDelete(employee.id);
                  setConfirmDeleteOpen(true);
                }}
              />
            ))}
          </div>
        )}

        {/* Employee Details Modal */}
        {showDetails && selectedEmployee && (
          <EmployeeDetailsModal
            employee={selectedEmployee}
            totalEmployees={employees.length}
            onClose={() => setShowDetails(false)}
          />
        )}

        {/* Edit/Add Employee Modal */}
        <EmployeeEditModal
          isOpen={showEditModal}
          editingEmployee={editingEmployee}
          formData={formData}
          saving={saving}
          onFormChange={handleFormChange}
          onSave={saveEmployee}
          onClose={() => setShowEditModal(false)}
        />
      </div>
    </div>
  );
}

// Bulk action bar component
const BulkActionBar = ({ selectedCount, totalCount, onSelectAll, onDeselectAll, onBulkDelete }) => (
  <div className="bubba-card mb-4 bg-blue-900/30 border-blue-500/30" data-testid="bulk-action-bar">
    <div className="p-4 flex items-center justify-between flex-wrap gap-3">
      <div className="flex items-center gap-4">
        <span className="text-slate-200 font-medium">
          {selectedCount} of {totalCount} selected
        </span>
        <div className="flex gap-2">
          <Button onClick={onSelectAll} variant="outline" size="sm" className="border-slate-500 text-slate-200 hover:bg-slate-700" data-testid="select-all-btn">
            Select All
          </Button>
          <Button onClick={onDeselectAll} variant="outline" size="sm" className="border-slate-500 text-slate-200 hover:bg-slate-700" data-testid="deselect-all-btn">
            Deselect All
          </Button>
        </div>
      </div>
      <Button onClick={onBulkDelete} disabled={selectedCount === 0} variant="destructive" className="bg-red-600 hover:bg-red-700" data-testid="bulk-delete-btn">
        Delete Selected ({selectedCount})
      </Button>
    </div>
  </div>
);

// Filters card component
const FiltersCard = ({ selectedYear, setSelectedYear, selectedQuarter, setSelectedQuarter, searchTerm, setSearchTerm, performanceFilter, setPerformanceFilter }) => (
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
            <span className="text-sm text-slate-400">{selectedQuarter} {selectedYear}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
);
