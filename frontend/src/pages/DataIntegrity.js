import { useState, useEffect, useCallback } from "react";
import { ShieldCheck, AlertTriangle, CheckCircle, XCircle, RefreshCw, Trash2, Database, Users, Star, MessageSquare, UserMinus, Search, Download, Upload } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function DataIntegrity() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState({});
  const currentQ = getCurrentQuarter();
  const [quarter] = useState(currentQ.quarter);
  const [year] = useState(currentQ.year);
  
  // Employee cleanup state
  const [cleanupData, setCleanupData] = useState(null);
  const [cleanupLoading, setCleanupLoading] = useState(false);
  const [selectedForDeletion, setSelectedForDeletion] = useState(new Set());
  const [showCleanupSection, setShowCleanupSection] = useState(false);
  
  // Import state
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      // Fetch basic stats
      const [employeesRes, cvRes, rtRes] = await Promise.all([
        api.get(`/v2/employees?quarter=${quarter}&year=${year}`),
        api.get(`/v2/cv/stats?quarter=${quarter}&year=${year}`).catch(() => ({ data: {} })),
        api.get(`/v2/reviews/stats?quarter=${quarter}&year=${year}`).catch(() => ({ data: {} }))
      ]);
      
      const cvData = cvRes.data || {};
      const rtData = rtRes.data || {};
      
      setStats({
        employees: employeesRes.data?.length || 0,
        cv: {
          responses: cvData.total_surveys || cvData.total_responses || 0,
          promoters: cvData.promoter_count || 0,
          passives: cvData.passive_count || 0,
          detractors: cvData.detractor_count || 0,
          nps: cvData.avg_nps || cvData.store_nps || 0
        },
        rt: {
          mentions: rtData.total_mentions || 0,
          employees: rtData.employees_with_mentions || rtData.top_mentioned?.length || 0,
          avgPerEmployee: rtData.total_mentions && rtData.employees_with_mentions 
            ? (rtData.total_mentions / rtData.employees_with_mentions).toFixed(1) 
            : 0
        }
      });
    } catch (error) {
      console.error("Stats error:", error);
      toast.error("Failed to fetch data stats");
    }
  }, [quarter, year]);

  // Clear all CV data
  const clearCVData = async () => {
    if (!window.confirm("Delete ALL Customer Voice data? This cannot be undone.")) return;
    
    setRunning(prev => ({ ...prev, clearCV: true }));
    try {
      await api.delete(`/v2/admin/clear-cv-data?quarter=${quarter}&year=${year}`);
      toast.success("Customer Voice data cleared");
      fetchStats();
    } catch (error) {
      toast.error("Failed to clear CV data");
    } finally {
      setRunning(prev => ({ ...prev, clearCV: false }));
    }
  };

  // Clear all RT data
  const clearRTData = async () => {
    if (!window.confirm("Reset ALL Review Tracker mention counts to 0? This cannot be undone.")) return;
    
    setRunning(prev => ({ ...prev, clearRT: true }));
    try {
      await api.delete(`/v2/admin/clear-rt-data?quarter=${quarter}&year=${year}`);
      toast.success("Review Tracker data cleared");
      fetchStats();
    } catch (error) {
      toast.error("Failed to clear RT data");
    } finally {
      setRunning(prev => ({ ...prev, clearRT: false }));
    }
  };

  // Recalculate all scores
  const recalculateScores = async () => {
    setRunning(prev => ({ ...prev, recalc: true }));
    toast.info("Recalculating all scores...");
    try {
      const response = await api.post(`/v2/audit/fix-all-discrepancies?quarter=${quarter}&year=${year}`);
      toast.success(response.data.message || "All scores recalculated!");
      fetchStats();
    } catch (error) {
      toast.error("Failed to recalculate scores");
    } finally {
      setRunning(prev => ({ ...prev, recalc: false }));
    }
  };

  // Analyze employees for cleanup
  const analyzeEmployees = async () => {
    setCleanupLoading(true);
    setShowCleanupSection(true);
    try {
      const response = await api.get('/v2/employees/cleanup/analyze');
      setCleanupData(response.data);
      // Pre-select all duplicates and test data for deletion
      const toDelete = new Set([
        ...response.data.potential_duplicates.map(e => e.id),
        ...response.data.test_data.map(e => e.id)
      ]);
      setSelectedForDeletion(toDelete);
    } catch (error) {
      toast.error("Failed to analyze employees");
    } finally {
      setCleanupLoading(false);
    }
  };

  // Toggle selection for deletion
  const toggleSelection = (id) => {
    setSelectedForDeletion(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  // Delete selected employees
  const deleteSelected = async () => {
    if (selectedForDeletion.size === 0) {
      toast.error("No employees selected for deletion");
      return;
    }
    
    if (!window.confirm(`Delete ${selectedForDeletion.size} employee(s)? This cannot be undone.`)) {
      return;
    }
    
    setRunning(prev => ({ ...prev, deleteEmployees: true }));
    try {
      const response = await api.post('/v2/employees/cleanup/delete', {
        employee_ids: Array.from(selectedForDeletion)
      });
      
      toast.success(`Deleted ${response.data.deleted_count} employees`);
      setSelectedForDeletion(new Set());
      
      // Refresh data
      await Promise.all([fetchStats(), analyzeEmployees()]);
    } catch (error) {
      toast.error("Failed to delete employees");
    } finally {
      setRunning(prev => ({ ...prev, deleteEmployees: false }));
    }
  };

  // Export data - mobile friendly
  const exportData = async () => {
    setRunning(prev => ({ ...prev, export: true }));
    try {
      const response = await api.get(`/v2/data/export?quarter=${quarter}&year=${year}`);
      const data = response.data;
      
      // Download as JSON file - mobile friendly approach
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: 'application/json' });
      const filename = `employee_data_${quarter}_${year}_${new Date().toISOString().split('T')[0]}.json`;
      
      // Check if we can use the native share API (mobile)
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [new File([blob], filename, { type: 'application/json' })] })) {
        try {
          await navigator.share({
            files: [new File([blob], filename, { type: 'application/json' })],
            title: 'Employee Data Export',
          });
          toast.success(`Exported ${data.employee_count} employees`);
        } catch (shareError) {
          // User cancelled or share failed, fall back to download
          downloadFile(blob, filename);
          toast.success(`Exported ${data.employee_count} employees`);
        }
      } else {
        // Desktop or unsupported mobile - use download
        downloadFile(blob, filename);
        toast.success(`Exported ${data.employee_count} employees`);
      }
    } catch (error) {
      console.error("Export error:", error);
      toast.error("Failed to export data");
    } finally {
      setRunning(prev => ({ ...prev, export: false }));
    }
  };
  
  // Helper function to trigger download
  const downloadFile = (blob, filename) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.style.display = 'none';
    document.body.appendChild(a);
    
    // Use setTimeout to ensure the element is in DOM
    setTimeout(() => {
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 100);
  };

  // Import data
  const importData = async () => {
    if (!importFile) return;
    
    setImporting(true);
    try {
      const text = await importFile.text();
      const data = JSON.parse(text);
      
      const response = await api.post('/v2/data/import', data);
      
      toast.success(`Imported ${response.data.employees_imported} employees, ${response.data.qr_employees_imported} QR employees`);
      setImportFile(null);
      fetchStats();
    } catch (error) {
      toast.error("Failed to import data: " + (error.message || "Invalid file"));
    } finally {
      setImporting(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchStats();
      setLoading(false);
    };
    init();
  }, [fetchStats]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 p-3 md:p-6">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 md:p-3 bg-blue-500/20 rounded-xl shrink-0">
              <Database className="w-5 h-5 md:w-7 md:h-7 text-blue-400" />
            </div>
            <div>
              <h1 className="text-lg md:text-2xl font-bold text-white">Data Integrity</h1>
              <p className="text-xs md:text-sm text-slate-400">{quarter} {year} • Manage uploaded data</p>
            </div>
          </div>
          
          <Button
            onClick={recalculateScores}
            disabled={running.recalc}
            className="bg-blue-600 hover:bg-blue-700"
            size="sm"
          >
            {running.recalc ? (
              <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4 mr-2" />
            )}
            Recalculate All
          </Button>
        </div>

        {/* Stats Overview */}
        <div className="grid grid-cols-3 gap-2 md:gap-4 mb-6">
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-4 text-center">
            <Users className="w-5 h-5 md:w-6 md:h-6 text-blue-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-white">{stats?.employees || 0}</div>
            <div className="text-xs text-slate-400">Employees</div>
          </div>
          
          <div className="bg-slate-800/50 rounded-xl border border-orange-500/30 p-3 md:p-4 text-center">
            <Star className="w-5 h-5 md:w-6 md:h-6 text-orange-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-orange-400">{stats?.cv?.responses || 0}</div>
            <div className="text-xs text-slate-400">CV Responses</div>
          </div>
          
          <div className="bg-slate-800/50 rounded-xl border border-purple-500/30 p-3 md:p-4 text-center">
            <MessageSquare className="w-5 h-5 md:w-6 md:h-6 text-purple-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-purple-400">{stats?.rt?.mentions || 0}</div>
            <div className="text-xs text-slate-400">RT Mentions</div>
          </div>
        </div>

        {/* Data Management Cards */}
        <div className="space-y-4">
          {/* Customer Voice */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 md:p-6">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-500/20 rounded-lg shrink-0">
                  <Star className="w-5 h-5 text-orange-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Customer Voice Data</h3>
                  <p className="text-xs md:text-sm text-slate-400">
                    {stats?.cv?.responses || 0} responses • 
                    <span className="text-green-400 ml-1">{stats?.cv?.promoters || 0} promoters</span> • 
                    <span className="text-red-400 ml-1">{stats?.cv?.detractors || 0} detractors</span>
                  </p>
                </div>
              </div>
              
              <Button
                onClick={clearCVData}
                disabled={running.clearCV}
                variant="outline"
                size="sm"
                className="border-red-500/50 text-red-400 hover:bg-red-500/20 shrink-0"
              >
                {running.clearCV ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Trash2 className="w-4 h-4 mr-1" />
                    <span className="hidden sm:inline">Clear</span>
                  </>
                )}
              </Button>
            </div>
            
            {stats?.cv?.responses > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-700/50">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Customer Voice Total:</span>
                  <span className="font-bold text-purple-400">
                    {((stats?.cv?.promoters || 0) * 0.5) - (stats?.cv?.detractors || 0)} pts
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Review Tracker */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 md:p-6">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-500/20 rounded-lg shrink-0">
                  <MessageSquare className="w-5 h-5 text-purple-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-white">Review Tracker Data</h3>
                  <p className="text-xs md:text-sm text-slate-400">
                    {stats?.rt?.mentions || 0} total mentions • 
                    {stats?.rt?.employees || 0} employees with mentions
                  </p>
                </div>
              </div>
              
              <Button
                onClick={clearRTData}
                disabled={running.clearRT}
                variant="outline"
                size="sm"
                className="border-red-500/50 text-red-400 hover:bg-red-500/20 shrink-0"
              >
                {running.clearRT ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Trash2 className="w-4 h-4 mr-1" />
                    <span className="hidden sm:inline">Clear</span>
                  </>
                )}
              </Button>
            </div>
            
            {stats?.rt?.mentions > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-700/50">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Avg mentions/employee:</span>
                  <span className="font-bold text-purple-400">
                    {stats?.rt?.employees > 0 ? (stats?.rt?.mentions / stats?.rt?.employees).toFixed(1) : 0}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Employee Cleanup Section */}
        <div className="mt-6 bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 md:p-6">
          <div className="flex items-start justify-between gap-3 mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-red-500/20 rounded-lg shrink-0">
                <UserMinus className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">Employee Cleanup</h3>
                <p className="text-xs md:text-sm text-slate-400">
                  Find and remove duplicate or test employees
                </p>
              </div>
            </div>
            
            <Button
              onClick={analyzeEmployees}
              disabled={cleanupLoading}
              variant="outline"
              size="sm"
              className="border-blue-500/50 text-blue-400 hover:bg-blue-500/20 shrink-0"
            >
              {cleanupLoading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Search className="w-4 h-4 mr-1" />
                  <span className="hidden sm:inline">Analyze</span>
                </>
              )}
            </Button>
          </div>
          
          {showCleanupSection && cleanupData && (
            <div className="space-y-4">
              {/* Summary */}
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-green-500/10 rounded-lg p-2 border border-green-500/30">
                  <div className="text-lg font-bold text-green-400">{cleanupData.valid_count}</div>
                  <div className="text-xs text-slate-400">Valid</div>
                </div>
                <div className="bg-yellow-500/10 rounded-lg p-2 border border-yellow-500/30">
                  <div className="text-lg font-bold text-yellow-400">{cleanupData.duplicate_count}</div>
                  <div className="text-xs text-slate-400">Duplicates</div>
                </div>
                <div className="bg-red-500/10 rounded-lg p-2 border border-red-500/30">
                  <div className="text-lg font-bold text-red-400">{cleanupData.test_data_count}</div>
                  <div className="text-xs text-slate-400">Test Data</div>
                </div>
              </div>
              
              {/* Employees to delete */}
              {(cleanupData.potential_duplicates.length > 0 || cleanupData.test_data.length > 0) && (
                <>
                  <div className="border-t border-slate-700/50 pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-sm font-medium text-white">
                        Employees flagged for removal ({cleanupData.potential_duplicates.length + cleanupData.test_data.length})
                      </h4>
                      <Button
                        onClick={deleteSelected}
                        disabled={selectedForDeletion.size === 0 || running.deleteEmployees}
                        size="sm"
                        className="bg-red-600 hover:bg-red-700"
                      >
                        {running.deleteEmployees ? (
                          <RefreshCw className="w-4 h-4 animate-spin" />
                        ) : (
                          <>
                            <Trash2 className="w-4 h-4 mr-1" />
                            Delete Selected ({selectedForDeletion.size})
                          </>
                        )}
                      </Button>
                    </div>
                    
                    <div className="max-h-64 overflow-auto space-y-1">
                      {/* Test Data */}
                      {cleanupData.test_data.map(emp => (
                        <div 
                          key={emp.id}
                          className={`flex items-center gap-3 p-2 rounded-lg ${
                            selectedForDeletion.has(emp.id) ? 'bg-red-500/20' : 'bg-slate-700/30'
                          }`}
                        >
                          <Checkbox
                            checked={selectedForDeletion.has(emp.id)}
                            onCheckedChange={() => toggleSelection(emp.id)}
                            className="h-4 w-4"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-white truncate">{emp.name}</div>
                            <div className="text-xs text-red-400">{emp.reason}</div>
                          </div>
                          <span className="text-xs text-slate-500 shrink-0">Score: {emp.score?.toFixed(1) || 0}</span>
                        </div>
                      ))}
                      
                      {/* Duplicates */}
                      {cleanupData.potential_duplicates.map(emp => (
                        <div 
                          key={emp.id}
                          className={`flex items-center gap-3 p-2 rounded-lg ${
                            selectedForDeletion.has(emp.id) ? 'bg-yellow-500/20' : 'bg-slate-700/30'
                          }`}
                        >
                          <Checkbox
                            checked={selectedForDeletion.has(emp.id)}
                            onCheckedChange={() => toggleSelection(emp.id)}
                            className="h-4 w-4"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="text-sm text-white truncate">{emp.name}</div>
                            <div className="text-xs text-yellow-400">{emp.reason}</div>
                          </div>
                          <span className="text-xs text-slate-500 shrink-0">Score: {emp.score?.toFixed(1) || 0}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
              
              {cleanupData.potential_duplicates.length === 0 && cleanupData.test_data.length === 0 && (
                <div className="text-center py-4 text-green-400 flex items-center justify-center gap-2">
                  <CheckCircle className="w-5 h-5" />
                  <span>All employees look valid! No cleanup needed.</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Data Export/Import Section */}
        <div className="mt-6 bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 md:p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-purple-500/20 rounded-lg shrink-0">
              <Database className="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <h3 className="font-semibold text-white">Data Export / Import</h3>
              <p className="text-xs md:text-sm text-slate-400">
                Backup data or migrate between environments
              </p>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Export */}
            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/50">
              <h4 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                <Download className="w-4 h-4 text-green-400" />
                Export Data
              </h4>
              <p className="text-xs text-slate-400 mb-3">
                Download all employees and QR data as JSON
              </p>
              <Button
                onClick={exportData}
                disabled={running.export}
                className="w-full bg-green-600 hover:bg-green-700"
                size="sm"
              >
                {running.export ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Download className="w-4 h-4 mr-2" />
                    Export to JSON
                  </>
                )}
              </Button>
            </div>
            
            {/* Import */}
            <div className="bg-slate-900/50 rounded-lg p-4 border border-slate-700/50">
              <h4 className="text-sm font-medium text-white mb-2 flex items-center gap-2">
                <Upload className="w-4 h-4 text-blue-400" />
                Import Data
              </h4>
              <p className="text-xs text-slate-400 mb-3">
                Upload exported JSON to restore data
              </p>
              <div className="space-y-2">
                <label className="block">
                  <input
                    type="file"
                    accept=".json"
                    onChange={(e) => setImportFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                  <div className={`flex items-center justify-center gap-2 p-2 border border-dashed rounded-lg cursor-pointer transition-colors text-sm ${
                    importFile 
                      ? 'border-blue-500/50 bg-blue-500/10 text-blue-400' 
                      : 'border-slate-600 hover:border-slate-500 text-slate-400'
                  }`}>
                    {importFile ? importFile.name : 'Select JSON file'}
                  </div>
                </label>
                <Button
                  onClick={importData}
                  disabled={!importFile || importing}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                  size="sm"
                >
                  {importing ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      Import Data
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>

        {/* Help Text */}
        <div className="mt-6 p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
          <h3 className="font-semibold text-white text-sm mb-2 flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-blue-400" />
            Data Management
          </h3>
          <ul className="text-xs text-slate-400 space-y-1 list-disc list-inside">
            <li><strong>Recalculate All:</strong> Re-syncs all employee scores from current data</li>
            <li><strong>Clear CV:</strong> Removes all Customer Voice data (use before re-upload)</li>
            <li><strong>Clear RT:</strong> Resets all review mention counts to zero</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
