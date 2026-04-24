import { useState, useEffect } from "react";
import { QrCode, Star, TrendingUp, Users, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";

export default function QRDashboard() {
  const [stats, setStats] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, employeesRes] = await Promise.all([
        api.get('/qr/stats'),
        api.get('/qr/employees')
      ]);
      setStats(statsRes.data);
      setEmployees(employeesRes.data);
    } catch (error) {
      toast.error("Failed to load QR data");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const StatCard = ({ label, value, icon: Icon, color }) => (
    <div className="bg-white/5 backdrop-blur-sm rounded-2xl p-6 border border-white/10">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-slate-400 text-sm">{label}</p>
          <p className={`text-3xl font-bold mt-1 ${color}`}>{value}</p>
        </div>
        <div className={`p-3 rounded-xl ${color.replace('text-', 'bg-')}/20`}>
          <Icon className={`w-6 h-6 ${color}`} />
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <QrCode className="w-8 h-8 text-red-400" />
              QR Track Hub
            </h1>
            <p className="text-slate-400 mt-1">Track your team's QR code performance</p>
          </div>
          <Button onClick={fetchData} variant="outline" className="border-slate-600">
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <StatCard 
            label="Total Scans" 
            value={stats?.total_scans || 0} 
            icon={QrCode} 
            color="text-blue-400" 
          />
          <StatCard 
            label="Yelp Scans" 
            value={stats?.yelp_scans || 0} 
            icon={Star} 
            color="text-red-400" 
          />
          <StatCard 
            label="Google Scans" 
            value={stats?.google_scans || 0} 
            icon={TrendingUp} 
            color="text-green-400" 
          />
          <StatCard 
            label="TripAdvisor Scans" 
            value={stats?.tripadvisor_scans || 0} 
            icon={Star} 
            color="text-emerald-400" 
          />
          <StatCard 
            label="Total Employees" 
            value={stats?.total_employees || 0} 
            icon={Users} 
            color="text-purple-400" 
          />
        </div>

        {/* Employee List */}
        <div className="bg-white/5 backdrop-blur-sm rounded-2xl border border-white/10 overflow-hidden">
          <div className="p-6 border-b border-white/10">
            <h2 className="text-xl font-semibold text-white flex items-center gap-2">
              <Users className="w-5 h-5 text-slate-400" />
              All Employees
              <span className="text-sm text-slate-400 font-normal">({employees.length} total)</span>
            </h2>
          </div>
          
          <div className="divide-y divide-white/5">
            {employees.map((emp, idx) => {
              const yelp = emp.yelp_clicks || 0;
              const google = emp.google_clicks || 0;
              const tripadvisor = emp.tripadvisor_clicks || 0;
              return (
              <div key={emp.id} className="flex items-center justify-between p-4 hover:bg-white/5 transition-colors">
                <div className="flex items-center gap-4">
                  <span className="text-2xl font-bold text-slate-500 w-12">#{idx + 1}</span>
                  <span className="text-white font-medium">{emp.name}</span>
                </div>
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <p className="text-2xl font-bold text-red-400">{yelp}</p>
                    <p className="text-xs text-slate-500">Yelp</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold text-green-400">{google}</p>
                    <p className="text-xs text-slate-500">Google</p>
                  </div>
                  <div className="text-center">
                    <p className="text-2xl font-bold text-emerald-400">{tripadvisor}</p>
                    <p className="text-xs text-slate-500">TripAdvisor</p>
                  </div>
                  <div className="text-center min-w-[60px]">
                    <p className="text-2xl font-bold text-blue-400">{yelp + google + tripadvisor}</p>
                    <p className="text-xs text-slate-500">Total</p>
                  </div>
                </div>
              </div>
              );
            })}
            
            {employees.length === 0 && !loading && (
              <div className="p-8 text-center text-slate-400">
                No employees found. Sync from main employee list or add manually.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
