import { existsSync, readFileSync, statSync } from "node:fs"
import { resolve } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"

/** index.html's inline scripts, as Vite copies them into the build (only %VITE_*% change). */
const HTML = readFileSync(resolve(process.cwd(), "index.html"), "utf8")
const INLINE_SCRIPTS = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1])

function inlineScript(marker: string): string {
  const script = INLINE_SCRIPTS.find((s) => s.includes(marker))
  if (!script) throw new Error(`no inline script with ${marker}`)
  return script
}

describe("index.html: the Umami bootstrap", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("tells the tracker to drop query strings (reset and verification tokens, a room's code and PIN)", () => {
    // Prepare: the bootstrap as a build with analytics configured renders it
    const built = inlineScript("%VITE_UMAMI_URL%").replace("%VITE_UMAMI_URL%", "https://analytics.example").replace("%VITE_UMAMI_WEBSITE_ID%", "site-1")

    const appended: Node[] = []
    vi.spyOn(document.head, "appendChild").mockImplementation(<T extends Node>(node: T) => (appended.push(node), node))

    // Act
    new Function(built)()

    // Assert
    const tracker = appended.find((n): n is HTMLScriptElement => n instanceof HTMLScriptElement)
    expect(tracker?.src).toBe("https://analytics.example/script.js")
    expect(tracker?.getAttribute("data-website-id")).toBe("site-1")
    expect(tracker?.getAttribute("data-exclude-search")).toBe("true")
  })

  it("injects nothing in a build without analytics", () => {
    // Prepare: the placeholders Vite leaves when the variables are unset
    const built = inlineScript("%VITE_UMAMI_URL%")
    const appendChild = vi.spyOn(document.head, "appendChild")

    // Act
    new Function(built)()

    // Assert
    expect(appendChild).not.toHaveBeenCalled()
  })
})

describe("index.html: link previews", () => {
  it("points og:image and twitter:image at the JPEG card, with its type and size", () => {
    // Prepare
    const meta = (attr: string, key: string) => new RegExp(`<meta ${attr}="${key}" content="([^"]+)"`).exec(HTML)?.[1]

    // Act / Assert
    expect(meta("property", "og:image")).toBe("https://majlisna.app/og-image.jpg")
    expect(meta("name", "twitter:image")).toBe("https://majlisna.app/og-image.jpg")
    expect(meta("property", "og:image:type")).toBe("image/jpeg")
    expect(meta("property", "og:image:width")).toBe("1200")
    expect(meta("property", "og:image:height")).toBe("630")
  })

  it("ships a 1200 x 630 JPEG of 230 kB at most, and no longer the 670 kB PNG", () => {
    // Prepare
    const file = resolve(process.cwd(), "public/og-image.jpg")
    const bytes = readFileSync(file)

    // Act: the frame size, from the first start-of-frame marker (baseline or progressive)
    let size: { width: number; height: number } | null = null
    for (let i = 2; i < bytes.length - 9 && !size;) {
      const marker = bytes[i + 1]
      const length = bytes.readUInt16BE(i + 2)
      if (marker === 0xc0 || marker === 0xc2) size = { height: bytes.readUInt16BE(i + 5), width: bytes.readUInt16BE(i + 7) }
      i += 2 + length
    }

    // Assert
    expect(bytes.subarray(0, 2)).toEqual(Buffer.from([0xff, 0xd8]))
    expect(size).toEqual({ width: 1200, height: 630 })
    expect(statSync(file).size).toBeLessThanOrEqual(230 * 1024)
    expect(existsSync(resolve(process.cwd(), "public/og-image.png"))).toBe(false)
  })
})
