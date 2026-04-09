import { useState } from "react";
import { 
  FileSpreadsheet, 
  Download, 
  Upload, 
  CheckCircle, 
  ExternalLink,
  ChevronRight,
  ChevronDown,
  AlertTriangle,
  Info,
  ArrowRight,
  Monitor,
  Printer,
  Star,
  MessageSquare,
  Users,
  HelpCircle
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Link } from "react-router-dom";

export default function DataUploadTutorial() {
  const [expandedSection, setExpandedSection] = useState("pos");
  
  const toggleSection = (section) => {
    setExpandedSection(expandedSection === section ? null : section);
  };

  const TutorialStep = ({ number, title, children, icon: Icon }) => (
    <div className="flex gap-4 mb-6">
      <div className="flex-shrink-0">
        <div className="w-10 h-10 rounded-full bg-primary/20 text-primary flex items-center justify-center font-bold text-lg">
          {number}
        </div>
      </div>
      <div className="flex-1">
        <h4 className="font-semibold text-white mb-2 flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-primary" />}
          {title}
        </h4>
        <div className="text-slate-300 text-sm space-y-2">
          {children}
        </div>
      </div>
    </div>
  );

  const ExternalLinkButton = ({ href, children }) => (
    <a 
      href={href} 
      target="_blank" 
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-primary hover:text-primary/80 underline"
    >
      {children}
      <ExternalLink className="w-3 h-3" />
    </a>
  );

  const ProTip = ({ children }) => (
    <div className="flex gap-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mt-3">
      <Info className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
      <p className="text-sm text-amber-200">{children}</p>
    </div>
  );

  const Warning = ({ children }) => (
    <div className="flex gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg mt-3">
      <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
      <p className="text-sm text-red-200">{children}</p>
    </div>
  );

  const SectionHeader = ({ id, icon: Icon, title, subtitle, isExpanded, colorClass = "blue" }) => {
    const colorMap = {
      blue: "bg-blue-500/20 text-blue-400",
      green: "bg-green-500/20 text-green-400",
      yellow: "bg-yellow-500/20 text-yellow-400",
      purple: "bg-purple-500/20 text-purple-400"
    };
    
    return (
      <button
        onClick={() => toggleSection(id)}
        className="w-full flex items-center justify-between p-4 bg-slate-800/50 rounded-xl border border-slate-700/50 hover:bg-slate-800 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2.5 rounded-xl ${colorMap[colorClass]}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="text-left">
            <h3 className="font-semibold text-white">{title}</h3>
            <p className="text-xs text-slate-400">{subtitle}</p>
          </div>
        </div>
        {isExpanded ? (
          <ChevronDown className="w-5 h-5 text-slate-400" />
        ) : (
          <ChevronRight className="w-5 h-5 text-slate-400" />
        )}
      </button>
    );
  };

  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="w-16 h-16 rounded-2xl bg-primary/20 flex items-center justify-center mx-auto mb-4">
            <FileSpreadsheet className="w-8 h-8 text-primary" />
          </div>
          <h1 className="text-3xl font-serif font-bold text-white mb-2">
            Data Upload Tutorial
          </h1>
          <p className="text-slate-400 max-w-xl mx-auto">
            Step-by-step guide to downloading reports from Landry's systems and uploading them to the Performance Hub
          </p>
        </div>

        {/* Quick Links */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          <button
            onClick={() => { setExpandedSection("pos"); document.getElementById("pos-section")?.scrollIntoView({ behavior: "smooth" }); }}
            className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl hover:bg-blue-500/20 transition-colors"
          >
            <FileSpreadsheet className="w-5 h-5 text-blue-400 mx-auto mb-1" />
            <span className="text-xs text-blue-300 font-medium">POS Report</span>
          </button>
          <button
            onClick={() => { setExpandedSection("nps"); document.getElementById("nps-section")?.scrollIntoView({ behavior: "smooth" }); }}
            className="p-3 bg-green-500/10 border border-green-500/30 rounded-xl hover:bg-green-500/20 transition-colors"
          >
            <Star className="w-5 h-5 text-green-400 mx-auto mb-1" />
            <span className="text-xs text-green-300 font-medium">NPS/CV Report</span>
          </button>
          <button
            onClick={() => { setExpandedSection("rt"); document.getElementById("rt-section")?.scrollIntoView({ behavior: "smooth" }); }}
            className="p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-xl hover:bg-yellow-500/20 transition-colors"
          >
            <MessageSquare className="w-5 h-5 text-yellow-400 mx-auto mb-1" />
            <span className="text-xs text-yellow-300 font-medium">ReviewTrackers</span>
          </button>
          <button
            onClick={() => { setExpandedSection("scanned"); document.getElementById("scanned-section")?.scrollIntoView({ behavior: "smooth" }); }}
            className="p-3 bg-purple-500/10 border border-purple-500/30 rounded-xl hover:bg-purple-500/20 transition-colors"
          >
            <Printer className="w-5 h-5 text-purple-400 mx-auto mb-1" />
            <span className="text-xs text-purple-300 font-medium">Scanned PDF</span>
          </button>
        </div>

        {/* Prerequisites */}
        <div className="bg-slate-800/30 rounded-xl border border-slate-700/50 p-4 mb-6">
          <h3 className="font-semibold text-white mb-3 flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            Before You Begin
          </h3>
          <ul className="space-y-2 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              Make sure Quarter Settings are configured (Settings → Quarter Settings)
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              Have login credentials ready for: Aloha Back Office, Loyalty Voice, ReviewTrackers
            </li>
            <li className="flex items-start gap-2">
              <span className="text-green-400">✓</span>
              Select the correct Quarter (Q1, Q2, etc.) and Year before uploading
            </li>
          </ul>
        </div>

        {/* Section 1: POS Report */}
        <div id="pos-section" className="mb-4">
          <SectionHeader
            id="pos"
            icon={FileSpreadsheet}
            title="1. POS Report (Aloha Server Sales Detail)"
            subtitle="Sales, PPA, LBW, Glassware, LSC data"
            isExpanded={expandedSection === "pos"}
            colorClass="blue"
          />
          
          {expandedSection === "pos" && (
            <div className="mt-4 p-6 bg-slate-800/30 rounded-xl border border-slate-700/50">
              <h4 className="text-lg font-semibold text-white mb-4">Downloading from Aloha Back Office</h4>
              
              <TutorialStep number={1} title="Access Aloha Back Office" icon={Monitor}>
                <p>Log in to the Aloha Back Office system at your store's terminal or through the Landry's portal.</p>
                <ProTip>You'll need manager-level access to export reports.</ProTip>
              </TutorialStep>

              <TutorialStep number={2} title="Navigate to Reports" icon={FileSpreadsheet}>
                <p>Go to: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">Reports → Labor → Server Sales Detail</span></p>
                <p className="mt-2">Alternative path: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">Reports → Sales → Server Performance</span></p>
              </TutorialStep>

              <TutorialStep number={3} title="Set Date Range" icon={CheckCircle}>
                <p>Select the full quarter date range:</p>
                <ul className="list-disc list-inside ml-2 mt-2 space-y-1">
                  <li><strong>Q1:</strong> January 1 - March 31</li>
                  <li><strong>Q2:</strong> April 1 - June 30</li>
                  <li><strong>Q3:</strong> July 1 - September 30</li>
                  <li><strong>Q4:</strong> October 1 - December 31</li>
                </ul>
              </TutorialStep>

              <TutorialStep number={4} title="Export to Excel" icon={Download}>
                <p>Click <strong>Export</strong> or <strong>Download</strong> and select <strong>Excel (.xlsx)</strong> format.</p>
                <p className="mt-2">The file should contain columns for:</p>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Employee Name</span>
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Net Sales</span>
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Guest Count</span>
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Liquor/Beer/Wine</span>
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Glassware</span>
                  <span className="text-xs bg-slate-700 px-2 py-1 rounded">Loyalty$ (LSC)</span>
                </div>
              </TutorialStep>

              <TutorialStep number={5} title="Upload to Performance Hub" icon={Upload}>
                <p>In this app, go to <Link to="/data-uploads" className="text-primary hover:underline">Data Uploads</Link> and:</p>
                <ol className="list-decimal list-inside ml-2 mt-2 space-y-1">
                  <li>Select correct Quarter and Year</li>
                  <li>Click "Choose file" under <strong>POS Sales Report</strong></li>
                  <li>Select your downloaded .xlsx file</li>
                  <li>Click <strong>Upload & Process</strong></li>
                </ol>
                <Warning>Make sure Quarter Settings exist before uploading. Go to Settings first if needed.</Warning>
              </TutorialStep>

              <div className="mt-6 pt-4 border-t border-slate-700">
                <Link to="/data-uploads">
                  <Button className="w-full bg-blue-600 hover:bg-blue-700">
                    <Upload className="w-4 h-4 mr-2" />
                    Go to Data Uploads
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Section 2: NPS/Customer Voice */}
        <div id="nps-section" className="mb-4">
          <SectionHeader
            id="nps"
            icon={Star}
            title="2. NPS/Customer Voice Report"
            subtitle="Server performance surveys from Loyalty Voice"
            isExpanded={expandedSection === "nps"}
            colorClass="green"
          />
          
          {expandedSection === "nps" && (
            <div className="mt-4 p-6 bg-slate-800/30 rounded-xl border border-slate-700/50">
              <h4 className="text-lg font-semibold text-white mb-4">Downloading from Loyalty Voice (NPS Toolkit)</h4>
              
              <TutorialStep number={1} title="Access Loyalty Voice Portal" icon={Monitor}>
                <p>Log in to the Landry's Loyalty Voice dashboard:</p>
                <p className="mt-2">
                  <ExternalLinkButton href="https://nps.landrysinc.com">
                    nps.landrysinc.com
                  </ExternalLinkButton>
                </p>
                <ProTip>Use your Landry's corporate credentials (same as email login).</ProTip>
              </TutorialStep>

              <TutorialStep number={2} title="Navigate to Server Performance" icon={FileSpreadsheet}>
                <p>Go to: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">Reports → Server Performance</span></p>
                <p className="mt-2">Or: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">NPS Toolkit → Export</span></p>
              </TutorialStep>

              <TutorialStep number={3} title="Filter by Location & Date" icon={CheckCircle}>
                <p>Select your store location (Las Vegas - 0337) and the quarter date range.</p>
                <p className="mt-2">Make sure to include:</p>
                <ul className="list-disc list-inside ml-2 mt-2 space-y-1">
                  <li>Server Name</li>
                  <li>NPS Score</li>
                  <li>Promoters / Passives / Detractors counts</li>
                  <li>Survey responses</li>
                </ul>
              </TutorialStep>

              <TutorialStep number={4} title="Export to Excel" icon={Download}>
                <p>Click <strong>Export to Excel</strong> or <strong>Download CSV</strong>.</p>
                <p className="mt-2">The exported file should contain survey-level data with server attribution.</p>
              </TutorialStep>

              <TutorialStep number={5} title="Upload to Performance Hub" icon={Upload}>
                <p>In this app, go to <Link to="/data-uploads" className="text-primary hover:underline">Data Uploads</Link> and:</p>
                <ol className="list-decimal list-inside ml-2 mt-2 space-y-1">
                  <li>Select correct Quarter and Year</li>
                  <li>Click "Choose file" under <strong>Customer Voice (NPS)</strong></li>
                  <li>Select your downloaded file</li>
                  <li>Click <strong>Upload & Process</strong></li>
                </ol>
              </TutorialStep>

              <div className="mt-6 pt-4 border-t border-slate-700">
                <Link to="/data-uploads">
                  <Button className="w-full bg-green-600 hover:bg-green-700">
                    <Upload className="w-4 h-4 mr-2" />
                    Go to Data Uploads
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Section 3: ReviewTrackers */}
        <div id="rt-section" className="mb-4">
          <SectionHeader
            id="rt"
            icon={MessageSquare}
            title="3. ReviewTrackers Export"
            subtitle="Public reviews from Google, Yelp, TripAdvisor"
            isExpanded={expandedSection === "rt"}
            colorClass="yellow"
          />
          
          {expandedSection === "rt" && (
            <div className="mt-4 p-6 bg-slate-800/30 rounded-xl border border-slate-700/50">
              <h4 className="text-lg font-semibold text-white mb-4">Downloading from ReviewTrackers</h4>
              
              <TutorialStep number={1} title="Access ReviewTrackers" icon={Monitor}>
                <p>Log in to ReviewTrackers:</p>
                <p className="mt-2">
                  <ExternalLinkButton href="https://www.reviewtrackers.com">
                    reviewtrackers.com
                  </ExternalLinkButton>
                </p>
              </TutorialStep>

              <TutorialStep number={2} title="Select Your Location" icon={CheckCircle}>
                <p>From the dashboard, select your Bubba Gump location (Las Vegas).</p>
                <p className="mt-2">Set the date filter to the quarter you're uploading.</p>
              </TutorialStep>

              <TutorialStep number={3} title="Navigate to Reviews Export" icon={FileSpreadsheet}>
                <p>Go to: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">Reviews → Export</span></p>
                <p className="mt-2">Or: <span className="font-mono bg-slate-700 px-2 py-0.5 rounded">Reports → Download Reviews</span></p>
              </TutorialStep>

              <TutorialStep number={4} title="Export to CSV" icon={Download}>
                <p>Select <strong>CSV</strong> format and include:</p>
                <ul className="list-disc list-inside ml-2 mt-2 space-y-1">
                  <li>Review Date</li>
                  <li>Review Text (for name extraction)</li>
                  <li>Star Rating</li>
                  <li>Source (Google, Yelp, etc.)</li>
                </ul>
                <ProTip>The system uses AI to detect employee names mentioned in review text.</ProTip>
              </TutorialStep>

              <TutorialStep number={5} title="Upload to Performance Hub" icon={Upload}>
                <p>In this app, go to <Link to="/data-uploads" className="text-primary hover:underline">Data Uploads</Link> and:</p>
                <ol className="list-decimal list-inside ml-2 mt-2 space-y-1">
                  <li>Select correct Quarter and Year</li>
                  <li>Click "Choose file" under <strong>Public Reviews (ReviewTrackers)</strong></li>
                  <li>Select your downloaded .csv file</li>
                  <li>Click <strong>Upload & Process</strong></li>
                </ol>
              </TutorialStep>

              <div className="mt-6 pt-4 border-t border-slate-700">
                <Link to="/data-uploads">
                  <Button className="w-full bg-yellow-600 hover:bg-yellow-700">
                    <Upload className="w-4 h-4 mr-2" />
                    Go to Data Uploads
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* Section 4: Scanned PDF */}
        <div id="scanned-section" className="mb-4">
          <SectionHeader
            id="scanned"
            icon={Printer}
            title="4. Scanned POS Reports (PDF)"
            subtitle="For printed reports that need OCR processing"
            isExpanded={expandedSection === "scanned"}
            colorClass="purple"
          />
          
          {expandedSection === "scanned" && (
            <div className="mt-4 p-6 bg-slate-800/30 rounded-xl border border-slate-700/50">
              <h4 className="text-lg font-semibold text-white mb-4">Uploading Scanned Documents</h4>
              
              <TutorialStep number={1} title="When to Use This Method" icon={HelpCircle}>
                <p>Use this option when you only have a <strong>printed paper copy</strong> of the POS report and cannot export digitally.</p>
                <Warning>Digital XLSX export (Method 1) is always preferred for accuracy. Use PDF scanning only when necessary.</Warning>
              </TutorialStep>

              <TutorialStep number={2} title="Scan the Report" icon={Printer}>
                <p>Scan your printed POS report to PDF:</p>
                <ul className="list-disc list-inside ml-2 mt-2 space-y-1">
                  <li>Use 300 DPI or higher for best results</li>
                  <li>Ensure text is clear and not blurry</li>
                  <li>Scan in color if possible</li>
                  <li>Save as PDF format</li>
                </ul>
              </TutorialStep>

              <TutorialStep number={3} title="Upload & Parse" icon={Upload}>
                <p>In <Link to="/data-uploads" className="text-primary hover:underline">Data Uploads</Link>, scroll to the <strong>Scanned POS Report</strong> section.</p>
                <ol className="list-decimal list-inside ml-2 mt-2 space-y-1">
                  <li>Click "Choose file" and select your PDF</li>
                  <li>Click <strong>Parse PDF</strong></li>
                  <li>Wait for AI processing (may take 1-2 minutes)</li>
                </ol>
              </TutorialStep>

              <TutorialStep number={4} title="Review & Edit" icon={CheckCircle}>
                <p>After parsing, you'll see a preview of extracted data. <strong>Review carefully</strong> and edit any incorrect values before importing.</p>
                <ProTip>Click on any row to edit values. The AI may misread some numbers.</ProTip>
              </TutorialStep>

              <TutorialStep number={5} title="Import Data" icon={ArrowRight}>
                <p>Once you've verified the data, click <strong>Import to Database</strong>.</p>
                <p className="mt-2">The system will match employees by name and update their records.</p>
              </TutorialStep>

              <div className="mt-6 pt-4 border-t border-slate-700">
                <Link to="/data-uploads">
                  <Button className="w-full bg-purple-600 hover:bg-purple-700">
                    <Upload className="w-4 h-4 mr-2" />
                    Go to Data Uploads
                    <ArrowRight className="w-4 h-4 ml-2" />
                  </Button>
                </Link>
              </div>
            </div>
          )}
        </div>

        {/* After Upload Checklist */}
        <div className="mt-8 bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl border border-slate-700 p-6">
          <h3 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <CheckCircle className="w-5 h-5 text-green-400" />
            After Upload Checklist
          </h3>
          <div className="space-y-3">
            <label className="flex items-start gap-3 text-slate-300 text-sm">
              <input type="checkbox" className="mt-1 rounded border-slate-600" />
              <span>Go to <Link to="/" className="text-primary hover:underline">Dashboard</Link> and verify employee count is correct</span>
            </label>
            <label className="flex items-start gap-3 text-slate-300 text-sm">
              <input type="checkbox" className="mt-1 rounded border-slate-600" />
              <span>Check a few employee scores in <Link to="/rankings" className="text-primary hover:underline">Full Rankings</Link> for accuracy</span>
            </label>
            <label className="flex items-start gap-3 text-slate-300 text-sm">
              <input type="checkbox" className="mt-1 rounded border-slate-600" />
              <span>Run the <Link to="/audit" className="text-primary hover:underline">Scoring Audit</Link> to verify data integrity</span>
            </label>
            <label className="flex items-start gap-3 text-slate-300 text-sm">
              <input type="checkbox" className="mt-1 rounded border-slate-600" />
              <span>Create a <Link to="/snapshots" className="text-primary hover:underline">Snapshot</Link> to lock in the current data</span>
            </label>
          </div>
        </div>

        {/* Help Link */}
        <div className="mt-6 text-center">
          <p className="text-slate-400 text-sm">
            Need more help? Visit the{" "}
            <Link to="/help" className="text-primary hover:underline">Help Center</Link>
            {" "}or{" "}
            <Link to="/scoring-guide" className="text-primary hover:underline">Scoring Guide</Link>
          </p>
        </div>
      </div>
    </div>
  );
}
