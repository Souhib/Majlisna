import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen } from "@testing-library/react"
import { StrictMode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { dur, ease, inkDuration } from "@/lib/motion"
import { CLUE_STAMP_MS, CLUE_REDUCED_FADE_MS, ClueBanner, writesRightToLeft } from "./ClueBanner"
import { ClueAnnouncer, CluePanel } from "./CluePanel"

const ui = vi.hoisted(() => ({ language: "en" }))
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: ui.language } }),
}))

/**
 * ANIM-3, "the Codenames clue is written in, and its count stamped". A NEW clue on the
 * table is written in its reading direction (the qalam, `inkDuration(word)` on --ease-ink),
 * then its count is stamped, lozenge by lozenge (loz-stamp: 220 ms on --ease-press,
 * --dur-tap apart). Never on a page opened or reloaded on a clue, never on a refetch or a
 * socket push of the same clue. The word, its count and its lozenges are in the DOM from
 * the first frame: the animation only moves them, on `transform` and `opacity` alone.
 * happy-dom has no Web Animations, so `Element.animate` is a recording fake here.
 */

interface FakeAnimation {
  id: string
  cancel: Mock
}

interface AnimateCall {
  el: Element
  keyframes: Keyframe[]
  options: KeyframeAnimationOptions
  anim: FakeAnimation
}

let calls: AnimateCall[] = []

const turn = (clue_word: string | null, clue_number = 2, guesses_made = 0) => ({ clue_word, clue_number, guesses_made })

const cubic = (curve: readonly number[]) => `cubic-bezier(${curve.join(", ")})`

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

/** translateX(…%) → the number of percent. */
function shift(keyframe: Keyframe): number {
  const match = /^translateX\((-?[\d.]+)%\)$/.exec(String(keyframe.transform))
  if (!match) throw new Error(`not a translateX keyframe: ${String(keyframe.transform)}`)
  return Number(match[1])
}

/** Every property a call's keyframes write, apart from the timing keys. */
function animatedProperties(): Set<string> {
  const properties = new Set<string>()
  for (const call of calls)
    for (const frame of call.keyframes) for (const key of Object.keys(frame)) if (key !== "offset" && key !== "easing") properties.add(key)
  return properties
}

const line = (container: HTMLElement) => container.querySelector(".cn-clue-line") as HTMLElement
const pen = (container: HTMLElement) => container.querySelector(".cn-clue-pen") as HTMLElement
const ink = (container: HTMLElement) => container.querySelector(".cn-clue-ink") as HTMLElement
const lozenges = (container: HTMLElement) => [...container.querySelectorAll(".cn-clue-loz > i")]
const callsOn = (el: Element) => calls.filter((call) => call.el === el)

beforeEach(() => {
  calls = []
  stubReducedMotion(false)
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
      const anim: FakeAnimation = { id: "", cancel: vi.fn() }
      calls.push({ el: this, keyframes, options, anim })
      return anim
    }),
  })
})

afterEach(() => {
  delete (HTMLElement.prototype as { animate?: unknown }).animate
  vi.unstubAllGlobals()
})

describe("ClueBanner: the clue at rest", () => {
  it("draws the count as that many brass lozenges beside its figure, for the eye only", () => {
    // Prepare / Act
    const { container } = render(<ClueBanner turn={turn("knowledge", 3)} />)

    // Assert: the figure is still the text a reader and a test read
    expect(screen.getByText("3")).toHaveClass("cn-clue-n")
    expect(lozenges(container)).toHaveLength(3)
    expect(container.querySelector(".cn-clue-loz")).toHaveAttribute("aria-hidden", "true")
  })

  it("draws no lozenge for a clue with no limit, nor for a count past the composer's four", () => {
    const { container, rerender } = render(<ClueBanner turn={turn("mercy", 0)} />)
    expect(lozenges(container)).toHaveLength(0)

    rerender(<ClueBanner turn={turn("mercy", 7)} />)
    expect(lozenges(container)).toHaveLength(0)
    expect(screen.getByText("7")).toBeInTheDocument()
  })
})

