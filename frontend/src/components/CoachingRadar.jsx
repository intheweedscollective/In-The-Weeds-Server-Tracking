import { useState, useEffect } from "react";
import { Radar, AlertTriangle, DollarSign, TrendingUp, ChevronRight, Users } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CoachingRadar({ quarter = "Q1", year = 2026 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v2/insights/coaching-radar?quarter=${quarter}&year=${year}`);
        const json = await res.json();
        setData(json);
      } catch (error) {
        console.error("Failed to fetch coaching radar:", error);
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [quarter, year]);

  if (loading) {
    return (
      <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700 p-6 animate-pulse">
        <div className="h-8 bg-slate-700 rounded w-48 mb-4"></div>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-24 bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const opportunities = data.coaching_opportunities || [];
  const topOpportunities = opportunities.slice(0, 4);

  const getCategoryIcon = (category) => {
    switch (category) {
      case "Glassware": return "🍷";
      case "LBW": return "🍹";
      case "Loyalty": return "⭐";
      case "PPA": return "💰";
      default: return "📊";
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700 p-6" data-testid="coaching-radar">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/20 flex items-center justify-center">
            <Radar className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h3 className="font-bold text-white">Coaching Radar</h3>
            <p className="text-xs text-slate-400">High Impact Opportunities</p>
          </div>
        </div>
        <div className="flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full">
          <AlertTriangle className="w-3 h-3" />
          <span>{data.employees_needing_coaching} need coaching</span>
        </div>
      </div>

      {/* Total Potential */}
      <div className="bg-gradient-to-r from-emerald-500/10 to-cyan-500/10 rounded-xl p-4 mb-4 border border-emerald-500/20">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-slate-400">Monthly Revenue Potential</p>
            <p className="text-2xl font-bold text-emerald-400">
              {formatCurrency(data.total_potential_monthly_revenue)}
            </p>
          </div>
          <div className="w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center">
            <DollarSign className="w-6 h-6 text-emerald-400" />
          </div>
        </div>
      </div>

      {/* Top Opportunities */}
      <div className="space-y-3">
        {topOpportunities.map((opp, idx) => (
          <div
            key={opp.employee_name || idx}
            className="bg-slate-800/50 rounded-xl p-3 border border-slate-700/50 hover:border-amber-500/30 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-slate-700 flex items-center justify-center text-sm">
                  {idx + 1}
                </div>
                <div>
                  <p className="font-medium text-white text-sm">{opp.employee_name}</p>
                  <p className="text-xs text-slate-400">{opp.tier || "Server"}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold text-emerald-400">
                  +{formatCurrency(opp.total_potential_monthly)}/mo
                </p>
              </div>
            </div>
            
            {/* Top opportunity for this employee */}
            {opp.opportunities?.[0] && (
              <div className="flex items-center gap-2 text-xs">
                <span className="text-lg">{getCategoryIcon(opp.opportunities[0].category)}</span>
                <span className="text-slate-400">{opp.opportunities[0].description}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      {opportunities.length > 4 && (
        <div className="mt-4 pt-4 border-t border-slate-700/50">
          <button className="w-full flex items-center justify-center gap-2 text-sm text-cyan-400 hover:text-cyan-300 transition-colors">
            <span>View all {opportunities.length} opportunities</span>
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  );
}
