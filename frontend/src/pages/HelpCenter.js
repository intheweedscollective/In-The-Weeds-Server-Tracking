import { useState } from "react";
import { 
  HelpCircle, 
  BookOpen, 
  Video, 
  MessageCircle, 
  ChevronDown, 
  ChevronRight,
  Upload,
  Trophy,
  Star,
  Camera,
  FileText,
  Settings,
  BarChart3
} from "lucide-react";

const faqs = [
  {
    category: "Getting Started",
    icon: BookOpen,
    questions: [
      {
        q: "How do I upload employee data?",
        a: "Go to Snapshots, click 'New Snapshot', and upload your bi-weekly CSV file. The system will automatically calculate scores and update rankings."
      },
      {
        q: "What file format should I use?",
        a: "Use the CSV template (download from Dashboard). Required columns: Employee Name, Job Title, Guests, Net Sales, Liquor Sales, Beer Sales, Wine Sales, Glassware Sales, LSC Count."
      },
      {
        q: "How often should I upload data?",
        a: "Upload bi-weekly (1st and 15th of each month) for accurate performance tracking and trend analysis."
      }
    ]
  },
  {
    category: "Scoring & Rankings",
    icon: Trophy,
    questions: [
      {
        q: "How are scores calculated?",
        a: "Total Score = PPA (25%) + LSC (25%) + LBW (20%) + Glassware (15%) + Customer Voice (15%) + Bonuses. Each metric is scored against benchmarks you set in Settings."
      },
      {
        q: "What are A, B, and C Server tiers?",
        a: "A-Server: Score ≥ 80 (default), B-Server: Score ≥ 70, C-Server: Score < 70. Trainers and Bartenders are always listed at the top regardless of score."
      },
      {
        q: "How does Customer Voice scoring work?",
        a: "Customer Voice uses your NPS score from Loyalty Voice. NPS% × 0.10 = points (max ±10 pts). 100% NPS = +10 pts, -100% NPS = -10 pts."
      },
      {
        q: "What is the Review Tracker bonus?",
        a: "Each positive mention on external review platforms (Google, Yelp, TripAdvisor) = +0.2 bonus points. Sync reviews from Settings > Integrations."
      }
    ]
  },
  {
    category: "Reviews & Reports",
    icon: Star,
    questions: [
      {
        q: "How do I sync customer reviews?",
        a: "Go to Review Tracker page and click 'Sync Reviews'. This pulls reviews from connected platforms (ReviewTrackers, Loyalty Voice) and matches employee mentions."
      },
      {
        q: "How do I generate PDF reviews?",
        a: "Go to Rankings, click the PDF icon next to any employee, or use the Reports page to batch generate reviews for the entire team."
      },
      {
        q: "What are Yodeck slides?",
        a: "Yodeck slides are display-ready images (1920x1080) showing rankings, Top 10 lists, etc. Perfect for digital signage in the break room."
      }
    ]
  },
  {
    category: "Snapshots & Analytics",
    icon: Camera,
    questions: [
      {
        q: "What is a Snapshot?",
        a: "A snapshot is a point-in-time record of all employee performance data. Create snapshots bi-weekly to track progress over the quarter."
      },
      {
        q: "How do I compare performance over time?",
        a: "Go to Analytics to see trend charts. Compare individual employees or view team averages across multiple snapshots."
      }
    ]
  },
  {
    category: "Settings & Configuration",
    icon: Settings,
    questions: [
      {
        q: "How do I set benchmarks?",
        a: "Go to Settings > Quarter Settings. Set benchmark values for PPA, LBW, Glassware, and LSC. These determine what 100% score means for each metric."
      },
      {
        q: "How do I finalize a quarter?",
        a: "At quarter end, go to Dashboard and click 'Finalize Rankings'. This locks scores, applies DAR penalties, and prepares data for the next quarter."
      },
      {
        q: "Can I edit data after finalizing?",
        a: "No, finalized quarters are locked. Double-check all data before finalizing. You can view finalized data but not modify it."
      }
    ]
  }
];

