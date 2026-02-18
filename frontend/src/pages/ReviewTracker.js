import { useState, useEffect, useCallback } from "react";
import { Star, Plus, Search, Filter, Trash2, Edit2, MessageSquare, TrendingUp, Award, X, Check, AlertCircle, RefreshCw, Cloud, CheckCircle } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { toast } from "sonner";
import Navigation from "../components/Navigation";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const PLATFORM_COLORS = {
  Google: "bg-blue-500",
  Yelp: "bg-red-500",
  Facebook: "bg-indigo-600",
  TripAdvisor: "bg-green-500",
  OpenTable: "bg-orange-500"
};

const PLATFORM_ICONS = {
  Google: "🔍",
  Yelp: "📍",
  Facebook: "📘",
  TripAdvisor: "🦉",
  OpenTable: "🍽️"
};

export default function ReviewTracker() {
  const [reviews, setReviews] = useState([]);
  const [stats, setStats] = useState(null);
  const [platforms, setPlatforms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [selectedYear, setSelectedYear] = useState(2026);
  const [filterPlatform, setFilterPlatform] = useState("");
  const [filterEmployee, setFilterEmployee] = useState("");
  const [syncStatus, setSyncStatus] = useState(null);
  const [syncing, setSyncing] = useState(false);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      
      // Fetch platforms
      const platformsRes = await fetch(`${API_URL}/api/v2/reviews/platforms`);
      const platformsData = await platformsRes.json();
      setPlatforms(platformsData.platforms || []);
      
      // Fetch reviews
      let reviewsUrl = `${API_URL}/api/v2/reviews?quarter=${selectedQuarter}&year=${selectedYear}`;
      if (filterPlatform) reviewsUrl += `&platform=${filterPlatform}`;
      if (filterEmployee) reviewsUrl += `&employee_name=${filterEmployee}`;
      
      const reviewsRes = await fetch(reviewsUrl);
      const reviewsData = await reviewsRes.json();
      setReviews(reviewsData.reviews || []);
      
      // Fetch stats
      const statsRes = await fetch(`${API_URL}/api/v2/reviews/stats?quarter=${selectedQuarter}&year=${selectedYear}`);
      const statsData = await statsRes.json();
      setStats(statsData);
      
      // Fetch sync status
      const syncRes = await fetch(`${API_URL}/api/v2/reviews/sync/status`);
      const syncData = await syncRes.json();
      setSyncStatus(syncData);
      
    } catch (error) {
      console.error("Error fetching review data:", error);
      toast.error("Failed to load reviews");
    } finally {
      setLoading(false);
    }
  }, [selectedQuarter, selectedYear, filterPlatform, filterEmployee]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Sync from ReviewTrackers
  const handleSync = async () => {
    setSyncing(true);
    toast.info("Syncing from ReviewTrackers... This may take a few minutes.");
    
    try {
      const res = await fetch(
        `${API_URL}/api/v2/reviews/sync?quarter=${selectedQuarter}&year=${selectedYear}`,
        { method: "POST" }
      );
      
      const data = await res.json();
      
      if (data.success) {
        toast.success(`Synced ${data.new_reviews} new reviews!`);
        fetchData(); // Refresh the data
      } else {
        toast.error(data.message || "Sync failed");
      }
    } catch (error) {
      toast.error("Sync request failed - it may still be processing in the background");
    } finally {
      setSyncing(false);
    }
  };

  // Delete review
  const handleDeleteReview = async (reviewId) => {
    if (!window.confirm("Are you sure you want to delete this review?")) return;
    
    try {
      const res = await fetch(`${API_URL}/api/v2/reviews/${reviewId}`, {
        method: "DELETE"
      });
      
      if (res.ok) {
        toast.success("Review deleted");
        fetchData();
      } else {
        toast.error("Failed to delete review");
      }
    } catch (error) {
      toast.error("Error deleting review");
    }
  };

  // Render star rating
  const renderStars = (rating) => {
    return (
      <div className="flex gap-0.5">
        {[1, 2, 3, 4, 5].map((star) => (
          <Star
            key={star}
            className={`w-4 h-4 ${star <= rating ? "text-yellow-400 fill-yellow-400" : "text-gray-300"}`}
          />
        ))}
      </div>
    );
  };

  return (
    <>
      <Navigation />
      <div className="min-h-screen bg-gray-50 p-4 md:p-8" data-testid="review-tracker-page">
        {/* Header */}
        <div className="mb-6">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1 className="text-2xl md:text-3xl font-bold text-gray-900 flex items-center gap-2">
                <MessageSquare className="w-8 h-8 text-primary" />
                Review Tracker
              </h1>
              <p className="text-gray-600 mt-1">
                Track customer reviews and employee mentions across platforms
              </p>
            </div>
            <div className="flex items-center gap-2">
              {/* ReviewTrackers Sync Button */}
              {syncStatus?.configured && (
                <Button
                  onClick={handleSync}
                  disabled={syncing}
                  variant="outline"
                  className="border-green-500 text-green-600 hover:bg-green-50"
                  data-testid="sync-reviewtrackers-btn"
                >
                  {syncing ? (
                    <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Cloud className="w-4 h-4 mr-2" />
                  )}
                  {syncing ? "Syncing..." : "Sync ReviewTrackers"}
                </Button>
              )}
              <Button
                onClick={() => setShowAddModal(true)}
                className="bg-primary hover:bg-primary/90 text-white"
                data-testid="add-review-btn"
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Manual
              </Button>
            </div>
          </div>
          
          {/* Sync Status Banner */}
          {syncStatus?.configured && (
            <div className="mt-3 flex items-center gap-2 text-sm text-green-600 bg-green-50 px-3 py-2 rounded-lg">
              <CheckCircle className="w-4 h-4" />
              <span>
                ReviewTrackers connected • {syncStatus.total_synced_reviews || 0} reviews synced
                {syncStatus.last_sync_time && (
                  <span className="text-gray-500 ml-2">
                    • Last sync: {new Date(syncStatus.last_sync_time).toLocaleString()}
                  </span>
                )}
              </span>
            </div>
          )}
        </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-xl p-4 shadow-sm border" data-testid="stat-total-reviews">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-100 rounded-lg">
                <MessageSquare className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">{stats.total_reviews}</p>
                <p className="text-xs text-gray-500">Total Reviews</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white rounded-xl p-4 shadow-sm border" data-testid="stat-mentions">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-100 rounded-lg">
                <Award className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold text-gray-900">
                  {stats.top_mentioned?.length || 0}
                </p>
                <p className="text-xs text-gray-500">Employees Mentioned</p>
              </div>
            </div>
          </div>
          
          <div className="bg-white rounded-xl p-4 shadow-sm border col-span-2" data-testid="stat-platforms">
            <p className="text-sm font-medium text-gray-700 mb-2">By Platform</p>
            <div className="flex flex-wrap gap-2">
              {platforms.map((platform) => (
                <span
                  key={platform}
                  className={`px-2 py-1 rounded-full text-xs text-white ${PLATFORM_COLORS[platform]}`}
                >
                  {PLATFORM_ICONS[platform]} {platform}: {stats.by_platform?.[platform] || 0}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Top Mentioned Employees */}
      {stats?.top_mentioned?.length > 0 && (
        <div className="bg-white rounded-xl p-4 shadow-sm border mb-6" data-testid="top-mentioned-section">
          <h2 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-primary" />
            Top Mentioned Employees
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
            {stats.top_mentioned.slice(0, 5).map((emp, idx) => (
              <div
                key={emp.name}
                className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg"
              >
                <div className={`w-8 h-8 rounded-full flex items-center justify-center text-white font-bold ${
                  idx === 0 ? "bg-yellow-500" : idx === 1 ? "bg-gray-400" : idx === 2 ? "bg-amber-600" : "bg-gray-300"
                }`}>
                  {idx + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-gray-900 truncate">{emp.name}</p>
                  <p className="text-xs text-gray-500">
                    {emp.mentions} mentions • {emp.points.toFixed(1)} pts
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="bg-white rounded-xl p-4 shadow-sm border mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <Filter className="w-4 h-4 text-gray-500" />
            <span className="text-sm font-medium text-gray-700">Filters:</span>
          </div>
          
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            className="px-3 py-1.5 border rounded-lg text-sm"
            data-testid="filter-year"
          >
            <option value={2026}>2026</option>
            <option value={2025}>2025</option>
          </select>
          
          <select
            value={selectedQuarter}
            onChange={(e) => setSelectedQuarter(e.target.value)}
            className="px-3 py-1.5 border rounded-lg text-sm"
            data-testid="filter-quarter"
          >
            <option value="Q1">Q1</option>
            <option value="Q2">Q2</option>
            <option value="Q3">Q3</option>
            <option value="Q4">Q4</option>
          </select>
          
          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="px-3 py-1.5 border rounded-lg text-sm"
            data-testid="filter-platform"
          >
            <option value="">All Platforms</option>
            {platforms.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          
          <Input
            placeholder="Filter by employee..."
            value={filterEmployee}
            onChange={(e) => setFilterEmployee(e.target.value)}
            className="w-48 text-sm"
            data-testid="filter-employee"
          />
        </div>
      </div>

      {/* Reviews List */}
      <div className="space-y-4" data-testid="reviews-list">
        {loading ? (
          <div className="text-center py-12 text-gray-500">Loading reviews...</div>
        ) : reviews.length === 0 ? (
          <div className="text-center py-12 bg-white rounded-xl border">
            <MessageSquare className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">No reviews yet</p>
            <p className="text-sm text-gray-400 mt-1">Add your first review to start tracking</p>
          </div>
        ) : (
          reviews.map((review) => (
            <div
              key={review.id}
              className="bg-white rounded-xl p-4 shadow-sm border hover:shadow-md transition-shadow"
              data-testid={`review-card-${review.id}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  {/* Platform & Date */}
                  <div className="flex items-center gap-2 mb-2">
                    <span className={`px-2 py-0.5 rounded-full text-xs text-white ${PLATFORM_COLORS[review.platform]}`}>
                      {PLATFORM_ICONS[review.platform]} {review.platform}
                    </span>
                    <span className="text-sm text-gray-500">{review.review_date}</span>
                    {renderStars(review.rating)}
                    {review.reviewer_name && (
                      <span className="text-sm text-gray-400">by {review.reviewer_name}</span>
                    )}
                  </div>
                  
                  {/* Review Text */}
                  <p className="text-gray-700 text-sm leading-relaxed mb-3">
                    "{review.review_text}"
                  </p>
                  
                  {/* Employee Mentions */}
                  {review.employee_mentions?.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {review.employee_mentions.map((mention, idx) => (
                        <span
                          key={idx}
                          className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs ${
                            mention.sentiment === "positive"
                              ? "bg-green-100 text-green-700"
                              : mention.sentiment === "negative"
                              ? "bg-red-100 text-red-700"
                              : "bg-gray-100 text-gray-700"
                          }`}
                        >
                          {mention.sentiment === "positive" && <Check className="w-3 h-3" />}
                          {mention.sentiment === "negative" && <X className="w-3 h-3" />}
                          {mention.name}
                          {mention.points > 0 && (
                            <span className="font-medium">+{mention.points}</span>
                          )}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                
                {/* Actions */}
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDeleteReview(review.id)}
                    className="text-red-500 hover:text-red-600 hover:bg-red-50"
                    data-testid={`delete-review-${review.id}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Review Modal */}
      {showAddModal && (
        <AddReviewModal
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false);
            fetchData();
          }}
          platforms={platforms}
          quarter={selectedQuarter}
          year={selectedYear}
        />
      )}
    </div>
    </>
  );
}

// Add Review Modal Component
function AddReviewModal({ onClose, onSuccess, platforms, quarter, year }) {
  const [formData, setFormData] = useState({
    platform: "Google",
    review_date: new Date().toISOString().split("T")[0],
    rating: 5,
    review_text: "",
    reviewer_name: "",
    quarter,
    year
  });
  const [detectedEmployees, setDetectedEmployees] = useState([]);
  const [detecting, setDetecting] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Detect employees in review text
  const handleDetect = async () => {
    if (!formData.review_text.trim()) {
      toast.error("Please enter review text first");
      return;
    }
    
    setDetecting(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v2/reviews/detect?review_text=${encodeURIComponent(formData.review_text)}&quarter=${quarter}&year=${year}`,
        { method: "POST" }
      );
      const data = await res.json();
      setDetectedEmployees(data.mentions || []);
      
      if (data.mentions?.length > 0) {
        toast.success(`Detected ${data.mentions.length} employee(s)`);
      } else {
        toast.info("No employee names detected");
      }
    } catch (error) {
      toast.error("Detection failed");
    } finally {
      setDetecting(false);
    }
  };

  // Submit review
  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.review_text.trim()) {
      toast.error("Please enter review text");
      return;
    }
    
    setSubmitting(true);
    try {
      const res = await fetch(`${API_URL}/api/v2/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      
      const data = await res.json();
      
      if (res.status === 409) {
        toast.error("This review appears to be a duplicate");
        return;
      }
      
      if (data.success) {
        toast.success(data.message);
        onSuccess();
      } else {
        toast.error("Failed to add review");
      }
    } catch (error) {
      toast.error("Error adding review");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" data-testid="add-review-modal">
      <div className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        <div className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-xl font-bold text-gray-900">Add Customer Review</h2>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="w-5 h-5" />
            </Button>
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Platform & Date Row */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Platform</label>
                <select
                  value={formData.platform}
                  onChange={(e) => setFormData({ ...formData, platform: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg"
                  data-testid="input-platform"
                >
                  {platforms.map((p) => (
                    <option key={p} value={p}>{PLATFORM_ICONS[p]} {p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Review Date</label>
                <Input
                  type="date"
                  value={formData.review_date}
                  onChange={(e) => setFormData({ ...formData, review_date: e.target.value })}
                  data-testid="input-date"
                />
              </div>
            </div>
            
            {/* Rating */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Rating</label>
              <div className="flex gap-1">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setFormData({ ...formData, rating: star })}
                    className="p-1 hover:scale-110 transition-transform"
                    data-testid={`rating-star-${star}`}
                  >
                    <Star
                      className={`w-8 h-8 ${
                        star <= formData.rating
                          ? "text-yellow-400 fill-yellow-400"
                          : "text-gray-300"
                      }`}
                    />
                  </button>
                ))}
              </div>
            </div>
            
            {/* Review Text */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Review Text</label>
              <textarea
                value={formData.review_text}
                onChange={(e) => setFormData({ ...formData, review_text: e.target.value })}
                placeholder="Paste the customer review here..."
                rows={5}
                className="w-full px-3 py-2 border rounded-lg resize-none"
                data-testid="input-review-text"
              />
              <div className="flex justify-end mt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleDetect}
                  disabled={detecting}
                  data-testid="detect-employees-btn"
                >
                  <Search className="w-4 h-4 mr-1" />
                  {detecting ? "Detecting..." : "Detect Employees"}
                </Button>
              </div>
            </div>
            
            {/* Detected Employees Preview */}
            {detectedEmployees.length > 0 && (
              <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                <p className="text-sm font-medium text-green-800 mb-2 flex items-center gap-1">
                  <Check className="w-4 h-4" />
                  Detected Employees:
                </p>
                <div className="flex flex-wrap gap-2">
                  {detectedEmployees.map((emp, idx) => (
                    <span
                      key={idx}
                      className={`px-2 py-1 rounded-full text-xs ${
                        emp.sentiment === "positive"
                          ? "bg-green-200 text-green-800"
                          : emp.sentiment === "negative"
                          ? "bg-red-200 text-red-800"
                          : "bg-gray-200 text-gray-800"
                      }`}
                    >
                      {emp.name} ({emp.sentiment}) +{emp.points} pts
                    </span>
                  ))}
                </div>
              </div>
            )}
            
            {/* Reviewer Name (Optional) */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Reviewer Name <span className="text-gray-400">(optional)</span>
              </label>
              <Input
                value={formData.reviewer_name}
                onChange={(e) => setFormData({ ...formData, reviewer_name: e.target.value })}
                placeholder="John D."
                data-testid="input-reviewer-name"
              />
            </div>
            
            {/* Info Box */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex gap-2">
              <AlertCircle className="w-5 h-5 text-blue-500 flex-shrink-0 mt-0.5" />
              <div className="text-sm text-blue-700">
                <p className="font-medium">How points work:</p>
                <p>Each positive employee mention = +0.2 points</p>
                <p>Every 5 mentions = 1 full point toward their ranking</p>
              </div>
            </div>
            
            {/* Actions */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button type="button" variant="outline" onClick={onClose}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={submitting || !formData.review_text.trim()}
                className="bg-primary hover:bg-primary/90 text-white"
                data-testid="submit-review-btn"
              >
                {submitting ? "Adding..." : "Add Review"}
              </Button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
