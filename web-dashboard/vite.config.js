import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    watch: {
      // Ignore config file to prevent restart loops on some OS filestems
      ignored: ['**/vite.config.js'],
      usePolling: true,
      interval: 1000,
    },
    hmr: {
      overlay: true,
    }
  }
})
