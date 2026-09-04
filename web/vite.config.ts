import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Build output is served by FastAPI: the HTML lives at /app (route in
// companion/main.py) and hashed assets resolve under /static/app/.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/app/",
  build: {
    outDir: "../companion/static/app",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
