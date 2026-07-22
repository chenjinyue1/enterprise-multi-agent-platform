import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 开发时代理API请求到后端
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // WebSocket代理
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
