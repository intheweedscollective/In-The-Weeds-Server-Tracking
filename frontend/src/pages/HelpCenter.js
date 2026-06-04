import { useState } from "react";
import { Link } from "react-router-dom";
import { 
  HelpCircle, 
  BookOpen, 
  MessageCircle, 
  ChevronDown, 
  ChevronRight,
  Upload,
  Trophy,
  Star,
  Camera,
  FileText,
  Settings,
  BarChart3,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Search,
  ExternalLink,
  Calculator,
  Users,
  Building2,
  Download,
  RefreshCw
} from "lucide-react";
import { Input } from "../components/ui/input";

// =============================================================================
// FAQ DATA - Updated with accurate scoring formulas and new features
// =============================================================================

const faqs = [
  {
    category: "Getting Started",
    icon: BookOpen,
    color: "text-blue-400",
    questions: [
      {
        q: "How do I upload employee data?",
        a: "Go to Data Uploads page, select your data type (POS Report, CV Data, or RT Data), and upload your file. The system supports XLSX, CSV, and scanned PDF formats. POS data is parsed using AI to extract metrics automatically."
      },
      {
        q: "What file formats are supported?",
        a: "POS Reports: XLSX, CSV, or scanned PDF (AI-powered OCR). Customer Voice: NPS Toolkit Server Performance Report (XLSX). Review Tracker: CSV export from ReviewTrackers dashboard."
      },
      {
        q: "How often should I upload data?",
        a: "Upload POS data bi-weekly (1st and 15th). Customer Voice and Review Tracker data can be uploaded monthly or as needed. Create snapshots to lock in scores at key intervals."
      },
      {
        q: "What is a Snapshot?",
        a: "A snapshot is a point-in-time record of all employee scores. Once created, snapshot data is locked and used for official rankings, slides, and reports. Create snapshots bi-weekly to track progress."
      }
    ]
  },
  {
    category: "Scoring Formula",
    icon: Calculator,
    color: "text-green-400",
    questions: [
      {
        q: "How is the Total Score calculated?",
        a: "Total Score = Weighted POS Score + Customer Voice + Metric Bonus + RT Bonus. The Weighted POS Score uses: PPA (25%) + LSC (25%) + LBW (20%) + Glassware (15%). Customer Voice and bonuses are added on top."
      },
      {
        q: "How does Customer Voice scoring work?",
        a: "Customer Voice = NPS%/10 + (Promoters × 1) − (Detractors × 2). The NPS% portion contributes up to ~10 pts (e.g. NPS 77% = 7.7 pts). Promoters (9-10) add +1 pt each, Detractors (1-6) subtract 2 pts each, Passives (7-8) = 0 points. UNCAPPED — exceptional service can significantly boost scores."
      },
      {
        q: "What is the Metric Bonus?",
        a: "Metric Bonus rewards exceeding benchmarks. For each metric (PPA, LSC, LBW, Glass), if you score 100-120% of benchmark, you earn 0.25 points per 1% above 100%. Maximum 5 points per metric, 20 points total."
      },
      {
        q: "How does Review Tracker bonus work?",
        a: "Each positive mention on external review platforms (Google, Yelp, TripAdvisor, etc.) earns RT bonus points. Q2+ rule: +0.33 pts per mention, capped at 20 points (~61 mentions). Q1 2026 used the legacy +0.5 pts/mention with a 15 pt cap. Upload RT data via the Data Uploads page."
      },
      {
        q: "What are the Server Tier thresholds?",
        a: "A-Server: Score ≥ 85. B-Server: Score ≥ 70 and < 85. C-Server: Score < 70. Trainers and Bartenders are displayed at the top of rankings regardless of score due to their leadership roles."
      }
    ]
  },
  {
    category: "Customer Voice",
    icon: MessageCircle,
    color: "text-purple-400",
    questions: [
      {
        q: "Where does Customer Voice data come from?",
        a: "Customer Voice data comes from Landry's Loyalty Voice surveys. Download the 'NPS Toolkit Server Performance Report' from the Loyalty Voice dashboard and upload it via Data Uploads > CV Data."
      },
      {
        q: "What counts as a Promoter vs Detractor?",
        a: "Promoter: Rating 9-10 (+1 pt each). Passive: Rating 7-8 (0 pts). Detractor: Rating 1-6 (−2 pts each). The Customer Voice score also adds NPS%/10. Q1 2026 used the legacy weights (Promoter +0.5, Detractor −1) and is preserved for historical accuracy."
      },
      {
        q: "Why is Customer Voice uncapped?",
        a: "To heavily reward exceptional guest service! An employee with many promoters can earn significant bonus points, incentivizing the team to create memorable experiences."
      }
    ]
  },
  {
    category: "Reports & Slides",
    icon: FileText,
    color: "text-amber-400",
    questions: [
      {
        q: "How do I generate Yodeck slides?",
        a: "Go to Yodeck Slides page. Choose from Leaderboard, Top 10, or Individual slides. Customize the theme and download as PNG (1920x1080) for your digital signage playlist."
      },
      {
        q: "What is the Quarterly Summary report?",
        a: "The Quarterly Summary (Reports > Quarterly Summary) shows a print-friendly overview of all Customer Voice and Metric Bonus data. Great for management reviews and quarterly meetings."
      },
      {
        q: "How do I download all slides at once?",
        a: "Currently, slides are downloaded individually. A 'Download All as ZIP' feature is planned for a future update."
      }
    ]
  },
  {
    category: "Multi-Store",
    icon: Building2,
    color: "text-cyan-400",
    questions: [
      {
        q: "How does Multi-Store work?",
        a: "The system supports all 22 Bubba Gump locations. Use the store selector in the sidebar to switch between locations. The Global Overview page shows cross-store comparisons and rankings."
      },
      {
        q: "Can I compare stores?",
        a: "Yes! Go to Global Overview to see all stores ranked by average score, top performers across the company, and regional breakdowns. Store vs Store detailed comparison is coming soon."
      }
    ]
  },
  {
    category: "Settings & Admin",
    icon: Settings,
    color: "text-slate-400",
    questions: [
      {
        q: "How do I set benchmarks?",
        a: "Go to Quarter Settings. Set benchmark values for PPA ($55 default), LBW ($8), Glassware ($1), and LSC (100 guests). These determine what 100% means for each metric."
      },
      {
        q: "How do I finalize a quarter?",
        a: "Go to Quarter Settings and click 'Finalize Quarter'. This locks all scores, applies any DAR (Disciplinary Action Record) deductions, and prepares the system for the next quarter."
      },
      {
        q: "Can I edit data after finalizing?",
        a: "No, finalized quarters are locked to preserve data integrity. Always verify all data before finalizing. You can view finalized snapshots but cannot modify them."
      },
      {
        q: "How do I add a DAR deduction?",
        a: "Edit any employee from the Rankings page. In the edit modal, you can add DAR entries with point deductions. These are applied to the pre-DAR score to calculate the final score."
      }
    ]
  }
];

