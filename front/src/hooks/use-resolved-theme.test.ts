import { act, renderHook } from "@testing-library/react"
import { flushSync } from "react-dom"
import { beforeEach, describe, expect, it } from "vitest"
import { announceResolvedTheme, useResolvedTheme } from "./use-resolved-theme"

/**
 * The light on screen, read from <html data-theme>. The sky's turn (ThemeProvider) writes
 * the attribute inside a view transition's update: every reader must have re-rendered
 * before that update returns, or the browser captures the new state with the old title
 * and the old sky (a MutationObserver only answers one microtask later).
 */
beforeEach(() => {
  document.documentElement.dataset.theme = "dark"
})

describe("useResolvedTheme", () => {
  it("reads the light from <html data-theme>", () => {
    // Prepare
    document.documentElement.dataset.theme = "light"

    // Act
    const { result } = renderHook(() => useResolvedTheme())

    // Assert
    expect(result.current).toBe("light")
  })

  it("re-renders in the same task when the light is announced, inside flushSync", () => {
    // Prepare
    document.documentElement.dataset.theme = "dark"
    const { result } = renderHook(() => useResolvedTheme())
    let seenInsideUpdate: string | null = null

    // Act: what a view transition's update does
    act(() => {
      flushSync(() => {
        document.documentElement.dataset.theme = "light"
        announceResolvedTheme()
      })
      seenInsideUpdate = result.current
    })

    // Assert
    expect(seenInsideUpdate).toBe("light")
  })

  it("still follows a change nobody announced (another writer of the attribute)", async () => {
    // Prepare
    document.documentElement.dataset.theme = "dark"
    const { result } = renderHook(() => useResolvedTheme())

    // Act
    await act(async () => {
      document.documentElement.dataset.theme = "light"
    })

    // Assert
    expect(result.current).toBe("light")
  })
})
