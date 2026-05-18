import { useState, useEffect } from "react";
import { Settings, Lock, Unlock, Save, RefreshCw, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import NicknameManager from "../components/NicknameManager";

// NOTE: SLIDE_THEMES and SEASONAL_THEMES removed - functionality deprecated

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

export default function QuarterSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [fixingRankings, setFixingRankings] = useState(false);
  const [allSettings, setAllSettings] = useState([]);
  const currentQ = getCurrentQuarter();
  const [selectedYear, setSelectedYear] = useState(currentQ.year);
  const [selectedQuarter, setSelectedQuarter] = useState(currentQ.quarter);
  const [settings, setSettings] = useState(null);
  const [suggestions, setSuggestions] = useState(null);
  const [isNew, setIsNew] = useState(false);

  // Form state - Q1 2026 Official Model
  const [formData, setFormData] = useState({
    benchmark_ppa: 55.0,
    benchmark_lbw: 8.0,
    benchmark_glass: 1.0,
    benchmark_lsc: 100.0,
    benchmark_cv: 5.0,
    weight_ppa: 0.25,
    weight_lbw: 0.20,
    weight_glass: 0.15,
    weight_lsc: 0.25,
    weight_cv: 0.15,
    bonus_rate: 0.2,
    bonus_cap: 5.0,
    // Server tier thresholds
    a_server_min_score: 85.0,
    b_server_min_score: 70.0
  });

  useEffect(() => {
    fetchAllSettings();
  }, []);

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true);
      try {
        const response = await api.get(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
        setSettings(response.data);
        setFormData({
          benchmark_ppa: response.data.benchmark_ppa,
          benchmark_lbw: response.data.benchmark_lbw,
          benchmark_glass: response.data.benchmark_glass,
          benchmark_lsc: response.data.benchmark_lsc,
          benchmark_cv: response.data.benchmark_cv || 5.0,
          weight_ppa: response.data.weight_ppa,
          weight_lbw: response.data.weight_lbw,
          weight_glass: response.data.weight_glass,
          weight_lsc: response.data.weight_lsc,
          weight_cv: response.data.weight_cv || 0.15,
          bonus_rate: response.data.bonus_rate,
          bonus_cap: response.data.bonus_cap,
          a_server_min_score: response.data.a_server_min_score || 80.0,
          b_server_min_score: response.data.b_server_min_score || 70.1
        });
        setIsNew(false);
      } catch (error) {
        if (error.response?.status === 404) {
          setSettings(null);
          setIsNew(true);
          setFormData({
            benchmark_ppa: 55.0,
            benchmark_lbw: 8.0,
            benchmark_glass: 1.0,
            benchmark_lsc: 100.0,
            benchmark_cv: 5.0,
            weight_ppa: 0.25,
            weight_lbw: 0.20,
            weight_glass: 0.15,
            weight_lsc: 0.25,
            weight_cv: 0.15,
            bonus_rate: 0.2,
            bonus_cap: 5.0,
            a_server_min_score: 80.0,
            b_server_min_score: 70.0
          });
        } else {
          toast.error("Error loading settings");
        }
      } finally {
        setLoading(false);
      }
    };

    const loadSuggestions = async () => {
      try {
        const response = await api.get(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}/benchmark-suggestions`);
        setSuggestions(response.data);
      } catch (error) {
        setSuggestions(null);
      }
    };

    loadSettings();
    loadSuggestions();
  }, [selectedYear, selectedQuarter]);

  const fetchAllSettings = async () => {
    try {
      const response = await api.get(`/v2/quarter-settings`);
      setAllSettings(response.data);
    } catch (error) {
    }
  };

  const refetchSettings = async () => {
    setLoading(true);
    try {
      const response = await api.get(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
      setSettings(response.data);
      setFormData({
        benchmark_ppa: response.data.benchmark_ppa,
        benchmark_lbw: response.data.benchmark_lbw,
        benchmark_glass: response.data.benchmark_glass,
        benchmark_lsc: response.data.benchmark_lsc,
        benchmark_cv: response.data.benchmark_cv || 5.0,
        weight_ppa: response.data.weight_ppa,
        weight_lbw: response.data.weight_lbw,
        weight_glass: response.data.weight_glass,
        weight_lsc: response.data.weight_lsc,
        weight_cv: response.data.weight_cv || 0.15,
        bonus_rate: response.data.bonus_rate,
        bonus_cap: response.data.bonus_cap,
        a_server_min_score: response.data.a_server_min_score || 80.0,
        b_server_min_score: response.data.b_server_min_score || 70.1
      });
      setIsNew(false);
    } catch (error) {
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    // Validate POS weights are within a reasonable range. Default Q2+ model
    // sums to 0.85 (PPA 25% + LSC 25% + LBW 20% + Glass 15%); legacy Q1
    // model summed to 0.75. CV/RT/Metric Bonuses are added on top — they
    // are NOT weighted percentages.
    const posWeightSum = formData.weight_ppa + formData.weight_lbw + formData.weight_glass + formData.weight_lsc;
    
    // Allow flexibility - weights can sum to anywhere between 0.50 and 1.05
    // The scoring formula uses these as multipliers, so any reasonable sum works
    if (posWeightSum < 0.50 || posWeightSum > 1.05) {
      toast.error(`POS weights should sum to between 0.50 and 1.05 (currently ${posWeightSum.toFixed(2)})`);
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        await api.post(`/v2/quarter-settings`, {
          year: selectedYear,
          quarter: selectedQuarter,
          ...formData
        });
        toast.success(`Created settings for ${selectedQuarter} ${selectedYear}`);
      } else {
        await api.put(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}`, formData);
        toast.success(`Updated settings for ${selectedQuarter} ${selectedYear}`);
      }
      refetchSettings();
      fetchAllSettings();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Error saving settings");
    } finally {
      setSaving(false);
    }
  };

  // Emergency fix for all rankings
  const handleFixAllRankings = async () => {
    if (!window.confirm("This will recalculate ALL employee rankings and update ALL snapshots. Continue?")) {
      return;
    }
    
    setFixingRankings(true);
    try {
      const response = await api.post(`/v2/admin/fix-all-rankings?quarter=${selectedQuarter}&year=${selectedYear}`);
      const data = response.data;
      toast.success(`Fixed ${data.employees_fixed} employees and ${data.snapshots_fixed} snapshots!`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Error fixing rankings");
    } finally {
      setFixingRankings(false);
    }
  };

  // Unlock a previously-locked quarter so benchmarks/weights can be edited.
  // After unlocking + saving new values, the user should re-run scoring (Fix
  // All Rankings or the Snapshot Workflow rescore button) to push the new
  // benchmark through every employee's score.
  const handleUnlock = async () => {
    if (!window.confirm(
      `Unlock ${selectedQuarter} ${selectedYear} settings?\n\n` +
      `You'll be able to edit benchmarks and weights. After saving, run "Fix All Rankings" ` +
      `to recalculate every employee's score against the new values.`
    )) {
      return;
    }
    try {
      await api.post(`/v2/quarter-settings/${selectedYear}/${selectedQuarter}/unlock`);
      toast.success(`${selectedQuarter} ${selectedYear} unlocked. Edit and save your changes.`);
      refetchSettings();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to unlock settings");
    }
  };

  const applySuggestion = (metric, value) => {
    setFormData(prev => ({
      ...prev,
      [`benchmark_${metric}`]: value
    }));
  };

  // NOTE: applyThemePreset function removed - slide themes deprecated

  // POS weights validation (PPA + LBW + Glass + LSC)
  // CV is a bonus system, not included in weight validation
  const posWeightSum = formData.weight_ppa + formData.weight_lbw + formData.weight_glass + formData.weight_lsc;
  const weightsValid = posWeightSum >= 0.50 && posWeightSum <= 1.05;

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      <div className="splash-red" style={{ top: '10%', right: '5%' }} />
      <div className="splash-blue" style={{ bottom: '15%', left: '3%', opacity: 0.5 }} />
      
      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Settings className="w-8 h-8 text-secondary" />
            <h1 className="text-3xl font-serif font-black text-foreground">
              Quarter Settings
            </h1>
          </div>
          <p className="text-slate-400">
            Configure benchmarks and weights for scoring
          </p>
        </div>

        {/* Quarter Selector */}
        <div className="bubba-card mb-8">
          <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Select Period</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Year</label>
                <select
                  className="w-full h-10 rounded-lg border-2 border-slate-600 bg-slate-700 px-3 text-sm text-slate-200"
                  value={selectedYear}
                  onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                >
                  <option value={2025}>2025</option>
                  <option value={2026}>2026</option>
                  <option value={2027}>2027</option>
                </select>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Quarter</label>
                <select
                  className="w-full h-10 rounded-lg border-2 border-slate-600 bg-slate-700 px-3 text-sm text-slate-200"
                  value={selectedQuarter}
                  onChange={(e) => setSelectedQuarter(e.target.value)}
                >
                  <option value="Q1">Q1 (Jan - Mar)</option>
                  <option value="Q2">Q2 (Apr - Jun)</option>
                  <option value="Q3">Q3 (Jul - Sep)</option>
                  <option value="Q4">Q4 (Oct - Dec)</option>
                </select>
              </div>
            </div>

            {/* Status Badge */}
            <div className="mt-4 flex items-center gap-3">
              {isNew ? (
                <span className="px-3 py-1 bg-yellow-100 text-yellow-800 rounded-full text-sm font-semibold flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4" />
                  No settings yet - create new
                </span>
              ) : settings?.is_locked ? (
                <>
                  <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-semibold flex items-center gap-2">
                    <Lock className="w-4 h-4" />
                    Locked (scores generated)
                  </span>
                  <button
                    onClick={handleUnlock}
                    data-testid="unlock-quarter-settings-btn"
                    className="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-white rounded-full text-sm font-semibold flex items-center gap-2 transition-colors"
                    title="Unlock to edit benchmarks/weights for this quarter"
                  >
                    <Unlock className="w-4 h-4" />
                    Unlock to Edit
                  </button>
                </>
              ) : (
                <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm font-semibold flex items-center gap-2">
                  <Unlock className="w-4 h-4" />
                  Editable
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Benchmark Suggestions */}
        {suggestions?.has_previous_data && (
          <div className="bubba-card mb-8">
            <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
            <div className="p-6 pt-8">
              <div className="flex items-center gap-2 mb-4">
                <RefreshCw className="w-5 h-5 text-secondary" />
                <h2 className="text-lg font-serif font-bold text-foreground">
                  Suggestions from {suggestions.previous_quarter} {suggestions.previous_year}
                </h2>
              </div>
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {suggestions.suggestions?.ppa && (
                  <div className="p-3 bg-blue-50 rounded-lg border border-blue-100">
                    <div className="text-xs text-blue-700 uppercase font-bold mb-1">PPA</div>
                    <div className="text-sm text-blue-600 font-semibold mb-2">Avg: ${suggestions.previous_averages.avg_ppa}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('ppa', suggestions.suggestions.ppa.default)}
                        className="w-full text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 font-semibold px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.ppa.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.lbw && (
                  <div className="p-3 bg-purple-50 rounded-lg border border-purple-100">
                    <div className="text-xs text-purple-700 uppercase font-bold mb-1">LBW/Guest</div>
                    <div className="text-sm text-purple-600 font-semibold mb-2">Avg: ${suggestions.previous_averages.avg_lbw}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('lbw', suggestions.suggestions.lbw.default)}
                        className="w-full text-xs bg-purple-100 hover:bg-purple-200 text-purple-800 font-semibold px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.lbw.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.glass && (
                  <div className="p-3 bg-gray-100 rounded-lg border border-gray-200">
                    <div className="text-xs text-gray-700 uppercase font-bold mb-1">Glass/Guest</div>
                    <div className="text-sm text-gray-600 font-semibold mb-2">Avg: ${suggestions.previous_averages.avg_glass}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('glass', suggestions.suggestions.glass.default)}
                        className="w-full text-xs bg-gray-200 hover:bg-gray-300 text-gray-800 font-semibold px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.glass.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.lsc && (
                  <div className="p-3 bg-green-50 rounded-lg border border-green-100">
                    <div className="text-xs text-green-700 uppercase font-bold mb-1">Guests/LSC</div>
                    <div className="text-sm text-green-600 font-semibold mb-2">Avg: {suggestions.previous_averages.avg_lsc}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('lsc', suggestions.suggestions.lsc.default)}
                        className="w-full text-xs bg-green-100 hover:bg-green-200 text-green-800 font-semibold px-2 py-1 rounded"
                      >
                        Use {suggestions.suggestions.lsc.default} (÷1.15)
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Benchmarks */}
        <div className="bubba-card mb-8">
          <div className="tape tape-red" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-2deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Benchmarks</h2>
            <p className="text-sm text-slate-400 mb-4">
              Score = (Employee Metric / Benchmark) × 100. For LSC, lower guests per signup is better.
            </p>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">PPA Benchmark ($)</label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.benchmark_ppa}
                  onChange={(e) => setFormData(prev => ({ ...prev, benchmark_ppa: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">LBW/Guest Benchmark ($)</label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.benchmark_lbw}
                  onChange={(e) => setFormData(prev => ({ ...prev, benchmark_lbw: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Glass/Guest Benchmark ($)</label>
                <Input
                  type="number"
                  step="0.01"
                  value={formData.benchmark_glass}
                  onChange={(e) => setFormData(prev => ({ ...prev, benchmark_glass: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Guests/LSC Benchmark</label>
                <Input
                  type="number"
                  step="1"
                  value={formData.benchmark_lsc}
                  onChange={(e) => setFormData(prev => ({ ...prev, benchmark_lsc: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
                <p className="text-xs text-gray-400">Lower = better (inverse metric)</p>
              </div>
            </div>
          </div>
        </div>

        {/* Weights */}
        <div className="bubba-card mb-8">
          <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Metric Weights (POS Scoring)</h2>
            <p className="text-sm text-slate-400 mb-4">
              POS weights (PPA + LBW + Glass + LSC). Current sum: 
              <span className={`ml-2 font-bold ${weightsValid ? 'text-green-600' : 'text-red-600'}`}>
                {posWeightSum.toFixed(2)}
              </span>
              {weightsValid && <span className="ml-2 text-green-500">✓</span>}
            </p>
            
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">PPA ({Math.round((formData.weight_ppa || 0) * 100)}%)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={formData.weight_ppa}
                  onChange={(e) => setFormData(prev => ({ ...prev, weight_ppa: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">LBW ({Math.round((formData.weight_lbw || 0) * 100)}%)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={formData.weight_lbw}
                  onChange={(e) => setFormData(prev => ({ ...prev, weight_lbw: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Glass ({Math.round((formData.weight_glass || 0) * 100)}%)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={formData.weight_glass}
                  onChange={(e) => setFormData(prev => ({ ...prev, weight_glass: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">LSC ({Math.round((formData.weight_lsc || 0) * 100)}%)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={formData.weight_lsc}
                  onChange={(e) => setFormData(prev => ({ ...prev, weight_lsc: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
            </div>
            
            {/* Info about CV scoring */}
            <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800">
                <strong>Note:</strong> Customer Voice (CV) points are added directly to the total score as raw points, not as a weighted percentage.
                Formula: NPS%/10 + (Promoters × {formData.cv_promoter_points ?? 1}) − (Detractors × {formData.cv_detractor_points ?? 2})
              </p>
              <p className="text-xs text-blue-700 mt-1">
                The Review Tracker bonus ({formData.rt_points_per_mention ?? 0.33} pts/mention, max {Math.round(formData.rt_max_points ?? 20)}) is a SEPARATE bonus added on top of CV.
              </p>
            </div>
          </div>
        </div>

        {/* Bonus Settings */}
        <div className="bubba-card mb-8">
          <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Bonus Settings</h2>
            <p className="text-sm text-slate-400 mb-4">
              Bonus = MIN((Score - 100) × Rate, Cap) for each metric where Score &gt; 100
            </p>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">Bonus Rate (per 1% over benchmark)</label>
                <Input
                  type="number"
                  step="0.05"
                  value={formData.bonus_rate}
                  onChange={(e) => setFormData(prev => ({ ...prev, bonus_rate: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium">Bonus Cap (max per metric)</label>
                <Input
                  type="number"
                  step="0.5"
                  value={formData.bonus_cap}
                  onChange={(e) => setFormData(prev => ({ ...prev, bonus_cap: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Server Tier Thresholds */}
        <div className="bubba-card mb-8">
          <div className="tape tape-red" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(1deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Server Tier Thresholds</h2>
            <p className="text-sm text-slate-400 mb-4">
              Rankings hierarchy: Trainers → Bartenders → A-Servers → B-Servers → C-Servers.
              Server tiers are determined by Total Score thresholds (adjustable).
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-green-500"></span>
                  A-Server Minimum Score
                </label>
                <Input
                  type="number"
                  step="0.1"
                  value={formData.a_server_min_score}
                  onChange={(e) => setFormData(prev => ({ ...prev, a_server_min_score: parseFloat(e.target.value) || 80.0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
                <p className="text-xs text-gray-400">Score ≥ this = A-Server</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-yellow-500"></span>
                  B-Server Minimum Score
                </label>
                <Input
                  type="number"
                  step="0.1"
                  value={formData.b_server_min_score}
                  onChange={(e) => setFormData(prev => ({ ...prev, b_server_min_score: parseFloat(e.target.value) || 70.0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
                <p className="text-xs text-gray-400">Score ≥ this AND &lt; A-Server = B-Server</p>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-red-500"></span>
                  C-Server (Auto)
                </label>
                <div className="h-10 flex items-center px-3 bg-slate-700 border-2 border-gray-200 rounded-lg text-slate-400">
                  Score &lt; {formData.b_server_min_score}
                </div>
                <p className="text-xs text-gray-400">Automatically calculated</p>
              </div>
            </div>
          </div>
        </div>

        {/* NOTE: Slide Theme and Seasonal Decorations sections removed - functionality deprecated */}

        {/* Save Button - Always show (theme settings can be saved even when locked) */}
        <div className="flex justify-between items-center">
          {/* Fix All Rankings Button */}
          <Button
            onClick={handleFixAllRankings}
            disabled={fixingRankings}
            variant="destructive"
            className="bg-red-600 hover:bg-red-700"
            data-testid="fix-rankings-btn"
          >
            {fixingRankings ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                Fixing Rankings...
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4" />
                Fix All Rankings
              </div>
            )}
          </Button>
          
          <Button
            onClick={handleSave}
            disabled={saving || (!settings?.is_locked && !weightsValid)}
            className="bubba-btn-primary"
          >
            {saving ? (
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                Saving...
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Save className="w-4 h-4" />
                {isNew ? 'Create Settings' : settings?.is_locked ? 'Save Theme Settings' : 'Save Changes'}
              </div>
            )}
          </Button>
        </div>

        {settings?.is_locked && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-yellow-800">
            <div className="flex items-center gap-2">
              <Lock className="w-5 h-5" />
              <span className="font-semibold">Scoring settings are locked</span>
            </div>
            <p className="text-sm mt-1">
              Scores have been generated for this quarter. Benchmarks, weights, and tier thresholds cannot be changed, but you can still customize theme and seasonal decoration settings.
            </p>
          </div>
        )}

        {/* User Manual Section */}
        <div className="mt-12 border-t-4 border-primary pt-8" data-testid="user-manual">
          <h2 className="text-3xl font-serif font-bold text-foreground mb-6 flex items-center gap-3">
            📖 User Manual
          </h2>
          
          {/* Quick Start Guide */}
          <div className="bubba-card mb-6">
            <div className="tape" style={{ top: '-8px', left: '20%', transform: 'rotate(-2deg)' }} />
            <div className="p-6 pt-8">
              <h3 className="text-xl font-bold text-primary mb-4">🚀 Quick Start Guide</h3>
              <ol className="space-y-3 text-slate-200">
                <li className="flex gap-3">
                  <span className="font-bold text-primary">1.</span>
                  <div>
                    <strong>Set Up Quarter Settings (this page)</strong> - Configure benchmarks and weights before uploading data. These determine how scores are calculated.
                  </div>
                </li>
                <li className="flex gap-3">
                  <span className="font-bold text-primary">2.</span>
                  <div>
                    <strong>Upload Employee Data (Dashboard)</strong> - Download the template, fill it with your team's numbers, and upload it back.
                  </div>
                </li>
                <li className="flex gap-3">
                  <span className="font-bold text-primary">3.</span>
                  <div>
                    <strong>Review Rankings</strong> - Check the Rankings page to see how everyone stacks up by tier.
                  </div>
                </li>
                <li className="flex gap-3">
                  <span className="font-bold text-primary">4.</span>
                  <div>
                    <strong>Generate Reviews & Slides</strong> - Create individual PDF reviews and Yodeck display slides.
                  </div>
                </li>
              </ol>
            </div>
          </div>

          {/* Page-by-Page Guide */}
          <div className="grid gap-4">
            {/* Dashboard */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-primary/10 rounded-full flex items-center justify-center text-primary">🏠</span>
                Dashboard
              </h4>
              <p className="text-slate-300 mb-3">Your home base for uploading and managing employee data.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Download Template</strong> - Get the Excel/CSV template with the correct columns</li>
                <li>• <strong>Upload Data</strong> - Upload your filled template to calculate scores</li>
                <li>• <strong>View Stats</strong> - See quick summary of team performance</li>
              </ul>
              <div className="mt-3 p-3 bg-blue-50 rounded-lg text-sm text-blue-800">
                <strong>💡 Tip:</strong> Review CV Passives carefully - they indicate mediocre service and affect the NPS calculation.
              </div>
            </div>

            {/* Rankings */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-purple-100 rounded-full flex items-center justify-center text-purple-600">📊</span>
                Rankings
              </h4>
              <p className="text-slate-300 mb-3">Full team rankings sorted by hierarchy and score.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Tier Order</strong> - Trainers → Bartenders → A-Servers → B-Servers → C-Servers</li>
                <li>• <strong>Position Labels</strong> - T1, T2 for Trainers; Bar1, Bar2 for Bartenders; A1, B1, C1, etc.</li>
                <li>• <strong>Download PDF</strong> - Export the full rankings table</li>
              </ul>
            </div>

            {/* Reviews */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-green-100 rounded-full flex items-center justify-center text-green-600">📝</span>
                Reviews
              </h4>
              <p className="text-slate-300 mb-3">Generate individual employee performance reviews with AI.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Generate Review</strong> - AI creates personalized feedback based on metrics</li>
                <li>• <strong>Download PDF</strong> - Print-ready review document</li>
                <li>• <strong>View Trends</strong> - See quarter-over-quarter performance graphs</li>
              </ul>
            </div>

            {/* Snapshots */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-orange-100 rounded-full flex items-center justify-center text-orange-600">📸</span>
                Snapshots (Bi-Weekly)
              </h4>
              <p className="text-slate-300 mb-3">Create mid-month check-in slides showing everyone on one page.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Schedule</strong> - Upload on the 1st and 15th of each month</li>
                <li>• <strong>Grid Layout</strong> - All employees visible on one slide, sorted by tier</li>
                <li>• <strong>Color Coding</strong> - 🟢 ≥80%, 🟡 70-79%, 🔴 &lt;70% of benchmark</li>
                <li>• <strong>Fun Backgrounds</strong> - Choose from 12 colorful themes</li>
              </ul>
              <div className="mt-3 p-3 bg-orange-50 rounded-lg text-sm text-orange-800">
                <strong>💡 Tip:</strong> Snapshots are standalone - each upload creates a separate point-in-time record.
              </div>
            </div>

            {/* Yodeck Slides */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-blue-600">🖥️</span>
                Yodeck Slides
              </h4>
              <p className="text-slate-300 mb-3">Generate 1920x1080 PNG slides for digital signage displays.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Top 10</strong> - Leaderboard of best performers</li>
                <li>• <strong>Tier Slides</strong> - Separate slides for each tier (Trainers, Bartenders, A/B/C)</li>
                <li>• <strong>Most Improved</strong> - Employees with biggest score increases</li>
                <li>• <strong>Promotion Watchlist</strong> - B-Servers close to A-Server status</li>
                <li>• <strong>Coaching Focus</strong> - C-Servers needing attention (manager only)</li>
              </ul>
              <div className="mt-3 p-3 bg-blue-50 rounded-lg text-sm text-blue-800">
                <strong>🎨 Themes:</strong> Customize colors and seasonal decorations (Valentine's, Christmas, etc.) in Settings above.
              </div>
            </div>

            {/* Analytics */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-indigo-100 rounded-full flex items-center justify-center text-indigo-600">📈</span>
                Analytics
              </h4>
              <p className="text-slate-300 mb-3">Deep dive into team metrics and trends.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Overview Tab</strong> - Average metrics with visual range charts vs benchmarks</li>
                <li>• <strong>Trends Tab</strong> - Quarter-over-quarter comparisons</li>
                <li>• <strong>Tier Distribution</strong> - Pie charts showing team composition</li>
                <li>• <strong>Download PDF</strong> - Export analytics summary</li>
              </ul>
            </div>

            {/* Settings */}
            <div className="bg-slate-800 border border-gray-200 rounded-xl p-5 shadow-sm">
              <h4 className="font-bold text-lg mb-2 flex items-center gap-2">
                <span className="w-8 h-8 bg-gray-200 rounded-full flex items-center justify-center text-slate-300">⚙️</span>
                Settings (This Page)
              </h4>
              <p className="text-slate-300 mb-3">Configure how scores are calculated and how slides look.</p>
              <ul className="text-sm text-slate-300 space-y-1 ml-10">
                <li>• <strong>Benchmarks</strong> - Target values for PPA, LBW, Glassware, LSC, CV</li>
                <li>• <strong>Weights</strong> - How much each metric (PPA, LBW, Glass, LSC) contributes to base score (must = 85%). CV points are added separately.</li>
                <li>• <strong>Tier Thresholds</strong> - Score cutoffs for A-Server (≥80) and B-Server (≥70)</li>
                <li>• <strong>Slide Themes</strong> - Colors and seasonal decorations for Yodeck</li>
              </ul>
              <div className="mt-3 p-3 bg-yellow-50 rounded-lg text-sm text-yellow-800">
                <strong>⚠️ Note:</strong> Once scores are generated, benchmarks and weights are locked. Only theme settings can be changed.
              </div>
            </div>
          </div>

          {/* Scoring Formula */}
          <div className="bubba-card mt-6">
            <div className="tape tape-red" style={{ top: '-8px', right: '20%', transform: 'rotate(2deg)' }} />
            <div className="p-6 pt-8">
              <h3 className="text-xl font-bold text-primary mb-4">🧮 How Scoring Works</h3>
              <div className="bg-background rounded-lg p-4 font-mono text-sm mb-4">
                <p className="text-slate-200 mb-2"><strong>Normalized Score</strong> = (Actual Value / Benchmark) × 100</p>
                <p className="text-slate-200 mb-2"><strong>Metric Points</strong> = Normalized Score × Weight × Max Points</p>
                <p className="text-slate-200 mb-2"><strong>Bonus</strong> = MIN((Score - 100) × 0.2, 5) if Score &gt; 100</p>
                <p className="text-slate-200"><strong>Total Score</strong> = Sum of all Metric Points + Bonuses</p>
              </div>
              <div className="grid md:grid-cols-2 gap-4 text-sm">
                <div>
                  <h5 className="font-semibold mb-2">Server Tiers:</h5>
                  <ul className="space-y-1 text-slate-300">
                    <li>🟢 <strong>A-Server</strong>: Score ≥ 80.0</li>
                    <li>🟡 <strong>B-Server</strong>: Score ≥ 70</li>
                    <li>🔴 <strong>C-Server</strong>: Score &lt; 70</li>
                  </ul>
                </div>
                <div>
                  <h5 className="font-semibold mb-2">Special Roles:</h5>
                  <ul className="space-y-1 text-slate-300">
                    <li>👑 <strong>Trainer</strong>: Always ranked first</li>
                    <li>🍸 <strong>Bartender</strong>: Ranked after Trainers</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>

          {/* Template Columns */}
          <div className="bubba-card mt-6">
            <div className="tape" style={{ top: '-8px', left: '40%', transform: 'rotate(-1deg)' }} />
            <div className="p-6 pt-8">
              <h3 className="text-xl font-bold text-primary mb-4">📋 Upload Template Columns</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b-2 border-primary">
                      <th className="text-left py-2 px-3">Column</th>
                      <th className="text-left py-2 px-3">Required</th>
                      <th className="text-left py-2 px-3">Description</th>
                    </tr>
                  </thead>
                  <tbody className="text-slate-300">
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Employee Name</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Full name</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Job Title</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Server, Bartender, or Trainer</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Guests</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Total guests served</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Net Sales</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Total sales in $</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Liquor Sales</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Liquor sales in $</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Beer Sales</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Beer sales in $</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Wine Sales</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Wine sales in $</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">Glassware Sales</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Glassware sales in $</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">LSC Count</td><td className="py-2 px-3">✅ Yes</td><td className="py-2 px-3">Number of Landry's Select Card enrollments</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">CV Promoters</td><td className="py-2 px-3">Optional</td><td className="py-2 px-3">Customer Voice scores 9-10</td></tr>
                    <tr className="border-b"><td className="py-2 px-3 font-medium">CV Detractors</td><td className="py-2 px-3">Optional</td><td className="py-2 px-3">Customer Voice scores 0-6</td></tr>
                    <tr><td className="py-2 px-3 font-medium">Review Mentions</td><td className="py-2 px-3">Optional</td><td className="py-2 px-3">Online review mentions</td></tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* FAQ */}
          <div className="bubba-card mt-6 mb-8">
            <div className="tape tape-red" style={{ top: '-8px', left: '60%', transform: 'rotate(1deg)' }} />
            <div className="p-6 pt-8">
              <h3 className="text-xl font-bold text-primary mb-4">❓ Frequently Asked Questions</h3>
              <div className="space-y-4">
                <div>
                  <h5 className="font-semibold text-gray-800">Why can't I change benchmarks after uploading data?</h5>
                  <p className="text-slate-300 text-sm">Once scores are generated, benchmarks are locked to maintain consistency. Create a new quarter if you need different settings.</p>
                </div>
                <div>
                  <h5 className="font-semibold text-gray-800">What's the difference between Quarterly Data and Snapshots?</h5>
                  <p className="text-slate-300 text-sm">Quarterly data (Dashboard) is your main scoring - one upload per quarter. Snapshots are bi-weekly check-ins (1st & 15th) that create standalone visual reports.</p>
                </div>
                <div>
                  <h5 className="font-semibold text-gray-800">How do I fix a mistake in uploaded data?</h5>
                  <p className="text-slate-300 text-sm">Go to Employees page, find the employee, and use Edit to correct values. Or delete all and re-upload a corrected file.</p>
                </div>
                <div>
                  <h5 className="font-semibold text-gray-800">What's LBW?</h5>
                  <p className="text-slate-300 text-sm">LBW = Liquor + Beer + Wine sales combined. It's automatically calculated from the three separate columns.</p>
                </div>
                <div>
                  <h5 className="font-semibold text-gray-800">What does "Guests/LSC" mean?</h5>
                  <p className="text-slate-300 text-sm">Guests per Landry's Select Card enrollment. Lower is better - it means the employee is signing up more cards relative to their guest count.</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Nickname Aliases — affects CV/RT employee matching */}
        <div className="mt-8" data-testid="nickname-section">
          <NicknameManager />
        </div>
      </div>
    </div>
  );
}
