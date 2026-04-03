import { CheckSquare, Pencil, Eye, Trash2 } from "lucide-react";
import { Button } from "./ui/button";
import { formatCurrency, formatNumber } from "../utils/formatters";

/**
 * EmployeeCard - Individual employee card component
 * Extracted from EmployeeList.js for better maintainability
 */
export const EmployeeCard = ({
  employee,
  selectMode,
  isSelected,
  onToggleSelection,
  onEdit,
  onViewDetails,
  onDelete
}) => {
  const performance = getPerformanceLevelLocal(employee.performance_tier, employee.total_score || employee.pre_dar_score);
  
  // Use V2 fields with fallbacks to V1
  const score = employee.pre_dar_score || employee.total_score || employee.cumulative_score || 0;
  const ppa = employee.ppa || 0;
  const lbwPerGuest = employee.lbw_per_guest || employee.pplbw || 0;
  const glassPerGuest = employee.glassware_per_guest || employee.gpg || 0;
  const guestsPerLsc = employee.guests_per_lsc;
  const cvScore = employee.cv_score || 0;
  
  // New bonus metrics
  const rtBonus = employee.review_tracker_bonus || 0;
  const metricBonus = employee.total_metric_bonus || 0;
  const qrScans = (employee.yelp_clicks || 0) + (employee.google_clicks || 0);
  
  return (
    <div 
      className={`bubba-card relative ${selectMode && isSelected ? 'ring-2 ring-blue-500 bg-blue-900/20' : ''}`} 
      data-testid={`employee-card-${employee.id}`}
      onClick={selectMode ? onToggleSelection : undefined}
      style={selectMode ? { cursor: 'pointer' } : {}}
    >
      {/* Checkbox overlay in select mode */}
      {selectMode && (
        <div className="absolute top-2 left-2 z-10">
          <div 
            className={`w-6 h-6 rounded border-2 flex items-center justify-center transition-colors ${
              isSelected 
                ? 'bg-blue-600 border-blue-600 text-white' 
                : 'bg-slate-700 border-slate-500 hover:border-blue-400'
            }`}
            data-testid={`employee-checkbox-${employee.id}`}
          >
            {isSelected && <CheckSquare className="w-4 h-4" />}
          </div>
        </div>
      )}
      
      <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
      <div className={`p-5 pt-7 ${selectMode ? 'pl-10' : ''}`}>
        {/* Header with name and performance badge */}
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="text-lg font-serif font-bold text-foreground" data-testid={`employee-name-${employee.id}`}>
              {employee.name}
            </h3>
            <p className="text-sm text-slate-400 capitalize" data-testid={`employee-job-title-${employee.id}`}>
              {employee.job_title || 'Server'}
            </p>
            <p className="text-slate-500 text-xs" data-testid={`employee-rank-${employee.id}`}>
              Rank: #{employee.peer_rank || '-'}
            </p>
          </div>
          <span className={`performance-badge ${performance.class}`} data-testid={`employee-performance-${employee.id}`}>
            {performance.text}
          </span>
        </div>
        
        {/* Metrics Grid */}
        <MetricsGrid 
          score={score}
          ppa={ppa}
          lbwPerGuest={lbwPerGuest}
          glassPerGuest={glassPerGuest}
          guestsPerLsc={guestsPerLsc}
          cvScore={cvScore}
          rtBonus={rtBonus}
          metricBonus={metricBonus}
          qrScans={qrScans}
        />
        
        {/* Actions - hidden in select mode */}
        {!selectMode && (
          <div className="flex gap-2">
            <Button 
              onClick={(e) => { e.stopPropagation(); onEdit(); }}
              variant="outline" 
              size="sm" 
              className="flex-1 border-2 border-blue-200 hover:bg-blue-50"
              data-testid={`edit-employee-btn-${employee.id}`}
            >
              <Pencil className="w-4 h-4 mr-2" />
              Edit
            </Button>
            <Button 
              onClick={(e) => { e.stopPropagation(); onViewDetails(); }}
              variant="outline" 
              size="sm" 
              className="flex-1 border-2"
              data-testid={`view-details-btn-${employee.id}`}
            >
              <Eye className="w-4 h-4 mr-2" />
              Details
            </Button>
            <Button 
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              variant="destructive" 
              size="sm"
              data-testid={`delete-employee-btn-${employee.id}`}
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * Metrics grid showing the 9 key metrics (expanded from 6)
 * Row 1: Score, PPA, LBW/G
 * Row 2: Glass/G, G/LSC, CV Score  
 * Row 3: RT Bonus, Metric Bonus, QR Scans
 */
const MetricsGrid = ({ score, ppa, lbwPerGuest, glassPerGuest, guestsPerLsc, cvScore, rtBonus, metricBonus, qrScans }) => (
  <div className="grid grid-cols-3 gap-2 mb-4">
    {/* Row 1: Core metrics */}
    <div className="text-center p-2 bg-red-50 rounded-lg border border-red-100">
      <div className="text-lg font-serif font-bold text-primary">{formatNumber(score)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">Score</div>
    </div>
    <div className="text-center p-2 bg-blue-50 rounded-lg border border-blue-100">
      <div className="text-sm font-serif font-bold text-secondary">{formatCurrency(ppa)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">PPA</div>
    </div>
    <div className="text-center p-2 bg-purple-50 rounded-lg border border-purple-100">
      <div className="text-sm font-serif font-bold text-purple-700">{formatCurrency(lbwPerGuest)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">LBW/G</div>
    </div>
    
    {/* Row 2: Per-guest metrics */}
    <div className="text-center p-2 bg-slate-600 rounded-lg border border-slate-500">
      <div className="text-sm font-serif font-bold text-slate-100">{formatCurrency(glassPerGuest)}</div>
      <div className="text-[10px] text-slate-300 font-semibold uppercase">Glass/G</div>
    </div>
    <div className="text-center p-2 bg-green-50 rounded-lg border border-green-100">
      <div className="text-sm font-serif font-bold text-green-700">{guestsPerLsc ? formatNumber(guestsPerLsc) : 'N/A'}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">G/LSC</div>
    </div>
    <div className="text-center p-2 bg-yellow-50 rounded-lg border border-yellow-100">
      <div className="text-sm font-serif font-bold text-yellow-700">{cvScore > 0 ? '+' : ''}{formatNumber(cvScore)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">CV</div>
    </div>
    
    {/* Row 3: Bonus metrics & QR */}
    <div className="text-center p-2 bg-teal-50 rounded-lg border border-teal-100">
      <div className="text-sm font-serif font-bold text-teal-700">{rtBonus > 0 ? '+' : ''}{formatNumber(rtBonus)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">RT Bonus</div>
    </div>
    <div className="text-center p-2 bg-orange-50 rounded-lg border border-orange-100">
      <div className="text-sm font-serif font-bold text-orange-700">{metricBonus > 0 ? '+' : ''}{formatNumber(metricBonus)}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">Metric+</div>
    </div>
    <div className="text-center p-2 bg-indigo-50 rounded-lg border border-indigo-100">
      <div className="text-sm font-serif font-bold text-indigo-700">{qrScans || 0}</div>
      <div className="text-[10px] text-slate-400 font-semibold uppercase">QR Scans</div>
    </div>
  </div>
);

/**
 * Get performance level styling based on tier or score
 */
const getPerformanceLevelLocal = (tier, score) => {
  if (tier) {
    const tierMap = {
      "Top Performer": { text: "Top Performer", class: "performance-excellent" },
      "Above Average": { text: "Above Average", class: "performance-above-average" },
      "Below Average": { text: "Below Average", class: "performance-satisfactory" },
      "Needs Immediate Improvement": { text: "Needs Improvement", class: "performance-below" }
    };
    return tierMap[tier] || { text: tier, class: "performance-satisfactory" };
  }
  // Fallback for legacy data
  if (!score) return { text: "Not Assessed", class: "performance-below" };
  if (score >= 90) return { text: "Excellent", class: "performance-excellent" };
  if (score >= 80) return { text: "Above Average", class: "performance-above-average" };
  if (score >= 70) return { text: "Satisfactory", class: "performance-satisfactory" };
  if (score >= 60) return { text: "Needs Improvement", class: "performance-needs-improvement" };
  return { text: "Below Expectations", class: "performance-below" };
};

export default EmployeeCard;
