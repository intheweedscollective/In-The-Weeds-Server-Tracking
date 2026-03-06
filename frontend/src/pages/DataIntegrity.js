import { useState, useEffect, useCallback } from "react";
import { ShieldCheck, AlertTriangle, CheckCircle, XCircle, RefreshCw, Trash2, Database, FileWarning, Users, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import { Button } from "../components/ui/button";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const StatusBadge = ({ status }) => {
  if (status === "healthy") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-green-500/20 text-green-400 text-sm font-medium">
        <CheckCircle className="w-4 h-4" />
        Healthy
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-yellow-500/20 text-yellow-400 text-sm font-medium">
      <AlertTriangle className="w-4 h-4" />
      Needs Attention
    </span>
  );
};

const IntegrityCard = ({ title, icon: Icon, children, status }) => (
  <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
    <div className="flex items-center justify-between mb-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${status === "error" ? "bg-red-500/20" : status === "warning" ? "bg-yellow-500/20" : "bg-green-500/20"}`}>
          <Icon className={`w-5 h-5 ${status === "error" ? "text-red-400" : status === "warning" ? "text-yellow-400" : "text-green-400"}`} />
        </div>
        <h3 className="font-semibold text-white">{title}</h3>
      </div>
      {status === "error" && <XCircle className="w-5 h-5 text-red-400" />}
      {status === "warning" && <AlertTriangle className="w-5 h-5 text-yellow-400" />}
      {status === "ok" && <CheckCircle className="w-5 h-5 text-green-400" />}
    </div>
    {children}
  </div>
);

