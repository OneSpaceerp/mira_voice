import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Mira Core's API. It listens on 127.0.0.1 only, so the dev server (and `vite preview` on a
// test server) forwards /api to it; production serving behind the HTTPS proxy is task 2.1/2.6.
const core = process.env.MIRA_CORE_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: { proxy: { '/api': core } },
  preview: { proxy: { '/api': core } },
})
