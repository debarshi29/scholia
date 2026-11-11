import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The browser only ever talks to the FastAPI app (never to Ollama or Gemini).
// SCHOLIA_API points the dev proxy at another API instance, e.g. one on a scratch database.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "SCHOLIA_");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": env.SCHOLIA_API ?? "http://localhost:8000" },
    },
  };
});
