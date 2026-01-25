import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { Upload, Users, FileText, TrendingUp, Award, Target, Anchor, Fish, Settings, AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import StatsCard from "../components/StatsCard";
import { Button } from "../components/ui/button";
import { formatCurrency, formatNumber } from "../utils/formatters";
import ConfirmDialog from "../components/ConfirmDialog";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Dashboard() {
  const [employees, setEmployees] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  
  // V2 Upload state
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [quarterSettings, setQuarterSettings] = useState(null);
  const [validationResult, setValidationResult] = useState(null);
  const [pendingFile, setPendingFile] = useState(null);
  const [showValidation, setShowValidation] = useState(false);

  const [stats, setStats] = useState({
    totalEmployees: 0,
    avgTotalScore: 0,
    topPerformers: 0,
    recentUploads: 0
  });

  const calculateStats = useCallback(() => {
    const total = employees.length;
    const avgScore = total > 0 ? employees.reduce((sum, emp) => sum + (emp.total_score || emp.cumulative_score || 0), 0) / total : 0;
    const topPerformers = employees.filter(emp => emp.performance_tier === "Top Performer" || (emp.cumulative_score || 0) >= 85).length;
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
    fetchQuarterSettings();
  }, []);

  useEffect(() => {
    fetchQuarterSettings();
    fetchEmployeesForQuarter();
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    calculateStats();
  }, [employees, calculateStats]);

  const fetchEmployees = async () => {
    try {
      // Try V2 first
      const v2Response = await axios.get(`${API}/v2/employees`);
      if (v2Response.data.length > 0) {
        setEmployees(v2Response.data);
        return;
      }
      // Fall back to V1
      const response = await axios.get(`${API}/employees`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
    }
  };

  const fetchEmployeesForQuarter = async () => {
    try {
      const response = await axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
    }
  };

  const fetchQuarterSettings = async () => {
    try {
      const response = await axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
      setQuarterSettings(response.data);
    } catch (error) {
      if (error.response?.status === 404) {
        setQuarterSettings(null);
      }
    }
  };

  const validateFile = async (file) => {
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const response = await axios.post(`${API}/v2/upload/validate`, formData);
      setValidationResult(response.data);
      setPendingFile(file);
      setShowValidation(true);
    } catch (error) {
      toast.error("Error validating file: " + (error.response?.data?.detail || error.message));
    }
  };

  const onDrop = async (acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;

    if (!file.name.match(/\.(xlsx|xls|csv)$/)) {
      toast.error("Please upload an Excel or CSV file");
      return;
    }

    // Check if quarter settings exist
    if (!quarterSettings) {
      toast.error(`Quarter settings must be created for ${selectedQuarter} ${selectedYear} first. Go to Settings.`);
      return;
    }

    if (quarterSettings.is_locked) {
      toast.error(`${selectedQuarter} ${selectedYear} is locked. Clear existing data first to re-upload.`);
      return;
    }

    // Validate first
    setUploading(true);
    await validateFile(file);
    setUploading(false);
  };

  const confirmUpload = async () => {
    if (!pendingFile || !validationResult?.valid) return;

    setUploading(true);
    setShowValidation(false);

    const formData = new FormData();
    formData.append("file", pendingFile);

    try {
      const response = await axios.post(
        `${API}/v2/upload?year=${selectedYear}&quarter=${selectedQuarter}`,
        formData
      );

      if (response.data.success) {
        toast.success(`Successfully imported and scored ${response.data.employees_count} employees!`);
        fetchEmployeesForQuarter();
        fetchQuarterSettings();
        setValidationResult(null);
        setPendingFile(null);
      }
    } catch (error) {
      toast.error("Error uploading file: " + (error.response?.data?.detail || error.message));
    } finally {
      setUploading(false);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "text/csv": [".csv"]
    },
    multiple: false,
  });

  const clearAllEmployees = async () => {
    try {
      const response = await axios.delete(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      if (response.data.success) {
        toast.success(`Cleared ${response.data.deleted_count} employees`);
        fetchEmployeesForQuarter();
        fetchQuarterSettings();
      }
    } catch (error) {
      console.error("Error clearing employees:", error);
      toast.error("Error clearing employees");
    } finally {
      setConfirmClearOpen(false);
    }
  };

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Decorative splashes */}
      <div className="splash-red" style={{ top: '8%', right: '3%' }} />
      <div className="splash-blue" style={{ top: '20%', left: '2%' }} />
      <div className="splash-red" style={{ bottom: '15%', left: '5%', opacity: 0.4 }} />
      <div className="splash-blue" style={{ bottom: '8%', right: '8%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="flex items-center justify-center gap-5 mb-4">
            <img 
              src="https://customer-assets.emergentagent.com/job_beaba37a-d1bc-43b6-b0ee-0f4c332229d2/artifacts/shpi6789_IMG_0599.png" 
              alt="Bubba Gump Logo" 
              className="w-24 h-24 rounded-full shadow-xl border-4 border-white"
              data-testid="bubba-gump-logo"
            />
            <div className="text-left">
              <h1 className="text-4xl md:text-5xl font-serif font-black text-primary tracking-tight" data-testid="main-title">
                Performance Hub
              </h1>
              <p className="text-lg text-secondary font-medium italic" data-testid="main-subtitle">
                {selectedQuarter} {selectedYear} • Quarterly Crew Reviews
              </p>
            </div>
          </div>
        </div>

        {/* Stats Dashboard */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 md:gap-6 mb-10" data-testid="stats-dashboard">
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
            title="Top Performers"
            value={stats.topPerformers}
            color="bg-yellow-500"
            testId="top-performers-card"
            linkTo="/top-performers"
          />
          <StatsCard 
            icon={Target}
            title="New This Week"
            value={stats.recentUploads}
            color="bg-purple-500"
            testId="recent-uploads-card"
          />
        </div>

        {/* Main Actions */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-10">
          <ConfirmDialog
            open={confirmClearOpen}
            onOpenChange={setConfirmClearOpen}
            title={`Clear ${selectedQuarter} ${selectedYear} data?`}
            description="This will permanently delete all employee records for this quarter. Settings will be unlocked for re-upload."
            confirmText="Clear All"
            cancelText="Cancel"
            onConfirm={clearAllEmployees}
            variant="destructive"
          />
          
          {/* File Upload */}
          <div className="bubba-card" data-testid="upload-card">
            <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-2deg)' }} />
            
            <div className="p-6 pt-8">
              {/* Quarter Selector */}
              <div className="grid grid-cols-2 gap-3 mb-5">
                <div>
                  <label className="text-xs font-semibold text-gray-500 uppercase">Year</label>
                  <select
                    className="w-full h-9 rounded-lg border-2 border-gray-200 bg-white px-2 text-sm font-medium"
                    value={selectedYear}
                    onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                  >
                    <option value={2025}>2025</option>
                    <option value={2026}>2026</option>
                    <option value={2027}>2027</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-gray-500 uppercase">Quarter</label>
                  <select
                    className="w-full h-9 rounded-lg border-2 border-gray-200 bg-white px-2 text-sm font-medium"
                    value={selectedQuarter}
                    onChange={(e) => setSelectedQuarter(e.target.value)}
                  >
                    <option value="Q1">Q1</option>
                    <option value="Q2">Q2</option>
                    <option value="Q3">Q3</option>
                    <option value="Q4">Q4</option>
                  </select>
                </div>
              </div>

              {/* Settings Status */}
              <div className="mb-4">
                {!quarterSettings ? (
                  <div className="flex items-center gap-2 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-800 text-sm">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                    <span>No settings for {selectedQuarter} {selectedYear}.</span>
                    <Link to="/settings" className="font-semibold underline">Create Settings</Link>
                  </div>
                ) : quarterSettings.is_locked ? (
                  <div className="flex items-center justify-between p-3 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      <span>Scored: {employees.length} employees</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="text-red-600 hover:bg-red-50 font-semibold text-xs"
                      onClick={() => setConfirmClearOpen(true)}
                    >
                      Clear & Re-upload
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2 p-3 bg-blue-50 border border-blue-200 rounded-lg text-blue-800 text-sm">
                    <Settings className="w-4 h-4" />
                    <span>Ready for upload. Benchmarks: PPA ${quarterSettings.benchmark_ppa}, LBW ${quarterSettings.benchmark_lbw}</span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                    <Anchor className="w-5 h-5 text-secondary" />
                  </div>
                  <div>
                    <h2 className="text-lg font-serif font-bold text-foreground">
                      Cast Your Net
                    </h2>
                    <p className="text-xs text-gray-500">
                      Upload employee data (CSV/Excel)
                    </p>
                  </div>
                </div>
              </div>
              
              <div
                {...getRootProps()}
                className={`upload-zone ${isDragActive ? 'drag-over' : ''} ${!quarterSettings || quarterSettings.is_locked ? 'opacity-50 cursor-not-allowed' : ''}`}
                data-testid="file-upload-zone"
              >
                <input {...getInputProps()} disabled={!quarterSettings || quarterSettings.is_locked} />
                {uploading ? (
                  <div className="flex flex-col items-center py-6" data-testid="uploading-state">
                    <div className="loading-spinner mb-4"></div>
                    <p className="text-primary font-serif font-bold">Processing...</p>
                  </div>
                ) : (
                  <div className="py-6 text-center" data-testid="upload-ready-state">
                    <div className="relative mx-auto w-14 h-14 mb-3">
                      <Fish className="w-14 h-14 text-blue-200" />
                      <Upload className="w-6 h-6 text-primary absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2" />
                    </div>
                    <p className="text-base font-serif font-bold text-foreground mb-1">
                      {isDragActive ? 'Drop it!' : 'Drag & drop file'}
                    </p>
                    <p className="text-gray-500 text-xs mb-2">or click to browse</p>
                    <span className="inline-block px-3 py-1 bg-gray-100 rounded-full text-xs font-semibold text-gray-600">
                      .xlsx, .xls, .csv
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="bubba-card" data-testid="quick-actions-card">
            <div className="tape tape-red" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(2deg)' }} />
            
            <div className="p-6 pt-8">
              <div className="flex items-center gap-3 mb-6">
                <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center">
                  <FileText className="w-5 h-5 text-primary" />
                </div>
                <div>
                  <h2 className="text-lg font-serif font-bold text-foreground">
                    Quick Actions
                  </h2>
                  <p className="text-xs text-gray-500">
                    Manage your crew
                  </p>
                </div>
              </div>
              
              <div className="space-y-3">
                <Link to="/employees" className="block" data-testid="view-employees-link">
                  <button className="bubba-btn-primary w-full flex items-center justify-center gap-2">
                    <Users className="w-5 h-5" />
                    View All Crew
                  </button>
                </Link>
                
                <Link to="/reviews" className="block" data-testid="generate-reviews-link">
                  <button className="bubba-btn-secondary w-full flex items-center justify-center gap-2">
                    <FileText className="w-5 h-5" />
                    Generate Reviews
                  </button>
                </Link>

                <Link to="/settings" className="block" data-testid="settings-link">
                  <button className="w-full flex items-center justify-center gap-2 px-4 py-2 border-2 border-gray-300 text-gray-700 rounded-full font-semibold hover:bg-gray-50 transition-colors">
                    <Settings className="w-5 h-5" />
                    Quarter Settings
                  </button>
                </Link>
              </div>

              <div className="mt-5 pt-4 border-t-2 border-dashed border-gray-200" data-testid="system-info">
                <h4 className="font-serif font-bold text-foreground mb-2 flex items-center gap-2 text-sm">
                  <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                  System Status
                </h4>
                <div className="grid grid-cols-3 gap-2 text-xs">
                  <div className="text-center p-2 bg-green-50 rounded-lg">
                    <div className="font-bold text-green-600">Online</div>
                    <div className="text-gray-500">DB</div>
                  </div>
                  <div className="text-center p-2 bg-green-50 rounded-lg">
                    <div className="font-bold text-green-600">Ready</div>
                    <div className="text-gray-500">AI</div>
                  </div>
                  <div className="text-center p-2 bg-green-50 rounded-lg">
                    <div className="font-bold text-green-600">V2</div>
                    <div className="text-gray-500">Engine</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Recent Employees Preview */}
        {employees.length > 0 && (
          <div className="bubba-card" data-testid="recent-employees-card">
            <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
            
            <div className="p-6 pt-8">
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
                    <Award className="w-5 h-5 text-yellow-600" />
                  </div>
                  <h2 className="text-lg font-serif font-bold text-foreground">
                    {selectedQuarter} {selectedYear} Rankings
                  </h2>
                </div>
                <span className="text-sm text-gray-500 font-medium">
                  {employees.length} employees
                </span>
              </div>
              
              <div className="space-y-3">
                {employees.slice(0, 5).map((employee, idx) => (
                  <div 
                    key={employee.id} 
                    className="flex items-center justify-between p-4 rounded-xl border-2 border-gray-200 bg-gray-50 hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-full bg-white border-2 border-gray-200 flex items-center justify-center font-serif font-bold text-primary">
                        {employee.peer_rank || idx + 1}
                      </div>
                      <div>
                        <h3 className="font-serif font-bold text-foreground">
                          {employee.name}
                        </h3>
                        <p className="text-gray-500 text-sm">{employee.position || 'Server'}</p>
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <div className="text-xl font-serif font-bold text-primary">
                          {formatNumber(employee.total_score || employee.cumulative_score)}
                        </div>
                        <div className="text-xs text-gray-500">Total Score</div>
                      </div>
                      {employee.performance_tier && (
                        <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                          employee.performance_tier === 'Top Performer' ? 'bg-green-100 text-green-800' :
                          employee.performance_tier === 'Above Average' ? 'bg-blue-100 text-blue-800' :
                          employee.performance_tier === 'Below Average' ? 'bg-yellow-100 text-yellow-800' :
                          'bg-red-100 text-red-800'
                        }`}>
                          {employee.performance_tier}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              
              {employees.length > 5 && (
                <div className="mt-6 text-center">
                  <Link to="/employees">
                    <button className="bubba-btn-secondary">
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
          <div className="bubba-card p-10 text-center">
            <Fish className="w-20 h-20 text-blue-200 mx-auto mb-4" />
            <p className="empty-state-quote">
              No data for {selectedQuarter} {selectedYear} yet.
            </p>
            <p className="text-sm text-gray-500 mt-4">
              {quarterSettings ? "Upload a file above to get started" : "Create quarter settings first, then upload"}
            </p>
          </div>
        )}

        {/* Validation Modal */}
        {showValidation && validationResult && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[80vh] overflow-auto shadow-2xl">
              <div className="p-6 border-b border-gray-200">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-serif font-bold text-foreground flex items-center gap-2">
                    {validationResult.valid ? (
                      <><CheckCircle className="w-6 h-6 text-green-600" /> Validation Passed</>
                    ) : (
                      <><XCircle className="w-6 h-6 text-red-600" /> Validation Failed</>
                    )}
                  </h2>
                  <Button variant="ghost" onClick={() => setShowValidation(false)}>×</Button>
                </div>
              </div>
              
              <div className="p-6">
                {/* Column Mapping */}
                <div className="mb-6">
                  <h3 className="font-semibold mb-2">Column Mapping</h3>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {Object.entries(validationResult.column_validation?.mapping || {}).map(([field, col]) => (
                      <div key={field} className="flex items-center gap-2 p-2 bg-green-50 rounded">
                        <CheckCircle className="w-4 h-4 text-green-600" />
                        <span className="font-medium">{field}</span>
                        <span className="text-gray-500">← {col}</span>
                      </div>
                    ))}
                  </div>
                  {validationResult.column_validation?.missing?.length > 0 && (
                    <div className="mt-2">
                      <div className="text-red-600 font-semibold">Missing columns:</div>
                      {validationResult.column_validation.missing.map(col => (
                        <span key={col} className="inline-block px-2 py-1 bg-red-100 text-red-800 rounded mr-2 mt-1 text-sm">{col}</span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Row Validation */}
                <div className="mb-6">
                  <h3 className="font-semibold mb-2">Row Validation</h3>
                  <div className="flex gap-4 text-sm">
                    <span className="text-green-600 font-medium">✓ {validationResult.row_validation?.valid_rows || 0} valid</span>
                    <span className="text-red-600 font-medium">✗ {validationResult.row_validation?.invalid_rows || 0} invalid</span>
                  </div>
                  
                  {validationResult.row_validation?.errors?.length > 0 && (
                    <div className="mt-3 max-h-40 overflow-auto">
                      {validationResult.row_validation.errors.map((err, i) => (
                        <div key={i} className="p-2 bg-red-50 rounded mb-2 text-sm">
                          <span className="font-medium">Row {err.row}: {err.name}</span>
                          <ul className="text-red-700 ml-4">
                            {err.errors.map((e, j) => <li key={j}>• {e}</li>)}
                          </ul>
                        </div>
                      ))}
                    </div>
                  )}

                  {validationResult.row_validation?.duplicate_names?.length > 0 && (
                    <div className="mt-2 p-2 bg-yellow-50 rounded text-sm">
                      <span className="font-medium text-yellow-800">Duplicate names found: </span>
                      {validationResult.row_validation.duplicate_names.join(', ')}
                    </div>
                  )}
                </div>

                {/* Preview */}
                {validationResult.preview && (
                  <div className="mb-6">
                    <h3 className="font-semibold mb-2">Preview (first 5 rows)</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="bg-gray-100">
                            <th className="p-2 text-left">Name</th>
                            <th className="p-2 text-right">Guests</th>
                            <th className="p-2 text-right">Net Sales</th>
                            <th className="p-2 text-right">LBW</th>
                            <th className="p-2 text-right">Glass</th>
                            <th className="p-2 text-right">LSC</th>
                          </tr>
                        </thead>
                        <tbody>
                          {validationResult.preview.map((row, i) => (
                            <tr key={i} className="border-b">
                              <td className="p-2">{row.name}</td>
                              <td className="p-2 text-right">{row.guests}</td>
                              <td className="p-2 text-right">${row.net_sales?.toFixed(0)}</td>
                              <td className="p-2 text-right">${row.lbw?.toFixed(0)}</td>
                              <td className="p-2 text-right">${row.glassware_sales?.toFixed(0)}</td>
                              <td className="p-2 text-right">{row.lsc_count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>

              <div className="p-6 border-t border-gray-200 flex justify-end gap-3">
                <Button variant="outline" onClick={() => setShowValidation(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={confirmUpload} 
                  disabled={!validationResult.valid}
                  className="bubba-btn-primary"
                >
                  Import & Score {validationResult.row_validation?.valid_rows || 0} Employees
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
