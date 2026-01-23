/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
    './app/**/*.{js,jsx}',
    './src/**/*.{js,jsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        'serif': ['Merriweather', 'serif'],
        'sans': ['Inter', 'sans-serif'],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "#D12E2E",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#005B96",
          foreground: "#FFFFFF",
        },
        accent: {
          DEFAULT: "#F4D03F",
          foreground: "#2C3E50",
        },
        muted: {
          DEFAULT: "#E5E7EB",
          foreground: "#6B7280",
        },
        card: {
          DEFAULT: "#FFFFFF",
          foreground: "#2C3E50",
        },
        popover: {
          DEFAULT: "#FFFFFF",
          foreground: "#2C3E50",
        },
        'brand-red': '#D12E2E',
        'brand-blue': '#005B96',
        'brand-yellow': '#F4D03F',
        'wood-texture': '#8B5A2B',
        'paper-bg': '#F9F7F2',
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}