// =============================================================================
// TROUBLESHOOTING DATA
// =============================================================================

const troubleshooting = [
  {
    issue: "Scores don't match my calculations",
    severity: "high",
    symptoms: ["Total score seems wrong", "Customer Voice points are off", "Metric bonus not showing"],
    solutions: [
      "Go to Scoring Audit page to verify all calculations step-by-step",
      "Check that you're using the correct formula: CV = NPS%/10 + (Promoters × 1) − (Detractors × 2)",
      "Verify benchmark settings in Quarter Settings match your expectations",
      "Use 'Fix All' button on Scoring Audit to recalculate all scores"
    ],
    link: "/scoring-audit"
  },
  {
    issue: "Upload failed or data not appearing",
    severity: "high",
    symptoms: ["File upload error", "Employees missing after upload", "Metrics showing as 0"],
    solutions: [
      "Ensure file is XLSX or CSV format (not XLS)",
      "Check that column headers match expected format (download template for reference)",
      "For POS PDFs, ensure the scan is clear and not rotated",
      "Try uploading a smaller file first to test",
      "Check the upload job status on Data Uploads page"
    ],
    link: "/data-uploads"
  },
  {
    issue: "Employee names not matching",
    severity: "medium",
    symptoms: ["CV data not attributed to employees", "Review mentions not detected", "Duplicate employees"],
    solutions: [
      "Use exact name spelling from POS report as the source of truth",
      "Check for extra spaces or special characters in names",
      "Go to Admin > Name Matching to preview and fix name mappings",
      "Edit employee to add name aliases for common variations"
    ],
    link: "/employees"
  },
  {
    issue: "Slides not downloading",
    severity: "low",
    symptoms: ["Download button not working", "Blank or corrupted PNG", "Wrong data on slide"],
    solutions: [
      "Ensure you have an active snapshot selected",
      "Try a different browser (Chrome recommended)",
      "Check that employees have valid scores (not all zeros)",
      "Refresh the page and try again"
    ],
    link: "/yodeck"
  },
  {
    issue: "Dashboard showing old data",
    severity: "medium",
    symptoms: ["Numbers haven't updated", "Missing recent uploads", "Wrong quarter displayed"],
    solutions: [
      "Check the quarter/year filter at the top of the page",
      "Verify your latest upload completed successfully on Data Uploads page",
      "Create a new snapshot to capture updated data",
      "Hard refresh the page (Ctrl+Shift+R or Cmd+Shift+R)"
    ],
    link: "/"
  },
  {
    issue: "Review Tracker data not syncing",
    severity: "medium",
    symptoms: ["RT mentions showing 0", "RT bonus not calculating", "Missing employee mentions"],
    solutions: [
      "RT data must be manually uploaded (automated sync is deprecated)",
      "Download CSV export from ReviewTrackers dashboard",
      "Upload via Data Uploads > Review Tracker Data",
      "Check that review dates fall within the current quarter"
    ],
    link: "/data-uploads"
  }
];

