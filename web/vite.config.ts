import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Always resolve from this file’s directory — avoids wrong cwd or a stray `web/#` folder breaking builds.
const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  root: __dirname,
  publicDir: path.join(__dirname, "public"),
  plugins: [react()],
  resolve: {
    alias: { "@": path.join(__dirname, "src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/assistant": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/v1": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
