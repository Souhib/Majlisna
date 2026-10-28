import { afterEach, describe, expect, it, vi } from "vitest"
import { noteServerDate, resetServerClock, serverNow } from "./server-clock"

const at = (iso: string) => new Date(iso).toUTCString()

describe("server clock", () => {
  afterEach(() => {
    resetServerClock()
    vi.useRealTimers()
  })

  it("is the device clock until a response says otherwise", () => {
    vi.useFakeTimers({ now: new Date("2026-10-28T20:00:00Z") })
    expect(serverNow()).toBe(Date.now())
  })

  it("corrects a device clock 3 s ahead, so a rung is never crossed before the server", () => {
    // device reads 20:00:03.400 while the server stamps 20:00:00 (its clock: 20:00:00.4)
    vi.useFakeTimers({ now: new Date("2026-10-28T20:00:03.400Z") })
    noteServerDate(at("2026-10-28T20:00:00Z"))
    const server = new Date("2026-10-28T20:00:00.400Z").getTime()
    expect(serverNow()).toBeLessThanOrEqual(server)
    expect(server - serverNow()).toBeLessThan(1000)
  })

  it("corrects a device clock behind the server too", () => {
    vi.useFakeTimers({ now: new Date("2026-10-28T19:59:55.000Z") })
    noteServerDate(at("2026-10-28T20:00:00Z"))
    expect(serverNow()).toBe(new Date("2026-10-28T20:00:00Z").getTime())
  })

  it("keeps the tightest bound: a sample stamped earlier in its second does not pull it back", () => {
    vi.useFakeTimers({ now: new Date("2026-10-28T20:00:00.900Z") })
    noteServerDate(at("2026-10-28T20:00:00Z")) // bound -900 ms
    vi.setSystemTime(new Date("2026-10-28T20:00:01.100Z"))
    noteServerDate(at("2026-10-28T20:00:01Z")) // bound -100 ms: tighter, kept
    vi.setSystemTime(new Date("2026-10-28T20:00:02.800Z"))
    noteServerDate(at("2026-10-28T20:00:02Z")) // bound -800 ms: looser, ignored
    expect(serverNow()).toBe(Date.now() - 100)
  })

  it("starts again when the device clock is changed by hand", () => {
    vi.useFakeTimers({ now: new Date("2026-10-28T20:00:00Z") })
    noteServerDate(at("2026-10-28T20:00:10Z")) // device 10 s behind
    noteServerDate(at("2026-10-28T20:00:00Z")) // the device was set right: bound 0, 10 s looser
    expect(serverNow()).toBe(Date.now())
  })

  it("ignores a missing or unreadable header", () => {
    vi.useFakeTimers({ now: new Date("2026-10-28T20:00:00Z") })
    noteServerDate(null)
    noteServerDate("not a date")
    expect(serverNow()).toBe(Date.now())
  })
})
