import { describe, expect, it, vi } from "vitest"
import { isRefusal, joinRepairFor, retryUnlessRefused, ROOM_ERROR_KEYS, roomErrorKey, roomErrorMessage } from "./errors"

vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { frontend_message?: string } } }, fallback: string) => err.response?.data?.frontend_message ?? fallback,
}))

/** An error as the ky client throws it: the response, with its parsed body as `data`. */
const answered = (status: number, data: unknown = {}) => Object.assign(new Error(`HTTP ${status}`), { response: { status, data } })

describe("roomErrorMessage", () => {
  it("uses the server's message when the server answered", () => {
    const err = { response: { data: { frontend_message: "Room not found." } } }
    expect(roomErrorMessage(err, "fallback")).toBe("Room not found.")
  })

  it("never shows a transport error to the player", () => {
    expect(roomErrorMessage(new Error("Request timed out: PATCH http://x/api/v1/rooms/join"), "fallback")).toBe("fallback")
    expect(roomErrorMessage(undefined, "fallback")).toBe("fallback")
  })
})

describe("roomErrorKey", () => {
  it("reads the server's error key", () => {
    expect(roomErrorKey(answered(409, { error_key: "errors.api.userAlreadyInRoom" }))).toBe(ROOM_ERROR_KEYS.alreadyInRoom)
    expect(roomErrorKey(answered(403, { error_key: "errors.api.roomBanned" }))).toBe(ROOM_ERROR_KEYS.banned)
    expect(roomErrorKey(answered(403, { error_key: "errors.api.inviteeBanned" }))).toBe(ROOM_ERROR_KEYS.inviteeBanned)
  })

  it("has none for a transport error or a body without one", () => {
    expect(roomErrorKey(new Error("Failed to fetch"))).toBeNull()
    expect(roomErrorKey(answered(500, null))).toBeNull()
    expect(roomErrorKey(null)).toBeNull()
  })
})

describe("isRefusal", () => {
  it("is a 4xx: the server answered no, and asking again changes nothing", () => {
    expect(isRefusal(answered(404, { error_key: "errors.api.userNotInRoom" }))).toBe(true)
    expect(isRefusal(answered(403))).toBe(true)
    expect(isRefusal(answered(429))).toBe(true)
  })

  it("is not a server failure or a dropped connection", () => {
    expect(isRefusal(answered(500))).toBe(false)
    expect(isRefusal(answered(503))).toBe(false)
    expect(isRefusal(new Error("Failed to fetch"))).toBe(false)
  })
})

describe("retryUnlessRefused", () => {
  it("never retries a refusal", () => {
    // FR-5: a 404 for a non-member was retried, then polled every 2 s, forever
    expect(retryUnlessRefused(0, answered(404))).toBe(false)
  })

  it("retries anything else twice", () => {
    expect(retryUnlessRefused(0, answered(502))).toBe(true)
    expect(retryUnlessRefused(1, new Error("Failed to fetch"))).toBe(true)
    expect(retryUnlessRefused(2, answered(502))).toBe(false)
  })
})

describe("joinRepairFor", () => {
  it("offers no repair for a ban or a seat elsewhere (review F2)", () => {
    expect(joinRepairFor(ROOM_ERROR_KEYS.banned)).toBe("none")
    expect(joinRepairFor(ROOM_ERROR_KEYS.alreadyInRoom)).toBe("none")
  })

  it("says the PIN may have changed when the PIN is refused (review F1)", () => {
    expect(joinRepairFor(ROOM_ERROR_KEYS.wrongPin)).toBe("pinChanged")
  })

  it("keeps the general repair for anything else", () => {
    expect(joinRepairFor("errors.api.roomNotFound")).toBe("generic")
    expect(joinRepairFor(null)).toBe("generic")
  })
})
