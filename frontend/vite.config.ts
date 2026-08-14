import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Backend FastAPI chạy ở :8080 (config/settings.py API_PORT). Dùng tiền tố
// /api/* RIÊNG cho mọi gọi API — KHÔNG dùng /search /temporal /submit trực
// tiếp vì chúng TRÙNG với route trang React (/temporal, /submit): Vite proxy
// chặn request TRƯỚC khi React Router kịp xử lý, nên load thẳng URL /temporal
// (gõ tay hoặc F5) sẽ bị forward nhầm sang backend (chỉ nhận POST) -> lỗi
// "Method Not Allowed". /media không đụng route trang nào nên giữ nguyên.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
      "/media": "http://localhost:8080",
    },
  },
});
