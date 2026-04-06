import { X, Target } from "lucide-react";
import { Button } from "./ui/button";
import { formatCurrency, formatNumber } from "../utils/formatters";

/**
 * EmployeeDetailsModal - Displays detailed employee scoring breakdown
 * Extracted from EmployeeList.js to reduce component size
 */
export const EmployeeDetailsModal = ({ 
  employee, 
  totalEmployees, 
  onClose 
}) => {
  if (!employee) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50" data-testid="employee-details-modal">
      <div className="bg-slate-800 rounded-2xl w-full max-w-3xl max-h-[90vh] overflow-auto shadow-2xl">
        {/* Header */}
        <div className="p-6 border-b border-gray-200 sticky top-0 bg-slate-800 z-10">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-serif font-black text-primary">{employee.name}</h2>
              <p className="text-slate-400">
                Rank #{employee.peer_rank || '-'} of {totalEmployees} • {employee.performance_tier || 'Not Assessed'}
              </p>
            </div>
            <Button 
              onClick={onClose}
              variant="outline"
              size="sm"
              className="border-2"
              data-testid="close-modal-btn"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>
        
        <div className="p-6">
          {/* Total Score Summary */}
          <div className="mb-6 p-4 bg-slate-700 rounded-xl border-2 border-slate-600">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-serif font-bold text-white">Total Score</h3>
                <p className="text-sm text-slate-300">Weighted score + bonuses</p>
              </div>
              <div className="text-right">
                <div className="text-4xl font-serif font-black text-green-400">
                  {formatNumber(employee.pre_dar_score || employee.total_score || 0)}
                </div>
                <div className="text-sm text-slate-300">points</div>
              </div>
            </div>
          </div>

          {/* Scoring Breakdown by Category */}
          <ScoringBreakdown employee={employee} />

          {/* Score Summary Table */}
          <ScoreSummaryTable employee={employee} />

          {/* Customer Voice Breakdown */}
          <CustomerVoiceBreakdown employee={employee} />
          
          {/* Raw Data Section */}
          <RawDataSection employee={employee} />
        </div>
      </div>
    </div>
  );
};

/**
 * Scoring breakdown showing weighted categories
 */
