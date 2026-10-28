import { afterEach, describe, expect, it, vi } from "vitest"
import { hasReadRole, rememberReads, rememberRoleRead, storedReads } from "./undercover-session"

describe("undercover-session", () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    sessionStorage.clear()
  })

  it("keeps the first reading dismissed per game, across a reload of the tab", () => {
    expect(hasReadRole("g1")).toBe(false)
    rememberRoleRead("g1")
    expect(hasReadRole("g1")).toBe(true)
    expect(hasReadRole("g2")).toBe(false)
  })

  it("keeps the tablet's read count per game", () => {
    expect(storedReads("g1")).toBe(0)
    rememberReads("g1", 3)
    expect(storedReads("g1")).toBe(3)
    sessionStorage.setItem("uc-reads:g1", "nonsense")
    expect(storedReads("g1")).toBe(0)
  })

  it("degrades to nothing kept when storage is refused", () => {
    const denied = () => {
      throw new Error("denied")
    }
    vi.stubGlobal("sessionStorage", { getItem: denied, setItem: denied, removeItem: denied, clear: () => {} })
    expect(() => rememberRoleRead("g1")).not.toThrow()
    expect(hasReadRole("g1")).toBe(false)
    expect(() => rememberReads("g1", 2)).not.toThrow()
    expect(storedReads("g1")).toBe(0)
  })
})
