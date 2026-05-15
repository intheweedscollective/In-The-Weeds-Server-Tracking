import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { FileText, Download, BarChart3, Trophy, QrCode, Star, TrendingUp, Calendar } from "lucide-react";
import { Button } from "../components/ui/button";
import QRTopClicksCard from "../components/QRTopClicksCard";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { getDisplayFirstName } from "../utils/displayName";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

export default function Reports() {
  const currentQ = getCurrentQuarter();
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);
  const [employees, setEmployees] = useState([]);
  const [reviewStats, setReviewStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [selectedYear, selectedQuarter]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [empRes, statsRes] = await Promise.all([
        api.get(`/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`),
        api.get(`/v2/reviews/stats?quarter=${selectedQuarter}&year=${selectedYear}`)
      ]);
      
      const sorted = (empRes.data || []).sort((a, b) => (b.total_score || 0) - (a.total_score || 0));
      setEmployees(sorted);
      setReviewStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch data:', error);
    } finally {
      setLoading(false);
    }
  };

  const [downloading, setDownloading] = useState(null);

  const downloadFile = async (url, filename) => {
    try {
      setDownloading(filename);
      const response = await fetch(url);
      if (!response.ok) throw new Error('Download failed');
      
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error('Download error:', error);
      alert('Download failed. Please try again.');
    } finally {
      setDownloading(null);
    }
  };

  const downloadRankingsPDF = () => {
    downloadFile(
      `${BACKEND_URL}/api/v2/yodeck/${selectedYear}/${selectedQuarter}/printable-rankings`,
      `rankings_${selectedQuarter}_${selectedYear}.png`
    );
  };

  const downloadYodeckSlide = (type) => {
    // For complete-rankings, use the rainbow_bubbles background
    const bgParam = type === 'complete-rankings' ? '?format=16:9&background=rainbow_bubbles' : '?format=16:9';
    downloadFile(
      `${BACKEND_URL}/api/v2/yodeck/${selectedYear}/${selectedQuarter}/${type}${bgParam}`,
      `${type}_${selectedQuarter}_${selectedYear}.png`
    );
  };

  const topPerformers = employees.slice(0, 5);
  const avgScore = employees.length > 0 
    ? (employees.reduce((sum, e) => sum + (e.total_score || 0), 0) / employees.length).toFixed(1) 
    : 0;

  return (
    <div className="min-h-screen bg-background p-4 md:p-8" data-testid="reports-page">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
              <FileText className="w-8 h-8 text-primary" />
              Reports & Analytics
            </h1>
            <p className="text-slate-400 mt-1">
              Performance summaries and downloadable reports
            </p>
          </div>
          <div className="flex items-center gap-2">
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
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <span className="text-sm text-slate-400">Employees</span>
          </div>
          <p className="text-2xl font-bold text-white">{employees.length}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-5 h-5 text-cyan-400" />
            <span className="text-sm text-slate-400">Avg Score</span>
          </div>
          <p className="text-2xl font-bold text-white">{avgScore}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Star className="w-5 h-5 text-yellow-400" />
            <span className="text-sm text-slate-400">Reviews</span>
          </div>
          <p className="text-2xl font-bold text-white">{reviewStats?.total_reviews || 0}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Calendar className="w-5 h-5 text-emerald-400" />
            <span className="text-sm text-slate-400">Period</span>
          </div>
          <p className="text-2xl font-bold text-white">{selectedQuarter} {selectedYear}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content - 2 columns */}
        <div className="lg:col-span-2 space-y-6">
          {/* Top 5 Performance Summary */}
          <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
            <div className="p-5 border-b border-slate-700 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
                  <Trophy className="w-5 h-5 text-amber-400" />
                </div>
                <div>
                  <h2 className="font-bold text-white">Top 5 Performers</h2>
                  <p className="text-xs text-slate-500">{selectedQuarter} {selectedYear}</p>
                </div>
              </div>
              <Link to="/rankings" className="text-sm text-primary font-medium hover:underline">
                View Full Rankings →
              </Link>
            </div>
            <div className="divide-y divide-slate-700">
              {loading ? (
                <div className="p-8 text-center text-slate-400">Loading...</div>
              ) : topPerformers.length > 0 ? (
                topPerformers.map((emp, idx) => (
                  <div key={getDisplayFirstName(emp)} className="flex items-center justify-between p-4">
                    <div className="flex items-center gap-3">
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        idx === 0 ? 'bg-amber-500 text-white' : 
                        idx === 1 ? 'bg-slate-400 text-white' : 
                        idx === 2 ? 'bg-amber-700 text-white' : 
                        'bg-slate-600 text-slate-300'
                      }`}>
                        {idx + 1}
                      </div>
                      <div>
                        <span className="font-medium text-white">{getDisplayFirstName(emp)}</span>
                        <p className="text-xs text-slate-500 capitalize">{emp.job_title || 'Server'}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <span className="text-lg font-bold text-primary">{(emp.total_score || 0).toFixed(2)}</span>
                      <p className="text-xs text-slate-500">points</p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center text-slate-400">No data available</div>
              )}
            </div>
          </div>

          {/* Download Reports Section */}
          <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
                <Download className="w-5 h-5 text-cyan-400" />
              </div>
              <div>
                <h2 className="font-bold text-white">Downloadable Reports</h2>
                <p className="text-xs text-slate-500">Export slides and PDFs</p>
              </div>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {/* Quarterly Summary Report - NEW */}
              <Link to="/quarterly-summary" className="block">
                <Button
                  variant="outline"
                  className="w-full justify-start h-auto py-3 border-slate-600 hover:bg-slate-700"
                  data-testid="quarterly-summary-link"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-cyan-500/20 flex items-center justify-center">
                      <FileText className="w-5 h-5 text-cyan-400" />
                    </div>
                    <div className="text-left">
                      <p className="font-medium text-white">Quarterly Summary</p>
                      <p className="text-xs text-slate-400">CV & Metric Bonus report</p>
                    </div>
                  </div>
                </Button>
              </Link>
              
              <Button
                variant="outline"
                className="justify-start h-auto py-3 border-slate-600 hover:bg-slate-700"
                onClick={() => downloadYodeckSlide('complete-rankings')}
                disabled={downloading === 'complete-rankings_Q1_2026.png'}
                data-testid="download-rankings-slide"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                    {downloading === 'complete-rankings_Q1_2026.png' ? (
                      <div className="w-5 h-5 border-2 border-emerald-400 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <Trophy className="w-5 h-5 text-emerald-400" />
                    )}
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-white">
                      {downloading === 'complete-rankings_Q1_2026.png' ? 'Downloading...' : 'Complete Rankings'}
                    </p>
                    <p className="text-xs text-slate-400">Yodeck slide (1920x1080)</p>
                  </div>
                </div>
              </Button>
              
              <Button
                variant="outline"
                className="justify-start h-auto py-3 border-slate-600 hover:bg-slate-700"
                onClick={() => downloadYodeckSlide('top10')}
                data-testid="download-top10-slide"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center">
                    <Star className="w-5 h-5 text-amber-400" />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-white">Top 10 Slide</p>
                    <p className="text-xs text-slate-400">Yodeck slide (1920x1080)</p>
                  </div>
                </div>
              </Button>
              
              <Button
                variant="outline"
                className="justify-start h-auto py-3 border-slate-600 hover:bg-slate-700"
                onClick={downloadRankingsPDF}
                data-testid="download-rankings-pdf"
              >
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-red-500/20 flex items-center justify-center">
                    <FileText className="w-5 h-5 text-red-400" />
                  </div>
                  <div className="text-left">
                    <p className="font-medium text-white">Rankings PDF</p>
                    <p className="text-xs text-slate-400">Full detailed report</p>
                  </div>
                </div>
              </Button>
              
              <Link to="/yodeck" className="block">
                <Button
                  variant="outline"
                  className="w-full justify-start h-auto py-3 border-slate-600 hover:bg-slate-700"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                      <BarChart3 className="w-5 h-5 text-purple-400" />
                    </div>
                    <div className="text-left">
                      <p className="font-medium text-white">More Slides</p>
                      <p className="text-xs text-slate-400">View all export options</p>
                    </div>
                  </div>
                </Button>
              </Link>
            </div>
          </div>
        </div>

        {/* Right Column - QR Top Clicks */}
        <div className="space-y-6">
          <QRTopClicksCard showViewAll={true} limit={10} />
        </div>
      </div>
    </div>
  );
}
