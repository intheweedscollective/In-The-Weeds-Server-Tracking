import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Upload, Users, FileText, TrendingUp, Award, Target } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import StatsCard from "../components/StatsCard";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { formatCurrency, formatLSCRatio, formatNumber, getPerformanceLevel } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [employees, setEmployees] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [stats, setStats] = useState({
    totalEmployees: 0,
    avgTotalScore: 0,
    topPerformers: 0,
    recentUploads: 0
  });

  useEffect(() => {
    fetchEmployees();
  }, []);

  useEffect(() => {
    calculateStats();
  }, [employees]);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API}/employees`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
    }
  };

  const calculateStats = () => {
    const total = employees.length;
    const avgScore = employees.reduce((sum, emp) => sum + (emp.cumulative_score || 0), 0) / total;
    const topPerformers = employees.filter(emp => (emp.cumulative_score || 0) >= 85).length;
    const recentUploads = employees.filter(emp => {
      const uploadDate = new Date(emp.created_at);
      const weekAgo = new Date();
      weekAgo.setDate(weekAgo.getDate() - 7);
      return uploadDate > weekAgo;
    }).length;

    setStats({
      totalEmployees: total,
      avgTotalScore: avgScore.toFixed(1),
      topPerformers,
      recentUploads
    });
  };

  const onDrop = async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    if (!file.name.match(/\.(xlsx|xls)$/)) {
      toast.error("Please upload an Excel file (.xlsx or .xls)");
      return;
    }

    setUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await axios.post(`${API}/upload-excel`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
      });

      if (response.data.success) {
        toast.success(`Successfully uploaded ${response.data.employees_count} employees!`);
        fetchEmployees();
      } else {
        toast.error("Failed to upload file");
      }
    } catch (error) {
      console.error("Upload error:", error);
      toast.error("Error uploading file: " + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"]
    },
    multiple: false,
  });

  const clearAllEmployees = async () => {
    if (!window.confirm("Are you sure you want to clear all employee data? This cannot be undone.")) {
      return;
    }

    try {
      const response = await axios.delete(`${API}/employees`);
      if (response.data.success) {
        toast.success(`Cleared ${response.data.deleted_count} employees`);
        fetchEmployees();
      }
    } catch (error) {
      console.error("Error clearing employees:", error);
      toast.error("Error clearing employees");
    }
  };

  return (
    <div className="min-h-screen bg-paper-bg">
      <Navigation />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center gap-4 mb-6">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump Logo" 
              className="w-20 h-20 rounded-full shadow-lg"
              data-testid="bubba-gump-logo"
            />
            <div>
              <h1 className="text-4xl md:text-5xl font-serif font-bold text-primary tracking-tight" data-testid="main-title">
                Employee Review System
              </h1>
              <p className="text-lg text-muted-foreground mt-2" data-testid="main-subtitle">
                Quarterly Performance Management Dashboard
              </p>
            </div>
          </div>
        </div>

        {/* Stats Dashboard */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-12" data-testid="stats-dashboard">
          <StatsCard 
            icon={Users}
            title="Total Employees"
            value={stats.totalEmployees}
            color="bg-blue-500"
            testId="total-employees-card"
          />
          <StatsCard 
            icon={TrendingUp}
            title="Avg Score"
            value={stats.avgTotalScore}
            color="bg-green-500"
            testId="avg-score-card"
          />
          <StatsCard 
            icon={Award}
            title="Top Performers"
            value={stats.topPerformers}
            color="bg-yellow-500"
            testId="top-performers-card"
          />
          <StatsCard 
            icon={Target}
            title="Recent Uploads"
            value={stats.recentUploads}
            color="bg-purple-500"
            testId="recent-uploads-card"
          />
        </div>

        {/* Main Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* File Upload */}
          <Card className="bubba-card" data-testid="upload-card">
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl font-serif text-primary">
                <Upload className="w-7 h-7" />
                Upload Employee Data
              </CardTitle>
              <CardDescription className="text-base">
                Upload an Excel spreadsheet with employee performance data
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div
                {...getRootProps()}
                className={`upload-zone p-8 text-center cursor-pointer transition-all duration-300 ${
                  isDragActive ? 'drag-over' : ''
                }`}
                data-testid="file-upload-zone"
              >
                <input {...getInputProps()} />
                {uploading ? (
                  <div className="flex flex-col items-center" data-testid="uploading-state">
                    <div className="loading-spinner mb-4"></div>
                    <p className="text-primary font-medium">Processing your file...</p>
                  </div>
                ) : (
                  <div data-testid="upload-ready-state">
                    <Upload className="w-12 h-12 text-primary mx-auto mb-4" />
                    <p className="text-lg font-medium text-primary mb-2">
                      {isDragActive ? 'Drop the Excel file here' : 'Drag & drop an Excel file here'}
                    </p>
                    <p className="text-muted-foreground mb-4">or click to select a file</p>
                    <p className="text-sm text-muted-foreground">
                      Supported formats: .xlsx, .xls
                    </p>
                  </div>
                )}
              </div>
              
              {employees.length > 0 && (
                <div className="mt-6 pt-6 border-t border-border">
                  <Button 
                    onClick={clearAllEmployees}
                    variant="outline" 
                    className="w-full text-destructive hover:bg-destructive hover:text-white"
                    data-testid="clear-all-employees-btn"
                  >
                    Clear All Employee Data
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Quick Actions */}
          <Card className="bubba-card" data-testid="quick-actions-card">
            <CardHeader>
              <CardTitle className="text-2xl font-serif text-primary">
                Quick Actions
              </CardTitle>
              <CardDescription className="text-base">
                Manage employees and generate reviews
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Link to="/employees" data-testid="view-employees-link">
                <Button className="bubba-btn-primary w-full h-12 text-base" size="lg">
                  <Users className="w-5 h-5 mr-3" />
                  View All Employees
                </Button>
              </Link>
              
              <Link to="/reviews" data-testid="generate-reviews-link">
                <Button className="bubba-btn-secondary w-full h-12 text-base" size="lg">
                  <FileText className="w-5 h-5 mr-3" />
                  Generate Reviews
                </Button>
              </Link>

              <div className="pt-4 border-t border-border" data-testid="system-info">
                <h4 className="font-semibold text-primary mb-2">System Status</h4>
                <div className="space-y-2 text-sm text-muted-foreground">
                  <div className="flex justify-between">
                    <span>Database:</span>
                    <span className="text-green-600 font-medium">Connected</span>
                  </div>
                  <div className="flex justify-between">
                    <span>AI Service:</span>
                    <span className="text-green-600 font-medium">Ready</span>
                  </div>
                  <div className="flex justify-between">
                    <span>PDF Generation:</span>
                    <span className="text-green-600 font-medium">Available</span>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Recent Employees Preview */}
        {employees.length > 0 && (
          <Card className="bubba-card" data-testid="recent-employees-card">
            <CardHeader>
              <CardTitle className="text-xl font-serif text-primary">
                Recently Added Employees
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="overflow-x-auto">
                <table className="w-full" data-testid="recent-employees-table">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-4 font-semibold text-primary">Name</th>
                      <th className="text-left py-3 px-4 font-semibold text-primary">Position</th>
                      <th className="text-center py-3 px-4 font-semibold text-primary">Cumulative Score</th>
                      <th className="text-center py-3 px-4 font-semibold text-primary">Performance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.slice(0, 5).map((employee) => {
                      const score = employee.cumulative_score || 0;
                      let performanceClass = 'performance-below';
                      let performanceText = 'Below Expectations';
                      
                      if (score >= 90) {
                        performanceClass = 'performance-excellent';
                        performanceText = 'Excellent';
                      } else if (score >= 80) {
                        performanceClass = 'performance-above-average';
                        performanceText = 'Above Average';
                      } else if (score >= 70) {
                        performanceClass = 'performance-satisfactory';
                        performanceText = 'Satisfactory';
                      } else if (score >= 60) {
                        performanceClass = 'performance-needs-improvement';
                        performanceText = 'Needs Improvement';
                      }

                      return (
                        <tr key={employee.id} className="border-b border-border hover:bg-muted/50" data-testid={`employee-row-${employee.id}`}>
                          <td className="py-3 px-4 font-medium" data-testid={`employee-name-${employee.id}`}>{employee.name}</td>
                          <td className="py-3 px-4 text-muted-foreground" data-testid={`employee-position-${employee.id}`}>{employee.position}</td>
                          <td className="py-3 px-4 text-center font-bold text-primary" data-testid={`employee-score-${employee.id}`}>
                            {score.toFixed(1)}
                          </td>
                          <td className="py-3 px-4 text-center" data-testid={`employee-performance-${employee.id}`}>
                            <span className={`performance-badge ${performanceClass}`}>
                              {performanceText}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              
              {employees.length > 5 && (
                <div className="mt-6 text-center">
                  <Link to="/employees">
                    <Button variant="outline" className="bubba-btn-secondary" data-testid="view-all-employees-btn">
                      View All {employees.length} Employees
                    </Button>
                  </Link>
                </div>
              )}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}