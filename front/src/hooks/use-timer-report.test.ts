import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { isTimerNoOpAction, TIMER_REPORT_JITTER_MAX_MS, TIMER_REPORT_JITTER_MIN_MS, useTimerReport } from "./use-timer-report"

/**
 * BDP-03, the client half: every player's clock reported the end of a timed phase at the
 * same instant, so a 12-player table sent 12 POSTs (11 of them no-ops), each followed by
 * a refetch of the state, plus the 12 refetches the one real change caused.
 */
interface Props {
  isHost: boolean
  phaseKey: string
  windowKey: string | null
  paused?: boolean
}

function setup(initial: Props) {
  const send = vi.fn(async () => ({ action: "results" as string | undefined }))
  const onChanged = vi.fn()
  const hook = renderHook((props: Props) => useTimerReport({ ...props, paused: props.paused ?? false, send, onChanged }), { initialProps: initial })
  return { ...hook, send, onChanged }
}

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useTimerReport", () => {
  it("lets the host report at once", async () => {
    // Prepare
    const { result, send } = setup({ isHost: true, phaseKey: "playing:t0", windowKey: "t0" })

    // Act
    await act(() => result.current())

    // Assert
    expect(send).toHaveBeenCalledTimes(1)
  })

  it("makes everyone else wait a jittered 1 to 2 s, then report", async () => {
    // Prepare
    const { result, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })

    // Act
    await act(() => result.current())
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MIN_MS - 1))

    // Assert: nothing within the first second
    expect(send).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS - TIMER_REPORT_JITTER_MIN_MS + 1))
    expect(send).toHaveBeenCalledTimes(1)
  })

  it("does not POST when a game_updated (the phase moved on) arrives first", async () => {
    // Prepare: a non-host's clock ran out
    const { result, rerender, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })
    await act(() => result.current())
    await act(() => vi.advanceTimersByTimeAsync(500))

    // Act: the host's report landed; its game_updated brought the results phase
    rerender({ isHost: false, phaseKey: "results:t0", windowKey: "t0" })
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS * 2))

    // Assert
    expect(send).not.toHaveBeenCalled()
  })

  it("keeps a waiting report through a state change that does not end the phase", async () => {
    const { result, rerender, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })
    await act(() => result.current())

    // someone else's answer: same phase, same clock
    rerender({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS + 1))

    expect(send).toHaveBeenCalledTimes(1)
  })

  it("waits once per expiry, however often the clock says so", async () => {
    const { result, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })

    await act(() => result.current())
    await act(() => result.current())
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS + 1))

    expect(send).toHaveBeenCalledTimes(1)
  })

  it("refetches after an answer that changed the game, never after a no-op", async () => {
    // Prepare
    const { result, send, onChanged } = setup({ isHost: true, phaseKey: "playing:t0", windowKey: "t0" })
    send.mockResolvedValueOnce({ action: "not_playing" })

    // Act: a no-op
    await act(() => result.current())

    // Assert
    expect(onChanged).not.toHaveBeenCalled()
    send.mockResolvedValueOnce({ action: "results" })
    await act(() => result.current())
    expect(onChanged).toHaveBeenCalledTimes(1)
  })

  it("stops reporting a window the server answered a stop for, until a new one", async () => {
    const { result, rerender, send } = setup({ isHost: true, phaseKey: "playing:t0", windowKey: "t0" })
    send.mockResolvedValue({ action: "paused" })

    await act(() => result.current())
    await act(() => result.current())
    expect(send).toHaveBeenCalledTimes(1)

    rerender({ isHost: true, phaseKey: "playing:t1", windowKey: "t1" })
    await act(() => result.current())
    expect(send).toHaveBeenCalledTimes(2)
  })

  it("sends nothing while paused, nor a report that was waiting when the pause came", async () => {
    const { result, rerender, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })
    await act(() => result.current())

    rerender({ isHost: false, phaseKey: "playing:t0", windowKey: "t0", paused: true })
    await act(() => vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS + 1))
    await act(() => result.current())

    expect(send).not.toHaveBeenCalled()
  })

  it("drops a waiting report when the page goes away", async () => {
    const { result, unmount, send } = setup({ isHost: false, phaseKey: "playing:t0", windowKey: "t0" })
    await act(() => result.current())

    unmount()
    await vi.advanceTimersByTimeAsync(TIMER_REPORT_JITTER_MAX_MS + 1)

    expect(send).not.toHaveBeenCalled()
  })
})

describe("isTimerNoOpAction", () => {
  it.each(["paused", "timer_not_expired", "not_playing", "round_already_resolved", "none"])("calls %s a no-op", (action) => {
    expect(isTimerNoOpAction(action)).toBe(true)
  })

  it.each(["results", "auto_end_turn", "skip_to_voting", "auto_vote", "mr_white_guess_timeout"])("calls %s a change", (action) => {
    expect(isTimerNoOpAction(action)).toBe(false)
  })

  it("calls a missing answer a change (refetch, to be safe)", () => {
    expect(isTimerNoOpAction(undefined)).toBe(false)
  })
})
