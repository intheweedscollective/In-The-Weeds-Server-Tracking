import { HelpCircle } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";

/**
 * Contextual help tooltips that link to relevant Help Center sections.
 * Use these throughout the app to provide quick help without leaving the page.
 * 
 * Usage:
 *   <HelpTooltip topic="cv-scoring" />
 *   <HelpTooltip topic="metric-bonus" size="sm" />
 */

// Help topic definitions with content and links
const HELP_TOPICS = {
  // Scoring topics
  "cv-scoring": {
    title: "Customer Voice Scoring",
    content: "CV = (Promoters × 0.5) - (Detractors × 1). This score is uncapped to reward exceptional service.",
    link: "/help#scoring-formula",
    linkText: "Learn more about scoring"
  },
  "metric-bonus": {
    title: "Metric Bonus",
    content: "Earn 0.25 pts for each 1% above benchmark (100-120% range). Max 5 pts per metric, 20 pts total.",
    link: "/help#scoring-formula",
    linkText: "View full formula"
  },
  "rt-bonus": {
    title: "Review Tracker Bonus",
    content: "Each positive mention on external reviews = +0.5 pts. Maximum 15 pts (30 mentions).",
    link: "/help#scoring-formula",
    linkText: "How RT works"
  },
  "weighted-pos": {
    title: "Weighted POS Score",
    content: "PPA (25%) + LSC (25%) + LBW (20%) + Glassware (15%) = 85% of base score.",
    link: "/scoring-guide",
    linkText: "View Scoring Guide"
  },
  "total-score": {
    title: "Total Score",
    content: "Weighted POS + Customer Voice + Metric Bonus + RT Bonus. DAR deductions applied separately.",
    link: "/scoring-guide",
    linkText: "Full breakdown"
  },
  
  // Tier topics
  "server-tiers": {
    title: "Server Tiers",
    content: "A-Server: ≥85 pts. B-Server: ≥70 pts. C-Server: <70 pts. Trainers & Bartenders listed first.",
    link: "/help#scoring-formula",
    linkText: "Tier details"
  },
  
  // Data topics
  "snapshot": {
    title: "Snapshots",
    content: "A snapshot locks employee scores at a point in time. Create bi-weekly to track progress.",
    link: "/help#getting-started",
    linkText: "About snapshots"
  },
  "pos-upload": {
    title: "POS Data Upload",
    content: "Upload Excel, CSV, or scanned PDF. AI extracts metrics automatically. Use bi-weekly uploads.",
    link: "/data-uploads",
    linkText: "Go to uploads"
  },
  "cv-upload": {
    title: "Customer Voice Upload",
    content: "Download NPS Toolkit Server Performance Report from Loyalty Voice and upload here.",
    link: "/data-uploads",
    linkText: "Upload CV data"
  },
  "rt-upload": {
    title: "Review Tracker Upload",
    content: "Export CSV from ReviewTrackers dashboard. Employee mentions are matched automatically.",
    link: "/data-uploads",
    linkText: "Upload RT data"
  },
  
  // Metric explanations
  "ppa": {
    title: "PPA (Per Person Average)",
    content: "Net Sales ÷ Guests. Higher is better. Benchmark default: $55.",
    link: "/scoring-guide#pos-metrics",
    linkText: "PPA details"
  },
  "lsc": {
    title: "LSC (Loyalty Scans)",
    content: "Guests ÷ LSC Count. Lower is better (more scans per guest). Benchmark: 100.",
    link: "/scoring-guide#pos-metrics",
    linkText: "LSC details"
  },
  "lbw": {
    title: "LBW (Liquor/Beer/Wine)",
    content: "Beverage sales per guest. Higher is better. Benchmark default: $8.",
    link: "/scoring-guide#pos-metrics",
    linkText: "LBW details"
  },
  "glassware": {
    title: "Glassware",
    content: "Glassware sales per guest. Higher is better. Benchmark default: $1.",
    link: "/scoring-guide#pos-metrics",
    linkText: "Glassware details"
  },
  
  // Feature explanations
  "yodeck": {
    title: "Yodeck Slides",
    content: "Generate 1920x1080 PNG slides for digital signage. Choose leaderboard, top 10, or individual formats.",
    link: "/help#reports-slides",
    linkText: "Slide options"
  },
  "quarterly-summary": {
    title: "Quarterly Summary",
    content: "Print-friendly report showing Customer Voice and Metric Bonus data for all employees.",
    link: "/quarterly-summary",
    linkText: "View report"
  },
  "finalize-quarter": {
    title: "Finalize Quarter",
    content: "Locks all scores and applies DAR deductions. Cannot be undone. Verify all data first!",
    link: "/help#settings-admin",
    linkText: "Finalization guide"
  },
  "dar": {
    title: "DAR (Disciplinary Action Record)",
    content: "Point deductions for policy violations. Applied after pre-DAR score is calculated.",
    link: "/help#settings-admin",
    linkText: "DAR info"
  },
  
  // Audit topics
  "scoring-audit": {
    title: "Scoring Audit",
    content: "Verify all employee calculations are correct. Use 'Fix All' to recalculate if needed.",
    link: "/scoring-audit",
    linkText: "Run audit"
  },
  "data-reconciliation": {
    title: "Data Reconciliation",
    content: "Match local data with official dashboard numbers. Set official stats to ensure accuracy.",
    link: "/scoring-audit",
    linkText: "Reconcile data"
  }
};

export function HelpTooltip({ 
  topic, 
  size = "md", 
  className = "",
  showLink = true 
}) {
  const helpData = HELP_TOPICS[topic];
  
  if (!helpData) {
    console.warn(`HelpTooltip: Unknown topic "${topic}"`);
    return null;
  }
  
  const iconSize = size === "sm" ? "w-3.5 h-3.5" : size === "lg" ? "w-5 h-5" : "w-4 h-4";
  
  return (
    <TooltipProvider>
      <Tooltip delayDuration={200}>
        <TooltipTrigger asChild>
          <button 
            className={`inline-flex items-center justify-center text-slate-400 hover:text-primary transition-colors ${className}`}
            aria-label={`Help: ${helpData.title}`}
          >
            <HelpCircle className={iconSize} />
          </button>
        </TooltipTrigger>
        <TooltipContent 
          side="top" 
          className="max-w-xs bg-slate-800 border-slate-700 p-3"
        >
          <div className="space-y-2">
            <p className="font-semibold text-white text-sm">{helpData.title}</p>
            <p className="text-slate-300 text-xs leading-relaxed">{helpData.content}</p>
            {showLink && helpData.link && (
              <Link 
                to={helpData.link}
                className="inline-block text-xs text-primary hover:underline mt-1"
              >
                {helpData.linkText} →
              </Link>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

/**
 * Inline help text with optional tooltip
 * Use for labels that need explanation
 * 
 * Usage:
 *   <HelpLabel label="Customer Voice" topic="cv-scoring" />
 */
export function HelpLabel({ label, topic, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      {label}
      <HelpTooltip topic={topic} size="sm" />
    </span>
  );
}

export default HelpTooltip;
