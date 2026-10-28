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

    const timer = screen.getByRole("timer")
    // named, then the time (i18n is not initialised in unit tests: the key is the label)
    expect(timer).toHaveAttribute("aria-label", "ui.clock.label: 0:20")
    expect(timer).toHaveTextContent("0:20")
  })

  it("shows the full duration when no start time is known yet", () => {
    render(<PhaseTimer timerStartedAt={null} durationSeconds={45} />)

    expect(screen.getByRole("timer")).toHaveAttribute("aria-label", "ui.clock.label: 0:45")
  })

  it("draws the running thread at the fraction of time left", () => {
    render(<PhaseTimer timerStartedAt={pastIso(15)} durationSeconds={60} />)

    const timer = screen.getByRole("timer")
    expect(timer).toHaveAttribute("data-phase", "running")
    expect(timer.style.getPropertyValue("--left")).toBe("0.75")
    // No lozenges and no knot while the thread still runs.
    expect(timer.querySelectorAll(".lozenges > i")).toHaveLength(0)
    expect(timer.querySelector(".knot")).toBeNull()
  })

  it("stamps one brass lozenge per second in the last five seconds", () => {
    render(<PhaseTimer timerStartedAt={pastIso(27)} durationSeconds={30} />)

    const timer = screen.getByRole("timer")
    expect(timer).toHaveAttribute("data-phase", "last")
    const lozenges = timer.querySelectorAll(".lozenges > i")
    expect(lozenges).toHaveLength(5)
    // 3 seconds left: 2 of the 5 beats are stamped.
    expect(timer.querySelectorAll('.lozenges > i[data-on="true"]')).toHaveLength(2)
  })

  it("knots the thread at zero and never turns red", () => {
    render(<PhaseTimer timerStartedAt={pastIso(120)} durationSeconds={30} />)

    const timer = screen.getByRole("timer")
    expect(timer).toHaveAttribute("data-phase", "done")
    expect(timer).toHaveTextContent("0:00")
    expect(timer.querySelector(".knot")).not.toBeNull()
    expect(timer.querySelectorAll('.lozenges > i[data-on="true"]')).toHaveLength(5)
    expect(timer.innerHTML).not.toMatch(/red|destructive|ember|pulse/)
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

  describe("the prayer pause", () => {
    it("stands still at the server's frozen countdown while paused", () => {
      // Prepare: the server froze the clock with 25 s left; the local start time is stale.
      render(<PhaseTimer timerStartedAt={pastIso(40)} durationSeconds={30} paused frozenRemaining={25} />)
      const timer = screen.getByRole("timer")
      expect(timer).toHaveTextContent("0:25")

      // Act: a minute passes on this device.
      tick(60_000)

      // Assert: nothing moved, and the thread is drawn at the frozen fraction.
      expect(timer).toHaveTextContent("0:25")
      expect(timer).toHaveAttribute("data-phase", "running")
      expect(timer.style.getPropertyValue("--left")).toBe(String(25 / 30))
    })

    it("never fires onExpired while paused, even long past the old deadline", () => {
      const onExpired = vi.fn()
      render(<PhaseTimer timerStartedAt={pastIso(120)} durationSeconds={30} onExpired={onExpired} paused frozenRemaining={0} />)

      tick(30_000)

      expect(onExpired).not.toHaveBeenCalled()
    })

    it("keeps the time it last showed when the server gives no frozen value", () => {
      const startedAt = pastIso(10)
      const { rerender } = render(<PhaseTimer timerStartedAt={startedAt} durationSeconds={30} />)
      expect(screen.getByRole("timer")).toHaveTextContent("0:20")

      rerender(<PhaseTimer timerStartedAt={startedAt} durationSeconds={30} paused />)
      tick(15_000)

      expect(screen.getByRole("timer")).toHaveTextContent("0:20")
    })

    it("continues from the frozen value on resume (the server moved the start forward)", () => {
      const onExpired = vi.fn()
      const { rerender } = render(
        <PhaseTimer timerStartedAt={pastIso(600)} durationSeconds={30} onExpired={onExpired} paused frozenRemaining={25} />,
      )
      tick(5_000)

      // Resume: the anchor is shifted by the paused duration, 5 s into the 30 s phase.
      rerender(<PhaseTimer timerStartedAt={pastIso(5)} durationSeconds={30} onExpired={onExpired} />)
      expect(screen.getByRole("timer")).toHaveTextContent("0:25")
      tick(1_000)
      expect(screen.getByRole("timer")).toHaveTextContent("0:24")

      // ...and it still fires once when it really runs out.
      tick(25_000)
      expect(onExpired).toHaveBeenCalledTimes(1)
    })
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
