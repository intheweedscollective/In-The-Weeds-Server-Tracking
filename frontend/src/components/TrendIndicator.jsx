import { TrendingUp, TrendingDown, Minus } from "lucide-react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

/**
 * TrendIndicator - Shows momentum/trend with direction and point change
 * Compares current score against rolling average of previous snapshots
 * 
 * Props:
 *   direction: "up" | "down" | "stable"
 *   change: number (point change, e.g., 3.5 or -2.1)
 *   size: "sm" | "md" | "lg"
 *   showTooltip: boolean (show detailed tooltip on hover)
 *   rollingAvg: number (for tooltip display)
 *   snapshotsUsed: number (for tooltip display)
 */
export function TrendIndicator({ 
  direction = "stable", 
  change = 0, 
  size = "md",
  showTooltip = true,
  rollingAvg = null,
  snapshotsUsed = 0,
  className = ""
}) {
  // Size configurations
  const sizes = {
    sm: { icon: "w-3 h-3", text: "text-xs", container: "gap-0.5" },
    md: { icon: "w-4 h-4", text: "text-sm", container: "gap-1" },
    lg: { icon: "w-5 h-5", text: "text-base", container: "gap-1.5" }
  };
  
  const sizeConfig = sizes[size] || sizes.md;
  
  // Color and icon based on direction
  const config = {
    up: {
      color: "text-green-400",
      bgColor: "bg-green-400/10",
      borderColor: "border-green-400/30",
      icon: TrendingUp,
      label: "Improving"
    },
    down: {
      color: "text-red-400",
      bgColor: "bg-red-400/10",
      borderColor: "border-red-400/30",
      icon: TrendingDown,
      label: "Declining"
    },
    stable: {
      color: "text-slate-400",
      bgColor: "bg-slate-400/10",
      borderColor: "border-slate-400/30",
      icon: Minus,
      label: "Stable"
    }
  };
  
  const { color, bgColor, borderColor, icon: Icon, label } = config[direction] || config.stable;
  
  // Format the change value
  const formatChange = (val) => {
    if (val === 0 || val === null || val === undefined) return "—";
    const sign = val > 0 ? "+" : "";
    return `${sign}${val.toFixed(1)}`;
  };
  
  const indicator = (
    <div 
      className={`inline-flex items-center ${sizeConfig.container} ${color} ${className}`}
      data-testid="trend-indicator"
      data-direction={direction}
    >
      <Icon className={sizeConfig.icon} />
      <span className={`font-medium ${sizeConfig.text}`}>
        {formatChange(change)}
      </span>
    </div>
  );
  
  if (!showTooltip) {
    return indicator;
  }
  
  return (
    <TooltipProvider>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <div className="cursor-help">
            {indicator}
          </div>
        </TooltipTrigger>
        <TooltipContent 
          side="top" 
          className="bg-slate-800 border-slate-700 p-3 max-w-xs"
        >
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className={`w-6 h-6 rounded-full ${bgColor} flex items-center justify-center`}>
                <Icon className={`w-4 h-4 ${color}`} />
              </div>
              <span className="font-semibold text-white">{label}</span>
            </div>
            
            <div className="text-xs text-slate-300 space-y-1">
              <div className="flex justify-between">
                <span>Change from avg:</span>
                <span className={`font-medium ${color}`}>{formatChange(change)} pts</span>
              </div>
              {rollingAvg !== null && (
                <div className="flex justify-between">
                  <span>Rolling average:</span>
                  <span className="font-medium text-white">{rollingAvg.toFixed(1)} pts</span>
                </div>
              )}
              {snapshotsUsed > 0 && (
                <div className="flex justify-between text-slate-400">
                  <span>Based on:</span>
                  <span>{snapshotsUsed} snapshot{snapshotsUsed !== 1 ? 's' : ''}</span>
                </div>
              )}
            </div>
            
            <p className="text-xs text-slate-500 pt-1 border-t border-slate-700">
              {direction === "up" && "Great progress! Keep up the momentum."}
              {direction === "down" && "Score has dipped. Focus on key metrics."}
              {direction === "stable" && "Consistent performance. Room to grow!"}
            </p>
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * TrendBadge - Compact badge version for tight spaces (like table cells)
 */
export function TrendBadge({ 
  direction = "stable", 
  change = 0,
  className = ""
}) {
  const config = {
    up: {
      color: "text-green-400",
      bg: "bg-green-400/10",
      border: "border-green-400/20",
      icon: TrendingUp
    },
    down: {
      color: "text-red-400",
      bg: "bg-red-400/10",
      border: "border-red-400/20",
      icon: TrendingDown
    },
    stable: {
      color: "text-slate-400",
      bg: "bg-slate-400/10",
      border: "border-slate-400/20",
      icon: Minus
    }
  };
  
  const { color, bg, border, icon: Icon } = config[direction] || config.stable;
  
  const formatChange = (val) => {
    if (val === 0 || Math.abs(val) < 0.1) return "—";
    const sign = val > 0 ? "+" : "";
    return `${sign}${val.toFixed(1)}`;
  };
  
  return (
    <span 
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${bg} ${border} border ${color} ${className}`}
      data-testid="trend-badge"
    >
      <Icon className="w-3 h-3" />
      {formatChange(change)}
    </span>
  );
}

/**
 * Hook to fetch momentum data for all employees
 */
export function useMomentumData(year, quarter) {
  // This would typically use React Query or SWR
  // For now, it's a placeholder that components can call
  return {
    data: null,
    loading: false,
    error: null
  };
}

export default TrendIndicator;
