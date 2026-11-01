#!/usr/bin/env node
/**
 * The CSP source list for the inline scripts of a built index.html: one
 * `'sha256-…'` per distinct inline <script>, so `script-src` can drop 'unsafe-inline'.
 *
 * The frontend Dockerfile runs it on dist/index.html right after `vite build` and
 * substitutes the output into security-headers.conf. It must read the BUILT file:
 * Vite rewrites the inline Umami bootstrap (`%VITE_UMAMI_URL%`, `%VITE_UMAMI_WEBSITE_ID%`)
 * from the build args, so the bytes, and therefore the hashes, change with them.
 *
 * What it hashes is what the browser hashes: the element's text exactly as written
 * (no trimming, no entity decoding: script content is raw text), after the HTML
 * parser's line-break normalisation (CRLF and a lone CR become LF).
 *
 * It refuses, with exit code 1, a page a hash cannot cover: an inline event handler
 * (`onload="…"`) or a `javascript:` URL would need 'unsafe-inline' (or
 * 'unsafe-hashes') back, and a page broken by its own policy must fail the build,
 * not production.
 *
 * Usage: node scripts/csp-inline-hashes.mjs dist/index.html   (bun works too)
 */
import { createHash } from "node:crypto"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fileURLToPath } from "node:url"

const SCRIPT_ELEMENT = /<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi
const SRC_ATTRIBUTE = /(?:^|\s)src\s*=/i
// An attribute named on<something>, preceded by whitespace inside a tag.
const EVENT_HANDLER = /<[a-z][^>]*?\s(on[a-z]+)\s*=/i
const JAVASCRIPT_URL = /\b(?:href|src|action|formaction)\s*=\s*["']?\s*javascript:/i

/** The browser's view of script text: CRLF and lone CR become LF. */
function normaliseLineBreaks(text) {
  return text.replace(/\r\n?/g, "\n")
}

/** `'sha256-<base64>'` of a script's text, as CSP spells a hash source. */
function hashSource(text) {
  const digest = createHash("sha256").update(normaliseLineBreaks(text), "utf8").digest("base64")
  return `'sha256-${digest}'`
}

/**
 * The hash sources of every inline script in `html`, in document order, each once.
 * Throws when the page needs something a hash cannot allow.
 */
export function inlineScriptHashes(html) {
  const handler = html.match(EVENT_HANDLER)
  if (handler) {
    throw new Error(`inline event handler "${handler[1]}" found: a CSP hash cannot allow it. Attach the listener from a script instead.`)
  }
  if (JAVASCRIPT_URL.test(html)) {
    throw new Error("a javascript: URL was found: a CSP hash cannot allow it.")
  }

  const hashes = []
  for (const [, attributes, body] of html.matchAll(SCRIPT_ELEMENT)) {
    if (SRC_ATTRIBUTE.test(attributes)) continue
    const source = hashSource(body)
    if (!hashes.includes(source)) hashes.push(source)
  }
  return hashes
}

/** The hashes as one space-separated CSP source list ("" when there are none). */
export function cspSourceList(hashes) {
  return hashes.join(" ")
}

function main(argv) {
  const [file] = argv
  if (!file) {
    console.error("usage: csp-inline-hashes.mjs <path to the built index.html>")
    return 2
  }
  try {
    const html = readFileSync(resolve(file), "utf8")
    process.stdout.write(`${cspSourceList(inlineScriptHashes(html))}\n`)
    return 0
  } catch (error) {
    console.error(`csp-inline-hashes: ${error instanceof Error ? error.message : String(error)}`)
    return 1
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = main(process.argv.slice(2))
}
