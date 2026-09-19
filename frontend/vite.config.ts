import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 开发模式：Vite 代理 /api 到 Flask（附录 G G1）；
// 生产构建产物由 Flask 同源托管，不需要 CORS。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:5000', changeOrigin: true },
      '/healthz': { target: 'http://127.0.0.1:5000', changeOrigin: true },
    },
  },
  build: { outDir: 'dist' },
})
