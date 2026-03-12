import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Building2, MapPin, Plus, Search, Filter, Settings, BarChart3, Trophy, Users, ChevronRight, Globe } from "lucide-react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import api from "../lib/api";

export default function StoreManagement() {
  const [stores, setStores] = useState([]);
  const [regions, setRegions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [showAddModal, setShowAddModal] = useState(false);
  const [globalStats, setGlobalStats] = useState(null);

  useEffect(() => {
    fetchStores();
    fetchGlobalStats();
  }, [selectedRegion]);

  const fetchStores = async () => {
    try {
      setLoading(true);
      let url = '/stores';
      if (selectedRegion) {
        url += `?region=${encodeURIComponent(selectedRegion)}`;
      }
      const response = await api.get(url);
      setStores(response.data.stores || []);
      setRegions(response.data.regions || []);
    } catch (error) {
      console.error('Failed to fetch stores:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchGlobalStats = async () => {
    try {
      const response = await api.get('/stores/reports/leaderboard?quarter=Q1&year=2026');
      setGlobalStats(response.data);
    } catch (error) {
      console.error('Failed to fetch global stats:', error);
    }
  };

  const initializeStores = async () => {
    try {
      const response = await api.post('/stores/initialize');
      if (response.data.success) {
        toast.success(`Created ${response.data.stores_created} stores`);
        fetchStores();
      } else {
        toast.info(response.data.message);
      }
    } catch (error) {
      toast.error('Failed to initialize stores');
    }
  };

  const filteredStores = stores.filter(store => 
    store.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    store.code.toLowerCase().includes(searchQuery.toLowerCase()) ||
    store.city?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Get store stats from leaderboard data
  const getStoreRank = (storeId) => {
    if (!globalStats?.leaderboard) return null;
    const store = globalStats.leaderboard.find(s => s.store_id === storeId);
    return store?.rank || null;
  };

  return (
    <div className="min-h-screen bg-background p-4 md:p-8" data-testid="store-management-page">
      {/* Header */}
      <div className="mb-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
              <Building2 className="w-8 h-8 text-primary" />
              Store Management
            </h1>
            <p className="text-slate-400 mt-1">
              Manage {stores.length} restaurant locations across {regions.length} regions
            </p>
          </div>
          <div className="flex items-center gap-2">
            {stores.length === 0 && (
              <Button
                onClick={initializeStores}
                className="bg-emerald-600 hover:bg-emerald-700"
                data-testid="init-stores-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Initialize Default Stores
              </Button>
            )}
            <Link to="/stores/leaderboard">
              <Button variant="outline" className="border-slate-600">
                <Trophy className="w-4 h-4 mr-2" />
                Store Leaderboard
              </Button>
            </Link>
          </div>
        </div>
      </div>

      {/* Global Stats Banner */}
      {globalStats && globalStats.leaderboard?.length > 0 && (
        <div className="bg-gradient-to-r from-violet-600/20 to-cyan-600/20 rounded-2xl border border-violet-500/30 p-5 mb-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-violet-500/30 flex items-center justify-center">
                <Globe className="w-6 h-6 text-violet-400" />
              </div>
              <div>
                <h2 className="text-lg font-bold text-white">Global Performance</h2>
                <p className="text-sm text-slate-400">Q1 2026 across all locations</p>
              </div>
            </div>
            <div className="flex items-center gap-8">
              <div className="text-center">
                <p className="text-2xl font-bold text-white">{globalStats.total_stores}</p>
                <p className="text-xs text-slate-400">Active Stores</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-emerald-400">
                  {globalStats.leaderboard[0]?.store_name?.split(' ').pop() || '-'}
                </p>
                <p className="text-xs text-slate-400">#1 Location</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col md:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input
            type="text"
            placeholder="Search stores by name, code, or city..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-400 focus:outline-none focus:border-primary"
            data-testid="store-search"
          />
        </div>
        <select
          value={selectedRegion}
          onChange={(e) => setSelectedRegion(e.target.value)}
          className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-primary"
          data-testid="region-filter"
        >
          <option value="">All Regions</option>
          {regions.map(region => (
            <option key={region} value={region}>{region}</option>
          ))}
        </select>
      </div>

      {/* Store Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="bg-slate-800 rounded-xl p-5 border border-slate-700 animate-pulse">
              <div className="h-6 bg-slate-700 rounded w-3/4 mb-3"></div>
              <div className="h-4 bg-slate-700 rounded w-1/2"></div>
            </div>
          ))}
        </div>
      ) : filteredStores.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredStores.map(store => {
            const rank = getStoreRank(store.id);
            const storeStats = globalStats?.leaderboard?.find(s => s.store_id === store.id);
            
            return (
              <Link
                key={store.id}
                to={`/stores/${store.id}`}
                className="block"
              >
                <div className="bg-slate-800 rounded-xl p-5 border border-slate-700 hover:border-primary/50 transition-all hover:shadow-lg hover:shadow-primary/10 group">
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      {rank && rank <= 3 ? (
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold ${
                          rank === 1 ? 'bg-amber-500 text-white' :
                          rank === 2 ? 'bg-slate-400 text-white' :
                          'bg-amber-700 text-white'
                        }`}>
                          #{rank}
                        </div>
                      ) : (
                        <div className="w-10 h-10 rounded-xl bg-slate-700 flex items-center justify-center">
                          <Building2 className="w-5 h-5 text-slate-400" />
                        </div>
                      )}
                      <div>
                        <h3 className="font-semibold text-white group-hover:text-primary transition-colors">
                          {store.name.replace('Bubba Gump ', '')}
                        </h3>
                        <p className="text-xs text-slate-400">{store.code}</p>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-slate-500 group-hover:text-primary transition-colors" />
                  </div>
                  
                  <div className="flex items-center gap-2 text-sm text-slate-400 mb-3">
                    <MapPin className="w-4 h-4" />
                    <span>{store.city}, {store.state}</span>
                    {store.region && (
                      <span className="px-2 py-0.5 bg-slate-700 rounded text-xs">{store.region}</span>
                    )}
                  </div>
                  
                  {storeStats && (
                    <div className="flex items-center gap-4 pt-3 border-t border-slate-700">
                      <div className="flex items-center gap-1">
                        <Users className="w-4 h-4 text-cyan-400" />
                        <span className="text-sm text-white">{storeStats.employee_count}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <BarChart3 className="w-4 h-4 text-emerald-400" />
                        <span className="text-sm text-white">{storeStats.average_score}</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Trophy className="w-4 h-4 text-amber-400" />
                        <span className="text-sm text-white">{storeStats.top_score}</span>
                      </div>
                    </div>
                  )}
                </div>
              </Link>
            );
          })}
        </div>
      ) : (
        <div className="bg-slate-800 rounded-xl p-12 border border-slate-700 text-center">
          <Building2 className="w-16 h-16 text-slate-600 mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-white mb-2">No Stores Found</h3>
          <p className="text-slate-400 mb-4">
            {stores.length === 0 
              ? "Initialize the default Landry's stores to get started."
              : "No stores match your search criteria."}
          </p>
          {stores.length === 0 && (
            <Button onClick={initializeStores} className="bg-primary">
              <Plus className="w-4 h-4 mr-2" />
              Initialize Default Stores
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
