import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import viteCompression from 'vite-plugin-compression'

// https://vite.dev/config/
export default defineConfig({
  esbuild: {
    drop: ['console', 'debugger'],
  },
  plugins: [
    TanStackRouterVite({
      routesDirectory: './src/routes',
      generatedRouteTree: './src/routeTree.gen.ts',
      routeFileIgnorePrefix: '-',
      quoteStyle: 'single',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
    // Gzip compression
    viteCompression({
      algorithm: 'gzip',
      ext: '.gz',
      threshold: 10240,
      deleteOriginFile: false,
    }),
    // Brotli compression
    viteCompression({
      algorithm: 'brotliCompress',
      ext: '.br',
      threshold: 10240,
      deleteOriginFile: false,
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:5000',
        changeOrigin: true,
      },
    },
    hmr: {
      overlay: true,
    },
  },
  optimizeDeps: {
    include: [
      'react',
      'react-dom',
      '@tanstack/react-router',
      '@tanstack/react-query',
      'motion/react',
      'lucide-react',
    ],
  },
  build: {
    target: 'es2020',
    chunkSizeWarningLimit: 800,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return

          if (/\/node_modules\/react\//.test(id) || id.includes('/react-dom/')) return 'react-vendor'
          if (id.includes('@tanstack/react-router') || id.includes('@tanstack/react-query')) return 'router-vendor'
          if (id.includes('/motion/') || id.includes('framer-motion')) return 'motion'
          if (id.includes('@radix-ui')) return 'radix-ui'
if (id.includes('i18next') || id.includes('react-i18next')) return 'i18n'
          if (id.includes('lucide-react')) return 'icons'
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    minify: 'esbuild',
  },
})
