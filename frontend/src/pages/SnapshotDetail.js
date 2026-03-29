import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Upload, CheckCircle, XCircle, Clock, RefreshCw, 
  PlayCircle, FileSpreadsheet, MessageSquare, Star, Loader2,
  AlertTriangle, FileText, Trash2, Eye, Calendar, Users, Settings2,
  Edit2, Save, X, AlertCircle
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../components/ui/dialog";
import { useToast } from "../hooks/use-toast";
import api from "../lib/api";

const STATUS_CONFIG = {
  draft: { label: "Draft", color: "bg-slate-500", textColor: "text-slate-300" },
  in_progress: { label: "In Progress", color: "bg-blue-500", textColor: "text-blue-300" },
  processing: { label: "Processing", color: "bg-yellow-500", textColor: "text-yellow-300" },
  completed: { label: "Completed", color: "bg-green-500", textColor: "text-green-300" },
  failed: { label: "Failed", color: "bg-red-500", textColor: "text-red-300" },
};

const UPLOAD_TYPES = [
  { 
    key: "pos_report", 
    label: "POS Report", 
    description: "Sales data from Aloha POS system",
    icon: FileSpreadsheet,
    accept: ".xlsx,.xls,.pdf",
    required: true,
    step: 1,
    requiresReview: true  // Must review data before proceeding
  },
  { 
    key: "customer_voice", 
    label: "NPS Toolkit / Customer Voice", 
    description: "Server Performance Report (XLSX) or use NPS Adjustment Tool",
    icon: MessageSquare,
    accept: ".xlsx,.xls,.csv",
    required: false,
    step: 2,
    hasAdjustmentTool: true
  },
  { 
    key: "review_tracker", 
    label: "Review Tracker", 
    description: "Public review mentions",
    icon: Star,
    accept: ".csv",
    required: false,
    step: 3
  },
];

