import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    // The backend serves this folder directly (STATIC_DIR), so the production
    // build must land in ../static - not in a separate frontend/dist that
    // nobody serves. `emptyOutDir` keeps stale hashed assets out.
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: false,
  },
});
