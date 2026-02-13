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
  bubba_gump: { bg: "#0D1B2A", text: "#FFFFFF", accent: "#E63946", name: "Bubba Gump (Recommended)", featured: true },
  dark_navy: { bg: "#0A1628", text: "#FFFFFF", accent: "#FF4757", name: "Dark Navy" },
  light_corporate: { bg: "#F0F4F8", text: "#1A202C", accent: "#E53E3E", name: "Light Corporate" },
  bubba_red: { bg: "#7F1D1D", text: "#FFFFFF", accent: "#FCD34D", name: "Bubba Red" },
  ocean_blue: { bg: "#082F49", text: "#FFFFFF", accent: "#FB923C", name: "Ocean Blue" },
  vegas_gold: { bg: "#1A1A2E", text: "#FFFFFF", accent: "#FFD700", name: "Vegas Gold" },
};

// Seasonal theme previews (auto-applied based on date, or manually selected)
const SEASONAL_THEMES = {
  none: { name: "None (Use Main Theme)", emoji: "" },
  auto: { name: "Auto (Based on Date)", emoji: "📅" },
  valentines: { bg: "#4A0D2A", text: "#FFFFFF", accent: "#FF6B9D", name: "Valentine's Day", emoji: "💕" },
  st_patricks: { bg: "#0D3B0D", text: "#FFFFFF", accent: "#00FF7F", name: "St. Patrick's Day", emoji: "🍀" },
  easter: { bg: "#E8F5E9", text: "#1A202C", accent: "#E91E63", name: "Easter", emoji: "🐰" },
  july_4th: { bg: "#0A1628", text: "#FFFFFF", accent: "#F44336", name: "4th of July", emoji: "🇺🇸" },
  halloween: { bg: "#1A0A00", text: "#FFFFFF", accent: "#FF6600", name: "Halloween", emoji: "🎃" },
  thanksgiving: { bg: "#3E2723", text: "#FFFFFF", accent: "#FF8A65", name: "Thanksgiving", emoji: "🦃" },
  christmas: { bg: "#0D2818", text: "#FFFFFF", accent: "#FF0000", name: "Christmas", emoji: "🎄" },
  new_year: { bg: "#0A0A1A", text: "#FFFFFF", accent: "#FFD700", name: "New Year", emoji: "🎆" },
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
  const [backgrounds, setBackgrounds] = useState([]);
  const [selectedBackground, setSelectedBackground] = useState("dark");
  
  // Theme settings
  const [themeSettings, setThemeSettings] = useState({
    slide_theme: "dark_navy",
    slide_seasonal_theme: "none",
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
      
      // Fetch backgrounds
      const bgResponse = await axios.get(`${API}/v2/snapshots/backgrounds`);
      setBackgrounds(bgResponse.data || []);
      
      // Also fetch current theme settings
      const settingsResponse = await axios.get(
        `${API}/v2/quarter-settings/${selectedYear}/${selectedQuarter}`
      );
      if (settingsResponse.data) {
        setThemeSettings({
          slide_theme: settingsResponse.data.slide_theme || "dark_navy",
          slide_seasonal_theme: settingsResponse.data.slide_seasonal_theme || "none",
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

  const downloadSlide = async (slideId, endpoint, page = 1, format = "16:9") => {
    const key = `${slideId}-${page}`;
    setDownloading(prev => ({ ...prev, [key]: true }));
    
    try {
      // Build the URL with page and format parameters
      let url = `${BACKEND_URL}${endpoint}`;
      // Check if endpoint already has query params
      if (!url.includes('?')) {
        url += page > 1 ? `?page=${page}` : '';
      }
      
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
      
      // Create download link with format in filename
      const formatSuffix = format === "letter" ? "_letter" : "_16x9";
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${slideId}_${selectedQuarter}_${selectedYear}${page > 1 ? `_p${page}` : ''}${formatSuffix}.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      
      // Clean up object URL after a short delay
      setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      
      toast.success("Slide downloaded!");
    } catch (error) {
      console.error("Error downloading slide:", error);
      // Fallback: open in new tab
      window.open(`${BACKEND_URL}${endpoint}`, '_blank');
      toast.info("Opening slide in new tab - right-click to save");
    } finally {
      setDownloading(prev => ({ ...prev, [key]: false }));
    }
  };

  const downloadAllSlides = async () => {
    if (!slideManifest) return;
    
    toast.info("Downloading all slides...");
    let successCount = 0;
    let failCount = 0;
    
    for (const slide of slideManifest.slides) {
      for (let page = 1; page <= slide.pages; page++) {
        try {
          // endpoint already includes /api prefix, so use BACKEND_URL directly
          const url = page > 1 ? `${BACKEND_URL}${slide.endpoint}?page=${page}` : `${BACKEND_URL}${slide.endpoint}`;
          const response = await fetch(url, {
            method: 'GET',
            headers: { 'Accept': 'image/png' }
          });
          
          if (!response.ok) throw new Error('Failed to fetch');
          
          const blob = await response.blob();
          const objectUrl = URL.createObjectURL(blob);
          
          const link = document.createElement('a');
          link.href = objectUrl;
          link.download = `${slide.id}_${selectedQuarter}_${selectedYear}${page > 1 ? `_p${page}` : ''}.png`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          
          setTimeout(() => URL.revokeObjectURL(objectUrl), 500);
          successCount++;
          
          // Small delay between downloads to prevent browser issues
          await new Promise(resolve => setTimeout(resolve, 500));
        } catch {
          failCount++;
          // Fallback: open in new tab
          const url = page > 1 ? `${BACKEND_URL}${slide.endpoint}?page=${page}` : `${BACKEND_URL}${slide.endpoint}`;
          window.open(url, '_blank');
        }
      }
    }
    
    if (failCount === 0) {
      toast.success(`Downloaded all ${successCount} slides!`);
    } else {
      toast.info(`Downloaded ${successCount} slides. ${failCount} opened in new tabs - save manually.`);
    }
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
                Reports & Downloads
              </h1>
            </div>
            <p className="text-gray-500" data-testid="page-subtitle">
              Digital signage slides and printable reports
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
                <label className="text-sm font-medium mb-3 block">Base Theme</label>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
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
              
              {/* Seasonal Theme Overlay */}
              <div className="mb-6">
                <label className="text-sm font-medium mb-3 block">Seasonal Theme (Optional Overlay)</label>
                <p className="text-xs text-gray-500 mb-3">Adds festive decorations and colors to your slides</p>
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  {Object.entries(SEASONAL_THEMES).map(([key, theme]) => (
                    <button
                      key={key}
                      onClick={() => setThemeSettings(prev => ({ ...prev, slide_seasonal_theme: key }))}
                      className={`p-3 rounded-lg border-2 transition-all ${
                        themeSettings.slide_seasonal_theme === key 
                          ? 'border-primary ring-2 ring-primary/20' 
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                      style={{ backgroundColor: theme.bg || '#f8fafc' }}
                    >
                      <div className="text-center">
                        <span className="text-2xl block mb-1">{theme.emoji || '🎨'}</span>
                        <span className="text-xs font-medium" style={{ color: theme.text || '#1a202c' }}>{theme.name}</span>
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
                    <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} backgrounds={backgrounds} selectedBackground={selectedBackground} setSelectedBackground={setSelectedBackground} />
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
                    <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} backgrounds={backgrounds} selectedBackground={selectedBackground} setSelectedBackground={setSelectedBackground} />
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
                      <SlideCard key={slide.id} slide={slide} downloading={downloading} downloadSlide={downloadSlide} selectedQuarter={selectedQuarter} selectedYear={selectedYear} backgrounds={backgrounds} selectedBackground={selectedBackground} setSelectedBackground={setSelectedBackground} />
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
                  <span className="text-gray-500">16:9 Format:</span>
                  <span className="ml-2 font-semibold">1920×1080px</span>
                </div>
                <div>
                  <span className="text-gray-500">Letter Format:</span>
                  <span className="ml-2 font-semibold">8.5×11" (300 DPI)</span>
                </div>
                <div>
                  <span className="text-gray-500">File Type:</span>
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
function SlideCard({ slide, downloading, downloadSlide, selectedQuarter, selectedYear, backgrounds, selectedBackground, setSelectedBackground }) {
  const CategoryIcon = CATEGORY_ICONS[slide.category] || FileImage;
  const categoryColor = CATEGORY_COLORS[slide.category] || "bg-gray-600";
  const [selectedFormat, setSelectedFormat] = useState("16:9");
  
  const hasFormatOptions = slide.formats && slide.formats.length > 1;
  const hasBackgroundOptions = slide.id === "complete-rankings" && backgrounds && backgrounds.length > 0;
  
  const handleDownload = (page = 1) => {
    // Build query params
    let params = [];
    if (hasFormatOptions) params.push(`format=${selectedFormat}`);
    if (hasBackgroundOptions && selectedBackground) params.push(`background=${selectedBackground}`);
    
    const queryString = params.length > 0 ? `?${params.join('&')}` : "";
    const endpoint = slide.endpoint + (page > 1 ? `?page=${page}${queryString ? '&' + params.join('&') : ''}` : queryString);
    downloadSlide(slide.id, endpoint, page, selectedFormat);
  };
  
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
          
          <div className="flex items-center gap-3">
            {/* Background selector for complete-rankings slide */}
            {hasBackgroundOptions && (
              <Select value={selectedBackground} onValueChange={setSelectedBackground}>
                <SelectTrigger className="w-40 h-9" data-testid={`background-select-${slide.id}`}>
                  <SelectValue placeholder="Background" />
                </SelectTrigger>
                <SelectContent>
                  {backgrounds.map((bg) => (
                    <SelectItem key={bg.key} value={bg.key}>
                      <div className="flex items-center gap-2">
                        {bg.preview ? (
                          <img src={bg.preview} alt="" className="w-6 h-4 rounded object-cover" />
                        ) : (
                          <div className="w-6 h-4 rounded bg-[#0f172a]" />
                        )}
                        <span>{bg.name}</span>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
            
            {/* Format selector for slides that support it */}
            {hasFormatOptions && (
              <Select value={selectedFormat} onValueChange={setSelectedFormat}>
                <SelectTrigger className="w-32 h-9" data-testid={`format-select-${slide.id}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="16:9">16:9 (Yodeck)</SelectItem>
                  <SelectItem value="letter">8.5×11" (Print)</SelectItem>
                </SelectContent>
              </Select>
            )}
            
            {slide.pages === 1 ? (
              <Button
                onClick={() => handleDownload()}
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
                    onClick={() => handleDownload(page)}
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
