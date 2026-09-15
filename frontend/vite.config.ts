import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// `npm run build:static` sets VITE_STATIC=true — outputs to ../docs with
// relative asset paths (base: './') so it works from a GitHub Pages project
// page (or any subpath) with zero per-repo configuration. Normal dev/build
// (VITE_STATIC unset) is untouched: base '/', outDir 'dist'.
const isStatic = process.env.VITE_STATIC === 'true'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: isStatic ? './' : '/',
  // emptyOutDir: false so a rebuild never wipes docs/data (the JSON export
  // lives there too, written separately by backend/app/export_static.py).
  build: isStatic ? { outDir: '../docs', emptyOutDir: false } : undefined,
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
