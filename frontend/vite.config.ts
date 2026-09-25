import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// API в разработке: сервис на Java, по умолчанию http://localhost:8081
const api = process.env.VITE_API_TARGET ?? 'http://localhost:8081';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: api, changeOrigin: true } },
  },
  preview: {
    port: 4173,
    proxy: { '/api': { target: api, changeOrigin: true } },
  },
  build: {
    target: 'es2023',
    cssCodeSplit: true,
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
  },
});
