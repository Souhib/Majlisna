import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it } from "vitest"
import { usePhaseFocus } from "./use-phase-focus"

/**
 * F2: every phase change dropped focus to <body>, so a keyboard player's next Tab
 * restarted at the skip link. The hook moves it to the new phase's title, but only when
 * nobody is using it for something else (typing, the chat, the nav).
 */
let region: HTMLDivElement
let outside: HTMLInputElement

function mountRegion(html: string) {
  region.innerHTML = html
}

beforeEach(() => {
  region = document.createElement("div")
  outside = document.createElement("input")
  document.body.append(region, outside)
})

afterEach(() => {
  region.remove()
  outside.remove()
})

function renderPhase(initial: string | null, options?: Parameters<typeof usePhaseFocus>[2]) {
  const ref = { current: region }
  return renderHook(({ phase }) => usePhaseFocus(phase, ref, options), { initialProps: { phase: initial } })
}

describe("usePhaseFocus", () => {
  it("moves focus from <body> to the new phase's h2, without scrolling", () => {
    // Prepare
    mountRegion("<h1>The Quiz</h1><h2>Question one</h2>")
    const { rerender } = renderPhase("playing")
    ;(document.activeElement as HTMLElement | null)?.blur()
    mountRegion("<h1>The Quiz</h1><h2>The answer</h2>")

    // Act
    act(() => rerender({ phase: "results" }))

    // Assert
    const title = region.querySelector("h2") as HTMLElement
    expect(document.activeElement).toBe(title)
    expect(title.getAttribute("tabindex")).toBe("-1")
  })

  it("leaves a player typing in an input alone", () => {
    // Prepare: the answer field keeps focus (an input in the game itself)
    mountRegion('<h2>Round 2</h2><input aria-label="answer" />')
    const { rerender } = renderPhase("results")
    const field = region.querySelector("input") as HTMLInputElement
    field.focus()

    // Act
    act(() => rerender({ phase: "playing" }))

    // Assert
    expect(document.activeElement).toBe(field)
  })

  it("leaves focus that is outside the game region alone (the chat, the nav)", () => {
    mountRegion("<h2>Vote</h2>")
    const { rerender } = renderPhase("describing")
    outside.focus()

    act(() => rerender({ phase: "playing" }))

    expect(document.activeElement).toBe(outside)
  })

  it("takes focus from a button inside the game (the one just pressed)", () => {
    mountRegion('<button type="button">Lock in</button><h2>The answer</h2>')
    const { rerender } = renderPhase("playing")
    const button = region.querySelector("button") as HTMLButtonElement
    button.focus()

    act(() => rerender({ phase: "results" }))

    expect(document.activeElement).toBe(region.querySelector("h2"))
  })

  it("never moves focus on the first render, nor when the page's first state arrives", () => {
    mountRegion("<h2>Question one</h2>")
    const { rerender } = renderPhase(null)
    expect(document.activeElement).toBe(document.body)

    // the loading state (null) gives way to the game: a page load, not a phase change
    act(() => rerender({ phase: "playing" }))

    expect(document.activeElement).toBe(document.body)
  })

  it("focuses the target the page names for that phase", () => {
    mountRegion('<h2>Question</h2><h3>Explanation</h3><p data-colophon-title="">Game over</p>')
    const { rerender } = renderPhase("playing", { targets: { results: "h3", game_over: "[data-colophon-title]" } })

    act(() => rerender({ phase: "results" }))
    expect(document.activeElement).toBe(region.querySelector("h3"))

    ;(document.activeElement as HTMLElement).blur()
    act(() => rerender({ phase: "game_over" }))
    expect(document.activeElement).toBe(region.querySelector("[data-colophon-title]"))
  })

  it("does nothing when the phase has no target", () => {
    mountRegion("<p>No heading here</p>")
    const { rerender } = renderPhase("playing")

    act(() => rerender({ phase: "results" }))

    expect(document.activeElement).toBe(document.body)
  })
})
