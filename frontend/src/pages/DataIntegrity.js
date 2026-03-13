import { useState, useEffect, useCallback } from "react";
import { ShieldCheck, AlertTriangle, CheckCircle, XCircle, RefreshCw, Trash2, Database, Users, Star, MessageSquare } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";

export default function DataIntegrity() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState({});
  const [quarter] = useState("Q1");
  const [year] = useState(2026);

  const fetchStats = useCallback(async () => {
    try {
      // Fetch basic stats
      const [employeesRes, cvRes, rtRes] = await Promise.all([
        api.get(`/v2/employees?quarter=${quarter}&year=${year}`),
        api.get(`/v2/cv/stats?quarter=${quarter}&year=${year}`).catch(() => ({ data: {} })),
        api.get(`/v2/reviews/stats?quarter=${quarter}&year=${year}`).catch(() => ({ data: {} }))
      ]);
      
      setStats({
        employees: employeesRes.data?.length || 0,
        cv: {
          responses: cvRes.data?.total_responses || 0,
          promoters: cvRes.data?.promoter_count || 0,
          detractors: cvRes.data?.detractor_count || 0,
          nps: cvRes.data?.avg_nps || 0
        },
        rt: {
          mentions: rtRes.data?.total_mentions || 0,
          employees: rtRes.data?.top_mentioned?.length || 0
        }
      });
    } catch (error) {
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
                  <span className="text-slate-400">NPS Score:</span>
                  <span className={`font-bold ${stats?.cv?.nps >= 70 ? 'text-green-400' : stats?.cv?.nps >= 50 ? 'text-yellow-400' : 'text-red-400'}`}>
                    {stats?.cv?.nps || 0}%
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
