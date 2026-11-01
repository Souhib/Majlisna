import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin, type Rollup } from 'vite'

/**
 * Whether a module is reached from the entry through static imports alone, i.e. whether
 * every page needs it at load (Vite's old splitVendorChunk test). A module only a lazy
 * route imports is not, and stays with that route.
 */
const staticFromEntry = new Map<string, boolean>()
function isStaticFromEntry(id: string, getModuleInfo: Rollup.GetModuleInfo, importStack: string[] = []): boolean {
  const known = staticFromEntry.get(id)
  if (known !== undefined) return known
  // an import cycle: not proven reachable through this path
  if (importStack.includes(id)) return false
  const info = getModuleInfo(id)
  const result = !!info && (info.isEntry || info.importers.some((importer) => isStaticFromEntry(importer, getModuleInfo, [...importStack, id])))
  staticFromEntry.set(id, result)
  return result
}

/** A fresh reachability cache for each build (watch mode rebuilds). */
const resetChunkCache: Plugin = { name: 'majlisna-reset-chunk-cache', buildStart: () => staticFromEntry.clear() }

/**
 * Preloads Readex Pro's Latin file from index.html (FP-13). Every page needs it in every
 * language (controls, figures, spaces), but a face is fetched only once a render uses
 * it, after the scripts: text first painted in fallback fonts. Its name carries a hash,
 * known once the bundle is written. src/fonts.ts imports the same file (?url).
 */
const UI_FONT_FILE = /^assets\/readex-pro-latin-wght-normal-[\w-]+\.woff2$/
const preloadUiFont: Plugin = {
  name: 'majlisna-preload-ui-font',
  transformIndexHtml: {
    order: 'post',
    handler(_html, { bundle }) {
      const file = Object.keys(bundle ?? {}).find((name) => UI_FONT_FILE.test(name))
      if (!file) return
      return [{ tag: 'link', attrs: { rel: 'preload', as: 'font', type: 'font/woff2', href: `/${file}`, crossorigin: '' }, injectTo: 'head' }]
    },
  },
}

// Dev proxy target. Defaults to the native backend (`uv run python main.py`);
// point it at the seeded E2E stack with VITE_DEV_PROXY_TARGET=http://127.0.0.1:5049.
const DEV_PROXY_TARGET = process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:5111'

// https://vite.dev/config/
export default defineConfig({
  esbuild: {
    // console.log/debug are debugging noise and leave the production bundle; console.warn
    // and console.error stay, so the warnings the code means to be seen are (FR-9).
    drop: ['debugger'],
    pure: ['console.log', 'console.debug'],
  },
  plugins: [
    resetChunkCache,
    preloadUiFont,
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
        manualChunks(id, { getModuleInfo }) {
          // stylesheets (the @fontsource faces) stay with the entry's CSS, in their order
          if (!id.includes('node_modules') || /\.css($|\?)/.test(id)) return

          // react, react-dom and its scheduler only: a bare '/react-dom/' also matched
          // @floating-ui/react-dom
          if (/\/node_modules\/(react|react-dom|scheduler)\//.test(id)) return 'react-vendor'
          if (id.includes('@tanstack/react-router') || id.includes('@tanstack/react-query')) return 'router-vendor'
          if (id.includes('/motion/') || id.includes('framer-motion')) return 'motion'
          // no Radix rule: each primitive goes with the routes that use it (Select only on
          // /profile, Tabs in the lobby…), instead of one chunk preloaded on every page
          if (id.includes('i18next') || id.includes('react-i18next')) return 'i18n'
          if (id.includes('lucide-react')) return 'icons'
          // the rest of what the app shell needs on every page (the nav's Radix pieces,
          // sonner, ky…): out of the entry, so a deploy that changes only app code leaves
          // it cached. Radix primitives only a lazy route uses are not in it.
          if (isStaticFromEntry(id, getModuleInfo)) return 'vendor'
        },
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash].[ext]',
      },
    },
    minify: 'esbuild',
  },
})
