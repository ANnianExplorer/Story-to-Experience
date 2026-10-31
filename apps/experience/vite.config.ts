import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      // The participant page only talks to the share/API routes; no provider keys.
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      '/healthz': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  build: { outDir: 'dist', sourcemap: false },
});
