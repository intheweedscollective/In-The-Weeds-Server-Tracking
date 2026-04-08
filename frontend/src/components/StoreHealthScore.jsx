import { useState, useEffect } from "react";
import { Activity, TrendingUp, TrendingDown, Minus, Target, Award, Zap } from "lucide-react";

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
          {[1, 2, 3, 4, 5].map(i => (
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

  // Order categories by weight (highest first)
  const categories = Object.values(data.categories || {}).sort((a, b) => (b.weight || 0) - (a.weight || 0));
  
  // Check for awards/achievements
  const hasAwards = data.awards && (data.awards.best_in_concept_lsc || data.awards.above_concept_ppa || data.awards.labor_efficient);

  return (
    <div className="bg-gradient-to-br from-slate-800 to-slate-900 rounded-2xl border border-slate-700 p-6" data-testid="store-health-score">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 flex items-center justify-center">
            <Activity className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <h3 className="font-bold text-white">Store Performance</h3>
            <p className="text-xs text-slate-400">{quarter} {year} Health Check</p>
          </div>
        </div>
        {hasAwards && (
          <div className="flex items-center gap-1">
            <Award className="w-5 h-5 text-amber-400" />
          </div>
        )}
      </div>

      {/* Main Health Score */}
      <div className="text-center mb-4">
        <div className={`text-5xl font-bold ${getScoreColor(data.store_health_score)}`}>
          {data.store_health_score}
        </div>
        <p className="text-sm text-slate-400 mt-1">Store Health Score</p>
      </div>

      {/* Best in Concept Badge */}
      {data.awards?.best_in_concept_lsc && (
        <div className="mb-4 p-2 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-center gap-2">
          <Award className="w-4 h-4 text-amber-400" />
          <span className="text-xs font-medium text-amber-400">Best in Concept - LSC</span>
        </div>
      )}

      {/* Category Breakdown */}
      <div className="space-y-2">
        {categories.map((cat) => (
          <div key={cat.label} className="flex items-center justify-between py-1">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              {getTrendIcon(cat.trend)}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1">
                  <span className="text-sm text-slate-300 truncate">{cat.label}</span>
                  {cat.weight && (
                    <span className="text-[10px] text-slate-500">({cat.weight}%)</span>
                  )}
                </div>
                {cat.vs_concept && (
                  <span className={`text-[10px] ${
                    cat.vs_concept.includes('+') || cat.vs_concept.includes('better') 
                      ? 'text-emerald-400' 
                      : cat.vs_concept.includes('-') || cat.vs_concept.includes('worse')
                        ? 'text-red-400'
                        : 'text-slate-500'
                  }`}>
                    vs concept: {cat.vs_concept}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {cat.best_in_concept && (
                <Award className="w-3 h-3 text-amber-400" />
              )}
              <div className={`px-2 py-0.5 rounded text-xs font-medium ${getScoreBg(cat.score)} ${getScoreColor(cat.score)}`}>
                {cat.score}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Concept Comparison Summary */}
      {data.concept_comparison && (
        <div className="mt-4 pt-3 border-t border-slate-700/50">
          <div className="grid grid-cols-3 gap-2 text-center">
            <div>
              <div className="text-xs text-slate-500">PPA</div>
              <div className={`text-sm font-medium ${data.concept_comparison.ppa?.status === 'above' ? 'text-emerald-400' : 'text-slate-400'}`}>
                ${data.concept_comparison.ppa?.store || 0}
              </div>
              <div className="text-[10px] text-slate-500">
                {data.concept_comparison.ppa?.diff_pct > 0 ? '+' : ''}{data.concept_comparison.ppa?.diff_pct}%
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">LSC</div>
              <div className={`text-sm font-medium ${data.concept_comparison.lsc_ratio?.status === 'above' ? 'text-emerald-400' : 'text-slate-400'}`}>
                {data.concept_comparison.lsc_ratio?.store || 'N/A'}
              </div>
              <div className="text-[10px] text-emerald-400">
                {data.concept_comparison.lsc_ratio?.multiplier}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-500">Labor</div>
              <div className={`text-sm font-medium ${data.concept_comparison.labor_pct?.status === 'better' ? 'text-emerald-400' : 'text-slate-400'}`}>
                {data.concept_comparison.labor_pct?.store || 0}%
              </div>
              <div className="text-[10px] text-emerald-400">
                {data.concept_comparison.labor_pct?.diff_pp > 0 ? '+' : ''}{data.concept_comparison.labor_pct?.diff_pp}pp
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="mt-3 pt-2 border-t border-slate-700/50">
        <p className="text-xs text-slate-500 text-center">
          Based on {data.employee_count} crew members
        </p>
      </div>
    </div>
  );
}
