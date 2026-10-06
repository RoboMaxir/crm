import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev proxy: SPA on :5173 -> FastAPI on :8000 (also avoids CORS in dev).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
