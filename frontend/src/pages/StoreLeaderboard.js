import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { Trophy, Building2, MapPin, Users, BarChart3, TrendingUp, ArrowLeft, Medal, Target } from "lucide-react";
import { Button } from "../components/ui/button";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";

export default function StoreLeaderboard() {
  const [leaderboard, setLeaderboard] = useState([]);
  const [loading, setLoading] = useState(true);
  const currentQ = getCurrentQuarter();
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);

  useEffect(() => {
    fetchLeaderboard();
  }, [selectedYear, selectedQuarter]);

  const fetchLeaderboard = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/stores/reports/leaderboard?quarter=${selectedQuarter}&year=${selectedYear}`);
      setLeaderboard(response.data.leaderboard || []);
    } catch (error) {
      console.error('Failed to fetch leaderboard:', error);
    } finally {
      setLoading(false);
    }
  };

  const getRankBadge = (rank) => {
    if (rank === 1) return { bg: 'bg-gradient-to-br from-amber-400 to-amber-600', icon: '🥇' };
    if (rank === 2) return { bg: 'bg-gradient-to-br from-slate-300 to-slate-500', icon: '🥈' };
    if (rank === 3) return { bg: 'bg-gradient-to-br from-amber-600 to-amber-800', icon: '🥉' };
    return { bg: 'bg-slate-700', icon: null };
  };

  const globalAvg = leaderboard.length > 0 
    ? (leaderboard.reduce((sum, s) => sum + s.average_score, 0) / leaderboard.length).toFixed(2)
    : 0;

  return (
    <div className="min-h-screen bg-background p-4 md:p-8" data-testid="store-leaderboard-page">
      {/* Header */}
      <div className="mb-6">
        <Link to="/stores" className="inline-flex items-center text-slate-400 hover:text-white mb-4 transition-colors">
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Stores
        </Link>
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-2">
              <Trophy className="w-8 h-8 text-amber-400" />
              Store Leaderboard
            </h1>
            <p className="text-slate-400 mt-1">
              Compare performance across all {leaderboard.length} locations
            </p>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={selectedYear}
              onChange={(e) => setSelectedYear(Number(e.target.value))}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white"
              data-testid="year-filter"
            >
              <option value={2026}>2026</option>
              <option value={2025}>2025</option>
            </select>
            <select
              value={selectedQuarter}
              onChange={(e) => setSelectedQuarter(e.target.value)}
              className="px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg text-white"
              data-testid="quarter-filter"
            >
              <option value="Q1">Q1</option>
              <option value="Q2">Q2</option>
              <option value="Q3">Q3</option>
              <option value="Q4">Q4</option>
            </select>
          </div>
        </div>
      </div>

      {/* Stats Banner */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Building2 className="w-5 h-5 text-cyan-400" />
            <span className="text-sm text-slate-400">Total Stores</span>
          </div>
          <p className="text-2xl font-bold text-white">{leaderboard.length}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Target className="w-5 h-5 text-emerald-400" />
            <span className="text-sm text-slate-400">Global Average</span>
          </div>
          <p className="text-2xl font-bold text-white">{globalAvg}</p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-amber-400" />
            <span className="text-sm text-slate-400">Top Score</span>
          </div>
          <p className="text-2xl font-bold text-white">
            {leaderboard[0]?.top_score || '-'}
          </p>
        </div>
        <div className="bg-slate-800 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-5 h-5 text-violet-400" />
            <span className="text-sm text-slate-400">Total Staff</span>
          </div>
          <p className="text-2xl font-bold text-white">
            {leaderboard.reduce((sum, s) => sum + s.employee_count, 0)}
          </p>
        </div>
      </div>

      {/* Leaderboard Table */}
      <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden">
        <div className="p-5 border-b border-slate-700">
          <h2 className="font-bold text-white flex items-center gap-2">
            <Medal className="w-5 h-5 text-amber-400" />
            {selectedQuarter} {selectedYear} Rankings
          </h2>
        </div>
        
        {loading ? (
          <div className="p-8 text-center">
            <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full mx-auto mb-4"></div>
            <p className="text-slate-400">Loading leaderboard...</p>
          </div>
        ) : leaderboard.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700 text-left">
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase">Rank</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase">Store</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase">Region</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase text-center">Staff</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase text-center">Avg Score</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase text-center">Top Score</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-400 uppercase text-center">Spread</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {leaderboard.map((store) => {
                  const badge = getRankBadge(store.rank);
                  const isAboveAvg = store.average_score > globalAvg;
                  
                  return (
                    <tr key={store.store_id} className="hover:bg-slate-750 transition-colors">
                      <td className="px-5 py-4">
                        <div className={`w-10 h-10 rounded-full flex items-center justify-center ${badge.bg}`}>
                          {badge.icon ? (
                            <span className="text-lg">{badge.icon}</span>
                          ) : (
                            <span className="text-white font-bold">{store.rank}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-5 py-4">
                        <Link to={`/stores/${store.store_id}`} className="hover:text-primary transition-colors">
                          <div className="font-semibold text-white">{store.store_name}</div>
                          <div className="flex items-center gap-1 text-sm text-slate-400">
                            <MapPin className="w-3 h-3" />
                            {store.city}, {store.state}
                          </div>
                        </Link>
                      </td>
                      <td className="px-5 py-4">
                        <span className="px-2 py-1 bg-slate-700 rounded text-sm text-slate-300">
                          {store.region || 'N/A'}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className="text-white font-medium">{store.employee_count}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className={`text-lg font-bold ${isAboveAvg ? 'text-emerald-400' : 'text-white'}`}>
                          {store.average_score}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className="text-amber-400 font-medium">{store.top_score}</span>
                      </td>
                      <td className="px-5 py-4 text-center">
                        <span className="text-slate-400">{store.score_spread}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-12 text-center">
            <Trophy className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl font-semibold text-white mb-2">No Data Available</h3>
            <p className="text-slate-400">
              Store performance data for {selectedQuarter} {selectedYear} is not available yet.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
