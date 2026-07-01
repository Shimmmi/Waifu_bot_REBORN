import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  base: '/armory/',
  build: {
    outDir: resolve(__dirname, '../static/armory'),
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api/armory': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
