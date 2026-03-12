import { useState, useEffect } from "react";
import { Settings, Save, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";

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

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await api.get('/qr/settings');
        setSettings(res.data);
      } catch (error) {
        console.error("Failed to load settings");
      }
    };
    fetchSettings();
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
        </div>
      </div>
    </div>
  );
}
