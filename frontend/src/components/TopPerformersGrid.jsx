import { Trophy, Medal, Award } from "lucide-react";
import { formatNumber, formatCurrency } from "../utils/formatters";
import { getDisplayFirstName } from "../utils/displayName";

// V2 Metrics Configuration
const V2_METRICS = {
  ppa: { label: 'PPA', format: 'currency', higherBetter: true },
  lbw_per_guest: { label: 'LBW/Guest', format: 'currency', higherBetter: true },
  glassware_per_guest: { label: 'Glass/Guest', format: 'currency', higherBetter: true },
  guests_per_lsc: { label: 'Guests/LSC', format: 'number', higherBetter: false },
  cv_score: { label: 'Customer Voice', format: 'number', higherBetter: true },
  pre_dar_score: { label: 'Total Score', format: 'number', higherBetter: true },
};

/**
 * Top performers grid showing top 10 by each metric
 */
export const TopPerformersGrid = ({ employees }) => {
  // Get top employees for a specific metric
  const getTopEmployees = (metric, limit = 10) => {
    const config = V2_METRICS[metric];
    if (!config) return [];
    const valid = employees.filter((e) => {
      const v = e[metric];
      if (v == null) return false;
      if (typeof v === 'number' && v === 0) return false;
      if (metric === 'guests_per_lsc' && (e.lsc_count == null || e.lsc_count === 0)) return false;
      return true;
    });

    const sorted = [...valid].sort((a, b) => {
      if (!config.higherBetter) return (a[metric] || 0) - (b[metric] || 0);
      return (b[metric] || 0) - (a[metric] || 0);
    });

    return sorted.slice(0, limit);
  };

  // Format metric value for display
  const formatMetricValue = (metric, value) => {
    if (value == null) return "N/A";
    const config = V2_METRICS[metric];
    if (!config) return formatNumber(value);
    
    switch (config.format) {
      case 'currency':
        return formatCurrency(value);
      default:
        return formatNumber(value);
    }
  };

  // Get icon for rank position
  const getMetricIcon = (rank) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-600" />;
    return <span className="text-sm font-bold text-slate-400">#{rank}</span>;
  };

  const metrics = Object.keys(V2_METRICS);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {metrics.map(metric => {
        const topEmployees = getTopEmployees(metric, 5);
        const config = V2_METRICS[metric];
        
        return (
          <div key={metric} className="bubba-card">
            <div className="p-4 border-b border-slate-700">
              <h3 className="font-serif font-bold text-foreground">{config.label}</h3>
              <p className="text-xs text-slate-400">
                {config.higherBetter ? 'Higher is better' : 'Lower is better'}
              </p>
            </div>
            <div className="p-4">
              <div className="space-y-2">
                {topEmployees.map((emp, idx) => (
                  <div key={emp.id} className="flex items-center justify-between py-2 px-3 bg-slate-700/30 rounded-lg">
                    <div className="flex items-center gap-3">
                      <div className="w-8 flex justify-center">
                        {getMetricIcon(idx + 1)}
                      </div>
                      <span className="text-sm font-medium text-white truncate max-w-[120px]">
                        {getDisplayFirstName(emp)}
                      </span>
                    </div>
                    <span className="text-sm font-bold text-primary">
                      {formatMetricValue(metric, emp[metric])}
                    </span>
                  </div>
                ))}
                {topEmployees.length === 0 && (
                  <p className="text-sm text-slate-400 text-center py-4">No data</p>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Top 10 overall performers card
 */
export const TopOverallCard = ({ employees }) => {
  const topOverall = [...employees]
    .filter(e => e.pre_dar_score != null)
    .sort((a, b) => (b.pre_dar_score || 0) - (a.pre_dar_score || 0))
    .slice(0, 10);

  const getMetricIcon = (rank) => {
    if (rank === 1) return <Trophy className="w-6 h-6 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-6 h-6 text-gray-400" />;
    if (rank === 3) return <Award className="w-6 h-6 text-amber-600" />;
    return <span className="text-lg font-bold text-slate-400">#{rank}</span>;
  };

  return (
    <div className="bubba-card">
      <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
      <div className="p-6 border-b border-slate-700">
        <div className="flex items-center gap-3">
          <Trophy className="w-6 h-6 text-yellow-500" />
          <h2 className="text-xl font-serif font-bold text-foreground">Top 10 Overall</h2>
        </div>
      </div>
      <div className="p-6">
        <div className="space-y-3">
          {topOverall.map((emp, idx) => (
            <div 
              key={emp.id} 
              className={`flex items-center justify-between py-3 px-4 rounded-xl ${
                idx < 3 ? 'bg-gradient-to-r from-yellow-500/10 to-amber-500/10 border border-yellow-500/20' : 'bg-slate-700/30'
              }`}
            >
              <div className="flex items-center gap-4">
                <div className="w-10 flex justify-center">
                  {getMetricIcon(idx + 1)}
                </div>
                <div>
                  <span className="font-semibold text-white">{getDisplayFirstName(emp)}</span>
                  <span className="ml-2 text-xs text-slate-400">{emp.tier_label}</span>
                </div>
              </div>
              <div className="text-right">
                <span className="text-xl font-bold text-primary">{formatNumber(emp.pre_dar_score)}</span>
                <span className="text-xs text-slate-400 ml-1">pts</span>
              </div>
            </div>
          ))}
          {topOverall.length === 0 && (
            <p className="text-center text-slate-400 py-8">No employee data available</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default TopPerformersGrid;
