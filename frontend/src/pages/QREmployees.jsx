import { useState, useEffect } from "react";
import { QrCode, Plus, Trash2, RefreshCw, Download, Copy, ExternalLink, Users, Archive, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import QRCode from "qrcode";
import JSZip from "jszip";
import { saveAs } from "file-saver";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function QREmployees() {
  const [employees, setEmployees] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [downloading, setDownloading] = useState(false);

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

  // Generate QR as blob for ZIP
  const generateQRBlob = async (url) => {
    const qrDataUrl = await QRCode.toDataURL(url, {
      width: settings?.qr_size || 300,
      margin: 2,
      color: {
        dark: settings?.qr_color || '#000000',
        light: settings?.qr_bg_color || '#FFFFFF'
      }
    });
    
    // Convert data URL to blob
    const response = await fetch(qrDataUrl);
    return await response.blob();
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
      // Sanitize name for filename
      const safeName = employeeName.toLowerCase().replace(/[^a-z0-9]/g, '_');
      link.download = `${safeName}_${platform}_qr.png`;
      link.href = qrDataUrl;
      link.click();
      toast.success(`Downloaded ${platform} QR for ${employeeName}`);
    } catch (error) {
      toast.error("Failed to generate QR");
    }
  };

  // Download All QR codes as ZIP
  const downloadAllQRs = async () => {
    if (employees.length === 0) {
      toast.error("No employees to download");
      return;
    }

    setDownloading(true);
    toast.info(`Generating ${employees.length * 2} QR codes...`);

    try {
      const zip = new JSZip();
      
      for (const emp of employees) {
        // Sanitize name for filename
        const safeName = emp.name.toLowerCase().replace(/[^a-z0-9]/g, '_');
        
        // Generate Yelp QR
        const yelpUrl = generateQRUrl(emp.id, 'yelp');
        const yelpBlob = await generateQRBlob(yelpUrl);
        zip.file(`${safeName}_yelp_qr.png`, yelpBlob);
        
        // Generate Google QR
        const googleUrl = generateQRUrl(emp.id, 'google');
        const googleBlob = await generateQRBlob(googleUrl);
        zip.file(`${safeName}_google_qr.png`, googleBlob);
      }

      // Generate and download ZIP using file-saver for better mobile compatibility
      const zipBlob = await zip.generateAsync({ type: "blob" });
      saveAs(zipBlob, "qr_codes_all_employees.zip");
      
      toast.success(`Downloaded ${employees.length * 2} QR codes`);
    } catch (error) {
      console.error("ZIP generation error:", error);
      toast.error("Failed to generate ZIP");
    }

    setDownloading(false);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-4 md:p-6">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-white flex items-center gap-3">
              <QrCode className="w-7 h-7 md:w-8 md:h-8 text-purple-400" />
              QR Codes
            </h1>
            <p className="text-slate-400 text-sm mt-1">Manage employee QR codes</p>
          </div>
          <div className="flex gap-2">
            <Button 
              onClick={downloadAllQRs} 
              disabled={downloading || employees.length === 0}
              className="bg-blue-600 hover:bg-blue-700 text-sm"
              data-testid="download-all-btn"
            >
              {downloading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Archive className="w-4 h-4 mr-2" />
              )}
              <span className="hidden sm:inline">Download All</span>
              <span className="sm:hidden">All ZIP</span>
            </Button>
            <Button 
              onClick={syncFromMain} 
              disabled={syncing}
              className="bg-purple-600 hover:bg-purple-700 text-sm"
            >
              <Users className={`w-4 h-4 mr-2 ${syncing ? 'animate-spin' : ''}`} />
              <span className="hidden sm:inline">Sync from Employees</span>
              <span className="sm:hidden">Sync</span>
            </Button>
          </div>
        </div>

        {/* Add Employee */}
        <div className="bg-white/5 rounded-xl p-3 md:p-4 mb-6 flex gap-2 md:gap-3">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Enter employee name..."
            className="bg-slate-800 border-slate-700 text-sm"
            onKeyPress={(e) => e.key === 'Enter' && addEmployee()}
          />
          <Button onClick={addEmployee} className="bg-green-600 hover:bg-green-700 shrink-0">
            <Plus className="w-4 h-4 sm:mr-2" />
            <span className="hidden sm:inline">Add</span>
          </Button>
        </div>

        {/* Employee Count */}
        {employees.length > 0 && (
          <div className="text-slate-400 text-sm mb-4">
            {employees.length} employees • {employees.length * 2} QR codes total
          </div>
        )}

        {/* Employee List - Mobile Optimized */}
        <div className="space-y-3">
          {employees.map((emp) => (
            <div key={emp.id} className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
              {/* Employee Header */}
              <div className="flex items-center justify-between p-3 md:p-4 border-b border-white/10">
                <div className="flex items-center gap-2 md:gap-4 min-w-0">
                  <span className="text-base md:text-xl font-semibold text-white truncate">{emp.name}</span>
                  <span className="text-xs md:text-sm text-slate-400 shrink-0">
                    Total: <span className="text-blue-400 font-bold">{emp.yelp_clicks + emp.google_clicks}</span>
                  </span>
                </div>
                <div className="flex items-center gap-1 md:gap-2 shrink-0">
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-slate-600 h-8 w-8 p-0"
                    onClick={() => resetClicks(emp.id, emp.name)}
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-red-600 text-red-400 hover:bg-red-600/20 h-8 w-8 p-0"
                    onClick={() => deleteEmployee(emp.id, emp.name)}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              
              {/* QR Code Options - Stack on Mobile */}
              <div className="grid grid-cols-1 sm:grid-cols-2 sm:divide-x divide-y sm:divide-y-0 divide-white/10">
                {/* Yelp */}
                <div className="p-3 md:p-4">
                  <div className="flex items-center justify-between mb-2 md:mb-3">
                    <span className="text-red-400 font-semibold text-sm md:text-base">Yelp QR</span>
                    <span className="text-red-400 font-bold text-sm">{emp.yelp_clicks} clicks</span>
                  </div>
                  <div className="flex gap-1.5 md:gap-2">
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="flex-1 border-red-500/50 text-red-400 text-xs md:text-sm h-8 md:h-9"
                      onClick={() => downloadQR(emp.id, emp.name, 'yelp')}
                    >
                      <Download className="w-3.5 h-3.5 mr-1" />
                      Download
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600 h-8 md:h-9 w-8 md:w-9 p-0"
                      onClick={() => copyUrl(generateQRUrl(emp.id, 'yelp'))}
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600 h-8 md:h-9 w-8 md:w-9 p-0"
                      onClick={() => window.open(generateQRUrl(emp.id, 'yelp'), '_blank')}
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
                
                {/* Google */}
                <div className="p-3 md:p-4">
                  <div className="flex items-center justify-between mb-2 md:mb-3">
                    <span className="text-green-400 font-semibold text-sm md:text-base">Google QR</span>
                    <span className="text-green-400 font-bold text-sm">{emp.google_clicks} clicks</span>
                  </div>
                  <div className="flex gap-1.5 md:gap-2">
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="flex-1 border-green-500/50 text-green-400 text-xs md:text-sm h-8 md:h-9"
                      onClick={() => downloadQR(emp.id, emp.name, 'google')}
                    >
                      <Download className="w-3.5 h-3.5 mr-1" />
                      Download
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600 h-8 md:h-9 w-8 md:w-9 p-0"
                      onClick={() => copyUrl(generateQRUrl(emp.id, 'google'))}
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </Button>
                    <Button 
                      size="sm" 
                      variant="outline" 
                      className="border-slate-600 h-8 md:h-9 w-8 md:w-9 p-0"
                      onClick={() => window.open(generateQRUrl(emp.id, 'google'), '_blank')}
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ))}
          
          {employees.length === 0 && !loading && (
            <div className="text-center text-slate-400 py-12 bg-white/5 rounded-xl">
              <QrCode className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p>No employees yet.</p>
              <p className="text-sm mt-1">Add one above or sync from main employee list.</p>
            </div>
          )}
          
          {loading && (
            <div className="text-center text-slate-400 py-12 bg-white/5 rounded-xl">
              <Loader2 className="w-8 h-8 mx-auto mb-3 animate-spin" />
              <p>Loading...</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
