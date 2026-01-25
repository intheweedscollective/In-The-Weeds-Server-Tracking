import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { Upload, Users, FileText, TrendingUp, Award, Target, Anchor, Fish } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import StatsCard from "../components/StatsCard";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { formatCurrency, formatLSCRatio, formatNumber, getPerformanceLevel, getBenchmarkStatus, KPI_DEFINITIONS, formatOverallRank, formatRanking, getRankingHierarchy } from "../utils/formatters";

import ConfirmDialog from "../components/ConfirmDialog";
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [employees, setEmployees] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);

  const [stats, setStats] = useState({
    totalEmployees: 0,
    avgTotalScore: 0,
    topPerformers: 0,
    recentUploads: 0
  });

  const calculateStats = useCallback(() => {
    const total = employees.length;
    const avgScore = total > 0 ? employees.reduce((sum, emp) => sum + (emp.cumulative_score || 0), 0) / total : 0;
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
  }, [employees]);

  useEffect(() => {
    fetchEmployees();
  }, []);

  useEffect(() => {
    calculateStats();
  }, [employees, calculateStats]);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API}/employees`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
    }
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
    try {
      const response = await axios.delete(`${API}/employees`);
      if (response.data.success) {
        toast.success(`Cleared ${response.data.deleted_count} employees`);
        fetchEmployees();
      }
    } catch (error) {
      console.error("Error clearing employees:", error);
      toast.error("Error clearing employees");
    } finally {
      setConfirmClearOpen(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      {/* Paper texture overlay */}
      <div className="fixed inset-0 pointer-events-none paper-texture" />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header with Bubba Gump styling */}
        <div className="text-center mb-12">
          <div className="flex items-center justify-center gap-5 mb-6">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump Logo" 
              className="w-24 h-24 rounded-full shadow-xl ring-4 ring-primary/20"
              data-testid="bubba-gump-logo"
            />
            <div className="text-left">
              <h1 className="text-4xl md:text-5xl font-serif font-black text-primary tracking-tight" data-testid="main-title">
                Performance Hub
              </h1>
              <p className="text-lg text-muted-foreground mt-1 font-medium italic" data-testid="main-subtitle">
                "Life is like a box of reviews..."
              </p>
            </div>
          </div>
        </div>

        {/* Stats Dashboard - Captain's Scoreboard */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-12" data-testid="stats-dashboard">
          <StatsCard 
            icon={Users}
            title="Crew Members"
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
            linkTo="/analytics"
          />
          <StatsCard 
            icon={Award}
            title="Top Shrimpers"
            value={stats.topPerformers}
            color="bg-yellow-500"
            testId="top-performers-card"
            linkTo="/top-performers"
          />
          <StatsCard 
            icon={Target}
            title="New Catches"
            value={stats.recentUploads}
            color="bg-purple-500"
            testId="recent-uploads-card"
          />
        </div>

        {/* Main Actions - Bento Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <ConfirmDialog
            open={confirmClearOpen}
            onOpenChange={setConfirmClearOpen}
            title="Clear all crew data?"
            description="This will permanently delete all employee records. This action cannot be undone - even Forrest couldn't run from this!"
            confirmText="Clear All"
            cancelText="Cancel"
            onConfirm={clearAllEmployees}
            variant="destructive"
          />
          
          {/* File Upload - The Fishing Net */}
          <div className="bubba-card overflow-hidden" data-testid="upload-card">
            {/* Tape decoration */}
            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-16 h-6 bg-accent/80 rotate-[-2deg] shadow-sm z-10" />
            
            <div className="p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-full bg-secondary/10">
                    <Anchor className="w-6 h-6 text-secondary" />
                  </div>
                  <div>
                    <h2 className="text-xl font-serif font-bold text-foreground">
                      Cast Your Net
                    </h2>
                    <p className="text-sm text-muted-foreground">
                      Upload employee performance data
                    </p>
                  </div>
                </div>
                {employees.length > 0 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:bg-destructive/10"
                    onClick={() => setConfirmClearOpen(true)}
                    data-testid="clear-all-employees-btn"
                  >
                    Clear All
                  </Button>
                )}
              </div>
              
              <div
                {...getRootProps()}
                className={`upload-zone ${isDragActive ? 'drag-over' : ''}`}
                data-testid="file-upload-zone"
              >
                <input {...getInputProps()} />
                {uploading ? (
                  <div className="flex flex-col items-center py-8" data-testid="uploading-state">
                    <div className="loading-spinner mb-4"></div>
                    <p className="text-primary font-serif font-semibold">Hauling in your catch...</p>
                  </div>
                ) : (
                  <div className="py-8" data-testid="upload-ready-state">
                    <div className="relative mx-auto w-16 h-16 mb-4">
                      <Fish className="w-16 h-16 text-secondary/30 absolute animate-pulse" />
                      <Upload className="w-8 h-8 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                    </div>
                    <p className="text-lg font-serif font-semibold text-foreground mb-2">
                      {isDragActive ? 'Drop it like it\'s hot!' : 'Drag & drop your Excel file'}
                    </p>
                    <p className="text-muted-foreground mb-3">or click to browse</p>
                    <span className="inline-block px-3 py-1 bg-muted rounded-full text-xs font-medium text-muted-foreground">
                      .xlsx, .xls supported
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bubba-card overflow-hidden" data-testid="quick-actions-card">
            {/* Tape decoration */}
            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-16 h-6 bg-primary/80 rotate-[2deg] shadow-sm z-10" />
            
            <div className="p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 rounded-full bg-primary/10">
                  <FileText className="w-6 h-6 text-primary" />
                </div>
                <div>
                  <h2 className="text-xl font-serif font-bold text-foreground">
                    Quick Actions
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    Manage your crew and reviews
                  </p>
                </div>
              </div>
              
              <div className="space-y-3">
                <Link to="/employees" className="block" data-testid="view-employees-link">
                  <button className="bubba-btn-primary w-full flex items-center justify-center gap-2">
                    <Users className="w-5 h-5" />
                    View All Crew Members
                  </button>
                </Link>
                
                <Link to="/reviews" className="block" data-testid="generate-reviews-link">
                  <button className="bubba-btn-secondary w-full flex items-center justify-center gap-2">
                    <FileText className="w-5 h-5" />
                    Generate Reviews
                  </button>
                </Link>
              </div>

              <div className="mt-6 pt-6 border-t border-border" data-testid="system-info">
                <h4 className="font-serif font-semibold text-foreground mb-3 flex items-center gap-2">
                  <Anchor className="w-4 h-4 text-secondary" />
                  Ship Status
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">Database:</span>
                    <span className="text-green-600 dark:text-green-400 font-semibold flex items-center gap-1">
                      <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                      Connected
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">AI Service:</span>
                    <span className="text-green-600 dark:text-green-400 font-semibold flex items-center gap-1">
                      <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                      Ready
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span className="text-muted-foreground">PDF Generation:</span>
                    <span className="text-green-600 dark:text-green-400 font-semibold flex items-center gap-1">
                      <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                      Available
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Employees Preview */}
        {employees.length > 0 && (
          <div className="bubba-card overflow-hidden" data-testid="recent-employees-card">
            {/* Tape decoration */}
            <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-20 h-6 bg-accent/80 rotate-[-1deg] shadow-sm z-10" />
            
            <div className="p-6">
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 rounded-full bg-accent/20">
                  <Award className="w-6 h-6 text-accent-foreground" />
                </div>
                <h2 className="text-xl font-serif font-bold text-foreground">
                  Crew Performance Overview
                </h2>
              </div>
              
              <div className="space-y-4">
                {employees.slice(0, 3).map((employee) => {
                  const performance = getPerformanceLevel(employee.cumulative_score);

                  return (
                    <div 
                      key={employee.id} 
                      className="p-4 rounded-xl border border-border bg-muted/30 hover:bg-muted/50 transition-colors"
                      data-testid={`employee-overview-${employee.id}`}
                    >
                      <div className="flex items-start justify-between mb-4">
                        <div>
                          <h3 className="text-lg font-serif font-semibold text-foreground" data-testid={`employee-name-${employee.id}`}>
                            {employee.name}
                          </h3>
                          <p className="text-muted-foreground text-sm" data-testid={`employee-position-${employee.id}`}>
                            {employee.position}
                          </p>
                          {(employee.overall_rank || employee.ranking) && (
                            <div className="flex gap-2 mt-1">
                              {employee.overall_rank && (
                                <span className="text-xs bg-secondary/10 text-secondary px-2 py-1 rounded-full font-medium">
                                  Rank: {formatOverallRank(employee.overall_rank)}
                                </span>
                              )}
                              {employee.ranking && (
                                <span className={`text-xs px-2 py-1 rounded-full font-medium ${getRankingHierarchy(employee.ranking).bgColor} ${getRankingHierarchy(employee.ranking).color}`}>
                                  {formatRanking(employee.ranking)} - {getRankingHierarchy(employee.ranking).level}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                        <span className={`performance-badge ${performance.class}`} data-testid={`employee-performance-${employee.id}`}>
                          {performance.text}
                        </span>
                      </div>
                      
                      {/* All 6 Metrics Quick View */}
                      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
                        <div className="text-center p-2 rounded-lg bg-background/50">
                          <div className="text-base font-serif font-bold text-primary">
                            {formatCurrency(employee.ppa)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.ppa.shortName}
                          </div>
                        </div>
                        
                        <div className="text-center p-2 rounded-lg bg-background/50">
                          <div className="text-base font-serif font-bold text-secondary">
                            {formatCurrency(employee.gpg)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.gpg.shortName}
                          </div>
                        </div>
                        
                        <div className="text-center p-2 rounded-lg bg-background/50">
                          <div className="text-base font-serif font-bold text-foreground">
                            {formatCurrency(employee.pplbw)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.pplbw.shortName}
                          </div>
                        </div>
                        
                        <div className="text-center p-2 rounded-lg bg-background/50">
                          <div className="text-base font-serif font-bold text-foreground">
                            {formatLSCRatio(employee.lsc_ratio)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.lsc_ratio.shortName}
                          </div>
                        </div>
                        
                        <div className="text-center p-2 rounded-lg bg-background/50">
                          <div className="text-base font-serif font-bold text-accent-foreground">
                            {formatNumber(employee.metric_bonus_points)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.metric_bonus_points.shortName}
                          </div>
                        </div>
                        
                        <div className="text-center p-2 rounded-lg bg-primary/10">
                          <div className="text-lg font-serif font-black text-primary">
                            {formatNumber(employee.cumulative_score)}
                          </div>
                          <div className="text-xs text-muted-foreground font-semibold uppercase tracking-wider">
                            {KPI_DEFINITIONS.cumulative_score.shortName}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
              
              {employees.length > 3 && (
                <div className="mt-6 text-center">
                  <Link to="/employees">
                    <button className="bubba-btn-secondary" data-testid="view-all-employees-btn">
                      View All {employees.length} Crew Members
                    </button>
                  </Link>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Empty State */}
        {employees.length === 0 && (
          <div className="bubba-card p-12 text-center">
            <Fish className="w-16 h-16 text-muted-foreground/30 mx-auto mb-4" />
            <p className="empty-state-quote">
              Mama always said, you gotta upload some data before you can see results.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
