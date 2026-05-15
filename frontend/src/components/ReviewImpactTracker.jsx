import { useState, useEffect } from "react";
import { Star, DollarSign, MessageSquare, ThumbsUp, TrendingUp, Sparkles } from "lucide-react";

const API_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

export default function ReviewImpactTracker({ quarter = "Q1", year = 2026 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v2/insights/review-impact?quarter=${quarter}&year=${year}`);
        const json = await res.json();
        setData(json);
      } catch (error) {
        console.error("Failed to fetch review impact:", error);
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
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-16 bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const impactList = data.review_impact || [];
  const topPerformers = impactList.slice(0, 5);
  const totals = data.totals || {};

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  const getSatisfactionColor = (color) => {
    switch (color) {
      case "emerald": return "text-emerald-400 bg-emerald-500/20";
      case "blue": return "text-blue-400 bg-blue-500/20";
      case "amber": return "text-amber-400 bg-amber-500/20";
      case "red": return "text-red-400 bg-red-500/20";
      default: return "text-slate-400 bg-slate-500/20";
    }
  };

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700 p-6 overflow-hidden" data-testid="review-impact-tracker">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-pink-500/20 flex items-center justify-center flex-shrink-0">
            <Sparkles className="w-5 h-5 text-purple-400" />
          </div>
          <div className="min-w-0">
            <h3 className="font-bold text-white truncate">Guest Impact</h3>
            <p className="text-xs text-slate-400 truncate">Revenue Influence from Reviews</p>
          </div>
        </div>
      </div>

      {/* Total Impact Banner */}
      <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-xl p-3 mb-4 border border-purple-500/20">
        <div className="grid grid-cols-3 gap-1 text-center">
          <div className="min-w-0 px-1">
            <p className="text-lg md:text-xl font-bold text-purple-400">{totals.total_mentions || 0}</p>
            <p className="text-xs text-slate-400">RT Mentions</p>
          </div>
          <div className="min-w-0 px-1">
            <p className="text-lg md:text-xl font-bold text-pink-400">{totals.total_promoters || 0}</p>
            <p className="text-xs text-slate-400">CV Promoters</p>
          </div>
          <div className="min-w-0 px-1">
            <p className="text-sm md:text-lg font-bold text-emerald-400">{formatCurrency(totals.total_revenue_influence || 0)}</p>
            <p className="text-xs text-slate-400">Influence</p>
          </div>
        </div>
      </div>

      {/* Top Influencers */}
      <div className="space-y-2 overflow-hidden">
        <p className="text-xs text-slate-400 uppercase tracking-wide mb-2">Top Guest Influencers</p>
        {topPerformers.map((emp, idx) => (
          <div
            key={emp.employee_name || idx}
            className="flex items-center justify-between py-2 px-3 rounded-lg bg-slate-800/50 hover:bg-slate-800 transition-colors gap-2"
          >
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                idx === 0 ? 'bg-amber-500 text-white' :
                idx === 1 ? 'bg-slate-400 text-white' :
                idx === 2 ? 'bg-amber-700 text-white' :
                'bg-slate-700 text-slate-300'
              }`}>
                {idx + 1}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-white truncate">{emp.employee_name}</p>
                <div className="flex items-center gap-2 text-xs">
                  <span className="flex items-center gap-1 text-slate-400">
                    <MessageSquare className="w-3 h-3 flex-shrink-0" />
                    {emp.review_mentions}
                  </span>
                  <span className="flex items-center gap-1 text-slate-400">
                    <ThumbsUp className="w-3 h-3 flex-shrink-0" />
                    {emp.cv_promoters}
                  </span>
                </div>
              </div>
            </div>
            <div className="text-right flex-shrink-0">
              <p className="text-sm font-bold text-emerald-400 whitespace-nowrap">
                {formatCurrency(emp.total_revenue_influence)}
              </p>
              <span className={`text-xs px-1.5 py-0.5 rounded whitespace-nowrap ${getSatisfactionColor(emp.satisfaction_color)}`}>
                {emp.satisfaction_level}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Methodology Note */}
      <div className="mt-4 pt-4 border-t border-slate-700/50">
        <p className="text-xs text-slate-500 text-center truncate">
          {formatCurrency(data.methodology?.revenue_per_mention || 550)}/mention + {formatCurrency(data.methodology?.revenue_per_promoter || 800)}/promoter
        </p>
      </div>
    </div>
  );
}
