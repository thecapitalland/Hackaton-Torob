/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          red: "#E5484D",
          green: "#30A46C",
          bg: "#FAFAF7",
          surface: "#FFFFFF",
          text: "#1C1C1A",
          muted: "#6F6E69",
          border: "#E6E4DD",
          amber: "#F5A524",
          gray: "#8E8C85",
          purple: "#8E4EC6",
          yellow: "#FFF4CC",
        },
      },
      fontFamily: {
        sans: ["Vazirmatn", "system-ui", "sans-serif"],
      },
      borderRadius: {
        card: "16px",
      },
      boxShadow: {
        card: "0 1px 2px rgba(0,0,0,.06), 0 4px 16px rgba(0,0,0,.04)",
        sheet: "0 -8px 32px rgba(0,0,0,.12)",
      },
      keyframes: {
        pulseRing: {
          "0%": { transform: "scale(0.8)", opacity: "0.7" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        wave: {
          "0%,100%": { transform: "scaleY(0.4)" },
          "50%": { transform: "scaleY(1)" },
        },
      },
      animation: {
        pulseRing: "pulseRing 1.8s ease-out infinite",
        wave: "wave 0.9s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
