import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// API_PROXY_TARGET lets local dev point at a Flask instance on a
// non-default port (e.g. when 5001 is already in use by an SSH tunnel to a
// deployed console) without changing the checked-in default.
const apiTarget = process.env.API_PROXY_TARGET || 'http://localhost:5001'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': apiTarget,
      '/update-skill': apiTarget,
    },
  },
})
