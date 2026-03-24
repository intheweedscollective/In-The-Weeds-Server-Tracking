import { useState, useEffect } from "react";
import { Settings, Save, ExternalLink, Trash2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../components/ui/alert-dialog";

export default function QRSettings() {
  const [settings, setSettings] = useState({
    yelp_url: "",
    google_url: "",
    qr_style: "circle",
    qr_color: "#000000",
    qr_bg_color: "#FFFFFF",
    qr_size: 300
  });
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [stats, setStats] = useState({ total_scans: 0, total_employees: 0 });

  const fetchData = async () => {
    try {
      const [settingsRes, statsRes] = await Promise.all([
        api.get('/qr/settings'),
        api.get('/qr/stats')
      ]);
      setSettings(settingsRes.data);
      setStats(statsRes.data);
    } catch (error) {
      console.error("Failed to load data");
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const saveSettings = async () => {
    setSaving(true);
    try {
      await api.post('/qr/settings', settings);
      toast.success("Settings saved!");
    } catch (error) {
      toast.error("Failed to save settings");
    }
    setSaving(false);
  };

  const resetAllScans = async () => {
    setResetting(true);
    try {
      const res = await api.delete('/qr/scans/reset-all');
      toast.success(`Reset complete! Deleted ${res.data.scans_deleted} scans, reset ${res.data.employees_reset} employees.`);
      fetchData(); // Refresh stats
    } catch (error) {
      toast.error("Failed to reset scan data");
    }
    setResetting(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-white flex items-center gap-3">
            <Settings className="w-8 h-8 text-slate-400" />
            QR Settings
          </h1>
          <p className="text-slate-400 mt-1">Configure QR code behavior and styling</p>
        </div>

        <div className="space-y-6">
          {/* Review URLs */}
          <div className="bg-white/5 rounded-xl p-6 border border-white/10">
            <h2 className="text-lg font-semibold text-white mb-4">Review Page URLs</h2>
            <p className="text-sm text-slate-400 mb-4">
              When a QR code is scanned, users will be redirected to these URLs.
            </p>
            
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-red-400 mb-2">Yelp Review URL</label>
                <div className="flex gap-2">
                  <Input
                    value={settings.yelp_url}
                    onChange={(e) => setSettings({...settings, yelp_url: e.target.value})}
                    placeholder="https://www.yelp.com/biz/your-restaurant"
                    className="bg-slate-800 border-slate-700"
                  />
                  {settings.yelp_url && (
                    <Button 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => window.open(settings.yelp_url, '_blank')}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </div>
              
              <div>
                <label className="block text-sm text-green-400 mb-2">Google Review URL</label>
                <div className="flex gap-2">
                  <Input
                    value={settings.google_url}
                    onChange={(e) => setSettings({...settings, google_url: e.target.value})}
                    placeholder="https://www.google.com/maps/place/..."
                    className="bg-slate-800 border-slate-700"
                  />
                  {settings.google_url && (
                    <Button 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => window.open(settings.google_url, '_blank')}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* QR Style */}
          <div className="bg-white/5 rounded-xl p-6 border border-white/10">
            <h2 className="text-lg font-semibold text-white mb-4">QR Code Style</h2>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-slate-400 mb-2">QR Color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={settings.qr_color}
                    onChange={(e) => setSettings({...settings, qr_color: e.target.value})}
                    className="w-12 h-10 rounded cursor-pointer"
                  />
                  <Input
                    value={settings.qr_color}
                    onChange={(e) => setSettings({...settings, qr_color: e.target.value})}
                    className="bg-slate-800 border-slate-700"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm text-slate-400 mb-2">Background Color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={settings.qr_bg_color}
                    onChange={(e) => setSettings({...settings, qr_bg_color: e.target.value})}
                    className="w-12 h-10 rounded cursor-pointer"
                  />
                  <Input
                    value={settings.qr_bg_color}
                    onChange={(e) => setSettings({...settings, qr_bg_color: e.target.value})}
                    className="bg-slate-800 border-slate-700"
                  />
                </div>
              </div>
              
              <div>
                <label className="block text-sm text-slate-400 mb-2">QR Size (px)</label>
                <Input
                  type="number"
                  value={settings.qr_size}
                  onChange={(e) => setSettings({...settings, qr_size: parseInt(e.target.value) || 300})}
                  className="bg-slate-800 border-slate-700"
                />
              </div>
            </div>
          </div>

          {/* Save Button */}
          <Button 
            onClick={saveSettings} 
            disabled={saving}
            className="w-full bg-blue-600 hover:bg-blue-700"
          >
            <Save className={`w-4 h-4 mr-2 ${saving ? 'animate-spin' : ''}`} />
            Save Settings
          </Button>

          {/* Danger Zone */}
          <div className="bg-red-500/10 rounded-xl p-6 border border-red-500/30 mt-8">
            <h2 className="text-lg font-semibold text-red-400 mb-2 flex items-center gap-2">
              <AlertTriangle className="w-5 h-5" />
              Danger Zone
            </h2>
            <p className="text-sm text-slate-400 mb-4">
              Reset all QR scan tracking data. This will delete all scan records and reset all employee click counts to zero.
              Current stats: <span className="text-white font-medium">{stats.total_scans} total scans</span> across <span className="text-white font-medium">{stats.total_employees} employees</span>.
            </p>
            
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button 
                  variant="destructive"
                  className="bg-red-600 hover:bg-red-700"
                  disabled={resetting}
                >
                  <Trash2 className={`w-4 h-4 mr-2 ${resetting ? 'animate-spin' : ''}`} />
                  Reset All QR Scans
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent className="bg-slate-900 border-slate-700">
                <AlertDialogHeader>
                  <AlertDialogTitle className="text-white flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-red-500" />
                    Are you absolutely sure?
                  </AlertDialogTitle>
                  <AlertDialogDescription className="text-slate-400">
                    This action <span className="text-red-400 font-semibold">cannot be undone</span>. This will permanently delete:
                    <ul className="list-disc list-inside mt-2 space-y-1">
                      <li><span className="text-white">{stats.total_scans}</span> scan records</li>
                      <li>All click counts for <span className="text-white">{stats.total_employees}</span> employees</li>
                    </ul>
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel className="bg-slate-700 border-slate-600 text-white hover:bg-slate-600">
                    Cancel
                  </AlertDialogCancel>
                  <AlertDialogAction 
                    onClick={resetAllScans}
                    className="bg-red-600 hover:bg-red-700"
                  >
                    Yes, Reset All Scans
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </div>
        </div>
      </div>
    </div>
  );
}
