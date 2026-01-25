import { useState, useEffect } from "react";
import { Trophy, Medal, Award, Download, Users } from "lucide-react";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { formatCurrency, formatLSCRatio, formatNumber, formatOverallRank, formatRanking, getRankingHierarchy, KPI_DEFINITIONS } from "../utils/formatters";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function TopPerformers() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [topPerformers, setTopPerformers] = useState({});
  const [topOverall, setTopOverall] = useState([]);

  useEffect(() => {
    fetchEmployees();
  }, []);

  useEffect(() => {
    if (employees.length > 0) {
      calculateTopPerformers();
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

  const calculateTopPerformers = () => {
    const metrics = ['ppa', 'gpg', 'pplbw', 'lsc_ratio', 'metric_bonus_points', 'cumulative_score'];
    const topPerformersData = {};

    metrics.forEach(metric => {
      let sortedEmployees;

      if (metric === 'lsc_ratio') {
        // For LSC ratio, lower is better
        sortedEmployees = [...employees]
          .filter(emp => emp[metric] != null)
          .sort((a, b) => a[metric] - b[metric])
          .slice(0, 10);
      } else {
        sortedEmployees = [...employees]
          .filter(emp => emp[metric] != null)
          .sort((a, b) => b[metric] - a[metric])
          .slice(0, 10);
      }

      topPerformersData[metric] = sortedEmployees;
    });

    // Top 10 overall = top by cumulative_score
    const overall = [...employees]
      .filter(emp => emp.cumulative_score != null)
      .sort((a, b) => (b.cumulative_score || 0) - (a.cumulative_score || 0))
      .slice(0, 10);

    setTopOverall(overall);
    setTopPerformers(topPerformersData);
  };

  const getMetricIcon = (rank) => {
    if (rank === 1) return <Trophy className="w-5 h-5 text-yellow-500" />;
    if (rank === 2) return <Medal className="w-5 h-5 text-gray-400" />;
    if (rank === 3) return <Award className="w-5 h-5 text-amber-600" />;
    return <span className="w-5 h-5 flex items-center justify-center text-xs font-bold text-gray-600">#{rank}</span>;
  };

  const formatMetricValue = (metric, value) => {
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
          
          <Card className="bubba-card">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Trophy className="w-8 h-8 text-yellow-500" />
                <div>
                  <p className="text-2xl font-bold text-primary">
                    {employees.filter(emp => (emp.cumulative_score || 0) >= 90).length}
                  </p>
                  <p className="text-sm text-muted-foreground">Excellent Performers</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
          <Card className="bubba-card">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Award className="w-8 h-8 text-green-500" />
                <div>
                  <p className="text-2xl font-bold text-primary">
                    {employees.filter(emp => (emp.cumulative_score || 0) >= 80).length}
                  </p>
                  <p className="text-sm text-muted-foreground">Above Average+</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Top 10 Overall */}
        <Card className="bubba-card mb-12 print:mb-6" data-testid="top-overall-card">
          <CardHeader>
            <CardTitle className="text-2xl font-serif text-primary flex items-center gap-3">
              <Trophy className="w-6 h-6 text-yellow-500" />
              Top 10 Overall (Cumulative Score)
            </CardTitle>
            <CardDescription className="text-base">
              Highest overall performers based on Cumulative Score
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {topOverall.map((employee, index) => {
                const ranking = getRankingHierarchy(employee.ranking);
                return (
                  <div
                    key={employee.id}
                    className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-muted/30 transition-colors"
                  >
                    <div className="flex items-center gap-4">
                      <div className="flex items-center justify-center w-10 h-10 bg-muted rounded-full">
                        {getMetricIcon(index + 1)}
                      </div>
                      <div>
                        <h4 className="font-semibold text-primary">{employee.name}</h4>
                        <p className="text-sm text-muted-foreground">{employee.position}</p>
                        {employee.ranking && (
                          <Badge className={`text-xs mt-1 ${ranking.bgColor} ${ranking.color}`}>
                            {employee.ranking} - {ranking.level}
                          </Badge>
                        )}
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-2xl font-serif font-bold text-primary">
                        {formatNumber(employee.cumulative_score)}
                      </div>
                      <div className="text-sm text-muted-foreground">
                        Overall Rank: {formatOverallRank(employee.overall_rank)}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {topOverall.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>No cumulative score data available</p>
              </div>
            )}
          </CardContent>
        </Card>


        {/* Top Performers by Metric */}
        <div className="space-y-12 print:space-y-8">
          {Object.entries(KPI_DEFINITIONS).map(([metricKey, metricInfo]) => {
            const performers = topPerformers[metricKey] || [];
            
            return (
              <Card key={metricKey} className="bubba-card">
                <CardHeader>
                  <CardTitle className="text-2xl font-serif text-primary flex items-center gap-3">
                    <Trophy className="w-6 h-6 text-yellow-500" />
                    Top 10 - {metricInfo.name}
                  </CardTitle>
                  <CardDescription className="text-base">
                    {metricKey === 'lsc_ratio' 
                      ? `Best LSC conversion rates (lower is better) • Benchmark: 1 in 100`
                      : `Highest ${metricInfo.name} performers • Benchmark: ${metricInfo.format === 'currency' ? '$' + metricInfo.benchmark : metricInfo.benchmark}`
                    }
                  </CardDescription>
                </CardHeader>
                
                <CardContent>
                  <div className="space-y-3">
                    {performers.map((employee, index) => {
                      const ranking = getRankingHierarchy(employee.ranking);
                      
                      return (
                        <div key={employee.id} className="flex items-center justify-between p-4 border border-border rounded-lg hover:bg-muted/30 transition-colors">
                          <div className="flex items-center gap-4">
                            <div className="flex items-center justify-center w-10 h-10 bg-muted rounded-full">
                              {getMetricIcon(index + 1)}
                            </div>
                            
                            <div>
                              <h4 className="font-semibold text-primary">{employee.name}</h4>
                              <p className="text-sm text-muted-foreground">{employee.position}</p>
                              {employee.ranking && (
                                <Badge className={`text-xs mt-1 ${ranking.bgColor} ${ranking.color}`}>
                                  {employee.ranking} - {ranking.level}
                                </Badge>
                              )}
                            </div>
                          </div>
                          
                          <div className="text-right">
                            <div className="text-2xl font-serif font-bold text-primary">
                              {formatMetricValue(metricKey, employee[metricKey])}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              Overall Rank: {formatOverallRank(employee.overall_rank)}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  
                  {performers.length === 0 && (
                    <div className="text-center py-8 text-muted-foreground">
                      <Users className="w-12 h-12 mx-auto mb-2 opacity-50" />
                      <p>No performance data available for this metric</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
        
        {/* Footer for print */}
        <div className="hidden print:block mt-12 pt-6 border-t text-center text-sm text-muted-foreground">
          <p>🦐 Bubba Gump Shrimp Co. Las Vegas • Top Performers Report • Generated {new Date().toLocaleDateString()} 🦐</p>
        </div>
      </div>
    </div>
  );
}