const quickLinks = [
  { label: "Upload Data", path: "/snapshots", icon: Upload, color: "bg-blue-500" },
  { label: "View Rankings", path: "/rankings", icon: Trophy, color: "bg-green-500" },
  { label: "Sync Reviews", path: "/review-tracker", icon: Star, color: "bg-yellow-500" },
  { label: "Generate Reports", path: "/yodeck", icon: FileText, color: "bg-purple-500" },
  { label: "View Analytics", path: "/analytics", icon: BarChart3, color: "bg-orange-500" },
  { label: "Quarter Settings", path: "/settings", icon: Settings, color: "bg-slate-500" }
];

export default function HelpCenter() {
  const [expandedCategory, setExpandedCategory] = useState("Getting Started");
  const [expandedQuestion, setExpandedQuestion] = useState(null);

  return (
    <div className="min-h-screen bg-paper">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
            <HelpCircle className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-3xl font-serif font-bold text-slate-800 mb-2">
            Help Center
          </h1>
          <p className="text-slate-500 max-w-xl mx-auto">
            Everything you need to know about the Bubba Gump Performance Hub. 
            Can't find what you're looking for? Contact your regional manager.
          </p>
        </div>

        {/* Quick Links */}
        <div className="mb-10">
          <h2 className="text-lg font-serif font-bold text-slate-700 mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            {quickLinks.map((link) => (
              <a
                key={link.path}
                href={link.path}
                className="flex flex-col items-center gap-2 p-4 bg-white rounded-xl border border-sand hover:shadow-md hover:-translate-y-1 transition-all"
              >
                <div className={`w-10 h-10 rounded-full ${link.color} flex items-center justify-center`}>
                  <link.icon className="w-5 h-5 text-white" />
                </div>
                <span className="text-sm font-medium text-slate-700 text-center">{link.label}</span>
              </a>
            ))}
          </div>
        </div>

        {/* FAQ Sections */}
        <div className="space-y-4">
          <h2 className="text-lg font-serif font-bold text-slate-700 mb-4">Frequently Asked Questions</h2>
          
          {faqs.map((category) => (
            <div key={category.category} className="bg-white rounded-xl border border-sand overflow-hidden">
              {/* Category Header */}
              <button
                onClick={() => setExpandedCategory(expandedCategory === category.category ? null : category.category)}
                className="w-full flex items-center justify-between p-4 hover:bg-slate-50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                    <category.icon className="w-5 h-5 text-primary" />
                  </div>
                  <span className="font-serif font-bold text-slate-800">{category.category}</span>
                  <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                    {category.questions.length} questions
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
                <div className="border-t border-sand">
                  {category.questions.map((qa, idx) => (
                    <div key={idx} className="border-b border-sand last:border-0">
                      <button
                        onClick={() => setExpandedQuestion(expandedQuestion === `${category.category}-${idx}` ? null : `${category.category}-${idx}`)}
                        className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-50 transition-colors"
                      >
                        <span className="font-medium text-slate-700 pr-4">{qa.q}</span>
                        {expandedQuestion === `${category.category}-${idx}` ? (
                          <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
                        ) : (
                          <ChevronRight className="w-4 h-4 text-slate-400 flex-shrink-0" />
                        )}
                      </button>
                      {expandedQuestion === `${category.category}-${idx}` && (
                        <div className="px-4 pb-4 text-slate-600 text-sm leading-relaxed bg-slate-50">
                          {qa.a}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Video Tutorials Placeholder */}
        <div className="mt-10 bg-gradient-to-br from-secondary to-primary rounded-xl p-6 text-white">
          <div className="flex items-start gap-4">
            <div className="w-12 h-12 rounded-full bg-white/20 flex items-center justify-center flex-shrink-0">
              <Video className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-serif font-bold text-lg mb-1">Video Tutorials Coming Soon</h3>
              <p className="text-white/80 text-sm">
                We're creating step-by-step video guides for common tasks. 
                Check back soon or contact your regional manager for live training.
              </p>
            </div>
          </div>
        </div>

        {/* Contact Support */}
        <div className="mt-6 text-center">
          <p className="text-slate-500 text-sm">
            Still need help? Contact{" "}
            <a href="mailto:support@bubbagump.com" className="text-primary font-medium hover:underline">
              support@bubbagump.com
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
