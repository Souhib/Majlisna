import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev proxy target. Defaults to the native backend (`uv run python main.py`);
// point it at the seeded E2E stack with VITE_DEV_PROXY_TARGET=http://127.0.0.1:5049.
const DEV_PROXY_TARGET = process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:5111'

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
        target: DEV_PROXY_TARGET,
        changeOrigin: true,
      },
      '/socket.io': {
        target: DEV_PROXY_TARGET,
        changeOrigin: true,
        ws: true,
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
