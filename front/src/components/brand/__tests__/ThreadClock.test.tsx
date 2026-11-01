import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { PhaseTimer } from "@/components/games/shared/PhaseTimer"
import { resetServerClock } from "@/lib/server-clock"
import { THREAD_ANIMATION_ID, ThreadClock } from "../ThreadClock"

/**
 * The loom clock (WP-18, F1/FP-04/I1): the thread is full length and is drawn back
 * through the loom at the reading start by ONE Web Animation on `transform` per phase
 * segment, never by a `width` transition re-rendered twice a second. happy-dom has no
 * Web Animations, so `Element.animate` is a recording fake here.
 */

interface FakeAnimation {
  id: string
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

const NOW = new Date("2026-10-31T12:00:00.000Z").getTime()

/** translateX(…%) → the number of percent. */
function shift(keyframe: Keyframe): number {
  const match = /^translateX\((-?[\d.]+)%\)$/.exec(String(keyframe.transform))
  if (!match) throw new Error(`not a translateX keyframe: ${String(keyframe.transform)}`)
  return Number(match[1])
}

function thread(container: HTMLElement) {
  return container.querySelector(".thread-clock .track > i") as HTMLElement
}

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

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
  resetServerClock()
  calls = []
  Object.defineProperty(HTMLElement.prototype, "animate", {
    configurable: true,
    writable: true,
    value: vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
      const anim: FakeAnimation = { id: "", pause: vi.fn(), play: vi.fn(), cancel: vi.fn() }
      calls.push({ el: this, keyframes, options, anim })
      return anim
    }),
  })
})

afterEach(() => {
  delete (HTMLElement.prototype as { animate?: unknown }).animate
  vi.unstubAllGlobals()
  vi.useRealTimers()
  document.documentElement.removeAttribute("dir")
})

