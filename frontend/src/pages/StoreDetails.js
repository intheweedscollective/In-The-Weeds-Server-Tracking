import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { Building2, MapPin, Users, BarChart3, Trophy, ArrowLeft, Settings, TrendingUp, Target, Clock, Globe } from "lucide-react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";

export default function StoreDetails() {
  const { storeId } = useParams();
  const [store, setStore] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const currentQ = getCurrentQuarter();
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);

  useEffect(() => {
    fetchStoreDetails();
  }, [storeId, selectedYear, selectedQuarter]);

  const fetchStoreDetails = async () => {
    try {
      setLoading(true);
      const [storeRes, statsRes] = await Promise.all([
        api.get(`/stores/${storeId}`),
        api.get(`/stores/${storeId}/stats?quarter=${selectedQuarter}&year=${selectedYear}`)
      ]);
      setStore(storeRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error('Failed to fetch store details:', error);
      toast.error('Failed to load store details');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background p-8 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full"></div>
      </div>
    );
  }

  if (!store) {
    return (
      <div className="min-h-screen bg-background p-8">
        <div className="text-center">
          <Building2 className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-white mb-2">Store Not Found</h2>
          <Link to="/stores">
            <Button variant="outline">Back to Stores</Button>
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background p-4 md:p-8" data-testid="store-details-page">
      {/* Header */}
      <div className="mb-6">
        <Link to="/stores" className="inline-flex items-center text-slate-400 hover:text-white mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Stores
        </Link>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-primary/20 to-cyan-500/20 flex items-center justify-center border border-primary/30">
              <Building2 className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-white">{store.name}</h1>
              <div className="flex items-center gap-3 mt-1">
                <span className="px-2 py-0.5 bg-primary/20 text-primary rounded text-sm font-mono">
                  {store.code}
                </span>
                <span className="flex items-center gap-1 text-slate-400">
                  <MapPin className="w-4 h-4" />
                  {store.city}, {store.state}
                </span>
                {store.region && (
                  <span className="px-2 py-0.5 bg-slate-700 rounded text-sm text-slate-300">
                    {store.region}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white"
            >
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
            </select>
            <select
              value={selectedQuarter}
              onChange={(e) => setSelectedQuarter(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white"
            >
              <option value="Q1">Q1</option>
              <option value="Q2">Q2</option>
              <option value="Q3">Q3</option>
              <option value="Q4">Q4</option>
            </select>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-5 h-5 text-cyan-400" />
            <span className="text-sm text-slate-400">Employees</span>
          </div>
          <p className="text-3xl font-bold text-white">{stats?.total_employees || 0}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-5 h-5 text-emerald-400" />
            <span className="text-sm text-slate-400">Avg Score</span>
          </div>
          <p className="text-3xl font-bold text-white">{stats?.average_score || 0}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Trophy className="w-5 h-5 text-amber-400" />
            <span className="text-sm text-slate-400">Top Score</span>
          </div>
          <p className="text-3xl font-bold text-white">
            {stats?.top_performers?.[0]?.score?.toFixed(1) || '-'}
          </p>
        </div>
        <div className="bg-slate-800 rounded-xl p-5 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Globe className="w-5 h-5 text-violet-400" />
            <span className="text-sm text-slate-400">Timezone</span>
          </div>
          <p className="text-lg font-medium text-white truncate">{store.timezone || 'America/Chicago'}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Performers */}
        <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
          <div className="p-5 border-b border-slate-700 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
                <Trophy className="w-5 h-5 text-amber-400" />
              </div>
              <div>
                <h2 className="font-bold text-white">Top Performers</h2>
                <p className="text-xs text-slate-500">{selectedQuarter} {selectedYear}</p>
              </div>
            </div>
          </div>
          <div className="divide-y divide-slate-700">
            {stats?.top_performers?.length > 0 ? (
              stats.top_performers.map((emp, idx) => (
                <div key={emp.name} className="flex items-center justify-between p-4">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                      idx === 0 ? 'bg-amber-500 text-white' :
                      idx === 1 ? 'bg-slate-400 text-white' :
                      idx === 2 ? 'bg-amber-700 text-white' :
                      'bg-slate-600 text-slate-300'
                    }`}>
                      {idx + 1}
                    </div>
                    <span className="font-medium text-white">{emp.name}</span>
                  </div>
                  <span className="text-lg font-bold text-primary">{emp.score?.toFixed(2)}</span>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-slate-400">
                No employee data for this period
              </div>
            )}
          </div>
        </div>

        {/* Metric Averages */}
        <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
          <div className="p-5 border-b border-slate-700 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
              <BarChart3 className="w-5 h-5 text-cyan-400" />
            </div>
            <div>
              <h2 className="font-bold text-white">Store Metrics</h2>
              <p className="text-xs text-slate-500">Average performance</p>
            </div>
          </div>
          <div className="p-5 space-y-4">
            {stats?.metric_averages ? (
              <>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">PPA (Per Person Average)</span>
                    <span className="text-white font-medium">${stats.metric_averages.ppa?.toFixed(2)}</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-cyan-500 to-cyan-400 rounded-full"
                      style={{ width: `${Math.min((stats.metric_averages.ppa / 60) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">LBW per Guest</span>
                    <span className="text-white font-medium">${stats.metric_averages.lbw_per_guest?.toFixed(2)}</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full"
                      style={{ width: `${Math.min((stats.metric_averages.lbw_per_guest / 12) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">Glassware per Guest</span>
                    <span className="text-white font-medium">${stats.metric_averages.glassware_per_guest?.toFixed(2)}</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-violet-500 to-violet-400 rounded-full"
                      style={{ width: `${Math.min((stats.metric_averages.glassware_per_guest / 2) * 100, 100)}%` }}
                    />
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-slate-400">Guests per LSC</span>
                    <span className="text-white font-medium">{stats.metric_averages.guests_per_lsc?.toFixed(1)}</span>
                  </div>
                  <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gradient-to-r from-amber-500 to-amber-400 rounded-full"
                      style={{ width: `${Math.min((100 / stats.metric_averages.guests_per_lsc) * 100, 100)}%` }}
                    />
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center text-slate-400 py-8">
                No metric data available
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Store Info */}
      <div className="mt-6 bg-slate-800 rounded-2xl border border-slate-700 p-5">
        <h3 className="font-bold text-white mb-4 flex items-center gap-2">
          <Settings className="w-5 h-5 text-slate-400" />
          Store Information
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-slate-400">Brand</p>
            <p className="text-white font-medium">{store.brand}</p>
          </div>
          <div>
            <p className="text-sm text-slate-400">Status</p>
            <p className={`font-medium ${store.is_active ? 'text-emerald-400' : 'text-red-400'}`}>
              {store.is_active ? 'Active' : 'Inactive'}
            </p>
          </div>
          <div>
            <p className="text-sm text-slate-400">Created</p>
            <p className="text-white font-medium">
              {store.created_at ? new Date(store.created_at).toLocaleDateString() : '-'}
            </p>
          </div>
          <div>
            <p className="text-sm text-slate-400">Address</p>
            <p className="text-white font-medium">{store.address || 'Not set'}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
