import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// SPA estática desplegada en Vercel (§12.2). Sin SSR: es un panel interno (§12.9).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      // En dev la API va por proxy para no lidiar con CORS (§12.8)
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    sourcemap: true, // Sentry necesita los sourcemaps (§12.2)
    rollupOptions: {
      output: {
        manualChunks: {
          // Las tablas virtualizadas y los catálogos masivos pesan;
          // separarlos evita un bundle inicial enorme (§12.9)
          vendor: ['react', 'react-dom', 'react-router-dom'],
          datos: ['@tanstack/react-query', '@supabase/supabase-js'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/pruebas/setup.ts'],
  },
});