// =============================================================================
// QUICK LINKS
// =============================================================================

const quickLinks = [
  { label: "Upload Data", path: "/data-uploads", icon: Upload, color: "bg-blue-500" },
  { label: "View Rankings", path: "/rankings", icon: Trophy, color: "bg-green-500" },
  { label: "Scoring Audit", path: "/scoring-audit", icon: Calculator, color: "bg-amber-500" },
  { label: "Quarterly Summary", path: "/quarterly-summary", icon: FileText, color: "bg-purple-500" },
  { label: "Yodeck Slides", path: "/yodeck", icon: Download, color: "bg-pink-500" },
  { label: "Quarter Settings", path: "/settings", icon: Settings, color: "bg-slate-500" }
];

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export default function HelpCenter() {
  const [expandedCategory, setExpandedCategory] = useState("Scoring Formula");
  const [expandedQuestion, setExpandedQuestion] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeTab, setActiveTab] = useState("faq"); // "faq" or "troubleshoot"

  // Filter FAQs based on search
  const filteredFaqs = searchQuery.trim() 
    ? faqs.map(cat => ({
        ...cat,
        questions: cat.questions.filter(
          qa => qa.q.toLowerCase().includes(searchQuery.toLowerCase()) ||
                qa.a.toLowerCase().includes(searchQuery.toLowerCase())
        )
      })).filter(cat => cat.questions.length > 0)
    : faqs;

  // Filter troubleshooting based on search
  const filteredTroubleshooting = searchQuery.trim()
    ? troubleshooting.filter(
        t => t.issue.toLowerCase().includes(searchQuery.toLowerCase()) ||
             t.symptoms.some(s => s.toLowerCase().includes(searchQuery.toLowerCase())) ||
             t.solutions.some(s => s.toLowerCase().includes(searchQuery.toLowerCase()))
      )
    : troubleshooting;

  return (
    <div className="min-h-screen bg-background" data-testid="help-center-page">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
            <HelpCircle className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-3xl font-serif font-bold text-white mb-2">
            Help Center
          </h1>
          <p className="text-slate-400 max-w-xl mx-auto">
            Everything you need to know about the Staff Performance Hub.
          </p>
        </div>

        {/* Search Bar */}
        <div className="relative max-w-md mx-auto mb-8">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
          <Input
            type="text"
            placeholder="Search help topics..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-slate-800 border-slate-700 text-white placeholder:text-slate-500"
            data-testid="help-search"
          />
          {searchQuery && (
            <button 
              onClick={() => setSearchQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white"
            >
              <XCircle className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Quick Links */}
        <div className="mb-8">
          <h2 className="text-lg font-serif font-bold text-slate-200 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {quickLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className="flex flex-col items-center gap-2 p-4 bg-slate-800 rounded-xl border border-slate-700 hover:border-slate-600 hover:bg-slate-700/50 transition-all"
              >
                <div className={`w-10 h-10 rounded-full ${link.color} flex items-center justify-center`}>
                  <link.icon className="w-5 h-5 text-white" />
                </div>
                <span className="text-sm font-medium text-slate-200 text-center">{link.label}</span>
              </Link>
            ))}
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab("faq")}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === "faq" 
                ? "bg-primary text-white" 
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <BookOpen className="w-4 h-4 inline mr-2" />
            FAQ ({filteredFaqs.reduce((acc, cat) => acc + cat.questions.length, 0)})
          </button>
          <button
            onClick={() => setActiveTab("troubleshoot")}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === "troubleshoot" 
                ? "bg-amber-500 text-white" 
                : "bg-slate-800 text-slate-300 hover:bg-slate-700"
            }`}
          >
            <AlertTriangle className="w-4 h-4 inline mr-2" />
            Troubleshooting ({filteredTroubleshooting.length})
          </button>
        </div>

        {/* FAQ Tab */}
        {activeTab === "faq" && (
          <div className="space-y-4">
            {filteredFaqs.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No results found for "{searchQuery}"</p>
                <button onClick={() => setSearchQuery("")} className="text-primary mt-2 hover:underline">
                  Clear search
                </button>
              </div>
            ) : (
              filteredFaqs.map((category) => (
                <div key={category.category} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                  {/* Category Header */}
                  <button
                    onClick={() => setExpandedCategory(expandedCategory === category.category ? null : category.category)}
                    className="w-full flex items-center justify-between p-4 hover:bg-slate-700/50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center ${category.color}`}>
                        <category.icon className="w-5 h-5" />
                      </div>
                      <span className="font-serif font-bold text-white">{category.category}</span>
                      <span className="text-xs text-slate-400 bg-slate-700 px-2 py-0.5 rounded-full">
                        {category.questions.length}
                      </span>
                    </div>
                    {expandedCategory === category.category ? (
                      <ChevronDown className="w-5 h-5 text-slate-400" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-slate-400" />
                    )}
                  </button>

                  {/* Questions */}
                  {expandedCategory === category.category && (
                    <div className="border-t border-slate-700">
                      {category.questions.map((qa, idx) => (
                        <div key={qa.q} className="border-b border-slate-700/50 last:border-0">
                          <button
                            onClick={() => setExpandedQuestion(
                              expandedQuestion === `${category.category}-${idx}` 
                                ? null 
                                : `${category.category}-${idx}`
                            )}
                            className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-700/30 transition-colors"
                          >
                            <span className="font-medium text-slate-200 pr-4">{qa.q}</span>
                            {expandedQuestion === `${category.category}-${idx}` ? (
                              <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                            ) : (
                              <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                            )}
                          </button>
                          {expandedQuestion === `${category.category}-${idx}` && (
                            <div className="px-4 pb-4 text-slate-300 text-sm leading-relaxed bg-slate-700/20">
                              {qa.a}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* Troubleshooting Tab */}
        {activeTab === "troubleshoot" && (
          <div className="space-y-4">
            {filteredTroubleshooting.length === 0 ? (
              <div className="text-center py-12 text-slate-400">
                <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
                <p>No troubleshooting topics found for "{searchQuery}"</p>
                <button onClick={() => setSearchQuery("")} className="text-primary mt-2 hover:underline">
                  Clear search
                </button>
              </div>
            ) : (
              filteredTroubleshooting.map((item) => (
                <div key={item.issue} className="bg-slate-800 rounded-xl border border-slate-700 overflow-hidden">
                  <div className="p-4">
                    {/* Issue Header */}
                    <div className="flex items-start gap-3 mb-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                        item.severity === 'high' ? 'bg-red-500/20 text-red-400' :
                        item.severity === 'medium' ? 'bg-amber-500/20 text-amber-400' :
                        'bg-blue-500/20 text-blue-400'
                      }`}>
                        <AlertTriangle className="w-4 h-4" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-bold text-white">{item.issue}</h3>
                        <div className="flex flex-wrap gap-2 mt-2">
                          {item.symptoms.map((symptom) => (
                            <span key={symptom} className="text-xs bg-slate-700 text-slate-300 px-2 py-1 rounded">
                              {symptom}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    {/* Solutions */}
                    <div className="ml-11">
                      <p className="text-sm font-medium text-slate-400 mb-2">Solutions:</p>
                      <ul className="space-y-2">
                        {item.solutions.map((solution, idx) => (
                          <li key={`${item.title}-solution-${idx}`} className="flex items-start gap-2 text-sm text-slate-300">
                            <CheckCircle className="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0" />
                            <span>{solution}</span>
                          </li>
                        ))}
                      </ul>
                      
                      {item.link && (
                        <Link 
                          to={item.link}
                          className="inline-flex items-center gap-1 mt-3 text-sm text-primary hover:underline"
                        >
                          Go to related page
                          <ExternalLink className="w-3 h-3" />
                        </Link>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

        {/* Scoring Formula Quick Reference */}
        <div className="mt-10 bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-slate-700 p-6">
          <div className="flex items-center gap-3 mb-4">
            <Calculator className="w-6 h-6 text-primary" />
            <h3 className="font-serif font-bold text-lg text-white">Scoring Formula Quick Reference</h3>
          </div>
          <div className="grid md:grid-cols-2 gap-4 text-sm">
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-slate-400 mb-2">Total Score =</p>
              <p className="text-white font-mono">
                Weighted POS + Customer Voice + Metric Bonus + RT Bonus
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-slate-400 mb-2">Customer Voice =</p>
              <p className="text-white font-mono">
                NPS%/10 + (Promoters × 1) − (Detractors × 2) <span className="text-green-400">[uncapped]</span>
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-slate-400 mb-2">Weighted POS =</p>
              <p className="text-white font-mono text-xs">
                PPA×25% + LSC×25% + LBW×20% + Glass×15%
              </p>
            </div>
            <div className="bg-slate-800/50 rounded-lg p-4">
              <p className="text-slate-400 mb-2">Tier Thresholds</p>
              <p className="text-white font-mono text-xs">
                A: ≥85 | B: ≥70 | C: &lt;70
              </p>
            </div>
          </div>
          <div className="mt-4 text-center">
            <Link to="/scoring-guide" className="text-primary hover:underline text-sm inline-flex items-center gap-1">
              View full Scoring Guide
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        </div>

        {/* Contact Support */}
        <div className="mt-6 text-center">
          <p className="text-slate-400 text-sm">
            Still need help? Contact your regional manager or reach out to{" "}
            <a href="mailto:support@intheweedscollective.com" className="text-primary font-medium hover:underline">
              In the Weeds Collective
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
