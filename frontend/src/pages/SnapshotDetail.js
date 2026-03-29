import { useState, useEffect, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { 
  ArrowLeft, Upload, CheckCircle, XCircle, Clock, RefreshCw, 
  PlayCircle, FileSpreadsheet, MessageSquare, Star, Loader2,
  AlertTriangle, FileText, Trash2, Eye, Calendar, Users, Settings2
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
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
    step: 1
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

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await api.get(`/v2/snapshot-workflow/snapshots/${snapshotId}`);
      setSnapshot(res.data);
    } catch (error) {
      console.error("Error fetching snapshot:", error);
      toast({ 
        title: "Error", 
        description: "Failed to load snapshot",
        variant: "destructive"
      });
    }
  }, [snapshotId, toast]);

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
    
    setUploading(uploadType);
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await api.post(
        `/v2/snapshot-workflow/snapshots/${snapshotId}/upload/${uploadType}`,
        formData,
        { headers: { "Content-Type": "multipart/form-data" } }
      );
      
      toast({ 
        title: "Upload Successful", 
        description: `${res.data.record_count || 0} records processed from ${file.name}`
      });
      
      await fetchSnapshot();
    } catch (error) {
      toast({ 
        title: "Upload Failed", 
        description: error.response?.data?.detail || "Failed to upload file",
        variant: "destructive"
      });
    }
    setUploading(null);
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
    </div>
  );
}
