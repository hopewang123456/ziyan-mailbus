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
        manualChunks(id) {
          if (id.includes("node_modules")) {
            if (
              id.includes("react-dom") ||
              id.includes("react-router") ||
              id.includes(`${path.sep}react${path.sep}`) ||
              id.includes("/react/")
            ) {
              return "react-vendor";
            }
            return "vendor";
          }
          if (id.includes(`${path.sep}pages${path.sep}thin${path.sep}`) || id.includes("WorkflowBoardPage")) {
            return "workflow";
          }
          if (id.includes("ClinicPage") || id.includes("ManagerDeskPage")) {
            return "ops-ui";
          }
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:9814" },
  },
});
