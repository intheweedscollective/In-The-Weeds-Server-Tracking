import { useState, useEffect } from "react";
import { Upload, FileSpreadsheet, Download, CheckCircle, XCircle, AlertTriangle, RefreshCw, Users, MessageSquare, Star } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function DataUploads() {
  const [quarter, setQuarter] = useState("Q1");
  const [year, setYear] = useState(2026);
  
  // Upload states
  const [posFile, setPosFile] = useState(null);
  const [cvFile, setCvFile] = useState(null);
  const [rtFile, setRtFile] = useState(null);
  
  const [posUploading, setPosUploading] = useState(false);
  const [cvUploading, setCvUploading] = useState(false);
  const [rtUploading, setRtUploading] = useState(false);
  
  const [posResult, setPosResult] = useState(null);
  const [cvResult, setCvResult] = useState(null);
  const [rtResult, setRtResult] = useState(null);
  
  // Current data status
  const [dataStatus, setDataStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);

  const fetchDataStatus = async () => {
    setLoadingStatus(true);
    try {
      const [employeesRes, auditRes] = await Promise.all([
        api.get(`/v2/employees?quarter=${quarter}&year=${year}`),
        api.get(`/v2/audit/data-cap-check?quarter=${quarter}&year=${year}`)
      ]);
      
      setDataStatus({
        employees: employeesRes.data?.length || 0,
        cv: auditRes.data?.customer_voice || {},
        rt: auditRes.data?.review_tracker || {}
      });
    } catch (error) {
      console.error("Failed to fetch data status");
    }
    setLoadingStatus(false);
  };

  useEffect(() => {
    fetchDataStatus();
  }, [quarter, year]);

  // POS Upload
  const handlePosUpload = async () => {
    if (!posFile) return;
    setPosUploading(true);
    setPosResult(null);
    
    const formData = new FormData();
    formData.append('file', posFile);
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/v2/pos-ocr/upload`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      if (response.ok) {
        setPosResult({ success: true, data });
        toast.success(`Extracted ${data.employees?.length || 0} employees from POS report`);
        fetchDataStatus();
      } else {
        setPosResult({ success: false, error: data.detail });
        toast.error(data.detail || "POS upload failed");
      }
    } catch (error) {
      setPosResult({ success: false, error: error.message });
      toast.error("POS upload failed");
    }
    setPosUploading(false);
  };

  // CV/NPS Upload
  const handleCvUpload = async () => {
    if (!cvFile) return;
    setCvUploading(true);
    setCvResult(null);
    
    const formData = new FormData();
    formData.append('file', cvFile);
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/v2/cv/server-performance/upload?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setCvResult({ success: true, data });
        toast.success(`Updated ${data.summary?.employees_updated || 0} employees with CV data`);
        fetchDataStatus();
      } else {
        setCvResult({ success: false, error: data.detail || "Upload failed" });
        toast.error(data.detail || "CV upload failed");
      }
    } catch (error) {
      setCvResult({ success: false, error: error.message });
      toast.error("CV upload failed");
    }
    setCvUploading(false);
  };

  // ReviewTracker Upload
  const handleRtUpload = async () => {
    if (!rtFile) return;
    setRtUploading(true);
    setRtResult(null);
    
    const formData = new FormData();
    formData.append('file', rtFile);
    
    try {
      const response = await fetch(`${BACKEND_URL}/api/v2/review-tracker/upload?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setRtResult({ success: true, data });
        toast.success(`Updated ${data.summary?.employees_updated || 0} employees with RT data`);
        fetchDataStatus();
      } else {
        setRtResult({ success: false, error: data.detail || "Upload failed" });
        toast.error(data.detail || "RT upload failed");
      }
    } catch (error) {
      setRtResult({ success: false, error: error.message });
      toast.error("RT upload failed");
    }
    setRtUploading(false);
  };

  // Download RT Template
  const downloadRtTemplate = () => {
    window.open(`${BACKEND_URL}/api/v2/review-tracker/template?quarter=${quarter}&year=${year}`, '_blank');
    toast.success("Template download started");
  };

  const UploadCard = ({ 
    title, 
    description, 
    icon: Icon, 
    file, 
    setFile, 
    onUpload, 
    uploading, 
    result,
    acceptTypes = ".xlsx,.xls,.csv",
    downloadTemplate,
    color = "blue"
  }) => (
    <div className={`bg-slate-800/50 rounded-xl border border-slate-700/50 p-6`}>
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-xl bg-${color}-500/20`}>
            <Icon className={`w-6 h-6 text-${color}-400`} />
          </div>
          <div>
            <h3 className="font-semibold text-white">{title}</h3>
            <p className="text-sm text-slate-400">{description}</p>
          </div>
        </div>
        {downloadTemplate && (
          <Button
            onClick={downloadTemplate}
            variant="outline"
            size="sm"
            className="border-slate-600 text-slate-300 hover:bg-slate-700"
          >
            <Download className="w-4 h-4 mr-2" />
            Template
          </Button>
        )}
      </div>
      
      <div className="space-y-4">
        <div className="flex items-center gap-3">
          <label className="flex-1">
            <input
              type="file"
              accept={acceptTypes}
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden"
            />
            <div className={`flex items-center justify-center gap-2 p-4 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
              file 
                ? 'border-green-500/50 bg-green-500/10' 
                : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50'
            }`}>
              {file ? (
                <>
                  <FileSpreadsheet className="w-5 h-5 text-green-400" />
                  <span className="text-green-400 font-medium truncate max-w-[200px]">{file.name}</span>
                </>
              ) : (
                <>
                  <Upload className="w-5 h-5 text-slate-400" />
                  <span className="text-slate-400">Click to select file</span>
                </>
              )}
            </div>
          </label>
          <Button
            onClick={onUpload}
            disabled={!file || uploading}
            className={`bg-${color}-600 hover:bg-${color}-700`}
          >
            {uploading ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              "Upload"
            )}
          </Button>
        </div>
        
        {/* Result Display */}
        {result && (
          <div className={`p-4 rounded-lg ${result.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
            <div className="flex items-center gap-2 mb-2">
              {result.success ? (
                <CheckCircle className="w-5 h-5 text-green-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
              <span className={result.success ? 'text-green-400' : 'text-red-400'}>
                {result.success ? 'Upload Successful' : 'Upload Failed'}
              </span>
            </div>
            {result.success && result.data?.summary && (
              <div className="text-sm text-slate-300 space-y-1">
                {result.data.summary.employees_updated !== undefined && (
                  <p>Employees updated: <span className="text-white font-medium">{result.data.summary.employees_updated}</span></p>
                )}
                {result.data.summary.total_responses !== undefined && (
                  <p>Total responses: <span className="text-white font-medium">{result.data.summary.total_responses}</span></p>
                )}
                {result.data.summary.total_promoters !== undefined && (
                  <p>Promoters: <span className="text-green-400 font-medium">{result.data.summary.total_promoters}</span> | Detractors: <span className="text-red-400 font-medium">{result.data.summary.total_detractors}</span></p>
                )}
                {result.data.summary.total_mentions !== undefined && (
                  <p>Total mentions: <span className="text-white font-medium">{result.data.summary.total_mentions}</span></p>
                )}
              </div>
            )}
            {result.error && (
              <p className="text-sm text-red-300">{result.error}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-900 p-4 md:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl md:text-3xl font-bold text-white mb-2">Data Uploads</h1>
          <p className="text-slate-400">Upload your data files to calculate employee scores</p>
        </div>

        {/* Quarter Selector */}
        <div className="flex items-center gap-4 mb-6 p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
          <span className="text-slate-400">Quarter:</span>
          <Select value={year.toString()} onValueChange={(v) => setYear(parseInt(v))}>
            <SelectTrigger className="w-24 bg-slate-900 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="2025">2025</SelectItem>
              <SelectItem value="2026">2026</SelectItem>
            </SelectContent>
          </Select>
          <Select value={quarter} onValueChange={setQuarter}>
            <SelectTrigger className="w-20 bg-slate-900 border-slate-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="Q1">Q1</SelectItem>
              <SelectItem value="Q2">Q2</SelectItem>
              <SelectItem value="Q3">Q3</SelectItem>
              <SelectItem value="Q4">Q4</SelectItem>
            </SelectContent>
          </Select>
          
          {/* Current Data Status */}
          <div className="ml-auto flex items-center gap-4 text-sm">
            {loadingStatus ? (
              <RefreshCw className="w-4 h-4 animate-spin text-slate-400" />
            ) : (
              <>
                <div className="flex items-center gap-1">
                  <Users className="w-4 h-4 text-blue-400" />
                  <span className="text-slate-400">Employees:</span>
                  <span className="text-white font-medium">{dataStatus?.employees || 0}</span>
                </div>
                <div className="flex items-center gap-1">
                  <MessageSquare className="w-4 h-4 text-green-400" />
                  <span className="text-slate-400">CV:</span>
                  <span className="text-white font-medium">{dataStatus?.cv?.our_count || 0}</span>
                </div>
                <div className="flex items-center gap-1">
                  <Star className="w-4 h-4 text-yellow-400" />
                  <span className="text-slate-400">RT:</span>
                  <span className="text-white font-medium">{dataStatus?.rt?.our_count || 0}</span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Upload Order Guide */}
        <div className="mb-6 p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-blue-400 mt-0.5" />
            <div>
              <h4 className="font-medium text-blue-400 mb-1">Recommended Upload Order</h4>
              <ol className="text-sm text-slate-300 space-y-1 list-decimal list-inside">
                <li><strong>POS Data</strong> - Creates employee records with operational metrics</li>
                <li><strong>CV/NPS Data</strong> - Adds Customer Voice scores to existing employees</li>
                <li><strong>ReviewTracker Data</strong> - Adds review mention bonuses</li>
              </ol>
            </div>
          </div>
        </div>

        {/* Upload Cards */}
        <div className="space-y-6">
          {/* POS Upload */}
          <UploadCard
            title="1. POS Data (Operational Metrics)"
            description="Upload POS report with PPA, LBW, LSC, Glassware metrics"
            icon={FileSpreadsheet}
            file={posFile}
            setFile={setPosFile}
            onUpload={handlePosUpload}
            uploading={posUploading}
            result={posResult}
            acceptTypes=".xlsx,.xls,.csv,.pdf,.png,.jpg,.jpeg"
            color="blue"
          />

          {/* CV/NPS Upload */}
          <UploadCard
            title="2. Customer Voice / NPS Data"
            description="Upload Server Performance Report from Loyalty Voice"
            icon={MessageSquare}
            file={cvFile}
            setFile={setCvFile}
            onUpload={handleCvUpload}
            uploading={cvUploading}
            result={cvResult}
            acceptTypes=".xlsx,.xls,.csv"
            color="green"
          />

          {/* ReviewTracker Upload */}
          <UploadCard
            title="3. ReviewTracker Mentions"
            description="Upload positive review mentions per employee"
            icon={Star}
            file={rtFile}
            setFile={setRtFile}
            onUpload={handleRtUpload}
            uploading={rtUploading}
            result={rtResult}
            acceptTypes=".xlsx,.xls,.csv"
            downloadTemplate={downloadRtTemplate}
            color="yellow"
          />
        </div>

        {/* Post-Upload Actions */}
        <div className="mt-8 p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
          <h3 className="font-semibold text-white mb-3">After Uploading</h3>
          <div className="flex flex-wrap gap-3">
            <Button
              onClick={() => window.location.href = '/scoring-audit'}
              variant="outline"
              className="border-slate-600"
            >
              Run Audit
            </Button>
            <Button
              onClick={() => window.location.href = '/rankings'}
              variant="outline"
              className="border-slate-600"
            >
              View Rankings
            </Button>
            <Button
              onClick={() => window.location.href = '/employees'}
              variant="outline"
              className="border-slate-600"
            >
              View Employees
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
