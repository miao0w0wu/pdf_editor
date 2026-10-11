import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发模式：python -m pdf_editor --dev 直接加载 http://localhost:5173
// 生产模式：vite build 产出 dist/，由后端 stdlib 静态服务器托管
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
