import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
      '@components': path.resolve(__dirname, './src/components'),
      '@pages': path.resolve(__dirname, './src/pages'),
      '@services': path.resolve(__dirname, './src/services'),
      '@hooks': path.resolve(__dirname, './src/hooks'),
      '@utils': path.resolve(__dirname, './src/utils'),
      '@contexts': path.resolve(__dirname, './src/contexts'),
      '@assets': path.resolve(__dirname, './src/assets'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/mcp': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/docs': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/redoc': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    }
  },
  build: {
    // Increase limit since PrimeReact is unavoidably large
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          // Split large vendor libraries into separate chunks
          if (id.includes('node_modules')) {
            // MathJax - separate chunk (loaded only on results page)
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
            // OIDC
            if (id.includes('oidc-client-ts') || id.includes('react-oidc-context')) {
              return 'vendor-oidc';
            }
            // PrimeReact - split into its own chunk
            if (id.includes('primereact') || id.includes('primeicons')) {
              return 'vendor-primereact';
            }
            // React core
            if (id.includes('react-dom') || id.includes('react-router')) {
              return 'vendor-react';
            }
            // DOMPurify
            if (id.includes('dompurify')) {
              return 'vendor-purify';
            }
          }
        }
      }
    }
  }
})
