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

  // POS Upload - UNIFIED (saves directly to database, syncs dashboard & snapshots)
  const handlePosUpload = async () => {
    if (!posFile) return;
    setPosUploading(true);
    setPosResult(null);
    
    const formData = new FormData();
    formData.append('file', posFile);
    
    try {
      // Use the new unified endpoint that saves directly to employees_v2
      const response = await fetch(`${BACKEND_URL}/api/v2/data/upload-pos?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setPosResult({ success: true, data });
        toast.success(`Updated ${data.employees_updated || 0} employees, created ${data.employees_created || 0} new`, {
          description: "Dashboard updated. Create a Snapshot to capture this data."
        });
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
      const response = await fetch(`${BACKEND_URL}/api/v2/rt/upload?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        body: formData
      });
      const data = await response.json();
      
      if (response.ok && data.success) {
        setRtResult({ success: true, data });
        toast.success(`Updated ${data.employees_updated || 0} employees with RT data`, {
          description: "Dashboard updated. Create a Snapshot to capture this data."
        });
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
    window.open(`${BACKEND_URL}/api/v2/rt/template`, '_blank');
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
    colorClass = "blue"
  }) => {
    const colorMap = {
      blue: { bg: "bg-blue-500/20", text: "text-blue-400", btn: "bg-blue-600 hover:bg-blue-700" },
      green: { bg: "bg-green-500/20", text: "text-green-400", btn: "bg-green-600 hover:bg-green-700" },
      yellow: { bg: "bg-yellow-500/20", text: "text-yellow-400", btn: "bg-yellow-600 hover:bg-yellow-700" }
    };
    const colors = colorMap[colorClass] || colorMap.blue;

    return (
      <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 p-4 md:p-6">
        {/* Header - Stack on mobile */}
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 md:p-3 rounded-xl ${colors.bg} shrink-0`}>
              <Icon className={`w-5 h-5 md:w-6 md:h-6 ${colors.text}`} />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-white text-sm md:text-base">{title}</h3>
              <p className="text-xs md:text-sm text-slate-400 line-clamp-2">{description}</p>
            </div>
          </div>
          {downloadTemplate && (
            <Button
              onClick={downloadTemplate}
              variant="outline"
              size="sm"
              className="border-slate-600 text-slate-300 hover:bg-slate-700 w-full sm:w-auto"
            >
              <Download className="w-4 h-4 mr-2" />
              Template
            </Button>
          )}
        </div>
        
        {/* Upload Area - Stack on mobile */}
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
            <label className="flex-1">
              <input
                type="file"
                accept={acceptTypes}
                onChange={(e) => setFile(e.target.files?.[0] || null)}
                className="hidden"
              />
              <div className={`flex items-center justify-center gap-2 p-3 md:p-4 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                file 
                  ? 'border-green-500/50 bg-green-500/10' 
                  : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50'
              }`}>
                {file ? (
                  <>
                    <FileSpreadsheet className="w-5 h-5 text-green-400 shrink-0" />
                    <span className="text-green-400 font-medium truncate text-sm">{file.name}</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-5 h-5 text-slate-400" />
                    <span className="text-slate-400 text-sm">Tap to select file</span>
                  </>
                )}
              </div>
            </label>
            <Button
              onClick={onUpload}
              disabled={!file || uploading}
              className={`${colors.btn} w-full sm:w-auto`}
            >
              {uploading ? (
                <RefreshCw className="w-4 h-4 animate-spin" />
              ) : (
                <>
                  <Upload className="w-4 h-4 mr-2 sm:mr-0 md:mr-2" />
                  <span className="sm:hidden md:inline">Upload</span>
                </>
              )}
            </Button>
          </div>
          
          {/* Result Display */}
          {result && (
            <div className={`p-3 md:p-4 rounded-lg ${result.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
              <div className="flex items-center gap-2 mb-2">
                {result.success ? (
                  <CheckCircle className="w-4 h-4 md:w-5 md:h-5 text-green-400" />
                ) : (
                  <XCircle className="w-4 h-4 md:w-5 md:h-5 text-red-400" />
                )}
                <span className={`text-sm ${result.success ? 'text-green-400' : 'text-red-400'}`}>
                  {result.success ? 'Upload Successful' : 'Upload Failed'}
                </span>
              </div>
              {result.success && result.data?.summary && (
                <div className="text-xs md:text-sm text-slate-300 space-y-1">
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
              {result.success && result.data?.employees_updated !== undefined && (
                <p className="text-xs md:text-sm text-slate-300">
                  Employees updated: <span className="text-white font-medium">{result.data.employees_updated}</span>
                </p>
              )}
              {result.error && (
                <p className="text-xs md:text-sm text-red-300">{result.error}</p>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-slate-900 p-3 md:p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-xl md:text-3xl font-bold text-white mb-1 md:mb-2">Data Uploads</h1>
          <p className="text-sm md:text-base text-slate-400">Upload your data files to calculate employee scores</p>
        </div>

        {/* Quarter Selector - Stack on mobile */}
        <div className="mb-4 md:mb-6 p-3 md:p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 text-sm">Quarter:</span>
              <Select value={year.toString()} onValueChange={(v) => setYear(parseInt(v))}>
                <SelectTrigger className="w-20 bg-slate-900 border-slate-700 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="2025">2025</SelectItem>
                  <SelectItem value="2026">2026</SelectItem>
                </SelectContent>
              </Select>
              <Select value={quarter} onValueChange={setQuarter}>
                <SelectTrigger className="w-16 bg-slate-900 border-slate-700 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="Q1">Q1</SelectItem>
                  <SelectItem value="Q2">Q2</SelectItem>
                  <SelectItem value="Q3">Q3</SelectItem>
                  <SelectItem value="Q4">Q4</SelectItem>
                </SelectContent>
              </Select>
            </div>
            
            {/* Current Data Status - Compact on mobile */}
            <div className="flex items-center gap-3 sm:gap-4 text-xs sm:text-sm sm:ml-auto">
              {loadingStatus ? (
                <RefreshCw className="w-4 h-4 animate-spin text-slate-400" />
              ) : (
                <>
                  <div className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5 md:w-4 md:h-4 text-blue-400" />
                    <span className="text-white font-medium">{dataStatus?.employees || 0}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <MessageSquare className="w-3.5 h-3.5 md:w-4 md:h-4 text-green-400" />
                    <span className="text-white font-medium">{dataStatus?.cv?.our_count || 0}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Star className="w-3.5 h-3.5 md:w-4 md:h-4 text-yellow-400" />
                    <span className="text-white font-medium">{dataStatus?.rt?.our_count || 0}</span>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Upload Order Guide - Compact on mobile */}
        <div className="mb-4 md:mb-6 p-3 md:p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl">
          <div className="flex items-start gap-2 md:gap-3">
            <CheckCircle className="w-4 h-4 md:w-5 md:h-5 text-blue-400 mt-0.5 shrink-0" />
            <div>
              <h4 className="font-medium text-blue-400 text-sm mb-1">How It Works</h4>
              <p className="text-xs md:text-sm text-slate-300 mb-2">
                Uploads update the <strong>Dashboard</strong> immediately. Create a <strong>Snapshot</strong> to capture point-in-time data for reports.
              </p>
              <ol className="text-xs md:text-sm text-slate-400 space-y-0.5 list-decimal list-inside">
                <li><strong className="text-white">POS</strong> - Employee metrics (PPA, LBW, LSC, Glass)</li>
                <li><strong className="text-white">CV/NPS</strong> - Customer Voice scores</li>
                <li><strong className="text-white">RT</strong> - Review mention bonuses</li>
              </ol>
            </div>
          </div>
        </div>

        {/* Upload Cards */}
        <div className="space-y-4 md:space-y-6">
          {/* POS Upload */}
          <UploadCard
            title="1. POS Data (SSD Engine / XLSX)"
            description="Directly updates Dashboard & Snapshots"
            icon={FileSpreadsheet}
            file={posFile}
            setFile={setPosFile}
            onUpload={handlePosUpload}
            uploading={posUploading}
            result={posResult}
            acceptTypes=".xlsx,.xls,.csv"
            colorClass="blue"
          />

          {/* CV/NPS Upload */}
          <UploadCard
            title="2. Customer Voice / NPS"
            description="Server Performance Report from Loyalty Voice"
            icon={MessageSquare}
            file={cvFile}
            setFile={setCvFile}
            onUpload={handleCvUpload}
            uploading={cvUploading}
            result={cvResult}
            acceptTypes=".xlsx,.xls,.csv"
            colorClass="green"
          />

          {/* ReviewTracker Upload */}
          <UploadCard
            title="3. ReviewTracker"
            description="Employee review mention counts (XLSX or CSV)"
            icon={Star}
            file={rtFile}
            setFile={setRtFile}
            onUpload={handleRtUpload}
            uploading={rtUploading}
            result={rtResult}
            acceptTypes=".xlsx,.csv"
            downloadTemplate={downloadRtTemplate}
            colorClass="yellow"
          />
        </div>

        {/* Post-Upload Actions */}
        <div className="mt-6 md:mt-8 p-3 md:p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
          <h3 className="font-semibold text-white text-sm md:text-base mb-3">After Uploading</h3>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 md:flex md:flex-wrap md:gap-3">
            <Button
              onClick={() => window.location.href = '/'}
              variant="default"
              size="sm"
              className="bg-emerald-600 hover:bg-emerald-700 text-xs md:text-sm"
            >
              Dashboard
            </Button>
            <Button
              onClick={() => window.location.href = '/scoring-audit'}
              variant="outline"
              size="sm"
              className="border-slate-600 text-xs md:text-sm"
            >
              Audit
            </Button>
            <Button
              onClick={() => window.location.href = '/rankings'}
              variant="outline"
              size="sm"
              className="border-slate-600 text-xs md:text-sm"
            >
              Rankings
            </Button>
            <Button
              onClick={() => window.location.href = '/employees'}
              variant="outline"
              size="sm"
              className="border-slate-600 text-xs md:text-sm"
            >
              Employees
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
