import { useState, useEffect } from "react";
import { Activity, TrendingUp, TrendingDown, Minus, Target } from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function StoreHealthScore({ quarter = "Q1", year = 2026 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v2/insights/store-health?quarter=${quarter}&year=${year}`);
        const json = await res.json();
        setData(json);
      } catch (error) {
        console.error("Failed to fetch store health:", error);
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
        <div className="h-16 bg-slate-700 rounded w-24 mb-6"></div>
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-8 bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  if (!data) return null;

  const getScoreColor = (score) => {
    if (score >= 85) return "text-emerald-400";
    if (score >= 70) return "text-blue-400";
    if (score >= 55) return "text-amber-400";
    return "text-red-400";
  };

  const getScoreBg = (score) => {
    if (score >= 85) return "bg-emerald-500/20";
    if (score >= 70) return "bg-blue-500/20";
    if (score >= 55) return "bg-amber-500/20";
    return "bg-red-500/20";
  };

  const getTrendIcon = (trend) => {
    if (trend === "up") return <TrendingUp className="w-4 h-4 text-emerald-400" />;
    if (trend === "down") return <TrendingDown className="w-4 h-4 text-red-400" />;
    return <Minus className="w-4 h-4 text-slate-400" />;
  };

  const categories = Object.values(data.categories || {});

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700 p-6" data-testid="store-health-score">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h3 className="font-bold text-white">Store Performance Index</h3>
            <p className="text-xs text-slate-400">{quarter} {year} Health Check</p>
          </div>
        </div>
        <Target className="w-5 h-5 text-slate-500" />
      </div>

      {/* Main Health Score */}
      <div className="text-center mb-6">
        <div className={`text-5xl font-bold ${getScoreColor(data.store_health_score)}`}>
          {data.store_health_score}
        </div>
        <p className="text-sm text-slate-400 mt-1">Store Health Score</p>
      </div>

      {/* Category Breakdown */}
      <div className="space-y-3">
        {categories.map((cat) => (
          <div key={cat.label} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {getTrendIcon(cat.trend)}
              <span className="text-sm text-slate-300">{cat.label}</span>
            </div>
            <div className="flex items-center gap-2">
              <div className={`px-2 py-0.5 rounded text-xs font-medium ${getScoreBg(cat.score)} ${getScoreColor(cat.score)}`}>
                {cat.score}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="mt-4 pt-4 border-t border-slate-700/50">
        <p className="text-xs text-slate-500 text-center">
          Based on {data.employee_count} crew members
        </p>
      </div>
    </div>
  );
}
