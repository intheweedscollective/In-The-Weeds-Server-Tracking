import { useState } from "react";
import { Check, Users, Trophy, Star, BarChart3, Settings } from "lucide-react";

const palettes = [
  {
    id: "ocean-professional",
    name: "Ocean Professional",
    description: "Navy base, ocean blue accents, crisp white cards",
    colors: {
      primary: "#0066CC",      // Ocean Blue
      primaryHover: "#0052A3",
      secondary: "#1E3A5F",    // Deep Navy
      accent: "#00A3E0",       // Bright Cyan
      background: "#F5F7FA",   // Cool Gray
      card: "#FFFFFF",
      text: "#1A2B3C",         // Dark Navy Text
      textMuted: "#64748B",
      success: "#059669",
      danger: "#DC2626",
      border: "#E2E8F0",
    }
  },
  {
    id: "bold-corporate",
    name: "Bold Corporate",
    description: "Charcoal dark mode, vibrant blue buttons, high contrast",
    colors: {
      primary: "#2563EB",      // Vibrant Blue
      primaryHover: "#1D4ED8",
      secondary: "#1F2937",    // Charcoal
      accent: "#3B82F6",       // Bright Blue
      background: "#111827",   // Near Black
      card: "#1F2937",         // Dark Card
      text: "#F9FAFB",         // White Text
      textMuted: "#9CA3AF",
      success: "#10B981",
      danger: "#EF4444",
      border: "#374151",
    }
  },
  {
    id: "deep-sea",
    name: "Deep Sea",
    description: "Slate backgrounds, teal accents, modern & sleek",
    colors: {
      primary: "#0891B2",      // Teal
      primaryHover: "#0E7490",
      secondary: "#0F172A",    // Slate 900
      accent: "#06B6D4",       // Cyan
      background: "#0F172A",   // Deep Slate
      card: "#1E293B",         // Slate 800
      text: "#F1F5F9",         // Slate 100
      textMuted: "#94A3B8",    // Slate 400
      success: "#14B8A6",      // Teal
      danger: "#F43F5E",       // Rose
      border: "#334155",       // Slate 700
    }
  }
];

