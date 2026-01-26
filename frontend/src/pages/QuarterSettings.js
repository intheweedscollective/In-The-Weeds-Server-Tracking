import { useState, useEffect } from "react";
import { Settings, Lock, Unlock, Save, RefreshCw, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function QuarterSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [allSettings, setAllSettings] = useState([]);
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
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
    a_server_min_score: 85.1,
    b_server_min_score: 70.1
  });

  useEffect(() => {
    fetchAllSettings();
  }, []);

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true);
      try {
        const response = await axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
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
          a_server_min_score: response.data.a_server_min_score || 85.1,
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
            a_server_min_score: 85.1,
            b_server_min_score: 70.1
          });
        } else {
          console.error("Error fetching settings:", error);
          toast.error("Error loading settings");
        }
      } finally {
        setLoading(false);
      }
    };

    const loadSuggestions = async () => {
      try {
        const response = await axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}/benchmark-suggestions`);
        setSuggestions(response.data);
      } catch (error) {
        console.error("Error fetching suggestions:", error);
        setSuggestions(null);
      }
    };

    loadSettings();
    loadSuggestions();
  }, [selectedYear, selectedQuarter]);

  const fetchAllSettings = async () => {
    try {
      const response = await axios.get(`${API}/v2/quarter-settings`);
      setAllSettings(response.data);
    } catch (error) {
      console.error("Error fetching all settings:", error);
    }
  };

  const refetchSettings = async () => {
    setLoading(true);
    try {
      const response = await axios.get(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`);
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
        bonus_cap: response.data.bonus_cap
      });
      setIsNew(false);
    } catch (error) {
      console.error("Error fetching settings:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    // Validate weights sum to 1.0 (including CV weight)
    const weightSum = formData.weight_ppa + formData.weight_lbw + formData.weight_glass + formData.weight_lsc + formData.weight_cv;
    if (Math.abs(weightSum - 1.0) > 0.01) {
      toast.error(`Weights must sum to 1.0 (currently ${weightSum.toFixed(2)})`);
      return;
    }

    setSaving(true);
    try {
      if (isNew) {
        await axios.post(`${API}/v2/quarter-settings`, {
          year: selectedYear,
          quarter: selectedQuarter,
          ...formData
        });
        toast.success(`Created settings for ${selectedQuarter} ${selectedYear}`);
      } else {
        await axios.put(`${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`, formData);
        toast.success(`Updated settings for ${selectedQuarter} ${selectedYear}`);
      }
      refetchSettings();
      fetchAllSettings();
    } catch (error) {
      console.error("Error saving settings:", error);
      toast.error(error.response?.data?.detail || "Error saving settings");
    } finally {
      setSaving(false);
    }
  };

  const applySuggestion = (metric, value) => {
    setFormData(prev => ({
      ...prev,
      [`benchmark_${metric}`]: value
    }));
  };

  const weightSum = formData.weight_ppa + formData.weight_lbw + formData.weight_glass + formData.weight_lsc + formData.weight_cv;
  const weightsValid = Math.abs(weightSum - 1.0) <= 0.01;

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
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
      
      <Navigation />
      
      <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <Settings className="w-8 h-8 text-secondary" />
            <h1 className="text-3xl font-serif font-black text-foreground">
              Quarter Settings
            </h1>
          </div>
          <p className="text-gray-500">
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
                  className="w-full h-10 rounded-lg border-2 border-gray-200 bg-white px-3 text-sm"
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
                  className="w-full h-10 rounded-lg border-2 border-gray-200 bg-white px-3 text-sm"
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
                <span className="px-3 py-1 bg-red-100 text-red-800 rounded-full text-sm font-semibold flex items-center gap-2">
                  <Lock className="w-4 h-4" />
                  Locked (scores generated)
                </span>
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
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">PPA</div>
                    <div className="text-sm text-gray-600 mb-2">Avg: ${suggestions.previous_averages.avg_ppa}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('ppa', suggestions.suggestions.ppa.default)}
                        className="w-full text-xs bg-blue-100 hover:bg-blue-200 text-blue-800 px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.ppa.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.lbw && (
                  <div className="p-3 bg-purple-50 rounded-lg border border-purple-100">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">LBW/Guest</div>
                    <div className="text-sm text-gray-600 mb-2">Avg: ${suggestions.previous_averages.avg_lbw}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('lbw', suggestions.suggestions.lbw.default)}
                        className="w-full text-xs bg-purple-100 hover:bg-purple-200 text-purple-800 px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.lbw.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.glass && (
                  <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">Glass/Guest</div>
                    <div className="text-sm text-gray-600 mb-2">Avg: ${suggestions.previous_averages.avg_glass}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('glass', suggestions.suggestions.glass.default)}
                        className="w-full text-xs bg-gray-200 hover:bg-gray-300 text-gray-800 px-2 py-1 rounded"
                      >
                        Use ${suggestions.suggestions.glass.default} (115%)
                      </button>
                    </div>
                  </div>
                )}
                {suggestions.suggestions?.lsc && (
                  <div className="p-3 bg-green-50 rounded-lg border border-green-100">
                    <div className="text-xs text-gray-500 uppercase font-semibold mb-1">Guests/LSC</div>
                    <div className="text-sm text-gray-600 mb-2">Avg: {suggestions.previous_averages.avg_lsc}</div>
                    <div className="space-y-1">
                      <button 
                        onClick={() => applySuggestion('lsc', suggestions.suggestions.lsc.default)}
                        className="w-full text-xs bg-green-100 hover:bg-green-200 text-green-800 px-2 py-1 rounded"
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
            <p className="text-sm text-gray-500 mb-4">
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
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Metric Weights (Q1 2026 Model)</h2>
            <p className="text-sm text-gray-500 mb-4">
              Weights must sum to 1.0. Current sum: 
              <span className={`ml-2 font-bold ${weightsValid ? 'text-green-600' : 'text-red-600'}`}>
                {weightSum.toFixed(2)}
              </span>
            </p>
            
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="space-y-2">
                <label className="text-sm font-medium">PPA (25%)</label>
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
                <label className="text-sm font-medium">LBW (20%)</label>
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
                <label className="text-sm font-medium">Glass (15%)</label>
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
                <label className="text-sm font-medium">LSC (25%)</label>
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
              <div className="space-y-2">
                <label className="text-sm font-medium">CV & Reviews (15%)</label>
                <Input
                  type="number"
                  step="0.05"
                  min="0"
                  max="1"
                  value={formData.weight_cv}
                  onChange={(e) => setFormData(prev => ({ ...prev, weight_cv: parseFloat(e.target.value) || 0 }))}
                  disabled={settings?.is_locked}
                  className="border-2"
                />
                <p className="text-xs text-gray-400">Customer Voice + Review Tracker</p>
              </div>
            </div>
          </div>
        </div>

        {/* Bonus Settings */}
        <div className="bubba-card mb-8">
          <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <h2 className="text-lg font-serif font-bold text-foreground mb-4">Bonus Settings</h2>
            <p className="text-sm text-gray-500 mb-4">
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

        {/* Save Button */}
        {!settings?.is_locked && (
          <div className="flex justify-end">
            <Button
              onClick={handleSave}
              disabled={saving || !weightsValid}
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
                  {isNew ? 'Create Settings' : 'Save Changes'}
                </div>
              )}
            </Button>
          </div>
        )}

        {settings?.is_locked && (
          <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 text-yellow-800">
            <div className="flex items-center gap-2">
              <Lock className="w-5 h-5" />
              <span className="font-semibold">Settings are locked</span>
            </div>
            <p className="text-sm mt-1">
              Scores have been generated for this quarter. To make changes, clear the employee data first.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
