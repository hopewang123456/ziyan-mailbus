/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        abyss: "#060910",
        hull: "#0c121c",
        panel: "#101826",
        rail: "#1a2436",
        frost: "#e6eef8",
        mute: "#8a9bb0",
        cyan: {
          signal: "#00d4ff",
          dim: "#0a7a94",
        },
        violet: {
          signal: "#8b5cf6",
          dim: "#5b3d9e",
        },
        amber: {
          signal: "#e8a045",
          dim: "#8a5c12",
        },
        mint: "#3ecf8e",
        flare: "#ff6b4a",
      },
      fontFamily: {
        display: ['"Sora"', "Segoe UI", "sans-serif"],
        body: ['"IBM Plex Sans"', "Segoe UI", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      boxShadow: {
        hud: "0 1px 0 rgba(0,212,255,0.06), 0 12px 40px rgba(0,0,0,0.4)",
        glow: "0 0 0 1px rgba(0,212,255,0.2)",
      },
      keyframes: {
        "star-drift": {
          "0%": { transform: "translate3d(0,0,0)" },
          "100%": { transform: "translate3d(-1.5%, 0.8%, 0)" },
        },
        "brand-in": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "panel-rise": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pulse-ring": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(62,207,142,0.35)" },
          "50%": { boxShadow: "0 0 0 5px rgba(62,207,142,0)" },
        },
      },
      animation: {
        "star-drift": "star-drift 64s linear infinite alternate",
        "brand-in": "brand-in 0.7s cubic-bezier(0.22, 1, 0.36, 1) both",
        "panel-rise": "panel-rise 0.4s ease-out both",
        "pulse-ring": "pulse-ring 2.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