export default function PalettePreview() {
  const [selected, setSelected] = useState(null);

  return (
    <div className="min-h-screen bg-gray-900 p-8">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-3xl font-bold text-white text-center mb-2">
          Color Palette Options
        </h1>
        <p className="text-gray-400 text-center mb-8">
          Click a palette to see it in more detail
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {palettes.map((palette) => (
            <div
              key={palette.id}
              onClick={() => setSelected(palette.id)}
              className={`rounded-2xl overflow-hidden cursor-pointer transition-all ${
                selected === palette.id ? "ring-4 ring-white scale-[1.02]" : "hover:scale-[1.01]"
              }`}
              style={{ backgroundColor: palette.colors.background }}
            >
              {/* Header */}
              <div 
                className="p-4 flex items-center justify-between"
                style={{ backgroundColor: palette.colors.secondary }}
              >
                <div className="flex items-center gap-3">
                  <div 
                    className="w-10 h-10 rounded-full flex items-center justify-center text-white font-bold"
                    style={{ backgroundColor: palette.colors.primary }}
                  >
                    BG
                  </div>
                  <span style={{ color: palette.colors.text }} className="font-semibold">
                    Performance Hub
                  </span>
                </div>
                {selected === palette.id && (
                  <Check className="w-6 h-6 text-green-400" />
                )}
              </div>

              {/* Content */}
              <div className="p-4 space-y-4">
                {/* Palette Name */}
                <div 
                  className="p-4 rounded-xl"
                  style={{ backgroundColor: palette.colors.card, borderColor: palette.colors.border, borderWidth: 1 }}
                >
                  <h3 style={{ color: palette.colors.text }} className="font-bold text-lg">
                    {palette.name}
                  </h3>
                  <p style={{ color: palette.colors.textMuted }} className="text-sm mt-1">
                    {palette.description}
                  </p>
                </div>

                {/* Sample KPI Cards */}
                <div className="grid grid-cols-2 gap-3">
                  <div 
                    className="p-3 rounded-xl"
                    style={{ backgroundColor: palette.colors.card, borderColor: palette.colors.border, borderWidth: 1 }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Users style={{ color: palette.colors.primary }} className="w-4 h-4" />
                      <span style={{ color: palette.colors.textMuted }} className="text-xs uppercase">Crew</span>
                    </div>
                    <span style={{ color: palette.colors.text }} className="text-2xl font-bold">28</span>
                  </div>
                  <div 
                    className="p-3 rounded-xl"
                    style={{ backgroundColor: palette.colors.card, borderColor: palette.colors.border, borderWidth: 1 }}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <Trophy style={{ color: palette.colors.success }} className="w-4 h-4" />
                      <span style={{ color: palette.colors.textMuted }} className="text-xs uppercase">Top</span>
                    </div>
                    <span style={{ color: palette.colors.success }} className="text-2xl font-bold">10</span>
                  </div>
                </div>

                {/* Sample Buttons */}
                <div className="space-y-2">
                  <button
                    className="w-full py-2.5 rounded-lg font-semibold text-white transition-colors"
                    style={{ backgroundColor: palette.colors.primary }}
                  >
                    Primary Button
                  </button>
                  <button
                    className="w-full py-2.5 rounded-lg font-semibold transition-colors"
                    style={{ 
                      backgroundColor: "transparent", 
                      borderColor: palette.colors.primary, 
                      borderWidth: 2,
                      color: palette.colors.primary 
                    }}
                  >
                    Secondary Button
                  </button>
                </div>

                {/* Color Swatches */}
                <div className="flex gap-2 pt-2">
                  <div 
                    className="w-8 h-8 rounded-full border-2 border-white/20" 
                    style={{ backgroundColor: palette.colors.primary }}
                    title="Primary"
                  />
                  <div 
                    className="w-8 h-8 rounded-full border-2 border-white/20" 
                    style={{ backgroundColor: palette.colors.secondary }}
                    title="Secondary"
                  />
                  <div 
                    className="w-8 h-8 rounded-full border-2 border-white/20" 
                    style={{ backgroundColor: palette.colors.accent }}
                    title="Accent"
                  />
                  <div 
                    className="w-8 h-8 rounded-full border-2 border-white/20" 
                    style={{ backgroundColor: palette.colors.success }}
                    title="Success"
                  />
                  <div 
                    className="w-8 h-8 rounded-full border-2 border-white/20" 
                    style={{ backgroundColor: palette.colors.danger }}
                    title="Danger"
                  />
                </div>

                {/* Navigation Sample */}
                <div 
                  className="p-3 rounded-xl space-y-1"
                  style={{ backgroundColor: palette.colors.secondary }}
                >
                  <div 
                    className="flex items-center gap-2 px-3 py-2 rounded-lg"
                    style={{ backgroundColor: palette.colors.primary }}
                  >
                    <BarChart3 className="w-4 h-4 text-white" />
                    <span className="text-white text-sm font-medium">Dashboard</span>
                  </div>
                  <div 
                    className="flex items-center gap-2 px-3 py-2 rounded-lg"
                    style={{ color: palette.colors.textMuted }}
                  >
                    <Trophy className="w-4 h-4" />
                    <span className="text-sm">Rankings</span>
                  </div>
                  <div 
                    className="flex items-center gap-2 px-3 py-2 rounded-lg"
                    style={{ color: palette.colors.textMuted }}
                  >
                    <Star className="w-4 h-4" />
                    <span className="text-sm">Reviews</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Instructions */}
        <div className="mt-8 text-center">
          <p className="text-gray-400">
            Tell me which palette you prefer: <span className="text-white font-semibold">Ocean Professional</span>, <span className="text-white font-semibold">Bold Corporate</span>, or <span className="text-white font-semibold">Deep Sea</span>
          </p>
          <p className="text-gray-500 text-sm mt-2">
            Or let me know what you'd like to adjust and I'll create a custom version.
          </p>
        </div>
      </div>
    </div>
  );
}
