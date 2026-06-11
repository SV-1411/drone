import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Where the trigger API lives, as seen FROM THIS PROCESS. On a dev machine
// that's localhost; inside the docker-compose dashboard container it must be
// the api service hostname — compose sets API_UPSTREAM=http://api:8000.
const apiUpstream = process.env.API_UPSTREAM || 'http://localhost:8000'
const wsUpstream = apiUpstream.replace(/^http/, 'ws')

const proxy = {
  '/api': {
    target: apiUpstream,
    changeOrigin: true,
    rewrite: (p) => p.replace(/^\/api/, '')
  },
  '/ws': {
    target: wsUpstream,
    ws: true,
    changeOrigin: true
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
    proxy
  },
  // `vite preview` (used by the Docker image) reads preview.proxy, not
  // server.proxy — declare it explicitly so the containerised dashboard
  // can reach the API.
  preview: {
    port: 5173,
    host: '0.0.0.0',
    proxy
  }
})
