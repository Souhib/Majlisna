#!/usr/bin/env node
/**
 * The entry chunk's diet, checked on a production build (`bun run build`, then
 * `bun run check:bundle`). The entry is what every page downloads and parses before the
 * first paint, so it keeps out what only some pages, or no page, needs:
 *
 * - zod: Kubb's schemas were re-exported by the generated barrel and nothing imported
 *   them, yet they shipped (and were built) on every load; `jitless` is the marker of the
 *   old zod-jitless shim that came with them;
 * - the Sentry SDK: lib/report-error.ts loads it after the first paint;
 * - and the whole entry stays under a gzip budget.
 *
 * Usage: node scripts/check-bundle.mjs [dist directory]   (default: ./dist)
 * Exit code 1 names every rule that failed.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { gzipSync } from "node:zlib"

/** The entry's gzip budget, in bytes (kB as Vite prints them: 1 kB = 1000 B). */
const ENTRY_GZIP_BUDGET = 60_000

/** Strings that only appear when a module is bundled in (minification keeps them). */
const FORBIDDEN_IN_ENTRY = [
  { name: "the zod-jitless shim", markers: ["jitless"] },
  { name: "zod", markers: ["$ZodType", "ZodError"] },
  { name: "the Sentry SDK (load it lazily, see lib/report-error.ts)", markers: ["__SENTRY__", "Sentry Logger"] },
]

const here = dirname(fileURLToPath(import.meta.url))
const distDir = resolve(process.argv[2] ?? join(here, "..", "dist"))
const kB = (bytes) => `${(bytes / 1000).toFixed(2)} kB`

function fail(message) {
  console.error(`check-bundle: ${message}`)
  process.exit(1)
}

const indexPath = join(distDir, "index.html")
if (!existsSync(indexPath)) fail(`${indexPath} not found: run \`bun run build\` first`)
const html = readFileSync(indexPath, "utf8")

const entrySrc = html.match(/<script[^>]+type="module"[^>]+src="\/?([^"]+\.js)"/)?.[1]
if (!entrySrc) fail("no <script type=module src=…> in index.html")
const entryPath = join(distDir, entrySrc)
const entry = readFileSync(entryPath)
const entryText = entry.toString("utf8")
const entryGzip = gzipSync(entry).length

const problems = []
for (const { name, markers } of FORBIDDEN_IN_ENTRY) {
  const found = markers.filter((marker) => entryText.includes(marker))
  if (found.length > 0) problems.push(`the entry contains ${name} (${found.map((m) => JSON.stringify(m)).join(", ")})`)
}
if (entryGzip >= ENTRY_GZIP_BUDGET) {
  problems.push(`the entry is ${kB(entryGzip)} gzip, over the ${kB(ENTRY_GZIP_BUDGET)} budget`)
}

// For the record: what the first load preloads beside the entry.
const preloads = [...html.matchAll(/rel="modulepreload"[^>]+href="\/?([^"]+\.js)"/g)].map((m) => m[1])
const preloadGzip = preloads.reduce((n, path) => n + gzipSync(readFileSync(join(distDir, path))).length, 0)
const chunkCount = readdirSync(join(distDir, "assets")).filter((f) => f.endsWith(".js")).length

console.log(`entry      ${entrySrc}  ${kB(entry.length)} raw, ${kB(entryGzip)} gzip (budget ${kB(ENTRY_GZIP_BUDGET)})`)
console.log(`preloaded  ${preloads.length} chunks, ${kB(preloadGzip)} gzip`)
console.log(`total      ${chunkCount} JS chunks`)

if (problems.length > 0) {
  for (const problem of problems) console.error(`✗ ${problem}`)
  process.exit(1)
}
console.log("✓ the entry chunk is within its diet")
