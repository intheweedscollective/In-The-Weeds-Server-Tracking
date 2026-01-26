import { useState, useEffect, useCallback, useMemo } from "react";
import { Trophy, Medal, Award, Download, Users, Calendar } from "lucide-react";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { formatCurrency, formatNumber } from "../utils/formatters";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// V2 Metrics Configuration
const V2_METRICS = {
  ppa: { label: 'PPA', format: 'currency', higherBetter: true },
  lbw_per_guest: { label: 'LBW/Guest', format: 'currency', higherBetter: true },
  glassware_per_guest: { label: 'Glass/Guest', format: 'currency', higherBetter: true },
  guests_per_lsc: { label: 'Guests/LSC', format: 'number', higherBetter: false },
  cv_score: { label: 'CV Score', format: 'number', higherBetter: true },
  pre_dar_score: { label: 'Total Score', format: 'number', higherBetter: true },
};

export default function TopPerformers() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // V2 Quarter Selection
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");

  const fetchEmployees = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/v2/employees?year=${selectedYear}&quarter=${selectedQuarter}`);
      setEmployees(response.data);
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

  const getTopEmployees = (metric, limit = 10) => {
    const config = V2_METRICS[metric];
    const valid = employees.filter((e) => e[metric] != null);

    const sorted = [...valid].sort((a, b) => {
      if (!config.higherBetter) return (a[metric] || 0) - (b[metric] || 0);
      return (b[metric] || 0) - (a[metric] || 0);
    });

    return sorted.slice(0, limit);
  };

  const getRankBadge = (rank) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-600" />;
    return <span className="w-5 h-5 flex items-center justify-center font-bold text-gray-500">#{rank}</span>;
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

  // Computed values
  const topOverall = useMemo(() => {
    return getTopEmployees('pre_dar_score', 10);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employees]);

  const topPerformers = useMemo(() => {
    const result = {};
    Object.keys(V2_METRICS).forEach(metric => {
      result[metric] = getTopEmployees(metric, 10);
    });
    return result;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employees]);

  const getMetricIcon = (rank) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-600" />;
    return <span className="text-sm font-bold text-gray-500">#{rank}</span>;
  };

  const handlePrint = async () => {
    try {
      const response = await axios.get(`${API}/top-performers/pdf`, {
        responseType: "blob",
      });

      const blob = new Blob([response.data], { type: "application/pdf" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "top_performers_report.pdf";
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      toast.success("Top Performers PDF downloaded");
    } catch (error) {
      console.error(error);
      toast.error("Could not download Top Performers PDF");
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
      <div className="splash-red" style={{ top: '8%', right: '5%' }} />
      <div className="splash-blue" style={{ bottom: '15%', left: '3%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Trophy className="w-8 h-8 text-yellow-500" />
              <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
                Top Performers
              </h1>
            </div>
            <p className="text-gray-500" data-testid="page-subtitle">
              Top 10 crew members in each performance metric
            </p>
          </div>

          <Button
            onClick={handlePrint}
            className="bubba-btn-primary w-full sm:w-auto print:hidden"
            data-testid="print-btn"
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
            data-testid="year-select"
          >
            <option value={2024}>2024</option>
            <option value={2025}>2025</option>
            <option value={2026}>2026</option>
            <option value={2027}>2027</option>
          </select>
          
          <select
            value={selectedQuarter}
            onChange={(e) => setSelectedQuarter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            data-testid="quarter-select"
          >
            <option value="Q1">Q1</option>
            <option value="Q2">Q2</option>
            <option value="Q3">Q3</option>
            <option value="Q4">Q4</option>
          </select>
          
          <span className="ml-auto text-sm text-gray-500">
            {employees.length} crew members
          </span>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-10 print:mb-6">
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center">
                <Users className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-primary">{employees.length}</p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Total Crew</p>
              </div>
            </div>
          </div>
          
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-yellow-100 flex items-center justify-center">
                <Trophy className="w-6 h-6 text-yellow-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-yellow-600">
                  {employees.filter(emp => (emp.pre_dar_score || 0) >= 90).length}
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Excellent</p>
              </div>
            </div>
          </div>
          
          <div className="bubba-card p-5">
            <div className="flex items-center gap-3">
              <div className="w-12 h-12 rounded-full bg-green-100 flex items-center justify-center">
                <Award className="w-6 h-6 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-serif font-bold text-green-600">
                  {employees.filter(emp => (emp.pre_dar_score || 0) >= 80).length}
                </p>
                <p className="text-xs text-gray-500 font-semibold uppercase">Above Average+</p>
              </div>
            </div>
          </div>
        </div>

        {/* Top 10 Overall */}
        <div className="bubba-card mb-10 print:mb-6" data-testid="top-overall-card">
          <div className="p-5">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-yellow-100 flex items-center justify-center">
                <Trophy className="w-5 h-5 text-yellow-600" />
              </div>
              <div>
                <h2 className="text-xl font-serif font-bold text-foreground">Top 10 Overall</h2>
                <p className="text-sm text-gray-500">Highest performers by Total Score</p>
              </div>
            </div>
            
            <div className="space-y-3">
              {topOverall.map((employee, index) => {
                return (
                  <div
                    key={employee.id}
                    className="flex items-center justify-between p-4 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex items-center justify-center w-10 h-10 bg-gray-100 rounded-full">
                        {getMetricIcon(index + 1)}
                      </div>
                      <div>
                        <h4 className="font-semibold text-foreground">{employee.name}</h4>
                        <p className="text-sm text-gray-500">{employee.performance_tier || 'Not Assessed'}</p>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-2xl font-serif font-bold text-primary">
                        {formatNumber(employee.pre_dar_score)}
                      </div>
                      <div className="text-sm text-gray-500">
                        Total Score
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {topOverall.length === 0 && (
              <div className="text-center py-8 text-gray-400">
                <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>No total score data available</p>
              </div>
            )}
          </div>
        </div>


        {/* Top Performers by Metric */}
        <div className="space-y-8 print:space-y-6">
          {Object.entries(V2_METRICS).map(([metricKey, metricInfo]) => {
            const performers = topPerformers[metricKey] || [];
            
            return (
              <div key={metricKey} className="bubba-card">
                <div className="p-5">
                  <h3 className="text-lg font-serif font-bold text-foreground mb-1">
                    Top 10 - {metricInfo.label}
                  </h3>
                  <p className="text-sm text-gray-500 mb-4">
                    {!metricInfo.higherBetter 
                      ? `Best ${metricInfo.label} performers (lower is better)`
                      : `Highest ${metricInfo.label} performers`
                    }
                  </p>
                
                  <div className="space-y-2">
                    {performers.map((employee, index) => {
                      return (
                        <div key={employee.id} className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
                          <div className="flex items-center gap-3">
                            <div className="flex items-center justify-center w-8 h-8 bg-gray-100 rounded-full text-sm font-bold text-primary">
                              {index + 1}
                            </div>
                            
                            <div>
                              <h4 className="font-semibold text-foreground text-sm">{employee.name}</h4>
                              <p className="text-xs text-gray-500">{employee.performance_tier || 'Not Assessed'}</p>
                            </div>
                          </div>
                          
                          <div className="text-right">
                            <div className="text-lg font-serif font-bold text-primary">
                              {formatMetricValue(metricKey, employee[metricKey])}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  
                  {performers.length === 0 && (
                    <div className="text-center py-8 text-gray-400">
                      <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p>No performance data available for this metric</p>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        
        {/* Footer for print */}
        <div className="hidden print:block mt-12 pt-6 border-t text-center text-sm text-gray-400">
          <p>Bubba Gump Shrimp Co. Las Vegas • Top Performers Report • Generated {new Date().toLocaleDateString()}</p>
        </div>
      </div>
    </div>
  );
}