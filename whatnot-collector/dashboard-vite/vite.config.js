import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { resolve } from 'node:path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // Keep previous hashed chunks so open browser tabs do not crash when a new
    // deployment lands while they still reference the prior lazy-loaded module.
    emptyOutDir: false,
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        opsNext: resolve(__dirname, 'ops-next.html'),
      },
    },
  },
  server: {
    host: true,      // bind to 0.0.0.0 — accessible from any network device
    proxy: {
      '/events': 'http://localhost:8088',
      '/latest_id': 'http://localhost:8088',
      '/recent': 'http://localhost:8088',
      '/api': 'http://localhost:8088',
    },
  },
})