describe("ClueBanner: a page opened on a clue", () => {
  it("writes nothing on the first render of a clue (a page load or a reload)", () => {
    // Prepare / Act
    const { container } = render(<ClueBanner turn={turn("knowledge", 2)} />)

    // Assert: nothing animates, and everything is there and visible
    expect(calls).toHaveLength(0)
    expect(screen.getByText("knowledge")).toBeInTheDocument()
    expect(lozenges(container)).toHaveLength(2)
    expect(container.querySelector("[style*='opacity']")).toBeNull()
  })

  it("replays nothing on a refetch or a socket push of the same clue", () => {
    // Prepare: the clue arrived and was written in
    const { rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 2)} />)
    const written = calls.length

    // Act: the same clue again, as new objects, a guess made in between
    rerender(<ClueBanner turn={turn("knowledge", 2)} />)
    rerender(<ClueBanner turn={turn("knowledge", 2, 1)} spymasterName="Yusuf" pointing={{ current: 1, total: 2 }} />)

    // Assert
    expect(calls).toHaveLength(written)
    for (const call of calls) expect(call.anim.cancel).not.toHaveBeenCalled()
  })

  it("is still on a page opened on a clue while the announcer mounts with it", () => {
    render(
      <>
        <ClueAnnouncer clueWord="knowledge" clueNumber={2} teamName="Red" />
        <ClueBanner turn={turn("knowledge", 2)} />
      </>,
    )
    expect(calls).toHaveLength(0)
  })
})

