import React, { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { toast } from 'sonner';
import { 
  Upload, AlertTriangle, CheckCircle, XCircle, RefreshCw, 
  FileSpreadsheet, Filter, ThumbsUp, ThumbsDown, Minus,
  ChevronDown, ChevronUp, Info, ArrowLeft, Send
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Safe fetch helper that handles JSON parsing errors
async function safeFetch(url, options = {}) {
  const response = await fetch(url, options);
  
  let data = null;
  const contentType = response.headers.get('content-type');
  
  if (contentType && contentType.includes('application/json')) {
    try {
      data = await response.json();
    } catch (e) {
      console.error('Failed to parse JSON:', e);
      data = { error: 'Invalid server response' };
    }
  } else {
    const text = await response.text();
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = { error: text || 'Unknown error' };
    }
  }
  
  return { ok: response.ok, status: response.status, data };
}

export default function CVAdjustment() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const snapshotId = searchParams.get('snapshot');
  
  const [feedbackFile, setFeedbackFile] = useState(null);
  const [transactionFile, setTransactionFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [session, setSession] = useState(null);
  const [feedbackItems, setFeedbackItems] = useState([]);
  const [filter, setFilter] = useState('all');
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [sessions, setSessions] = useState([]);
  
  const quarter = 'Q1';
  const year = 2026;

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/cv/adjustment/sessions?quarter=${quarter}&year=${year}`
      );
      if (ok && Array.isArray(data)) {
        setSessions(data);
      }
    } catch (error) {
      console.error('Error fetching sessions:', error);
    }
  };

  const handleImportToSnapshot = async () => {
    if (!session?.session_id || !snapshotId) {
      toast.error('No session or snapshot to import to');
      return;
    }
    
    setImporting(true);
    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/snapshot-workflow/snapshots/${snapshotId}/import-cv-adjustment/${session.session_id}`,
        { method: 'POST' }
      );
      
      if (!ok) {
        throw new Error(data?.detail || 'Import failed');
      }
      
      toast.success(`Imported ${data.employees_imported} employees to snapshot`);
      navigate(`/snapshot-workflow/${snapshotId}`);
    } catch (error) {
      toast.error(error.message || 'Failed to import to snapshot');
    }
    setImporting(false);
  };

  const handleUpload = async () => {
    if (!feedbackFile) {
      toast.error('Please select a Feedback Report file');
      return;
    }

    setLoading(true);
    const formData = new FormData();
    formData.append('feedback_file', feedbackFile);
    if (transactionFile) {
      formData.append('transaction_file', transactionFile);
    }

    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/cv/adjustment/upload?quarter=${quarter}&year=${year}`,
        { method: 'POST', body: formData }
      );
      
      if (!ok) {
        throw new Error(data?.detail || data?.message || data?.error || 'Upload failed');
      }

      setSession(data);
      setFeedbackItems(data.feedback_items || []);
      toast.success(`Processed ${data.summary?.total_feedback || 0} feedback items`);
      fetchSessions();
      
      // Clear file inputs
      setFeedbackFile(null);
      setTransactionFile(null);
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(error.message || 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleExclusion = async (itemId, currentlyExcluded) => {
    if (!session?.session_id) return;

    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/cv/adjustment/session/${session.session_id}/update-item?item_id=${itemId}&excluded=${!currentlyExcluded}`,
        { method: 'POST' }
      );
      
      if (!ok) {
        throw new Error(data?.detail || 'Failed to update');
      }
      
      // Update local state
      setFeedbackItems(prev => prev.map(item => 
        item.id === itemId 
          ? { ...item, excluded: !currentlyExcluded }
          : item
      ));
      
      setSession(prev => ({
        ...prev,
        adjusted_nps: data.adjusted_nps,
        excluded_count: data.excluded_count
      }));

    } catch (error) {
      toast.error('Failed to update item');
    }
  };

  const loadSession = async (sessionId) => {
    setLoading(true);
    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/cv/adjustment/session/${sessionId}`
      );
      
      if (!ok) {
        throw new Error(data?.detail || 'Failed to load session');
      }
      
      setSession(data);
      setFeedbackItems(data.feedback_items || []);
    } catch (error) {
      toast.error(error.message || 'Failed to load session');
    } finally {
      setLoading(false);
    }
  };

  const applyAdjustments = async () => {
    if (!session?.session_id) return;
    
    setLoading(true);
    try {
      const { ok, data } = await safeFetch(
        `${API_URL}/api/v2/cv/adjustment/session/${session.session_id}/apply`,
        { method: 'POST' }
      );
      
      if (!ok) {
        throw new Error(data?.detail || 'Failed to apply adjustments');
      }
      
      toast.success('Adjustments applied! Employee scores updated.');
      setSession(prev => ({ ...prev, status: 'applied' }));
      fetchSessions();
    } catch (error) {
      toast.error(error.message || 'Failed to apply adjustments');
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (itemId) => {
    setExpandedItems(prev => {
      const newSet = new Set(prev);
      if (newSet.has(itemId)) {
        newSet.delete(itemId);
      } else {
        newSet.add(itemId);
      }
      return newSet;
    });
  };

  const filteredItems = feedbackItems.filter(item => {
    if (filter === 'all') return true;
    if (filter === 'detractors') return item.nps_category === 'detractor';
    if (filter === 'passives') return item.nps_category === 'passive';
    if (filter === 'promoters') return item.nps_category === 'promoter';
    if (filter === 'flagged') return item.auto_flagged_non_server;
    if (filter === 'excluded') return item.excluded;
    return true;
  });

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'promoter': return <ThumbsUp className="w-4 h-4 text-green-500" />;
      case 'passive': return <Minus className="w-4 h-4 text-yellow-500" />;
      case 'detractor': return <ThumbsDown className="w-4 h-4 text-red-500" />;
      default: return null;
    }
  };

  const getRatingColor = (rating) => {
    if (rating >= 9) return 'bg-green-100 text-green-800 border-green-300';
    if (rating >= 7) return 'bg-yellow-100 text-yellow-800 border-yellow-300';
    return 'bg-red-100 text-red-800 border-red-300';
  };

  // Calculate current NPS stats
  const calculateStats = () => {
    if (!feedbackItems || feedbackItems.length === 0) {
      return { promoters: 0, passives: 0, detractors: 0, total: 0, nps: '0.0', excluded: 0 };
    }
    const included = feedbackItems.filter(item => !item.excluded);
    const promoters = included.filter(i => i.nps_category === 'promoter').length;
    const passives = included.filter(i => i.nps_category === 'passive').length;
    const detractors = included.filter(i => i.nps_category === 'detractor').length;
    const total = promoters + passives + detractors;
    const nps = total > 0 ? ((promoters - detractors) / total * 100).toFixed(1) : '0.0';
    return { promoters, passives, detractors, total, nps, excluded: feedbackItems.length - included.length };
  };

  const stats = session ? calculateStats() : { promoters: 0, passives: 0, detractors: 0, total: 0, nps: '0.0', excluded: 0 };

  return (
    <div className="min-h-screen bg-slate-50 p-4 md:p-6" data-testid="cv-adjustment-page">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-4">
            {snapshotId && (
              <Button 
                variant="ghost" 
                size="icon"
                onClick={() => navigate(`/snapshot-workflow/${snapshotId}`)}
                className="text-slate-600 hover:text-slate-900"
              >
                <ArrowLeft className="w-5 h-5" />
              </Button>
            )}
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-slate-900">CV NPS Adjustment Tool</h1>
              <p className="text-slate-600 mt-1 text-sm md:text-base">
                Remove feedback that isn't the server's fault and recalculate NPS
              </p>
              {snapshotId && (
                <p className="text-blue-600 text-sm mt-1">
                  Linked to Snapshot • Adjusted data will be imported when ready
                </p>
              )}
            </div>
          </div>
          {session && snapshotId && (
            <Button
              onClick={handleImportToSnapshot}
              disabled={importing}
              className="bg-green-600 hover:bg-green-700"
            >
              {importing ? (
                <>
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  Importing...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 mr-2" />
                  Import to Snapshot
                </>
              )}
            </Button>
          )}
        </div>

        {/* Upload Section */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="w-5 h-5" />
              Upload Reports
            </CardTitle>
            <CardDescription>
              Upload your Feedback Report and optionally the Transaction Report to match feedback to servers
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Feedback Report (Required)
                </label>
                <Input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={(e) => setFeedbackFile(e.target.files?.[0] || null)}
                  data-testid="feedback-file-input"
                />
                <p className="text-xs text-slate-500 mt-1">Contains ratings, comments, and customer info</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-2">
                  Transaction Report (Optional)
                </label>
                <Input
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={(e) => setTransactionFile(e.target.files?.[0] || null)}
                  data-testid="transaction-file-input"
                />
                <p className="text-xs text-slate-500 mt-1">Links check numbers to additional data</p>
              </div>
            </div>
            <Button 
              onClick={handleUpload} 
              disabled={loading || !feedbackFile}
              className="bg-red-500 hover:bg-red-600 text-white"
              data-testid="upload-btn"
            >
              {loading ? (
                <><RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Processing...</>
              ) : (
                <><FileSpreadsheet className="w-4 h-4 mr-2" /> Process Reports</>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Previous Sessions */}
        {sessions.length > 0 && !session && (
          <Card>
            <CardHeader>
              <CardTitle>Previous Sessions</CardTitle>
              <CardDescription>Resume a previous adjustment session</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {sessions.map((s) => (
                  <div 
                    key={s.session_id} 
                    className="flex items-center justify-between p-3 bg-slate-100 rounded-lg hover:bg-slate-200 cursor-pointer transition-colors"
                    onClick={() => loadSession(s.session_id)}
                  >
                    <div>
                      <div className="font-medium">{new Date(s.created_at).toLocaleDateString()}</div>
                      <div className="text-sm text-slate-500">
                        {s.total_items} items • Status: {s.status}
                      </div>
                    </div>
                    <Badge variant={s.status === 'applied' ? 'default' : 'outline'}>
                      {s.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Active Session */}
        {session && (
          <>
            {/* NPS Summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card className="bg-white">
                <CardContent className="pt-6">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-slate-900">
                      {typeof session.original_nps === 'number' ? session.original_nps.toFixed(1) : '0.0'}
                    </div>
                    <div className="text-sm text-slate-500">Original NPS</div>
                    <div className="text-xs text-slate-400 mt-1">
                      {session.summary?.promoter_count ?? 0} Promoters, {session.summary?.passive_count ?? 0} Passives, {session.summary?.detractor_count ?? 0} Detractors
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              <Card className="bg-green-50 border-green-200">
                <CardContent className="pt-6">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-green-700">{stats.nps}</div>
                    <div className="text-sm text-green-600">Adjusted NPS</div>
                    <div className="text-xs text-green-500 mt-1">
                      {stats.promoters} Promoters, {stats.passives} Passives, {stats.detractors} Detractors, {stats.excluded} excluded
                    </div>
                  </div>
                </CardContent>
              </Card>
              
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-slate-900">{feedbackItems.length}</div>
                    <div className="text-sm text-slate-500">Total Items</div>
                  </div>
                </CardContent>
              </Card>
              
              <Card>
                <CardContent className="pt-6">
                  <div className="text-center">
                    <div className="text-3xl font-bold text-orange-600">{stats.excluded}</div>
                    <div className="text-sm text-slate-500">Excluded</div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Filter & Actions */}
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div className="flex flex-wrap gap-2">
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'all' 
                      ? 'bg-red-500 text-white' 
                      : 'bg-slate-200 text-slate-700 hover:bg-slate-300'
                  }`}
                  onClick={() => setFilter('all')}
                >
                  All ({feedbackItems.length})
                </button>
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'detractors' 
                      ? 'bg-red-600 text-white' 
                      : 'bg-red-100 text-red-800 hover:bg-red-200'
                  }`}
                  onClick={() => setFilter('detractors')}
                >
                  Detractors ({feedbackItems.filter(i => i.nps_category === 'detractor').length})
                </button>
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'passives' 
                      ? 'bg-yellow-500 text-white' 
                      : 'bg-yellow-100 text-yellow-800 hover:bg-yellow-200'
                  }`}
                  onClick={() => setFilter('passives')}
                >
                  Passives ({feedbackItems.filter(i => i.nps_category === 'passive').length})
                </button>
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'promoters' 
                      ? 'bg-green-600 text-white' 
                      : 'bg-green-100 text-green-800 hover:bg-green-200'
                  }`}
                  onClick={() => setFilter('promoters')}
                >
                  Promoters ({feedbackItems.filter(i => i.nps_category === 'promoter').length})
                </button>
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'flagged' 
                      ? 'bg-orange-500 text-white' 
                      : 'bg-orange-100 text-orange-800 hover:bg-orange-200'
                  }`}
                  onClick={() => setFilter('flagged')}
                >
                  Auto-flagged ({feedbackItems.filter(i => i.auto_flagged_non_server).length})
                </button>
                <button 
                  className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    filter === 'excluded' 
                      ? 'bg-slate-700 text-white' 
                      : 'bg-slate-200 text-slate-700 hover:bg-slate-300'
                  }`}
                  onClick={() => setFilter('excluded')}
                >
                  Excluded ({stats.excluded})
                </button>
              </div>
              
              {session.status !== 'applied' && (
                <Button 
                  onClick={applyAdjustments}
                  disabled={loading}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  {loading ? (
                    <><RefreshCw className="w-4 h-4 mr-2 animate-spin" /> Applying...</>
                  ) : (
                    <><CheckCircle className="w-4 h-4 mr-2" /> Apply Adjustments</>
                  )}
                </Button>
              )}
            </div>

            {/* Feedback Items */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Filter className="w-5 h-5" />
                  Review Feedback ({filteredItems.length} items)
                </CardTitle>
                <CardDescription>
                  Check/uncheck items to exclude them from NPS calculation
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {filteredItems.map((item) => (
                    <div 
                      key={item.id}
                      className={`p-4 rounded-lg border transition-all ${
                        item.excluded 
                          ? 'bg-slate-100 border-slate-300 opacity-60' 
                          : item.auto_flagged_non_server
                            ? 'bg-yellow-50 border-yellow-300'
                            : 'bg-white border-slate-200'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <Checkbox
                          checked={!item.excluded}
                          onCheckedChange={() => handleToggleExclusion(item.id, item.excluded)}
                          className="mt-1"
                        />
                        
                        <div className="flex-1 min-w-0">
                          <div className="flex flex-wrap items-center gap-2 mb-2">
                            {getCategoryIcon(item.nps_category)}
                            <Badge className={getRatingColor(item.rating)}>
                              Rating: {item.rating}
                            </Badge>
                            {item.customer_name && (
                              <span className="text-sm font-medium text-slate-700">{item.customer_name}</span>
                            )}
                            {item.auto_flagged_non_server && (
                              <Badge variant="outline" className="bg-yellow-100 text-yellow-800 border-yellow-300">
                                <AlertTriangle className="w-3 h-3 mr-1" />
                                Auto-flagged
                              </Badge>
                            )}
                            {item.excluded && (
                              <Badge className="bg-slate-600 text-white border-slate-600">
                                Excluded
                              </Badge>
                            )}
                          </div>
                          
                          {item.comment && (
                            <p className={`text-sm ${item.excluded ? 'text-slate-400 line-through' : 'text-slate-600'}`}>
                              "{item.comment}"
                            </p>
                          )}
                          
                          {item.flag_reason && (
                            <div className="mt-2 text-xs text-yellow-700 bg-yellow-100 px-2 py-1 rounded inline-block">
                              <Info className="w-3 h-3 inline mr-1" />
                              {item.flag_reason}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                  
                  {filteredItems.length === 0 && (
                    <div className="text-center py-8 text-slate-500">
                      No items match the current filter
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Back Button */}
            <Button 
              variant="outline" 
              onClick={() => {
                setSession(null);
                setFeedbackItems([]);
              }}
            >
              Back to Upload
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