const ScoringBreakdown = ({ employee }) => {
  const categories = [
    {
      label: "PPA (Per Person Average)",
      weight: "25%",
      color: "blue",
      value: employee.ppa || 0,
      score: employee.score_ppa || 0,
      bonus: employee.bonus_ppa || 0,
      maxPts: 30,
      formatValue: (v) => formatCurrency(v)
    },
    {
      label: "LSC (Guests per Signup)",
      weight: "25%",
      color: "green",
      value: employee.guests_per_lsc,
      score: employee.score_lsc || 0,
      bonus: employee.bonus_lsc || 0,
      maxPts: 30,
      formatValue: (v) => v ? `${formatNumber(v)} G/LSC` : 'N/A'
    },
    {
      label: "LBW per Guest",
      weight: "20%",
      color: "purple",
      value: employee.lbw_per_guest || 0,
      score: employee.score_lbw || 0,
      bonus: employee.bonus_lbw || 0,
      maxPts: 25,
      formatValue: (v) => formatCurrency(v)
    },
    {
      label: "Glassware per Guest",
      weight: "15%",
      color: "slate",
      value: employee.glassware_per_guest || 0,
      score: employee.score_glass || 0,
      bonus: employee.bonus_glass || 0,
      maxPts: 20,
      formatValue: (v) => formatCurrency(v)
    }
  ];

  const weightMap = { "25%": 0.25, "20%": 0.20, "15%": 0.15 };

  return (
    <div className="mb-4">
      <h4 className="font-serif font-bold text-foreground mb-4 flex items-center gap-2">
        <Target className="w-5 h-5 text-secondary" />
        Scoring Breakdown by Category
      </h4>
      
      <div className="space-y-3">
        {categories.map((cat) => {
          const weightNum = weightMap[cat.weight] || 0.25;
          const earnedPts = Math.min(cat.score, 100) * weightNum + cat.bonus;
          const percentage = (earnedPts / cat.maxPts) * 100;
          
          const colorClasses = {
            blue: { bg: "bg-blue-600", border: "border-blue-500/30", text: "text-blue-400", bar: "bg-blue-500" },
            green: { bg: "bg-green-600", border: "border-green-500/30", text: "text-green-400", bar: "bg-green-500" },
            purple: { bg: "bg-purple-600", border: "border-purple-500/30", text: "text-purple-400", bar: "bg-purple-500" },
            slate: { bg: "bg-slate-600", border: "border-slate-500/30", text: "text-slate-300", bar: "bg-slate-400" }
          };
          const colors = colorClasses[cat.color] || colorClasses.blue;
          
          return (
            <div key={cat.label} className={`p-4 bg-slate-700/50 rounded-lg border ${colors.border}`}>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="font-semibold text-white">{cat.label}</span>
                  <span className={`ml-2 text-xs ${colors.bg} text-white px-2 py-0.5 rounded-full`}>{cat.weight} weight</span>
                </div>
                <div className="text-right">
                  <span className={`font-bold ${colors.text} text-lg`}>{formatNumber(earnedPts)}</span>
                  <span className="text-slate-400 text-sm"> / {cat.maxPts} pts</span>
                </div>
              </div>
              <div className="flex items-center gap-4 text-sm">
                <span className="text-slate-200">Value: {cat.formatValue(cat.value)}</span>
                <span className="text-slate-500">|</span>
                <span className="text-slate-200">Score: {formatNumber(cat.score)}%</span>
                {cat.bonus > 0 && (
                  <>
                    <span className="text-slate-500">|</span>
                    <span className="text-green-400 font-medium">+{formatNumber(cat.bonus)} bonus</span>
                  </>
                )}
              </div>
              <div className="mt-2 h-2 bg-slate-600 rounded-full overflow-hidden">
                <div 
                  className={`h-full ${colors.bar} rounded-full transition-all`}
                  style={{ width: `${Math.min(100, percentage)}%` }}
                />
              </div>
            </div>
          );
        })}

        {/* Customer Voice - Direct Points */}
        <CustomerVoiceCategory employee={employee} />

        {/* Review Tracker Bonus */}
        {(employee.review_tracker_bonus || 0) > 0 && (
          <div className="p-4 bg-slate-700/50 rounded-lg border border-green-500/30">
            <div className="flex items-center justify-between mb-2">
              <div>
                <span className="font-semibold text-white">Review Tracker Bonus</span>
                <span className="ml-2 text-xs bg-green-600 text-white px-2 py-0.5 rounded-full">+0.2 per mention</span>
              </div>
              <div className="text-right">
                <span className="font-bold text-green-400 text-lg">+{formatNumber(employee.review_tracker_bonus || 0)}</span>
                <span className="text-slate-400 text-sm"> pts</span>
              </div>
            </div>
            <div className="text-sm text-slate-300">
              {employee.review_mentions || employee.rt_mentions || 0} mentions × 0.5 pts each (max 15 pts)
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Customer Voice category display - Combined NPS + Promoter/Detractor points as single total
 */
const CustomerVoiceCategory = ({ employee }) => {
  const cvScore = employee.cv_score || 0;
  
  return (
    <div className="p-4 bg-slate-700/50 rounded-lg border border-yellow-500/30">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="font-semibold text-white">Customer Voice</span>
          <span className="ml-2 text-xs bg-yellow-600 text-white px-2 py-0.5 rounded-full">Combined Total</span>
        </div>
        <div className="text-right">
          <span className={`font-bold text-lg ${cvScore >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
            {cvScore >= 0 ? '+' : ''}{formatNumber(cvScore)}
          </span>
          <span className="text-slate-400 text-sm"> pts</span>
        </div>
      </div>
      <div className="flex items-center gap-4 text-sm flex-wrap">
        <span className="text-green-400">{employee.cv_promoters || 0} promoters (+{((employee.cv_promoters || 0) * 0.5).toFixed(1)} pts)</span>
        <span className="text-slate-500">|</span>
        <span className="text-red-400">{employee.cv_detractors || 0} detractors ({(employee.cv_detractors || 0) * -1} pts)</span>
      </div>
      <div className="mt-2 text-xs text-slate-400">
        Formula: Promoters×0.5 + Detractors×-1 (uncapped)
      </div>
    </div>
  );
};

/**
 * Score summary table
 */
const ScoreSummaryTable = ({ employee }) => {
  const cvScore = employee.cv_score || 0;
  
  return (
    <div className="mb-6 p-4 bg-slate-700/50 rounded-xl border border-slate-600">
      <h4 className="font-serif font-bold text-white mb-3">Score Summary</h4>
      <div className="space-y-2 text-sm">
        <div className="flex justify-between py-1 border-b border-slate-600">
          <span className="text-slate-300">Weighted POS Score (PPA+LSC+LBW+Glass)</span>
          <span className="font-medium text-white">{formatNumber(employee.weighted_score || 0)}</span>
        </div>
        <div className="flex justify-between py-1 border-b border-slate-600">
          <span className="text-slate-300">Customer Voice</span>
          <span className={`font-medium ${cvScore >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>
            {cvScore >= 0 ? '+' : ''}{formatNumber(cvScore)}
          </span>
        </div>
        <div className="flex justify-between py-1 border-b border-slate-600">
          <span className="text-slate-300">Metric Bonus</span>
          <span className="font-medium text-green-400">+{formatNumber(employee.total_metric_bonus || 0)}</span>
        </div>
        <div className="flex justify-between py-1 border-b border-slate-600">
          <span className="text-slate-300">Review Tracker Bonus</span>
          <span className="font-medium text-green-400">+{formatNumber(employee.review_tracker_bonus || 0)}</span>
        </div>
        <div className="flex justify-between py-2 font-bold text-base">
          <span className="text-white">Final Score</span>
          <span className="text-green-400">{formatNumber(employee.pre_dar_score || employee.total_score || 0)}</span>
        </div>
      </div>
    </div>
  );
};

/**
 * Customer voice breakdown cards - Shows combined total prominently
 */
const CustomerVoiceBreakdown = ({ employee }) => {
  if (!(employee.cv_promoters > 0 || employee.cv_passives > 0 || employee.cv_detractors > 0)) {
    return null;
  }

  const cvScore = employee.cv_score || 0;

  return (
    <div className="mb-4">
      <h4 className="font-serif font-bold text-white mb-3">Customer Voice Breakdown</h4>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <div className="text-center p-3 bg-yellow-900/30 rounded-lg border border-yellow-500/30">
          <div className={`text-xl font-bold ${cvScore >= 0 ? 'text-yellow-400' : 'text-red-400'}`}>{cvScore >= 0 ? '+' : ''}{cvScore.toFixed(1)}</div>
          <div className="text-xs text-slate-300">Total CV Score</div>
          <div className="text-xs text-yellow-400 font-medium">Combined</div>
        </div>
        <div className="text-center p-3 bg-green-900/30 rounded-lg border border-green-500/30">
          <div className="text-xl font-bold text-green-400">{employee.cv_promoters || 0}</div>
          <div className="text-xs text-slate-300">Promoters</div>
          <div className="text-xs text-green-400 font-medium">+{((employee.cv_promoters || 0) * 0.5).toFixed(1)} pts</div>
        </div>
        <div className="text-center p-3 bg-slate-700/50 rounded-lg border border-slate-600">
          <div className="text-xl font-bold text-slate-300">{employee.cv_passives || 0}</div>
          <div className="text-xs text-slate-400">Passives</div>
          <div className="text-xs text-slate-400">0 pts</div>
        </div>
        <div className="text-center p-3 bg-red-900/30 rounded-lg border border-red-500/30">
          <div className="text-xl font-bold text-red-400">{employee.cv_detractors || 0}</div>
          <div className="text-xs text-slate-300">Detractors</div>
          <div className="text-xs text-red-400 font-medium">{(employee.cv_detractors || 0) * -1} pts</div>
        </div>
      </div>
    </div>
  );
};

/**
 * Raw input data section
 */
const RawDataSection = ({ employee }) => {
  const dataFields = [
    { label: "Guests", value: formatNumber(employee.guests || 0) },
    { label: "Net Sales", value: formatCurrency(employee.net_sales || 0) },
    { label: "LBW Total", value: formatCurrency(employee.lbw || 0) },
    { label: "Glassware", value: formatCurrency(employee.glassware_sales || 0) },
    { label: "LSC Count", value: formatNumber(employee.lsc_count || 0) },
    { label: "Review Mentions", value: formatNumber(employee.review_mentions || 0) }
  ];

  return (
    <div>
      <h4 className="font-serif font-bold text-white mb-3">Raw Input Data</h4>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {dataFields.map(({ label, value }) => (
          <div key={label} className="flex justify-between py-2 px-3 bg-slate-700/50 rounded-lg text-sm">
            <span className="text-slate-300">{label}</span>
            <span className="font-medium text-white">{value}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

export default EmployeeDetailsModal;
