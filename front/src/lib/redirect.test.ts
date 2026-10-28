import { describe, expect, it } from "vitest"
import { safeRedirect } from "./redirect"

describe("safeRedirect", () => {
  it("keeps a same-site path with its query", () => {
    expect(safeRedirect("/rooms/join?code=ABCDE&pin=1234")).toBe("/rooms/join?code=ABCDE&pin=1234")
  })

  it.each(["//evil.example", "https://evil.example", "/\\evil.example", "javascript:alert(1)", "rooms", ""])("rejects %s", (value) => {
    expect(safeRedirect(value)).toBeUndefined()
  })

  it("rejects non-strings", () => {
    expect(safeRedirect(undefined)).toBeUndefined()
    expect(safeRedirect(42)).toBeUndefined()
  })

  it("never redirects back into the auth pages", () => {
    expect(safeRedirect("/auth/login")).toBeUndefined()
  })
})
