import { useState, useEffect, useCallback } from "react";
import { X, AlertTriangle, CheckCircle2, Lock, Unlock, FileWarning, Save } from "lucide-react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { toast } from "sonner";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

export default function FinalizeQuarterModal({ isOpen, onClose, quarter, year, employees, onFinalized }) {
  const [darEntries, setDarEntries] = useState({});
  const [isFinalized, setIsFinalized] = useState(false);
  const [finalRankings, setFinalRankings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  // Load existing DAR data
  const loadDARData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Check if already finalized
      const finResponse = await axios.get(`${API}/api/v2/finalization/${year}/${quarter}`);
      if (finResponse.data.is_finalized) {
        setIsFinalized(true);
        setFinalRankings(finResponse.data.final_rankings || []);
        
        // Load DAR entries from finalization
        const darLookup = {};
        (finResponse.data.dar_entries || []).forEach(entry => {
          darLookup[entry.employee_id] = {
            written_warnings: entry.written_warnings || 0,
            suspensions: entry.suspensions || 0
          };
        });
        setDarEntries(darLookup);
      } else {
        // Load draft DAR entries
        const darResponse = await axios.get(`${API}/api/v2/dar/${year}/${quarter}`);
        const darLookup = {};
        (darResponse.data || []).forEach(entry => {
          darLookup[entry.employee_id] = {
            written_warnings: entry.written_warnings || 0,
            suspensions: entry.suspensions || 0
          };
        });
        setDarEntries(darLookup);
      }
    } catch (error) {
      console.error("Error loading DAR data:", error);
    } finally {
      setLoading(false);
    }
  }, [year, quarter]);

  useEffect(() => {
    if (isOpen) {
      loadDARData();
    }
  }, [isOpen, loadDARData]);

  const handleDARChange = (employeeId, field, value) => {
    const numValue = Math.max(0, parseInt(value) || 0);
    setDarEntries(prev => ({
      ...prev,
      [employeeId]: {
        ...prev[employeeId],
        [field]: numValue
      }
    }));
  };

  const calculateFinalScore = (employee) => {
    const dar = darEntries[employee.id] || { written_warnings: 0, suspensions: 0 };
    const preDarScore = employee.pre_dar_score || employee.total_score || 0;
    const writtenDeduction = dar.written_warnings * 3;
    const suspensionDeduction = dar.suspensions * 5;
    return Math.max(0, preDarScore - writtenDeduction - suspensionDeduction);
  };

  const getTotalDeduction = (employee) => {
    const dar = darEntries[employee.id] || { written_warnings: 0, suspensions: 0 };
    return (dar.written_warnings * 3) + (dar.suspensions * 5);
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
    if (!window.confirm(`Are you sure you want to finalize ${quarter} ${year}? This will lock the final rankings with DAR deductions applied.`)) {
      return;
    }

    try {
      setSaving(true);
      const entries = employees.map(emp => ({
        employee_id: emp.id,
        employee_name: emp.name,
        written_warnings: darEntries[emp.id]?.written_warnings || 0,
        suspensions: darEntries[emp.id]?.suspensions || 0
      }));

      const response = await axios.post(`${API}/api/v2/finalize/${year}/${quarter}`, {
        quarter,
        year,
        entries
      });

      setIsFinalized(true);
      setFinalRankings(response.data.final_rankings || []);
      toast.success(`${quarter} ${year} finalized successfully!`);
      
      if (onFinalized) {
        onFinalized(response.data.final_rankings);
      }
    } catch (error) {
      console.error("Error finalizing quarter:", error);
      toast.error("Failed to finalize quarter");
    } finally {
      setSaving(false);
    }
  };

  const handleUnfinalize = async () => {
    if (!window.confirm(`Are you sure you want to reopen ${quarter} ${year}? This will unlock the quarter for further edits.`)) {
      return;
    }

    try {
      setSaving(true);
      await axios.delete(`${API}/api/v2/finalize/${year}/${quarter}`);
      setIsFinalized(false);
      setFinalRankings([]);
      toast.success(`${quarter} ${year} reopened for edits`);
    } catch (error) {
      console.error("Error unfinalizing quarter:", error);
      toast.error("Failed to reopen quarter");
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
              <p className="text-xl font-bold text-foreground">{employees.length}</p>
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
                          <p className="font-semibold text-foreground">{employee.name}</p>
                          <p className="text-xs text-gray-500">{employee.job_title || 'Server'}</p>
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
                          className="w-20 text-center mx-auto"
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
                          className="w-20 text-center mx-auto"
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
