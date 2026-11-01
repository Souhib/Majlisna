import { existsSync, readFileSync, statSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { describe, expect, it } from "vitest"

/**
 * The faces fonts.css declares on top of @fontsource's (FP-13): a few-kB Readex Pro face
 * for the transliteration letters, and Amiri's space alone, so that one "salām" or one
 * space in an Arabic phrase no longer downloads a whole latin-ext or Latin file.
 */
const FONTS_TS = readFileSync(resolve(process.cwd(), "src/fonts.ts"), "utf8")
const FONTS_CSS_PATH = resolve(process.cwd(), "src/fonts.css")

interface Face {
  family: string
  weight: string
  src: string
  ranges: [number, number][]
}

function faces(): Face[] {
  const css = readFileSync(FONTS_CSS_PATH, "utf8").replace(/\/\*[\s\S]*?\*\//g, "")
  return [...css.matchAll(/@font-face\s*{([^}]*)}/g)].map(([, body]) => {
    const prop = (name: string) => new RegExp(`${name}\\s*:\\s*([^;]+);`).exec(body)?.[1].trim() ?? ""
    return {
      family: prop("font-family").replace(/["']/g, ""),
      weight: prop("font-weight"),
      src: /url\(["']?([^"')]+)["']?\)/.exec(prop("src"))?.[1] ?? "",
      ranges: prop("unicode-range")
        .split(",")
        .map((r) => r.trim().replace(/^U\+/i, ""))
        .filter(Boolean)
        .map((r) => {
          const [a, b = a] = r.split("-")
          return [parseInt(a, 16), parseInt(b, 16)] as [number, number]
        }),
    }
  })
}

const covers = (face: Face, cp: number) => face.ranges.some(([a, b]) => a <= cp && cp <= b)

/** fontsource's latin face for Readex Pro and Amiri (the same range): what it already draws. */
const LATIN =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD"
    .split(",")
    .map((r) =>
      r
        .replace("U+", "")
        .split("-")
        .map((h) => parseInt(h, 16)),
    )
    .map(([a, b = a]) => [a, b] as [number, number])
const inLatin = (cp: number) => LATIN.some(([a, b]) => a <= cp && cp <= b)

/** WOFF2's known table tags, in the order of their 6-bit index (WOFF2 spec, 5.1). */
const WOFF2_TAGS =
  "cmap,head,hhea,hmtx,maxp,name,OS/2,post,cvt ,fpgm,glyf,loca,prep,CFF ,VORG,EBDT,EBLC,gasp,hdmx,kern,LTSH,PCLT,VDMX,vhea,vmtx,BASE,GDEF,GPOS,GSUB,EBSC,JSTF,MATH,CBDT,CBLC,COLR,CPAL,SVG ,sbix,acnt,avar,bdat,bloc,bsln,cvar,fdsc,feat,fmtx,fvar,gvar,hsty,just,lcar,mort,morx,opbd,prop,trak,Zapf,Silf,Glat,Gloc,Feat,Sill".split(
    ",",
  )

/** The original length of each table of a WOFF2 file, from its table directory. */
function woff2TableLengths(file: string): Record<string, number> {
  const buf = readFileSync(file)
  expect(buf.toString("latin1", 0, 4)).toBe("wOF2")
  let at = 48
  const base128 = () => {
    let value = 0
    for (let i = 0; i < 5; i++) {
      const byte = buf[at++]
      value = value * 128 + (byte & 0x7f)
      if (!(byte & 0x80)) return value
    }
    throw new Error("bad UIntBase128")
  }
  const lengths: Record<string, number> = {}
  for (let i = buf.readUInt16BE(12); i > 0; i--) {
    const flags = buf[at++]
    let tag = WOFF2_TAGS[flags & 0x3f]
    if ((flags & 0x3f) === 0x3f) {
      tag = buf.toString("latin1", at, at + 4)
      at += 4
    }
    lengths[tag] = base128()
    const version = flags >> 6
    if (tag === "glyf" || tag === "loca" ? version !== 3 : version !== 0) base128() // transformLength
  }
  return lengths
}

describe("fonts.css", () => {
  it("is imported after the @fontsource faces it overrides (a later face wins for its range)", () => {
    // Prepare
    const at = (s: string) => FONTS_TS.indexOf(s)

    // Act / Assert
    expect(at('import "./fonts.css"')).toBeGreaterThan(at('import "@fontsource-variable/readex-pro"'))
    expect(at('import "./fonts.css"')).toBeGreaterThan(at('import "@fontsource/amiri/700.css"'))
    expect(at('import "@fontsource-variable/readex-pro"')).toBeGreaterThanOrEqual(0)
  })

  it("draws every non-Latin-1 letter of the interface's copy with the small transliteration face", () => {
    // Prepare: the letters the three locales use beyond the Latin file (ā, ṣ, ʿ, ʾ…)
    const translit = faces().find((f) => f.family === "Readex Pro Variable")
    const used = new Set<number>()
    for (const lang of ["en", "fr", "ar"]) {
      const text = readFileSync(resolve(process.cwd(), `src/i18n/locales/${lang}.json`), "utf8")
      for (const ch of text) {
        const cp = ch.codePointAt(0) as number
        if (cp >= 0x0100 && cp < 0x0600 && !inLatin(cp)) used.add(cp)
        if (cp >= 0x1e00 && cp <= 0x1eff) used.add(cp)
      }
    }

    // Act
    const missing = [...used].filter((cp) => !translit || !covers(translit, cp)).map((cp) => String.fromCodePoint(cp))

    // Assert
    expect(translit).toBeDefined()
    expect(translit?.weight).toBe("160 700")
    expect(missing).toEqual([])
    for (const letter of "āīūĀĪŪḥḤṣṢḍḌṭṬẓẒʾʿ") expect(covers(translit as Face, letter.codePointAt(0) as number)).toBe(true)
  })

  it("keeps the transliteration file a few kB, and its range off the Latin file's", () => {
    // Prepare
    const translit = faces().find((f) => f.family === "Readex Pro Variable") as Face
    const file = resolve(dirname(FONTS_CSS_PATH), translit.src)

    // Act / Assert
    expect(existsSync(file)).toBe(true)
    expect(statSync(file).size).toBeLessThan(8 * 1024)
    for (const [a, b] of translit.ranges) for (let cp = a; cp <= b; cp++) expect(inLatin(cp)).toBe(false)
  })

  it("gives Amiri, in both weights, a face for the space and the no-break space alone", () => {
    // Prepare
    const amiri = faces().filter((f) => f.family === "Amiri")

    // Act
    const weights = amiri.map((f) => f.weight).sort()

    // Assert: only U+0020 and U+00A0, never a letter (Latin text set in Amiri keeps its latin face)
    expect(weights).toEqual(["400", "700"])
    for (const face of amiri) {
      expect(face.ranges).toEqual([
        [0x20, 0x20],
        [0xa0, 0xa0],
      ])
      const file = resolve(dirname(FONTS_CSS_PATH), face.src)
      expect(existsSync(file)).toBe(true)
      // small enough for Vite to inline it (assetsInlineLimit 4096): no request at all
      expect(statSync(file).size).toBeLessThan(4096)
    }
  })

  it("ships subset files a browser accepts: every glyf holds an outline", () => {
    // Prepare: a subset of spaces alone has no outline, and Chrome's sanitizer (OTS)
    // rejects it ("glyf: zero-length table"); the face fails silently and the space
    // falls back to the 20 kB Latin file (pyftsubset --notdef-outline, SOURCES.txt)
    const files = faces().map((f) => resolve(dirname(FONTS_CSS_PATH), f.src))

    // Act
    const glyf = files.map((file) => woff2TableLengths(file).glyf)

    // Assert: a glyph record is a 10-byte header plus its outline
    expect(files).toHaveLength(3)
    for (const length of glyf) expect(length).toBeGreaterThan(10)
  })
})
