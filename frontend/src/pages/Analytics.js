import { useState, useEffect, useCallback } from "react";
import { BarChart3, TrendingUp, Target, Download, Calendar, Info, ArrowUp, ArrowDown, Minus, X, Users, Filter } from "lucide-react";
import axios from "axios";
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

// Zone types for filtering
const ZONE_TYPES = {
  HIGH: 'high',
  MEDIUM: 'medium', 
  LOW: 'low',
  AVERAGE: 'average'
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
  const [trendData, setTrendData] = useState(null);
  const [activeTab, setActiveTab] = useState('metrics'); // 'metrics' or 'trends'
  
  // Interactive filter state
  const [activeFilter, setActiveFilter] = useState(null); // { metric: 'ppa', zone: 'high' }
  const [filteredEmployees, setFilteredEmployees] = useState([]);
  
  // V2 Quarter Selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");

  // Filter employees by zone
  const filterByZone = (metricKey, zone) => {
    const config = V2_METRICS[metricKey];
    const data = analytics[metricKey];
    if (!config || !data) return;
    
    const benchmark = data.benchmarkValue;
    const highThreshold = data.highThreshold;
    const lowThreshold = data.lowThreshold;
    const average = data.average;
    
    let filtered = [];
    
    if (zone === ZONE_TYPES.HIGH) {
      filtered = employees.filter(emp => {
        const val = emp[metricKey];
        if (val == null) return false;
        if (!config.higherBetter) {
          return val <= highThreshold;
        }
        return val >= highThreshold;
      });
    } else if (zone === ZONE_TYPES.LOW) {
      filtered = employees.filter(emp => {
        const val = emp[metricKey];
        if (val == null) return false;
        if (!config.higherBetter) {
          return val >= lowThreshold;
        }
        return val < lowThreshold;
      });
    } else if (zone === ZONE_TYPES.MEDIUM) {
      filtered = employees.filter(emp => {
        const val = emp[metricKey];
        if (val == null) return false;
        if (!config.higherBetter) {
          return val > highThreshold && val < lowThreshold;
        }
        return val >= lowThreshold && val < highThreshold;
      });
    } else if (zone === ZONE_TYPES.AVERAGE) {
      // Show employees within 10% of average
      const tolerance = average * 0.1;
      filtered = employees.filter(emp => {
        const val = emp[metricKey];
        if (val == null) return false;
        return Math.abs(val - average) <= tolerance;
      });
    }
    
    // Sort by the metric value
    filtered.sort((a, b) => {
      if (!config.higherBetter) {
        return (a[metricKey] || 0) - (b[metricKey] || 0);
      }
      return (b[metricKey] || 0) - (a[metricKey] || 0);
    });
    
    setActiveFilter({ metric: metricKey, zone });
    setFilteredEmployees(filtered);
    
    // Scroll to the filtered results
    setTimeout(() => {
      document.getElementById('filtered-results')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };
  
  const clearFilter = () => {
    setActiveFilter(null);
    setFilteredEmployees([]);
  };

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const [empResponse, settingsResponse, trendResponse] = await Promise.all([
        axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`),
        axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`).catch(() => null),
        axios.get(`${API}/v2/trends/${selectedYear}/${selectedQuarter}/team/data`).catch(() => null)
      ]);
      
      setEmployees(empResponse.data);
      if (settingsResponse?.data) {
        setQuarterSettings(settingsResponse.data);
      }
      if (trendResponse?.data) {
        setTrendData(trendResponse.data);
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
        window.open(`${API}/v2/analytics/${selectedYear}/${selectedQuarter}/pdf`, "_blank", "noopener,noreferrer");
        toast.success("Opened Analytics PDF");
        return;
      }

      const response = await axios.get(`${API}/v2/analytics/${selectedYear}/${selectedQuarter}/pdf`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `analytics_${selectedQuarter}_${selectedYear}.pdf`;
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
      <div className="min-h-screen bg-paper">
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper relative overflow-hidden">
      {/* Decorative splashes */}
      <div className="splash-blue" style={{ top: '10%', right: '5%' }} />
      <div className="splash-red" style={{ bottom: '20%', left: '3%', opacity: 0.5 }} />
      
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

        {/* Tab Navigation */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('metrics')}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'metrics'
                ? 'bg-primary text-white shadow-md'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            data-testid="metrics-tab"
          >
            <BarChart3 className="w-4 h-4 inline mr-2" />
            Metrics Analysis
          </button>
          <button
            onClick={() => setActiveTab('trends')}
            className={`px-6 py-3 rounded-lg font-medium transition-all ${
              activeTab === 'trends'
                ? 'bg-primary text-white shadow-md'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            data-testid="trends-tab"
          >
            <TrendingUp className="w-4 h-4 inline mr-2" />
            Quarter Trends
          </button>
        </div>

        {/* Conditional Content Based on Tab */}
        {activeTab === 'metrics' ? (
          <>
        {/* Overview Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10" data-testid="score-distribution">
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
            const benchmark = data.benchmarkValue || metricInfo.defaultBenchmark;
            const isInverse = !metricInfo.higherBetter;
            
            // Calculate the position of benchmark, average, and thresholds on a visual scale
            const rangeMin = data.min || 0;
            const rangeMax = data.max || benchmark * 2;
            const range = Math.max(rangeMax - rangeMin, 1);
            
            // For visual positioning (0-100%)
            const getPosition = (value) => {
              if (isInverse) {
                // For inverse metrics, flip the scale so lower values appear on the right
                return Math.max(0, Math.min(100, ((rangeMax - value) / range) * 100));
              }
              return Math.max(0, Math.min(100, ((value - rangeMin) / range) * 100));
            };
            
            const benchmarkPosition = getPosition(benchmark);
            const averagePosition = getPosition(data.average || 0);
            const highThresholdPos = getPosition(data.highThreshold || benchmark * 1.1);
            const lowThresholdPos = getPosition(data.lowThreshold || benchmark * 0.9);
            
            return (
              <div key={metricKey} className="bubba-card" data-testid={`metric-card-${metricKey}`}>
                <div className="p-5">
                  {/* Header with benchmark info */}
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="text-lg font-serif font-bold text-foreground">
                        {metricInfo.label}
                      </h3>
                      <p className="text-sm text-gray-500">
                        Weight: {metricInfo.weight ? `${metricInfo.weight * 100}%` : '—'}
                      </p>
                    </div>
                    <div className="text-right">
                      <div className="flex items-center gap-2">
                        <Target className="w-4 h-4 text-primary" />
                        <span className="text-sm font-semibold text-primary">
                          Benchmark: {metricInfo.format === 'currency' ? '$' : ''}{benchmark}{metricInfo.unit ? ` ${metricInfo.unit}` : ''}
                        </span>
                      </div>
                      <p className="text-xs text-gray-400 mt-1">
                        {isInverse ? 'Lower is better' : 'Higher is better'}
                      </p>
                    </div>
                  </div>
                
                  <div className="space-y-4">
                    {/* Contextual Explanation Box */}
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 mb-3">
                      <div className="flex items-start gap-2">
                        <Info className="w-4 h-4 text-slate-500 mt-0.5 flex-shrink-0" />
                        <div className="text-xs text-slate-600">
                          <span className="font-semibold">How to read this chart:</span> The scale below shows where your team stands. 
                          The <span className="font-bold text-amber-600">orange target line</span> is your benchmark goal ({formatMetricValue(metricKey, benchmark)}). 
                          The <span className="font-bold text-blue-600">blue diamond</span> shows the team's current average ({formatMetricValue(metricKey, data.average)}).
                          {isInverse 
                            ? " For this metric, lower values are better — aim to stay left of the target."
                            : " For this metric, higher values are better — aim to stay right of the target."
                          }
                        </div>
                      </div>
                    </div>
                    
                    {/* Visual Range Chart with Benchmark Line */}
                    <div className="space-y-2" data-testid={`metric-chart-${metricKey}`}>
                      <div className="flex justify-between text-xs font-semibold">
                        <span className={isInverse ? "text-green-600" : "text-red-500"}>
                          {isInverse ? '✓ Best' : '⚠ Low'}: {formatMetricValue(metricKey, rangeMin)}
                        </span>
                        <span className={isInverse ? "text-red-500" : "text-green-600"}>
                          {isInverse ? '⚠ Worst' : '✓ High'}: {formatMetricValue(metricKey, rangeMax)}
                        </span>
                      </div>
                      
                      {/* Visual scale with zones and benchmark line - INTERACTIVE */}
                      <div className="relative h-14 bg-gradient-to-r from-red-100 via-yellow-50 to-green-100 rounded-lg overflow-visible border border-gray-200">
                        {/* Clickable Green Zone (Exceeds Target) */}
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.HIGH)}
                          className={`absolute top-0 h-full bg-green-300/40 hover:bg-green-400/60 transition-colors cursor-pointer z-10 ${
                            activeFilter?.metric === metricKey && activeFilter?.zone === ZONE_TYPES.HIGH 
                              ? 'ring-2 ring-green-500 ring-inset bg-green-400/60' 
                              : ''
                          }`}
                          style={{ 
                            left: isInverse ? '0%' : `${highThresholdPos}%`,
                            width: isInverse ? `${100 - highThresholdPos}%` : `${100 - highThresholdPos}%`
                          }}
                          title={`Click to see ${data.high} employees exceeding target`}
                          data-testid={`zone-high-${metricKey}`}
                        />
                        {/* Clickable Red Zone (Below Target) */}
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.LOW)}
                          className={`absolute top-0 h-full bg-red-300/40 hover:bg-red-400/60 transition-colors cursor-pointer z-10 ${
                            activeFilter?.metric === metricKey && activeFilter?.zone === ZONE_TYPES.LOW 
                              ? 'ring-2 ring-red-500 ring-inset bg-red-400/60' 
                              : ''
                          }`}
                          style={{ 
                            left: isInverse ? `${100 - lowThresholdPos}%` : '0%',
                            width: isInverse ? `${lowThresholdPos}%` : `${lowThresholdPos}%`
                          }}
                          title={`Click to see ${data.low} employees below target`}
                          data-testid={`zone-low-${metricKey}`}
                        />
                        {/* Clickable Middle Zone (Near Target) */}
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.MEDIUM)}
                          className={`absolute top-0 h-full hover:bg-yellow-200/60 transition-colors cursor-pointer z-10 ${
                            activeFilter?.metric === metricKey && activeFilter?.zone === ZONE_TYPES.MEDIUM 
                              ? 'ring-2 ring-yellow-500 ring-inset bg-yellow-200/60' 
                              : ''
                          }`}
                          style={{ 
                            left: isInverse ? `${100 - lowThresholdPos}%` : `${lowThresholdPos}%`,
                            width: `${Math.abs(highThresholdPos - lowThresholdPos)}%`
                          }}
                          title={`Click to see ${data.medium} employees near target`}
                          data-testid={`zone-medium-${metricKey}`}
                        />
                        
                        {/* Benchmark/Target line - ORANGE dashed line for clear distinction */}
                        <div 
                          className="absolute top-0 h-full w-0.5 z-20"
                          style={{ 
                            left: `${benchmarkPosition}%`, 
                            transform: 'translateX(-50%)',
                            background: 'repeating-linear-gradient(to bottom, #f59e0b, #f59e0b 4px, transparent 4px, transparent 8px)',
                          }}
                        />
                        {/* Target arrow indicator at top */}
                        <div 
                          className="absolute -top-2 z-30"
                          style={{ left: `${benchmarkPosition}%`, transform: 'translateX(-50%)' }}
                        >
                          <div className="w-0 h-0 border-l-[6px] border-r-[6px] border-t-[8px] border-l-transparent border-r-transparent border-t-amber-500" />
                        </div>
                        {/* Target label at bottom */}
                        <div 
                          className="absolute -bottom-5 text-[10px] font-bold text-amber-600 whitespace-nowrap z-30"
                          style={{ left: `${benchmarkPosition}%`, transform: 'translateX(-50%)' }}
                        >
                          TARGET
                        </div>
                        
                        {/* Average indicator - BLUE diamond for clear distinction - CLICKABLE */}
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.AVERAGE)}
                          className={`absolute top-1/2 transform -translate-y-1/2 -translate-x-1/2 z-20 cursor-pointer group ${
                            activeFilter?.metric === metricKey && activeFilter?.zone === ZONE_TYPES.AVERAGE 
                              ? '' : ''
                          }`}
                          style={{ left: `${averagePosition}%` }}
                          title="Click to see employees near team average"
                          data-testid={`zone-average-${metricKey}`}
                        >
                          <div className={`w-5 h-5 bg-blue-500 rotate-45 shadow-lg border-2 border-white group-hover:scale-125 transition-transform ${
                            activeFilter?.metric === metricKey && activeFilter?.zone === ZONE_TYPES.AVERAGE 
                              ? 'scale-125 ring-2 ring-blue-400' 
                              : ''
                          }`} />
                        </button>
                        {/* Team Avg label */}
                        <div 
                          className="absolute top-1 text-[10px] font-bold text-blue-600 whitespace-nowrap z-30"
                          style={{ left: `${averagePosition}%`, transform: 'translateX(-50%)' }}
                        >
                          TEAM AVG
                        </div>
                      </div>
                      
                      {/* Legend - more descriptive with click hint */}
                      <div className="flex items-center justify-center gap-6 text-xs pt-4 mt-2 border-t border-dashed border-gray-200">
                        <div className="flex items-center gap-1 text-slate-500">
                          <Filter className="w-3 h-3" />
                          <span className="font-medium">Click zones to filter:</span>
                        </div>
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.HIGH)}
                          className="flex items-center gap-1.5 hover:opacity-70 transition-opacity cursor-pointer"
                        >
                          <div className="w-3 h-3 bg-green-300 rounded-sm border border-green-400" />
                          <span className="text-gray-600 font-medium">Exceeds ({data.high})</span>
                        </button>
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.MEDIUM)}
                          className="flex items-center gap-1.5 hover:opacity-70 transition-opacity cursor-pointer"
                        >
                          <div className="w-3 h-3 bg-yellow-200 rounded-sm border border-yellow-400" />
                          <span className="text-gray-600 font-medium">Near Target ({data.medium})</span>
                        </button>
                        <button 
                          onClick={() => filterByZone(metricKey, ZONE_TYPES.LOW)}
                          className="flex items-center gap-1.5 hover:opacity-70 transition-opacity cursor-pointer"
                        >
                          <div className="w-3 h-3 bg-red-300 rounded-sm border border-red-400" />
                          <span className="text-gray-600 font-medium">Below ({data.low})</span>
                        </button>
                      </div>
                    </div>
                    
                    {/* Performance Distribution Bar */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-medium">
                        <span>Performance Distribution</span>
                        <span className="text-gray-500">{total} employees</span>
                      </div>
                      <div className="w-full bg-gray-200 rounded-full h-6 overflow-hidden">
                        <div className="h-full flex">
                          <div 
                            className="bg-orange-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.low, total)}%` }}
                          >
                            {getPercentage(data.low, total) > 10 ? `${getPercentage(data.low, total)}%` : ''}
                          </div>
                          <div 
                            className="bg-yellow-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.medium, total)}%` }}
                          >
                            {getPercentage(data.medium, total) > 10 ? `${getPercentage(data.medium, total)}%` : ''}
                          </div>
                          <div 
                            className="bg-green-500 h-full flex items-center justify-center text-white text-xs font-medium"
                            style={{ width: `${getPercentage(data.high, total)}%` }}
                          >
                            {getPercentage(data.high, total) > 10 ? `${getPercentage(data.high, total)}%` : ''}
                          </div>
                        </div>
                      </div>
                      <div className="flex justify-between text-xs text-gray-500">
                        <span className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-orange-500 rounded-full"></span>
                          Low ({data.low})
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-yellow-500 rounded-full"></span>
                          Medium ({data.medium})
                        </span>
                        <span className="flex items-center gap-1">
                          <span className="w-2 h-2 bg-green-500 rounded-full"></span>
                          High ({data.high})
                        </span>
                      </div>
                    </div>
                    
                    {/* Key Metrics */}
                    <div className="grid grid-cols-3 gap-3 pt-4 border-t border-gray-200">
                      <div className="text-center p-2 bg-gray-50 rounded-lg">
                        <div className="text-xl font-serif font-bold text-green-600">
                          {data.benchmark || 0}
                        </div>
                        <div className="text-xs text-gray-500 uppercase tracking-wider">
                          ≥ Benchmark
                        </div>
                      </div>
                      
                      <div className="text-center p-2 bg-gray-50 rounded-lg">
                        <div className="text-xl font-serif font-bold text-secondary">
                          {formatMetricValue(metricKey, data.average)}
                        </div>
                        <div className="text-xs text-gray-500 uppercase tracking-wider">
                          Team Avg
                        </div>
                      </div>
                      
                      <div className="text-center p-2 bg-gray-50 rounded-lg">
                        <div className={`text-xl font-serif font-bold ${
                          (isInverse ? data.average < benchmark : data.average > benchmark)
                            ? 'text-green-600' : 'text-orange-600'
                        }`}>
                          {isInverse 
                            ? (data.average < benchmark ? '↓' : '↑')
                            : (data.average > benchmark ? '↑' : '↓')
                          }
                          {Math.abs(((data.average - benchmark) / benchmark) * 100).toFixed(0)}%
                        </div>
                        <div className="text-xs text-gray-500 uppercase tracking-wider">
                          vs Target
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

        {/* Interactive Filtered Results Panel */}
        {activeFilter && (
          <div id="filtered-results" className="mt-8 scroll-mt-8" data-testid="filtered-results-panel">
            <div className="bubba-card border-2 border-primary/30 shadow-lg">
              <div className="p-6">
                {/* Header with filter info and clear button */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      activeFilter.zone === ZONE_TYPES.HIGH ? 'bg-green-100' :
                      activeFilter.zone === ZONE_TYPES.LOW ? 'bg-red-100' :
                      activeFilter.zone === ZONE_TYPES.MEDIUM ? 'bg-yellow-100' :
                      'bg-blue-100'
                    }`}>
                      <Users className={`w-5 h-5 ${
                        activeFilter.zone === ZONE_TYPES.HIGH ? 'text-green-600' :
                        activeFilter.zone === ZONE_TYPES.LOW ? 'text-red-600' :
                        activeFilter.zone === ZONE_TYPES.MEDIUM ? 'text-yellow-600' :
                        'text-blue-600'
                      }`} />
                    </div>
                    <div>
                      <h3 className="text-lg font-serif font-bold text-foreground">
                        {activeFilter.zone === ZONE_TYPES.HIGH && 'Exceeding Target'}
                        {activeFilter.zone === ZONE_TYPES.LOW && 'Below Target'}
                        {activeFilter.zone === ZONE_TYPES.MEDIUM && 'Near Target'}
                        {activeFilter.zone === ZONE_TYPES.AVERAGE && 'Near Team Average'}
                        {' '}— {V2_METRICS[activeFilter.metric]?.label}
                      </h3>
                      <p className="text-sm text-gray-500">
                        {filteredEmployees.length} employee{filteredEmployees.length !== 1 ? 's' : ''} in this zone
                      </p>
                    </div>
                  </div>
                  <Button
                    onClick={clearFilter}
                    variant="outline"
                    size="sm"
                    className="flex items-center gap-2"
                    data-testid="clear-filter-btn"
                  >
                    <X className="w-4 h-4" />
                    Clear Filter
                  </Button>
                </div>
                
                {/* Filtered Employee List */}
                {filteredEmployees.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    <Users className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                    <p>No employees found in this zone</p>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredEmployees.map((emp, idx) => {
                      const metricVal = emp[activeFilter.metric];
                      const config = V2_METRICS[activeFilter.metric];
                      
                      return (
                        <div 
                          key={emp.id}
                          className={`p-4 rounded-lg border-2 transition-all ${
                            activeFilter.zone === ZONE_TYPES.HIGH ? 'border-green-200 bg-green-50/50' :
                            activeFilter.zone === ZONE_TYPES.LOW ? 'border-red-200 bg-red-50/50' :
                            activeFilter.zone === ZONE_TYPES.MEDIUM ? 'border-yellow-200 bg-yellow-50/50' :
                            'border-blue-200 bg-blue-50/50'
                          }`}
                          data-testid={`filtered-employee-${emp.id}`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className={`text-sm font-bold ${
                                  activeFilter.zone === ZONE_TYPES.HIGH ? 'text-green-700' :
                                  activeFilter.zone === ZONE_TYPES.LOW ? 'text-red-700' :
                                  activeFilter.zone === ZONE_TYPES.MEDIUM ? 'text-yellow-700' :
                                  'text-blue-700'
                                }`}>#{idx + 1}</span>
                                <span className="font-semibold text-foreground truncate">{emp.name}</span>
                              </div>
                              {emp.ranking && (
                                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-0.5 rounded-full">
                                  {emp.ranking}
                                </span>
                              )}
                            </div>
                            <div className="text-right shrink-0 ml-2">
                              <div className={`text-lg font-bold ${
                                activeFilter.zone === ZONE_TYPES.HIGH ? 'text-green-600' :
                                activeFilter.zone === ZONE_TYPES.LOW ? 'text-red-600' :
                                activeFilter.zone === ZONE_TYPES.MEDIUM ? 'text-yellow-600' :
                                'text-blue-600'
                              }`}>
                                {config?.format === 'currency' ? formatCurrency(metricVal) : formatNumber(metricVal)}
                              </div>
                              <div className="text-xs text-gray-500">
                                {config?.label}
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

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
          </>
        ) : (
          /* Trends Tab Content */
          <div className="space-y-8" data-testid="trends-content">
            {/* Trend Overview Banner */}
            <div className="bubba-card p-6 bg-gradient-to-r from-primary/5 to-secondary/5">
              <div className="flex items-center gap-4 mb-4">
                <TrendingUp className="w-8 h-8 text-primary" />
                <div>
                  <h2 className="text-xl font-serif font-bold text-foreground">
                    Quarter-over-Quarter Trends
                  </h2>
                  <p className="text-sm text-gray-500">
                    Comparing {trendData?.previous_quarter || 'Previous'} {trendData?.previous_year || ''} → {selectedQuarter} {selectedYear}
                  </p>
                </div>
              </div>
              
              {!trendData?.has_previous_data && (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-800">
                  <Info className="w-5 h-5 inline mr-2" />
                  No previous quarter data available for comparison. Trends will show once multiple quarters have data.
                </div>
              )}
            </div>

            {/* Team Trend Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Team Comparison Chart */}
              <div className="bubba-card">
                <div className="p-5">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-4">
                    📊 Team Average Comparison
                  </h3>
                  <img 
                    src={`${API}/v2/trends/${selectedYear}/${selectedQuarter}/team?chart_type=comparison`}
                    alt="Team Comparison Chart"
                    className="w-full rounded-lg"
                    data-testid="team-comparison-chart"
                  />
                </div>
              </div>

              {/* Tier Distribution Chart */}
              <div className="bubba-card">
                <div className="p-5">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-4">
                    📈 Tier Distribution
                  </h3>
                  <img 
                    src={`${API}/v2/trends/${selectedYear}/${selectedQuarter}/team?chart_type=distribution`}
                    alt="Tier Distribution Chart"
                    className="w-full rounded-lg"
                    data-testid="tier-distribution-chart"
                  />
                </div>
              </div>
            </div>

            {/* Metric Change Cards */}
            {trendData && (
              <div className="bubba-card">
                <div className="p-6">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-4">
                    📉 Team Metric Changes
                  </h3>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    {Object.entries(V2_METRICS).map(([metricKey, metricInfo]) => {
                      const change = trendData.changes?.[metricKey] || 0;
                      const currentVal = trendData.current_averages?.[metricKey] || 0;
                      const isPositive = metricInfo.higherBetter ? change > 0 : change < 0;
                      const isNeutral = change === 0;
                      
                      return (
                        <div 
                          key={metricKey}
                          className={`p-4 rounded-lg border-2 ${
                            isNeutral 
                              ? 'border-gray-200 bg-gray-50'
                              : isPositive 
                                ? 'border-green-200 bg-green-50' 
                                : 'border-red-200 bg-red-50'
                          }`}
                          data-testid={`trend-card-${metricKey}`}
                        >
                          <div className="text-xs text-gray-500 font-medium mb-1">
                            {metricInfo.label}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-bold text-foreground">
                              {metricInfo.format === 'currency' ? '$' : ''}{currentVal?.toFixed(2) || '0'}
                            </span>
                            <span className={`flex items-center text-sm font-semibold ${
                              isNeutral 
                                ? 'text-gray-500'
                                : isPositive 
                                  ? 'text-green-600' 
                                  : 'text-red-600'
                            }`}>
                              {isNeutral ? (
                                <Minus className="w-4 h-4" />
                              ) : isPositive ? (
                                <ArrowUp className="w-4 h-4" />
                              ) : (
                                <ArrowDown className="w-4 h-4" />
                              )}
                              {Math.abs(change).toFixed(1)}%
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}

            {/* Tier Movement Summary */}
            {trendData && trendData.has_previous_data && (
              <div className="bubba-card">
                <div className="p-6">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-4">
                    🔄 Tier Count Changes
                  </h3>
                  <div className="grid grid-cols-5 gap-4">
                    {['Trainer', 'Bartender', 'A-Server', 'B-Server', 'C-Server'].map((tier) => {
                      const currentCount = trendData.current_tier_distribution?.[tier] || 0;
                      const prevCount = trendData.previous_tier_distribution?.[tier] || 0;
                      const diff = currentCount - prevCount;
                      
                      const tierColors = {
                        'Trainer': 'bg-purple-100 border-purple-300 text-purple-700',
                        'Bartender': 'bg-blue-100 border-blue-300 text-blue-700',
                        'A-Server': 'bg-green-100 border-green-300 text-green-700',
                        'B-Server': 'bg-yellow-100 border-yellow-300 text-yellow-700',
                        'C-Server': 'bg-red-100 border-red-300 text-red-700',
                      };
                      
                      return (
                        <div 
                          key={tier}
                          className={`p-4 rounded-lg border-2 text-center ${tierColors[tier]}`}
                        >
                          <div className="text-sm font-medium mb-1">{tier}</div>
                          <div className="text-2xl font-bold">{currentCount}</div>
                          {diff !== 0 && (
                            <div className={`text-xs font-semibold ${diff > 0 ? 'text-green-600' : 'text-red-600'}`}>
                              {diff > 0 ? '+' : ''}{diff} from prev
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}