import { useState, useEffect } from "react";
import { QrCode, Plus, Trash2, RefreshCw, Download, Copy, ExternalLink, Users } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import QRCode from "qrcode";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function QREmployees() {
  const [employees, setEmployees] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [syncing, setSyncing] = useState(false);

  const fetchData = async () => {
    try {
      const [empRes, settingsRes] = await Promise.all([
        api.get('/qr/employees'),
        api.get('/qr/settings')
      ]);
      setEmployees(empRes.data);
      setSettings(settingsRes.data);
    } catch (error) {
      toast.error("Failed to load data");
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchData();
  }, []);

  const addEmployee = async () => {
    if (!newName.trim()) return;
    try {
      await api.post('/qr/employees', { name: newName.trim() });
      setNewName("");
      toast.success(`Added ${newName}`);
      fetchData();
    } catch (error) {
      toast.error("Failed to add employee");
    }
  };

  const deleteEmployee = async (id, name) => {
    if (!confirm(`Delete ${name}?`)) return;
    try {
      await api.delete(`/qr/employees/${id}`);
      toast.success(`Deleted ${name}`);
      fetchData();
    } catch (error) {
      toast.error("Failed to delete");
    }
  };

  const resetClicks = async (id, name) => {
    if (!confirm(`Reset clicks for ${name}?`)) return;
    try {
      await api.post(`/qr/employees/${id}/reset`);
      toast.success(`Reset ${name}'s clicks`);
      fetchData();
    } catch (error) {
      toast.error("Failed to reset");
    }
  };

  const syncFromMain = async () => {
    setSyncing(true);
    try {
      const res = await api.post('/qr/sync-from-employees?quarter=Q1&year=2026');
      toast.success(`Synced ${res.data.synced} new employees`);
      fetchData();
    } catch (error) {
      toast.error("Sync failed");
    }
    setSyncing(false);
  };

  const generateQRUrl = (employeeId, platform) => {
    return `${BACKEND_URL}/api/qr/scan/${employeeId}/${platform}`;
  };

  const copyUrl = (url) => {
    navigator.clipboard.writeText(url);
    toast.success("URL copied!");
  };

  const downloadQR = async (employeeId, employeeName, platform) => {
    const url = generateQRUrl(employeeId, platform);
    try {
      const qrDataUrl = await QRCode.toDataURL(url, {
        width: settings?.qr_size || 300,
        margin: 2,
        color: {
          dark: settings?.qr_color || '#000000',
          light: settings?.qr_bg_color || '#FFFFFF'
        }
      });
      
      const link = document.createElement('a');
      link.download = `${employeeName}_${platform}_qr.png`;
      link.href = qrDataUrl;
      link.click();
      toast.success(`Downloaded ${platform} QR for ${employeeName}`);
    } catch (error) {
      toast.error("Failed to generate QR");
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-bold text-white flex items-center gap-3">
              <QrCode className="w-8 h-8 text-purple-400" />
              QR Codes
            </h1>
            <p className="text-slate-400 mt-1">Manage employee QR codes</p>
          </div>
          <Button 
            onClick={syncFromMain} 
            disabled={syncing}
            className="bg-purple-600 hover:bg-purple-700"
          >
            <Users className={`w-4 h-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
            Sync from Employees
          </Button>
        </div>

        {/* Add Employee */}
        <div className="bg-white/5 rounded-xl p-4 mb-6 flex gap-3">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Enter employee name..."
            className="bg-slate-800 border-slate-700"
            onKeyPress={(e) => e.key === 'Enter' && addEmployee()}
          />
          <Button onClick={addEmployee} className="bg-green-600 hover:bg-green-700">
            <Plus className="w-4 h-4 mr-2" />
            Add
          </Button>
        </div>

        {/* Employee List */}
        <div className="space-y-4">
          {employees.map((emp) => (
            <div key={emp.id} className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-white/10">
                <div className="flex items-center gap-4">
                  <span className="text-xl font-semibold text-white">{emp.name}</span>
                  <span className="text-sm text-slate-400">
                    Total: <span className="text-blue-400 font-bold">{emp.yelp_clicks + emp.google_clicks}</span>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-slate-600"
                    onClick={() => resetClicks(emp.id, emp.name)}
                  >
                    <RefreshCw className="w-4 h-4" />
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-red-600 text-red-400 hover:bg-red-600/20"
                    onClick={() => deleteEmployee(emp.id, emp.name)}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
              
              {/* QR Code Options */}
              <div className="grid grid-cols-2 divide-x divide-white/10">
                {/* Yelp */}
                <div className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-red-400 font-semibold">Yelp QR</span>
                    <span className="text-red-400 font-bold">{emp.yelp_clicks} clicks</span>
                  </div>
                  <div className="flex gap-2">
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="flex-1 border-red-500/50 text-red-400"
                      onClick={() => downloadQR(emp.id, emp.name, 'yelp')}
                    >
                      <Download className="w-4 h-4 mr-1" />
                      Download
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => copyUrl(generateQRUrl(emp.id, 'yelp'))}
                    >
                      <Copy className="w-4 h-4" />
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => window.open(generateQRUrl(emp.id, 'yelp'), '_blank')}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
                
                {/* Google */}
                <div className="p-4">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-green-400 font-semibold">Google QR</span>
                    <span className="text-green-400 font-bold">{emp.google_clicks} clicks</span>
                  </div>
                  <div className="flex gap-2">
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="flex-1 border-green-500/50 text-green-400"
                      onClick={() => downloadQR(emp.id, emp.name, 'google')}
                    >
                      <Download className="w-4 h-4 mr-1" />
                      Download
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => copyUrl(generateQRUrl(emp.id, 'google'))}
                    >
                      <Copy className="w-4 h-4" />
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600"
                      onClick={() => window.open(generateQRUrl(emp.id, 'google'), '_blank')}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {employees.length === 0 && !loading && (
            <div className="text-center text-slate-400 py-12 bg-white/5 rounded-xl">
              No employees yet. Add one above or sync from main employee list.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
