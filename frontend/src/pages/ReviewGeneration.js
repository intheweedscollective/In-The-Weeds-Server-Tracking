import { useState, useEffect } from "react";
import { FileText, Download, Clock, User, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Badge } from "../components/ui/badge";
import { formatCurrency, formatLSCRatio, formatNumber, getPerformanceLevel, getBenchmarkStatus, KPI_DEFINITIONS } from "../utils/formatters";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function ReviewGeneration() {
  const [employees, setEmployees] = useState([]);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState({});
  const [selectedQuarter, setSelectedQuarter] = useState("Q4");
  const [selectedYear, setSelectedYear] = useState("2024");

  useEffect(() => {
    fetchEmployees();
    fetchReviews();
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

  const fetchReviews = async () => {
    try {
      const response = await axios.get(`${API}/reviews`);
      setReviews(response.data);
    } catch (error) {
      console.error("Error fetching reviews:", error);
    }
  };

  const generateReview = async (employeeId) => {
    setGenerating(prev => ({ ...prev, [employeeId]: true }));
    
    try {
      toast.loading("Generating review with AI...", {
        id: `review-${employeeId}`,
        duration: 30000
      });
      
      const response = await axios.post(`${API}/employees/${employeeId}/generate-review`, {
        quarter: selectedQuarter,
        year: parseInt(selectedYear)
      }, {
        timeout: 60000 // 60 second timeout
      });

      toast.dismiss(`review-${employeeId}`);

      if (response.data.success) {
        toast.success("Review generated successfully!", {
          description: "Processing PDF download...",
          duration: 2000
        });
        
        // Download PDF
        if (response.data.pdf_base64) {
          const employee = employees.find(emp => emp.id === employeeId);
          const filename = `${employee?.name?.replace(/[^a-zA-Z0-9]/g, '_') || 'Employee'}_${selectedQuarter}_${selectedYear}_Review.pdf`;
          downloadPDF(response.data.pdf_base64, filename);
        } else {
          toast.warning("Review generated but PDF creation failed");
        }
        
        fetchReviews();
      } else {
        toast.error(response.data.message || "Failed to generate review");
      }
    } catch (error) {
      toast.dismiss(`review-${employeeId}`);
      console.error("Error generating review:", error);
      
      if (error.code === 'ECONNABORTED') {
        toast.error("Review generation timed out. Please try again.");
      } else if (error.response?.status === 500) {
        toast.error("Server error. Please check your API key and try again.");
      } else {
        toast.error("Error generating review: " + (error.response?.data?.detail || error.message));
      }
    } finally {
      setGenerating(prev => ({ ...prev, [employeeId]: false }));
    }
  };

  const downloadPDF = (base64Data, filename) => {
    try {
      // Create blob from base64 data
      const binaryString = atob(base64Data);
      const bytes = new Uint8Array(binaryString.length);
      for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      const blob = new Blob([bytes], { type: 'application/pdf' });
      
      // Check if we're on mobile
      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      
      if (isMobile) {
        // For mobile devices, open PDF in new window/tab
        const url = URL.createObjectURL(blob);
        const newWindow = window.open(url, '_blank');
        if (!newWindow) {
          // If popup blocked, show message with URL
          toast.success("Review generated! PDF will download shortly.", {
            description: "If download doesn't start, check your downloads folder.",
            duration: 5000
          });
          // Fallback: still try the download link method
          const link = document.createElement('a');
          link.href = url;
          link.download = filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }
        
        // Clean up URL after a delay
        setTimeout(() => URL.revokeObjectURL(url), 10000);
      } else {
        // Desktop: use standard download method
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
      
      toast.success("Review PDF generated successfully!", {
        description: `${filename} ready for download`,
        duration: 3000
      });
      
    } catch (error) {
      console.error('PDF download error:', error);
      toast.error("PDF generated but download failed. Please try again.");
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
            Review Generation
          </h1>
          <p className="text-muted-foreground" data-testid="page-subtitle">
            Generate AI-powered quarterly performance reviews
          </p>
        </div>

        {/* Review Settings */}
        <Card className="bubba-card mb-8" data-testid="review-settings-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5" />
              Review Settings
            </CardTitle>
            <CardDescription>
              Configure the review period and generate branded PDF reports
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-2">
                <label className="text-sm font-medium">Quarter</label>
                <Select value={selectedQuarter} onValueChange={setSelectedQuarter}>
                  <SelectTrigger data-testid="quarter-select">
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
                  <SelectTrigger data-testid="year-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="2024">2024</SelectItem>
                    <SelectItem value="2025">2025</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            
            <div className="mt-6 p-4 bg-muted/30 rounded-lg">
              <h4 className="font-semibold text-primary mb-2">Review Features</h4>
              <ul className="text-sm text-muted-foreground space-y-1">
                <li>• AI-powered content generation using GPT-5.2</li>
                <li>• Human-like, HR-defensible review language</li>
                <li>• Focus on 6 key KPIs: Per Person Average, Glassware $ Per Guest, Per Person Liquor Beer Wine, Landry's Select Card Ratio, Metric Bonus Points, Cumulative Score</li>
                <li>• Professional PDF with Bubba Gump branding</li>
                <li>• Marketing-style document formatting</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* Line Graph Upload Section */}\n        <Card className=\"bubba-card mb-8\" data-testid=\"line-graph-upload-card\">\n          <CardHeader>\n            <CardTitle className=\"flex items-center gap-2\">\n              <FileText className=\"w-5 h-5\" />\n              Quarterly Performance Graph\n            </CardTitle>\n            <CardDescription>\n              Upload quarterly line graph to include as second page in all reviews\n            </CardDescription>\n          </CardHeader>\n          <CardContent>\n            <LineGraphUpload \n              quarter={selectedQuarter}\n              year={parseInt(selectedYear)}\n              onUploadSuccess={() => {\n                toast.success(\"Line graph uploaded successfully!\");\n                // Refresh any necessary data\n              }}\n            />\n          </CardContent>\n        </Card>\n\n        {/* Employee List */}
        {employees.length === 0 ? (
          <Card className="bubba-card" data-testid="no-employees">
            <CardContent className="text-center py-12">
              <User className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-semibold mb-2">No employees available</h3>
              <p className="text-muted-foreground mb-6">
                Upload employee data from the dashboard to start generating reviews
              </p>
              <Button asChild className="bubba-btn-primary">
                <a href="/" data-testid="go-to-dashboard-btn">Go to Dashboard</a>
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4" data-testid="employee-review-list">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-serif font-semibold text-primary">
                Employee Reviews for {selectedQuarter} {selectedYear}
              </h2>
              <Badge variant="outline" className="text-sm">
                {employees.length} employees
              </Badge>
            </div>
            
            {employees.map((employee) => {
              const hasReview = hasRecentReview(employee.id);
              const review = getEmployeeReview(employee.id);
              const isGenerating = generating[employee.id];
              
              return (
                <Card key={employee.id} className="bubba-card" data-testid={`employee-review-card-${employee.id}`}>
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div>
                          <h3 className="text-lg font-serif font-semibold text-primary" data-testid={`employee-name-${employee.id}`}>
                            {employee.name}
                          </h3>
                          <p className="text-muted-foreground" data-testid={`employee-position-${employee.id}`}>
                            {employee.position}
                          </p>
                        </div>
                        
                        {/* KPI Summary - All 6 Metrics */}
                        <div className="hidden md:flex gap-4 ml-8">
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-primary">
                              {formatNumber(employee.cumulative_score)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              Final Grade
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-secondary">
                              {formatCurrency(employee.ppa)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              PPA
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-accent-foreground">
                              {formatCurrency(employee.gpg)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              GPG
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-wood-texture">
                              {formatCurrency(employee.pplbw)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              PPLBW
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-muted-foreground">
                              {formatLSCRatio(employee.lsc_ratio)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              LSC
                            </div>
                          </div>
                          <div className="text-center">
                            <div className="text-sm font-serif font-bold text-brand-yellow">
                              {formatNumber(employee.metric_bonus_points)}
                            </div>
                            <div className="text-xs text-muted-foreground uppercase">
                              Bonus
                            </div>
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        {hasReview && (
                          <div className="flex items-center gap-2 text-green-600">
                            <Clock className="w-4 h-4" />
                            <span className="text-sm font-medium">
                              Generated {new Date(review.created_at).toLocaleDateString()}
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
                              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                              Generating...
                            </div>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Download className="w-4 h-4" />
                              {hasReview ? "Regenerate Review" : "Generate Review"}
                            </div>
                          )}
                        </Button>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}

        {/* Recent Reviews */}
        {reviews.length > 0 && (
          <Card className="bubba-card mt-12" data-testid="recent-reviews-card">
            <CardHeader>
              <CardTitle className="text-xl font-serif text-primary">
                Recent Reviews
              </CardTitle>
              <CardDescription>
                Latest generated performance reviews
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {reviews.slice(0, 10).map((review) => (
                  <div 
                    key={review.id} 
                    className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-muted/30 transition-colors"
                    data-testid={`recent-review-${review.id}`}
                  >
                    <div>
                      <h4 className="font-medium text-primary">{review.employee_name}</h4>
                      <p className="text-sm text-muted-foreground">
                        {review.quarter} {review.year} • Generated {new Date(review.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    <Badge variant="outline">
                      {review.quarter} {review.year}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}