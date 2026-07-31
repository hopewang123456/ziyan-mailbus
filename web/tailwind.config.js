/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        abyss: "#070b12",
        hull: "#0e1624",
        panel: "#121c2e",
        rail: "#1a2740",
        frost: "#d7e6f5",
        mute: "#7a8fa8",
        cyan: {
          signal: "#3de0ff",
          dim: "#1a8fa8",
        },
        amber: {
          signal: "#f0a020",
          dim: "#8a5c12",
        },
        mint: "#4ade80",
        flare: "#ff6b4a",
      },
      fontFamily: {
        display: ['"Orbitron"', "sans-serif"],
        body: ['"IBM Plex Sans"', "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        hud: "0 0 0 1px rgba(61,224,255,0.12), 0 8px 32px rgba(0,0,0,0.45)",
        glow: "0 0 24px rgba(61,224,255,0.25)",
      },
      keyframes: {
        "star-drift": {
          "0%": { transform: "translate3d(0,0,0)" },
          "100%": { transform: "translate3d(-2%, 1%, 0)" },
        },
        "scan-sweep": {
          "0%": { transform: "translateY(-100%)", opacity: "0" },
          "20%": { opacity: "0.35" },
          "100%": { transform: "translateY(100%)", opacity: "0" },
        },
        "brand-in": {
          "0%": { opacity: "0", letterSpacing: "0.35em", transform: "translateY(12px)" },
          "100%": { opacity: "1", letterSpacing: "0.12em", transform: "translateY(0)" },
        },
        "panel-rise": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(61,224,255,0.35)" },
          "50%": { boxShadow: "0 0 0 6px rgba(61,224,255,0)" },
        },
      },
      animation: {
        "star-drift": "star-drift 48s linear infinite alternate",
        "scan-sweep": "scan-sweep 6s ease-in-out infinite",
        "brand-in": "brand-in 1.1s ease-out forwards",
        "panel-rise": "panel-rise 0.45s ease-out both",
        "pulse-ring": "pulse-ring 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
