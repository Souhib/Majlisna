import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { AdhanSuggestion } from "../AdhanSuggestion"
import { PauseControl } from "../PauseControl"

// react-i18next is mocked by the setup file: names are the keys.

describe("PauseControl (the header's pause / resume)", () => {
  it("offers the host Pause while the game runs, by its full name", () => {
    const onPause = vi.fn()
    render(<PauseControl canPause canResume={false} paused={false} onPause={onPause} onResume={vi.fn()} />)

    const button = screen.getByRole("button", { name: "pause.pauseLabel" })
    expect(button).toHaveTextContent("pause.pause")
    fireEvent.click(button)
    expect(onPause).toHaveBeenCalledTimes(1)
  })

  it("shows nothing to a player who cannot pause", () => {
    const { container } = render(<PauseControl canPause={false} canResume={false} paused={false} onPause={vi.fn()} onResume={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("leaves Resume to the veil while paused, even for whoever may resume", () => {
    // the header's own Resume showed through the veil as an unpressable ghost of the real one
    const { container } = render(<PauseControl canPause={false} canResume paused onPause={vi.fn()} onResume={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("shows nothing while paused to whoever may not resume", () => {
    const { container } = render(<PauseControl canPause={false} canResume={false} paused onPause={vi.fn()} onResume={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it("never offers Pause on a paused game, even to the host", () => {
    // the server answers can_pause=false while paused; a stale true must not show Pause
    render(<PauseControl canPause canResume={false} paused onPause={vi.fn()} onResume={vi.fn()} />)

    expect(screen.queryByRole("button")).toBeNull()
  })

  it("keeps its label while the request runs (busy, not gone)", () => {
    render(<PauseControl canPause canResume={false} paused={false} onPause={vi.fn()} onResume={vi.fn()} pending />)

    expect(screen.getByRole("button", { name: "pause.pauseLabel" })).toHaveAttribute("aria-busy", "true")
  })
})

describe("AdhanSuggestion (the host's strip)", () => {
  it("names the prayer and offers Pause or Not now, without taking focus", () => {
    const onPause = vi.fn()
    const onDismiss = vi.fn()
    render(<AdhanSuggestion prayerKey="asr" onPause={onPause} onDismiss={onDismiss} />)

    const strip = screen.getByRole("region", { name: "pause.suggestLabel" })
    expect(strip).toHaveTextContent("pause.suggest")
    expect(strip).not.toContainElement(document.activeElement as HTMLElement)

    fireEvent.click(screen.getByRole("button", { name: "pause.suggestPause" }))
    fireEvent.click(screen.getByRole("button", { name: "pause.notNow" }))
    expect(onPause).toHaveBeenCalledTimes(1)
    expect(onDismiss).toHaveBeenCalledTimes(1)
  })
})
