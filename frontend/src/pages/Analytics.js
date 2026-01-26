import { useState, useEffect, useCallback } from "react";
import { BarChart3, TrendingUp, Target, Download, Calendar, Info } from "lucide-react";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { formatCurrency, formatNumber } from "../utils/formatters";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// V2 Metric Definitions with benchmarks
const V2_METRICS = {
  ppa: { label: 'PPA', defaultBenchmark: 55.0, format: 'currency', higherBetter: true, settingsKey: 'benchmark_ppa', unit: '$/guest', weight: 0.25 },
  lbw_per_guest: { label: 'LBW/Guest', defaultBenchmark: 8.0, format: 'currency', higherBetter: true, settingsKey: 'benchmark_lbw', unit: '$/guest', weight: 0.20 },
  glassware_per_guest: { label: 'Glass/Guest', defaultBenchmark: 1.0, format: 'currency', higherBetter: true, settingsKey: 'benchmark_glass', unit: '$/guest', weight: 0.15 },
  guests_per_lsc: { label: 'Guests/LSC', defaultBenchmark: 100.0, format: 'number', higherBetter: false, settingsKey: 'benchmark_lsc', unit: 'guests', weight: 0.25 },
  cv_score: { label: 'CV Score', defaultBenchmark: 5.0, format: 'number', higherBetter: true, settingsKey: 'benchmark_cv', unit: 'pts', weight: 0.15 },
  pre_dar_score: { label: 'Total Score', defaultBenchmark: 100.0, format: 'number', higherBetter: true, settingsKey: null, unit: 'pts', weight: null },
};

// Helper to get actual benchmark from settings or default
const getBenchmark = (metricKey, quarterSettings) => {
  const metric = V2_METRICS[metricKey];
  if (!metric) return 0;
  if (metric.settingsKey && quarterSettings?.[metric.settingsKey]) {
    return quarterSettings[metric.settingsKey];
  }
  return metric.defaultBenchmark;
};