describe("ThreadClock, the loom", () => {
  it("runs the thread as one linear transform animation from the server's start to five seconds left", () => {
    // Prepare: a 60 s phase that started 10 s ago on the server's clock.
    const startedAt = NOW - 10_000

    // Act
    const { container } = render(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} />)

    // Assert: one animation, on the thread, from 50/60 left to 5/60 left, over the 45 s between.
    expect(calls).toHaveLength(1)
    const [call] = calls
    expect(call.el).toBe(thread(container))
    expect(call.keyframes).toHaveLength(2)
    expect(shift(call.keyframes[0])).toBeCloseTo(-(1 - 50 / 60) * 100, 2)
    expect(shift(call.keyframes[1])).toBeCloseTo(-(1 - 5 / 60) * 100, 2)
    expect(call.options).toMatchObject({ duration: 45_000, easing: "linear", fill: "forwards" })
    // named: it lasts the whole phase, so a test settling the page's animations skips it
    expect(call.anim.id).toBe(THREAD_ANIMATION_ID)
  })

  it("is not restarted by the once-a-second ticks of the figures", () => {
    const startedAt = NOW - 10_000
    const { rerender } = render(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} />)

    for (const remaining of [49, 48, 47, 46]) rerender(<ThreadClock remaining={remaining} total={60} startedAt={startedAt} durationMs={60_000} />)

    expect(calls).toHaveLength(1)
    expect(calls[0].anim.cancel).not.toHaveBeenCalled()
    expect(screen.getByRole("timer")).toHaveTextContent("0:46")
  })

  it("never writes width, on the thread or in its keyframes", () => {
    const startedAt = NOW - 10_000
    const { container, rerender } = render(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} />)
    rerender(<ThreadClock remaining={49} total={60} startedAt={startedAt} durationMs={60_000} />)

    const el = thread(container)
    expect(el.style.width).toBe("")
    expect(screen.getByRole("timer").style.width).toBe("")
    for (const call of calls) for (const keyframe of call.keyframes) expect(Object.keys(keyframe)).toEqual(["transform"])
  })

  it("pauses the same animation for the prayer and plays it on resume", () => {
    // Prepare
    const startedAt = NOW - 10_000
    const { rerender } = render(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} />)
    const { anim } = calls[0]

    // Act: the host pauses for the adhan.
    rerender(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} paused />)

    // Assert: paused, not restarted.
    expect(anim.pause).toHaveBeenCalledTimes(1)
    expect(anim.cancel).not.toHaveBeenCalled()
    expect(calls).toHaveLength(1)

    // Act: resumed (before the server's shifted start arrives).
    rerender(<ThreadClock remaining={50} total={60} startedAt={startedAt} durationMs={60_000} />)

    // Assert
    expect(anim.play).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(1)
  })

  it("starts a new segment when the start or the duration changes", () => {
    // Prepare
    const { rerender } = render(<ThreadClock remaining={50} total={60} startedAt={NOW - 10_000} durationMs={60_000} />)

    // Act: the server moved the start forward by the pause (40 s later, 10 s elapsed still).
    vi.setSystemTime(NOW + 40_000)
    rerender(<ThreadClock remaining={50} total={60} startedAt={NOW + 30_000} durationMs={60_000} />)

    // Assert: the old segment is cancelled and a new one starts where the server says.
    expect(calls).toHaveLength(2)
    expect(calls[0].anim.cancel).toHaveBeenCalledTimes(1)
    expect(shift(calls[1].keyframes[0])).toBeCloseTo(-(1 - 50 / 60) * 100, 2)
    expect(calls[1].options.duration).toBe(45_000)

    // Act: a new duration (a different phase length).
    rerender(<ThreadClock remaining={50} total={90} startedAt={NOW + 30_000} durationMs={90_000} />)

    // Assert
    expect(calls).toHaveLength(3)
    expect(calls[2].options.duration).toBe(75_000)
  })

  it("is mirrored in Arabic: the thread is drawn back toward the right", () => {
    document.documentElement.setAttribute("dir", "rtl")

    render(<ThreadClock remaining={50} total={60} startedAt={NOW - 10_000} durationMs={60_000} />)

    expect(calls).toHaveLength(1)
    expect(shift(calls[0].keyframes[0])).toBeCloseTo((1 - 50 / 60) * 100, 2)
    expect(shift(calls[0].keyframes[1])).toBeCloseTo((1 - 5 / 60) * 100, 2)
  })

  it("leaves the thread to the 14 px stub and the stamped lozenges in the last five seconds", () => {
    // Prepare
    const startedAt = NOW - 10_000
    const { rerender } = render(<ThreadClock remaining={6} total={60} startedAt={startedAt} durationMs={60_000} />)
    const timer = screen.getByRole("timer")

    // Act
    vi.setSystemTime(NOW + 45_000)
    rerender(<ThreadClock remaining={5} total={60} startedAt={startedAt} durationMs={60_000} />)

    // Assert: the running animation is gone (the CSS stub takes over), the lozenges stand.
    expect(calls[0].anim.cancel).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(1)
    expect(timer).toHaveAttribute("data-phase", "last")
    expect(timer.querySelectorAll(".lozenges > i")).toHaveLength(5)
  })

  it("does not animate a clock that is already in its last five seconds", () => {
    render(<ThreadClock remaining={4} total={60} startedAt={NOW - 56_000} durationMs={60_000} />)

    expect(calls).toHaveLength(0)
    expect(screen.getByRole("timer")).toHaveAttribute("data-phase", "last")
  })

  it("under reduced motion, does not animate and steps the thread once a second", () => {
    // Prepare
    stubReducedMotion(true)
    const startedAt = NOW - 15_000

    // Act
    const { rerender } = render(<ThreadClock remaining={45} total={60} startedAt={startedAt} durationMs={60_000} />)
    const timer = screen.getByRole("timer")
    const first = timer.style.getPropertyValue("--left")
    rerender(<ThreadClock remaining={44} total={60} startedAt={startedAt} durationMs={60_000} />)

    // Assert: no Web Animation; the step comes from --left, which moves with each second.
    expect(calls).toHaveLength(0)
    expect(first).toBe("0.75")
    expect(timer.style.getPropertyValue("--left")).toBe(String(44 / 60))
  })

  it("keeps the remaining/total props working on their own (a static clock steps, never animates)", () => {
    render(<ThreadClock remaining={45} total={60} />)

    const timer = screen.getByRole("timer")
    expect(calls).toHaveLength(0)
    expect(timer).toHaveAttribute("data-phase", "running")
    expect(timer.style.getPropertyValue("--left")).toBe("0.75")
  })

  it("mounted during a pause, places the thread at the frozen countdown and holds it", () => {
    // Prepare: a reload during the prayer. The server's start is stale (it moves on resume).
    // Act
    render(<ThreadClock remaining={25} total={30} startedAt={NOW - 600_000} durationMs={30_000} paused />)

    // Assert
    expect(calls).toHaveLength(1)
    expect(shift(calls[0].keyframes[0])).toBeCloseTo(-(1 - 25 / 30) * 100, 2)
    expect(calls[0].options.duration).toBe(20_000)
    expect(calls[0].anim.pause).toHaveBeenCalledTimes(1)
  })
})

