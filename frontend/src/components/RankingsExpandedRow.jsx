import { MessageCircle, TrendingUp, TrendingDown, Target, ArrowUp, Edit3, Check, X } from "lucide-react";
import { Button } from "./ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { formatNumber, formatCurrency } from "../utils/formatters";

// Tier badge colors
const TIER_STYLES = {
  "Trainer": { bg: "bg-purple-100", text: "text-purple-800", border: "border-purple-200" },
  "Bartender": { bg: "bg-blue-100", text: "text-blue-800", border: "border-blue-200" },
  "A-Server": { bg: "bg-green-100", text: "text-green-800", border: "border-green-200" },
  "B-Server": { bg: "bg-yellow-100", text: "text-yellow-800", border: "border-yellow-200" },
  "C-Server": { bg: "bg-red-100", text: "text-red-800", border: "border-red-200" }
};

/**
 * RankingsExpandedRow - The expanded details view for a ranking row
 */
export const RankingsExpandedRow = ({
  employee,
  employeeDetails,
  metricRankings,
  quarterSettings,
  employeeAbove,
  totalEmployees,
  editingJobTitle,
  pendingJobTitle,
  savingJobTitle,
  onStartEditJobTitle,
  onSaveJobTitle,
  onCancelEditJobTitle,
  onPendingJobTitleChange
}) => {
  const ranks = metricRankings[employee.employee_id] || {};
  const total = totalEmployees;
  const benchmarks = quarterSettings || {};
  const tierStyle = TIER_STYLES[employee.tier_label] || { bg: "bg-slate-700", text: "text-gray-800", border: "border-gray-200" };
  
  const metrics = [
    {
      label: 'PPA',
      value: `$${(employeeDetails.ppa || 0).toFixed(0)}`,
      benchmark: `Target: $${benchmarks.benchmark_ppa || 55}`,
      rank: ranks.ppa,
      total,
      color: (employeeDetails.ppa || 0) >= (benchmarks.benchmark_ppa || 55) ? 'text-green-400' : 'text-red-400'
    },
    {
      label: 'LBW',
      value: `$${(employeeDetails.lbw_per_guest || 0).toFixed(2)}`,
      benchmark: `Target: $${benchmarks.benchmark_lbw || 8}`,
      rank: ranks.lbw,
      total,
      color: (employeeDetails.lbw_per_guest || 0) >= (benchmarks.benchmark_lbw || 8) ? 'text-green-400' : 'text-red-400'
    },
    {
      label: 'Glass',
      value: `$${(employeeDetails.glassware_per_guest || 0).toFixed(2)}`,
      benchmark: `Target: $${benchmarks.benchmark_glass || 1.25}`,
      rank: ranks.glass,
      total,
      color: (employeeDetails.glassware_per_guest || 0) >= (benchmarks.benchmark_glass || 1.25) ? 'text-green-400' : 'text-red-400'
    },
    {
      label: 'LSC',
      value: (employeeDetails.guests_per_lsc || 0).toFixed(0),
      benchmark: `Target: ≤${benchmarks.benchmark_lsc || 100}`,
      rank: ranks.lsc,
      total,
      color: (employeeDetails.guests_per_lsc || 999) <= (benchmarks.benchmark_lsc || 100) ? 'text-green-400' : 'text-red-400'
    },
    {
      label: 'RT',
      value: `+${(employeeDetails.review_tracker_bonus || 0).toFixed(1)}`,
      benchmark: `${employeeDetails.review_mentions || 0} mentions`,
      rank: null,
      total: null,
      color: 'text-green-400'
    }
  ];

  const cvScore = employeeDetails.cv_score || 0;

  return (
    <tr className="bg-slate-900">
      <td colSpan={12} className="p-0 relative">
        <div className="sticky left-0 px-3 sm:px-6 py-4 w-screen sm:w-full max-w-full overflow-hidden">
          <div className="space-y-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-lg font-serif font-bold text-slate-200">Metric Breakdown</span>
              <span className="text-sm text-slate-400">• {employee.name}</span>
            </div>
            
            {/* Metrics Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {metrics.map((m) => (
                <MetricCard key={m.label} metric={m} />
              ))}
              
              {/* Customer Voice Card - Combined Total */}
              <CustomerVoiceCard cvScore={cvScore} />
            </div>
            
            {/* Summary Row with Editable Job Title */}
            <SummaryRow
              employee={employee}
              employeeDetails={employeeDetails}
              tierStyle={tierStyle}
              totalEmployees={totalEmployees}
              editingJobTitle={editingJobTitle}
              pendingJobTitle={pendingJobTitle}
              savingJobTitle={savingJobTitle}
              onStartEditJobTitle={onStartEditJobTitle}
              onSaveJobTitle={onSaveJobTitle}
              onCancelEditJobTitle={onCancelEditJobTitle}
              onPendingJobTitleChange={onPendingJobTitleChange}
            />
            
            {/* Improvement Plan Section */}
            <ImprovementPlanSection
              employee={employee}
              employeeDetails={employeeDetails}
              employeeAbove={employeeAbove}
              benchmarks={benchmarks}
            />
          </div>
        </div>
      </td>
    </tr>
  );
};

