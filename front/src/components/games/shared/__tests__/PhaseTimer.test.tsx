import { act, render, screen } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { PhaseTimer } from "../PhaseTimer"

describe("PhaseTimer", () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  /** An ISO start time `secondsAgo` in the past, captured once (the server value is stable). */
  function pastIso(secondsAgo: number) {
    return new Date(Date.now() - secondsAgo * 1000).toISOString()
  }

  /** Advance the 500ms display interval, flushing the state updates it causes. */
  function tick(ms: number) {
    act(() => {
      vi.advanceTimersByTime(ms)
    })
  }

  it("counts down from the server-provided start time", () => {
    render(<PhaseTimer timerStartedAt={pastIso(10)} durationSeconds={30} />)

    expect(screen.getByRole("timer")).toHaveAttribute("aria-label", "20s remaining")
  })

  it("shows the full duration when no start time is known yet", () => {
    render(<PhaseTimer timerStartedAt={null} durationSeconds={45} />)

    expect(screen.getByRole("timer")).toHaveAttribute("aria-label", "45s remaining")
  })

  it("fires onExpired once when the timer reaches zero", () => {
    const onExpired = vi.fn()
    render(<PhaseTimer timerStartedAt={pastIso(1)} durationSeconds={3} onExpired={onExpired} />)

    expect(onExpired).not.toHaveBeenCalled()

    tick(3_000)

    expect(onExpired).toHaveBeenCalledTimes(1)
  })

  it("does not re-fire onExpired on every tick while still expired", () => {
    const onExpired = vi.fn()
    render(<PhaseTimer timerStartedAt={pastIso(120)} durationSeconds={30} onExpired={onExpired} />)

    // Ten seconds of 500ms display ticks — the old effect re-ran on each of them.
    tick(10_000)

    expect(onExpired).toHaveBeenCalledTimes(1)
  })

  it("does not re-fire when the parent re-renders with a new callback identity", () => {
    // This is the loop that mattered in production: onExpired is a useCallback whose
    // deps include a React Query mutation object, which is a fresh object on every
    // render — and the handler itself invalidates queries, which re-renders the
    // parent. Each re-render used to re-arm the effect and fire another POST.
    const startedAt = pastIso(120)
    const calls: number[] = []
    const { rerender } = render(
      <PhaseTimer timerStartedAt={startedAt} durationSeconds={30} onExpired={() => calls.push(1)} />,
    )

    for (let i = 0; i < 8; i++) {
      rerender(<PhaseTimer timerStartedAt={startedAt} durationSeconds={30} onExpired={() => calls.push(1)} />)
      tick(500)
    }

    expect(calls).toHaveLength(1)
  })

  it("re-arms for a new timer window", () => {
    const onExpired = vi.fn()
    const firstWindow = pastIso(120)
    const { rerender } = render(
      <PhaseTimer timerStartedAt={firstWindow} durationSeconds={30} onExpired={onExpired} />,
    )
    tick(1_000)
    expect(onExpired).toHaveBeenCalledTimes(1)

    // The server moved the phase on and started a fresh timer, itself already elapsed.
    const secondWindow = pastIso(200)
    rerender(<PhaseTimer timerStartedAt={secondWindow} durationSeconds={30} onExpired={onExpired} />)
    tick(1_000)

    expect(onExpired).toHaveBeenCalledTimes(2)
  })
})
