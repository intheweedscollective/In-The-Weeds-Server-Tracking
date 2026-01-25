import { useState, useEffect } from "react";
import { BarChart3, TrendingUp, Target, Download } from "lucide-react";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { formatCurrency, formatLSCRatio, formatNumber, KPI_DEFINITIONS } from "../utils/formatters";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Analytics() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState({});


  const handlePrint = async () => {
    try {
      const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent);

      // iOS often “downloads” without opening; users then print the webpage instead.
      // Opening the PDF in a new tab ensures the print/share action targets the PDF.
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
    const valid = employees.filter((e) => e[metric] != null);

    const sorted = [...valid].sort((a, b) => {
      if (metric === "lsc_ratio") return (a[metric] || 0) - (b[metric] || 0);
      return (b[metric] || 0) - (a[metric] || 0);
    });

    return sorted.slice(0, limit);
  };

  const formatMetricValue = (metric, value) => {
    if (value == null) return "N/A";
    switch (metric) {
      case "ppa":
      case "gpg":
      case "pplbw":
        return formatCurrency(value);
      case "lsc_ratio":
        return formatLSCRatio(value);
      default:
        return formatNumber(value);
    }
  };

  useEffect(() => {
    fetchEmployees();
  }, []);

  useEffect(() => {
    if (employees.length > 0) {
      calculateAnalytics();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employees]);

  const fetchEmployees = async () => {
    try {
      const response = await axios.get(`${API}/employees`);
      setEmployees(response.data);
    } catch (error) {
      console.error("Error fetching employees:", error);
    } finally {
      setLoading(false);
    }
  };

  const calculateAnalytics = () => {
    const metrics = ['ppa', 'gpg', 'pplbw', 'lsc_ratio', 'metric_bonus_points', 'cumulative_score'];
    const analyticsData = {};

    metrics.forEach(metric => {
      const validValues = employees
        .map(emp => emp[metric])
        .filter(val => val != null && !isNaN(val));
      
      if (validValues.length === 0) {
        analyticsData[metric] = { high: 0, medium: 0, low: 0, benchmark: 0, average: 0, total: 0 };
        return;
      }

      // Benchmark-relative buckets (more meaningful than splitting into thirds)
      const benchmark = KPI_DEFINITIONS[metric]?.benchmark || 0;
      const average = validValues.reduce((sum, val) => sum + val, 0) / validValues.length;

      let highThreshold = 0;
      let lowThreshold = 0;

      if (metric === 'lsc_ratio') {
        // Inverse metric. Values are denominators ("1 in X"). Lower is better.
        // Benchmark is 0.01 => "1 in 100".
        const benchmarkDenominator = Math.round(1 / benchmark);
        highThreshold = Math.round(benchmarkDenominator * 0.9); // 10% better
        lowThreshold = Math.round(benchmarkDenominator * 1.1); // 10% worse

        let high = 0, medium = 0, low = 0, aboveBenchmark = 0;

        validValues.forEach(val => {
          if (val <= highThreshold) high++;
          else if (val >= lowThreshold) low++;
          else medium++;

          if (val <= benchmarkDenominator) aboveBenchmark++;
        });

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
        };

        return;
      }

      // Normal metrics where higher is better
      highThreshold = benchmark ? benchmark * 1.1 : 0; // 10% above
      lowThreshold = benchmark ? benchmark * 0.9 : 0; // 10% below

      let high = 0, medium = 0, low = 0, aboveBenchmark = 0;

      validValues.forEach(val => {
        if (benchmark) {
          if (val >= highThreshold) high++;
          else if (val < lowThreshold) low++;
          else medium++;

          if (val >= benchmark) aboveBenchmark++;
        } else {
          // No benchmark defined; keep everything as medium but still compute average.
          medium++;
        }
      });

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
      };
      
      analyticsData[metric] = {
        high,
        medium, 
        low,
        benchmark: aboveBenchmark,
        average,
        total: validValues.length,
        highThreshold,
        lowThreshold,
        benchmarkValue: benchmark
      };
    });

    setAnalytics(analyticsData);
  };

  const getPercentage = (count, total) => {
    if (total === 0) return 0;
    return Math.round((count / total) * 100);
  };

  const formatMetricValueOld = (metric, value) => {
    switch (metric) {
      case 'ppa':
      case 'gpg':
      case 'pplbw':
        return formatCurrency(value);
      case 'lsc_ratio':
        return formatLSCRatio(value);
      case 'metric_bonus_points':
      case 'cumulative_score':
        return formatNumber(value);
      default:
        return value?.toString() || 'N/A';
    }
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
          
          <Card className="bubba-card">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Target className="w-8 h-8 text-yellow-500" />
                <div>
                  <p className="text-2xl font-bold text-primary">
                    {getPercentage(
                      Object.values(analytics).reduce((sum, metric) => sum + (metric.medium || 0), 0),
                      Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                    )}%
                  </p>
                  <p className="text-sm text-muted-foreground">Medium Performers</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bubba-card">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <BarChart3 className="w-8 h-8 text-orange-500" />
                <div>
                  <p className="text-2xl font-bold text-primary">
                    {getPercentage(
                      Object.values(analytics).reduce((sum, metric) => sum + (metric.low || 0), 0),
                      Object.values(analytics).reduce((sum, metric) => sum + (metric.total || 0), 0)
                    )}%
                  </p>
                  <p className="text-sm text-muted-foreground">Needs Improvement</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Analytics by Metric */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {Object.entries(KPI_DEFINITIONS).map(([metricKey, metricInfo]) => {
            const data = analytics[metricKey] || {};
            const total = data.total || 1;
            
            return (
              <Card key={metricKey} className="bubba-card">
                <CardHeader>
                  <CardTitle className="text-xl font-serif text-primary">
                    {metricInfo.name}
                  </CardTitle>
                  <CardDescription>
                    Benchmark: {metricInfo.format === 'currency' ? '$' + metricInfo.benchmark : 
                              metricKey === 'lsc_ratio' ? '1 in 100' : metricInfo.benchmark}
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-4">
                    {/* Performance Distribution Bar */}
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm font-medium">
                        <span>Performance Distribution</span>
                        <span>{total} employees</span>
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
                      <div className="flex justify-between text-xs text-muted-foreground">
                        <span>High ({data.high})</span>
                        <span>Medium ({data.medium})</span>
                        <span>Low ({data.low})</span>
                      </div>
                    </div>
                    
                    {/* Key Metrics */}
                    <div className="grid grid-cols-2 gap-4 pt-4 border-t">
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-green-600">
                          {data.benchmark || 0}
                        </div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wider">
                          Above Benchmark
                        </div>
                      </div>
                      
                      <div className="text-center">
                        <div className="text-2xl font-serif font-bold text-primary">
                          {formatMetricValueOld(metricKey, data.average)}
                        </div>
                        <div className="text-xs text-muted-foreground uppercase tracking-wider">
                          Team Average
                        </div>
                      </div>
                    </div>
                    
                    {/* Benchmark Status */}
                    <div className="pt-2">
                      <Badge 
                        className={`w-full justify-center ${
                          getPercentage(data.benchmark, total) >= 60 
                            ? 'bg-green-100 text-green-800' 
                            : getPercentage(data.benchmark, total) >= 40
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {getPercentage(data.benchmark, total)}% Meeting Benchmark
                      </Badge>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Top 10 Overall + Top 10 per Metric */}
        <div className="mt-12 space-y-10">
          <div className="space-y-4" data-testid="analytics-top-overall">
            <h2 className="text-2xl font-serif font-bold text-primary">Top 10 Overall (Cumulative Score)</h2>
            <Card className="bubba-card">
              <CardContent className="pt-6">
                <div className="space-y-2">
                  {getTopEmployees("cumulative_score", 10).map((emp, idx) => (
                    <div
                      key={emp.id}
                      className="flex items-center justify-between p-3 border border-border rounded-lg bg-background"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-primary">#{idx + 1}</span>
                          <span className="font-semibold text-primary truncate">{emp.name}</span>
                          {emp.ranking && (
                            <Badge variant="secondary" className="text-xs">
                              {emp.ranking}
                            </Badge>
                          )}
                        </div>
                        <div className="text-sm text-muted-foreground truncate">{emp.position}</div>
                        <div className="text-xs text-muted-foreground">Overall Rank: {emp.overall_rank || "N/A"}</div>
                      </div>

                      <div className="text-right shrink-0">
                        <div className="font-bold text-primary">
                          {formatMetricValue("cumulative_score", emp.cumulative_score)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4" data-testid="analytics-top-10-metrics">
            <h2 className="text-2xl font-serif font-bold text-primary">Top 10 by Metric</h2>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {Object.keys(KPI_DEFINITIONS).map((metric) => {
                const metricInfo = KPI_DEFINITIONS[metric];
                const top = getTopEmployees(metric, 10);

                return (
                  <Card key={metric} className="bubba-card">
                    <CardHeader>
                      <CardTitle className="text-xl font-serif text-primary">
                        {metricInfo.shortName} — {metricInfo.name}
                      </CardTitle>
                      <CardDescription>Top 10 employees for this metric</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        {top.map((emp, idx) => (
                          <div
                            key={emp.id}
                            className="flex items-center justify-between p-3 border border-border rounded-lg bg-background"
                          >
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-semibold text-primary">#{idx + 1}</span>
                                <span className="font-semibold text-primary truncate">{emp.name}</span>
                                {emp.ranking && (
                                  <Badge variant="secondary" className="text-xs">
                                    {emp.ranking}
                                  </Badge>
                                )}
                              </div>
                              <div className="text-sm text-muted-foreground truncate">{emp.position}</div>
                              <div className="text-xs text-muted-foreground">Overall Rank: {emp.overall_rank || "N/A"}</div>
                            </div>

                            <div className="text-right shrink-0">
                              <div className="font-bold text-primary">
                                {formatMetricValue(metric, emp[metric])}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}