/**
 * Individual metric card
 */
const MetricCard = ({ metric }) => (
  <div className="bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-600 min-w-0">
    <div className="text-xs font-semibold text-slate-400 uppercase mb-1 truncate">{metric.label}</div>
    <div className={`text-xl sm:text-2xl font-bold ${metric.color} truncate`}>{metric.value}</div>
    <div className="text-xs text-slate-400 mt-1 truncate">{metric.benchmark}</div>
    <div className="mt-2 pt-2 border-t border-slate-600">
      {metric.rank !== null ? (
        <span className="inline-flex items-center px-2 py-0.5 bg-blue-600 text-white rounded-full text-xs font-semibold whitespace-nowrap">
          {metric.rank}{metric.rank === 1 ? 'st' : metric.rank === 2 ? 'nd' : metric.rank === 3 ? 'rd' : 'th'}/{metric.total}
        </span>
      ) : (
        <span className="inline-flex items-center px-2 py-0.5 bg-green-600 text-white rounded-full text-xs font-semibold">
          Bonus
        </span>
      )}
    </div>
  </div>
);

/**
 * Customer Voice Card component - shows combined total
 */
const CustomerVoiceCard = ({ cvScore }) => (
  <div className="bg-slate-800 rounded-xl p-3 shadow-sm border border-slate-600 min-w-0">
    <div className="text-xs font-semibold text-slate-400 uppercase mb-1 flex items-center gap-1">
      <MessageCircle className="w-3 h-3 flex-shrink-0" />
      <span className="truncate">Cust. Voice</span>
    </div>
    <div className={`text-xl sm:text-2xl font-bold ${cvScore > 0 ? 'text-green-400' : cvScore < 0 ? 'text-red-400' : 'text-slate-400'}`}>
      {cvScore > 0 ? '+' : ''}{cvScore.toFixed(1)}
    </div>
    <div className="text-xs text-slate-400 mt-1 truncate">Combined pts</div>
    <div className="mt-2 pt-2 border-t border-slate-600">
      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
        cvScore > 0 ? 'bg-green-600 text-white' : cvScore < 0 ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-400'
      }`}>
        {cvScore > 0 ? 'Positive' : cvScore < 0 ? 'Negative' : 'Neutral'}
      </span>
    </div>
  </div>
);

/**
 * Summary row with editable job title
 */
const SummaryRow = ({
  employee,
  employeeDetails,
  tierStyle,
  totalEmployees,
  editingJobTitle,
  pendingJobTitle,
  savingJobTitle,
  onStartEditJobTitle,
  onSaveJobTitle,
  onCancelEditJobTitle,
  onPendingJobTitleChange
}) => (
  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-800 rounded-xl p-3 sm:p-4 shadow-sm border border-slate-600 mt-4">
    <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-2">
      <span className="text-xs sm:text-sm text-slate-400">Job Title:</span>
      {editingJobTitle === employee.employee_id ? (
        <div className="flex items-center gap-1">
          <Select value={pendingJobTitle} onValueChange={onPendingJobTitleChange}>
            <SelectTrigger className="w-24 sm:w-32 h-7 sm:h-8 bg-slate-700 border-slate-500 text-white text-xs sm:text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Trainer">Trainer</SelectItem>
              <SelectItem value="Bartender">Bartender</SelectItem>
              <SelectItem value="Server">Server</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            variant="ghost"
            onClick={onSaveJobTitle}
            disabled={savingJobTitle}
            className="h-7 w-7 p-0 text-green-400 hover:text-green-300 hover:bg-green-900/30"
            data-testid={`save-job-title-${employee.position}`}
          >
            {savingJobTitle ? (
              <div className="w-3 h-3 border-2 border-green-400 border-t-transparent rounded-full animate-spin" />
            ) : (
              <Check className="w-3 h-3" />
            )}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onCancelEditJobTitle}
            className="h-7 w-7 p-0 text-red-400 hover:text-red-300 hover:bg-red-900/30"
          >
            <X className="w-3 h-3" />
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-1">
          <span className={`px-2 py-0.5 rounded-full text-xs sm:text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
            {employeeDetails?.job_title || employee.job_title || 'Server'}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={onStartEditJobTitle}
            className="h-6 w-6 p-0 text-slate-400 hover:text-white hover:bg-slate-700"
            title="Edit job title"
            data-testid={`edit-job-title-${employee.position}`}
          >
            <Edit3 className="w-3 h-3" />
          </Button>
        </div>
      )}
    </div>
    <div className="flex flex-col sm:flex-row sm:items-center gap-1">
      <span className="text-xs sm:text-sm text-slate-400">Tier:</span>
      <span className={`px-2 py-0.5 rounded-full text-xs sm:text-sm font-bold ${tierStyle.bg} ${tierStyle.text}`}>
        {employee.tier_label}
      </span>
    </div>
    <div className="flex flex-col sm:flex-row sm:items-center gap-1">
      <span className="text-xs sm:text-sm text-slate-400">Bonus:</span>
      <span className="text-base sm:text-lg font-bold text-green-400">+{formatNumber(employee.bonus_points)}</span>
    </div>
    <div className="flex flex-col sm:flex-row sm:items-center gap-1">
      <span className="text-xs sm:text-sm text-slate-400">Rank:</span>
      <span className="text-base sm:text-lg font-bold text-primary">#{employee.peer_rank || employee.position}/{totalEmployees}</span>
    </div>
  </div>
);

