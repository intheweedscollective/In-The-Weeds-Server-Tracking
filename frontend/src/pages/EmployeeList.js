import { useState, useEffect } from "react";
import { Trash2, Eye, FileText, Search, Filter } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";

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

  const deleteEmployee = async (employeeId) => {
    if (!window.confirm("Are you sure you want to delete this employee?")) {
      return;
    }

    try {
      await axios.delete(`${API}/employees/${employeeId}`);
      toast.success("Employee deleted successfully");
      fetchEmployees();
    } catch (error) {
      console.error("Error deleting employee:", error);
      toast.error("Error deleting employee");
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
      <div className="min-h-screen bg-paper-bg">
        <Navigation />
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper-bg">
      <Navigation />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-serif font-bold text-primary mb-2" data-testid="page-title">
            Employee Management
          </h1>
          <p className="text-muted-foreground" data-testid="page-subtitle">
            View and manage all employee performance data
          </p>
        </div>

        {/* Filters */}
        <Card className="bubba-card mb-8" data-testid="filters-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Filter className="w-5 h-5" />
              Filters & Search
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Search</label>
                <div className="relative">
                  <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Search by name or position..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-9"
                    data-testid="search-input"
                  />
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium">Position</label>
                <Select value={positionFilter} onValueChange={setPositionFilter}>
                  <SelectTrigger data-testid="position-filter">
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
                  <SelectTrigger data-testid="performance-filter">
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
          </CardContent>
        </Card>

        {/* Results Summary */}
        <div className="mb-6" data-testid="results-summary">
          <p className="text-muted-foreground">
            Showing {filteredEmployees.length} of {employees.length} employees
          </p>
        </div>

        {/* Employee Grid */}
        {filteredEmployees.length === 0 ? (
          <Card className="bubba-card" data-testid="no-results">
            <CardContent className="text-center py-12">
              <FileText className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No employees found</h3>
              <p className="text-muted-foreground">
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
                    {/* KPI Grid */}
                    <div className="grid grid-cols-2 gap-4 mb-6">
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-primary" data-testid={`employee-cumulative-score-${employee.id}`}>
                          {employee.cumulative_score?.toFixed(1) || 'N/A'}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          Cumulative Score
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-secondary" data-testid={`employee-ppa-${employee.id}`}>
                          {employee.ppa?.toFixed(1) || 'N/A'}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          PPA
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-xl font-serif font-bold text-accent-foreground" data-testid={`employee-gpg-${employee.id}`}>
                          {employee.gpg?.toFixed(1) || 'N/A'}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          GPG
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-xl font-serif font-bold text-muted-foreground" data-testid={`employee-lsc-${employee.id}`}>
                          {employee.lsc_ratio?.toFixed(2) || 'N/A'}
                        </div>
                        <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                          LSC Ratio
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
                        onClick={() => deleteEmployee(employee.id)}
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
                      {selectedEmployee.ppa?.toFixed(2) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      PPA (Per Person Average)
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-secondary mb-2">
                      {selectedEmployee.gpg?.toFixed(2) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      GPG (Gross Profit Generated)
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-accent-foreground mb-2">
                      {selectedEmployee.pplbw?.toFixed(2) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      PPLBW (People Per Labor Budget Week)
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-wood-texture mb-2">
                      {selectedEmployee.lsc_ratio?.toFixed(2) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      LSC Ratio (Labor Sales Cost)
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-muted/30 rounded-lg">
                    <div className="text-3xl font-serif font-bold text-brand-yellow mb-2">
                      {selectedEmployee.bonus_points?.toFixed(1) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      Bonus Points
                    </div>
                  </div>
                  
                  <div className="text-center p-4 bg-primary/10 rounded-lg">
                    <div className="text-4xl font-serif font-bold text-primary mb-2">
                      {selectedEmployee.total_score?.toFixed(1) || 'N/A'}
                    </div>
                    <div className="text-sm font-semibold text-muted-foreground uppercase">
                      Total Score
                    </div>
                  </div>
                </div>
                
                {/* Additional Data */}
                {Object.keys(selectedEmployee.additional_data || {}).length > 0 && (
                  <div>
                    <h4 className="font-semibold text-primary mb-4">Additional Information</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {Object.entries(selectedEmployee.additional_data || {}).map(([key, value]) => (
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