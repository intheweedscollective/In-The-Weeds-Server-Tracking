import { useState, useEffect, useRef } from "react";
import { FileText, Download, Printer, ChevronDown, ChevronUp, Users, Award, MessageSquare, Star, TrendingUp, TrendingDown, Minus, ArrowLeft } from "lucide-react";
import { Button } from "../components/ui/button";
import { Link } from "react-router-dom";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { formatNumber, formatCurrency } from "../utils/formatters";
import { getDisplayFirstName } from "../utils/displayName";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Print-friendly Quarterly Summary Report
 * Displays Customer Voice and Metric Bonus data for all employees
 */
export default function QuarterlySummary() {
  const currentQ = getCurrentQuarter();
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedSections, setExpandedSections] = useState({
    overview: true,
    customerVoice: true,
    metricBonus: true,
    fullTable: true
  });
  const printRef = useRef();

  useEffect(() => {
    fetchEmployees();
  }, [selectedYear, selectedQuarter]);

  const fetchEmployees = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      const sorted = (res.data || []).sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
      setEmployees(sorted);
    } catch (error) {
      console.error('Failed to fetch employees:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handlePrint = () => {
    window.print();
  };

  const downloadPDF = () => {
    window.open(`${BACKEND_URL}/api/v2/reports/${selectedYear}/${selectedQuarter}/quarterly-summary`, '_blank');
  };

  // Calculate summary statistics
  const stats = {
    totalEmployees: employees.length,
    avgScore: employees.length > 0 
      ? employees.reduce((sum, e) => sum + (e.total_score || 0), 0) / employees.length 
      : 0,
    totalCVScore: employees.reduce((sum, e) => sum + (e.cv_score || 0), 0),
    avgCVScore: employees.length > 0 
      ? employees.reduce((sum, e) => sum + (e.cv_score || 0), 0) / employees.length 
      : 0,
    totalPromoters: employees.reduce((sum, e) => sum + (e.cv_promoters || 0), 0),
    totalDetractors: employees.reduce((sum, e) => sum + (e.cv_detractors || 0), 0),
    totalPassives: employees.reduce((sum, e) => sum + (e.cv_passives || 0), 0),
    totalMetricBonus: employees.reduce((sum, e) => sum + (e.total_metric_bonus || 0), 0),
    avgMetricBonus: employees.length > 0 
      ? employees.reduce((sum, e) => sum + (e.total_metric_bonus || 0), 0) / employees.length 
      : 0,
    employeesWithBonus: employees.filter(e => (e.total_metric_bonus || 0) > 0).length,
  };

  // Top performers by Customer Voice
  const topCVPerformers = [...employees]
    .sort((a, b) => (b.cv_score || 0) - (a.cv_score || 0))
    .slice(0, 5);

  // Top performers by Metric Bonus
  const topMetricBonusPerformers = [...employees]
    .sort((a, b) => (b.total_metric_bonus || 0) - (a.total_metric_bonus || 0))
    .slice(0, 5);

  // Tier breakdown
  const tiers = {
    trainer: employees.filter(e => (e.job_title || '').toLowerCase().includes('trainer')).length,
    bartender: employees.filter(e => (e.job_title || '').toLowerCase().includes('bartend')).length,
    aServer: employees.filter(e => (e.total_score || 0) >= 85 && !(e.job_title || '').toLowerCase().includes('trainer') && !(e.job_title || '').toLowerCase().includes('bartend')).length,
    bServer: employees.filter(e => (e.total_score || 0) >= 70 && (e.total_score || 0) < 85).length,
    cServer: employees.filter(e => (e.total_score || 0) < 70 && !(e.job_title || '').toLowerCase().includes('trainer') && !(e.job_title || '').toLowerCase().includes('bartend')).length,
  };

  return (
    <div className="min-h-screen bg-background" data-testid="quarterly-summary-page">
      {/* Screen Header - Hidden when printing */}
      <div className="p-4 md:p-8 print:hidden">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 mb-6">
          <div className="flex items-center gap-4">
            <Link to="/reports" className="text-slate-400 hover:text-white">
              <ArrowLeft className="w-5 h-5" />
            </Link>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
                <FileText className="w-8 h-8 text-primary" />
                Quarterly Summary Report
              </h1>
              <p className="text-slate-400 mt-1">
                Customer Voice & Metric Bonus Overview
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="px-3 py-2 border border-slate-600 rounded-lg text-sm bg-slate-800 text-slate-200"
              data-testid="filter-year"
            >
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
            </select>
            <select
              value={selectedQuarter}
              onChange={(e) => setSelectedQuarter(e.target.value)}
              className="px-3 py-2 border border-slate-600 rounded-lg text-sm bg-slate-800 text-slate-200"
              data-testid="filter-quarter"
            >
              <option value="Q1">Q1</option>
              <option value="Q2">Q2</option>
              <option value="Q3">Q3</option>
              <option value="Q4">Q4</option>
            </select>
            <Button onClick={handlePrint} variant="outline" className="flex items-center gap-2">
              <Printer className="w-4 h-4" />
              Print
            </Button>
          </div>
        </div>
      </div>

      {/* Printable Content */}
      <div ref={printRef} className="px-4 md:px-8 pb-8 print:px-8 print:py-4">
        {/* Print Header */}
        <div className="hidden print:block mb-6">
          <div className="flex items-center justify-between border-b-2 border-slate-300 pb-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">Bubba Gump Shrimp Co.</h1>
              <p className="text-lg text-slate-600">Quarterly Performance Summary</p>
            </div>
            <div className="text-right">
              <p className="text-xl font-bold text-slate-900">{selectedQuarter} {selectedYear}</p>
              <p className="text-sm text-slate-500">Generated: {new Date().toLocaleDateString()}</p>
            </div>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Overview Section */}
            <SectionCard 
              title="Executive Overview" 
              icon={<Users className="w-5 h-5" />}
              expanded={expandedSections.overview}
              onToggle={() => toggleSection('overview')}
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 print:grid-cols-4">
                <StatCard label="Total Employees" value={stats.totalEmployees} color="blue" />
                <StatCard label="Avg Total Score" value={stats.avgScore.toFixed(1)} color="green" />
                <StatCard label="Avg Customer Voice" value={stats.avgCVScore.toFixed(1)} color="purple" suffix="pts" />
                <StatCard label="Avg Metric Bonus" value={stats.avgMetricBonus.toFixed(1)} color="amber" suffix="pts" />
              </div>

              {/* Tier Distribution */}
              <div className="mt-4 pt-4 border-t border-slate-700 print:border-slate-300">
                <h4 className="text-sm font-semibold text-slate-300 print:text-slate-700 mb-3">Team Distribution</h4>
                <div className="flex flex-wrap gap-3">
                  <TierBadge label="Trainers" count={tiers.trainer} color="purple" />
                  <TierBadge label="Bartenders" count={tiers.bartender} color="blue" />
                  <TierBadge label="A-Servers" count={tiers.aServer} color="green" />
                  <TierBadge label="B-Servers" count={tiers.bServer} color="yellow" />
                  <TierBadge label="C-Servers" count={tiers.cServer} color="red" />
                </div>
              </div>
            </SectionCard>

            {/* Customer Voice Section */}
            <SectionCard 
              title="Customer Voice Summary" 
              icon={<MessageSquare className="w-5 h-5" />}
              expanded={expandedSections.customerVoice}
              onToggle={() => toggleSection('customerVoice')}
              color="purple"
            >
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 print:grid-cols-4 mb-4">
                <StatCard label="Total CV Points" value={stats.totalCVScore.toFixed(1)} color="purple" />
                <StatCard label="Promoters" value={stats.totalPromoters} color="green" sublabel={`+${stats.totalPromoters} pts`} />
                <StatCard label="Passives" value={stats.totalPassives} color="slate" sublabel="0 pts" />
                <StatCard label="Detractors" value={stats.totalDetractors} color="red" sublabel={`−${stats.totalDetractors * 2} pts`} />
              </div>

              {/* Top CV Performers */}
              <div className="mt-4 pt-4 border-t border-slate-700 print:border-slate-300">
                <h4 className="text-sm font-semibold text-slate-300 print:text-slate-700 mb-3">Top 5 by Customer Voice</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-400 print:text-slate-600 border-b border-slate-700 print:border-slate-300">
                        <th className="pb-2 pr-4">Rank</th>
                        <th className="pb-2 pr-4">Employee</th>
                        <th className="pb-2 pr-4 text-center">Promoters</th>
                        <th className="pb-2 pr-4 text-center">Detractors</th>
                        <th className="pb-2 text-right">CV Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topCVPerformers.map((emp, idx) => (
                        <tr key={emp.id || emp.name} className="border-b border-slate-700/50 print:border-slate-200">
                          <td className="py-2 pr-4">
                            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                              idx === 0 ? 'bg-amber-500 text-white' : 'bg-slate-700 print:bg-slate-200 text-slate-300 print:text-slate-700'
                            }`}>
                              {idx + 1}
                            </span>
                          </td>
                          <td className="py-2 pr-4 font-medium text-white print:text-slate-900">{getDisplayFirstName(emp)}</td>
                          <td className="py-2 pr-4 text-center text-green-400 print:text-green-600">{emp.cv_promoters || 0}</td>
                          <td className="py-2 pr-4 text-center text-red-400 print:text-red-600">{emp.cv_detractors || 0}</td>
                          <td className={`py-2 text-right font-bold ${
                            (emp.cv_score || 0) > 0 ? 'text-green-400 print:text-green-600' : 
                            (emp.cv_score || 0) < 0 ? 'text-red-400 print:text-red-600' : 
                            'text-slate-400 print:text-slate-600'
                          }`}>
                            {(emp.cv_score || 0) > 0 ? '+' : ''}{(emp.cv_score || 0).toFixed(1)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </SectionCard>

            {/* Metric Bonus Section */}
            <SectionCard 
              title="Metric Bonus Summary" 
              icon={<Award className="w-5 h-5" />}
              expanded={expandedSections.metricBonus}
              onToggle={() => toggleSection('metricBonus')}
              color="amber"
            >
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4 print:grid-cols-3 mb-4">
                <StatCard label="Total Bonus Points" value={stats.totalMetricBonus.toFixed(1)} color="amber" />
                <StatCard label="Employees w/ Bonus" value={stats.employeesWithBonus} color="green" sublabel={`of ${stats.totalEmployees}`} />
                <StatCard label="Avg Bonus/Employee" value={stats.avgMetricBonus.toFixed(2)} color="blue" suffix="pts" />
              </div>

              {/* Top Metric Bonus Performers */}
              <div className="mt-4 pt-4 border-t border-slate-700 print:border-slate-300">
                <h4 className="text-sm font-semibold text-slate-300 print:text-slate-700 mb-3">Top 5 by Metric Bonus</h4>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-slate-400 print:text-slate-600 border-b border-slate-700 print:border-slate-300">
                        <th className="pb-2 pr-4">Rank</th>
                        <th className="pb-2 pr-4">Employee</th>
                        <th className="pb-2 pr-4 text-center">PPA</th>
                        <th className="pb-2 pr-4 text-center">LSC</th>
                        <th className="pb-2 pr-4 text-center">LBW</th>
                        <th className="pb-2 pr-4 text-center">Glass</th>
                        <th className="pb-2 text-right">Total Bonus</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topMetricBonusPerformers.map((emp, idx) => (
                        <tr key={emp.id || emp.name} className="border-b border-slate-700/50 print:border-slate-200">
                          <td className="py-2 pr-4">
                            <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                              idx === 0 ? 'bg-amber-500 text-white' : 'bg-slate-700 print:bg-slate-200 text-slate-300 print:text-slate-700'
                            }`}>
                              {idx + 1}
                            </span>
                          </td>
                          <td className="py-2 pr-4 font-medium text-white print:text-slate-900">{getDisplayFirstName(emp)}</td>
                          <td className="py-2 pr-4 text-center text-slate-300 print:text-slate-700">
                            {formatCurrency(emp.ppa || 0)}
                          </td>
                          <td className="py-2 pr-4 text-center text-slate-300 print:text-slate-700">
                            {(emp.guests_per_lsc || 0).toFixed(0)}
                          </td>
                          <td className="py-2 pr-4 text-center text-slate-300 print:text-slate-700">
                            {formatCurrency(emp.lbw_per_guest || 0)}
                          </td>
                          <td className="py-2 pr-4 text-center text-slate-300 print:text-slate-700">
                            {formatCurrency(emp.glassware_per_guest || 0)}
                          </td>
                          <td className="py-2 text-right font-bold text-amber-400 print:text-amber-600">
                            +{(emp.total_metric_bonus || 0).toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </SectionCard>

            {/* Full Employee Table */}
            <SectionCard 
              title="Complete Employee Breakdown" 
              icon={<Star className="w-5 h-5" />}
              expanded={expandedSections.fullTable}
              onToggle={() => toggleSection('fullTable')}
              color="cyan"
            >
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 print:text-slate-600 border-b border-slate-700 print:border-slate-300">
                      <th className="pb-2 pr-3">#</th>
                      <th className="pb-2 pr-3">Employee</th>
                      <th className="pb-2 pr-3">Title</th>
                      <th className="pb-2 pr-3 text-right">Total Score</th>
                      <th className="pb-2 pr-3 text-center">Promoters</th>
                      <th className="pb-2 pr-3 text-center">Detractors</th>
                      <th className="pb-2 pr-3 text-right">Cust. Voice</th>
                      <th className="pb-2 pr-3 text-right">Metric Bonus</th>
                      <th className="pb-2 text-right">RT Bonus</th>
                    </tr>
                  </thead>
                  <tbody>
                    {employees.map((emp, idx) => (
                      <tr key={emp.id || emp.name} className={`border-b border-slate-700/50 print:border-slate-200 ${idx % 2 === 0 ? '' : 'bg-slate-800/30 print:bg-slate-50'}`}>
                        <td className="py-2 pr-3 text-slate-400 print:text-slate-600">{idx + 1}</td>
                        <td className="py-2 pr-3 font-medium text-white print:text-slate-900">{getDisplayFirstName(emp)}</td>
                        <td className="py-2 pr-3 text-slate-400 print:text-slate-600 capitalize text-xs">{emp.job_title || 'Server'}</td>
                        <td className="py-2 pr-3 text-right font-bold text-primary print:text-blue-600">{(emp.total_score || 0).toFixed(2)}</td>
                        <td className="py-2 pr-3 text-center text-green-400 print:text-green-600">{emp.cv_promoters || 0}</td>
                        <td className="py-2 pr-3 text-center text-red-400 print:text-red-600">{emp.cv_detractors || 0}</td>
                        <td className={`py-2 pr-3 text-right font-semibold ${
                          (emp.cv_score || 0) > 0 ? 'text-green-400 print:text-green-600' : 
                          (emp.cv_score || 0) < 0 ? 'text-red-400 print:text-red-600' : 
                          'text-slate-400 print:text-slate-600'
                        }`}>
                          {(emp.cv_score || 0) > 0 ? '+' : ''}{(emp.cv_score || 0).toFixed(1)}
                        </td>
                        <td className="py-2 pr-3 text-right text-amber-400 print:text-amber-600">
                          +{(emp.total_metric_bonus || 0).toFixed(2)}
                        </td>
                        <td className="py-2 text-right text-pink-400 print:text-pink-600">
                          +{(emp.review_tracker_bonus || 0).toFixed(1)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t-2 border-slate-600 print:border-slate-400 font-bold">
                      <td colSpan="3" className="py-3 text-slate-300 print:text-slate-700">TOTALS</td>
                      <td className="py-3 text-right text-primary print:text-blue-600">
                        {(employees.reduce((sum, e) => sum + (e.total_score || 0), 0)).toFixed(1)}
                      </td>
                      <td className="py-3 text-center text-green-400 print:text-green-600">{stats.totalPromoters}</td>
                      <td className="py-3 text-center text-red-400 print:text-red-600">{stats.totalDetractors}</td>
                      <td className={`py-3 text-right ${stats.totalCVScore > 0 ? 'text-green-400 print:text-green-600' : 'text-red-400 print:text-red-600'}`}>
                        {stats.totalCVScore > 0 ? '+' : ''}{stats.totalCVScore.toFixed(1)}
                      </td>
                      <td className="py-3 text-right text-amber-400 print:text-amber-600">
                        +{stats.totalMetricBonus.toFixed(1)}
                      </td>
                      <td className="py-3 text-right text-pink-400 print:text-pink-600">
                        +{employees.reduce((sum, e) => sum + (e.review_tracker_bonus || 0), 0).toFixed(1)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            </SectionCard>

            {/* Print Footer */}
            <div className="hidden print:block mt-8 pt-4 border-t border-slate-300 text-center text-sm text-slate-500">
              <p>Bubba Gump Shrimp Co. - Las Vegas • {selectedQuarter} {selectedYear} Performance Report</p>
              <p className="mt-1">Confidential - For Internal Use Only</p>
            </div>
          </div>
        )}
      </div>

      {/* Print Styles */}
      <style>{`
        @media print {
          body { 
            background: white !important; 
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .print\\:hidden { display: none !important; }
          .print\\:block { display: block !important; }
          .print\\:grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)) !important; }
          .print\\:grid-cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)) !important; }
          @page { 
            size: letter portrait;
            margin: 0.5in;
          }
        }
      `}</style>
    </div>
  );
}

/**
 * Collapsible section card component
 */
const SectionCard = ({ title, icon, children, expanded, onToggle, color = "blue" }) => {
  const colorClasses = {
    blue: "text-blue-400",
    purple: "text-purple-400",
    amber: "text-amber-400",
    cyan: "text-cyan-400",
    green: "text-green-400"
  };

  return (
    <div className="bg-slate-800 print:bg-white rounded-xl border border-slate-700 print:border-slate-300 overflow-hidden print:break-inside-avoid">
      <button 
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-slate-700/50 print:hover:bg-transparent transition-colors print:cursor-default"
      >
        <div className="flex items-center gap-3">
          <div className={colorClasses[color]}>{icon}</div>
          <h3 className="font-bold text-white print:text-slate-900">{title}</h3>
        </div>
        <div className="print:hidden">
          {expanded ? <ChevronUp className="w-5 h-5 text-slate-400" /> : <ChevronDown className="w-5 h-5 text-slate-400" />}
        </div>
      </button>
      {(expanded || true) && (
        <div className={`p-4 pt-0 ${expanded ? '' : 'hidden print:block'}`}>
          {children}
        </div>
      )}
    </div>
  );
};

/**
 * Stat card component
 */
const StatCard = ({ label, value, color = "blue", suffix = "", sublabel = "" }) => {
  const colorClasses = {
    blue: "bg-blue-500/20 text-blue-400 print:text-blue-600",
    green: "bg-green-500/20 text-green-400 print:text-green-600",
    purple: "bg-purple-500/20 text-purple-400 print:text-purple-600",
    amber: "bg-amber-500/20 text-amber-400 print:text-amber-600",
    red: "bg-red-500/20 text-red-400 print:text-red-600",
    slate: "bg-slate-500/20 text-slate-400 print:text-slate-600",
    cyan: "bg-cyan-500/20 text-cyan-400 print:text-cyan-600"
  };

  return (
    <div className={`rounded-lg p-4 print:p-3 ${colorClasses[color].split(' ')[0]} print:bg-slate-100`}>
      <p className="text-xs text-slate-400 print:text-slate-600 mb-1">{label}</p>
      <p className={`text-2xl print:text-xl font-bold ${colorClasses[color].split(' ').slice(1).join(' ')}`}>
        {value}{suffix && <span className="text-sm ml-1">{suffix}</span>}
      </p>
      {sublabel && <p className="text-xs text-slate-500 print:text-slate-500 mt-1">{sublabel}</p>}
    </div>
  );
};

/**
 * Tier badge component
 */
const TierBadge = ({ label, count, color }) => {
  const colorClasses = {
    purple: "bg-purple-500/20 text-purple-400 border-purple-500/30",
    blue: "bg-blue-500/20 text-blue-400 border-blue-500/30",
    green: "bg-green-500/20 text-green-400 border-green-500/30",
    yellow: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    red: "bg-red-500/20 text-red-400 border-red-500/30"
  };

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium border ${colorClasses[color]} print:bg-white print:border-slate-300 print:text-slate-700`}>
      {label}: <strong>{count}</strong>
    </span>
  );
};
