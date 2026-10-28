import { describe, expect, it } from "vitest"
import type { GamePause } from "@/api/generated"
import { elapsedAtPause, formatWallClock, isGamePausedError, isTimerStopAction, msUntilAnyoneCanResume } from "../pause-utils"

const pause: GamePause = {
  by_user_id: "h",
  by_username: "Yusuf",
  since: "2026-10-28T15:00:00Z",
  reason: "salah",
  remaining_seconds: 42,
  paused_for_seconds: 600,
  anyone_can_resume_at: "2026-10-28T15:45:00Z",
}

describe("pause-utils", () => {
  it("treats 'paused' and 'round_already_resolved' as stop, nothing else", () => {
    expect(isTimerStopAction("paused")).toBe(true)
    expect(isTimerStopAction("round_already_resolved")).toBe(true)
    expect(isTimerStopAction("timer_not_expired")).toBe(false)
    expect(isTimerStopAction("auto_vote")).toBe(false)
    expect(isTimerStopAction(undefined)).toBe(false)
  })

  it("recognises the 409 a move gets while the game is paused", () => {
    expect(isGamePausedError({ response: { status: 409, data: { error_key: "errors.api.gamePaused" } } })).toBe(true)
    expect(isGamePausedError({ response: { status: 409, data: { error_key: "errors.api.gameAlreadyPaused" } } })).toBe(false)
    expect(isGamePausedError({ response: { status: 400, data: { error_key: "errors.api.gamePaused" } } })).toBe(false)
    expect(isGamePausedError(new Error("network"))).toBe(false)
    expect(isGamePausedError(null)).toBe(false)
  })

  it("reads how far into a timed phase the pause came from the server's frozen countdown", () => {
    expect(elapsedAtPause(pause, 60)).toBe(18)
    expect(elapsedAtPause({ ...pause, remaining_seconds: null }, 60)).toBeNull()
    expect(elapsedAtPause(pause, 0)).toBeNull()
    expect(elapsedAtPause(null, 60)).toBeNull()
  })

  it("writes wall-clock times in 24 h with Western digits", () => {
    expect(formatWallClock("2026-10-28T15:45:00Z")).toMatch(/^\d{2}:\d{2}$/)
    expect(formatWallClock("not a date")).toBe("")
  })

  it("measures the wait for 'anyone may resume' on the server's clock", () => {
    // 45 min after the pause, 10 min of which have passed: 35 min to go
    expect(msUntilAnyoneCanResume(pause)).toBe(35 * 60_000)
    expect(msUntilAnyoneCanResume({ ...pause, paused_for_seconds: 46 * 60 })).toBeNull()
  })
})