export default function SnapshotDetail() {
  const { snapshotId } = useParams();
  const navigate = useNavigate();
  const { toast } = useToast();
  
  const [snapshot, setSnapshot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(null);
  const [processing, setProcessing] = useState(false);
  
  // Upload progress state
  const [uploadProgress, setUploadProgress] = useState({ stage: '', elapsed: 0 });
  
  // POS Data Review state
  const [showReviewModal, setShowReviewModal] = useState(false);
  const [reviewData, setReviewData] = useState([]);
  const [historicalAvg, setHistoricalAvg] = useState({});
  const [editingRow, setEditingRow] = useState(null);
  const [editValues, setEditValues] = useState({});
  const [dataReviewed, setDataReviewed] = useState(false);
  const [savingReview, setSavingReview] = useState(false);

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await api.get(`/v2/snapshot-workflow/snapshots/${snapshotId}`);
      setSnapshot(res.data);
      
      // Check if POS data has been reviewed
      const posUpload = res.data.uploads?.find(u => u.upload_type === 'pos_report');
      if (posUpload?.reviewed) {
        setDataReviewed(true);
      }
    } catch (error) {
      console.error("Error fetching snapshot:", error);
      toast({ 
        title: "Error", 
        description: "Failed to load snapshot",
        variant: "destructive"
      });
    }
  }, [snapshotId, toast]);

  const fetchHistoricalAverages = async () => {
    try {
      const res = await api.get('/v2/snapshot-workflow/historical-averages');
      setHistoricalAvg(res.data.averages || {});
    } catch (error) {
      console.error("Error fetching historical averages:", error);
    }
  };

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchSnapshot();
      setLoading(false);
    };
    load();
  }, [fetchSnapshot]);

  const handleFileUpload = async (uploadType, file) => {
    if (!file) return;
    
    const isPdf = file.name.toLowerCase().endsWith('.pdf');
    setUploading(uploadType);
    setUploadProgress({ stage: 'Uploading file...', elapsed: 0 });
    
    // Start elapsed time counter
    const startTime = Date.now();
    const progressInterval = setInterval(() => {
      const elapsed = Math.round((Date.now() - startTime) / 1000);
      let stage = 'Uploading file...';
      let estimate = '';
      
      if (isPdf) {
        if (elapsed < 3) {
          stage = 'Uploading PDF...';
        } else if (elapsed < 10) {
          stage = 'Starting AI analysis...';
          estimate = '~1-2 min remaining';
        } else if (elapsed < 60) {
          stage = 'AI analyzing pages...';
          estimate = `~${Math.max(60 - elapsed, 10)}s remaining`;
        } else {
          stage = 'Still processing...';
          estimate = 'Almost done';
        }
      } else {
        if (elapsed < 3) {
          stage = 'Uploading file...';
        } else {
          stage = 'Processing data...';
          estimate = '~5s remaining';
        }
      }
      
      setUploadProgress({ stage, elapsed, estimate });
    }, 1000);
    
    try {
      if (isPdf && uploadType === 'pos_report') {
        // Handle PDF with background job polling
        const formData = new FormData();
        formData.append('file', file);
        
        // Step 1: Upload and get job ID
        const uploadResponse = await fetch(
          `${process.env.REACT_APP_BACKEND_URL}/api/v2/pos-pdf/parse`,
          { method: 'POST', body: formData }
        );
        
        if (!uploadResponse.ok) {
          throw new Error(`Upload failed: ${uploadResponse.status}`);
        }
        
        const uploadData = await uploadResponse.json();
        
        if (!uploadData.job_id) {
          throw new Error("Server didn't return a job ID");
        }
        
        // Step 2: Poll for results
        const jobId = uploadData.job_id;
        let attempts = 0;
        const maxAttempts = 180; // 3 minutes
        
        while (attempts < maxAttempts) {
          attempts++;
          await new Promise(resolve => setTimeout(resolve, 1000));
          
          try {
            const statusResponse = await fetch(
              `${process.env.REACT_APP_BACKEND_URL}/api/v2/pos-pdf/job/${jobId}`
            );
            const statusData = await statusResponse.json();
            
            if (statusData.status === 'completed') {
              clearInterval(progressInterval);
              
              if (statusData.result?.success) {
                // Now save to snapshot
                const saveRes = await api.post(
                  `/v2/snapshot-workflow/snapshots/${snapshotId}/upload/${uploadType}`,
                  { 
                    parsed_data: statusData.result,
                    filename: file.name,
                    source: 'pdf_ocr'
                  }
                );
                
                toast({ 
                  title: "Upload Successful", 
                  description: `${statusData.result.employee_count || 0} employees parsed from PDF`
                });
                
                await fetchSnapshot();
                
                // Show review modal
                if (statusData.result.employee_count > 0) {
                  const employees = statusData.result.employees || [];
                  setReviewData(employees);
                  setDataReviewed(false);
                  await fetchHistoricalAverages();
                  setShowReviewModal(true);
                }
              } else {
                throw new Error(statusData.result?.error || 'PDF parsing failed');
              }
              
              setUploading(null);
              setUploadProgress({ stage: '', elapsed: 0 });
              return;
              
            } else if (statusData.status === 'failed') {
              throw new Error(statusData.error || 'PDF parsing failed');
            }
            // Still processing, continue polling
          } catch (pollError) {
            console.error('Polling error:', pollError);
            if (pollError.message.includes('failed')) throw pollError;
          }
        }
        
        throw new Error('PDF processing timed out. Please try again.');
        
      } else {
        // Handle regular file upload (XLSX, CSV)
        const formData = new FormData();
        formData.append("file", file);
        
        const res = await api.post(
          `/v2/snapshot-workflow/snapshots/${snapshotId}/upload/${uploadType}`,
          formData,
          { headers: { "Content-Type": "multipart/form-data" } }
        );
        
        clearInterval(progressInterval);
        
        toast({ 
          title: "Upload Successful", 
          description: `${res.data.record_count || 0} records processed from ${file.name}`
        });
        
        await fetchSnapshot();
        
        // If POS upload, show review modal
        if (uploadType === 'pos_report' && res.data.record_count > 0) {
          const parsedData = res.data.upload?.parsed_data?.employees || [];
          setReviewData(parsedData);
          setDataReviewed(false);
          await fetchHistoricalAverages();
          setShowReviewModal(true);
        }
      }
    } catch (error) {
      clearInterval(progressInterval);
      console.error('Upload error:', error);
      toast({ 
        title: "Upload Failed", 
        description: error.message || error.response?.data?.detail || "Failed to upload file",
        variant: "destructive"
      });
    }
    
    setUploading(null);
    setUploadProgress({ stage: '', elapsed: 0 });
  };

  const openReviewModal = async () => {
    const posUpload = snapshot?.uploads?.find(u => u.upload_type === 'pos_report');
    if (posUpload?.parsed_data?.employees) {
      setReviewData(posUpload.parsed_data.employees);
      await fetchHistoricalAverages();
      setShowReviewModal(true);
    }
  };

  const startEditRow = (index, emp) => {
    setEditingRow(index);
    setEditValues({
      ppa: emp.ppa || 0,
      lbw_per_guest: emp.lbw_per_guest || 0,
      glassware_per_guest: emp.glassware_per_guest || 0,
      lsc_count: emp.lsc_count || 0,
      guest_count: emp.guest_count || 0,
    });
  };

  const saveRowEdit = (index) => {
    const updated = [...reviewData];
    updated[index] = { ...updated[index], ...editValues };
    setReviewData(updated);
    setEditingRow(null);
    setEditValues({});
  };

  const cancelEdit = () => {
    setEditingRow(null);
    setEditValues({});
  };

  const isValueFlagged = (field, value, avgValue) => {
    if (value === 0 || value === null || value === undefined) return true;
    if (!avgValue || avgValue === 0) return false;
    
    // Flag if more than 33% deviation from historical average
    const deviation = Math.abs(value - avgValue) / avgValue;
    return deviation > 0.33;
  };

  const confirmReviewData = async () => {
    setSavingReview(true);
    try {
      await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/confirm-pos-review`, {
        employees: reviewData
      });
      
      toast({ title: "Data Confirmed", description: "POS data has been reviewed and saved" });
      setDataReviewed(true);
      setShowReviewModal(false);
      await fetchSnapshot();
    } catch (error) {
      toast({ 
        title: "Error", 
        description: error.response?.data?.detail || "Failed to save review",
        variant: "destructive"
      });
    }
    setSavingReview(false);
  };

  const handleProcess = async () => {
    setProcessing(true);
    try {
      const res = await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/process`);
      toast({ 
        title: "Processing Complete", 
        description: `Snapshot processed with ${res.data.employee_count} employees`
      });
      await fetchSnapshot();
    } catch (error) {
      toast({ 
        title: "Processing Failed", 
        description: error.response?.data?.detail || "Failed to process snapshot",
        variant: "destructive"
      });
    }
    setProcessing(false);
  };

  const handleReprocess = async () => {
    setProcessing(true);
    try {
      const res = await api.post(`/v2/snapshot-workflow/snapshots/${snapshotId}/reprocess`);
      toast({ 
        title: "Reprocessing Complete", 
        description: `Snapshot reprocessed with ${res.data.employee_count} employees`
      });
      await fetchSnapshot();
    } catch (error) {
      toast({ 
        title: "Reprocessing Failed", 
        description: error.response?.data?.detail || "Failed to reprocess snapshot",
        variant: "destructive"
      });
    }
    setProcessing(false);
  };

  const getUploadStatus = (uploadType) => {
    const upload = snapshot?.uploads?.find(u => u.upload_type === uploadType);
    return upload;
  };

  const canProcess = () => {
    const progress = snapshot?.upload_progress || {};
    return progress.pos_report === true && snapshot?.status !== 'completed' && snapshot?.status !== 'processing';
  };

  const getOverallProgress = () => {
    const progress = snapshot?.upload_progress || {};
    const completed = Object.values(progress).filter(v => v).length;
    return (completed / 3) * 100;
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
        <div className="max-w-4xl mx-auto text-center py-20">
          <AlertTriangle className="w-16 h-16 text-yellow-500 mx-auto mb-4" />
          <h2 className="text-2xl font-bold text-white mb-2">Snapshot Not Found</h2>
          <p className="text-slate-400 mb-6">The snapshot you're looking for doesn't exist.</p>
          <Button onClick={() => navigate("/snapshot-workflow")} variant="outline">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Snapshots
          </Button>
        </div>
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[snapshot.status] || STATUS_CONFIG.draft;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <Button 
            variant="ghost" 
            size="icon"
            onClick={() => navigate("/snapshot-workflow")}
            className="text-slate-400 hover:text-white"
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold text-white">{snapshot.name}</h1>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusConfig.color} text-white`}>
                {statusConfig.label}
              </span>
              {snapshot.is_current && (
                <span className="px-3 py-1 rounded-full text-sm font-medium bg-green-500/20 text-green-400 border border-green-500/30">
                  Current Rankings
                </span>
              )}
            </div>
            <p className="text-slate-400 mt-1">
              {snapshot.period_start} to {snapshot.period_end} • {snapshot.quarter} {snapshot.year}
            </p>
          </div>
        </div>

        {/* Snapshot Info Card */}
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-6">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <p className="text-slate-400 text-sm">Effective Date</p>
                <p className="text-white font-medium flex items-center gap-2 mt-1">
                  <Calendar className="w-4 h-4 text-blue-400" />
                  {snapshot.effective_date}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-sm">Employees</p>
                <p className="text-white font-medium flex items-center gap-2 mt-1">
                  <Users className="w-4 h-4 text-blue-400" />
                  {snapshot.employee_count || 0}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-sm">Created</p>
                <p className="text-white font-medium mt-1">
                  {new Date(snapshot.created_at).toLocaleDateString()}
                </p>
              </div>
              <div>
                <p className="text-slate-400 text-sm">Completed</p>
                <p className="text-white font-medium mt-1">
                  {snapshot.completed_at 
                    ? new Date(snapshot.completed_at).toLocaleDateString()
                    : "—"
                  }
                </p>
              </div>
            </div>
            {snapshot.notes && (
              <div className="mt-4 pt-4 border-t border-slate-700">
                <p className="text-slate-400 text-sm">Notes</p>
                <p className="text-white mt-1">{snapshot.notes}</p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Active Upload Progress Bar */}
        {uploading && uploadProgress.stage && (
          <Card className="bg-blue-900/30 border-blue-500/30">
            <CardContent className="p-4">
              <div className="flex items-center gap-4">
                <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                <div className="flex-1">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-blue-300 font-medium">{uploadProgress.stage}</span>
                    <span className="text-blue-400 text-sm">
                      {uploadProgress.elapsed}s {uploadProgress.estimate && `• ${uploadProgress.estimate}`}
                    </span>
                  </div>
                  <Progress value={Math.min(uploadProgress.elapsed * 1.5, 95)} className="h-2" />
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Upload Progress */}
        <Card className="bg-slate-800/50 border-slate-700">
          <CardHeader>
            <CardTitle className="text-white flex items-center justify-between">
              <span>Upload Progress</span>
              <span className="text-sm font-normal text-slate-400">
                {Math.round(getOverallProgress())}% Complete
              </span>
            </CardTitle>
            <Progress value={getOverallProgress()} className="h-2" />
          </CardHeader>
          <CardContent className="space-y-4">
            {UPLOAD_TYPES.map((uploadType) => {
              const upload = getUploadStatus(uploadType.key);
              const isCompleted = snapshot?.upload_progress?.[uploadType.key];
              const isUploading = uploading === uploadType.key;
              const Icon = uploadType.icon;
              
              return (
                <div 
                  key={uploadType.key}
                  className={`p-4 rounded-lg border transition-colors ${
                    isCompleted 
                      ? 'bg-green-900/20 border-green-500/30'
                      : 'bg-slate-700/30 border-slate-600 hover:border-slate-500'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        isCompleted ? 'bg-green-500/20' : 'bg-slate-700'
                      }`}>
                        {isCompleted ? (
                          <CheckCircle className="w-5 h-5 text-green-400" />
                        ) : (
                          <Icon className={`w-5 h-5 ${uploadType.required ? 'text-blue-400' : 'text-slate-400'}`} />
                        )}
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium text-white">
                            Step {uploadType.step}: {uploadType.label}
                          </h4>
                          {uploadType.required && (
                            <span className="text-xs bg-red-500/20 text-red-400 px-2 py-0.5 rounded">
                              Required
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-400">{uploadType.description}</p>
                        {upload && (
                          <p className="text-xs text-slate-500 mt-1">
                            {upload.filename} • {upload.record_count || 0} records • {new Date(upload.uploaded_at).toLocaleString()}
                          </p>
                        )}
                        {/* Show review warning for POS */}
                        {uploadType.requiresReview && isCompleted && !dataReviewed && upload?.record_count > 0 && (
                          <p className="text-xs text-yellow-400 mt-1 flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            Data needs review before proceeding to Step 2
                          </p>
                        )}
                        {uploadType.requiresReview && isCompleted && dataReviewed && (
                          <p className="text-xs text-green-400 mt-1 flex items-center gap-1">
                            <CheckCircle className="w-3 h-3" />
                            Data reviewed and confirmed
                          </p>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-2">
                      {snapshot.status !== 'completed' && (
                        <>
                          <input
                            type="file"
                            id={`file-input-${uploadType.key}`}
                            accept={uploadType.accept}
                            className="hidden"
                            onChange={(e) => {
                              if (e.target.files[0]) {
                                handleFileUpload(uploadType.key, e.target.files[0]);
                              }
                              // Reset input so same file can be re-selected
                              e.target.value = '';
                            }}
                            disabled={isUploading || snapshot.status === 'processing'}
                          />
                          <Button
                            variant={isCompleted ? "outline" : "default"}
                            size="sm"
                            className={isCompleted ? "border-slate-600" : "bg-blue-600 hover:bg-blue-700"}
                            disabled={isUploading || snapshot.status === 'processing'}
                            onClick={() => document.getElementById(`file-input-${uploadType.key}`).click()}
                          >
                            {isUploading ? (
                              <>
                                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                Uploading...
                              </>
                            ) : isCompleted ? (
                              <>
                                <RefreshCw className="w-4 h-4 mr-2" />
                                Replace
                              </>
                            ) : (
                              <>
                                <Upload className="w-4 h-4 mr-2" />
                                Upload
                              </>
                            )}
                          </Button>
                          {/* Review Data button for POS */}
                          {uploadType.requiresReview && isCompleted && upload?.record_count > 0 && (
                            <Button
                              variant={dataReviewed ? "outline" : "default"}
                              size="sm"
                              className={dataReviewed ? "border-slate-600 text-slate-300" : "bg-yellow-600 hover:bg-yellow-700"}
                              onClick={openReviewModal}
                            >
                              <Eye className="w-4 h-4 mr-2" />
                              {dataReviewed ? "Re-Review" : "Review Data"}
                            </Button>
                          )}
                          {/* NPS Adjustment Tool button for Customer Voice */}
                          {uploadType.hasAdjustmentTool && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="border-slate-600 text-slate-300 hover:bg-slate-700"
                              onClick={() => navigate(`/cv-adjustment?snapshot=${snapshotId}`)}
                            >
                              <Settings2 className="w-4 h-4 mr-2" />
                              NPS Adjustment Tool
                            </Button>
                          )}
                        </>
                      )}
                      {isCompleted && (
                        <CheckCircle className="w-5 h-5 text-green-400" />
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        {/* Action Buttons */}
        <Card className="bg-slate-800/50 border-slate-700">
          <CardContent className="p-6">
            {snapshot.status === 'completed' ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CheckCircle className="w-6 h-6 text-green-400" />
                  <div>
                    <p className="text-white font-medium">Snapshot Completed</p>
                    <p className="text-slate-400 text-sm">
                      {snapshot.employee_count} employees processed
                    </p>
                  </div>
                </div>
                <div className="flex gap-3">
                  <Button
                    variant="outline"
                    onClick={() => navigate(`/leaderboard?snapshot=${snapshotId}`)}
                    className="border-slate-600"
                  >
                    <Eye className="w-4 h-4 mr-2" />
                    View Rankings
                  </Button>
                  <Button
                    variant="outline"
                    onClick={handleReprocess}
                    disabled={processing}
                    className="border-slate-600"
                  >
                    {processing ? (
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    ) : (
                      <RefreshCw className="w-4 h-4 mr-2" />
                    )}
                    Reprocess
                  </Button>
                </div>
              </div>
            ) : snapshot.status === 'processing' ? (
              <div className="flex items-center justify-center gap-3 py-4">
                <Loader2 className="w-6 h-6 text-yellow-400 animate-spin" />
                <p className="text-yellow-300 font-medium">Processing snapshot...</p>
              </div>
            ) : snapshot.status === 'failed' ? (
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <XCircle className="w-6 h-6 text-red-400" />
                  <div>
                    <p className="text-white font-medium">Processing Failed</p>
                    <p className="text-slate-400 text-sm">Check logs and try again</p>
                  </div>
                </div>
                <Button
                  onClick={handleReprocess}
                  disabled={processing}
                  className="bg-blue-600 hover:bg-blue-700"
                >
                  {processing ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4 mr-2" />
                  )}
                  Retry Processing
                </Button>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-white font-medium">Ready to Process?</p>
                  <p className="text-slate-400 text-sm">
                    {canProcess() 
                      ? "All required uploads are complete. Click Process to finalize."
                      : "Upload the required POS Report to continue."
                    }
                  </p>
                </div>
                <Button
                  onClick={handleProcess}
                  disabled={!canProcess() || processing}
                  className={canProcess() ? "bg-green-600 hover:bg-green-700" : "bg-slate-600"}
                  data-testid="process-snapshot-btn"
                >
                  {processing ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <PlayCircle className="w-4 h-4 mr-2" />
                      Process Snapshot
                    </>
                  )}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Employee Preview (if completed) */}
        {snapshot.status === 'completed' && snapshot.employees?.length > 0 && (
          <Card className="bg-slate-800/50 border-slate-700">
            <CardHeader>
              <CardTitle className="text-white">Top Performers</CardTitle>
              <CardDescription className="text-slate-400">
                Top 5 employees from this snapshot
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {snapshot.employees.slice(0, 5).map((emp, idx) => (
                  <div 
                    key={emp.id}
                    className="flex items-center justify-between p-3 rounded-lg bg-slate-700/30"
                  >
                    <div className="flex items-center gap-3">
                      <span className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold ${
                        idx === 0 ? 'bg-yellow-500/20 text-yellow-400' :
                        idx === 1 ? 'bg-slate-400/20 text-slate-300' :
                        idx === 2 ? 'bg-amber-600/20 text-amber-500' :
                        'bg-slate-600/20 text-slate-400'
                      }`}>
                        {idx + 1}
                      </span>
                      <div>
                        <p className="text-white font-medium">{emp.name}</p>
                        <p className="text-slate-400 text-xs">{emp.job_title || 'Server'}</p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-white font-semibold">{emp.total_score?.toFixed(1)}</p>
                      <p className="text-slate-400 text-xs">Total Score</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* POS Data Review Modal */}
      <Dialog open={showReviewModal} onOpenChange={setShowReviewModal}>
        <DialogContent className="bg-slate-900 border-slate-700 text-white max-w-6xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="text-xl flex items-center gap-2">
              <FileSpreadsheet className="w-5 h-5 text-blue-400" />
              Review POS Data Before Proceeding
            </DialogTitle>
            <DialogDescription className="text-slate-400">
              Review and correct any data issues. Fields highlighted in <span className="text-red-400 font-medium">red</span> have zeros or significant deviation from historical averages.
            </DialogDescription>
          </DialogHeader>
          
          <div className="flex-1 overflow-auto mt-4">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-slate-800 z-10">
                <tr className="text-slate-300 text-left">
                  <th className="px-3 py-2 font-medium">Employee</th>
                  <th className="px-3 py-2 font-medium text-right">Guests</th>
                  <th className="px-3 py-2 font-medium text-right">PPA</th>
                  <th className="px-3 py-2 font-medium text-right">LBW/Guest</th>
                  <th className="px-3 py-2 font-medium text-right">Glass/Guest</th>
                  <th className="px-3 py-2 font-medium text-right">LSC Qty</th>
                  <th className="px-3 py-2 font-medium text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700">
                {reviewData.map((emp, idx) => (
                  <tr key={idx} className="hover:bg-slate-800/50">
                    <td className="px-3 py-2 text-white font-medium">{emp.name}</td>
                    {editingRow === idx ? (
                      <>
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            value={editValues.guest_count}
                            onChange={(e) => setEditValues({...editValues, guest_count: parseFloat(e.target.value) || 0})}
                            className="w-20 h-7 text-right bg-slate-700 border-slate-600 text-white"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            step="0.01"
                            value={editValues.ppa}
                            onChange={(e) => setEditValues({...editValues, ppa: parseFloat(e.target.value) || 0})}
                            className="w-20 h-7 text-right bg-slate-700 border-slate-600 text-white"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            step="0.01"
                            value={editValues.lbw_per_guest}
                            onChange={(e) => setEditValues({...editValues, lbw_per_guest: parseFloat(e.target.value) || 0})}
                            className="w-20 h-7 text-right bg-slate-700 border-slate-600 text-white"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            step="0.01"
                            value={editValues.glassware_per_guest}
                            onChange={(e) => setEditValues({...editValues, glassware_per_guest: parseFloat(e.target.value) || 0})}
                            className="w-20 h-7 text-right bg-slate-700 border-slate-600 text-white"
                          />
                        </td>
                        <td className="px-3 py-2">
                          <Input
                            type="number"
                            step="1"
                            value={editValues.lsc_count}
                            onChange={(e) => setEditValues({...editValues, lsc_count: parseInt(e.target.value) || 0})}
                            className="w-20 h-7 text-right bg-slate-700 border-slate-600 text-white"
                          />
                        </td>
                        <td className="px-3 py-2 text-center">
                          <div className="flex justify-center gap-1">
                            <Button size="sm" variant="ghost" onClick={() => saveRowEdit(idx)} className="h-7 w-7 p-0 text-green-400 hover:bg-green-900/50">
                              <Save className="w-4 h-4" />
                            </Button>
                            <Button size="sm" variant="ghost" onClick={cancelEdit} className="h-7 w-7 p-0 text-slate-400 hover:bg-slate-700">
                              <X className="w-4 h-4" />
                            </Button>
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className={`px-3 py-2 text-right ${isValueFlagged('guest_count', emp.guest_count, historicalAvg.guest_count) ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                          {emp.guest_count || 0}
                        </td>
                        <td className={`px-3 py-2 text-right ${isValueFlagged('ppa', emp.ppa, historicalAvg.ppa) ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                          ${(emp.ppa || 0).toFixed(2)}
                        </td>
                        <td className={`px-3 py-2 text-right ${isValueFlagged('lbw_per_guest', emp.lbw_per_guest, historicalAvg.lbw_per_guest) ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                          ${(emp.lbw_per_guest || 0).toFixed(2)}
                        </td>
                        <td className={`px-3 py-2 text-right ${isValueFlagged('glassware_per_guest', emp.glassware_per_guest, historicalAvg.glassware_per_guest) ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                          ${(emp.glassware_per_guest || 0).toFixed(2)}
                        </td>
                        <td className={`px-3 py-2 text-right ${isValueFlagged('lsc_count', emp.lsc_count, historicalAvg.lsc_count) ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                          {emp.lsc_count || 0}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <Button size="sm" variant="ghost" onClick={() => startEditRow(idx, emp)} className="h-7 w-7 p-0 text-slate-400 hover:bg-slate-700 hover:text-white">
                            <Edit2 className="w-4 h-4" />
                          </Button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Summary and Actions */}
          <div className="mt-4 pt-4 border-t border-slate-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-2 text-sm">
                  <AlertCircle className="w-4 h-4 text-red-400" />
                  <span className="text-red-400 font-medium">
                    {reviewData.filter(e => 
                      isValueFlagged('ppa', e.ppa, historicalAvg.ppa) ||
                      isValueFlagged('lbw_per_guest', e.lbw_per_guest, historicalAvg.lbw_per_guest) ||
                      isValueFlagged('glassware_per_guest', e.glassware_per_guest, historicalAvg.glassware_per_guest) ||
                      isValueFlagged('lsc_count', e.lsc_count, historicalAvg.lsc_count)
                    ).length} items need attention
                  </span>
                </div>
                <div className="text-sm text-slate-400">
                  Historical Avg: PPA ${historicalAvg.ppa?.toFixed(2) || '—'}, LBW ${historicalAvg.lbw_per_guest?.toFixed(2) || '—'}, Glass ${historicalAvg.glassware_per_guest?.toFixed(2) || '—'}, LSC {historicalAvg.lsc_count?.toFixed(0) || '—'}
                </div>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setShowReviewModal(false)} className="border-slate-600 text-slate-300">
                  Cancel
                </Button>
                <Button 
                  onClick={confirmReviewData} 
                  disabled={savingReview}
                  className="bg-green-600 hover:bg-green-700"
                >
                  {savingReview ? (
                    <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Saving...</>
                  ) : (
                    <><CheckCircle className="w-4 h-4 mr-2" /> Confirm & Proceed</>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
