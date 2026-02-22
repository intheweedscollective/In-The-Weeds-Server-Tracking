import { useState, useEffect, useCallback } from "react";
import { Camera, Upload, Download, Trash2, Plus, Calendar, Image, RefreshCw } from "lucide-react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { useToast } from "../hooks/use-toast";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export default function Snapshots() {
  const { toast } = useToast();
  const [snapshots, setSnapshots] = useState([]);
  const [backgrounds, setBackgrounds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(null);
  const [generating, setGenerating] = useState(null);
  const [recalculating, setRecalculating] = useState(null);
  
  // New snapshot form
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newSnapshot, setNewSnapshot] = useState({
    snapshot_date: new Date().toISOString().split('T')[0],
    title: "",
    year: new Date().getFullYear(),
    quarter: "Q1"
  });
  
  // Selected background for preview
  const [selectedBackground, setSelectedBackground] = useState("midnight_blue");

  const fetchSnapshots = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/v2/snapshots`);
      setSnapshots(res.data);
    } catch (error) {
      console.error("Error fetching snapshots:", error);
    }
  }, []);

  const fetchBackgrounds = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/v2/snapshots/backgrounds`);
      setBackgrounds(res.data);
    } catch (error) {
      console.error("Error fetching backgrounds:", error);
      // Fallback backgrounds
      setBackgrounds([
        { key: "midnight_blue", name: "Midnight Blue" },
        { key: "ocean_wave", name: "Ocean Wave" },
        { key: "sunset_gradient", name: "Sunset Gradient" },
        { key: "bubba_red", name: "Bubba Gump Red" },
      ]);
    }
  }, []);

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      await Promise.all([fetchSnapshots(), fetchBackgrounds()]);
      setLoading(false);
    };
    loadData();
  }, [fetchSnapshots, fetchBackgrounds]);

  const createSnapshot = async () => {
    if (!newSnapshot.snapshot_date) {
      toast({ title: "Error", description: "Please select a date", variant: "destructive" });
      return;
    }
    
    setCreating(true);
    try {
      const res = await axios.post(`${API}/v2/snapshots`, newSnapshot);
      toast({ title: "Success", description: "Snapshot created! Now upload data." });
      setShowCreateForm(false);
      setNewSnapshot({
        snapshot_date: new Date().toISOString().split('T')[0],
        title: "",
        year: new Date().getFullYear(),
        quarter: "Q1"
      });
      await fetchSnapshots();
    } catch (error) {
      toast({ 
        title: "Error", 
        description: error.response?.data?.detail || "Failed to create snapshot",
        variant: "destructive"
      });
    }
    setCreating(false);
  };

  const uploadData = async (snapshotId, file) => {
    setUploading(snapshotId);
    const formData = new FormData();
    formData.append("file", file);
    
    try {
      const res = await axios.post(`${API}/v2/snapshots/${snapshotId}/upload`, formData);
      toast({ 
        title: "Success", 
        description: `Uploaded ${res.data.employee_count} employees. Dashboard & Rankings updated!` 
      });
      await fetchSnapshots();
    } catch (error) {
      toast({
        title: "Upload Failed",
        description: error.response?.data?.detail || "Error uploading data",
        variant: "destructive"
      });
    }
    setUploading(null);
  };

  const generateSlide = async (snapshot) => {
    setGenerating(snapshot.id);
    try {
      const response = await axios.get(
        `${API}/v2/snapshots/${snapshot.id}/slide?background=${selectedBackground}`,
        { responseType: 'blob' }
      );
      
      // Create download link with explicit PNG type
      const blob = new Blob([response.data], { type: 'image/png' });
      const url = window.URL.createObjectURL(blob);
      const filename = `snapshot_${snapshot.snapshot_date}.png`;
      
      // iOS/Safari compatible download
      if (navigator.userAgent.match(/iPhone|iPad|iPod/i)) {
        // For iOS, open in new tab (will allow saving via share sheet)
        const newTab = window.open(url, '_blank');
        if (newTab) {
          toast({ title: "Image Opened", description: "Tap and hold to save the image" });
        } else {
          // Fallback: create link anyway
          const link = document.createElement('a');
          link.href = url;
          link.setAttribute('download', filename);
          document.body.appendChild(link);
          link.click();
          link.remove();
        }
      } else {
        // Standard download for desktop browsers
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();
        link.remove();
        toast({ title: "Success", description: "Snapshot slide downloaded!" });
      }
      
      // Cleanup URL after short delay
      setTimeout(() => window.URL.revokeObjectURL(url), 1000);
    } catch (error) {
      toast({
        title: "Error",
        description: error.response?.data?.detail || "Failed to generate slide",
        variant: "destructive"
      });
    }
    setGenerating(null);
  };

  const recalculateSnapshot = async (snapshotId) => {
    setRecalculating(snapshotId);
    try {
      const res = await axios.post(`${API}/v2/snapshots/${snapshotId}/recalculate`);
      toast({ 
        title: "Success", 
        description: `Recalculated ${res.data.employee_count} employees. Dashboard & Rankings updated!` 
      });
      await fetchSnapshots();
    } catch (error) {
      toast({
        title: "Error",
        description: error.response?.data?.detail || "Failed to recalculate scores",
        variant: "destructive"
      });
    }
    setRecalculating(null);
  };

  const deleteSnapshot = async (snapshotId) => {
    if (!window.confirm("Are you sure you want to delete this snapshot?")) return;
    
    try {
      await axios.delete(`${API}/v2/snapshots/${snapshotId}`);
      toast({ title: "Deleted", description: "Snapshot removed" });
      await fetchSnapshots();
    } catch (error) {
      toast({
        title: "Error",
        description: "Failed to delete snapshot",
        variant: "destructive"
      });
    }
  };

  const formatDate = (dateStr) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleDateString('en-US', { 
        month: 'short', 
        day: 'numeric', 
        year: 'numeric' 
      });
    } catch {
      return dateStr;
    }
  };

  // Get quick date options (1st and 15th of current and next month)
  const getQuickDates = () => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    
    const dates = [];
    
    // Current month 1st and 15th
    dates.push(new Date(year, month, 1));
    dates.push(new Date(year, month, 15));
    
    // Next month 1st and 15th
    dates.push(new Date(year, month + 1, 1));
    dates.push(new Date(year, month + 1, 15));
    
    return dates.map(d => ({
      value: d.toISOString().split('T')[0],
      label: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <>
      <>
      <div className="container mx-auto py-8 px-4" data-testid="snapshots-page">
      {/* Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold flex items-center gap-3" data-testid="snapshots-title">
            <Camera className="w-8 h-8 text-primary" />
            Bi-Weekly Snapshots
          </h1>
          <p className="text-muted-foreground mt-2">
            Team performance snapshots for the 1st & 15th of each month
          </p>
        </div>
        
        <Button 
          onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-2"
          data-testid="create-snapshot-btn"
        >
          <Plus className="w-4 h-4" />
          New Snapshot
        </Button>
      </div>

      {/* Background Selector */}
      <Card className="mb-8" data-testid="background-selector">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Image className="w-5 h-5" />
            Slide Background
          </CardTitle>
          <CardDescription>Choose a background for your snapshot slides</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {backgrounds.map((bg) => (
              <button
                key={bg.key}
                onClick={() => setSelectedBackground(bg.key)}
                className={`relative overflow-hidden rounded-xl border-2 transition-all ${
                  selectedBackground === bg.key
                    ? "border-primary ring-2 ring-primary ring-offset-2"
                    : "border-muted hover:border-primary/50"
                }`}
                data-testid={`bg-option-${bg.key}`}
              >
                {/* Preview Image or Solid Color */}
                <div className="aspect-video w-full">
                  {bg.preview ? (
                    <img 
                      src={bg.preview} 
                      alt={bg.name}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full bg-[#0f172a]" />
                  )}
                </div>
                {/* Label overlay */}
                <div className={`absolute bottom-0 left-0 right-0 py-2 px-2 text-xs font-medium text-center ${
                  selectedBackground === bg.key
                    ? "bg-primary text-white"
                    : "bg-black/60 text-white"
                }`}>
                  {bg.name}
                </div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Create Snapshot Form */}
      {showCreateForm && (
        <Card className="mb-8 border-primary" data-testid="create-snapshot-form">
          <CardHeader>
            <CardTitle>Create New Snapshot</CardTitle>
            <CardDescription>Set up a new bi-weekly snapshot</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Quick Date Buttons */}
              <div className="lg:col-span-4">
                <Label className="mb-2 block">Quick Select Date</Label>
                <div className="flex flex-wrap gap-2">
                  {getQuickDates().map((d) => (
                    <Button
                      key={d.value}
                      variant={newSnapshot.snapshot_date === d.value ? "default" : "outline"}
                      size="sm"
                      onClick={() => setNewSnapshot({ ...newSnapshot, snapshot_date: d.value })}
                    >
                      {d.label}
                    </Button>
                  ))}
                </div>
              </div>
              
              <div>
                <Label htmlFor="snapshot-date">Date</Label>
                <Input
                  id="snapshot-date"
                  type="date"
                  value={newSnapshot.snapshot_date}
                  onChange={(e) => setNewSnapshot({ ...newSnapshot, snapshot_date: e.target.value })}
                />
              </div>
              
              <div>
                <Label htmlFor="snapshot-title">Title (Optional)</Label>
                <Input
                  id="snapshot-title"
                  placeholder="e.g., Mid-Month Check-in"
                  value={newSnapshot.title}
                  onChange={(e) => setNewSnapshot({ ...newSnapshot, title: e.target.value })}
                />
              </div>
              
              <div>
                <Label htmlFor="snapshot-year">Year</Label>
                <Select
                  value={String(newSnapshot.year)}
                  onValueChange={(v) => setNewSnapshot({ ...newSnapshot, year: parseInt(v) })}
                >
                  <SelectTrigger id="snapshot-year">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="2025">2025</SelectItem>
                    <SelectItem value="2026">2026</SelectItem>
                    <SelectItem value="2027">2027</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label htmlFor="snapshot-quarter">Quarter (for benchmarks)</Label>
                <Select
                  value={newSnapshot.quarter}
                  onValueChange={(v) => setNewSnapshot({ ...newSnapshot, quarter: v })}
                >
                  <SelectTrigger id="snapshot-quarter">
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
            </div>
            
            <div className="flex gap-2 pt-4">
              <Button onClick={createSnapshot} disabled={creating}>
                {creating ? "Creating..." : "Create Snapshot"}
              </Button>
              <Button variant="outline" onClick={() => setShowCreateForm(false)}>
                Cancel
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Snapshots List */}
      {snapshots.length === 0 ? (
        <Card className="text-center py-12" data-testid="no-snapshots">
          <CardContent>
            <Camera className="w-16 h-16 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-xl font-semibold mb-2">No Snapshots Yet</h3>
            <p className="text-muted-foreground mb-4">
              Create your first bi-weekly snapshot to track team performance
            </p>
            <Button onClick={() => setShowCreateForm(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Create First Snapshot
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4" data-testid="snapshots-list">
          {snapshots.map((snapshot) => (
            <Card key={snapshot.id} className="hover:shadow-md transition-shadow" data-testid={`snapshot-${snapshot.id}`}>
              <CardContent className="p-6">
                <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                  <div className="flex items-center gap-4">
                    <div className="w-14 h-14 rounded-full bg-primary/10 flex items-center justify-center">
                      <Calendar className="w-7 h-7 text-primary" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-lg">
                        {snapshot.title || `Snapshot - ${formatDate(snapshot.snapshot_date)}`}
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        {formatDate(snapshot.snapshot_date)} • {snapshot.quarter} {snapshot.year}
                      </p>
                      <p className="text-sm mt-1">
                        {snapshot.employee_count > 0 ? (
                          <span className="text-green-600 font-medium">
                            ✓ {snapshot.employee_count} employees
                          </span>
                        ) : (
                          <span className="text-yellow-600">⚠ No data uploaded</span>
                        )}
                      </p>
                    </div>
                  </div>
                  
                  <div className="flex flex-wrap gap-2">
                    {/* Upload Data */}
                    <label className="cursor-pointer">
                      <input
                        type="file"
                        accept=".csv,.xlsx,.xls"
                        className="hidden"
                        onChange={(e) => {
                          if (e.target.files?.[0]) {
                            uploadData(snapshot.id, e.target.files[0]);
                          }
                        }}
                        disabled={uploading === snapshot.id}
                      />
                      <Button
                        variant="outline"
                        className="pointer-events-none"
                        disabled={uploading === snapshot.id}
                      >
                        <Upload className="w-4 h-4 mr-2" />
                        {uploading === snapshot.id ? "Uploading..." : "Upload Data"}
                      </Button>
                    </label>
                    
                    {/* Generate Slide */}
                    <Button
                      onClick={() => generateSlide(snapshot)}
                      disabled={snapshot.employee_count === 0 || generating === snapshot.id}
                      className="bg-green-600 hover:bg-green-700"
                    >
                      <Download className="w-4 h-4 mr-2" />
                      {generating === snapshot.id ? "Generating..." : "Download Slide"}
                    </Button>
                    
                    {/* Recalculate Scores */}
                    <Button
                      variant="outline"
                      onClick={() => recalculateSnapshot(snapshot.id)}
                      disabled={snapshot.employee_count === 0 || recalculating === snapshot.id}
                      title="Recalculate all scores with latest scoring engine"
                    >
                      <RefreshCw className={`w-4 h-4 mr-2 ${recalculating === snapshot.id ? 'animate-spin' : ''}`} />
                      {recalculating === snapshot.id ? "Recalculating..." : "Recalculate"}
                    </Button>
                    
                    {/* Delete */}
                    <Button
                      variant="destructive"
                      size="icon"
                      onClick={() => deleteSnapshot(snapshot.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Info Card */}
      <Card className="mt-8 bg-blue-50 border-blue-200" data-testid="info-card">
        <CardContent className="p-6">
          <h3 className="font-semibold text-blue-900 mb-2">📊 How Snapshots Work</h3>
          <ul className="text-sm text-blue-800 space-y-1">
            <li>• <strong>Auto-Sync:</strong> Uploading here automatically updates Dashboard, Rankings, Reviews & Yodeck</li>
            <li>• <strong>Trend Tracking:</strong> Each snapshot is saved for quarter-end line graphs in PDF reviews</li>
            <li>• <strong>Grid Layout:</strong> All employees on one slide, sorted by tier (Trainers → Bartenders → A/B/C-Servers)</li>
            <li>• <strong>Color Coding:</strong> 🔵 ≥100%, 🟢 ≥80%, 🟡 70-79%, 🔴 &lt;70%</li>
            <li>• <strong>Recommended Schedule:</strong> Upload cumulative quarter data on the 1st and 15th of each month</li>
          </ul>
        </CardContent>
      </Card>
    </div>
    </>
  );
}
