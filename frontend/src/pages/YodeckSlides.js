import { useState, useEffect, useCallback } from "react";
import { Monitor, Download, Calendar, FileImage, Palette, Star, TrendingUp, AlertTriangle, Settings2 } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";
import Navigation from "../components/Navigation";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Input } from "../components/ui/input";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Pre-built theme previews
const THEME_PREVIEWS = {
  dark_navy: { bg: "#0A1628", text: "#FFFFFF", accent: "#D12E2E", name: "Dark Navy" },
  light_corporate: { bg: "#F8FAFC", text: "#1E293B", accent: "#D12E2E", name: "Light Corporate" },
  bubba_red: { bg: "#7F1D1D", text: "#FFFFFF", accent: "#FEF2F2", name: "Bubba Red" },
  ocean_blue: { bg: "#0C4A6E", text: "#FFFFFF", accent: "#38BDF8", name: "Ocean Blue" },
};

// Category icons
const CATEGORY_ICONS = {
  primary: Star,
  tier: FileImage,
  special: TrendingUp,
  manager: AlertTriangle,
};

// Category colors
const CATEGORY_COLORS = {
  primary: "bg-gradient-to-br from-yellow-400 to-orange-500",
  tier: "bg-secondary",
  special: "bg-green-600",
  manager: "bg-red-600",
};