/**
 * Improvement plan section
 */
const ImprovementPlanSection = ({ employee, employeeDetails, employeeAbove, benchmarks }) => {
  const gaps = [
    { 
      label: 'PPA', 
      current: employeeDetails.ppa || 0, 
      target: benchmarks.benchmark_ppa || 55,
      format: v => `$${v.toFixed(2)}`
    },
    { 
      label: 'LBW', 
      current: employeeDetails.lbw_per_guest || 0, 
      target: benchmarks.benchmark_lbw || 8,
      format: v => `$${v.toFixed(2)}`
    },
    { 
      label: 'Glass', 
      current: employeeDetails.glassware_per_guest || 0, 
      target: benchmarks.benchmark_glass || 1.25,
      format: v => `$${v.toFixed(2)}`
    },
    { 
      label: 'LSC', 
      current: employeeDetails.guests_per_lsc || 999, 
      target: benchmarks.benchmark_lsc || 100,
      format: v => v.toFixed(0),
      inverse: true
    }
  ];

  return (
    <div className="mt-6 bg-slate-800 rounded-xl p-5 border border-slate-600 shadow-sm">
      <div className="flex items-center gap-2 mb-4">
        <Target className="w-5 h-5 text-blue-400" />
        <span className="text-lg font-serif font-bold text-white">Improvement Plan</span>
      </div>
      
      {/* Gap Analysis vs Benchmarks */}
      <div className="mb-5">
        <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          Gap Analysis vs Benchmarks
        </h4>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {gaps.map((g) => {
            const diff = g.inverse ? g.target - g.current : g.current - g.target;
            const isGood = diff >= 0;
            return (
              <div key={g.label} className={`p-3 rounded-lg ${isGood ? 'bg-green-900/40 border border-green-500/50' : 'bg-red-900/40 border border-red-500/50'}`}>
                <div className="text-xs text-slate-300 mb-1">{g.label}</div>
                <div className={`text-lg font-bold ${isGood ? 'text-green-400' : 'text-red-400'}`}>
                  {isGood ? '+' : '-'}{g.format(Math.abs(diff))}
                </div>
                <div className="text-xs text-slate-400">
                  {isGood ? 'Above target' : `Need ${g.format(Math.abs(diff))} more`}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      
      {/* To Pass Next Employee */}
      {employeeAbove && (employee.peer_rank || 0) > 1 && (
        <ToPassSection employee={employee} employeeAbove={employeeAbove} />
      )}
    </div>
  );
};

/**
 * "To Pass" comparison section
 */
const ToPassSection = ({ employee, employeeAbove }) => (
  <div className="border-t border-slate-600 pt-4">
    <h4 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
      <ArrowUp className="w-4 h-4 text-blue-400" />
      <span className="truncate">To Pass #{(employee.peer_rank || 0) - 1} ({employeeAbove.name})</span>
    </h4>
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 sm:gap-3">
      <div className="bg-blue-900/40 rounded-lg p-2 sm:p-3 border border-blue-500/50">
        <div className="text-xs text-slate-300">Gap</div>
        <div className="text-base sm:text-lg font-bold text-blue-400">
          +{((employeeAbove.total_score || 0) - (employee.total_score || 0)).toFixed(1)}
        </div>
        <div className="text-xs text-slate-400 hidden sm:block">pts needed</div>
      </div>
      <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
        <div className="text-xs text-slate-400">PPA</div>
        <div className="text-sm font-semibold text-white">
          ${(employeeAbove.ppa || 0).toFixed(0)}
        </div>
        <div className="text-xs text-slate-500">vs ${(employee.ppa || 0).toFixed(0)}</div>
      </div>
      <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
        <div className="text-xs text-slate-400">LBW</div>
        <div className="text-sm font-semibold text-white">
          ${(employeeAbove.lbw_per_guest || 0).toFixed(2)}
        </div>
        <div className="text-xs text-slate-500">vs ${(employee.lbw_per_guest || 0).toFixed(2)}</div>
      </div>
      <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
        <div className="text-xs text-slate-400">Glass</div>
        <div className="text-sm font-semibold text-white">
          ${(employeeAbove.glassware_per_guest || 0).toFixed(2)}
        </div>
        <div className="text-xs text-slate-500">vs ${(employee.glassware_per_guest || 0).toFixed(2)}</div>
      </div>
      <div className="bg-slate-700/50 rounded-lg p-2 sm:p-3">
        <div className="text-xs text-slate-400">LSC</div>
        <div className="text-sm font-semibold text-white">
          {(employeeAbove.guests_per_lsc || 0).toFixed(0)}
        </div>
        <div className="text-xs text-slate-500">vs {(employee.guests_per_lsc || 0).toFixed(0)}</div>
      </div>
    </div>
  </div>
);

export default RankingsExpandedRow;
