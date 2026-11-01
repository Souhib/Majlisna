import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { canViewTransition, useViewTransitionValue, withViewTransition } from "./view-transition"

/**
 * Phase crossfades (WP-18, F7 and F9): reduced motion keeps the crossfade (the CSS shortens it
 * to 120 ms with no group movement), and a page load (a value first arriving) never fades.
 */

let start: Mock

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
  // Like the browser: the update callback runs once the old state has been captured, after
  // the current task — never inside React's commit. A stub that called it synchronously
  // ran the hook's flushSync from its own effect, which React refuses ("flushSync was
  // called from inside a lifecycle method"), and could not show the old phase being held.
  start = vi.fn((update: () => void) => ({ finished: Promise.resolve().then(update) }))
  Object.defineProperty(document, "startViewTransition", { configurable: true, writable: true, value: start })
})

afterEach(() => {
  delete (document as { startViewTransition?: unknown }).startViewTransition
  vi.unstubAllGlobals()
})

describe("useViewTransitionValue", () => {
  it("crossfades a phase change", async () => {
    // Prepare
    stubReducedMotion(false)
    const { result, rerender } = renderHook(({ value }) => useViewTransitionValue(value), { initialProps: { value: "describing" } })

    // Act
    rerender({ value: "voting" })

    // Assert: the old phase stays on screen while the browser captures it...
    expect(start).toHaveBeenCalledTimes(1)
    expect(result.current).toBe("describing")
    // ...then the browser runs the update, and the new phase is rendered
    await act(async () => {})
    expect(result.current).toBe("voting")
  })

  it("still crossfades a phase change under reduced motion (the CSS shortens it)", async () => {
    // Prepare
    stubReducedMotion(true)
    const { result, rerender } = renderHook(({ value }) => useViewTransitionValue(value), { initialProps: { value: "describing" } })

    // Act
    rerender({ value: "voting" })
    await act(async () => {})

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(result.current).toBe("voting")
  })

  it("adopts the first real value at once, with no transition (a page load is not a phase change)", async () => {
    // Prepare: the quiz page while its state loads.
    stubReducedMotion(false)
    const { result, rerender } = renderHook(({ value }: { value: string | null }) => useViewTransitionValue(value), { initialProps: { value: null } })

    // Act: the state arrives.
    rerender({ value: "playing" })

    // Assert: shown in the same render, and no crossfade.
    expect(result.current).toBe("playing")
    expect(start).not.toHaveBeenCalled()

    // Act: the next phase is a real change.
    rerender({ value: "results" })
    await act(async () => {})

    // Assert
    expect(start).toHaveBeenCalledTimes(1)
    expect(result.current).toBe("results")
  })
})

describe("withViewTransition", () => {
  it("runs under reduced motion too", async () => {
    stubReducedMotion(true)
    const update = vi.fn()

    await withViewTransition(update)

    expect(canViewTransition()).toBe(true)
    expect(start).toHaveBeenCalledTimes(1)
    expect(update).toHaveBeenCalledTimes(1)
  })

  it("just runs the update where the browser has no view transitions", async () => {
    delete (document as { startViewTransition?: unknown }).startViewTransition
    const update = vi.fn()

    await withViewTransition(update)

    expect(canViewTransition()).toBe(false)
    expect(update).toHaveBeenCalledTimes(1)
  })
})
