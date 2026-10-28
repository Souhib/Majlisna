// Renders the raster brand assets from the vector sources, with the Chromium that the
// E2E suite already installs (e2e/node_modules/playwright):
//
//   public/icons/icon-192.png, icon-512.png       app icon (src/assets/brand/app-icon.svg)
//   public/icons/icon-maskable-512.png             full bleed, ring inside the 80 % safe zone
//   public/icons/apple-touch-icon.png (180)        full bleed (iOS rounds the corners)
//   public/favicon.ico (16, 32, 48)                from public/favicon.svg (needs Pillow)
//   public/og-image.png (1200 × 630)               og-card.html: the night sky + the frozen wordmark
//
// Run from the repo root:  node front/scripts/brand/render-icons.mjs
import { execFileSync } from "node:child_process"
import fs from "node:fs"
import { createRequire } from "node:module"
import os from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const HERE = path.dirname(fileURLToPath(import.meta.url))
const FRONT = path.resolve(HERE, "../..")
const require = createRequire(path.resolve(FRONT, "../e2e/package.json"))
const { chromium } = require("playwright")

const appIcon = fs.readFileSync(`${FRONT}/src/assets/brand/app-icon.svg`, "utf8")
const favicon = fs.readFileSync(`${FRONT}/public/favicon.svg`, "utf8")
const GROUND = "#1d1613"
const inner = (svg) =>
  svg
    .replace(/^[\s\S]*?<svg[^>]*>/, "")
    .replace(/<\/svg>\s*$/, "")
    .replace(/<title>[\s\S]*?<\/title>/, "")
    .replace(/<rect width="100" height="100" rx="22" fill="#1d1613"\/>/, "")
const bleed = (svg, scale) =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="${GROUND}"/>` +
  `<g transform="translate(50 50) scale(${scale}) translate(-50 -50)">${inner(svg)}</g></svg>`

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "majlisna-icons-"))
const jobs = [
  { out: `${FRONT}/public/icons/icon-192.png`, size: 192, svg: appIcon },
  { out: `${FRONT}/public/icons/icon-512.png`, size: 512, svg: appIcon },
  { out: `${FRONT}/public/icons/icon-maskable-512.png`, size: 512, svg: bleed(appIcon, 0.78) },
  { out: `${FRONT}/public/icons/apple-touch-icon.png`, size: 180, svg: bleed(appIcon, 0.86) },
  ...[16, 32, 48].map((size) => ({ out: `${tmp}/ico-${size}.png`, size, svg: favicon })),
]

const browser = await chromium.launch()
const page = await browser.newPage({ deviceScaleFactor: 1 })
for (const job of jobs) {
  await page.setViewportSize({ width: job.size, height: job.size })
  const svg = job.svg.replace("<svg ", `<svg width="${job.size}" height="${job.size}" `)
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`)
  await page.screenshot({ path: job.out, omitBackground: true, clip: { x: 0, y: 0, width: job.size, height: job.size } })
  console.log("wrote", path.relative(FRONT, job.out))
}

await page.setViewportSize({ width: 1200, height: 630 })
await page.goto(`file://${HERE}/og-card.html`, { waitUntil: "networkidle" })
await page.evaluate(() => document.fonts.ready)
await page.screenshot({ path: `${FRONT}/public/og-image.png`, clip: { x: 0, y: 0, width: 1200, height: 630 } })
console.log("wrote public/og-image.png")
await browser.close()

execFileSync("python3", [
  "-I",
  "-c",
  "import sys;from PIL import Image;d=sys.argv[1];i=[Image.open(f'{d}/ico-{s}.png').convert('RGBA') for s in (16,32,48)];" +
    "i[2].save(sys.argv[2],format='ICO',sizes=[(16,16),(32,32),(48,48)],append_images=i[:2])",
  tmp,
  `${FRONT}/public/favicon.ico`,
])
console.log("wrote public/favicon.ico")