describe("ClueBanner: a new clue is written in, then its count stamped", () => {
  it("writes the word in the reading direction: the pen opens from the start while the ink stands still", () => {
    // Prepare: the spymaster is choosing
    const { container, rerender } = render(<ClueBanner turn={turn(null)} spymasterName="Yusuf" />)
    expect(calls).toHaveLength(0)

    // Act: the clue lands
    rerender(<ClueBanner turn={turn("knowledge", 2)} spymasterName="Yusuf" />)

    // Assert: the pen travels from one full length before the reading start, the ink
    // the opposite way, on the same clock, so the word stays put while it is uncovered
    const [penRun] = callsOn(pen(container))
    const [inkRun] = callsOn(ink(container))
    expect(pen(container)).toHaveAttribute("data-dir", "ltr")
    expect(shift(penRun.keyframes[0])).toBe(-100)
    expect(shift(penRun.keyframes.at(-1) as Keyframe)).toBe(0)
    expect(shift(inkRun.keyframes[0])).toBe(100)
    expect(shift(inkRun.keyframes.at(-1) as Keyframe)).toBe(0)
    const writing = { duration: inkDuration("knowledge") * 1000, easing: cubic(ease.ink) }
    expect(penRun.options).toMatchObject(writing)
    expect(inkRun.options).toMatchObject(writing)
    expect(penRun.options.delay ?? 0).toBe(0)
  })

  it("then stamps the count's lozenges one by one, once the word is written", () => {
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 3)} />)

    const written = inkDuration("knowledge") * 1000
    const stamps = lozenges(container).map((el) => callsOn(el))
    expect(stamps.map((runs) => runs.length)).toEqual([1, 1, 1])
    stamps.forEach(([run], i) => {
      expect(run.options).toMatchObject({ duration: CLUE_STAMP_MS, easing: cubic(ease.press), fill: "backwards" })
      expect(run.options.delay).toBeCloseTo(written + i * dur.tap * 1000, 6)
      // loz-stamp: from 1.6 and unseen, through 0.92, to rest
      expect(run.keyframes[0]).toMatchObject({ transform: "scale(1.6)", opacity: 0 })
      expect(run.keyframes[1]).toMatchObject({ transform: "scale(0.92)", opacity: 1, offset: 0.6 })
      expect(run.keyframes.at(-1)).toMatchObject({ transform: "scale(1)" })
    })
    // the figure itself stands: the lozenges are the count stamped
    expect(callsOn(screen.getByText("3"))).toHaveLength(0)
  })

  it("stamps the figure instead on a banner too narrow for the lozenges (the stylesheet hides them)", () => {
    // Prepare: a phone's banner, where `.cn-clue-loz` is display: none
    const real = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el: Element, pseudo?: string | null) =>
      el.classList.contains("cn-clue-loz") ? ({ display: "none" } as CSSStyleDeclaration) : real(el, pseudo),
    )
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)

    // Act
    rerender(<ClueBanner turn={turn("knowledge", 3)} />)

    // Assert: one stamp, on the figure, once the word is written
    expect(lozenges(container).flatMap((el) => callsOn(el))).toHaveLength(0)
    const [run] = callsOn(screen.getByText("3"))
    expect(run.options).toMatchObject({ duration: CLUE_STAMP_MS, delay: inkDuration("knowledge") * 1000, fill: "backwards" })
    vi.mocked(window.getComputedStyle).mockRestore()
  })

  it("stamps the figure once when the count has no lozenges (no limit)", () => {
    const { rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("mercy", 0)} />)

    const [run] = callsOn(screen.getByText("∞"))
    expect(run.options).toMatchObject({ duration: CLUE_STAMP_MS, delay: inkDuration("mercy") * 1000, fill: "backwards" })
  })

  it("writes an Arabic clue right to left, whatever the interface", () => {
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("صبر", 1)} />)

    expect(pen(container)).toHaveAttribute("data-dir", "rtl")
    expect(shift(callsOn(pen(container))[0].keyframes[0])).toBe(100)
    expect(shift(callsOn(ink(container))[0].keyframes[0])).toBe(-100)
    expect(callsOn(pen(container))[0].options.duration).toBeCloseTo(inkDuration("صبر") * 1000, 6)
  })

  it("moves transform and opacity only, never a property that lays the page out", () => {
    const { rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 4)} />)

    expect(calls.length).toBe(2 + 4)
    expect([...animatedProperties()].sort()).toEqual(["opacity", "transform"])
  })

  it("leaves nothing hidden behind: the word and the count are in the DOM while they are written", () => {
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 2)} />)

    expect(screen.getByText("knowledge")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    // no fill holds anything once its time is over: the stamps only wait for their turn
    for (const call of calls) expect(call.options.fill ?? "none").not.toMatch(/forwards|both/)
    expect(container.querySelector("[style*='opacity']")).toBeNull()
  })

  it("writes each new clue: the next turn's clue is written in too", () => {
    const { rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 1)} />)
    rerender(<ClueBanner turn={turn(null)} />)
    const before = calls.length

    rerender(<ClueBanner turn={turn("knowledge", 1)} />)

    // the same word for the other team is a new clue on the table
    expect(calls.length).toBe(before * 2)
  })

  it("cancels a writing still running when the clue goes, and when the banner goes", () => {
    const { rerender, unmount } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 2)} />)
    const first = [...calls]

    rerender(<ClueBanner turn={turn(null)} />)
    for (const call of first) expect(call.anim.cancel).toHaveBeenCalledOnce()

    rerender(<ClueBanner turn={turn("ilm", 1)} />)
    const second = calls.slice(first.length)
    unmount()
    for (const call of second) expect(call.anim.cancel).toHaveBeenCalledOnce()
  })

  it("names its animations, for a test settling the page", () => {
    const { rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 1)} />)
    expect(new Set(calls.map((call) => call.anim.id))).toEqual(new Set(["clue-ink", "clue-stamp"]))
  })

  it("simply shows the clue where there are no Web Animations", () => {
    delete (HTMLElement.prototype as { animate?: unknown }).animate
    const { rerender } = render(<ClueBanner turn={turn(null)} />)

    rerender(<ClueBanner turn={turn("knowledge", 2)} />)

    expect(screen.getByText("knowledge")).toBeInTheDocument()
  })
})

