import { useState, useEffect, useCallback } from "react";
import { Monitor, Download, Image, Calendar, ChevronRight, FileImage } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Tier colors matching the slides
const TIER_COLORS = {
  "Trainer": "bg-purple-600",
  "Bartender": "bg-blue-600",
  "A-Server": "bg-green-600",
  "B-Server": "bg-yellow-600",
  "C-Server": "bg-red-600",
};

export default function YodeckSlides() {
  const [slideManifest, setSlideManifest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState({});
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");

  const fetchSlideManifest = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        `${API}/v2/yodeck/${selectedYear}/${selectedQuarter}/all`
      );
      setSlideManifest(response.data);
    } catch (error) {
      console.error("Error fetching slide manifest:", error);
      if (error.response?.status === 404) {
        toast.error(`No data for ${selectedQuarter} ${selectedYear}`);
        setSlideManifest(null);
      } else {
        toast.error("Error loading slides");
      }
    } finally {
      setLoading(false);
    }
  }, [selectedYear, selectedQuarter]);

  useEffect(() => {
    fetchSlideManifest();
  }, [fetchSlideManifest]);

  const downloadSlide = async (slideId, endpoint, page = 1) => {
    const key = `${slideId}-${page}`;
    setDownloading(prev => ({ ...prev, [key]: true }));
    
    try {
      const url = page > 1 ? `${API}${endpoint}?page=${page}` : `${API}${endpoint}`;
      const response = await axios.get(url, { responseType: 'blob' });
      
      // Create download link
      const blob = new Blob([response.data], { type: 'image/png' });
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = downloadUrl;
      link.setAttribute('download', `${slideId}_${selectedQuarter}_${selectedYear}${page > 1 ? `_p${page}` : ''}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      
      toast.success("Slide downloaded!");
    } catch (error) {
      console.error("Error downloading slide:", error);
      toast.error("Failed to download slide");
    } finally {
      setDownloading(prev => ({ ...prev, [key]: false }));
    }
  };

  const downloadAllSlides = async () => {
    if (!slideManifest) return;
    
    toast.info("Downloading all slides...");
    
    for (const slide of slideManifest.slides) {
      for (let page = 1; page <= slide.pages; page++) {
        await downloadSlide(slide.id, slide.endpoint, page);
        // Small delay to prevent overwhelming the server
        await new Promise(resolve => setTimeout(resolve, 500));
      }
    }
    
    toast.success("All slides downloaded!");
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-background">
        <Navigation />
        <div className="flex items-center justify-center h-96">
          <div className="loading-spinner"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background relative overflow-hidden">
      <div className="splash-red" style={{ top: '10%', right: '5%' }} />
      <div className="splash-blue" style={{ bottom: '15%', left: '3%', opacity: 0.5 }} />
      
      <Navigation />
      
      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Monitor className="w-8 h-8 text-secondary" />
              <h1 className="text-3xl font-serif font-black text-foreground" data-testid="page-title">
                Yodeck Slides
              </h1>
            </div>
            <p className="text-gray-500" data-testid="page-subtitle">
              16:9 digital signage slides for TV displays
            </p>
          </div>
          
          {slideManifest && (
            <Button
              onClick={downloadAllSlides}
              className="bg-primary hover:bg-primary/90 text-white flex items-center gap-2"
              data-testid="download-all-btn"
            >
              <Download className="w-4 h-4" />
              Download All Slides
            </Button>
          )}
        </div>

        {/* Quarter Selection */}
        <div className="bubba-card mb-8" data-testid="quarter-selection">
          <div className="tape" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
          <div className="p-6 pt-8">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
                <Calendar className="w-5 h-5 text-secondary" />
              </div>
              <h2 className="text-lg font-serif font-bold text-foreground">Select Quarter</h2>
            </div>
            
            <div className="flex gap-4">
              <select 
                value={selectedYear}
                onChange={(e) => setSelectedYear(parseInt(e.target.value))}
                className="h-10 px-4 border-2 border-gray-200 rounded-lg focus:border-secondary"
                data-testid="year-select"
              >
                <option value={2024}>2024</option>
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
                <option value={2027}>2027</option>
              </select>
              <select
                value={selectedQuarter}
                onChange={(e) => setSelectedQuarter(e.target.value)}
                className="h-10 px-4 border-2 border-gray-200 rounded-lg focus:border-secondary"
                data-testid="quarter-select"
              >
                <option value="Q1">Q1</option>
                <option value="Q2">Q2</option>
                <option value="Q3">Q3</option>
                <option value="Q4">Q4</option>
              </select>
            </div>
          </div>
        </div>

        {/* Slides Grid */}
        {!slideManifest ? (
          <div className="bubba-card p-12 text-center" data-testid="no-data">
            <Monitor className="w-16 h-16 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-serif font-bold mb-2">No slides available</h3>
            <p className="text-gray-500">
              No data for {selectedQuarter} {selectedYear}. Upload employee data on the Dashboard first.
            </p>
          </div>
        ) : (
          <>
            {/* Summary */}
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-8">
              <div className="bubba-card p-4 text-center">
                <div className="text-2xl font-serif font-black text-primary">{slideManifest.total_employees}</div>
                <div className="text-xs text-gray-500 uppercase">Total Employees</div>
              </div>
              {Object.entries(slideManifest.tier_counts).map(([tier, count]) => (
                <div key={tier} className="bubba-card p-4 text-center">
                  <div className={`text-2xl font-serif font-black ${tier === "A-Server" ? "text-green-600" : tier === "B-Server" ? "text-yellow-600" : tier === "C-Server" ? "text-red-600" : tier === "Trainer" ? "text-purple-600" : "text-blue-600"}`}>
                    {count}
                  </div>
                  <div className="text-xs text-gray-500 uppercase">{tier}s</div>
                </div>
              ))}
            </div>

            {/* Slide Cards */}
            <div className="space-y-4" data-testid="slides-list">
              <h2 className="text-xl font-serif font-bold text-foreground mb-4">Available Slides</h2>
              
              {slideManifest.slides.map((slide) => (
                <div key={slide.id} className="bubba-card" data-testid={`slide-card-${slide.id}`}>
                  <div className="p-5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-4">
                        <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                          slide.id === "top10" ? "bg-gradient-to-br from-yellow-400 to-orange-500" :
                          slide.id === "trainers" ? "bg-purple-600" :
                          slide.id === "bartenders" ? "bg-blue-600" :
                          slide.id === "a-servers" ? "bg-green-600" :
                          slide.id === "b-servers" ? "bg-yellow-600" :
                          "bg-red-600"
                        }`}>
                          <FileImage className="w-6 h-6 text-white" />
                        </div>
                        <div>
                          <h3 className="text-lg font-serif font-bold text-foreground">
                            {slide.name}
                          </h3>
                          <p className="text-sm text-gray-500">
                            {slide.id === "top10" ? "Top performers leaderboard" : 
                             `${slide.employee_count} employees • ${slide.pages} slide${slide.pages > 1 ? 's' : ''}`}
                          </p>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2">
                        {slide.pages === 1 ? (
                          <Button
                            onClick={() => downloadSlide(slide.id, slide.endpoint)}
                            disabled={downloading[`${slide.id}-1`]}
                            variant="outline"
                            className="flex items-center gap-2"
                            data-testid={`download-${slide.id}`}
                          >
                            {downloading[`${slide.id}-1`] ? (
                              <div className="animate-spin h-4 w-4 border-2 border-current border-t-transparent rounded-full" />
                            ) : (
                              <Download className="w-4 h-4" />
                            )}
                            Download PNG
                          </Button>
                        ) : (
                          <div className="flex items-center gap-1">
                            {Array.from({ length: slide.pages }, (_, i) => i + 1).map((page) => (
                              <Button
                                key={page}
                                onClick={() => downloadSlide(slide.id, slide.endpoint, page)}
                                disabled={downloading[`${slide.id}-${page}`]}
                                variant="outline"
                                size="sm"
                                className="px-3"
                                data-testid={`download-${slide.id}-p${page}`}
                              >
                                {downloading[`${slide.id}-${page}`] ? (
                                  <div className="animate-spin h-3 w-3 border-2 border-current border-t-transparent rounded-full" />
                                ) : (
                                  `P${page}`
                                )}
                              </Button>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Specs Info */}
            <div className="mt-8 bubba-card p-6">
              <h3 className="font-serif font-bold text-foreground mb-3">Slide Specifications</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <span className="text-gray-500">Resolution:</span>
                  <span className="ml-2 font-semibold">1920×1080</span>
                </div>
                <div>
                  <span className="text-gray-500">Aspect Ratio:</span>
                  <span className="ml-2 font-semibold">16:9</span>
                </div>
                <div>
                  <span className="text-gray-500">Format:</span>
                  <span className="ml-2 font-semibold">PNG</span>
                </div>
                <div>
                  <span className="text-gray-500">Yodeck Ready:</span>
                  <span className="ml-2 font-semibold text-green-600">✓ Yes</span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