export default function YodeckSlides() {
  const [slideManifest, setSlideManifest] = useState(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState({});
  const [selectedYear, setSelectedYear] = useState(2026);
  const [selectedQuarter, setSelectedQuarter] = useState("Q1");
  const [showThemeSettings, setShowThemeSettings] = useState(false);
  const [savingTheme, setSavingTheme] = useState(false);
  
  // Theme settings
  const [themeSettings, setThemeSettings] = useState({
    slide_theme: "dark_navy",
    slide_bg_color: "#0A1628",
    slide_bg_gradient: "#132238",
    slide_text_color: "#FFFFFF",
    slide_accent_color: "#D12E2E",
    slide_secondary_color: "#005B96",
  });

  const fetchSlideManifest = useCallback(async () => {
    setLoading(true);
    try {
      const response = await axios.get(
        `${API}/v2/yodeck/${selectedYear}/${selectedQuarter}/all`
      );
      setSlideManifest(response.data);
      
      // Also fetch current theme settings
      const settingsResponse = await axios.get(
        `${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`
      );
      if (settingsResponse.data) {
        setThemeSettings({
          slide_theme: settingsResponse.data.slide_theme || "dark_navy",
          slide_bg_color: settingsResponse.data.slide_bg_color || "#0A1628",
          slide_bg_gradient: settingsResponse.data.slide_bg_gradient || "#132238",
          slide_text_color: settingsResponse.data.slide_text_color || "#FFFFFF",
          slide_accent_color: settingsResponse.data.slide_accent_color || "#D12E2E",
          slide_secondary_color: settingsResponse.data.slide_secondary_color || "#005B96",
        });
      }
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
      
      // Use fetch to get the blob directly - more reliable than anchor download
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Accept': 'image/png'
        }
      });
      
      if (!response.ok) {
        throw new Error(`Failed to fetch slide: ${response.status}`);
      }
      
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      
      // Create download link
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${slideId}_${selectedQuarter}_${selectedYear}${page > 1 ? `_p${page}` : ''}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up object URL after a short delay
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      
      toast.success("Slide downloaded!");
    } catch (error) {
      console.error("Error downloading slide:", error);
      // Fallback: open in new tab
      const url = page > 1 ? `${API}${endpoint}?page=${page}` : `${API}${endpoint}`;
      window.open(url, '_blank');
      toast.info("Opening slide in new tab - right-click to save");
    } finally {
      setDownloading(prev => ({ ...prev, [key]: false }));
    }
  };

  const downloadAllSlides = async () => {
    if (!slideManifest) return;
    
    toast.info("Opening all slides for download...");
    
    for (const slide of slideManifest.slides) {
      for (let page = 1; page <= slide.pages; page++) {
        const url = page > 1 ? `${API}${slide.endpoint}?page=${page}` : `${API}${slide.endpoint}`;
        window.open(url, '_blank');
        await new Promise(resolve => setTimeout(resolve, 800));
      }
    }
    
    toast.success("All slides opened - save each from browser!");
  };

  const saveThemeSettings = async () => {
    setSavingTheme(true);
    try {
      await axios.put(
        `${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`,
        themeSettings
      );
      toast.success("Theme settings saved!");
      setShowThemeSettings(false);
      fetchSlideManifest(); // Refresh to show updated theme
    } catch (error) {
      console.error("Error saving theme:", error);
      toast.error("Failed to save theme settings");
    } finally {
      setSavingTheme(false);
    }
  };

  const handleThemePresetChange = (themeName) => {
    const preset = THEME_PREVIEWS[themeName];
    if (preset) {
      setThemeSettings(prev => ({
        ...prev,
        slide_theme: themeName,
        slide_bg_color: preset.bg,
        slide_text_color: preset.text,
        slide_accent_color: preset.accent,
      }));
    }
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
          
          <div className="flex gap-2">
            <Button
              onClick={() => setShowThemeSettings(!showThemeSettings)}
              variant="outline"
              className="flex items-center gap-2"
              data-testid="theme-settings-btn"
            >
              <Palette className="w-4 h-4" />
              Theme
            </Button>
            {slideManifest && (
              <Button
                onClick={downloadAllSlides}
                className="bg-primary hover:bg-primary/90 text-white flex items-center gap-2"
                data-testid="download-all-btn"
              >
                <Download className="w-4 h-4" />
                Download All
              </Button>
            )}
          </div>
        </div>

        {/* Theme Settings Panel */}
        {showThemeSettings && (
          <div className="bubba-card mb-8" data-testid="theme-panel">
            <div className="tape tape-blue" style={{ top: '-8px', left: '50%', transform: 'translateX(-50%) rotate(-1deg)' }} />
            <div className="p-6 pt-8">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-10 h-10 rounded-full bg-purple-100 flex items-center justify-center">
                  <Palette className="w-5 h-5 text-purple-600" />
                </div>
                <h2 className="text-lg font-serif font-bold text-foreground">Slide Theme Settings</h2>
                <span className="text-sm text-gray-500 ml-2">(Per-Quarter)</span>
              </div>
              
              {/* Pre-built Themes */}
              <div className="mb-6">
                <label className="text-sm font-medium mb-3 block">Pre-built Themes</label>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  {Object.entries(THEME_PREVIEWS).map(([key, theme]) => (
                    <button
                      key={key}
                      onClick={() => handleThemePresetChange(key)}
                      className={`p-4 rounded-lg border-2 transition-all ${
                        themeSettings.slide_theme === key 
                          ? 'border-primary ring-2 ring-primary/20' 
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                      style={{ backgroundColor: theme.bg }}
                    >
                      <div className="text-center">
                        <div className="w-8 h-8 rounded-full mx-auto mb-2" style={{ backgroundColor: theme.accent }}></div>
                        <span className="text-xs font-medium" style={{ color: theme.text }}>{theme.name}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
              
              {/* Custom Colors */}
              <div className="mb-6">
                <label className="text-sm font-medium mb-3 block">Custom Colors (for &quot;custom&quot; theme)</label>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Background</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={themeSettings.slide_bg_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_bg_color: e.target.value, slide_theme: 'custom' }))}
                        className="w-10 h-10 rounded cursor-pointer"
                      />
                      <Input
                        value={themeSettings.slide_bg_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_bg_color: e.target.value, slide_theme: 'custom' }))}
                        className="text-xs h-8"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Gradient End</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={themeSettings.slide_bg_gradient}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_bg_gradient: e.target.value, slide_theme: 'custom' }))}
                        className="w-10 h-10 rounded cursor-pointer"
                      />
                      <Input
                        value={themeSettings.slide_bg_gradient}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_bg_gradient: e.target.value, slide_theme: 'custom' }))}
                        className="text-xs h-8"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Text Color</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={themeSettings.slide_text_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_text_color: e.target.value, slide_theme: 'custom' }))}
                        className="w-10 h-10 rounded cursor-pointer"
                      />
                      <Input
                        value={themeSettings.slide_text_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_text_color: e.target.value, slide_theme: 'custom' }))}
                        className="text-xs h-8"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Accent (Primary)</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={themeSettings.slide_accent_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_accent_color: e.target.value, slide_theme: 'custom' }))}
                        className="w-10 h-10 rounded cursor-pointer"
                      />
                      <Input
                        value={themeSettings.slide_accent_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_accent_color: e.target.value, slide_theme: 'custom' }))}
                        className="text-xs h-8"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-gray-500 block mb-1">Secondary</label>
                    <div className="flex items-center gap-2">
                      <input
                        type="color"
                        value={themeSettings.slide_secondary_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_secondary_color: e.target.value, slide_theme: 'custom' }))}
                        className="w-10 h-10 rounded cursor-pointer"
                      />
                      <Input
                        value={themeSettings.slide_secondary_color}
                        onChange={(e) => setThemeSettings(prev => ({ ...prev, slide_secondary_color: e.target.value, slide_theme: 'custom' }))}
                        className="text-xs h-8"
                      />
                    </div>
                  </div>
                </div>
              </div>
              
              {/* Save Button */}
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setShowThemeSettings(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={saveThemeSettings}
                  disabled={savingTheme}
                  className="bg-primary hover:bg-primary/90"
                >
                  {savingTheme ? "Saving..." : "Save Theme"}
                </Button>
              </div>
            </div>
          </div>
        )}

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
            
            <div className="flex gap-4 items-center">
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
              
              {slideManifest && (
                <div className="ml-4 flex items-center gap-2 text-sm text-gray-500">
                  <span>Current theme:</span>
                  <span className="px-2 py-1 bg-gray-100 rounded font-medium">
                    {THEME_PREVIEWS[slideManifest.theme]?.name || slideManifest.theme}
                  </span>
                </div>
              )}
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
                <div className="text-xs text-gray-500 uppercase">Total</div>
              </div>
              {Object.entries(slideManifest.tier_counts).map(([tier, count]) => (
                <div key={tier} className="bubba-card p-4 text-center">
                  <div className={`text-2xl font-serif font-black ${tier === "A-Server" ? "text-green-600" : tier === "B-Server" ? "text-yellow-600" : tier === "C-Server" ? "text-red-600" : tier === "Trainer" ? "text-purple-600" : "text-blue-600"}`}>
                    {count}
                  </div>
                  <div className="text-xs text-gray-500 uppercase">{tier.replace("-Server", "")}</div>
                </div>
              ))}
            </div>

            {/* Slide Cards by Category */}
            <div className="space-y-6" data-testid="slides-list">
              {/* Primary Slides */}
              <div>
                <h2 className="text-lg font-serif font-bold text-foreground mb-3 flex items-center gap-2">
                  <Star className="w-5 h-5 text-yellow-500" />
                  Primary Display
                </h2>
                <div className="space-y-3">
                  {slideManifest.slides.filter(s => s.category === "primary").map((slide) => (
                    <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} />
                  ))}
                </div>
              </div>
              
              {/* Tier Slides */}
              <div>
                <h2 className="text-lg font-serif font-bold text-foreground mb-3 flex items-center gap-2">
                  <FileImage className="w-5 h-5 text-secondary" />
                  Tier Rankings
                </h2>
                <div className="space-y-3">
                  {slideManifest.slides.filter(s => s.category === "tier").map((slide) => (
                    <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} />
                  ))}
                </div>
              </div>
              
              {/* Special Slides */}
              <div>
                <h2 className="text-lg font-serif font-bold text-foreground mb-3 flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-green-600" />
                  Special Slides
                </h2>
                <div className="space-y-3">
                  {slideManifest.slides.filter(s => s.category === "special").map((slide) => (
                    <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} />
                  ))}
                </div>
              </div>
              
              {/* Manager Only Slides */}
              {slideManifest.slides.some(s => s.category === "manager") && (
                <div>
                  <h2 className="text-lg font-serif font-bold text-foreground mb-3 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5 text-red-600" />
                    Manager Only
                  </h2>
                  <div className="space-y-3">
                    {slideManifest.slides.filter(s => s.category === "manager").map((slide) => (
                      <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} />
                    ))}
                  </div>
                </div>
              )}
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

// Slide Card Component
function SlideCard({ slide, downloading, downloadSlide, selectedQuarter, selectedYear }) {
  const CategoryIcon = CATEGORY_ICONS[slide.category] || FileImage;
  const categoryColor = CATEGORY_COLORS[slide.category] || "bg-gray-600";
  
  return (
    <div className="bubba-card" data-testid={`slide-card-${slide.id}`}>
      <div className="p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className={`w-12 h-12 rounded-lg flex items-center justify-center ${categoryColor}`}>
              <CategoryIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h3 className="text-lg font-serif font-bold text-foreground">
                {slide.name}
              </h3>
              <p className="text-sm text-gray-500">
                {slide.employee_count !== undefined 
                  ? `${slide.employee_count} employees • ${slide.pages} slide${slide.pages > 1 ? 's' : ''}`
                  : `${slide.pages} slide`
                }
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
                Download
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
  );
}
