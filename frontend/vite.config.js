import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The browser talks to Vite only; Vite forwards /api to FastAPI.
      // That keeps the frontend free of absolute URLs and avoids CORS
      // entirely in development.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
