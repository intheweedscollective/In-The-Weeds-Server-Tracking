import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { QrCode, TrendingUp } from "lucide-react";
import api from "../lib/api";
import { getDisplayFirstName } from "../utils/displayName";

export default function QRTopClicksCard({ showViewAll = true, limit = 5 }) {
  const [topClicks, setTopClicks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ total_scans: 0, yelp_scans: 0, google_scans: 0, tripadvisor_scans: 0 });

  useEffect(() => {
    fetchTopClicks();
  }, []);

  const fetchTopClicks = async () => {
    try {
      const response = await api.get('/qr/stats');
      setTopClicks(response.data.top_10?.slice(0, limit) || []);
      setStats({
        total_scans: response.data.total_scans || 0,
        yelp_scans: response.data.yelp_scans || 0,
        google_scans: response.data.google_scans || 0,
        tripadvisor_scans: response.data.tripadvisor_scans || 0
      });
    } catch (error) {
      console.error('Failed to fetch QR stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-slate-800 rounded-2xl border border-slate-700 p-5 animate-pulse">
        <div className="h-6 bg-slate-700 rounded w-1/2 mb-4"></div>
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={`skeleton-${i}`} className="h-12 bg-slate-700 rounded"></div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-2xl border border-slate-700 overflow-hidden" data-testid="qr-top-clicks-card">
      <div className="p-5 border-b border-slate-700 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-violet-500/20 flex items-center justify-center">
            <QrCode className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h2 className="font-bold text-white">Top QR Clicks</h2>
            <p className="text-xs text-slate-500">{stats.total_scans} total scans</p>
          </div>
        </div>
        {showViewAll && (
          <Link to="/qr/leaderboard" className="text-sm text-primary font-medium hover:underline">
            View All →
          </Link>
        )}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-3 gap-2 p-4 border-b border-slate-700">
        <div className="flex items-center gap-2 p-2 bg-red-500/10 rounded-lg">
          <span className="text-sm">📍</span>
          <div>
            <p className="text-xs text-slate-400">Yelp</p>
            <p className="text-sm font-bold text-red-400">{stats.yelp_scans}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 bg-blue-500/10 rounded-lg">
          <span className="text-sm">🔍</span>
          <div>
            <p className="text-xs text-slate-400">Google</p>
            <p className="text-sm font-bold text-blue-400">{stats.google_scans}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 p-2 bg-emerald-500/10 rounded-lg">
          <span className="text-sm">🦉</span>
          <div>
            <p className="text-xs text-slate-400">TripAdvisor</p>
            <p className="text-sm font-bold text-emerald-400">{stats.tripadvisor_scans}</p>
          </div>
        </div>
      </div>

      {/* Leaderboard */}
      <div className="divide-y divide-slate-700">
        {topClicks.length > 0 ? (
          topClicks.map((emp, idx) => (
            <div key={getDisplayFirstName(emp)} className="flex items-center justify-between p-4 hover:bg-slate-750 transition-colors">
              <div className="flex items-center gap-3">
                <div className={`w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold ${
                  idx === 0 ? 'bg-amber-500 text-white' : 
                  idx === 1 ? 'bg-slate-400 text-white' : 
                  idx === 2 ? 'bg-amber-700 text-white' : 
                  'bg-slate-600 text-slate-300'
                }`}>
                  {idx + 1}
                </div>
                <span className="font-medium text-white">{getDisplayFirstName(emp)}</span>
              </div>
              <div className="flex items-center gap-3">
                <div className="flex items-center gap-1 text-xs">
                  <span className="text-red-400">{emp.yelp_clicks}</span>
                  <span className="text-slate-500">/</span>
                  <span className="text-blue-400">{emp.google_clicks}</span>
                  <span className="text-slate-500">/</span>
                  <span className="text-emerald-400">{emp.tripadvisor_clicks || 0}</span>
                </div>
                <div className="flex items-center gap-1 px-2 py-1 bg-violet-500/20 rounded-full">
                  <TrendingUp className="w-3 h-3 text-violet-400" />
                  <span className="text-xs font-bold text-violet-400">{emp.total}</span>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="p-6 text-center">
            <QrCode className="w-10 h-10 text-slate-600 mx-auto mb-2" />
            <p className="text-slate-400 text-sm">No QR scans yet</p>
            <p className="text-slate-500 text-xs">Generate QR codes and start tracking</p>
          </div>
        )}
      </div>
    </div>
  );
}