describe("ClueBanner: reduced motion", () => {
  it("fades the clue line in, once, in 140 ms: nothing travels and nothing is stamped", () => {
    // Prepare
    stubReducedMotion(true)
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)

    // Act
    rerender(<ClueBanner turn={turn("knowledge", 3)} />)

    // Assert
    expect(calls).toHaveLength(1)
    const [fade] = calls
    expect(fade.el).toBe(line(container))
    expect(fade.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(fade.options).toMatchObject({ duration: CLUE_REDUCED_FADE_MS, easing: "linear" })
    expect(fade.options.fill ?? "none").toBe("none")
  })

  it("does not fade a clue the page opened on either", () => {
    stubReducedMotion(true)
    render(<ClueBanner turn={turn("knowledge", 3)} />)
    expect(calls).toHaveLength(0)
  })
})

describe("ClueBanner: a clue that is a sacred name", () => {
  /**
   * The clue is the spymaster's free text, and the server refuses only a card's own word: a
   * name of Allah, the Prophet ﷺ or a prophet may be given. Nothing ever passes over a sacred
   * name (DESIGN.md §7), so the pen's soft edge never sweeps it: the word fades in over
   * --dur-state, then its count is stamped as usual (the lozenges stand beside the word).
   */
  it.each(["Allah", "الله", "Musa", "Muhammad", "Quran"])("fades %s in, and never sweeps the pen across it", (word) => {
    // Prepare
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)

    // Act
    rerender(<ClueBanner turn={turn(word, 2)} />)

    // Assert: nothing travels over the word
    expect(callsOn(pen(container))).toHaveLength(0)
    const [fade, ...more] = callsOn(ink(container))
    expect(more).toHaveLength(0)
    expect(fade.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(fade.options).toMatchObject({ duration: dur.state * 1000, easing: cubic(ease.out) })
    expect(fade.options.fill ?? "none").toBe("none")
    expect(fade.anim.id).toBe("clue-ink")
    for (const call of calls) expect(String(call.keyframes[0].transform ?? "")).not.toMatch(/translate/)
    // the word is there, whole, from the first frame
    expect(screen.getByText(word)).toBeInTheDocument()
  })

  it("then stamps the count, once the word has faded in", () => {
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("Allah", 3)} />)

    const stamps = lozenges(container).map((el) => callsOn(el))
    expect(stamps.map((runs) => runs.length)).toEqual([1, 1, 1])
    stamps.forEach(([run], i) => {
      expect(run.options).toMatchObject({ duration: CLUE_STAMP_MS, fill: "backwards" })
      expect(run.options.delay).toBeCloseTo(dur.state * 1000 + i * dur.tap * 1000, 6)
      expect(run.anim.id).toBe("clue-stamp")
    })
  })

  it("under reduced motion is the line's own 140 ms fade, like any clue", () => {
    stubReducedMotion(true)
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("Allah", 2)} />)

    expect(calls).toHaveLength(1)
    expect(calls[0].el).toBe(line(container))
    expect(calls[0].options).toMatchObject({ duration: CLUE_REDUCED_FADE_MS })
  })

  it("still writes an ordinary clue in", () => {
    const { container, rerender } = render(<ClueBanner turn={turn(null)} />)
    rerender(<ClueBanner turn={turn("knowledge", 2)} />)
    expect(callsOn(pen(container))).toHaveLength(1)
  })
})