export default function Analytics() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState({});
  const [quarterSettings, setQuarterSettings] = useState(null);
  
  // V2 Quarter Selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const [empResponse, settingsResponse] = await Promise.all([
        axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`),
        axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`).catch(() => null)
      ]);
      
      setEmployees(empResponse.data);
      if (settingsResponse?.data) {
        setQuarterSettings(settingsResponse.data);
      }
    } catch (error) {
      console.error("Error fetching employees:", error);
      toast.error("Error loading employees");
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchEmployees();
  }, [fetchEmployees]);

  useEffect(() => {
    if (employees.length > 0) {
      calculateAnalytics();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employees, quarterSettings]);

  const handlePrint = async () => {
    try {
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);

      if (isIOS) {
        window.open(`${API}/analytics/pdf`, "_blank", "noopener,noreferrer");
        toast.success("Opened Analytics PDF");
        return;
      }

      const response = await axios.get(`${API}/analytics/pdf`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "analytics_report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      toast.success("Analytics PDF downloaded");
    } catch (error) {
      console.error(error);
      toast.error("Could not download Analytics PDF");
    }
  };

  const getTopEmployees = (metric, limit = 10) => {
    const config = V2_METRICS[metric];
    const valid = employees.filter((e) => e[metric] != null);

    const sorted = [...valid].sort((a, b) => {
      if (!config.higherBetter) return (a[metric] || 0) - (b[metric] || 0);
      return (b[metric] || 0) - (a[metric] || 0);
    });

    return sorted.slice(0, limit);
  };

  const formatMetricValue = (metric, value) => {
    if (value == null) return "N/A";
    const config = V2_METRICS[metric];
    if (!config) return formatNumber(value);
    
    switch (config.format) {
      case 'currency':
        return formatCurrency(value);
      default:
        return formatNumber(value);
    }
  };

  const calculateAnalytics = () => {
    const metrics = Object.keys(V2_METRICS);
    const analyticsData = {};

    metrics.forEach(metric => {
      const config = V2_METRICS[metric];
      const validValues = employees
        .map(emp => emp[metric])
        .filter(val => val != null && !isNaN(val));
      
      if (validValues.length === 0) {
        analyticsData[metric] = { high: 0, medium: 0, low: 0, benchmark: 0, average: 0, total: 0, min: 0, max: 0 };
        return;
      }

      // Get benchmark from quarter settings or use default
      const benchmark = getBenchmark(metric, quarterSettings);
      const average = validValues.reduce((sum, val) => sum + val, 0) / validValues.length;
      const min = Math.min(...validValues);
      const max = Math.max(...validValues);

      let highThreshold, lowThreshold;
      let high = 0, medium = 0, low = 0, aboveBenchmark = 0;

      if (!config.higherBetter) {
        // Lower is better (e.g., Guests/LSC)
        highThreshold = benchmark * 0.9;
        lowThreshold = benchmark * 1.1;

        validValues.forEach(val => {
          if (val <= highThreshold) high++;
          else if (val >= lowThreshold) low++;
          else medium++;
          if (val <= benchmark) aboveBenchmark++;
        });
      } else {
        // Higher is better
        highThreshold = benchmark * 1.1;
        lowThreshold = benchmark * 0.9;

        validValues.forEach(val => {
          if (val >= highThreshold) high++;
          else if (val < lowThreshold) low++;
          else medium++;
          if (val >= benchmark) aboveBenchmark++;
        });
      }

      analyticsData[metric] = {
        high,
        medium,
        low,
        benchmark: aboveBenchmark,
        average,
        total: validValues.length,
        highThreshold,
        lowThreshold,
        benchmarkValue: benchmark,
        min,
        max,
        values: validValues,
      };
    });

    setAnalytics(analyticsData);
  };

  const getPercentage = (count, total) => {
    if (total === 0) return 0;
    return Math.round((count / total) * 100);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      {/* Decorative splashes */}
      <div className="splash-blue" style={{ top: '10%', right: '5%' }} />
      <div className="splash-red" style={{ bottom: '20%', left: '3%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <BarChart3 className="w-8 h-8 text-secondary" />
              <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
                Performance Analytics
              </h1>
            </div>
            <p className="text-gray-500" data-testid="page-subtitle">
              Performance distribution and benchmark analysis for all metrics
            </p>
          </div>

          <Button
            onClick={handlePrint}
            className="bubba-btn-primary w-full sm:w-auto print:hidden"
            data-testid="download-analytics-pdf"
          >
            <Download className="w-4 h-4 mr-2" />
            Download PDF
          </Button>
        </div>

        {/* Quarter Selection */}
        <div className="flex items-center gap-4 mb-8 p-4 bg-gray-50 rounded-lg">
          <Calendar className="w-5 h-5 text-gray-600" />
          <span className="font-medium text-gray-700">Period:</span>
          
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(parseInt(e.target.value))}
            className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={2025}>2025</option>
            <option value={2026}>2026</option>
          </select>
          
          <select
            value={selectedQuarter}
            onChange={(e) => setSelectedQuarter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="Q1">Q1</option>
            <option value="Q2">Q2</option>
            <option value="Q3">Q3</option>
            <option value="Q4">Q4</option>
          </select>
        </div>

        {/* Overview Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <TrendingUp className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-primary">
                  {getPercentage(
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.benchmark || 0), 0),
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                  )}%
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Above Benchmark</p>
              </div>
            </div>
          </div>
          
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-secondary">
                  {getPercentage(
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.high || 0), 0),
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                  )}%
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">High Performers</p>
              </div>
            </div>
          </div>
          
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-yellow-100 flex items-center justify-center">
                <Target className="w-6 h-6 text-yellow-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-yellow-600">
                  {getPercentage(
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.medium || 0), 0),
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                  )}%
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Medium Performers</p>
              </div>
            </div>
          </div>
          
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-orange-100 flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-orange-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-orange-600">
                  {getPercentage(
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.low || 0), 0),
                    Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                  )}%
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Needs Improvement</p>
              </div>
            </div>
          </div>
        </div>

        {/* Analytics by Metric */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {Object.entries(V2_METRICS).map(([metricKey, metricInfo]) => {
            const data = analytics[metricKey] || {};
            const total = data.total || 1;
            
            return (
              <div key={metricKey} className="bubba-card">
                <div className="p-5">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-1">
                    {metricInfo.label}
                  </h3>
                  <p className="text-sm text-gray-500 mb-4">
                    Benchmark: {metricInfo.format === 'currency' ? '$' + metricInfo.benchmark : metricInfo.benchmark}
                  </p>
                
                  <div className="space-y-4">
                    {/* Performance Distribution Bar */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-medium">
                        <span>Performance Distribution</span>
                        <span className="text-gray-500">{total} employees</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-6 overflow-hidden">
                        <div className="h-full flex">
                          <div 
                            className="bg-green-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.high, total)}%` }}
                          >
                            {getPercentage(data.high, total) > 10 ? `${getPercentage(data.high, total)}%` : ''}
                          </div>
                          <div 
                            className="bg-yellow-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.medium, total)}%` }}
                          >
                            {getPercentage(data.medium, total) > 10 ? `${getPercentage(data.medium, total)}%` : ''}
                          </div>
                          <div 
                            className="bg-orange-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.low, total)}%` }}
                          >
                            {getPercentage(data.low, total) > 10 ? `${getPercentage(data.low, total)}%` : ''}
                          </div>
                        </div>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span>High ({data.high})</span>
                        <span>Medium ({data.medium})</span>
                        <span>Low ({data.low})</span>
                      </div>
                    </div>
                    
                    {/* Key Metrics */}
                    <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-200">
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-green-600">
                          {data.benchmark || 0}
                        </div>
                        <div className="text-xs text-gray-500 uppercase tracking-wider">
                          Above Benchmark
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-primary">
                          {formatMetricValue(metricKey, data.average)}
                        </div>
                        <div className="text-xs text-gray-500 uppercase tracking-wider">
                          Team Average
                        </div>
                      </div>
                    </div>
                    
                    {/* Benchmark Status */}
                    <div className="pt-2">
                      <span 
                        className={`block w-full text-center py-2 rounded-full text-sm font-semibold ${
                          getPercentage(data.benchmark, total) >= 60 
                            ? 'bg-green-100 text-green-800' 
                            : getPercentage(data.benchmark, total) >= 40
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {getPercentage(data.benchmark, total)}% Meeting Benchmark
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Top 10 Overall + Top 10 per Metric */}
        <div className="mt-10 space-y-8">
          <div className="space-y-4" data-testid="analytics-top-overall">
            <h2 className="text-2xl font-serif font-bold text-foreground">Top 10 Overall (Total Score)</h2>
            <div className="bubba-card">
              <div className="p-5">
                <div className="space-y-2">
                  {getTopEmployees("pre_dar_score", 10).map((emp, idx) => (
                    <div
                      key={emp.id}
                      className="flex items-center justify-between p-3 border border-gray-200 rounded-lg bg-gray-50"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-primary">#{idx + 1}</span>
                          <span className="font-semibold text-foreground truncate">{emp.name}</span>
                          {emp.ranking && (
                            <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-semibold">
                              {emp.ranking}
                            </span>
                          )}
                        </div>
                        <div className="text-sm text-gray-500 truncate">{emp.performance_tier || 'Not Assessed'}</div>
                        <div className="text-xs text-gray-400">Rank: #{emp.peer_rank || "N/A"}</div>
                      </div>

                      <div className="text-right shrink-0">
                        <div className="font-bold text-primary">
                          {formatMetricValue("pre_dar_score", emp.pre_dar_score)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-4" data-testid="analytics-top-10-metrics">
            <h2 className="text-2xl font-serif font-bold text-foreground">Top 10 by Metric</h2>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {Object.keys(V2_METRICS).map((metric) => {
                const metricInfo = V2_METRICS[metric];
                const top = getTopEmployees(metric, 10);

                return (
                  <div key={metric} className="bubba-card">
                    <div className="p-5">
                      <h3 className="text-lg font-serif font-bold text-foreground">
                        {metricInfo.label}
                      </h3>
                      <p className="text-sm text-gray-500 mb-4">Top 10 employees for this metric</p>
                      
                      <div className="space-y-2">
                        {top.map((emp, idx) => (
                          <div
                            key={emp.id}
                            className="flex items-center justify-between p-3 border border-gray-200 rounded-lg bg-gray-50"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-primary">#{idx + 1}</span>
                                <span className="font-semibold text-foreground truncate">{emp.name}</span>
                              </div>
                              <div className="text-sm text-gray-500 truncate">{emp.performance_tier || 'Not Assessed'}</div>
                              <div className="text-xs text-gray-400">Overall Rank: #{emp.peer_rank || "N/A"}</div>
                            </div>

                            <div className="text-right shrink-0">
                              <div className="font-bold text-primary">
                                {formatMetricValue(metric, emp[metric])}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}