import { useState, useEffect } from 'react';
import { useStore } from '../contexts/StoreContext';
import { 
  Building2, Users, TrendingUp, Award, AlertTriangle, 
  Globe, MapPin, ChevronRight, BarChart3 
} from 'lucide-react';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function GlobalOverview() {
  const { stores, regions, isGlobalView } = useStore();
  const [quarter, setQuarter] = useState('Q1');
  const [year, setYear] = useState(2026);
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [overview, setOverview] = useState(null);
  const [leaderboard, setLeaderboard] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, [quarter, year, selectedRegion]);

  const loadData = async () => {
    setLoading(true);
    try {
      const regionParam = selectedRegion ? `&region=${selectedRegion}` : '';
      
      const [overviewRes, leaderboardRes] = await Promise.all([
        fetch(`${BACKEND_URL}/api/v2/stores/reports/overview?quarter=${quarter}&year=${year}${regionParam}`),
        fetch(`${BACKEND_URL}/api/v2/stores/reports/leaderboard?quarter=${quarter}&year=${year}${regionParam}&limit=10`)
      ]);
      
      const overviewData = await overviewRes.json();
      const leaderboardData = await leaderboardRes.json();
      
      setOverview(overviewData);
      setLeaderboard(leaderboardData);
    } catch (error) {
      console.error('Failed to load global data:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  const summary = overview?.summary || {};
  const storeData = overview?.stores || [];

  return (
    <div className="p-6 space-y-6" data-testid="global-overview">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Globe className="w-7 h-7 text-blue-400" />
            Global Performance Overview
          </h1>
          <p className="text-muted-foreground mt-1">
            {selectedRegion ? `${selectedRegion} Region` : 'All Stores'} • {quarter} {year}
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Region Filter */}
          <Select value={selectedRegion || 'all'} onValueChange={(v) => setSelectedRegion(v === 'all' ? null : v)}>
            <SelectTrigger className="w-40" data-testid="region-filter">
              <SelectValue placeholder="All Regions" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Regions</SelectItem>
              {regions.map(region => (
                <SelectItem key={region} value={region}>{region}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          {/* Quarter/Year Selection */}
          <Select value={quarter} onValueChange={setQuarter}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Q1">Q1</SelectItem>
              <SelectItem value="Q2">Q2</SelectItem>
              <SelectItem value="Q3">Q3</SelectItem>
              <SelectItem value="Q4">Q4</SelectItem>
            </SelectContent>
          </Select>

          <Select value={year.toString()} onValueChange={(v) => setYear(parseInt(v))}>
            <SelectTrigger className="w-24">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="2026">2026</SelectItem>
              <SelectItem value="2025">2025</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-5 gap-4">
        <SummaryCard
          icon={Building2}
          label="Active Stores"
          value={summary.total_stores || 0}
          color="blue"
        />
        <SummaryCard
          icon={Users}
          label="Total Employees"
          value={summary.total_employees || 0}
          color="green"
        />
        <SummaryCard
          icon={BarChart3}
          label="Avg Score"
          value={(summary.avg_score || 0).toFixed(1)}
          color="yellow"
        />
        <SummaryCard
          icon={Award}
          label="Top Performers"
          value={summary.top_performers || 0}
          subtitle="A-Server+"
          color="emerald"
        />
        <SummaryCard
          icon={AlertTriangle}
          label="Needs Coaching"
          value={summary.needs_coaching || 0}
          subtitle="C-Server"
          color="red"
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-3 gap-6">
        {/* Store Rankings */}
        <div className="col-span-2 bg-[hsl(var(--card))] rounded-xl border border-[hsl(var(--border))] p-4">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-blue-400" />
            Store Performance Rankings
          </h2>
          
          <div className="space-y-2">
            {storeData.filter(s => s.employee_count > 0).map((store, index) => (
              <div 
                key={store.store_id}
                className="flex items-center gap-3 p-3 rounded-lg bg-[hsl(var(--background))] hover:bg-[hsl(var(--accent))] transition-colors"
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm
                  ${index === 0 ? 'bg-yellow-500/20 text-yellow-400' : 
                    index === 1 ? 'bg-gray-400/20 text-gray-300' :
                    index === 2 ? 'bg-orange-500/20 text-orange-400' :
                    'bg-[hsl(var(--muted))] text-muted-foreground'
                  }`}
                >
                  {index + 1}
                </div>
                
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{store.code}</span>
                    <span className="text-sm text-muted-foreground">{store.name.replace('Bubba Gump ', '')}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {store.employee_count} employees • {store.a_server_count} A-Servers
                  </div>
                </div>
                
                <div className="text-right">
                  <div className={`text-lg font-bold ${
                    store.avg_score >= 85 ? 'text-green-400' :
                    store.avg_score >= 70 ? 'text-yellow-400' :
                    'text-red-400'
                  }`}>
                    {store.avg_score.toFixed(1)}
                  </div>
                  <div className="text-xs text-muted-foreground">avg score</div>
                </div>
              </div>
            ))}
            
            {storeData.filter(s => s.employee_count > 0).length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                No stores have data for {quarter} {year}
              </div>
            )}
          </div>
        </div>

        {/* Global Leaderboard */}
        <div className="bg-[hsl(var(--card))] rounded-xl border border-[hsl(var(--border))] p-4">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Award className="w-5 h-5 text-yellow-400" />
            Top 10 Company-Wide
          </h2>
          
          <div className="space-y-2">
            {(leaderboard?.leaderboard || []).map((emp, index) => (
              <div 
                key={emp.employee_id}
                className="flex items-center gap-2 p-2 rounded-lg hover:bg-[hsl(var(--accent))] transition-colors"
              >
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold
                  ${index === 0 ? 'bg-yellow-500 text-yellow-950' : 
                    index === 1 ? 'bg-gray-400 text-gray-950' :
                    index === 2 ? 'bg-orange-500 text-orange-950' :
                    'bg-[hsl(var(--muted))] text-muted-foreground'
                  }`}
                >
                  {index + 1}
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate text-sm">{emp.name}</div>
                  <div className="text-xs text-muted-foreground flex items-center gap-1">
                    <MapPin className="w-3 h-3" />
                    {emp.store_code}
                  </div>
                </div>
                
                <div className="text-right">
                  <div className={`font-bold text-sm ${
                    emp.total_score >= 100 ? 'text-blue-400' :
                    emp.total_score >= 85 ? 'text-green-400' :
                    'text-yellow-400'
                  }`}>
                    {emp.total_score?.toFixed(1)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Inactive Stores */}
      {storeData.filter(s => s.employee_count === 0).length > 0 && (
        <div className="bg-[hsl(var(--card))] rounded-xl border border-[hsl(var(--border))] p-4">
          <h3 className="text-sm font-semibold text-muted-foreground mb-3">
            Stores Without Data ({storeData.filter(s => s.employee_count === 0).length})
          </h3>
          <div className="flex flex-wrap gap-2">
            {storeData.filter(s => s.employee_count === 0).map(store => (
              <span 
                key={store.store_id}
                className="px-2 py-1 text-xs rounded-full bg-[hsl(var(--muted))] text-muted-foreground"
              >
                {store.code} - {store.name.replace('Bubba Gump ', '')}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ icon: Icon, label, value, subtitle, color }) {
  const colorClasses = {
    blue: 'bg-blue-500/10 text-blue-400',
    green: 'bg-green-500/10 text-green-400',
    yellow: 'bg-yellow-500/10 text-yellow-400',
    emerald: 'bg-emerald-500/10 text-emerald-400',
    red: 'bg-red-500/10 text-red-400',
  };

  return (
    <div className="bg-[hsl(var(--card))] rounded-xl border border-[hsl(var(--border))] p-4">
      <div className="flex items-center gap-3">
        <div className={`p-2 rounded-lg ${colorClasses[color]}`}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="text-2xl font-bold">{value}</div>
          <div className="text-xs text-muted-foreground">
            {label}
            {subtitle && <span className="block">{subtitle}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
