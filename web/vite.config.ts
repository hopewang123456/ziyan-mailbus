import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          "react-vendor": ["react", "react-dom", "react-router-dom"],
        },
      },
    },
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    proxy: { "/api": process.env.MAILBUS_API_TARGET || "http://127.0.0.1:9814" },
  },
  // preview 也走同一代理，便于独立部署时先本地验证产物
  preview: {
    port: 4173,
    proxy: { "/api": process.env.MAILBUS_API_TARGET || "http://127.0.0.1:9814" },
  },
});