export default function DataIntegrity() {
  const [summary, setSummary] = useState(null);
  const [fullReport, setFullReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState({});

  const fetchSummary = useCallback(async () => {
    try {
      const response = await axios.get(`${API}/v2/admin/data-integrity/summary`);
      setSummary(response.data);
    } catch (error) {
      toast.error("Failed to fetch integrity summary");
    }
  }, []);

  const runFullCheck = async () => {
    setRunning(prev => ({ ...prev, fullCheck: true }));
    try {
      const response = await axios.get(`${API}/v2/admin/data-integrity/check`);
      setFullReport(response.data);
      toast.success(`Integrity check complete - ${response.data.issues_found} issues found`);
    } catch (error) {
      toast.error("Failed to run integrity check");
    } finally {
      setRunning(prev => ({ ...prev, fullCheck: false }));
    }
  };

  const removeDuplicates = async (dryRun = true) => {
    setRunning(prev => ({ ...prev, duplicates: true }));
    try {
      const response = await axios.post(`${API}/v2/admin/data-integrity/remove-duplicates?dry_run=${dryRun}`);
      if (dryRun) {
        toast.info(`Found ${response.data.duplicates_found} duplicate reviews`);
      } else {
        toast.success(`Removed ${response.data.duplicates_removed} duplicate reviews`);
        fetchSummary();
      }
    } catch (error) {
      toast.error("Failed to remove duplicates");
    } finally {
      setRunning(prev => ({ ...prev, duplicates: false }));
    }
  };

  const flagInvalidCV = async (dryRun = true) => {
    setRunning(prev => ({ ...prev, invalidCV: true }));
    try {
      const response = await axios.post(`${API}/v2/admin/data-integrity/flag-invalid-cv?dry_run=${dryRun}`);
      if (dryRun) {
        toast.info(`Found ${response.data.missing_found} CV entries without server names`);
      } else {
        toast.success(`Flagged ${response.data.flagged_count} invalid CV entries`);
        fetchSummary();
      }
    } catch (error) {
      toast.error("Failed to flag invalid CV");
    } finally {
      setRunning(prev => ({ ...prev, invalidCV: false }));
    }
  };

  const deleteInvalidCV = async () => {
    if (!window.confirm("Are you sure you want to delete all CV feedback entries without server names? This cannot be undone.")) {
      return;
    }
    
    setRunning(prev => ({ ...prev, deleteCV: true }));
    try {
      const response = await axios.delete(`${API}/v2/admin/data-integrity/invalid-cv-feedback`);
      toast.success(`Deleted ${response.data.deleted_count} invalid CV entries`);
      fetchSummary();
      runFullCheck();
    } catch (error) {
      toast.error("Failed to delete invalid CV feedback");
    } finally {
      setRunning(prev => ({ ...prev, deleteCV: false }));
    }
  };

  const recalculateNPS = async () => {
    setRunning(prev => ({ ...prev, recalculate: true }));
    try {
      const response = await axios.post(`${API}/v2/admin/data-integrity/recalculate-cv-nps`);
      toast.success(`Recalculated NPS for ${response.data.employees_processed} employees`);
      fetchSummary();
    } catch (error) {
      toast.error("Failed to recalculate NPS");
    } finally {
      setRunning(prev => ({ ...prev, recalculate: false }));
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await fetchSummary();
      setLoading(false);
    };
    init();
  }, [fetchSummary]);

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <div className="p-3 bg-blue-500/20 rounded-xl">
              <ShieldCheck className="w-8 h-8 text-blue-400" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-white">Data Integrity Panel</h1>
              <p className="text-slate-400">Admin controls for data accuracy verification</p>
            </div>
          </div>
          
          <div className="flex items-center gap-3">
            {summary && <StatusBadge status={summary.status} />}
            <Button
              onClick={runFullCheck}
              disabled={running.fullCheck}
              className="bg-blue-600 hover:bg-blue-700"
            >
              {running.fullCheck ? (
                <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <ShieldCheck className="w-4 h-4 mr-2" />
              )}
              Run Full Check
            </Button>
          </div>
        </div>

        {/* Summary Cards */}
        {summary && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <div className="flex items-center gap-3 mb-4">
                <MessageSquare className="w-5 h-5 text-blue-400" />
                <span className="text-slate-400">Customer Reviews</span>
              </div>
              <div className="text-3xl font-bold text-white">{summary.reviews?.total || 0}</div>
              <div className="text-sm text-slate-500">Total reviews in system</div>
            </div>

            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <div className="flex items-center gap-3 mb-4">
                <Users className="w-5 h-5 text-green-400" />
                <span className="text-slate-400">CV Feedback</span>
              </div>
              <div className="text-3xl font-bold text-white">{summary.cv_feedback?.total || 0}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className="text-sm text-green-400">{summary.cv_feedback?.valid || 0} valid</span>
                {summary.cv_feedback?.invalid > 0 && (
                  <span className="text-sm text-red-400">{summary.cv_feedback?.invalid} invalid</span>
                )}
              </div>
              <div className="text-sm text-slate-500 mt-1">
                {summary.cv_feedback?.attribution_rate}% attribution rate
              </div>
            </div>

            <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
              <div className="flex items-center gap-3 mb-4">
                <Database className="w-5 h-5 text-purple-400" />
                <span className="text-slate-400">CV NPS Records</span>
              </div>
              <div className="text-3xl font-bold text-white">{summary.cv_nps?.total || 0}</div>
              <div className="text-sm text-slate-500">Aggregated NPS records</div>
            </div>
          </div>
        )}

        {/* Action Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          <IntegrityCard
            title="Review Duplicates"
            icon={FileWarning}
            status={fullReport?.checks?.review_duplicates?.duplicates_found > 0 ? "warning" : "ok"}
          >
            <div className="space-y-3">
              {fullReport?.checks?.review_duplicates && (
                <div className="text-sm text-slate-400">
                  <div>Total Reviews: {fullReport.checks.review_duplicates.total_reviews}</div>
                  <div>Duplicates Found: {fullReport.checks.review_duplicates.duplicates_found}</div>
                </div>
              )}
              <div className="flex gap-2">
                <Button
                  onClick={() => removeDuplicates(true)}
                  disabled={running.duplicates}
                  variant="outline"
                  size="sm"
                  className="border-slate-600 text-slate-300"
                >
                  Check for Duplicates
                </Button>
                <Button
                  onClick={() => removeDuplicates(false)}
                  disabled={running.duplicates}
                  variant="destructive"
                  size="sm"
                >
                  Remove Duplicates
                </Button>
              </div>
            </div>
          </IntegrityCard>

          <IntegrityCard
            title="CV Server Attribution"
            icon={Users}
            status={summary?.cv_feedback?.invalid > 0 ? "error" : "ok"}
          >
            <div className="space-y-3">
              {summary?.cv_feedback && (
                <div className="text-sm text-slate-400">
                  <div>Valid Entries: {summary.cv_feedback.valid}</div>
                  <div className={summary.cv_feedback.invalid > 0 ? "text-red-400" : ""}>
                    Invalid (No Server): {summary.cv_feedback.invalid}
                  </div>
                  <div>Attribution Rate: {summary.cv_feedback.attribution_rate}%</div>
                </div>
              )}
              <div className="flex gap-2">
                <Button
                  onClick={() => flagInvalidCV(true)}
                  disabled={running.invalidCV}
                  variant="outline"
                  size="sm"
                  className="border-slate-600 text-slate-300"
                >
                  Check Invalid
                </Button>
                <Button
                  onClick={deleteInvalidCV}
                  disabled={running.deleteCV || summary?.cv_feedback?.invalid === 0}
                  variant="destructive"
                  size="sm"
                >
                  <Trash2 className="w-4 h-4 mr-1" />
                  Delete Invalid
                </Button>
              </div>
            </div>
          </IntegrityCard>

          <IntegrityCard
            title="NPS Calculation Validation"
            icon={CheckCircle}
            status={fullReport?.checks?.cv_nps_validation?.mismatches > 0 ? "warning" : "ok"}
          >
            <div className="space-y-3">
              {fullReport?.checks?.cv_nps_validation && (
                <div className="text-sm text-slate-400">
                  <div>Records Validated: {fullReport.checks.cv_nps_validation.validated}</div>
                  <div className={fullReport.checks.cv_nps_validation.mismatches > 0 ? "text-yellow-400" : ""}>
                    Mismatches: {fullReport.checks.cv_nps_validation.mismatches}
                  </div>
                </div>
              )}
              <Button
                onClick={recalculateNPS}
                disabled={running.recalculate}
                className="bg-green-600 hover:bg-green-700"
                size="sm"
              >
                {running.recalculate ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <RefreshCw className="w-4 h-4 mr-2" />
                )}
                Recalculate All NPS
              </Button>
            </div>
          </IntegrityCard>

          <IntegrityCard
            title="Orphaned Records"
            icon={Database}
            status={fullReport?.checks?.orphaned_records?.orphaned_count > 0 ? "warning" : "ok"}
          >
            <div className="space-y-3">
              {fullReport?.checks?.orphaned_records && (
                <div className="text-sm text-slate-400">
                  <div>Orphaned CV NPS Records: {fullReport.checks.orphaned_records.orphaned_count}</div>
                  {fullReport.checks.orphaned_records.orphaned_details?.length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs text-slate-500">Orphaned names:</div>
                      <div className="text-xs text-yellow-400">
                        {fullReport.checks.orphaned_records.orphaned_details.slice(0, 5).join(", ")}
                      </div>
                    </div>
                  )}
                </div>
              )}
              <div className="text-xs text-slate-500">
                Orphaned records are CV NPS entries for employees not in the system.
              </div>
            </div>
          </IntegrityCard>
        </div>

        {/* Full Report Details */}
        {fullReport && (
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-6">
            <h3 className="font-semibold text-white mb-4">Full Integrity Report</h3>
            <div className="text-sm text-slate-400 space-y-2">
              <div>Timestamp: {new Date(fullReport.timestamp).toLocaleString()}</div>
              <div>Status: {fullReport.status}</div>
              <div className={fullReport.issues_found > 0 ? "text-yellow-400" : "text-green-400"}>
                Issues Found: {fullReport.issues_found}
              </div>
              
              {fullReport.checks?.cv_nps_validation?.mismatch_details?.length > 0 && (
                <div className="mt-4">
                  <div className="font-semibold text-white mb-2">NPS Mismatches:</div>
                  <div className="bg-slate-900/50 rounded-lg p-3 max-h-48 overflow-y-auto">
                    {fullReport.checks.cv_nps_validation.mismatch_details.map((m, i) => (
                      <div key={i} className="text-xs mb-2 border-b border-slate-700 pb-2">
                        <div className="font-medium text-white">{m.employee} ({m.quarter} {m.year})</div>
                        <div className="text-red-400">
                          Stored: P={m.stored.promoters}, D={m.stored.detractors}, NPS={m.stored.nps}
                        </div>
                        <div className="text-green-400">
                          Actual: P={m.actual.promoters}, D={m.actual.detractors}, NPS={m.actual.nps}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Instructions */}
        <div className="mt-8 bg-blue-500/10 border border-blue-500/30 rounded-xl p-6">
          <h3 className="font-semibold text-blue-400 mb-3">Data Accuracy Guidelines</h3>
          <ul className="text-sm text-slate-400 space-y-2">
            <li>• <strong>CV Feedback</strong>: All entries MUST have a server name. Entries without attribution cannot be counted.</li>
            <li>• <strong>Reviews</strong>: Duplicate reviews are identified by content hash and should be removed.</li>
            <li>• <strong>NPS Validation</strong>: NPS records should exactly match the sum of promoters/detractors in raw feedback.</li>
            <li>• <strong>Verification Mode</strong>: Compare stored data against fresh scrape before finalizing scores.</li>
          </ul>
        </div>
      </div>
    </div>
  );
}
