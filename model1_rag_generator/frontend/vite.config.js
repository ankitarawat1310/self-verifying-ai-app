import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // 5173/5174 are used by SVAGA 2.0 and generated apps — 3.0 console uses 5303.
    port: Number(process.env.VITE_DEV_PORT || 5303),
    strictPort: true,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8003",
        changeOrigin: true,
        timeout: 600_000,
        proxyTimeout: 600_000,
      },
    },
  },
});
