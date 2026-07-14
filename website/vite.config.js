import { resolve } from 'node:path'
import { defineConfig } from 'vite'

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        main: resolve(import.meta.dirname, 'index.html'),
        goal: resolve(import.meta.dirname, 'goal.html'),
        tour: resolve(import.meta.dirname, 'tour.html'),
        security: resolve(import.meta.dirname, 'solutions/security.html'),
        platform: resolve(import.meta.dirname, 'solutions/platform.html'),
        integration: resolve(import.meta.dirname, 'integration.html'),
      },
    },
  },
})
