import { useState, useEffect } from "react";
import { Trash2, Eye, FileText, Search, Filter, Users, Anchor } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { formatCurrency, formatLSCRatio, formatNumber, getPerformanceLevel, getBenchmarkStatus, KPI_DEFINITIONS } from "../utils/formatters";

import ConfirmDialog from "../components/ConfirmDialog";
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function EmployeeList() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [performanceFilter, setPerformanceFilter] = useState("all");
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [showDetails, setShowDetails] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [employeeToDelete, setEmployeeToDelete] = useState(null);


  useEffect(() => {
    fetchEmployees();
  }, []);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API}/employees`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
      toast.error("Error loading employees");
    } finally {
      setLoading(false);
    }
  };

  const deleteEmployee = async () => {
    if (!employeeToDelete) return;

    try {
      await axios.delete(`${API}/employees/${employeeToDelete}`);
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

  const getPerformanceLevel = (score) => {
    if (!score) return { text: "Not Assessed", class: "performance-below" };
    
    if (score >= 90) return { text: "Excellent", class: "performance-excellent" };
    if (score >= 80) return { text: "Above Average", class: "performance-above-average" };
    if (score >= 70) return { text: "Satisfactory", class: "performance-satisfactory" };
    if (score >= 60) return { text: "Needs Improvement", class: "performance-needs-improvement" };
    return { text: "Below Expectations", class: "performance-below" };
  };

  // Filter employees
  const filteredEmployees = employees.filter(employee => {
    const matchesSearch = employee.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         employee.position.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesPosition = positionFilter === "all" || 
                           employee.position.toLowerCase().includes(positionFilter.toLowerCase());
    
    const performance = getPerformanceLevel(employee.cumulative_score);
    const matchesPerformance = performanceFilter === "all" || 
                              performance.text.toLowerCase().includes(performanceFilter.toLowerCase());
    
    return matchesSearch && matchesPosition && matchesPerformance;
  });

  // Get unique positions for filter
  const positions = [...new Set(employees.map(emp => emp.position))];

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
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Search</label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-gray-400" />
                  <Input
                    placeholder="Search by name or position..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9 border-2 border-gray-200 rounded-lg focus:border-secondary"
                    data-testid="search-input"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Position</label>
                <Select value={positionFilter} onValueChange={setPositionFilter}>
                  <SelectTrigger data-testid="position-filter" className="border-2 border-gray-200">
                    <SelectValue placeholder="All Positions" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Positions</SelectItem>
                    {positions.map(position => (
                      <SelectItem key={position} value={position}>{position}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Performance</label>
                <Select value={performanceFilter} onValueChange={setPerformanceFilter}>
                  <SelectTrigger data-testid="performance-filter" className="border-2 border-gray-200">
                    <SelectValue placeholder="All Performance Levels" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Performance Levels</SelectItem>
                    <SelectItem value="excellent">Excellent</SelectItem>
                    <SelectItem value="above average">Above Average</SelectItem>
                    <SelectItem value="satisfactory">Satisfactory</SelectItem>
                    <SelectItem value="needs improvement">Needs Improvement</SelectItem>
                    <SelectItem value="below expectations">Below Expectations</SelectItem>
                  </SelectContent>
                </Select>
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
                ? "Upload an Excel file to get started" 
                : "Try adjusting your search or filters"}
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6" data-testid="employee-grid">
            {filteredEmployees.map((employee) => {
              const performance = getPerformanceLevel(employee.cumulative_score);
              
              return (
                <Card key={employee.id} className="bubba-card" data-testid={`employee-card-${employee.id}`}>
                  <CardHeader>
                    <div className="flex items-start justify-between">
                      <div>
                        <CardTitle className="text-lg font-serif text-primary" data-testid={`employee-name-${employee.id}`}>
                          {employee.name}
                        </CardTitle>
                        <CardDescription data-testid={`employee-position-${employee.id}`}>
                          {employee.position}
                        </CardDescription>
                      </div>
                      <Badge className={`performance-badge ${performance.class}`} data-testid={`employee-performance-${employee.id}`}>
                        {performance.text}
                      </Badge>
                    </div>
                  </CardHeader>
                  
                  <CardContent>
                    {/* All 6 KPI Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-primary" data-testid={`employee-cumulative-score-${employee.id}`}>
                          {formatNumber(employee.cumulative_score)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          Cumulative Score
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-lg font-serif font-bold text-secondary" data-testid={`employee-ppa-${employee.id}`}>
                          {formatCurrency(employee.ppa)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          PPA
                        </div>
                        <div className={`text-xs ${getBenchmarkStatus('ppa', employee.ppa).class}`}>
                          {getBenchmarkStatus('ppa', employee.ppa).text}
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-lg font-serif font-bold text-accent-foreground" data-testid={`employee-gpg-${employee.id}`}>
                          {formatCurrency(employee.gpg)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          GPG
                        </div>
                        <div className={`text-xs ${getBenchmarkStatus('gpg', employee.gpg).class}`}>
                          {getBenchmarkStatus('gpg', employee.gpg).text}
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-lg font-serif font-bold text-wood-texture" data-testid={`employee-pplbw-${employee.id}`}>
                          {formatCurrency(employee.pplbw)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          PPLBW
                        </div>
                        <div className={`text-xs ${getBenchmarkStatus('pplbw', employee.pplbw).class}`}>
                          {getBenchmarkStatus('pplbw', employee.pplbw).text}
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-lg font-serif font-bold text-muted-foreground" data-testid={`employee-lsc-${employee.id}`}>
                          {formatLSCRatio(employee.lsc_ratio)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          LSC Ratio
                        </div>
                        <div className={`text-xs ${getBenchmarkStatus('lsc_ratio', employee.lsc_ratio).class}`}>
                          {getBenchmarkStatus('lsc_ratio', employee.lsc_ratio).text}
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-lg font-serif font-bold text-brand-yellow" data-testid={`employee-bonus-${employee.id}`}>
                          {formatNumber(employee.metric_bonus_points)}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          Metric Bonus
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Exceeds Benchmark
                        </div>
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
                        className="flex-1"
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
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* Employee Details Modal */}
        {showDetails && selectedEmployee && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" data-testid="employee-details-modal">
            <Card className="w-full max-w-2xl max-h-[80vh] overflow-auto">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-2xl font-serif text-primary">
                      {selectedEmployee.name}
                    </CardTitle>
                    <CardDescription className="text-base">
                      {selectedEmployee.position}
                    </CardDescription>
                  </div>
                  <Button 
                    onClick={() => setShowDetails(false)}
                    variant="outline"
                    size="sm"
                    data-testid="close-modal-btn"
                  >
                    Close
                  </Button>
                </div>
              </CardHeader>
              
              <CardContent>
                {/* Detailed KPIs */}
                <div className="grid grid-cols-2 md:grid-cols-3 gap-6 mb-8">
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-primary mb-2">
                      {formatCurrency(selectedEmployee.ppa)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      PPA (Per Person Average)
                    </div>
                    <div className={`text-sm mt-1 ${getBenchmarkStatus('ppa', selectedEmployee.ppa).class}`}>
                      {getBenchmarkStatus('ppa', selectedEmployee.ppa).text}
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-secondary mb-2">
                      {formatCurrency(selectedEmployee.gpg)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      GPG (Glassware $ Per Guest)
                    </div>
                    <div className={`text-sm mt-1 ${getBenchmarkStatus('gpg', selectedEmployee.gpg).class}`}>
                      {getBenchmarkStatus('gpg', selectedEmployee.gpg).text}
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-accent-foreground mb-2">
                      {formatCurrency(selectedEmployee.pplbw)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      PPLBW (Per Person Liquor Beer Wine)
                    </div>
                    <div className={`text-sm mt-1 ${getBenchmarkStatus('pplbw', selectedEmployee.pplbw).class}`}>
                      {getBenchmarkStatus('pplbw', selectedEmployee.pplbw).text}
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-wood-texture mb-2">
                      {formatLSCRatio(selectedEmployee.lsc_ratio)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      LSC Ratio (Landry&apos;s Select Card)
                    </div>
                    <div className={`text-sm mt-1 ${getBenchmarkStatus('lsc_ratio', selectedEmployee.lsc_ratio).class}`}>
                      {getBenchmarkStatus('lsc_ratio', selectedEmployee.lsc_ratio).text}
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-brand-yellow mb-2">
                      {formatNumber(selectedEmployee.metric_bonus_points)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      Metric Bonus Points
                    </div>
                    <div className="text-sm mt-1 text-muted-foreground">
                      Exceeds Benchmark
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-primary/10 rounded-lg">
                    <div className="text-4xl font-serif font-bold text-primary mb-2">
                      {formatNumber(selectedEmployee.cumulative_score)}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      Cumulative Score
                    </div>
                    <div className={`text-sm mt-1 performance-badge ${getPerformanceLevel(selectedEmployee.cumulative_score).class}`}>
                      {getPerformanceLevel(selectedEmployee.cumulative_score).text}
                    </div>
                  </div>
                </div>
                
                {/* Additional Data */}
                {Object.keys(selectedEmployee.additional_data || {}).length > 0 && (
                  <div>
                    <h4 className="font-semibold text-primary mb-4">Additional Information</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {Object.entries(selectedEmployee.additional_data || {})
                        .filter(([key]) => key !== "metric_tiers")
                        .map(([key, value]) => (
                          <div key={key} className="flex justify-between py-2 border-b border-border">
                            <span className="capitalize font-medium">{key.replace(/[_-]/g, ' ')}</span>
                            <span className="text-muted-foreground">{value || 'N/A'}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}