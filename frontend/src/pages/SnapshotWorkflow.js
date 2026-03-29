import { useState, useEffect, useCallback } from "react";
import { 
  Plus, Calendar, FileText, Upload, CheckCircle, XCircle, Clock, 
  RefreshCw, PlayCircle, Eye, ChevronRight, AlertCircle, Loader2,
  FileSpreadsheet, MessageSquare, Star, Trash2
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { useToast } from "../hooks/use-toast";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";

const STATUS_CONFIG = {
  draft: { label: "Draft", color: "bg-slate-500", icon: FileText },
  in_progress: { label: "In Progress", color: "bg-blue-500", icon: Upload },
  processing: { label: "Processing", color: "bg-yellow-500", icon: Loader2 },
  completed: { label: "Completed", color: "bg-green-500", icon: CheckCircle },
  failed: { label: "Failed", color: "bg-red-500", icon: XCircle },
};

export default function SnapshotWorkflow() {
  const { toast } = useToast();
  const navigate = useNavigate();
  const [snapshots, setSnapshots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [creating, setCreating] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  
  // Create form state
  const [formData, setFormData] = useState({
    name: "",
    effective_date: new Date().toISOString().split('T')[0],
    period_start: "",
    period_end: "",
    quarter: "Q1",
    year: 2026,
    notes: ""
  });

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await api.get("/v2/snapshot-workflow/snapshots");
      setSnapshots(res.data);
    } catch (error) {
      console.error("Error fetching snapshots:", error);
      toast({ 
        title: "Error", 
        description: "Failed to load snapshots",
        variant: "destructive"
      });
    }
  }, [toast]);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      await fetchSnapshots();
      setLoading(false);
    };
    load();
  }, [fetchSnapshots]);

  const handleDeleteSnapshot = async () => {
    if (!deleteTarget) return;
    
    setDeleting(true);
    try {
      await api.delete(`/v2/snapshot-workflow/snapshots/${deleteTarget.id}`);
      toast({ 
        title: "Snapshot Deleted", 
        description: `"${deleteTarget.name}" has been deleted`
      });
      await fetchSnapshots();
    } catch (error) {
      toast({ 
        title: "Delete Failed", 
        description: error.response?.data?.detail || "Cannot delete this snapshot",
        variant: "destructive"
      });
    } finally {
      setDeleting(false);
      setDeleteTarget(null);
    }
  };

  const handleCreateSnapshot = async () => {
    if (!formData.name || !formData.effective_date || !formData.period_start || !formData.period_end) {
      toast({ 
        title: "Missing Fields", 
        description: "Please fill in all required fields",
        variant: "destructive"
      });
      return;
    }

    setCreating(true);
    try {
      const res = await api.post("/v2/snapshot-workflow/snapshots", formData);
      toast({ 
        title: "Snapshot Created", 
        description: `"${formData.name}" is ready for uploads`
      });
      setShowCreateDialog(false);
      setFormData({
        name: "",
        effective_date: new Date().toISOString().split('T')[0],
        period_start: "",
        period_end: "",
        quarter: "Q1",
        year: 2026,
        notes: ""
      });
      await fetchSnapshots();
      // Navigate to the new snapshot detail page
      navigate(`/snapshot-workflow/${res.data.snapshot.id}`);
    } catch (error) {
      toast({ 
        title: "Error", 
        description: error.response?.data?.detail || "Failed to create snapshot",
        variant: "destructive"
      });
    }
    setCreating(false);
  };

  const getStatusBadge = (status) => {
    const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
    const Icon = config.icon;
    return (
      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium text-white ${config.color}`}>
        <Icon className={`w-3 h-3 ${status === 'processing' ? 'animate-spin' : ''}`} />
        {config.label}
      </span>
    );
  };

  const getUploadProgress = (progress) => {
    const items = [
      { key: "pos_report", label: "POS Report", icon: FileSpreadsheet, required: true },
      { key: "customer_voice", label: "Customer Voice", icon: MessageSquare, required: false },
      { key: "review_tracker", label: "Review Tracker", icon: Star, required: false },
    ];

    return (
      <div className="flex gap-2">
        {items.map(item => {
          const completed = progress?.[item.key];
          return (
            <div 
              key={item.key}
              className={`flex items-center gap-1 px-2 py-0.5 rounded text-xs ${
                completed 
                  ? 'bg-green-500/20 text-green-400' 
                  : item.required 
                    ? 'bg-red-500/20 text-red-400'
                    : 'bg-slate-700 text-slate-400'
              }`}
              title={`${item.label}${item.required ? ' (Required)' : ' (Optional)'}`}
            >
              <item.icon className="w-3 h-3" />
              {completed ? <CheckCircle className="w-3 h-3" /> : <Clock className="w-3 h-3" />}
            </div>
          );
        })}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center">
        <RefreshCw className="w-8 h-8 text-blue-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white">Snapshot Workflow</h1>
            <p className="text-slate-400 mt-1">Create and manage bi-weekly performance snapshots</p>
          </div>
          
          <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
            <DialogTrigger asChild>
              <Button className="bg-blue-600 hover:bg-blue-700" data-testid="create-snapshot-btn">
                <Plus className="w-4 h-4 mr-2" />
                New Snapshot
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-slate-800 border-slate-700 text-white max-w-lg">
              <DialogHeader>
                <DialogTitle className="text-xl">Create New Snapshot</DialogTitle>
                <DialogDescription className="text-slate-400">
                  Start a new bi-weekly performance snapshot. You'll upload data files in the next step.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 mt-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Snapshot Name *</Label>
                  <Input
                    id="name"
                    placeholder="e.g., Week 1-2 March 2026"
                    value={formData.name}
                    onChange={(e) => setFormData({...formData, name: e.target.value})}
                    className="bg-slate-700 border-slate-600"
                    data-testid="snapshot-name-input"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="period_start">Period Start *</Label>
                    <Input
                      id="period_start"
                      type="date"
                      value={formData.period_start}
                      onChange={(e) => setFormData({...formData, period_start: e.target.value})}
                      className="bg-slate-700 border-slate-600"
                      data-testid="period-start-input"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="period_end">Period End *</Label>
                    <Input
                      id="period_end"
                      type="date"
                      value={formData.period_end}
                      onChange={(e) => setFormData({...formData, period_end: e.target.value})}
                      className="bg-slate-700 border-slate-600"
                      data-testid="period-end-input"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="effective_date">Effective Date *</Label>
                  <Input
                    id="effective_date"
                    type="date"
                    value={formData.effective_date}
                    onChange={(e) => setFormData({...formData, effective_date: e.target.value})}
                    className="bg-slate-700 border-slate-600"
                    data-testid="effective-date-input"
                  />
                  <p className="text-xs text-slate-500">Date when this snapshot becomes the active rankings</p>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="quarter">Quarter</Label>
                    <Select
                      value={formData.quarter}
                      onValueChange={(val) => setFormData({...formData, quarter: val})}
                    >
                      <SelectTrigger className="bg-slate-700 border-slate-600">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-slate-700 border-slate-600">
                        <SelectItem value="Q1">Q1</SelectItem>
                        <SelectItem value="Q2">Q2</SelectItem>
                        <SelectItem value="Q3">Q3</SelectItem>
                        <SelectItem value="Q4">Q4</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="year">Year</Label>
                    <Input
                      id="year"
                      type="number"
                      value={formData.year}
                      onChange={(e) => setFormData({...formData, year: parseInt(e.target.value)})}
                      className="bg-slate-700 border-slate-600"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="notes">Notes (Optional)</Label>
                  <Textarea
                    id="notes"
                    placeholder="Any additional notes about this snapshot..."
                    value={formData.notes}
                    onChange={(e) => setFormData({...formData, notes: e.target.value})}
                    className="bg-slate-700 border-slate-600 h-20"
                  />
                </div>

                <Button 
                  onClick={handleCreateSnapshot} 
                  disabled={creating}
                  className="w-full bg-blue-600 hover:bg-blue-700"
                  data-testid="submit-create-snapshot"
                >
                  {creating ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Creating...
                    </>
                  ) : (
                    <>
                      <Plus className="w-4 h-4 mr-2" />
                      Create Snapshot
                    </>
                  )}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>

        {/* Current Rankings Info */}
        {snapshots.some(s => s.is_current) && (
          <Card className="bg-gradient-to-r from-green-900/30 to-emerald-900/30 border-green-500/30">
            <CardContent className="p-4">
              <div className="flex items-center gap-3">
                <CheckCircle className="w-5 h-5 text-green-400" />
                <div>
                  <p className="text-green-300 font-medium">
                    Current Rankings: {snapshots.find(s => s.is_current)?.name}
                  </p>
                  <p className="text-green-400/70 text-sm">
                    Effective {snapshots.find(s => s.is_current)?.effective_date} • {snapshots.find(s => s.is_current)?.employee_count} employees
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Snapshots List */}
        {snapshots.length === 0 ? (
          <Card className="bg-slate-800/50 border-slate-700">
            <CardContent className="p-12 text-center">
              <Calendar className="w-16 h-16 text-slate-600 mx-auto mb-4" />
              <h3 className="text-xl font-medium text-white mb-2">No Snapshots Yet</h3>
              <p className="text-slate-400 mb-6 max-w-md mx-auto">
                Create your first snapshot to start tracking bi-weekly performance data.
                Each snapshot captures employee metrics for a specific time period.
              </p>
              <Button 
                onClick={() => setShowCreateDialog(true)}
                className="bg-blue-600 hover:bg-blue-700"
              >
                <Plus className="w-4 h-4 mr-2" />
                Create First Snapshot
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {snapshots.map(snapshot => (
              <Card 
                key={snapshot.id}
                className={`bg-slate-800/50 border-slate-700 hover:border-slate-600 transition-colors cursor-pointer ${
                  snapshot.is_current ? 'ring-2 ring-green-500/50' : ''
                }`}
                onClick={() => navigate(`/snapshot-workflow/${snapshot.id}`)}
                data-testid={`snapshot-card-${snapshot.id}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-4">
                      <div className="w-12 h-12 rounded-lg bg-slate-700 flex items-center justify-center">
                        <Calendar className="w-6 h-6 text-blue-400" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-white">{snapshot.name}</h3>
                          {snapshot.is_current && (
                            <span className="text-xs bg-green-500/20 text-green-400 px-2 py-0.5 rounded">
                              Current
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-slate-400">
                          {snapshot.period_start} to {snapshot.period_end} • {snapshot.quarter} {snapshot.year}
                        </p>
                        {snapshot.employee_count > 0 && (
                          <p className="text-xs text-slate-500 mt-0.5">
                            {snapshot.employee_count} employees
                          </p>
                        )}
                      </div>
                    </div>
                    
                    <div className="flex items-center gap-4">
                      {getUploadProgress(snapshot.upload_progress)}
                      {getStatusBadge(snapshot.status)}
                      {snapshot.status !== 'completed' && (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0 text-slate-400 hover:text-red-400 hover:bg-red-900/20"
                          onClick={(e) => {
                            e.stopPropagation();
                            setDeleteTarget(snapshot);
                          }}
                          data-testid={`delete-snapshot-${snapshot.id}`}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      )}
                      <ChevronRight className="w-5 h-5 text-slate-500" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Delete Confirmation Dialog */}
        <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
          <AlertDialogContent className="bg-slate-800 border-slate-700">
            <AlertDialogHeader>
              <AlertDialogTitle className="text-white">Delete Snapshot?</AlertDialogTitle>
              <AlertDialogDescription className="text-slate-400">
                Are you sure you want to delete "{deleteTarget?.name}"? This action cannot be undone.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel className="bg-slate-700 border-slate-600 text-white hover:bg-slate-600">
                Cancel
              </AlertDialogCancel>
              <AlertDialogAction
                onClick={handleDeleteSnapshot}
                disabled={deleting}
                className="bg-red-600 hover:bg-red-700 text-white"
              >
                {deleting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Deleting...
                  </>
                ) : (
                  "Delete"
                )}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
