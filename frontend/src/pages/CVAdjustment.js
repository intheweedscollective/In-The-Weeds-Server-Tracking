import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Checkbox } from '../components/ui/checkbox';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { toast } from 'sonner';
import { 
  Upload, AlertTriangle, CheckCircle, XCircle, RefreshCw, 
  FileSpreadsheet, Filter, ThumbsUp, ThumbsDown, Minus,
  ChevronDown, ChevronUp, Info
} from 'lucide-react';

const API_URL = process.env.REACT_APP_BACKEND_URL;

export default function CVAdjustment() {
  const [feedbackFile, setFeedbackFile] = useState(null);
  const [transactionFile, setTransactionFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [session, setSession] = useState(null);
  const [feedbackItems, setFeedbackItems] = useState([]);
  const [filter, setFilter] = useState('all'); // all, detractors, passives, promoters, flagged
  const [expandedItems, setExpandedItems] = useState(new Set());
  const [sessions, setSessions] = useState([]);
  
  const quarter = 'Q1';
  const year = 2026;

  useEffect(() => {
    fetchSessions();
  }, []);

  const fetchSessions = async () => {
    try {
      const response = await fetch(`${API_URL}/api/v2/cv/adjustment/sessions?quarter=${quarter}&year=${year}`);
      if (response.ok) {
        const data = await response.json();
        setSessions(data);
      }
    } catch (error) {
      console.error('Error fetching sessions:', error);
    }
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
      const response = await fetch(
        `${API_URL}/api/v2/cv/adjustment/upload?quarter=${quarter}&year=${year}`,
        { method: 'POST', body: formData }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const data = await response.json();
      setSession(data);
      setFeedbackItems(data.feedback_items || []);
      toast.success(`Processed ${data.summary.total_feedback} feedback items`);
      fetchSessions();
    } catch (error) {
      toast.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleExclusion = async (itemId, currentlyExcluded) => {
    if (!session?.session_id) return;

    try {
      const response = await fetch(
        `${API_URL}/api/v2/cv/adjustment/session/${session.session_id}/update-item?item_id=${itemId}&excluded=${!currentlyExcluded}`,
        { method: 'POST' }
      );

      if (!response.ok) throw new Error('Failed to update');

      const data = await response.json();
      
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
      const response = await fetch(`${API_URL}/api/v2/cv/adjustment/session/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load session');
      
      const data = await response.json();
      setSession(data);
      setFeedbackItems(data.feedback_items || []);
    } catch (error) {
      toast.error(error.message);
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

  return (
    <div className="min-h-screen bg-slate-50 p-6" data-testid="cv-adjustment-page">
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">CV NPS Adjustment Tool</h1>
            <p className="text-slate-600 mt-1">
              Remove feedback that isn't the server's fault and recalculate NPS
            </p>
          </div>
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
                  onChange={(e) => setFeedbackFile(e.target.files[0])}
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
                  onChange={(e) => setTransactionFile(e.target.files[0])}
                  data-testid="transaction-file-input"
                />
                <p className="text-xs text-slate-500 mt-1">Links check numbers to additional data</p>
              </div>
            </div>
            <Button 
              onClick={handleUpload} 
              disabled={loading || !feedbackFile}
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
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {sessions.map(s => (
                  <div 
                    key={s.session_id}
                    className="flex items-center justify-between p-3 bg-slate-100 rounded-lg cursor-pointer hover:bg-slate-200"
                    onClick={() => loadSession(s.session_id)}
                  >
                    <div>
                      <p className="font-medium">{new Date(s.created_at).toLocaleString()}</p>
                      <p className="text-sm text-slate-600">{s.total_items} items | NPS: {s.original_nps?.nps_score} → {s.adjusted_nps?.nps_score}</p>
                    </div>
                    <Badge variant={s.status === 'applied' ? 'default' : 'secondary'}>
                      {s.status}
                    </Badge>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Results Section */}
        {session && (
          <>
            {/* NPS Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card className="border-2 border-slate-200">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">Original NPS</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-slate-900">
                    {session.original_nps?.nps_score?.toFixed(1)}
                  </div>
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="text-green-600">
                      <ThumbsUp className="w-4 h-4 inline mr-1" />
                      {session.original_nps?.promoters} Promoters
                    </span>
                    <span className="text-yellow-600">
                      <Minus className="w-4 h-4 inline mr-1" />
                      {session.original_nps?.passives} Passives
                    </span>
                    <span className="text-red-600">
                      <ThumbsDown className="w-4 h-4 inline mr-1" />
                      {session.original_nps?.detractors} Detractors
                    </span>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-2 border-green-200 bg-green-50">
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg text-green-800">Adjusted NPS</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="text-4xl font-bold text-green-700">
                    {session.adjusted_nps?.nps_score?.toFixed(1)}
                  </div>
                  <div className="flex gap-4 mt-2 text-sm">
                    <span className="text-green-600">
                      {session.adjusted_nps?.promoters} Promoters
                    </span>
                    <span className="text-yellow-600">
                      {session.adjusted_nps?.passives} Passives
                    </span>
                    <span className="text-red-600">
                      {session.adjusted_nps?.detractors} Detractors
                    </span>
                  </div>
                  <p className="text-sm text-green-700 mt-2">
                    {session.excluded_count?.total || 0} items excluded
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Feedback Review */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Review Feedback</CardTitle>
                  <div className="flex gap-2">
                    <Button
                      variant={filter === 'all' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilter('all')}
                    >
                      All ({feedbackItems.length})
                    </Button>
                    <Button
                      variant={filter === 'detractors' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilter('detractors')}
                    >
                      <ThumbsDown className="w-4 h-4 mr-1" />
                      Detractors
                    </Button>
                    <Button
                      variant={filter === 'passives' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilter('passives')}
                    >
                      <Minus className="w-4 h-4 mr-1" />
                      Passives
                    </Button>
                    <Button
                      variant={filter === 'flagged' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilter('flagged')}
                    >
                      <AlertTriangle className="w-4 h-4 mr-1" />
                      Auto-Flagged
                    </Button>
                    <Button
                      variant={filter === 'excluded' ? 'default' : 'outline'}
                      size="sm"
                      onClick={() => setFilter('excluded')}
                    >
                      <XCircle className="w-4 h-4 mr-1" />
                      Excluded
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  {filteredItems.map(item => (
                    <div 
                      key={item.id}
                      className={`border rounded-lg p-4 transition-all ${
                        item.excluded 
                          ? 'bg-slate-100 border-slate-300 opacity-60' 
                          : item.auto_flagged_non_server 
                            ? 'bg-amber-50 border-amber-200'
                            : 'bg-white border-slate-200'
                      }`}
                      data-testid={`feedback-item-${item.id}`}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-3 flex-1">
                          <Checkbox
                            checked={item.excluded}
                            onCheckedChange={() => handleToggleExclusion(item.id, item.excluded)}
                            data-testid={`exclude-checkbox-${item.id}`}
                          />
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-1">
                              {getCategoryIcon(item.nps_category)}
                              <Badge className={getRatingColor(item.rating)}>
                                Rating: {item.rating}
                              </Badge>
                              <span className="text-sm text-slate-600">
                                {item.customer_name} • {item.response_date}
                              </span>
                              {item.auto_flagged_non_server && (
                                <Badge variant="outline" className="bg-amber-100 text-amber-800 border-amber-300">
                                  <AlertTriangle className="w-3 h-3 mr-1" />
                                  Auto-flagged
                                </Badge>
                              )}
                              {item.excluded && (
                                <Badge variant="outline" className="bg-slate-200 text-slate-700">
                                  Excluded
                                </Badge>
                              )}
                            </div>
                            
                            {/* Comment preview or full */}
                            {item.comment && (
                              <div className="mt-2">
                                <p className={`text-sm text-slate-700 ${
                                  expandedItems.has(item.id) ? '' : 'line-clamp-2'
                                }`}>
                                  {item.comment}
                                </p>
                                {item.comment.length > 150 && (
                                  <button
                                    className="text-sm text-blue-600 hover:text-blue-800 mt-1 flex items-center"
                                    onClick={() => toggleExpand(item.id)}
                                  >
                                    {expandedItems.has(item.id) ? (
                                      <><ChevronUp className="w-4 h-4 mr-1" /> Show less</>
                                    ) : (
                                      <><ChevronDown className="w-4 h-4 mr-1" /> Show more</>
                                    )}
                                  </button>
                                )}
                              </div>
                            )}

                            {/* Auto-flag reasons */}
                            {item.auto_flagged_non_server && item.auto_flag_reasons?.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1">
                                {item.auto_flag_reasons.map((reason, idx) => (
                                  <Badge key={idx} variant="outline" className="text-xs bg-amber-50">
                                    {reason}
                                  </Badge>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}

                  {filteredItems.length === 0 && (
                    <div className="text-center py-8 text-slate-500">
                      No feedback items match the current filter
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Info Card */}
            <Card className="bg-blue-50 border-blue-200">
              <CardContent className="p-4">
                <div className="flex gap-3">
                  <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                  <div className="text-sm text-blue-800">
                    <p className="font-medium mb-1">How Exclusions Work</p>
                    <ul className="list-disc list-inside space-y-1">
                      <li>Check the box next to any feedback that isn't the server's fault</li>
                      <li>Auto-flagged items are suggestions based on keywords (food issues, environment, etc.)</li>
                      <li>Only passives and detractors can be excluded</li>
                      <li>The adjusted NPS recalculates automatically as you make changes</li>
                      <li>Formula: NPS = (Promoters - Detractors) / Total Responses × 100</li>
                    </ul>
                  </div>
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}
