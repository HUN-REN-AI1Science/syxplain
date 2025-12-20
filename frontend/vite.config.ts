import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    // PrimeReact (~525kB) and jsPDF (~616kB) are unavoidably large
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Split large vendor libraries into separate chunks
          if (id.includes('node_modules')) {
            // MathJax is huge - separate chunk
            if (id.includes('mathjax') || id.includes('better-react-mathjax')) {
              return 'vendor-mathjax';
            }
            // jsPDF and html2canvas for PDF export
            if (id.includes('jspdf') || id.includes('html2canvas')) {
              return 'vendor-pdf';
            }
            // Chart.js
            if (id.includes('chart.js') || id.includes('react-chartjs-2')) {
              return 'vendor-charts';
            }
            // Supabase
            if (id.includes('@supabase')) {
              return 'vendor-supabase';
            }
            // React core
            if (id.includes('react-dom')) {
              return 'vendor-react';
            }
            // Do NOT split primereact - causes circular dependency issues
          }
        }
      }
    }
  }
})
