import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies the API to FastAPI; production build is served by FastAPI itself.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
});
