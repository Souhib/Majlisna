import path from "node:path"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    globals: true,
    environment: "happy-dom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    // `bun run test:coverage`, which CI runs (TQ-14): the hand-written code only, every
    // source file counted whether a test loads it or not, and the build fails below the
    // floor. The floor sits about 2 points under the level measured on 2026-10-31
    // (statements 79.6, branches 75.3, functions 78.8, lines 80.7); raise it as coverage
    // grows, never lower it to let a change through.
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/api/generated/**", "src/routeTree.gen.ts", "src/**/*.test.{ts,tsx}", "src/**/__tests__/**", "src/**/-tests/**", "src/test/**"],
      reporter: ["text-summary", "html"],
      thresholds: {
        statements: 77,
        branches: 73,
        functions: 76,
        lines: 78,
      },
    },
  },
})
