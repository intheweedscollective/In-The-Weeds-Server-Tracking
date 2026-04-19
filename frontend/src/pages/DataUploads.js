import { useState, useEffect } from "react";
import { Upload, FileSpreadsheet, Download, CheckCircle, XCircle, AlertTriangle, RefreshCw, Users, MessageSquare, Star, FileText, Eye, Import, Filter, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import api from "../lib/api";
import { getCurrentQuarter } from "../lib/quarterUtils";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;

export default function DataUploads() {
  const currentQ = getCurrentQuarter();
  const [quarter, setQuarter] = useState(currentQ.quarter);
  const [year, setYear] = useState(currentQ.year);
  
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
  
  // Scanned PDF states
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfParsing, setPdfParsing] = useState(false);
  const [pdfParsedData, setPdfParsedData] = useState(null);
  const [pdfImporting, setPdfImporting] = useState(false);
  const [showPdfPreview, setShowPdfPreview] = useState(false);
  const [pdfProgress, setPdfProgress] = useState({ stage: '', elapsed: 0 });
  const [editingEmployee, setEditingEmployee] = useState(null);
  const [editForm, setEditForm] = useState({});
  
  // Current data status
  const [dataStatus, setDataStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  
  // Snapshot processing
  const [snapshotProcessing, setSnapshotProcessing] = useState(false);

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
      
      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { success: false, detail: text || `Server error (${response.status})` };
      }
      
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
      toast.error("POS upload failed: " + error.message);
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
      
      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { success: false, detail: text || `Server error (${response.status})` };
      }
      
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
      toast.error("CV upload failed: " + error.message);
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
      // Use review-tracker/upload-feedback which scans review text for employee names
      const response = await fetch(`${BACKEND_URL}/api/v2/review-tracker/upload-feedback?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        body: formData
      });
      
      const text = await response.text();
      let data;
      try {
        data = JSON.parse(text);
      } catch {
        data = { success: false, detail: text || `Server error (${response.status})` };
      }
      
      if (response.ok && data.success) {
        setRtResult({ success: true, data });
        const summary = data.summary || {};
        toast.success(`Found ${summary.total_mentions || 0} employee mentions in ${summary.reviews_with_mentions || 0} reviews`, {
          description: `Updated ${summary.employees_updated || 0} employees. Create a Snapshot to capture this data.`
        });
        fetchDataStatus();
      } else {
        setRtResult({ success: false, error: data.detail || "Upload failed" });
        toast.error(data.detail || "RT upload failed");
      }
    } catch (error) {
      setRtResult({ success: false, error: error.message });
      toast.error("RT upload failed: " + error.message);
    }
    setRtUploading(false);
  };

  // Download RT Template
  const downloadRtTemplate = () => {
    window.open(`${BACKEND_URL}/api/v2/rt/template`, '_blank');
    toast.success("Template download started");
  };

  // Process & Save Snapshot
  const handleProcessSnapshot = async () => {
    setSnapshotProcessing(true);
    try {
      // Step 1: Find or create a snapshot for this quarter
      let snapshots = [];
      try {
        const listRes = await api.get(`/v2/snapshot-workflow/snapshots?quarter=${quarter}&year=${year}`);
        snapshots = Array.isArray(listRes.data) ? listRes.data : [];
      } catch (listErr) {
        console.warn('Could not list snapshots:', listErr);
      }
      
      let snapshotId;
      const active = snapshots.find(s => s.is_current || s.status === 'completed' || s.status === 'draft');
      
      if (active) {
        snapshotId = active.id;
      } else {
        // Create new snapshot with required fields
        const qNum = parseInt(quarter.replace('Q', ''));
        const periodStart = `${year}-${String((qNum - 1) * 3 + 1).padStart(2, '0')}-01`;
        const periodEndMonth = qNum * 3;
        const lastDay = [4,6,9,11].includes(periodEndMonth) ? '30' : periodEndMonth === 2 ? '28' : '31';
        const periodEnd = `${year}-${String(periodEndMonth).padStart(2, '0')}-${lastDay}`;
        
        const createRes = await api.post('/v2/snapshot-workflow/snapshots', {
          name: `${quarter} ${year} Snapshot`,
          effective_date: new Date().toISOString().split('T')[0],
          period_start: periodStart,
          period_end: periodEnd,
          quarter,
          year: parseInt(year),
        });
        snapshotId = createRes.data?.snapshot?.id;
      }
      
      if (!snapshotId) {
        toast.error("Could not find or create snapshot");
        setSnapshotProcessing(false);
        return;
      }
      
      // Step 2: Sync employees from dashboard to snapshot
      try {
        await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/sync-from-employees`);
      } catch (syncErr) {
        console.warn('Sync warning (non-blocking):', syncErr?.response?.data?.detail || syncErr);
      }
      
      // Step 3: Process/recalculate (try process first, fall back to reprocess)
      let processRes;
      try {
        processRes = await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/process`);
      } catch (processErr) {
        // If already completed, use reprocess
        try {
          processRes = await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/reprocess`);
        } catch (reprocessErr) {
          console.warn('Reprocess warning:', reprocessErr?.response?.data?.detail);
        }
      }
      
      toast.success(`Snapshot saved with ${processRes?.data?.employee_count || 'all'} employees`, {
        description: "Rankings and slides are now updated"
      });
      fetchDataStatus();
    } catch (error) {
      console.error('Snapshot processing error:', error);
      toast.error(error?.response?.data?.detail || "Snapshot processing failed. Please try again.");
    }
    setSnapshotProcessing(false);
  };

  // Parse scanned PDF with background job polling
  const handlePdfParse = async () => {
    if (!pdfFile) return;
    setPdfParsing(true);
    setPdfParsedData(null);
    setPdfProgress({ stage: 'Uploading PDF...', elapsed: 0 });
    
    // Start elapsed time counter
    const startTime = Date.now();
    const progressInterval = setInterval(() => {
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      const stage = elapsed < 3 
        ? 'Uploading PDF...' 
        : elapsed < 10 
          ? 'Starting AI analysis...'
          : 'AI analyzing pages (this takes 1-2 minutes)...';
      setPdfProgress({ stage, elapsed });
    }, 1000);
    
    const formData = new FormData();
    formData.append('file', pdfFile);
    formData.append('quarter', quarter);
    formData.append('year', year.toString());
    
    try {
      // Use the new robust upload endpoint that handles large files
      const uploadResponse = await fetch(`${BACKEND_URL}/api/v2/upload-jobs/direct`, {
        method: 'POST',
        body: formData,
      });
      
      if (!uploadResponse.ok) {
        const errorText = await uploadResponse.text();
        let errorMsg = `Upload failed: ${uploadResponse.status}`;
        try {
          const errorData = JSON.parse(errorText);
          errorMsg = errorData.detail || errorData.error || errorMsg;
        } catch (e) {}
        throw new Error(errorMsg);
      }
      
      const uploadData = await uploadResponse.json();
      
      if (!uploadData.job_id) {
        throw new Error("Server didn't return a job ID");
      }
      
      // Step 2: Poll for results using the new upload-jobs endpoint
      const jobId = uploadData.job_id;
      let attempts = 0;
      const maxAttempts = 180; // 3 minutes with 1s intervals (longer for large files)
      
      const pollForResult = async () => {
        while (attempts < maxAttempts) {
          attempts++;
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          try {
            const statusResponse = await fetch(`${BACKEND_URL}/api/v2/upload-jobs/${jobId}`);
            const statusData = await statusResponse.json();
            
            // Update progress stage based on server progress
            if (statusData.progress) {
              const progressPct = statusData.progress;
              let stage = 'Processing...';
              if (progressPct < 30) stage = 'Uploading PDF...';
              else if (progressPct < 60) stage = 'Starting AI analysis...';
              else if (progressPct < 90) stage = 'AI analyzing pages...';
              else stage = 'Finalizing results...';
              setPdfProgress(prev => ({ ...prev, stage }));
            }
            
            if (statusData.status === 'completed') {
              clearInterval(progressInterval);
              
              if (statusData.result?.success) {
                // Deep clone to ensure serializable data
                const cleanData = JSON.parse(JSON.stringify(statusData.result));
                setPdfParsedData(cleanData);
                setShowPdfPreview(true);
                toast.success(`Parsed ${cleanData.total_extracted || cleanData.employees?.length || 0} employees from PDF`, {
                  description: cleanData.extraction_notes || 'Processed via AI/OCR'
                });
              } else {
                toast.error(statusData.result?.error || 'PDF parsing failed');
              }
              setPdfParsing(false);
              setPdfProgress({ stage: '', elapsed: 0 });
              return;
            } else if (statusData.status === 'failed') {
              clearInterval(progressInterval);
              toast.error(statusData.error || 'PDF parsing failed');
              setPdfParsing(false);
              setPdfProgress({ stage: '', elapsed: 0 });
              return;
            }
            // Still processing, continue polling
          } catch (pollError) {
            console.error('Polling error:', pollError);
            // Continue polling on error
          }
        }
        
        // Timeout after max attempts
        clearInterval(progressInterval);
        toast.error('PDF processing timed out. Please try again.');
        setPdfParsing(false);
        setPdfProgress({ stage: '', elapsed: 0 });
      };
      
      await pollForResult();
      
    } catch (error) {
      clearInterval(progressInterval);
      console.error('PDF parse error:', error);
      toast.error(error.message || 'PDF parsing failed');
      setPdfParsing(false);
      setPdfProgress({ stage: '', elapsed: 0 });
    }
  };

  // Import parsed PDF data - uses the already parsed preview data
  const handlePdfImport = async () => {
    if (!pdfParsedData || !pdfParsedData.employees) {
      toast.error("No parsed data to import. Please preview the PDF first.");
      return;
    }
    
    setPdfImporting(true);
    setPdfProgress({ stage: 'Importing data to database...', elapsed: 0 });
    
    const startTime = Date.now();
    const progressInterval = setInterval(() => {
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      setPdfProgress({ stage: 'Updating database & recalculating scores...', elapsed });
    }, 1000);
    
    try {
      // Send the already-parsed employee data directly
      const response = await fetch(`${BACKEND_URL}/api/v2/pos-pdf/import-parsed?quarter=${quarter}&year=${year}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ employees: pdfParsedData.employees })
      });
      
      clearInterval(progressInterval);
      
      const data = await response.json();
      
      if (response.ok && data.success) {
        toast.success(`Imported ${data.total_processed} employees`, {
          description: `${data.matched} matched, ${data.created} created`
        });
        setPdfFile(null);
        setPdfParsedData(null);
        setShowPdfPreview(false);
        fetchDataStatus();
      } else {
        toast.error(data.detail || data.error || "Import failed");
      }
    } catch (error) {
      clearInterval(progressInterval);
      console.error('Import error:', error);
      toast.error("Import failed: " + error.message);
    }
    setPdfImporting(false);
    setPdfProgress({ stage: '', elapsed: 0 });
  };

  // Edit employee in preview
  const startEditEmployee = (index) => {
    const emp = pdfParsedData.employees[index];
    setEditingEmployee(index);
    setEditForm({
      guest_count: String(emp.guest_count || 0),
      net_sales: String(emp.net_sales || 0),
      ppa: String(emp.ppa || 0),
      liquor_sales: String(emp.liquor_sales || 0),
      beer_sales: String(emp.beer_sales || 0),
      wine_sales: String(emp.wine_sales || 0),
      bar_glassware_sales: String(emp.bar_glassware_sales || 0),
      loyalty_sales: String(emp.loyalty_sales || 0)
    });
  };

  const saveEditEmployee = () => {
    if (editingEmployee === null || !pdfParsedData) return;
    
    // Deep clone to avoid mutation issues
    const newData = JSON.parse(JSON.stringify(pdfParsedData));
    
    newData.employees[editingEmployee] = {
      ...newData.employees[editingEmployee],
      guest_count: parseInt(editForm.guest_count) || 0,
      net_sales: parseFloat(editForm.net_sales) || 0,
      ppa: parseFloat(editForm.ppa) || 0,
      liquor_sales: parseFloat(editForm.liquor_sales) || 0,
      beer_sales: parseFloat(editForm.beer_sales) || 0,
      wine_sales: parseFloat(editForm.wine_sales) || 0,
      bar_glassware_sales: parseFloat(editForm.bar_glassware_sales) || 0,
      loyalty_sales: parseFloat(editForm.loyalty_sales) || 0,
      lbw_total: (parseFloat(editForm.liquor_sales) || 0) + 
                 (parseFloat(editForm.beer_sales) || 0) + 
                 (parseFloat(editForm.wine_sales) || 0)
    };
    
    setPdfParsedData(newData);
    setEditingEmployee(null);
    setEditForm({});
    toast.success("Employee data updated");
  };

  const cancelEditEmployee = () => {
    setEditingEmployee(null);
    setEditForm({});
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
          {/* POS Scanned PDF Upload - PRIMARY */}
          <div className="bg-slate-800/50 rounded-xl border border-blue-500/30 overflow-hidden">
            <div className="p-4 md:p-6 border-b border-slate-700/50">
              <div className="flex items-center gap-3 mb-2">
                <div className="p-2 bg-blue-500/20 rounded-lg">
                  <FileText className="w-5 h-5 text-blue-400" />
                </div>
                <div>
                  <h3 className="font-semibold text-white text-sm md:text-base">1. POS Data (Scanned PDF)</h3>
                  <p className="text-slate-400 text-xs md:text-sm">Server Sales Report PDFs with automatic OCR error correction</p>
                </div>
              </div>
            </div>
            
            <div className="p-4 md:p-6 space-y-4">
              {/* File Select */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
                <label className="flex-1">
                  <input
                    type="file"
                    accept=".pdf"
                    onChange={(e) => {
                      setPdfFile(e.target.files?.[0] || null);
                      setPdfParsedData(null);
                      setShowPdfPreview(false);
                    }}
                    className="hidden"
                  />
                  <div className={`flex items-center justify-center gap-2 p-3 md:p-4 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                    pdfFile 
                      ? 'border-blue-500/50 bg-blue-500/10' 
                      : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50'
                  }`}>
                    {pdfFile ? (
                      <>
                        <FileText className="w-5 h-5 text-blue-400 shrink-0" />
                        <span className="text-blue-400 font-medium truncate text-sm">{pdfFile.name}</span>
                      </>
                    ) : (
                      <>
                        <Upload className="w-5 h-5 text-slate-400" />
                        <span className="text-slate-400 text-sm">Select PDF file</span>
                      </>
                    )}
                  </div>
                </label>
                <div className="flex gap-2">
                  <Button
                    onClick={handlePdfParse}
                    disabled={!pdfFile || pdfParsing}
                    className="bg-blue-600 hover:bg-blue-700"
                  >
                    {pdfParsing ? (
                      <RefreshCw className="w-4 h-4 animate-spin" />
                    ) : (
                      <>
                        <Eye className="w-4 h-4 mr-2" />
                        Preview
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* AI Processing Progress Indicator */}
              {pdfParsing && (
                <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-xl border border-blue-500/30 p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <div className="relative">
                      <div className="w-10 h-10 rounded-full border-2 border-blue-500/30 flex items-center justify-center">
                        <RefreshCw className="w-5 h-5 text-blue-400 animate-spin" />
                      </div>
                      <div className="absolute -top-1 -right-1 w-4 h-4 bg-purple-500 rounded-full flex items-center justify-center">
                        <span className="text-[10px] text-white font-bold">AI</span>
                      </div>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-blue-300 font-medium text-sm">{pdfProgress.stage}</span>
                        <span className="text-blue-400 text-xs font-mono">{pdfProgress.elapsed}s</span>
                      </div>
                      <div className="h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full transition-all duration-1000"
                          style={{ 
                            width: `${Math.min(95, (pdfProgress.elapsed / 60) * 100)}%`,
                            animation: 'pulse 2s ease-in-out infinite'
                          }}
                        />
                      </div>
                    </div>
                  </div>
                  <p className="text-xs text-slate-400 ml-13">
                    <span className="text-slate-500">⏱</span> Large PDFs typically take 30-90 seconds to process via AI
                  </p>
                </div>
              )}

              {/* Preview Table */}
              {showPdfPreview && pdfParsedData?.employees && (
                <div className="bg-slate-900/50 rounded-lg border border-slate-700/50 overflow-hidden">
                  <div className="p-3 border-b border-slate-700/50 flex items-center justify-between">
                    <span className="text-sm text-slate-300">
                      <span className="text-white font-medium">{pdfParsedData.employee_count}</span> employees found
                    </span>
                    <Button
                      onClick={handlePdfImport}
                      disabled={pdfImporting}
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-700"
                    >
                      {pdfImporting ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <>
                          <Import className="w-4 h-4 mr-2" />
                          Import All
                        </>
                      )}
                    </Button>
                  </div>
                  
                  {/* Import Progress Indicator */}
                  {pdfImporting && (
                    <div className="mt-3 bg-gradient-to-r from-emerald-900/30 to-blue-900/30 rounded-lg border border-emerald-500/30 p-3">
                      <div className="flex items-center gap-2">
                        <RefreshCw className="w-4 h-4 text-emerald-400 animate-spin" />
                        <span className="text-emerald-300 text-sm font-medium">{pdfProgress.stage}</span>
                        <span className="text-emerald-400 text-xs font-mono ml-auto">{pdfProgress.elapsed}s</span>
                      </div>
                    </div>
                  )}
                  
                  <div className="max-h-96 overflow-auto">
                    <table className="w-full text-xs">
                      <thead className="bg-slate-800/50 sticky top-0">
                        <tr className="text-slate-400">
                          <th className="text-left px-2 py-2 font-medium">Name</th>
                          <th className="text-right px-2 py-2 font-medium">Guests</th>
                          <th className="text-right px-2 py-2 font-medium">PPA</th>
                          <th className="text-right px-2 py-2 font-medium">LBW</th>
                          <th className="text-right px-2 py-2 font-medium">LSC</th>
                          <th className="text-right px-2 py-2 font-medium">Glass</th>
                          <th className="text-center px-2 py-2 font-medium">Edit</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-700/50">
                        {pdfParsedData.employees.map((emp, idx) => (
                          <tr key={emp.name || `emp-${idx}`} className={`text-slate-300 hover:bg-slate-800/30 ${editingEmployee === idx ? 'bg-blue-900/20' : ''}`}>
                            {editingEmployee === idx ? (
                              <>
                                <td className="px-2 py-1 text-white font-medium">{emp.name}</td>
                                <td className="px-1 py-1">
                                  <input 
                                    type="number" 
                                    value={editForm.guest_count}
                                    onChange={(e) => setEditForm({...editForm, guest_count: e.target.value})}
                                    className="w-16 bg-slate-700 border border-slate-600 rounded px-1 py-0.5 text-right text-white text-xs"
                                  />
                                </td>
                                <td className="px-1 py-1">
                                  <input 
                                    type="number" 
                                    step="0.01"
                                    value={editForm.ppa}
                                    onChange={(e) => setEditForm({...editForm, ppa: e.target.value})}
                                    className="w-20 bg-slate-700 border border-slate-600 rounded px-1 py-0.5 text-right text-white text-xs"
                                  />
                                </td>
                                <td className="px-1 py-1 text-right text-slate-400">
                                  ${((parseFloat(editForm.liquor_sales)||0) + (parseFloat(editForm.beer_sales)||0) + (parseFloat(editForm.wine_sales)||0)).toFixed(0)}
                                </td>
                                <td className="px-1 py-1">
                                  <input 
                                    type="number" 
                                    step="0.01"
                                    value={editForm.loyalty_sales}
                                    onChange={(e) => setEditForm({...editForm, loyalty_sales: e.target.value})}
                                    className="w-16 bg-yellow-900/50 border border-yellow-600 rounded px-1 py-0.5 text-right text-yellow-300 text-xs"
                                    placeholder="LSC $"
                                  />
                                </td>
                                <td className="px-1 py-1">
                                  <input 
                                    type="number" 
                                    step="0.01"
                                    value={editForm.bar_glassware_sales}
                                    onChange={(e) => setEditForm({...editForm, bar_glassware_sales: e.target.value})}
                                    className="w-16 bg-slate-700 border border-slate-600 rounded px-1 py-0.5 text-right text-white text-xs"
                                  />
                                </td>
                                <td className="px-1 py-1 text-center">
                                  <button onClick={saveEditEmployee} className="text-green-400 hover:text-green-300 px-1">Save</button>
                                  <button onClick={cancelEditEmployee} className="text-slate-400 hover:text-slate-300 px-1">X</button>
                                </td>
                              </>
                            ) : (
                              <>
                                <td className="px-2 py-2 text-white">{emp.name}</td>
                                <td className="px-2 py-2 text-right">{emp.guest_count?.toLocaleString()}</td>
                                <td className="px-2 py-2 text-right">${emp.ppa?.toFixed(2)}</td>
                                <td className="px-2 py-2 text-right">${emp.lbw_total?.toLocaleString(undefined, {maximumFractionDigits: 0})}</td>
                                <td className={`px-2 py-2 text-right ${emp.loyalty_sales === 0 ? 'text-red-400' : 'text-green-400'}`}>
                                  ${emp.loyalty_sales?.toLocaleString(undefined, {maximumFractionDigits: 0})}
                                </td>
                                <td className="px-2 py-2 text-right">${emp.bar_glassware_sales?.toLocaleString(undefined, {maximumFractionDigits: 0})}</td>
                                <td className="px-2 py-2 text-center">
                                  <button 
                                    onClick={() => startEditEmployee(idx)}
                                    className="text-blue-400 hover:text-blue-300 text-xs underline"
                                  >
                                    Edit
                                  </button>
                                </td>
                              </>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-xs text-slate-500 px-3 py-2 border-t border-slate-700/50">
                    <span className="text-red-400">Red</span> = $0 (click Edit to fix). Loyalty = $25 per card (e.g., 2 cards = $50)
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* CV/NPS Upload */}
          <div className="bg-slate-800/50 rounded-xl border border-slate-700/50 overflow-hidden">
            <div className="p-4 md:p-6 border-b border-slate-700/50">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-green-500/20 rounded-lg">
                    <MessageSquare className="w-5 h-5 text-green-400" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-white text-sm md:text-base">2. Customer Voice / NPS</h3>
                    <p className="text-slate-400 text-xs md:text-sm">Server Performance Report from Loyalty Voice</p>
                  </div>
                </div>
                <Button
                  onClick={() => window.location.href = '/cv-adjustment'}
                  variant="outline"
                  size="sm"
                  className="border-green-500/50 text-green-400 hover:bg-green-500/10"
                >
                  <Filter className="w-4 h-4 mr-2" />
                  NPS Adjustment Tool
                </Button>
              </div>
            </div>
            
            <div className="p-4 md:p-6 space-y-4">
              {/* Quick Upload */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2 sm:gap-3">
                <label className="flex-1">
                  <input
                    type="file"
                    accept=".xlsx,.xls,.csv"
                    onChange={(e) => setCvFile(e.target.files?.[0] || null)}
                    className="hidden"
                  />
                  <div className={`flex items-center justify-center gap-2 p-3 md:p-4 border-2 border-dashed rounded-xl cursor-pointer transition-colors ${
                    cvFile 
                      ? 'border-green-500/50 bg-green-500/10' 
                      : 'border-slate-600 hover:border-slate-500 hover:bg-slate-800/50'
                  }`}>
                    {cvFile ? (
                      <>
                        <FileSpreadsheet className="w-5 h-5 text-green-400 shrink-0" />
                        <span className="text-green-400 font-medium truncate text-sm">{cvFile.name}</span>
                      </>
                    ) : (
                      <>
                        <Upload className="w-5 h-5 text-slate-400" />
                        <span className="text-slate-400 text-sm">Quick upload (no adjustment)</span>
                      </>
                    )}
                  </div>
                </label>
                <Button
                  onClick={handleCvUpload}
                  disabled={!cvFile || cvUploading}
                  className="bg-green-600 hover:bg-green-700"
                >
                  {cvUploading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <Upload className="w-4 h-4 mr-2" />
                      Upload
                    </>
                  )}
                </Button>
              </div>
              
              {/* Result Display */}
              {cvResult && (
                <div className={`p-3 md:p-4 rounded-lg ${cvResult.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    {cvResult.success ? (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    ) : (
                      <XCircle className="w-4 h-4 text-red-400" />
                    )}
                    <span className={`text-sm ${cvResult.success ? 'text-green-400' : 'text-red-400'}`}>
                      {cvResult.success ? 'Upload Successful' : 'Upload Failed'}
                    </span>
                  </div>
                  {cvResult.success && cvResult.data?.summary && (
                    <div className="text-xs md:text-sm text-slate-300 space-y-1">
                      <p>Total responses: <span className="text-white font-medium">{cvResult.data.summary.total_responses}</span></p>
                      <p>Promoters: <span className="text-green-400 font-medium">{cvResult.data.summary.total_promoters}</span> | Detractors: <span className="text-red-400 font-medium">{cvResult.data.summary.total_detractors}</span></p>
                    </div>
                  )}
                  {cvResult.error && (
                    <p className="text-xs md:text-sm text-red-300">{cvResult.error}</p>
                  )}
                </div>
              )}
              
              {/* Info about adjustment tool */}
              <div className="p-3 bg-slate-900/50 rounded-lg border border-slate-700/50">
                <p className="text-xs text-slate-400">
                  <strong className="text-slate-300">Need to exclude non-server feedback?</strong> Use the{' '}
                  <a href="/cv-adjustment" className="text-green-400 hover:underline">NPS Adjustment Tool</a>{' '}
                  to review and filter out feedback about food quality, environment, or other non-server issues before calculating NPS scores.
                </p>
              </div>
            </div>
          </div>

          {/* ReviewTracker Upload */}
          <UploadCard
            title="3. ReviewTracker (Public Reviews)"
            description="Raw review export - AI scans for employee name mentions"
            icon={Star}
            file={rtFile}
            setFile={setRtFile}
            onUpload={handleRtUpload}
            uploading={rtUploading}
            result={rtResult}
            acceptTypes=".xlsx,.csv"
            colorClass="yellow"
          />
        </div>

        {/* Save Snapshot */}
        <div className="mt-6 md:mt-8 p-4 md:p-6 bg-gradient-to-r from-blue-900/30 to-emerald-900/30 rounded-xl border border-blue-500/30">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h3 className="font-semibold text-white text-sm md:text-base">Save & Process Snapshot</h3>
              <p className="text-xs md:text-sm text-slate-400 mt-1">
                Finalize all uploaded data into a snapshot for reports and slides
              </p>
            </div>
            <Button
              onClick={handleProcessSnapshot}
              disabled={snapshotProcessing || (dataStatus?.employees || 0) === 0}
              className="bg-blue-600 hover:bg-blue-700 w-full sm:w-auto"
              data-testid="process-snapshot-btn"
            >
              {snapshotProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <CheckCircle className="w-4 h-4 mr-2" />
                  Save Snapshot
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Post-Upload Actions */}
        <div className="mt-4 p-3 md:p-4 bg-slate-800/50 rounded-xl border border-slate-700/50">
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
