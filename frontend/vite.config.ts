import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs in the app container on :8000 (override with API_URL);
// in production nginx proxies /api.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": process.env.API_URL ?? "http://localhost:8000" } },
});
