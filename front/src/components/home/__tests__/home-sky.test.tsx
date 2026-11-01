import { render } from "@testing-library/react"
import { existsSync, readFileSync, statSync } from "node:fs"
import { resolve } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@tanstack/react-router", () => ({ Link: () => null, useNavigate: () => vi.fn() }))

import { HomeSky } from "../HomeHero"

/**
 * The home sky: the <picture> in HomeHero and the preload in index.html's inline script
 * are one contract (front/CLAUDE.md): same files, same sizes, per width range, so the
 * browser downloads exactly one sky (FP-19).
 */
const HTML = readFileSync(resolve(process.cwd(), "index.html"), "utf8")
const THEME_SCRIPT = [...HTML.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).find((s) => s.includes("/sky/")) as string

const candidates = (srcset: string | null) =>
  (srcset ?? "")
    .split(",")
    .map((c) => c.trim())
    .filter(Boolean)

/** What the index.html script preloads on "/", by media query. */
function preloads(theme: "dark" | "light") {
  localStorage.setItem("majlisna-theme", theme)
  new Function(THEME_SCRIPT)()
  return [...document.head.querySelectorAll<HTMLLinkElement>('link[rel="preload"][as="image"]')].map((l) => ({
    media: l.media,
    href: l.getAttribute("href"),
    srcset: candidates(l.getAttribute("imagesrcset")),
    sizes: l.getAttribute("imagesizes"),
  }))
}

/** The same three ranges, read from the rendered <picture>. */
function pictureRanges(name: string) {
  const { container } = render(<HomeSky name={name} />)
  const [phone, tablet] = [...container.querySelectorAll("source")]
  const img = container.querySelector("img") as HTMLImageElement
  return {
    phone: { media: phone.getAttribute("media"), srcset: candidates(phone.getAttribute("srcset")), sizes: phone.getAttribute("sizes") },
    tablet: { media: tablet.getAttribute("media"), srcset: candidates(tablet.getAttribute("srcset")), sizes: tablet.getAttribute("sizes") },
    desktop: { srcset: candidates(img.getAttribute("srcset")), sizes: img.getAttribute("sizes"), src: img.getAttribute("src") },
  }
}

describe("home sky", () => {
  afterEach(() => {
    for (const l of document.head.querySelectorAll("link")) l.remove()
    localStorage.clear()
  })

  it("offers tablets an 800, a 1200 and a 1600 crop, sized as the cover box draws them", () => {
    // Prepare / Act
    const { tablet } = pictureRanges("sky-maghrib")

    // Assert: width descriptors, and sizes that follow the box (taller than 2:1 in portrait)
    expect(tablet.srcset).toEqual(["/sky/sky-maghrib.tab800.webp 800w", "/sky/sky-maghrib.tab1200.webp 1200w", "/sky/sky-maghrib.tab1600.webp 1600w"])
    expect(tablet.sizes).toBe("(min-aspect-ratio: 47/50) 100vw, 94vh")
  })

  it.each([
    ["dark", "sky-maghrib"],
    ["light", "sky-asr"],
  ] as const)("index.html preloads, for the %s light, exactly what the picture draws in each range", (theme, name) => {
    // Prepare
    const picture = pictureRanges(name)

    // Act
    const links = preloads(theme)
    const byMedia = (media: string) => links.find((l) => l.media === media)

    // Assert: one preload per range, the same candidates and sizes as the <picture>
    expect(links).toHaveLength(3)
    const phone = byMedia(`${picture.phone.media}`)
    const tablet = byMedia(`(min-width: 761px) and ${picture.tablet.media}`)
    const desktop = byMedia("(min-width: 1101px)")
    expect(phone).toMatchObject({ srcset: picture.phone.srcset, sizes: picture.phone.sizes })
    expect(tablet).toMatchObject({ srcset: picture.tablet.srcset, sizes: picture.tablet.sizes })
    expect(desktop).toMatchObject({ srcset: picture.desktop.srcset, sizes: picture.desktop.sizes, href: picture.desktop.src })
  })

  it("ships every file the picture names, the DPR-1 tablet crops at 110 kB or less", () => {
    // Prepare
    const files = (["sky-maghrib", "sky-asr"] as const).flatMap((name) => {
      const r = pictureRanges(name)
      return [...r.phone.srcset, ...r.tablet.srcset, ...r.desktop.srcset].map((c) => c.split(" ")[0])
    })

    // Act
    const missing = files.filter((f) => !existsSync(resolve(process.cwd(), `public${f}`)))
    const tabletSmall = files.filter((f) => /\.tab(800|1200)\.webp$/.test(f)).map((f) => statSync(resolve(process.cwd(), `public${f}`)).size)

    // Assert
    expect(missing).toEqual([])
    expect(tabletSmall).toHaveLength(4)
    for (const size of tabletSmall) expect(size).toBeLessThanOrEqual(110 * 1024)
  })
})
