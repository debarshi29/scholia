import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only ever talks to the FastAPI app (never to Ollama or Gemini).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
