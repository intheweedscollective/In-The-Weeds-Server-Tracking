import { useState, useEffect, useCallback } from "react";
import { 
  ShieldCheck, AlertTriangle, CheckCircle, XCircle, RefreshCw, 
  FileText, Users, ChevronDown, ChevronUp, Search, 
  Calculator, Database, ClipboardCheck, Info, ArrowRight, Trash2, RotateCcw, Settings, X, Clock, Play
} from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

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
    <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${styles[status] || styles.WARNING}`}>
      <Icon className="w-4 h-4" />
      {status}
    </span>
  );
};

const CalculationCard = ({ title, data }) => {
  const [expanded, setExpanded] = useState(false);
  
  if (!data) return null;
  
  const isMatch = data.match !== false;
  
  return (
    <div className={`bg-slate-800/50 rounded-lg border ${isMatch ? 'border-slate-700/50' : 'border-yellow-500/50'} p-4`}>
      <button 
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          {isMatch ? (
            <CheckCircle className="w-4 h-4 text-green-400" />
          ) : (
            <AlertTriangle className="w-4 h-4 text-yellow-400" />
          )}
          <span className="font-medium text-white">{title}</span>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
      </button>
      
      {expanded && (
        <div className="mt-3 pt-3 border-t border-slate-700/50 space-y-2">
          {data.formula && (
            <div className="text-xs text-slate-400">
              <span className="text-slate-500">Formula:</span> {data.formula}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div>
              <span className="text-slate-500">Expected:</span>
              <span className="ml-2 text-green-400 font-mono">{typeof data.expected === 'number' ? data.expected.toFixed(2) : data.expected ?? 'N/A'}</span>
            </div>
            <div>
              <span className="text-slate-500">Stored:</span>
              <span className={`ml-2 font-mono ${isMatch ? 'text-white' : 'text-yellow-400'}`}>
                {typeof data.stored === 'number' ? data.stored.toFixed(2) : data.stored ?? 'N/A'}
              </span>
            </div>
          </div>
          {data.breakdown && (
            <div className="mt-2 pt-2 border-t border-slate-700/30">
              <span className="text-xs text-slate-500">Breakdown:</span>
              <div className="grid grid-cols-2 gap-1 mt-1">
                {Object.entries(data.breakdown).map(([key, value]) => (
                  <div key={key} className="text-xs">
                    <span className="text-slate-500">{key.replace(/_/g, ' ')}:</span>
                    <span className="ml-1 text-slate-300 font-mono">{typeof value === 'number' ? value.toFixed(2) : value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const EmployeeAuditDetail = ({ audit, onFixEmployee }) => {
  if (!audit) return null;
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-bold text-white">{audit.employee_name}</h3>
          <p className="text-slate-400">{audit.quarter} {audit.year} • Audited {new Date(audit.audited_at).toLocaleString()}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm text-slate-400">Final Score</p>
            <p className="text-2xl font-bold text-white">{audit.final_score?.toFixed(2)}</p>
          </div>
          <StatusBadge status={audit.validation_status} />
        </div>
      </div>
      
      {/* Discrepancies */}
      {audit.discrepancies?.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-red-400 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              Discrepancies Found ({audit.discrepancies.length})
            </h4>
            {onFixEmployee && (
              <button
                onClick={() => onFixEmployee(audit.employee_name)}
                className="px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg flex items-center gap-2 transition-colors"
                data-testid="fix-employee-btn"
              >
                <RefreshCw className="w-4 h-4" />
                Fix This Employee
              </button>
            )}
          </div>
          <div className="space-y-2">
            {audit.discrepancies.map((d, i) => (
              <div key={i} className={`p-3 rounded-lg ${
                d.severity === 'CRITICAL' ? 'bg-red-500/20' : 
                d.severity === 'HIGH' ? 'bg-orange-500/20' : 'bg-yellow-500/20'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-white">{d.field}</span>
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    d.severity === 'CRITICAL' ? 'bg-red-600 text-white' :
                    d.severity === 'HIGH' ? 'bg-orange-600 text-white' : 'bg-yellow-600 text-black'
                  }`}>{d.severity}</span>
                </div>
                <p className="text-sm text-slate-300 mt-1">{d.description}</p>
              </div>
            ))}
          </div>
        </div>
      )}
      
      {/* Calculations */}
      <div className="space-y-4">
        <h4 className="font-semibold text-white flex items-center gap-2">
          <Calculator className="w-5 h-5 text-blue-400" />
          Calculation Audit Trail
        </h4>
        
        {/* POS Metrics */}
        <div className="bg-slate-800/30 rounded-xl p-4">
          <h5 className="text-sm font-medium text-slate-300 mb-3">POS Metrics</h5>
          <div className="grid grid-cols-2 gap-3">
            <CalculationCard title="PPA" data={audit.calculations?.pos_metrics?.ppa} />
            <CalculationCard title="LBW/Guest" data={audit.calculations?.pos_metrics?.lbw_per_guest} />
            <CalculationCard title="Glass/Guest" data={audit.calculations?.pos_metrics?.glassware_per_guest} />
            <CalculationCard title="Guests/LSC" data={audit.calculations?.pos_metrics?.guests_per_lsc} />
          </div>
        </div>
        
        {/* Normalized Scores */}
        <div className="bg-slate-800/30 rounded-xl p-4">
          <h5 className="text-sm font-medium text-slate-300 mb-3">Normalized Scores (vs Benchmark)</h5>
          <div className="grid grid-cols-2 gap-3">
            <CalculationCard title="PPA Score" data={audit.calculations?.normalized_scores?.ppa_score} />
            <CalculationCard title="LBW Score" data={audit.calculations?.normalized_scores?.lbw_score} />
            <CalculationCard title="Glass Score" data={audit.calculations?.normalized_scores?.glass_score} />
            <CalculationCard title="LSC Score" data={audit.calculations?.normalized_scores?.lsc_score} />
          </div>
        </div>
        
        {/* Weighted Score */}
        <CalculationCard title="Weighted Base Score (75 pts max)" data={audit.calculations?.weighted_score} />
        
        {/* Customer Voice */}
        <div className="bg-slate-800/30 rounded-xl p-4">
          <h5 className="text-sm font-medium text-slate-300 mb-3">Customer Voice Score</h5>
          <CalculationCard title="Total CV Score" data={audit.calculations?.customer_voice?.total_cv_score} />
          
          {audit.data_trail?.customer_voice && (
            <div className="mt-3 p-3 bg-slate-900/50 rounded-lg text-sm">
              <div className="text-xs text-slate-500 mb-2">Raw Data Trail:</div>
              <div className="grid grid-cols-4 gap-2">
                <div>
                  <span className="text-slate-500">Raw Feedback:</span>
                  <span className="ml-1 text-white font-mono">{audit.data_trail.customer_voice.raw_feedback_count}</span>
                </div>
                <div>
                  <span className="text-slate-500">Promoters:</span>
                  <span className="ml-1 text-green-400 font-mono">{audit.data_trail.customer_voice.raw_promoters}</span>
                </div>
                <div>
                  <span className="text-slate-500">Passives:</span>
                  <span className="ml-1 text-yellow-400 font-mono">{audit.data_trail.customer_voice.raw_passives}</span>
                </div>
                <div>
                  <span className="text-slate-500">Detractors:</span>
                  <span className="ml-1 text-red-400 font-mono">{audit.data_trail.customer_voice.raw_detractors}</span>
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* Review Tracker */}
        <CalculationCard title="Review Tracker Bonus" data={audit.calculations?.review_tracker} />
        
        {/* Metric Bonus */}
        <CalculationCard title="Total Metric Bonus (20 pts max)" data={audit.calculations?.metric_bonus?.total} />
        
        {/* Final Score */}
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
          <h5 className="text-sm font-medium text-blue-300 mb-3 flex items-center gap-2">
            <ClipboardCheck className="w-4 h-4" />
            Final Score Calculation
          </h5>
          <CalculationCard title="Pre-DAR Score" data={audit.calculations?.final_score} />
        </div>
      </div>
    </div>
  );
};

export default function ScoringAudit() {
  const [report, setReport] = useState(null);
  const [allEmployeesAudit, setAllEmployeesAudit] = useState(null);
  const [selectedEmployee, setSelectedEmployee] = useState(null);
  const [employeeAudit, setEmployeeAudit] = useState(null);
  const [loading, setLoading] = useState(true);
  const [auditLoading, setAuditLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [quarter] = useState("Q1");
  const [year] = useState(2026);
  const [dataCapStatus, setDataCapStatus] = useState(null);
  const [recalculating, setRecalculating] = useState(false);
  const [enforcing, setEnforcing] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncingNps, setSyncingNps] = useState(false);
  const [fixingAll, setFixingAll] = useState(false);
  
  // Official CV Stats state
  const [showCVModal, setShowCVModal] = useState(false);
  const [cvStats, setCvStats] = useState({
    promoters: 0,
    passives: 0,
    detractors: 0,
    total_responses: 0,
    nps_score: 0
  });
  const [savingCV, setSavingCV] = useState(false);
  const [reconcilingCV, setReconcilingCV] = useState(false);

  // Scheduler state
  const [showSchedulerModal, setShowSchedulerModal] = useState(false);
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [schedulerConfig, setSchedulerConfig] = useState({
    enabled: false,
    schedule_hour: 2,
    schedule_minute: 0,
    quarter: "Q1",
    year: 2026
  });
  const [savingScheduler, setSavingScheduler] = useState(false);
  const [runningNow, setRunningNow] = useState(false);
  const [reconciliationHistory, setReconciliationHistory] = useState([]);

  // Save official CV stats
  const saveOfficialCVStats = async () => {
    setSavingCV(true);
    try {
      await axios.post(`${API}/v2/admin/cv-stats/set`, {
        quarter,
        year,
        ...cvStats
      });
      toast.success("Official CV stats saved!");
      await fetchDataCapStatus();
    } catch (error) {
      toast.error("Failed to save CV stats");
    } finally {
      setSavingCV(false);
    }
  };

  // Reconcile CV data with official stats
  const reconcileCVData = async () => {
    setReconcilingCV(true);
    toast.info("Reconciling CV data with official stats...");
    try {
      const response = await axios.post(`${API}/v2/admin/cv-stats/reconcile?quarter=${quarter}&year=${year}`);
      const data = response.data;
      if (data.success) {
        toast.success(`Reconciled: Added ${data.added}, Removed ${data.removed} records`);
        // Now fix all to recalculate scores
        await fixAllDiscrepancies();
      }
      setShowCVModal(false);
    } catch (error) {
      toast.error(error.response?.data?.error || "Failed to reconcile CV data");
    } finally {
      setReconcilingCV(false);
    }
  };

  // Fetch current official CV stats
  const fetchOfficialCVStats = async () => {
    try {
      const response = await axios.get(`${API}/v2/admin/cv-stats/official?quarter=${quarter}&year=${year}`);
      if (response.data.official_stats_set) {
        setCvStats({
          promoters: response.data.stats.promoters || 0,
          passives: response.data.stats.passives || 0,
          detractors: response.data.stats.detractors || 0,
          total_responses: response.data.stats.total_responses || 0,
          nps_score: response.data.stats.nps_score || 0
        });
      }
    } catch (error) {
      console.error("Failed to fetch official CV stats");
    }
  };

  // Fetch scheduler status
  const fetchSchedulerStatus = async () => {
    try {
      const response = await axios.get(`${API}/v2/scheduler/status`);
      setSchedulerStatus(response.data);
      if (response.data.config) {
        setSchedulerConfig(response.data.config);
      }
    } catch (error) {
      console.error("Failed to fetch scheduler status");
    }
  };

  // Fetch reconciliation history
  const fetchReconciliationHistory = async () => {
    try {
      const response = await axios.get(`${API}/v2/scheduler/history?limit=5`);
      setReconciliationHistory(response.data.history || []);
    } catch (error) {
      console.error("Failed to fetch reconciliation history");
    }
  };

  // Save scheduler configuration
  const saveSchedulerConfig = async () => {
    setSavingScheduler(true);
    try {
      const response = await axios.post(`${API}/v2/scheduler/configure`, schedulerConfig);
      if (response.data.success) {
        toast.success(response.data.message);
        await fetchSchedulerStatus();
      }
    } catch (error) {
      toast.error("Failed to save scheduler configuration");
    } finally {
      setSavingScheduler(false);
    }
  };

  // Run reconciliation now
  const runReconciliationNow = async () => {
    setRunningNow(true);
    toast.info("Running full reconciliation... This may take a moment.");
    try {
      const response = await axios.post(`${API}/v2/scheduler/run-now?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        toast.success(`Reconciliation complete! ${response.data.steps[2]?.passed || 0}/${response.data.steps[2]?.total || 0} employees verified.`);
        // Refresh all data
        await fetchAuditReport();
        await fetchAllEmployeesAudit();
        await fetchDataCapStatus();
        await fetchReconciliationHistory();
      } else {
        toast.error("Reconciliation completed with issues");
      }
    } catch (error) {
      toast.error("Failed to run reconciliation");
    } finally {
      setRunningNow(false);
    }
  };

  // Fix all discrepancies - comprehensive fix
  const fixAllDiscrepancies = async () => {
    setFixingAll(true);
    toast.info("Fixing all discrepancies... This may take a moment.");
    try {
      const response = await axios.post(`${API}/v2/audit/fix-all-discrepancies?quarter=${quarter}&year=${year}`);
      if (response.data.steps) {
        const steps = response.data.steps;
        const reviewStep = steps.find(s => s.step === "sync_reviews");
        const mentionStep = steps.find(s => s.step === "update_mention_counts");
        const scoreStep = steps.find(s => s.step === "recalculate_scores");
        
        let message = "Fixed: ";
        if (reviewStep) message += `${reviewStep.updated || 0} reviews, `;
        if (mentionStep) message += `${mentionStep.updated || 0} mentions, `;
        if (scoreStep) message += `${scoreStep.recalculated || 0} scores`;
        
        toast.success(message);
      } else {
        toast.success("All discrepancies fixed!");
      }
      // Refresh all data
      await fetchAuditReport();
      await fetchAllEmployeesAudit();
      await fetchDataCapStatus();
    } catch (error) {
      console.error("Fix error:", error);
      toast.error(error.response?.data?.detail || "Failed to fix discrepancies");
    } finally {
      setFixingAll(false);
    }
  };

  // Sync NPS and Review data to employees
  const syncNpsToEmployees = async () => {
    setSyncingNps(true);
    try {
      const response = await axios.post(`${API}/v2/audit/sync-nps-to-employees?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        const summary = response.data.summary;
        toast.success(`Synced ${summary.nps_matched_to_employees} NPS records and ${summary.review_mentions_matched} review mentions`);
        // Refresh audit data
        await fetchAuditReport();
        await fetchAllEmployeesAudit();
      }
    } catch (error) {
      toast.error("Failed to sync NPS data");
    } finally {
      setSyncingNps(false);
    }
  };

  const fetchAuditReport = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/audit/report?quarter=${quarter}&year=${year}`);
      setReport(response.data);
    } catch (error) {
      toast.error("Failed to fetch audit report");
    }
  }, [quarter, year]);

  const fetchAllEmployeesAudit = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/audit/all?quarter=${quarter}&year=${year}`);
      setAllEmployeesAudit(response.data);
    } catch (error) {
      toast.error("Failed to fetch employees audit");
    }
  }, [quarter, year]);

  const fetchEmployeeAudit = async (employeeName) => {
    setAuditLoading(true);
    try {
      const response = await axios.get(`${API}/v2/audit/employee/${encodeURIComponent(employeeName)}?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        setEmployeeAudit(response.data.audit);
        setSelectedEmployee(employeeName);
      } else {
        toast.error(response.data.error || "Failed to fetch audit");
      }
    } catch (error) {
      toast.error("Failed to fetch employee audit");
    } finally {
      setAuditLoading(false);
    }
  };

  const runFullAudit = async () => {
    setLoading(true);
    toast.info("Running full audit...");
    try {
      await fetchAuditReport();
      await fetchAllEmployeesAudit();
      await fetchDataCapStatus();
      toast.success("Audit complete!");
    } catch (error) {
      toast.error("Failed to run audit");
    } finally {
      setLoading(false);
    }
  };

  const fetchDataCapStatus = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/audit/data-cap-check?quarter=${quarter}&year=${year}`);
      setDataCapStatus(response.data);
    } catch (error) {
      console.error("Failed to fetch data cap status");
    }
  }, [quarter, year]);

  const recalculateAllScores = async () => {
    setRecalculating(true);
    try {
      const response = await axios.post(`${API}/v2/audit/recalculate-all?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        const { fixed, unchanged, errors } = response.data.summary;
        if (fixed > 0) {
          toast.success(`Fixed ${fixed} employee scores!`);
        } else {
          toast.info("All scores are already correct");
        }
        // Refresh audit data
        await fetchAuditReport();
        await fetchAllEmployeesAudit();
      }
    } catch (error) {
      toast.error("Failed to recalculate scores");
    } finally {
      setRecalculating(false);
    }
  };

  const enforceDataCaps = async () => {
    setEnforcing(true);
    try {
      const response = await axios.post(`${API}/v2/audit/enforce-data-caps?quarter=${quarter}&year=${year}`);
      const cv_removed = response.data.customer_voice?.removed || 0;
      const rt_removed = response.data.review_tracker?.removed || 0;
      
      if (cv_removed > 0 || rt_removed > 0) {
        toast.success(`Removed ${cv_removed} excess CV entries and ${rt_removed} excess reviews`);
        // Sync employee mentions after removing data
        await syncEmployeeMentions();
        // Refresh data
        await fetchDataCapStatus();
        await fetchAuditReport();
        await fetchAllEmployeesAudit();
      } else {
        toast.info("All data is within official limits - no action needed");
      }
    } catch (error) {
      toast.error("Failed to enforce data caps");
    } finally {
      setEnforcing(false);
    }
  };

  const syncEmployeeMentions = async () => {
    setSyncing(true);
    try {
      const response = await axios.post(`${API}/v2/audit/sync-employee-mentions?quarter=${quarter}&year=${year}`);
      if (response.data.success) {
        const { updated, unchanged } = response.data.summary;
        if (updated > 0) {
          toast.success(`Synced ${updated} employee records with current review data`);
        }
        return response.data;
      }
    } catch (error) {
      toast.error("Failed to sync employee mentions");
    } finally {
      setSyncing(false);
    }
  };

  // Fix a single employee's discrepancies
  const fixSingleEmployee = async (employeeName) => {
    toast.info(`Fixing discrepancies for ${employeeName}...`);
    try {
      // Sync mentions for this employee
      await axios.post(`${API}/v2/audit/sync-employee-mentions?quarter=${quarter}&year=${year}`);
      // Sync NPS
      await axios.post(`${API}/v2/audit/sync-nps-to-employees?quarter=${quarter}&year=${year}`);
      // Recalculate
      await axios.post(`${API}/v2/audit/recalculate-all?quarter=${quarter}&year=${year}`);
      
      toast.success(`Fixed discrepancies for ${employeeName}`);
      
      // Refresh the audit for this employee
      await fetchEmployeeAudit(employeeName);
      await fetchAllEmployeesAudit();
    } catch (error) {
      toast.error(`Failed to fix ${employeeName}`);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      try {
        await Promise.all([
          fetchAuditReport(),
          fetchAllEmployeesAudit(),
          fetchDataCapStatus(),
          fetchOfficialCVStats(),
          fetchSchedulerStatus(),
          fetchReconciliationHistory()
        ]);
      } catch (error) {
        console.error("Error loading audit data:", error);
      }
      setLoading(false);
    };
    init();
  }, [fetchAuditReport, fetchAllEmployeesAudit, fetchDataCapStatus]);

  const filteredEmployees = allEmployeesAudit?.employees?.filter(emp =>
    emp.name.toLowerCase().includes(searchTerm.toLowerCase())
  ) || [];

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
    <div className="min-h-screen bg-slate-900 p-4 md:p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <div className="p-2 md:p-3 bg-emerald-500/20 rounded-xl shrink-0">
              <ShieldCheck className="w-6 h-6 md:w-8 md:h-8 text-emerald-400" />
            </div>
            <div>
              <h1 className="text-xl md:text-2xl font-bold text-white">Scoring Audit</h1>
              <p className="text-sm text-slate-400 hidden sm:block">Self-checking process for 100% accurate scoring</p>
            </div>
            {report && <StatusBadge status={report.overall_status} />}
          </div>
          
          {/* Action Buttons - Scrollable on mobile */}
          <div className="flex items-center gap-2 overflow-x-auto pb-2 -mx-4 px-4 md:mx-0 md:px-0 md:overflow-visible md:flex-wrap">
            <Button
              onClick={syncNpsToEmployees}
              disabled={syncingNps}
              variant="outline"
              size="sm"
              className="border-green-500/50 text-green-400 hover:bg-green-500/10 whitespace-nowrap shrink-0"
              data-testid="sync-nps-btn"
            >
              {syncingNps ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Users className="w-4 h-4 mr-1" />
              )}
              <span className="hidden sm:inline">Sync </span>NPS
            </Button>
            <Button
              onClick={async () => {
                await syncEmployeeMentions();
                await fetchAuditReport();
                await fetchAllEmployeesAudit();
              }}
              disabled={syncing}
              variant="outline"
              size="sm"
              className="border-yellow-500/50 text-yellow-400 hover:bg-yellow-500/10 whitespace-nowrap shrink-0"
            >
              {syncing ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Database className="w-4 h-4 mr-1" />
              )}
              <span className="hidden sm:inline">Sync </span>Mentions
            </Button>
            <Button
              onClick={recalculateAllScores}
              disabled={recalculating}
              variant="outline"
              size="sm"
              className="border-blue-500/50 text-blue-400 hover:bg-blue-500/10 whitespace-nowrap shrink-0"
            >
              {recalculating ? (
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <RotateCcw className="w-4 h-4 mr-1" />
              )}
              Recalc
            </Button>
            <Button
              onClick={fixAllDiscrepancies}
              disabled={fixingAll}
              size="sm"
              className="bg-red-600 hover:bg-red-700 text-white whitespace-nowrap shrink-0"
              data-testid="fix-all-btn"
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
              className="bg-emerald-600 hover:bg-emerald-700 whitespace-nowrap shrink-0"
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

        {/* Data Cap Enforcement Section */}
        {dataCapStatus && (
          <div className={`rounded-xl border p-3 md:p-4 mb-6 ${
            dataCapStatus.overall_status === 'COMPLIANT' 
              ? 'bg-green-500/10 border-green-500/30' 
              : 'bg-red-500/10 border-red-500/30'
          }`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
              <div className="flex items-center gap-2">
                <Database className="w-4 h-4 text-slate-400 shrink-0" />
                <div>
                  <h3 className="font-semibold text-white text-sm md:text-base">Data Cap Enforcement</h3>
                  <p className="text-xs text-slate-400 hidden sm:block">Official dashboard = MAXIMUM allowed</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  onClick={() => setShowSchedulerModal(true)}
                  size="sm"
                  variant="outline"
                  className="border-purple-500/50 text-purple-400 hover:bg-purple-500/10"
                >
                  <Clock className="w-4 h-4 mr-1" />
                  {schedulerStatus?.job_active ? "Scheduler On" : "Scheduler"}
                </Button>
                <Button
                  onClick={() => setShowCVModal(true)}
                  size="sm"
                  variant="outline"
                  className="border-blue-500/50 text-blue-400 hover:bg-blue-500/10"
                >
                  <Settings className="w-4 h-4 mr-1" />
                  Set Official CV
                </Button>
                {dataCapStatus.overall_status !== 'COMPLIANT' && (
                  <Button
                    onClick={enforceDataCaps}
                    disabled={enforcing}
                    size="sm"
                    className="bg-red-600 hover:bg-red-700"
                  >
                    {enforcing ? (
                      <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4 mr-1" />
                    )}
                    Remove Excess
                  </Button>
                )}
              </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {/* Customer Voice */}
              <div className={`p-2 md:p-3 rounded-lg ${
                dataCapStatus.customer_voice?.status === 'EXCEEDS_LIMIT' 
                  ? 'bg-red-500/20' 
                  : dataCapStatus.customer_voice?.status === 'AT_LIMIT'
                  ? 'bg-green-500/20'
                  : 'bg-slate-800/50'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-slate-300 text-sm">CV Feedback</span>
                  {dataCapStatus.customer_voice?.status === 'EXCEEDS_LIMIT' ? (
                    <span className="text-red-400 text-xs font-medium">
                      +{dataCapStatus.customer_voice.excess}
                    </span>
                  ) : (
                    <CheckCircle className="w-4 h-4 text-green-400" />
                  )}
                </div>
                <div className="text-xs text-slate-500">
                  <span className="text-white font-mono">{dataCapStatus.customer_voice?.our_count}</span>
                  {' / '}
                  <span className="text-white font-mono">{dataCapStatus.customer_voice?.official_max ?? '?'}</span>
                </div>
              </div>
              
              {/* Review Tracker */}
              <div className={`p-2 md:p-3 rounded-lg ${
                dataCapStatus.review_tracker?.status === 'EXCEEDS_LIMIT' 
                  ? 'bg-red-500/20' 
                  : dataCapStatus.review_tracker?.status === 'AT_LIMIT'
                  ? 'bg-green-500/20'
                  : 'bg-slate-800/50'
              }`}>
                <div className="flex items-center justify-between">
                  <span className="text-slate-300 text-sm">RT Reviews</span>
                  {dataCapStatus.review_tracker?.status === 'EXCEEDS_LIMIT' ? (
                    <span className="text-red-400 text-xs font-medium">
                      +{dataCapStatus.review_tracker.excess}
                    </span>
                  ) : (
                    <CheckCircle className="w-4 h-4 text-green-400" />
                  )}
                </div>
                <div className="text-xs text-slate-500">
                  <span className="text-white font-mono">{dataCapStatus.review_tracker?.our_count}</span>
                  {' / '}
                  <span className="text-white font-mono">{dataCapStatus.review_tracker?.official_max ?? '?'}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Summary Cards */}
        {report && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 md:gap-4 mb-6">
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-6">
              <div className="flex items-center gap-2 mb-1 md:mb-2">
                <Users className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
                <span className="text-slate-400 text-xs md:text-sm">Total</span>
              </div>
              <div className="text-2xl md:text-3xl font-bold text-white">{report.employee_audit?.total || 0}</div>
            </div>

            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-6">
              <div className="flex items-center gap-2 mb-1 md:mb-2">
                <CheckCircle className="w-4 h-4 md:w-5 md:h-5 text-green-400" />
                <span className="text-slate-400 text-xs md:text-sm">Passed</span>
              </div>
              <div className="text-2xl md:text-3xl font-bold text-green-400">{report.employee_audit?.passed || 0}</div>
            </div>

            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-6">
              <div className="flex items-center gap-2 mb-1 md:mb-2">
                <AlertTriangle className="w-4 h-4 md:w-5 md:h-5 text-yellow-400" />
                <span className="text-slate-400 text-xs md:text-sm">Warnings</span>
              </div>
              <div className="text-2xl md:text-3xl font-bold text-yellow-400">{report.employee_audit?.warnings || 0}</div>
            </div>

            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-6">
              <div className="flex items-center gap-2 mb-1 md:mb-2">
                <XCircle className="w-4 h-4 md:w-5 md:h-5 text-red-400" />
                <span className="text-slate-400 text-xs md:text-sm">Failed</span>
              </div>
              <div className="text-2xl md:text-3xl font-bold text-red-400">{report.employee_audit?.failed || 0}</div>
            </div>
          </div>
        )}

        {/* Data Sources Status */}
        {report && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 md:gap-4 mb-6">
            <div className={`rounded-xl border p-3 md:p-4 ${
              report.data_sources?.official_cv_stats?.set 
                ? 'bg-green-500/10 border-green-500/30' 
                : 'bg-yellow-500/10 border-yellow-500/30'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-slate-400" />
                  <span className="font-medium text-white text-sm md:text-base">CV Stats</span>
                </div>
                {report.data_sources?.official_cv_stats?.set ? (
                  <span className="text-green-400 text-xs flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> Set
                  </span>
                ) : (
                  <span className="text-yellow-400 text-xs flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Not Set
                  </span>
                )}
              </div>
              {report.data_sources?.official_cv_stats?.updated_at && (
                <p className="text-xs text-slate-500 mt-1">
                  {new Date(report.data_sources.official_cv_stats.updated_at).toLocaleDateString()}
                </p>
              )}
            </div>

            <div className={`rounded-xl border p-3 md:p-4 ${
              report.data_sources?.official_rt_stats?.set 
                ? 'bg-green-500/10 border-green-500/30' 
                : 'bg-yellow-500/10 border-yellow-500/30'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Database className="w-4 h-4 text-slate-400" />
                  <span className="font-medium text-white text-sm md:text-base">RT Stats</span>
                </div>
                {report.data_sources?.official_rt_stats?.set ? (
                  <span className="text-green-400 text-xs flex items-center gap-1">
                    <CheckCircle className="w-3 h-3" /> Set
                  </span>
                ) : (
                  <span className="text-yellow-400 text-xs flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Not Set
                  </span>
                )}
              </div>
              {report.data_sources?.official_rt_stats?.updated_at && (
                <p className="text-xs text-slate-500 mt-1">
                  {new Date(report.data_sources.official_rt_stats.updated_at).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Recommendations */}
        {report?.recommendations?.length > 0 && (
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 md:p-4 mb-6">
            <h3 className="font-semibold text-blue-400 flex items-center gap-2 mb-2 text-sm md:text-base">
              <Info className="w-4 h-4" />
              Recommendations
            </h3>
            <ul className="space-y-1">
              {report.recommendations.map((rec, i) => (
                <li key={i} className="text-xs md:text-sm text-slate-300 flex items-start gap-2">
                  <ArrowRight className="w-3 h-3 mt-0.5 text-blue-400 shrink-0" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Main Content - Stack on mobile */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Employee List */}
          <div className="lg:col-span-1 bg-slate-800/50 rounded-xl border border-slate-700/50 p-3 md:p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="font-semibold text-white text-sm md:text-base">Employee Audit Status</h3>
              <span className="text-xs text-slate-500">{filteredEmployees.length} emp</span>
            </div>
            
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-500" />
              <Input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-9 bg-slate-900/50 border-slate-700 h-9 text-sm"
              />
            </div>
            
            <div className="space-y-2 max-h-[400px] md:max-h-[600px] overflow-y-auto">
              {filteredEmployees.map((emp) => (
                <button
                  key={emp.name}
                  onClick={() => fetchEmployeeAudit(emp.name)}
                  className={`w-full text-left p-2 md:p-3 rounded-lg transition-colors ${
                    selectedEmployee === emp.name 
                      ? 'bg-blue-500/20 border border-blue-500/50' 
                      : 'bg-slate-900/50 hover:bg-slate-800/80 border border-transparent'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-white text-sm truncate">{emp.name}</span>
                    <StatusBadge status={emp.status} />
                  </div>
                  <div className="flex items-center justify-between mt-1 text-xs">
                    <span className="text-slate-500">Score: <span className="text-white">{emp.score?.toFixed(1)}</span></span>
                    {emp.discrepancy_count > 0 && (
                      <span className="text-yellow-400">{emp.discrepancy_count} issues</span>
                    )}
                  </div>
                  {emp.issues?.length > 0 && (
                    <p className="text-xs text-red-400 mt-1 truncate">{emp.issues[0]}</p>
                  )}
                </button>
              ))}
            </div>
          </div>
          
          {/* Employee Detail */}
          <div className="lg:col-span-2 bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            {auditLoading ? (
              <div className="flex items-center justify-center h-64">
                <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
              </div>
            ) : employeeAudit ? (
              <EmployeeAuditDetail audit={employeeAudit} onFixEmployee={fixSingleEmployee} />
            ) : (
              <div className="flex flex-col items-center justify-center h-64 text-slate-500">
                <FileText className="w-12 h-12 mb-4 opacity-50" />
                <p>Select an employee to view their audit details</p>
                <p className="text-sm mt-2">Click on any employee from the list to see how their score was calculated</p>
              </div>
            )}
          </div>
        </div>

        {/* Consistency Checks */}
        {report?.consistency_checks && (
          <div className="mt-8 bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <h3 className="font-semibold text-white mb-4 flex items-center gap-2">
              <ClipboardCheck className="w-5 h-5 text-blue-400" />
              Data Consistency Checks
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {report.consistency_checks.checks?.map((check, i) => (
                <div 
                  key={i} 
                  className={`p-4 rounded-lg border ${
                    check.passed 
                      ? 'bg-green-500/10 border-green-500/30' 
                      : 'bg-red-500/10 border-red-500/30'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    {check.passed ? (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400" />
                    )}
                    <span className="font-medium text-white">{check.name}</span>
                  </div>
                  <p className="text-sm text-slate-400">{check.message}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* How It Works */}
        <div className="mt-8 bg-emerald-500/10 border border-emerald-500/30 rounded-xl p-6">
          <h3 className="font-semibold text-emerald-400 mb-3 flex items-center gap-2">
            <Info className="w-5 h-5" />
            How the Audit System Works
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm text-slate-300">
            <div>
              <h4 className="font-medium text-white mb-2">1. Data Trail Verification</h4>
              <p>Every data point is traced back to its source: raw CV feedback, review mentions, and POS uploads. The system verifies that stored values match the raw data.</p>
            </div>
            <div>
              <h4 className="font-medium text-white mb-2">2. Calculation Audit</h4>
              <p>Each step of the scoring formula is independently recalculated and compared against stored values. Any discrepancy is flagged with severity level.</p>
            </div>
            <div>
              <h4 className="font-medium text-white mb-2">3. Cross-Reference Checks</h4>
              <p>The system ensures CV feedback counts match NPS records, review mentions are properly attributed, and all employees have complete data.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Official CV Stats Modal */}
      {showCVModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-md">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <h3 className="text-lg font-semibold text-white">Set Official CV Stats</h3>
              <button 
                onClick={() => setShowCVModal(false)}
                className="p-1 hover:bg-slate-700 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>
            
            <div className="p-4 space-y-4">
              <p className="text-sm text-slate-400">
                Enter the exact values from your Loyalty Voice dashboard to reconcile the data.
              </p>
              
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Promoters (9-10)</label>
                  <Input
                    type="number"
                    value={cvStats.promoters}
                    onChange={(e) => setCvStats({...cvStats, promoters: parseInt(e.target.value) || 0})}
                    className="bg-slate-900 border-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Passives (7-8)</label>
                  <Input
                    type="number"
                    value={cvStats.passives}
                    onChange={(e) => setCvStats({...cvStats, passives: parseInt(e.target.value) || 0})}
                    className="bg-slate-900 border-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Detractors (1-6)</label>
                  <Input
                    type="number"
                    value={cvStats.detractors}
                    onChange={(e) => setCvStats({...cvStats, detractors: parseInt(e.target.value) || 0})}
                    className="bg-slate-900 border-slate-700"
                  />
                </div>
                <div>
                  <label className="block text-sm text-slate-400 mb-1">Total Responses</label>
                  <Input
                    type="number"
                    value={cvStats.total_responses}
                    onChange={(e) => setCvStats({...cvStats, total_responses: parseInt(e.target.value) || 0})}
                    className="bg-slate-900 border-slate-700"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm text-slate-400 mb-1">NPS Score (%)</label>
                <Input
                  type="number"
                  step="0.01"
                  value={cvStats.nps_score}
                  onChange={(e) => setCvStats({...cvStats, nps_score: parseFloat(e.target.value) || 0})}
                  className="bg-slate-900 border-slate-700"
                />
              </div>
              
              <div className="bg-slate-900/50 rounded-lg p-3 text-sm">
                <p className="text-slate-400">
                  <strong className="text-white">Calculated Total:</strong> {cvStats.promoters + cvStats.passives + cvStats.detractors}
                </p>
                <p className="text-slate-400 mt-1">
                  <strong className="text-white">Calculated NPS:</strong> {
                    cvStats.total_responses > 0 
                      ? (((cvStats.promoters - cvStats.detractors) / cvStats.total_responses) * 100).toFixed(2)
                      : 0
                  }%
                </p>
              </div>
            </div>
            
            <div className="flex items-center gap-3 p-4 border-t border-slate-700">
              <Button
                onClick={saveOfficialCVStats}
                disabled={savingCV}
                className="flex-1 bg-blue-600 hover:bg-blue-700"
              >
                {savingCV ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                Save Stats
              </Button>
              <Button
                onClick={reconcileCVData}
                disabled={reconcilingCV || savingCV}
                className="flex-1 bg-green-600 hover:bg-green-700"
              >
                {reconcilingCV ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                Save & Reconcile
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Scheduler Modal */}
      {showSchedulerModal && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-lg">
            <div className="flex items-center justify-between p-4 border-b border-slate-700">
              <div className="flex items-center gap-2">
                <Clock className="w-5 h-5 text-purple-400" />
                <h3 className="text-lg font-semibold text-white">Automated Reconciliation</h3>
              </div>
              <button 
                onClick={() => setShowSchedulerModal(false)}
                className="p-1 hover:bg-slate-700 rounded-lg transition-colors"
              >
                <X className="w-5 h-5 text-slate-400" />
              </button>
            </div>
            
            <div className="p-4 space-y-4">
              <p className="text-sm text-slate-400">
                Schedule automatic data reconciliation to run daily. This runs: Fix All → Remove Excess → Audit.
              </p>
              
              {/* Status */}
              <div className={`rounded-lg p-3 ${schedulerStatus?.job_active ? 'bg-green-500/10 border border-green-500/30' : 'bg-slate-900/50'}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-white">
                      {schedulerStatus?.job_active ? 'Scheduler Active' : 'Scheduler Inactive'}
                    </p>
                    {schedulerStatus?.next_run && (
                      <p className="text-xs text-slate-400 mt-1">
                        Next run: {new Date(schedulerStatus.next_run).toLocaleString()}
                      </p>
                    )}
                  </div>
                  {schedulerStatus?.job_active && (
                    <CheckCircle className="w-5 h-5 text-green-400" />
                  )}
                </div>
              </div>
              
              {/* Configuration */}
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={schedulerConfig.enabled}
                      onChange={(e) => setSchedulerConfig({...schedulerConfig, enabled: e.target.checked})}
                      className="w-4 h-4 rounded border-slate-600 bg-slate-900 text-purple-500 focus:ring-purple-500"
                    />
                    <span className="text-sm text-white">Enable daily reconciliation</span>
                  </label>
                </div>
                
                <div className="flex items-center gap-3">
                  <label className="text-sm text-slate-400">Run at:</label>
                  <select
                    value={schedulerConfig.schedule_hour}
                    onChange={(e) => setSchedulerConfig({...schedulerConfig, schedule_hour: parseInt(e.target.value)})}
                    className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-white text-sm"
                  >
                    {Array.from({length: 24}, (_, i) => (
                      <option key={i} value={i}>{i.toString().padStart(2, '0')}:00</option>
                    ))}
                  </select>
                  <span className="text-sm text-slate-400">UTC</span>
                </div>
              </div>
              
              {/* Recent History */}
              {reconciliationHistory.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-sm font-medium text-white">Recent Runs</h4>
                  <div className="space-y-1 max-h-32 overflow-y-auto">
                    {reconciliationHistory.slice(0, 3).map((run, idx) => (
                      <div key={idx} className={`text-xs p-2 rounded ${run.success ? 'bg-green-500/10' : 'bg-red-500/10'}`}>
                        <div className="flex items-center justify-between">
                          <span className="text-slate-400">{new Date(run.timestamp).toLocaleString()}</span>
                          <span className={run.success ? 'text-green-400' : 'text-red-400'}>
                            {run.final_status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            
            <div className="flex items-center gap-3 p-4 border-t border-slate-700">
              <Button
                onClick={runReconciliationNow}
                disabled={runningNow}
                variant="outline"
                className="flex-1 border-purple-500/50 text-purple-400 hover:bg-purple-500/10"
              >
                {runningNow ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                Run Now
              </Button>
              <Button
                onClick={saveSchedulerConfig}
                disabled={savingScheduler}
                className="flex-1 bg-purple-600 hover:bg-purple-700"
              >
                {savingScheduler ? <RefreshCw className="w-4 h-4 mr-2 animate-spin" /> : null}
                Save Schedule
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