describe("ClueBanner: the spymaster's own clue", () => {
  const composer = { clueWord: "", clueNumber: 1, isSubmitting: false, onClueWordChange: vi.fn(), onClueNumberChange: vi.fn(), onSubmit: vi.fn() }

  /** The page's order: the announcer first, then the composer or the banner. */
  function Table({ clue, composing }: { clue: string | null; composing: boolean }) {
    return (
      <>
        <ClueAnnouncer clueWord={clue} clueNumber={clue ? 2 : null} teamName="Red" />
        {composing ? <CluePanel {...composer} /> : <ClueBanner turn={turn(clue, 2)} />}
      </>
    )
  }

  it("writes in the clue the spymaster just gave: their banner mounts with it, as the composer goes", () => {
    // Prepare: the spymaster composes; no banner yet
    const { container, rerender } = render(<Table clue={null} composing />)
    expect(container.querySelector(".cn-clue")).toBeNull()

    // Act: the clue is on the table, the composer gives way to the banner in the same commit
    rerender(<Table clue="knowledge" composing={false} />)

    // Assert
    expect(callsOn(pen(container))).toHaveLength(1)
    expect(lozenges(container).flatMap((el) => callsOn(el))).toHaveLength(2)
  })

  it("still writes it under StrictMode, whose mount, unmount, mount cancels the first writing", () => {
    const { container, rerender } = render(
      <StrictMode>
        <Table clue={null} composing />
      </StrictMode>,
    )

    rerender(
      <StrictMode>
        <Table clue="knowledge" composing={false} />
      </StrictMode>,
    )

    // the last writing started is the one left running
    const penRuns = callsOn(pen(container))
    expect(penRuns.length).toBeGreaterThan(0)
    expect(penRuns.at(-1)?.anim.cancel).not.toHaveBeenCalled()
  })

  it("the page mounts the announcer before the banner, which this relies on", () => {
    const page = readFileSync(resolve(process.cwd(), "src/routes/_auth/game/codenames.$gameId.tsx"), "utf8")
    expect(page.indexOf("<ClueAnnouncer")).toBeGreaterThan(-1)
    expect(page.indexOf("<ClueAnnouncer")).toBeLessThan(page.indexOf("<ClueBanner"))
  })
})

describe("ClueBanner: the clue's face is ready before the clue", () => {
  let load: Mock

  beforeEach(() => {
    load = vi.fn(() => Promise.resolve([]))
    Object.defineProperty(document, "fonts", { configurable: true, value: { load } })
  })

  afterEach(() => {
    delete (document as { fonts?: unknown }).fonts
    ui.language = "en"
  })

  it("asks for Marcellus while the spymaster chooses, so a Latin clue is written in its own face", () => {
    render(<ClueBanner turn={turn(null)} />)
    expect(load).toHaveBeenCalledWith("400 1em Marcellus", "A")
  })

  it("asks for the hand too in the Arabic interface, where a clue is most likely Arabic", () => {
    ui.language = "ar-SA"
    render(<ClueBanner turn={turn(null)} />)
    expect(load).toHaveBeenCalledWith('700 1em "Aref Ruqaa"', "ب")
    expect(load).toHaveBeenCalledWith("400 1em Marcellus", "A")
    expect(load).toHaveBeenCalledTimes(2)
  })

  it("asks once per wait, not on every re-render while the spymaster chooses", () => {
    const { rerender } = render(<ClueBanner turn={turn(null)} spymasterName="Yusuf" />)
    rerender(<ClueBanner turn={turn(null)} spymasterName="Yusuf" />)
    expect(load).toHaveBeenCalledOnce()
  })

  it("asks for nothing when the page opens on a clue (it is set in its face already)", () => {
    render(<ClueBanner turn={turn("knowledge", 2)} />)
    expect(load).not.toHaveBeenCalled()
  })

  it("lives without the Font Loading API, and a face that cannot be fetched now is not an error", async () => {
    load.mockReturnValueOnce(Promise.reject(new Error("offline")))
    render(<ClueBanner turn={turn(null)} />)
    await Promise.resolve()
    delete (document as { fonts?: unknown }).fonts
    expect(() => render(<ClueBanner turn={turn(null)} />)).not.toThrow()
  })
})

describe("ClueBanner: the timing mirrors the stylesheet", () => {
  it("stamps for loz-stamp's 220 ms, and fades for the reduced ink's 140 ms", () => {
    const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8")
    expect(css).toContain(`--animate-loz-stamp: loz-stamp ${CLUE_STAMP_MS}ms var(--ease-press) both;`)
    expect(css).toMatch(new RegExp(`\\.ink \\{[^}]*animation: fade-in ${CLUE_REDUCED_FADE_MS}ms linear both;`))
  })
})

describe("writesRightToLeft", () => {
  it("follows the word's first strong letter, as dir=auto does", () => {
    expect(writesRightToLeft("knowledge")).toBe(false)
    expect(writesRightToLeft("صبر")).toBe(true)
    expect(writesRightToLeft("3صبر")).toBe(true)
    expect(writesRightToLeft("Ilmعلم")).toBe(false)
    expect(writesRightToLeft("42")).toBe(false)
  })
})
