import { useState, useEffect } from "react";
import { Trophy, Star, Medal, Crown, Download, MessageSquare, MousePointerClick, Percent } from "lucide-react"; // eslint-disable-line no-unused-vars
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { getDisplayFirstName } from "../utils/displayName";

export default function QRLeaderboard() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const { quarter, year } = getCurrentQuarter();

  useEffect(() => {
    const fetchData = async () => {
      try {
        // New endpoint that merges clicks + RT mentions and pre-sorts by
        // conversion rate desc, mentions desc, clicks desc.
        const res = await api.get(
          `/qr/leaderboard-data?quarter=${quarter}&year=${year}`
        );
        setEmployees(res.data?.employees || []);
      } catch (error) {
        toast.error("Failed to load leaderboard");
      }
      setLoading(false);
    };
    fetchData();
  }, [quarter, year]);

  const downloadSlide = async () => {
    setDownloading(true);
    try {
      const res = await api.get(
        `/qr/leaderboard/slide?quarter=${quarter}&year=${year}`,
        { responseType: 'blob' }
      );
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `qr_clicks_vs_mentions_${quarter}_${year}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded ${quarter} ${year} clicks vs mentions report`);
    } catch (e) {
      toast.error('Slide download failed');
    } finally {
      setDownloading(false);
    }
  };

  const getRankIcon = (rank) => {
    if (rank === 1) return <Crown className="w-5 h-5 sm:w-6 sm:h-6 text-yellow-400" />;
    if (rank === 2) return <Medal className="w-5 h-5 sm:w-6 sm:h-6 text-slate-300" />;
    if (rank === 3) return <Medal className="w-5 h-5 sm:w-6 sm:h-6 text-amber-600" />;
    return <span className="text-slate-500 font-bold text-sm sm:text-base">#{rank}</span>;
  };

  const getRankBg = (rank) => {
    if (rank === 1) return "bg-gradient-to-r from-yellow-500/20 to-transparent border-yellow-500/30";
    if (rank === 2) return "bg-gradient-to-r from-slate-400/20 to-transparent border-slate-400/30";
    if (rank === 3) return "bg-gradient-to-r from-amber-600/20 to-transparent border-amber-600/30";
    return "bg-white/5 border-white/10";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-3 sm:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-6 sm:mb-8 relative">
          <div className="inline-flex items-center justify-center gap-2 sm:gap-3 mb-2">
            <Trophy className="w-7 h-7 sm:w-10 sm:h-10 text-yellow-400" />
            <h1 className="text-2xl sm:text-4xl font-bold text-white">QR Leaderboard</h1>
            <Trophy className="w-7 h-7 sm:w-10 sm:h-10 text-yellow-400" />
          </div>
          <p className="text-slate-400 text-xs sm:text-base">
            Sorted by conversion rate (mentions ÷ clicks)
          </p>
          <div className="mt-3 sm:mt-4 flex justify-center">
            <Button
              onClick={downloadSlide}
              disabled={downloading || employees.length === 0}
              className="bg-violet-600 hover:bg-violet-700 text-white text-xs sm:text-sm"
              data-testid="qr-leaderboard-download-slide"
            >
              <Download className="w-4 h-4 mr-2" />
              {downloading ? 'Generating…' : 'Download Clicks vs Mentions Report'}
            </Button>
          </div>
        </div>

        {/* Leaderboard rows */}
        <div className="space-y-2 sm:space-y-3">
          {employees.map((emp, idx) => {
            const rank = idx + 1;
            const yelp = emp.yelp_clicks || 0;
            const google = emp.google_clicks || 0;
            const tripadvisor = emp.tripadvisor_clicks || 0;
            const totalClicks = emp.total_clicks ?? (yelp + google + tripadvisor);
            const mentions = emp.rt_mentions || 0;
            const conv = emp.conversion_rate ?? (totalClicks > 0 ? (mentions / totalClicks) * 100 : 0);

            return (
              <div
                key={emp.id || emp.name}
                className={`rounded-xl border p-3 sm:p-4 transition-all hover:scale-[1.01] ${getRankBg(rank)}`}
                data-testid={`leaderboard-row-${rank}`}
              >
                {/* Top row: rank + name + (mobile: total) */}
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <div className="w-8 sm:w-12 flex justify-center flex-shrink-0">
                      {getRankIcon(rank)}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p
                        className={`font-semibold truncate ${rank <= 3 ? 'text-base sm:text-xl text-white' : 'text-sm sm:text-base text-white'}`}
                        title={getDisplayFirstName(emp)}
                      >
                        {getDisplayFirstName(emp)}
                      </p>
                      {rank <= 3 && (
                        <p className="text-[10px] sm:text-sm text-slate-400">
                          {rank === 1 ? "Top Conversion" : rank === 2 ? "2nd" : "3rd"}
                        </p>
                      )}
                    </div>
                  </div>
                  {/* Mobile-only: conversion shown beside name */}
                  <div className="sm:hidden text-right flex-shrink-0">
                    <p className="text-xl font-bold text-blue-400 leading-none">
                      {conv.toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-blue-300">Conv</p>
                  </div>
                </div>

                {/* Stats row — 4-col grid on mobile, single horizontal row on sm+ */}
                <div className="mt-3 grid grid-cols-4 gap-1 sm:flex sm:gap-6 sm:justify-end sm:mt-0 sm:pt-0">
                  <div className="text-center sm:order-1">
                    <p className="text-base sm:text-xl font-bold text-amber-400 leading-none">{totalClicks}</p>
                    <p className="text-[9px] sm:text-xs text-slate-500 mt-1">Clicks</p>
                  </div>
                  <div className="text-center sm:order-2">
                    <p className="text-base sm:text-xl font-bold text-emerald-400 leading-none">{mentions}</p>
                    <p className="text-[9px] sm:text-xs text-slate-500 mt-1">Mentions</p>
                  </div>
                  <div className="text-center sm:order-3">
                    <p className="text-base sm:text-xl font-bold text-red-400 leading-none">{yelp}</p>
                    <p className="text-[9px] sm:text-xs text-slate-500 mt-1">Yelp</p>
                  </div>
                  <div className="text-center sm:order-4">
                    <p className="text-base sm:text-xl font-bold text-green-400 leading-none">{google + tripadvisor}</p>
                    <p className="text-[9px] sm:text-xs text-slate-500 mt-1">Goog/TA</p>
                  </div>
                  {/* Desktop-only conversion pill */}
                  <div className="hidden sm:block text-center min-w-[90px] bg-blue-500/20 rounded-lg px-3 py-1.5 sm:order-5">
                    <p className="text-xl font-bold text-blue-400 leading-none">{conv.toFixed(1)}%</p>
                    <p className="text-xs text-blue-300 mt-0.5">Conversion</p>
                  </div>
                </div>
              </div>
            );
          })}

          {employees.length === 0 && !loading && (
            <div className="text-center text-slate-400 py-12">
              No employees found. Add employees in QR Codes page.
            </div>
          )}
          {loading && (
            <div className="text-center text-slate-400 py-12">Loading leaderboard…</div>
          )}
        </div>
      </div>
    </div>
  );
}
