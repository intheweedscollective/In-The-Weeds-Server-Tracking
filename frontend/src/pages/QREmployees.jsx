import { useState, useEffect } from "react";
import { QrCode, Plus, Trash2, RefreshCw, Download, Copy, ExternalLink, Users, Archive, Loader2, Eye, X } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import StyledQRCode, { generateStyledQRDataUrl } from "../components/StyledQRCode";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import { getDisplayFirstName } from "../utils/displayName";

const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/+$/, "");

export default function QREmployees() {
  const [employees, setEmployees] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [syncing, setSyncing] = useState(false);
  const [downloading, setDownloading] = useState(false);
  
  // QR Preview Modal
  const [previewEmployee, setPreviewEmployee] = useState(null);
  const [previewPlatform, setPreviewPlatform] = useState("google");

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
    // Use the simple /go/ endpoint for Google (more reliable)
    if (platform === 'google') {
      return `${BACKEND_URL}/api/qr/go/${employeeId}`;
    }
    // Use the simple /ta/ endpoint for TripAdvisor
    if (platform === 'tripadvisor') {
      return `${BACKEND_URL}/api/qr/ta/${employeeId}`;
    }
    return `${BACKEND_URL}/api/qr/scan/${employeeId}/${platform}`;
  };

  const copyUrl = (url) => {
    navigator.clipboard.writeText(url);
    toast.success("URL copied!");
  };

  // Download styled QR code
  const downloadQR = async (employeeId, employeeName, platform) => {
    const url = generateQRUrl(employeeId, platform);
    try {
      toast.info("Generating styled QR...");
      
      const qrDataUrl = await generateStyledQRDataUrl(url, {
        size: 400,
        logoSize: 140, // Large logo for printed QR codes
        qrColor: settings?.qr_color || '#000000',
        bgColor: settings?.qr_bg_color || '#FFFFFF',
        showFrame: false
      });
      
      const link = document.createElement('a');
      const safeName = employeeName.toLowerCase().replace(/[^a-z0-9]/g, '_');
      link.download = `${safeName}_${platform}_qr.png`;
      link.href = qrDataUrl;
      link.click();
      toast.success(`Downloaded ${platform} QR for ${employeeName}`);
    } catch (error) {
      console.error("QR generation error:", error);
      toast.error("Failed to generate QR");
    }
  };

  // Download All QR codes as ZIP with styled QRs
  const downloadAllQRs = async () => {
    if (employees.length === 0) {
      toast.error("No employees to download");
      return;
    }

    setDownloading(true);
    toast.info(`Generating ${employees.length} styled QR codes...`);

    try {
      const zip = new JSZip();
      
      for (let i = 0; i < employees.length; i++) {
        const emp = employees[i];
        const safeName = emp.name.toLowerCase().replace(/[^a-z0-9]/g, '_');
        
        // Generate one styled QR per platform so the ZIP contains Google, Yelp,
        // and TripAdvisor codes for each employee.
        const platforms = ['google', 'yelp', 'tripadvisor'];
        for (const platform of platforms) {
          const url = generateQRUrl(emp.id, platform);
          const qrDataUrl = await generateStyledQRDataUrl(url, {
            size: 400,
            logoSize: 160,
            showFrame: false
          });
          const blob = await (await fetch(qrDataUrl)).blob();
          zip.file(`${safeName}_${platform}_qr.png`, blob);
        }
        
        // Update progress
        if ((i + 1) % 5 === 0) {
          toast.info(`Processing ${i + 1} of ${employees.length}...`);
        }
      }
      
      // Generate and download ZIP
      const zipBlob = await zip.generateAsync({ type: "blob" });
      saveAs(zipBlob, "styled_qr_codes.zip");
      toast.success(`Downloaded ${employees.length} styled QR codes!`);
    } catch (error) {
      console.error("ZIP generation error:", error);
      toast.error("Failed to generate ZIP");
    }
    
    setDownloading(false);
  };

  // Open preview modal
  const openPreview = (employee, platform = "google") => {
    setPreviewEmployee(employee);
    setPreviewPlatform(platform);
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
            <p className="text-slate-400 text-sm mt-1">Professional styled QR codes for your team</p>
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
              <span className="hidden sm:inline">Download All (Styled)</span>
              <span className="sm:hidden">ZIP</span>
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
            {employees.length} employees • Click "Preview" to see styled QR code
          </div>
        )}

        {/* Employee List */}
        <div className="space-y-3">
          {employees.map((emp) => (
            <div key={emp.id} className="bg-white/5 rounded-xl border border-white/10 overflow-hidden">
              {/* Employee Header */}
              <div className="flex items-center justify-between p-3 md:p-4 border-b border-white/10">
                <div className="flex items-center gap-2 md:gap-4 min-w-0">
                  <span className="text-base md:text-xl font-semibold text-white truncate">{getDisplayFirstName(emp)}</span>
                  <span className="text-xs md:text-sm text-slate-400 shrink-0">
                    Scans: <span className="text-blue-400 font-bold">{(emp.yelp_clicks || 0) + (emp.google_clicks || 0) + (emp.tripadvisor_clicks || 0)}</span>
                  </span>
                </div>
                <div className="flex items-center gap-1 md:gap-2 shrink-0">
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-slate-600 h-8 w-8 p-0"
                    onClick={() => resetClicks(emp.id, emp.name)}
                    title="Reset clicks"
                  >
                    <RefreshCw className="w-3.5 h-3.5" />
                  </Button>
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-red-600 text-red-400 hover:bg-red-600/20 h-8 w-8 p-0"
                    onClick={() => deleteEmployee(emp.id, emp.name)}
                    title="Delete employee"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
              
              {/* QR Actions */}
              <div className="p-3 md:p-4">
                <div className="flex flex-wrap gap-2">
                  {/* Preview Button */}
                  <Button 
                    size="sm" 
                    className="bg-purple-600 hover:bg-purple-700 text-xs md:text-sm"
                    onClick={() => openPreview(emp, 'google')}
                  >
                    <Eye className="w-3.5 h-3.5 mr-1.5" />
                    Preview QR
                  </Button>
                  
                  {/* Download Google QR */}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-green-500/50 text-green-400 text-xs md:text-sm"
                    onClick={() => downloadQR(emp.id, emp.name, 'google')}
                  >
                    <Download className="w-3.5 h-3.5 mr-1" />
                    Google QR
                  </Button>
                  
                  {/* Download Yelp QR */}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-red-500/50 text-red-400 text-xs md:text-sm"
                    onClick={() => downloadQR(emp.id, emp.name, 'yelp')}
                  >
                    <Download className="w-3.5 h-3.5 mr-1" />
                    Yelp QR
                  </Button>
                  
                  {/* Download TripAdvisor QR */}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-emerald-500/50 text-emerald-400 text-xs md:text-sm"
                    onClick={() => downloadQR(emp.id, emp.name, 'tripadvisor')}
                    data-testid={`download-tripadvisor-qr-${emp.id}`}
                  >
                    <Download className="w-3.5 h-3.5 mr-1" />
                    TripAdvisor QR
                  </Button>
                  
                  {/* Copy URL */}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-slate-600 text-xs md:text-sm"
                    onClick={() => copyUrl(generateQRUrl(emp.id, 'google'))}
                  >
                    <Copy className="w-3.5 h-3.5 mr-1" />
                    Copy URL
                  </Button>
                  
                  {/* Test Link */}
                  <Button 
                    size="sm" 
                    variant="outline" 
                    className="border-slate-600 text-xs md:text-sm"
                    onClick={() => window.open(generateQRUrl(emp.id, 'google'), '_blank')}
                  >
                    <ExternalLink className="w-3.5 h-3.5 mr-1" />
                    Test
                  </Button>
                </div>
                
                {/* Click Stats */}
                <div className="flex gap-4 mt-3 text-xs text-slate-400">
                  <span>Google: <span className="text-green-400 font-medium">{emp.google_clicks || 0}</span></span>
                  <span>Yelp: <span className="text-red-400 font-medium">{emp.yelp_clicks || 0}</span></span>
                  <span>TripAdvisor: <span className="text-emerald-400 font-medium">{emp.tripadvisor_clicks || 0}</span></span>
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

      {/* QR Preview Modal */}
      {previewEmployee && (
        <div 
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={() => setPreviewEmployee(null)}
        >
          <div 
            className="bg-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl border border-slate-700"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-xl font-bold text-white">{previewEmployee.name}</h3>
                <p className="text-sm text-slate-400">Google Review QR Code</p>
              </div>
              <Button 
                size="sm" 
                variant="outline" 
                className="border-slate-600 h-8 w-8 p-0"
                onClick={() => setPreviewEmployee(null)}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
            
            {/* QR Code Preview */}
            <div className="flex justify-center mb-4 bg-slate-900 rounded-xl p-6">
              <StyledQRCode
                url={generateQRUrl(previewEmployee.id, previewPlatform)}
                size={280}
                logoSize={120}
                qrColor={settings?.qr_color || '#000000'}
                bgColor={settings?.qr_bg_color || '#FFFFFF'}
                showFrame={false}
              />
            </div>
            
            {/* Scan Stats */}
            <div className="text-center mb-4">
              <span className="text-slate-400 text-sm">
                Total Scans: <span className="text-blue-400 font-bold">{previewEmployee.google_clicks}</span>
              </span>
            </div>
            
            {/* Action Buttons */}
            <div className="flex gap-2">
              <Button 
                className="flex-1 bg-green-600 hover:bg-green-700"
                onClick={() => downloadQR(previewEmployee.id, previewEmployee.name, 'google')}
              >
                <Download className="w-4 h-4 mr-2" />
                Download PNG
              </Button>
              <Button 
                variant="outline" 
                className="border-slate-600"
                onClick={() => copyUrl(generateQRUrl(previewEmployee.id, 'google'))}
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy URL
              </Button>
            </div>
            
            {/* URL Display */}
            <div className="mt-4 p-3 bg-slate-900 rounded-lg">
              <p className="text-xs text-slate-500 mb-1">Tracking URL:</p>
              <p className="text-xs text-slate-300 break-all font-mono">
                {generateQRUrl(previewEmployee.id, 'google')}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
