import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// A versão vem do arquivo VERSION da raiz (fonte única), nunca do package.json.
const versao = readFileSync(fileURLToPath(new URL('../VERSION', import.meta.url)), 'utf-8').trim()

export default defineConfig({
  plugins: [react(), tailwindcss()],
  define: {
    __VERSAO_APP__: JSON.stringify(versao),
  },
  server: {
    // Em desenvolvimento, a API roda fora do Nginx.
    proxy: {
      '/api': 'http://localhost:8000',
      '/_allauth': 'http://localhost:8000',
      '/accounts': 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
  },
})
