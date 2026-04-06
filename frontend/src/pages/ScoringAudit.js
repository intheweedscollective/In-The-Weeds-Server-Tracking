import { useState, useEffect, useCallback } from "react";
import { 
  ShieldCheck, AlertTriangle, CheckCircle, XCircle, RefreshCw, 
  Users, Calculator, Database, Search
} from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

const StatusBadge = ({ status }) => {
  const styles = {
    PASS: "bg-green-500/20 text-green-400 border-green-500/30",
    VERIFIED: "bg-green-500/20 text-green-400 border-green-500/30",
    WARNING: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    FAIL: "bg-red-500/20 text-red-400 border-red-500/30",
    ISSUES_FOUND: "bg-red-500/20 text-red-400 border-red-500/30"
  };
  
  const icons = {
    PASS: CheckCircle,
    VERIFIED: CheckCircle,
    WARNING: AlertTriangle,
    FAIL: XCircle,
    ISSUES_FOUND: AlertTriangle
  };
  
  const Icon = icons[status] || AlertTriangle;
  
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 md:px-3 py-1 md:py-1.5 rounded-full text-xs md:text-sm font-medium border ${styles[status] || styles.WARNING}`}>
      <Icon className="w-3 h-3 md:w-4 md:h-4" />
      {status}
    </span>
  );
};

export default function ScoringAudit() {
  const [allEmployeesAudit, setAllEmployeesAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [quarter] = useState("Q1");
  const [year] = useState(2026);
  const [fixingAll, setFixingAll] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  // Fetch all employees audit
  const fetchAllEmployeesAudit = useCallback(async () => {
    try {
      const response = await api.get(`/v2/audit/all?quarter=${quarter}&year=${year}`);
      setAllEmployeesAudit(response.data);
    } catch (error) {
      toast.error("Failed to fetch audit data");
    }
  }, [quarter, year]);

  // Fix all discrepancies
  const fixAllDiscrepancies = async () => {
    setFixingAll(true);
    toast.info("Fixing all discrepancies...");
    try {
      const response = await api.post(`/v2/audit/fix-all-discrepancies?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        toast.success(response.data.message || "All discrepancies fixed!");
      }
      await fetchAllEmployeesAudit();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to fix discrepancies");
    } finally {
      setFixingAll(false);
    }
  };

  // Recalculate all scores
  const recalculateAllScores = async () => {
    setRecalculating(true);
    toast.info("Recalculating all scores...");
    try {
      const response = await api.post(`/v2/audit/recalculate-all?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        const { fixed, unchanged } = response.data.summary;
        if (fixed > 0) {
          toast.success(`Fixed ${fixed} employee scores!`);
        } else {
          toast.info("All scores are already correct");
        }
      }
      await fetchAllEmployeesAudit();
    } catch (error) {
      toast.error("Failed to recalculate scores");
    } finally {
      setRecalculating(false);
    }
  };

  // Run full audit
  const runFullAudit = async () => {
    setLoading(true);
    toast.info("Running audit...");
    try {
      await fetchAllEmployeesAudit();
      toast.success("Audit complete!");
    } catch (error) {
      toast.error("Failed to run audit");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        await fetchAllEmployeesAudit();
      } catch (error) {
        console.error("Error loading audit data:", error);
      }
      setLoading(false);
    };
    init();
  }, [fetchAllEmployeesAudit]);

  const filteredEmployees = allEmployeesAudit?.employees?.filter(emp =>
    emp.name.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

  const passCount = filteredEmployees.filter(e => e.status === 'PASS').length;
  const failCount = filteredEmployees.filter(e => e.status === 'FAIL').length;

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="text-center">
          <RefreshCw className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-4" />
          <p className="text-slate-400">Running scoring audit...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 p-3 md:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 md:p-3 bg-emerald-500/20 rounded-xl shrink-0">
              <ShieldCheck className="w-5 h-5 md:w-7 md:h-7 text-emerald-400" />
            </div>
            <div>
              <h1 className="text-lg md:text-2xl font-bold text-white">Scoring Audit</h1>
              <p className="text-xs md:text-sm text-slate-400">{quarter} {year}</p>
            </div>
          </div>
          
          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            <Button
              onClick={recalculateAllScores}
              disabled={recalculating}
              size="sm"
              variant="outline"
              className="border-blue-500/50 text-blue-400 hover:bg-blue-500/10"
            >
              {recalculating ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Calculator className="w-4 h-4 mr-1" />
              )}
              Recalc
            </Button>
            <Button
              onClick={fixAllDiscrepancies}
              disabled={fixingAll}
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white"
            >
              {fixingAll ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <AlertTriangle className="w-4 h-4 mr-1" />
              )}
              Fix All
            </Button>
            <Button
              onClick={runFullAudit}
              disabled={loading}
              size="sm"
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              {loading ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <ShieldCheck className="w-4 h-4 mr-1" />
              )}
              Audit
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-2 md:gap-4 mb-6">
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-4 text-center">
            <Users className="w-5 h-5 md:w-6 md:h-6 text-blue-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-white">{filteredEmployees.length}</div>
            <div className="text-xs text-slate-400">Total</div>
          </div>

          <div className="bg-green-500/10 rounded-xl border border-green-500/30 p-3 md:p-4 text-center">
            <CheckCircle className="w-5 h-5 md:w-6 md:h-6 text-green-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-green-400">{passCount}</div>
            <div className="text-xs text-slate-400">Pass</div>
          </div>

          <div className="bg-red-500/10 rounded-xl border border-red-500/30 p-3 md:p-4 text-center">
            <XCircle className="w-5 h-5 md:w-6 md:h-6 text-red-400 mx-auto mb-1" />
            <div className="text-xl md:text-3xl font-bold text-red-400">{failCount}</div>
            <div className="text-xs text-slate-400">Fail</div>
          </div>
        </div>

        {/* Overall Status */}
        {allEmployeesAudit && (
          <div className={`rounded-xl border p-4 mb-6 ${
            failCount === 0 
              ? 'bg-green-500/10 border-green-500/30' 
              : 'bg-red-500/10 border-red-500/30'
          }`}>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                {failCount === 0 ? (
                  <CheckCircle className="w-6 h-6 text-green-400" />
                ) : (
                  <AlertTriangle className="w-6 h-6 text-red-400" />
                )}
                <div>
                  <h3 className="font-semibold text-white">
                    {failCount === 0 ? 'All Scores Verified' : `${failCount} Issue(s) Found`}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {failCount === 0 
                      ? 'All employee scores match calculated values' 
                      : 'Click "Fix All" to correct discrepancies'}
                  </p>
                </div>
              </div>
              <StatusBadge status={failCount === 0 ? 'VERIFIED' : 'ISSUES_FOUND'} />
            </div>
          </div>
        )}

        {/* Search */}
        <div className="mb-4">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input
              placeholder="Search employees..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9 bg-slate-800 border-slate-700 text-sm"
            />
          </div>
        </div>

        {/* Employee Audit List */}
        <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 overflow-hidden">
          <div className="p-3 md:p-4 border-b border-slate-700/50">
            <h2 className="font-semibold text-white flex items-center gap-2">
              <Database className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
              Employee Audit Status
            </h2>
          </div>
          
          <div className="divide-y divide-slate-700/50 max-h-[500px] overflow-y-auto">
            {filteredEmployees.length === 0 ? (
              <div className="p-8 text-center text-slate-400">
                <Users className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>No employees found</p>
              </div>
            ) : (
              filteredEmployees.map((emp) => (
                <div 
                  key={emp.name}
                  className={`p-3 md:p-4 flex items-center justify-between hover:bg-slate-800/50 transition-colors ${
                    emp.status === 'FAIL' ? 'bg-red-500/5' : ''
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-8 h-8 md:w-10 md:h-10 rounded-full flex items-center justify-center shrink-0 ${
                      emp.status === 'PASS' ? 'bg-green-500/20' : 'bg-red-500/20'
                    }`}>
                      {emp.status === 'PASS' ? (
                        <CheckCircle className="w-4 h-4 md:w-5 md:h-5 text-green-400" />
                      ) : (
                        <XCircle className="w-4 h-4 md:w-5 md:h-5 text-red-400" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="font-medium text-white text-sm md:text-base truncate">{emp.name}</p>
                      {emp.status === 'FAIL' && emp.status_details && (
                        <p className="text-xs text-red-400 truncate">{emp.status_details}</p>
                      )}
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-2 md:gap-4 shrink-0">
                    <div className="text-right hidden sm:block">
                      <p className="text-xs text-slate-400">Score</p>
                      <p className="text-sm md:text-lg font-bold text-white">{emp.stored_score?.toFixed(1)}</p>
                    </div>
                    <div className="sm:hidden text-white font-bold text-sm">
                      {emp.stored_score?.toFixed(1)}
                    </div>
                    <StatusBadge status={emp.status} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Formula Reference */}
        <div className="mt-6 p-4 bg-slate-800/30 rounded-xl border border-slate-700/50">
          <h3 className="font-semibold text-white text-sm mb-3 flex items-center gap-2">
            <Calculator className="w-4 h-4 text-blue-400" />
            Score Formula
          </h3>
          <div className="text-xs text-slate-400 space-y-1">
            <p><span className="text-white">Total Score</span> = Weighted POS + Customer Voice + Metric Bonus + RT Bonus</p>
            <p><span className="text-slate-300">Weighted POS:</span> PPA×25% + LSC×25% + LBW×20% + Glass×15%</p>
            <p><span className="text-slate-300">Customer Voice:</span> (Promoters×0.5) - (Detractors×1) [uncapped]</p>
            <p><span className="text-slate-300">RT Bonus:</span> Mentions × 0.5 pts (max 15)</p>
          </div>
        </div>
      </div>
    </div>
  );
}
