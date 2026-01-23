import { useState, useEffect } from "react";
import { ArrowLeft, Trophy, Medal, Award, Printer, Users } from "lucide-react";
import { Link } from "react-router-dom";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { formatCurrency, formatLSCRatio, formatNumber, formatOverallRank, formatRanking, getRankingHierarchy, KPI_DEFINITIONS } from "../utils/formatters";

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
        // For LSC ratio, lower is better (closer to benchmark of 1 in 100)
        sortedEmployees = [...employees]
          .filter(emp => emp[metric] != null)
          .sort((a, b) => a[metric] - b[metric])
          .slice(0, 10);
      } else {
        // For other metrics, higher is better
        sortedEmployees = [...employees]
          .filter(emp => emp[metric] != null)
          .sort((a, b) => b[metric] - a[metric])
          .slice(0, 10);
      }
      
      topPerformersData[metric] = sortedEmployees;
    });

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

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-paper-bg">
        <Navigation />
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper-bg">
      <Navigation />
      
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-4">
            <Link to="/" className="print:hidden">
              <Button variant="outline" size="sm">
                <ArrowLeft className="w-4 h-4 mr-2" />
                Back to Dashboard
              </Button>
            </Link>
            <div>
              <h1 className="text-3xl font-serif font-bold text-primary mb-2" data-testid="page-title">
                🏆 Top Performers Report
              </h1>
              <p className="text-muted-foreground" data-testid="page-subtitle">
                Top 10 employees in each performance metric • Management Review
              </p>
            </div>
          </div>
          
          <Button onClick={handlePrint} className="bubba-btn-primary print:hidden" data-testid="print-btn">
            <Printer className="w-4 h-4 mr-2" />
            Print Report
          </Button>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12 print:mb-6">
          <Card className="bubba-card">
            <CardContent className="pt-6">
              <div className="flex items-center gap-3">
                <Users className="w-8 h-8 text-primary" />
                <div>
                  <p className="text-2xl font-bold text-primary">{employees.length}</p>
                  <p className="text-sm text-muted-foreground">Total Employees</p>
                </div>
              </div>
            </CardContent>
          </Card>
          
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