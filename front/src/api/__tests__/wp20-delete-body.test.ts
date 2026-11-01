import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { installFakeFetch, json, type FakeServer } from "./fake-fetch"

vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }))

// after the mock: the real ky client over the fake server
const { client } = await import("../client")
const { deleteAccountApiV1UsersMeAccountDelete } = await import("../generated")

const ACCOUNT = "DELETE /api/v1/users/me/account"

let server: FakeServer

beforeEach(() => {
  localStorage.clear()
  localStorage.setItem("majlisna-token", "access")
  localStorage.setItem("majlisna-token-expiry", String(Date.now() + 600_000))
  server = installFakeFetch()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

/**
 * A DELETE that carries a body sends it. Account deletion is the one such call: the
 * server needs the password (or a Google token) in the body, and the client used to drop
 * the body of every method but POST/PUT/PATCH, so every deletion from the profile answered
 * 422 (found by e2e/tests/auth/account-delete.spec.ts).
 */
describe("a DELETE with a body (WP-20)", () => {
  it("sends the password the account deletion is confirmed with", async () => {
    server.on(ACCOUNT, () => new Response(null, { status: 204 }))

    await deleteAccountApiV1UsersMeAccountDelete({ password: "my-password" })

    const [call] = server.calls(ACCOUNT)
    expect(call.body).toEqual({ password: "my-password" })
  })

  it("sends no body for a DELETE that has none", async () => {
    server.on("DELETE /api/v1/notebook/entries/abc", () => new Response(null, { status: 204 }))

    await client({ method: "DELETE", url: "/api/v1/notebook/entries/abc" })

    const [call] = server.calls("DELETE /api/v1/notebook/entries/abc")
    expect(call.body).toBeNull()
  })

  it("still answers a refused deletion with the server's error", async () => {
    server.on(ACCOUNT, json(401, { error_key: "errors.api.invalidCredentials", message: "Invalid credentials" }))

    await expect(deleteAccountApiV1UsersMeAccountDelete({ password: "wrong" })).rejects.toMatchObject({ response: { status: 401 } })
    expect(server.calls(ACCOUNT)[0].body).toEqual({ password: "wrong" })
  })
})