describe("PhaseTimer drives the loom", () => {
  function pastIso(secondsAgo: number) {
    return new Date(Date.now() - secondsAgo * 1000).toISOString()
  }

  function tick(ms: number) {
    act(() => {
      vi.advanceTimersByTime(ms)
    })
  }

  it("passes the server's start and the duration: one segment for the whole phase", () => {
    // Prepare
    const { container } = render(<PhaseTimer timerStartedAt={pastIso(10)} durationSeconds={30} />)

    // Act: three seconds of ticks.
    tick(3_000)

    // Assert
    expect(calls).toHaveLength(1)
    expect(calls[0].el).toBe(thread(container))
    expect(shift(calls[0].keyframes[0])).toBeCloseTo(-(1 - 20 / 30) * 100, 2)
    expect(shift(calls[0].keyframes[1])).toBeCloseTo(-(1 - 5 / 30) * 100, 2)
    expect(calls[0].options.duration).toBe(15_000)
    expect(screen.getByRole("timer")).toHaveTextContent("0:17")
  })

  it("freezes the thread exactly for the prayer pause and continues on resume", () => {
    // Prepare
    const { rerender } = render(<PhaseTimer timerStartedAt={pastIso(10)} durationSeconds={30} />)
    const { anim } = calls[0]

    // Act: paused with 20 s left; a minute of prayer passes.
    rerender(<PhaseTimer timerStartedAt={pastIso(10)} durationSeconds={30} paused frozenRemaining={20} />)
    tick(60_000)

    // Assert: the same animation is paused, never re-created while paused.
    expect(anim.pause).toHaveBeenCalledTimes(1)
    expect(calls).toHaveLength(1)
    expect(screen.getByRole("timer")).toHaveTextContent("0:20")

    // Act: resume; the server shifted the start by the pause (still 10 s into the phase).
    rerender(<PhaseTimer timerStartedAt={pastIso(10)} durationSeconds={30} />)

    // Assert: a new segment from the same place, 20 s left.
    expect(calls).toHaveLength(2)
    expect(anim.cancel).toHaveBeenCalledTimes(1)
    expect(shift(calls[1].keyframes[0])).toBeCloseTo(-(1 - 20 / 30) * 100, 2)
    expect(calls[1].options.duration).toBe(15_000)
  })
})

describe("ThreadClock, the CSS", () => {
  // vitest runs with `css: false`, so a `?raw` import of a stylesheet is empty: read the file.
  const css = readFileSync(resolve(process.cwd(), "src/styles/brand.css"), "utf8")

  /** One CSS rule's body, by its exact selector. */
  function rule(selector: string) {
    const at = css.indexOf(`${selector} {`)
    if (at < 0) return null
    return css.slice(at + selector.length + 2, css.indexOf("}", at))
  }

  it("never sizes or transitions the thread: it is full length, placed by a transform", () => {
    const thread = rule(".thread-clock .track > i") ?? ""
    expect(thread).not.toMatch(/width|transition/)
    expect(thread).toMatch(/transform: translateX\(calc\(\(var\(--left, 1\) - 1\) \* 100%\)\);/)
    expect(rule(".thread-clock .track")).toMatch(/overflow: hidden;/)
    expect(rule('[dir="rtl"] .thread-clock .track > i')).toMatch(/transform: translateX\(calc\(\(1 - var\(--left, 1\)\) \* 100%\)\);/)
  })

  it("keeps the 14 px stub for the last five seconds, from the reading start", () => {
    expect(rule('.thread-clock[data-phase="last"] .track > i')).toMatch(/transform: translateX\(calc\(14px - 100%\)\);/)
    expect(rule('[dir="rtl"] .thread-clock[data-phase="last"] .track > i')).toMatch(/transform: translateX\(calc\(100% - 14px\)\);/)
    expect(rule('.thread-clock[data-phase="last"] .track > i')).not.toMatch(/width|transition/)
  })
})
