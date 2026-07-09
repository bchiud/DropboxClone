import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev-only proxy: the browser talks to the Vite dev server (same origin), which
// forwards API calls to FastAPI on :8000. Keeps the frontend CORS-free in dev;
// in prod you serve the built dist/ from FastAPI, so it's same-origin anyway.
// Presigned B2 URLs are absolute, so they bypass this and go straight to B2
// (which is why the B2 bucket still needs its own CORS rule).
const API = "http://127.0.0.1:8000";
const proxy = Object.fromEntries(
  ["/auth", "/files", "/blocks", "/shares", "/link"].map((p) => [p, API]),
);

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      ...proxy,
      "/ws": { target: API, ws: true }, // WebSocket upgrade (used in v3)
    },
  },
});
