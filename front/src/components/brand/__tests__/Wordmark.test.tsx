import { act, render } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { KASHIDA_FONT_WAIT_MS, KASHIDA_WOVEN_KEY, Wordmark } from "../Wordmark"

/**
 * The kashida woven once (DESIGN.md §7): the home's large مجلسنا weaves its madd band on
 * the first visit of a session, after the fonts are ready. The band, full length in the
 * kashida's own clipping box, is translated in from the right (Arabic reads right to left)
 * by ONE Web Animation on `transform`, 1100 ms on --ease-ink. The letters are there from the
 * first frame; only the band moves. Reduced motion: nothing moves. happy-dom has no Web
 * Animations, so `Element.animate` is a recording fake here.
 */

interface FakeAnimation {
  pause: Mock
  play: Mock
  cancel: Mock
}

interface AnimateCall {
  el: Element
  keyframes: Keyframe[]
  options: KeyframeAnimationOptions
  anim: FakeAnimation
}

let calls: AnimateCall[] = []
let fontsLoaded: () => void = () => {}

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
    })),
  )
}

function stubFonts() {
  const loaded = new Promise<void>((resolve) => {
    fontsLoaded = resolve
  })
  const fonts = { load: vi.fn(() => loaded.then(() => [])), ready: loaded.then(() => fonts) }
  Object.defineProperty(document, "fonts", { configurable: true, value: fonts })
  return fonts
}

const band = (container: HTMLElement) => container.querySelector(".madd > .k > .k-band")

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => setTimeout(() => cb(performance.now()), 16))
  vi.stubGlobal("cancelAnimationFrame", (id: number) => clearTimeout(id))
  stubReducedMotion(false)
  stubFonts()
  sessionStorage.clear()
  calls = []
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
      const anim: FakeAnimation = { pause: vi.fn(), play: vi.fn(), cancel: vi.fn() }
      calls.push({ el: this, keyframes, options, anim })
      return anim
    }),
  })
})

afterEach(() => {
  delete (HTMLElement.prototype as { animate?: unknown }).animate
  delete (document as { fonts?: unknown }).fonts
  sessionStorage.clear()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("Wordmark: the kashida woven once", () => {
  it("weaves the band in from the right after the fonts, on the compositor, once", async () => {
    // Act
    const { container } = render(<Wordmark size={200} woven weave label={null} />)

    // Assert: one animation of the band, held at its first frame while the fonts load
    expect(calls).toHaveLength(1)
    const [{ el, keyframes, options, anim }] = calls
    expect(el).toBe(band(container))
    // held 2 px past the clip's end: at exactly 100% a fractional width left a 1-device-pixel
    // madder sliver at the open joint while the face loads (review RM-5); the end is the rest
    expect(keyframes).toEqual([{ transform: "translateX(calc(100% + 2px))" }, { transform: "translateX(0)" }])
    expect(options).toMatchObject({ duration: 1100, easing: "cubic-bezier(0.45, 0.05, 0.2, 1)" })
    expect(anim.pause).toHaveBeenCalled()
    expect(anim.play).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(KASHIDA_WOVEN_KEY)).toBe("1")

    // Act: the face is there, then the next frame
    await act(async () => {
      fontsLoaded()
    })
    await act(async () => {
      vi.advanceTimersByTime(16)
    })

    // Assert
    expect(anim.play).toHaveBeenCalledTimes(1)
    expect(anim.cancel).not.toHaveBeenCalled()
  })

  it("has every letter from the first frame, the band hidden from assistive tech", () => {
    // Act
    const { container } = render(<Wordmark size={200} woven weave label="مجلسنا" />)

    // Assert
    const name = container.querySelector(".madd") as HTMLElement
    expect(name.textContent).toBe("مجلـ" + "ـسنا")
    expect(name).toHaveAttribute("aria-label", "مجلسنا")
    expect(band(container)?.closest("[aria-hidden='true']")).not.toBeNull()
  })

  it("weaves once per session: a second visit to the home leaves the band in place", () => {
    // Prepare
    const first = render(<Wordmark size={200} weave />)
    first.unmount()
    calls = []

    // Act
    render(<Wordmark size={200} weave />)

    // Assert
    expect(calls).toHaveLength(0)
  })

  it("moves nothing under reduced motion, and keeps the session's weave for later", () => {
    // Prepare
    stubReducedMotion(true)

    // Act
    render(<Wordmark size={200} weave />)

    // Assert
    expect(calls).toHaveLength(0)
    expect(sessionStorage.getItem(KASHIDA_WOVEN_KEY)).toBeNull()
  })

  it("moves nothing when the session cannot be remembered (a reload would weave again)", () => {
    // Prepare
    const blocked = () => {
      throw new Error("blocked")
    }
    vi.stubGlobal("sessionStorage", { getItem: blocked, setItem: blocked, removeItem: blocked, clear: () => {} })

    // Act
    render(<Wordmark size={200} weave />)

    // Assert
    expect(calls).toHaveLength(0)
  })

  it("moves nothing without `weave`: the auth page's name, the nav's lockup", () => {
    // Act
    render(
      <>
        <Wordmark size={120} />
        <Wordmark size={32} />
      </>,
    )

    // Assert
    expect(calls).toHaveLength(0)
    expect(sessionStorage.getItem(KASHIDA_WOVEN_KEY)).toBeNull()
  })

  it("never holds the band out longer than the fonts' wait: it weaves anyway", async () => {
    // Prepare
    render(<Wordmark size={200} weave />)
    const [{ anim }] = calls

    // Act: the face never arrives
    await act(async () => {
      vi.advanceTimersByTime(KASHIDA_FONT_WAIT_MS + 16)
    })

    // Assert
    expect(anim.play).toHaveBeenCalledTimes(1)
  })

  it("lets the band go back to its place when the page leaves before the weave", () => {
    // Prepare
    const { unmount } = render(<Wordmark size={200} weave />)
    const [{ anim }] = calls

    // Act
    unmount()

    // Assert
    expect(anim.cancel).toHaveBeenCalled()
  })

  it("moves nothing in a browser without Web Animations", () => {
    // Prepare
    delete (HTMLElement.prototype as { animate?: unknown }).animate

    // Act
    const { container } = render(<Wordmark size={200} weave />)

    // Assert
    expect(band(container)).not.toBeNull()
    expect(sessionStorage.getItem(KASHIDA_WOVEN_KEY)).toBeNull()
  })
})
