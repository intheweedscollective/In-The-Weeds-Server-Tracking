import { useState, useEffect, useCallback } from "react";
import { X, AlertTriangle, CheckCircle2, Lock, Unlock, FileWarning, Save, RefreshCw } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

export default function FinalizeQuarterModal({ isOpen, onClose, quarter, year, employees, snapshotId, onFinalized }) {
  const [darEntries, setDarEntries] = useState({});
  const [isFinalized, setIsFinalized] = useState(false);
  const [workflowStatus, setWorkflowStatus] = useState(null);
  const [finalRankings, setFinalRankings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load workflow status and existing DAR data
  const loadWorkflowData = useCallback(async () => {
    if (!snapshotId) return;
    
    try {
      setLoading(true);
      
      // Get workflow status
      const statusResponse = await axios.get(`${API}/api/v2/snapshot-workflow/snapshots/${snapshotId}/workflow-status`);
      setWorkflowStatus(statusResponse.data);
      setIsFinalized(statusResponse.data.is_finalized);
      
      // Load existing DAR entries from employees
      const darLookup = {};
      employees.forEach(emp => {
        if (emp.dar_written_warnings || emp.dar_suspensions) {
          darLookup[emp.id] = {
            written_warnings: emp.dar_written_warnings || 0,
            suspensions: emp.dar_suspensions || 0
          };
        } else {
          darLookup[emp.id] = { written_warnings: 0, suspensions: 0 };
        }
      });
      setDarEntries(darLookup);
      
    } catch (error) {
      console.error("Error loading workflow data:", error);
      // Fallback - initialize empty DAR entries
      const darLookup = {};
      employees.forEach(emp => {
        darLookup[emp.id] = { written_warnings: 0, suspensions: 0 };
      });
      setDarEntries(darLookup);
    } finally {
      setLoading(false);
    }
  }, [snapshotId, employees]);

  useEffect(() => {
    if (isOpen) {
      loadWorkflowData();
    }
  }, [isOpen, loadWorkflowData]);

  const handleDARChange = (employeeId, field, value) => {
    const numValue = Math.max(0, parseInt(value) || 0);
    setDarEntries(prev => {
      const existing = prev[employeeId] || { written_warnings: 0, suspensions: 0 };
      return {
        ...prev,
        [employeeId]: {
          written_warnings: existing.written_warnings || 0,
          suspensions: existing.suspensions || 0,
          [field]: numValue
        }
      };
    });
  };

  const calculateFinalScore = (employee) => {
    const dar = darEntries[employee.id] || { written_warnings: 0, suspensions: 0 };
    const preDarScore = parseFloat(employee.pre_dar_score) || parseFloat(employee.total_score) || 0;
    const writtenDeduction = (parseInt(dar.written_warnings) || 0) * 3;
    const suspensionDeduction = (parseInt(dar.suspensions) || 0) * 5;
    const finalScore = preDarScore - writtenDeduction - suspensionDeduction;
    return Math.max(0, isNaN(finalScore) ? preDarScore : finalScore);
  };

  const getTotalDeduction = (employee) => {
    const dar = darEntries[employee.id] || { written_warnings: 0, suspensions: 0 };
    const writtenDeduction = (parseInt(dar.written_warnings) || 0) * 3;
    const suspensionDeduction = (parseInt(dar.suspensions) || 0) * 5;
    return writtenDeduction + suspensionDeduction;
  };

  const handleSaveDraft = async () => {
    try {
      setSaving(true);
      const entries = employees.map(emp => ({
        employee_id: emp.id,
        employee_name: emp.name,
        written_warnings: darEntries[emp.id]?.written_warnings || 0,
        suspensions: darEntries[emp.id]?.suspensions || 0
      }));

      await axios.post(`${API}/api/v2/dar/${year}/${quarter}`, {
        quarter,
        year,
        entries
      });

      toast.success("DAR entries saved as draft");
    } catch (error) {
      console.error("Error saving DAR draft:", error);
      toast.error("Failed to save DAR entries");
    } finally {
      setSaving(false);
    }
  };

  const handleFinalize = async () => {
    if (!snapshotId) {
      toast.error("No snapshot ID available");
      return;
    }
    
    if (!window.confirm(`Are you sure you want to finalize ${quarter} ${year}?\n\nThis will:\n• Apply all DAR deductions\n• Lock all scores\n• Prevent further edits\n\nYou can reopen later if needed.`)) {
      return;
    }

    try {
      setSaving(true);
      
      // Build DAR entries array for the request
      const darEntriesArray = employees.map(emp => ({
        employee_id: emp.id,
        written_warnings: parseInt(darEntries[emp.id]?.written_warnings) || 0,
        suspensions: parseInt(darEntries[emp.id]?.suspensions) || 0
      }));

      // Use the new snapshot-based finalization endpoint
      const response = await axios.post(
        `${API}/api/v2/snapshot-workflow/snapshots/${snapshotId}/finalize`,
        { dar_entries: darEntriesArray }
      );

      setIsFinalized(true);
      setWorkflowStatus(prev => ({ ...prev, status: "finalized", is_finalized: true }));
      toast.success(`${quarter} ${year} finalized successfully! ${response.data.summary?.employees_with_dar || 0} employees have DAR deductions.`);
      
      if (onFinalized) {
        onFinalized();
      }
    } catch (error) {
      console.error("Error finalizing quarter:", error);
      toast.error(error.response?.data?.detail || "Failed to finalize quarter");
    } finally {
      setSaving(false);
    }
  };

  const handleUnfinalize = async () => {
    if (!snapshotId) {
      toast.error("No snapshot ID available");
      return;
    }
    
    if (!window.confirm(`Are you sure you want to reopen ${quarter} ${year}?\n\nThis will:\n• Unlock the quarter for edits\n• Remove finalization status\n• Restore pre-DAR scores`)) {
      return;
    }

    try {
      setSaving(true);
      await axios.post(`${API}/api/v2/snapshot-workflow/snapshots/${snapshotId}/reopen`);
      setIsFinalized(false);
      setWorkflowStatus(prev => ({ ...prev, status: "reviewed", is_finalized: false }));
      setFinalRankings([]);
      toast.success(`${quarter} ${year} reopened for edits`);
      
      if (onFinalized) {
        onFinalized();
      }
    } catch (error) {
      console.error("Error reopening quarter:", error);
      toast.error(error.response?.data?.detail || "Failed to reopen quarter");
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  // Sort employees by score for display
  const sortedEmployees = [...employees].sort((a, b) => {
    const scoreA = calculateFinalScore(a);
    const scoreB = calculateFinalScore(b);
    return scoreB - scoreA;
  });

  const totalDARDeductions = employees.reduce((sum, emp) => sum + getTotalDeduction(emp), 0);
  const employeesWithDAR = employees.filter(emp => getTotalDeduction(emp) > 0).length;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className={`p-6 ${isFinalized ? 'bg-gradient-to-r from-green-600 to-green-700' : 'bg-gradient-to-r from-primary to-secondary'}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
                {isFinalized ? <Lock className="w-6 h-6 text-white" /> : <FileWarning className="w-6 h-6 text-white" />}
              </div>
              <div>
                <h2 className="text-2xl font-serif font-bold text-white">
                  {isFinalized ? `${quarter} ${year} - Finalized` : `Finalize ${quarter} ${year}`}
                </h2>
                <p className="text-white/80 text-sm">
                  {isFinalized 
                    ? "Quarter is locked. Final rankings include DAR deductions."
                    : "Enter DAR counts to calculate final rankings"
                  }
                </p>
              </div>
            </div>
            <button onClick={onClose} className="text-white/70 hover:text-white transition-colors">
              <X className="w-6 h-6" />
            </button>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="px-6 py-4 bg-gray-50 border-b flex items-center justify-between">
          <div className="flex gap-6">
            <div>
              <p className="text-xs text-gray-500 uppercase font-semibold">Total Employees</p>
              <p className="text-xl font-bold text-gray-900">{employees.length}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-semibold">Employees w/ DAR</p>
              <p className="text-xl font-bold text-orange-600">{employeesWithDAR}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 uppercase font-semibold">Total Deductions</p>
              <p className="text-xl font-bold text-red-600">-{totalDARDeductions} pts</p>
            </div>
          </div>
          
          <div className="flex gap-2">
            {!isFinalized && (
              <>
                <Button 
                  variant="outline" 
                  onClick={handleSaveDraft}
                  disabled={saving}
                >
                  <Save className="w-4 h-4 mr-2" />
                  Save Draft
                </Button>
                <Button 
                  onClick={handleFinalize}
                  disabled={saving}
                  className="bg-green-600 hover:bg-green-700"
                >
                  <Lock className="w-4 h-4 mr-2" />
                  Finalize Quarter
                </Button>
              </>
            )}
            {isFinalized && (
              <Button 
                variant="outline"
                onClick={handleUnfinalize}
                disabled={saving}
                className="text-orange-600 border-orange-300 hover:bg-orange-50"
              >
                <Unlock className="w-4 h-4 mr-2" />
                Reopen Quarter
              </Button>
            )}
          </div>
        </div>

        {/* DAR Info */}
        <div className="px-6 py-3 bg-yellow-50 border-b border-yellow-200">
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-5 h-5 text-yellow-600 mt-0.5" />
            <div className="text-sm text-yellow-800">
              <strong>DAR Deductions:</strong> Written Warning = -3 pts | Suspension = -5 pts
              <br />
              <span className="text-yellow-700">These deductions are for end-of-quarter reviews only and will NOT appear on printed materials.</span>
            </div>
          </div>
        </div>

        {/* DAR Grid */}
        <div className="overflow-auto max-h-[50vh]">
          {loading ? (
            <div className="p-10 text-center text-gray-500">Loading...</div>
          ) : (
            <table className="w-full">
              <thead className="bg-gray-100 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                    Rank
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                    Employee
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                    Pre-DAR Score
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-orange-600 uppercase tracking-wider">
                    Written Warnings (-3 ea)
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-red-600 uppercase tracking-wider">
                    Suspensions (-5 ea)
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                    Deduction
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-semibold text-green-600 uppercase tracking-wider">
                    Final Score
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {sortedEmployees.map((employee, idx) => {
                  const dar = darEntries[employee.id] || { written_warnings: 0, suspensions: 0 };
                  const preDarScore = employee.pre_dar_score || employee.total_score || 0;
                  const deduction = getTotalDeduction(employee);
                  const finalScore = calculateFinalScore(employee);
                  const hasDAR = deduction > 0;

                  return (
                    <tr 
                      key={employee.id} 
                      className={`${hasDAR ? 'bg-red-50' : ''} hover:bg-gray-50 transition-colors`}
                    >
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center justify-center w-8 h-8 rounded-full text-sm font-bold ${
                          idx === 0 ? 'bg-yellow-100 text-yellow-700' :
                          idx === 1 ? 'bg-gray-200 text-gray-700' :
                          idx === 2 ? 'bg-orange-100 text-orange-700' :
                          'bg-gray-100 text-gray-600'
                        }`}>
                          {idx + 1}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div>
                          <p className="font-semibold text-gray-900">{employee.display_name || employee.name}</p>
                          <p className="text-xs text-gray-600">{employee.job_title || 'Server'}</p>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="font-medium text-gray-700">{preDarScore.toFixed(1)}</span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Input
                          type="number"
                          min="0"
                          value={dar.written_warnings}
                          onChange={(e) => handleDARChange(employee.id, 'written_warnings', e.target.value)}
                          disabled={isFinalized}
                          className="w-20 text-center mx-auto text-gray-900 bg-white border-gray-300"
                          data-testid={`dar-written-${employee.id}`}
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <Input
                          type="number"
                          min="0"
                          value={dar.suspensions}
                          onChange={(e) => handleDARChange(employee.id, 'suspensions', e.target.value)}
                          disabled={isFinalized}
                          className="w-20 text-center mx-auto text-gray-900 bg-white border-gray-300"
                          data-testid={`dar-suspension-${employee.id}`}
                        />
                      </td>
                      <td className="px-4 py-3 text-center">
                        {deduction > 0 ? (
                          <span className="font-bold text-red-600">-{deduction}</span>
                        ) : (
                          <span className="text-gray-400">0</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`font-bold text-lg ${hasDAR ? 'text-orange-600' : 'text-green-600'}`}>
                          {finalScore.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t flex items-center justify-between">
          <p className="text-xs text-gray-500">
            {isFinalized ? (
              <span className="flex items-center gap-1 text-green-600">
                <CheckCircle2 className="w-4 h-4" />
                Quarter finalized. Rankings are locked.
              </span>
            ) : (
              "Changes are not saved until you click 'Save Draft' or 'Finalize Quarter'"
            )}
          </p>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
