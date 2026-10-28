import { describe, expect, it, vi } from "vitest"
import { roomErrorMessage } from "./errors"

vi.mock("@/api/client", () => ({
  getApiErrorMessage: (err: { response?: { data?: { frontend_message?: string } } }, fallback: string) =>
    err.response?.data?.frontend_message ?? fallback,
}))

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
