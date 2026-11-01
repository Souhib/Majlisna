// @vitest-environment node
import { mkdtempSync, rmSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { join } from "node:path"
import { spawnSync } from "node:child_process"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { cspSourceList, inlineScriptHashes } from "./csp-inline-hashes.mjs"

// Reference values computed outside this code: printf '<text>' | openssl dgst -sha256 -binary | base64
const SHA256_ALERT_1 = "'sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI='"
const SHA256_EMPTY = "'sha256-47DEQpj8HBSa+/TImW+5JCeuQeRkm5NMpJWZG3hSuFU='"
const SHA256_NEWLINE_LOG_NEWLINE = "'sha256-DJzIBIextruQuJdx8e16KYcQYMF+JURLmttUxtAZ10Y='"

const SCRIPT = fileURLToPath(new URL("./csp-inline-hashes.mjs", import.meta.url))

describe("inlineScriptHashes", () => {
  it("hashes the exact text of every inline script, in document order", () => {
    // Prepare
    const html = `<html><head><script>alert(1)</script></head><body><script>\nconsole.log("a")\n</script></body></html>`

    // Act
    const hashes = inlineScriptHashes(html)

    // Assert
    expect(hashes).toEqual([SHA256_ALERT_1, SHA256_NEWLINE_LOG_NEWLINE])
  })

  it("skips scripts loaded from a URL, which script-src allows by origin", () => {
    // Prepare
    const html = `<script type="module" crossorigin src="/assets/index-abc.js"></script><script>alert(1)</script><script defer src=https://x.test/s.js></script>`

    // Act / Assert
    expect(inlineScriptHashes(html)).toEqual([SHA256_ALERT_1])
  })

  it("keeps typed and empty inline scripts, and lists a repeated body once", () => {
    // Prepare
    const html = `<script type="text/javascript">alert(1)</script><SCRIPT>alert(1)</SCRIPT><script></script>`

    // Act / Assert
    expect(inlineScriptHashes(html)).toEqual([SHA256_ALERT_1, SHA256_EMPTY])
  })

  it("hashes what the browser hashes: line breaks normalised to LF", () => {
    // Prepare: the HTML parser turns CRLF and a lone CR into LF before the hash is taken.
    const crlf = `<script>\r\nconsole.log("a")\r\n</script>`
    const cr = `<script>\rconsole.log("a")\r</script>`

    // Act / Assert
    expect(inlineScriptHashes(crlf)).toEqual([SHA256_NEWLINE_LOG_NEWLINE])
    expect(inlineScriptHashes(cr)).toEqual([SHA256_NEWLINE_LOG_NEWLINE])
  })

  it("refuses inline event handlers, which a hash cannot allow", () => {
    // Prepare
    const html = `<link rel="preload" href="/a.css" onload="this.rel='stylesheet'">`

    // Act / Assert
    expect(() => inlineScriptHashes(html)).toThrow(/onload/)
  })

  it("refuses javascript: URLs", () => {
    expect(() => inlineScriptHashes(`<a href="javascript:void(0)">x</a>`)).toThrow(/javascript:/)
  })

  it("does not mistake an attribute that merely contains 'on' for a handler", () => {
    // Prepare
    const html = `<meta name="application-name" content="Majlisna" /><div data-section="x"></div><script>alert(1)</script>`

    // Act / Assert
    expect(inlineScriptHashes(html)).toEqual([SHA256_ALERT_1])
  })

  it("formats the hashes as one CSP source list", () => {
    expect(cspSourceList([SHA256_ALERT_1, SHA256_EMPTY])).toBe(`${SHA256_ALERT_1} ${SHA256_EMPTY}`)
    expect(cspSourceList([])).toBe("")
  })
})

describe("csp-inline-hashes CLI", () => {
  it("prints the source list for a built index.html", () => {
    // Prepare
    const dir = mkdtempSync(join(tmpdir(), "csp-hashes-"))
    const file = join(dir, "index.html")
    writeFileSync(file, `<!doctype html><script>alert(1)</script><script src="/a.js"></script>`)

    // Act
    const run = spawnSync(process.execPath, [SCRIPT, file], { encoding: "utf8" })
    rmSync(dir, { recursive: true, force: true })

    // Assert
    expect(run.status).toBe(0)
    expect(run.stdout.trim()).toBe(SHA256_ALERT_1)
  })

  it("fails the build on an inline handler instead of shipping a page the CSP breaks", () => {
    // Prepare
    const dir = mkdtempSync(join(tmpdir(), "csp-hashes-"))
    const file = join(dir, "index.html")
    writeFileSync(file, `<body onload="go()"></body>`)

    // Act
    const run = spawnSync(process.execPath, [SCRIPT, file], { encoding: "utf8" })
    rmSync(dir, { recursive: true, force: true })

    // Assert
    expect(run.status).toBe(1)
    expect(run.stderr).toMatch(/onload/)
  })
})
