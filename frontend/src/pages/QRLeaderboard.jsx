import { useState, useEffect } from "react";
import { Trophy, Star, Medal, Crown, Download } from "lucide-react";  // eslint-disable-line no-unused-vars
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { getCurrentQuarter } from "../lib/quarterUtils";

export default function QRLeaderboard() {
  const [employees, setEmployees] = useState([]);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);
  const { quarter, year } = getCurrentQuarter();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get('/qr/employees');
        // Sort by total clicks (yelp + google + tripadvisor)
        const sorted = res.data.sort((a, b) => 
          ((b.yelp_clicks || 0) + (b.google_clicks || 0) + (b.tripadvisor_clicks || 0)) -
          ((a.yelp_clicks || 0) + (a.google_clicks || 0) + (a.tripadvisor_clicks || 0))
        );
        setEmployees(sorted);
      } catch (error) {
        toast.error("Failed to load leaderboard");
      }
      setLoading(false);
    };
    fetchData();
  }, []);

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
    if (rank === 1) return <Crown className="w-6 h-6 text-yellow-400" />;
    if (rank === 2) return <Medal className="w-6 h-6 text-slate-300" />;
    if (rank === 3) return <Medal className="w-6 h-6 text-amber-600" />;
    return <span className="text-slate-500 font-bold">#{rank}</span>;
  };

  const getRankBg = (rank) => {
    if (rank === 1) return "bg-gradient-to-r from-yellow-500/20 to-transparent border-yellow-500/30";
    if (rank === 2) return "bg-gradient-to-r from-slate-400/20 to-transparent border-slate-400/30";
    if (rank === 3) return "bg-gradient-to-r from-amber-600/20 to-transparent border-amber-600/30";
    return "bg-white/5 border-white/10";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8 relative">
          <div className="inline-flex items-center justify-center gap-3 mb-2">
            <Trophy className="w-10 h-10 text-yellow-400" />
            <h1 className="text-4xl font-bold text-white">QR Leaderboard</h1>
            <Trophy className="w-10 h-10 text-yellow-400" />
          </div>
          <p className="text-slate-400">Top performers by total QR code scans</p>
          <div className="mt-4 flex justify-center">
            <Button
              onClick={downloadSlide}
              disabled={downloading || employees.length === 0}
              className="bg-violet-600 hover:bg-violet-700 text-white"
              data-testid="qr-leaderboard-download-slide"
            >
              <Download className="w-4 h-4 mr-2" />
              {downloading ? 'Generating…' : 'Download Clicks vs Mentions Report'}
            </Button>
          </div>
        </div>

        {/* Leaderboard */}
        <div className="space-y-3">
          {employees.map((emp, idx) => {
            const rank = idx + 1;
            const yelp = emp.yelp_clicks || 0;
            const google = emp.google_clicks || 0;
            const tripadvisor = emp.tripadvisor_clicks || 0;
            const total = yelp + google + tripadvisor;
            
            return (
              <div 
                key={emp.id}
                className={`flex items-center justify-between p-4 rounded-xl border transition-all hover:scale-[1.02] ${getRankBg(rank)}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-12 flex justify-center">
                    {getRankIcon(rank)}
                  </div>
                  <div>
                    <p className={`font-semibold ${rank <= 3 ? 'text-xl text-white' : 'text-white'}`}>
                      {emp.name}
                    </p>
                    {rank <= 3 && (
                      <p className="text-sm text-slate-400">
                        {rank === 1 ? "Champion" : rank === 2 ? "Runner Up" : "Third Place"}
                      </p>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4 text-red-400" />
                      <span className="text-xl font-bold text-red-400">{yelp}</span>
                    </div>
                    <p className="text-xs text-slate-500">Yelp</p>
                  </div>
                  <div className="text-center">
                    <div className="flex items-center gap-1">
                      <span className="text-xl font-bold text-green-400">{google}</span>
                    </div>
                    <p className="text-xs text-slate-500">Google</p>
                  </div>
                  <div className="text-center">
                    <div className="flex items-center gap-1">
                      <span className="text-xl font-bold text-emerald-400">{tripadvisor}</span>
                    </div>
                    <p className="text-xs text-slate-500">TripAdvisor</p>
                  </div>
                  <div className="text-center min-w-[80px] bg-blue-500/20 rounded-lg px-4 py-2">
                    <p className="text-2xl font-bold text-blue-400">{total}</p>
                    <p className="text-xs text-blue-300">Total</p>
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
        </div>
      </div>
    </div>
  );
}
