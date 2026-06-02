import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    // VITE_API_URL is set by Render to the backend's host (no protocol).
    // In dev (no env var) BASE stays '/api' and the proxy below handles it.
    'import.meta.env.VITE_API_BASE': JSON.stringify(
      process.env.VITE_API_URL ? `https://${process.env.VITE_API_URL}` : ''
    ),
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
