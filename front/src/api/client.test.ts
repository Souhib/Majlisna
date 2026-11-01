import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { held, html, installFakeFetch, json, offline, type FakeServer } from "./__tests__/fake-fetch"

// Mock i18n before importing the module
vi.mock("@/i18n", () => ({
  default: {
    t: (key: string, opts?: { defaultValue?: string }) => {
      const translations: Record<string, string> = {
        "errors.api.userNotFound": "User not found.",
        "errors.api.invalidCredentials": "Please check your email and password.",
        "errors.network": "The connection was lost.",
        "common.error": "An error occurred",
      }
      return translations[key] ?? opts?.defaultValue ?? ""
    },
  },
}))

// Must import after mock setup
const { client, getApiErrorMessage, redirectsToLoginOn401, refreshSession } = await import("./client")

const TOKEN_KEY = "majlisna-token"
const EXPIRY_KEY = "majlisna-token-expiry"
const LEGACY_REFRESH_KEY = "majlisna-refresh-token"
const REFRESH = "POST /api/v1/auth/refresh"
const ROOMS = "GET /api/v1/rooms"

// The server's answer: the refresh token is only ever the httpOnly cookie (SEC F13).
const freshPair = (access: string) => json(200, { access_token: access, expires_in: 900 })
const tokenRefused = json(401, { error_key: "errors.api.invalidToken", message: "Invalid token" })

/** A signed-in tab: an access token and its expiry, as storeAuthData leaves them. */
function signIn(token = "old-access", expiresInMs = 600_000) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(EXPIRY_KEY, String(Date.now() + expiresInMs))
  localStorage.setItem("majlisna-session", "1")
}

let server: FakeServer
let assign: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState(null, "", "/rooms")
  server = installFakeFetch()
  assign = vi.spyOn(window.location, "assign").mockImplementation(() => {})
})

afterEach(() => {
  assign.mockRestore()
  vi.unstubAllGlobals()
})

describe("redirectsToLoginOn401", () => {
  const signedIn = { hadToken: true, pathname: "/today" }

  it("sends a signed-in visitor to the login page when an ordinary request is refused", () => {
    expect(redirectsToLoginOn401("http://localhost:3000/api/v1/daily-word/guess?lang=en", signedIn)).toBe(true)
    expect(redirectsToLoginOn401("https://api.majlisna.app/api/v1/rooms", { hadToken: true, pathname: "/rooms" })).toBe(true)
  })

  it("leaves the session probes to AuthProvider, which ends signed out on the page instead", () => {
    // A returning visitor with an expired access token: the provider refreshes first,
    // and a refused /me or refresh must not bounce them off a public page.
    expect(redirectsToLoginOn401("http://localhost:3000/api/v1/auth/me", signedIn)).toBe(false)
    expect(redirectsToLoginOn401("https://api.majlisna.app/api/v1/auth/refresh", signedIn)).toBe(false)
  })

  it("never redirects without a stored token, nor from the login page itself", () => {
    expect(redirectsToLoginOn401("http://localhost:3000/api/v1/rooms", { hadToken: false, pathname: "/rooms" })).toBe(false)
    expect(redirectsToLoginOn401("http://localhost:3000/api/v1/rooms", { hadToken: true, pathname: "/auth/login" })).toBe(false)
  })
})

describe("getApiErrorMessage", () => {
  it("returns the fallback when there is no error", () => {
    expect(getApiErrorMessage(null, "Custom fallback")).toBe("Custom fallback")
    expect(getApiErrorMessage(undefined, "Custom fallback")).toBe("Custom fallback")
  })

  it("translates error_key via i18n", () => {
    const error = { response: { data: { error_key: "errors.api.userNotFound" } } }
    expect(getApiErrorMessage(error)).toBe("User not found.")
  })

  it("falls back to frontend_message when error_key has no translation", () => {
    const error = { response: { data: { error_key: "errors.api.unknownKey", frontend_message: "Something went wrong on our end." } } }
    expect(getApiErrorMessage(error)).toBe("Something went wrong on our end.")
  })

  it("falls back to message field", () => {
    const error = { response: { data: { message: "Internal server error" } } }
    expect(getApiErrorMessage(error)).toBe("Internal server error")
  })

  it("falls back to string detail field", () => {
    const error = { response: { data: { detail: "Not authorized" } } }
    expect(getApiErrorMessage(error)).toBe("Not authorized")
  })

  it("extracts first validation error from array detail", () => {
    const error = { response: { data: { detail: [{ type: "value_error", loc: ["body", "email"], msg: "Invalid email format" }] } } }
    expect(getApiErrorMessage(error)).toBe("Invalid email format")
  })

  it("never shows the browser's words for a request that got no answer (FR-8)", () => {
    // offline: what fetch rejects with
    expect(getApiErrorMessage(new TypeError("Failed to fetch"), "fb")).toBe("fb")
    // without a fallback, the translated generic line
    expect(getApiErrorMessage(new TypeError("Failed to fetch"))).toBe("The connection was lost.")
    expect(getApiErrorMessage(new Error("Network failure"))).toBe("The connection was lost.")
  })

  it("never shows ky's words, nor an internal URL, for a proxy's HTML 502 (FR-8)", async () => {
    // Prepare: the reverse proxy answers a deploy with an HTML page
    server.on("POST /api/v1/wordquiz/games/g1/answer", html(502))

    // Act
    const error = await client({ url: "/api/v1/wordquiz/games/g1/answer", method: "POST", data: { answer: "x" } }).catch((e: unknown) => e)

    // Assert
    expect((error as Error).message).toContain("502") // ky's own words, which name the URL
    expect(getApiErrorMessage(error, "fb")).toBe("fb")
    expect(getApiErrorMessage(error)).toBe("The connection was lost.")
  })

  it("says the generic error for an answer with an envelope it cannot read", () => {
    expect(getApiErrorMessage({ response: { data: {} } })).toBe("An error occurred")
    expect(getApiErrorMessage({ response: { data: {} } }, "fb")).toBe("fb")
  })
})

describe("client", () => {
  it("answers a 204 with no data, though FastAPI labels it application/json", async () => {
    // Prepare: FastAPI's No Content answer, an empty body under a JSON content type
    server.on("DELETE /api/v1/notebook/entries/e1", () => new Response(null, { status: 204, headers: { "content-type": "application/json" } }))

    // Act
    const response = await client({ url: "/api/v1/notebook/entries/e1", method: "DELETE" })

    // Assert
    expect(server.fetchMock).toHaveBeenCalledTimes(1)
    expect(response.status).toBe(204)
    expect(response.data).toBeUndefined()
  })

  it("sends the auth calls with credentials, so the httpOnly cookies are set and sent cross-origin too", async () => {
    // Prepare
    server.on("POST /api/v1/auth/login", json(200, { access_token: "a", expires_in: 900, user: {} }))
    server.on(ROOMS, json(200, []))

    // Act
    await client({ url: "/api/v1/auth/login", method: "POST", data: { email: "a@b.c", password: "x" } })
    await client({ url: "/api/v1/rooms" })

    // Assert: the cookies matter to /auth only; other calls carry the bearer
    expect(server.calls("POST /api/v1/auth/login")[0].credentials).toBe("include")
    expect(server.calls(ROOMS)[0].credentials).not.toBe("include")
  })
})

describe("a refused access token (FR-3)", () => {
  it("is refreshed once and the request replayed exactly once with the new token", async () => {
    // Prepare: the server refuses the old token and accepts the new one
    signIn("old-access")
    server.on(ROOMS, tokenRefused, json(200, [{ id: "r1" }]))
    server.on(REFRESH, freshPair("new-access"))

    // Act
    const response = await client<{ id: string }[]>({ url: "/api/v1/rooms" })

    // Assert
    expect(response.data).toEqual([{ id: "r1" }])
    expect(server.order()).toEqual([ROOMS, REFRESH, ROOMS])
    expect(server.calls(ROOMS).map((c) => c.authorization)).toEqual(["Bearer old-access", "Bearer new-access"])
    expect(localStorage.getItem(TOKEN_KEY)).toBe("new-access")
    expect(assign).not.toHaveBeenCalled()
  })

  it("asks the server with the cookie and no token in the body", async () => {
    signIn("old-access")
    server.on(ROOMS, tokenRefused, json(200, []))
    server.on(REFRESH, freshPair("new-access"))

    await client({ url: "/api/v1/rooms" })

    const [refresh] = server.calls(REFRESH)
    expect(refresh.credentials).toBe("include")
    expect(refresh.body).toBeNull()
  })

  it("replays a POST with its body", async () => {
    signIn("old-access")
    server.on("POST /api/v1/wordquiz/games/g1/answer", tokenRefused, json(200, { correct: true }))
    server.on(REFRESH, freshPair("new-access"))

    const response = await client<{ correct: boolean }>({ url: "/api/v1/wordquiz/games/g1/answer", method: "POST", data: { answer: "Badr" } })

    expect(response.data).toEqual({ correct: true })
    expect(server.calls("POST /api/v1/wordquiz/games/g1/answer").map((c) => c.body)).toEqual([{ answer: "Badr" }, { answer: "Badr" }])
  })

  it("shares one refresh between two requests refused together", async () => {
    // Prepare: the refresh is held in flight while both 401s arrive
    signIn("old-access")
    const refresh = held(freshPair("new-access"))
    server.on(ROOMS, (request) => (request.headers.get("authorization") === "Bearer new-access" ? json(200, [])(request) : tokenRefused(request)))
    server.on("GET /api/v1/users/me/stats", (request) =>
      request.headers.get("authorization") === "Bearer new-access" ? json(200, { wins: 1 })(request) : tokenRefused(request),
    )
    server.on(REFRESH, refresh.answer)

    // Act
    const both = Promise.all([client({ url: "/api/v1/rooms" }), client({ url: "/api/v1/users/me/stats" })])
    await vi.waitFor(() => expect(server.calls(REFRESH)).toHaveLength(1))
    refresh.release()
    const [rooms, stats] = await both

    // Assert
    expect(server.calls(REFRESH)).toHaveLength(1)
    expect(rooms.status).toBe(200)
    expect(stats.data).toEqual({ wins: 1 })
  })

  it("ends the session and goes to the login page only when the refresh itself is refused", async () => {
    // Prepare
    signIn("old-access")
    window.history.replaceState(null, "", "/stats?tab=undercover")
    server.on(ROOMS, tokenRefused)
    server.on(REFRESH, tokenRefused)

    // Act
    const error = await client({ url: "/api/v1/rooms" }).catch((e: unknown) => e)

    // Assert
    expect((error as { response?: { status: number } }).response?.status).toBe(401)
    expect(server.order()).toEqual([ROOMS, REFRESH])
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(assign).toHaveBeenCalledWith(`/auth/login?redirect=${encodeURIComponent("/stats?tab=undercover")}`)
  })

  it("keeps the session when the refresh is only rate-limited, and does not redirect", async () => {
    // Prepare: the refresh answers 429 (other phones on the IP spent the budget)
    signIn("old-access")
    server.on(ROOMS, tokenRefused)
    server.on(REFRESH, json(429, { error_key: "errors.api.rateLimitExceeded" }, { "retry-after": "30" }))

    // Act
    const error = await client({ url: "/api/v1/rooms" }).catch((e: unknown) => e)

    // Assert: the request failed, the session did not
    expect((error as { response?: { status: number } }).response?.status).toBe(401)
    expect(localStorage.getItem(TOKEN_KEY)).toBe("old-access")
    expect(assign).not.toHaveBeenCalled()
  })

  it("keeps the session when the refresh gets no answer at all", async () => {
    signIn("old-access")
    server.on(ROOMS, tokenRefused)
    server.on(REFRESH, offline())

    await client({ url: "/api/v1/rooms" }).catch(() => undefined)

    expect(localStorage.getItem(TOKEN_KEY)).toBe("old-access")
    expect(assign).not.toHaveBeenCalled()
  })

  it("does not refresh again when the replay is refused too", async () => {
    signIn("old-access")
    server.on(ROOMS, tokenRefused)
    server.on(REFRESH, freshPair("new-access"))

    await client({ url: "/api/v1/rooms" }).catch(() => undefined)

    expect(server.order()).toEqual([ROOMS, REFRESH, ROOMS])
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(assign).toHaveBeenCalledTimes(1)
  })

  it("goes straight to the login page, with the notice, when the session was revoked (SEC F01)", async () => {
    // Prepare: the server signed this session out (logout elsewhere, password reset)
    signIn("old-access")
    server.on(ROOMS, json(401, { error_key: "errors.api.sessionRevoked" }))
    server.on(REFRESH, freshPair("never"))

    // Act
    await client({ url: "/api/v1/rooms" }).catch(() => undefined)

    // Assert: no refresh, no retry loop
    expect(server.calls(REFRESH)).toHaveLength(0)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(sessionStorage.getItem("majlisna-auth-notice")).toBe("sessionRevoked")
    expect(assign).toHaveBeenCalledTimes(1)
  })

  it("does not end the session over a wrong current password", async () => {
    // Prepare: changing the password re-checks the current one, which answers 401
    signIn("old-access")
    server.on("PATCH /api/v1/users/me/password", json(401, { error_key: "errors.api.invalidCredentials" }))

    // Act
    const error = await client({ url: "/api/v1/users/me/password", method: "PATCH", data: { current_password: "x", new_password: "y" } }).catch(
      (e: unknown) => e,
    )

    // Assert: the form says the password is wrong; the player stays signed in
    expect(getApiErrorMessage(error, "fb")).toBe("Please check your email and password.")
    expect(server.calls(REFRESH)).toHaveLength(0)
    expect(localStorage.getItem(TOKEN_KEY)).toBe("old-access")
    expect(assign).not.toHaveBeenCalled()
  })

  it("leaves a visitor with no session alone", async () => {
    server.on(ROOMS, tokenRefused)

    await client({ url: "/api/v1/rooms" }).catch(() => undefined)

    expect(server.calls(REFRESH)).toHaveLength(0)
    expect(assign).not.toHaveBeenCalled()
  })

  it("leaves the auth endpoints' own 401s to their callers (a wrong password at login)", async () => {
    signIn("old-access")
    server.on("POST /api/v1/auth/login", json(401, { error_key: "errors.api.invalidCredentials" }))

    await client({ url: "/api/v1/auth/login", method: "POST", data: {} }).catch(() => undefined)

    expect(server.calls(REFRESH)).toHaveLength(0)
    expect(localStorage.getItem(TOKEN_KEY)).toBe("old-access")
    expect(assign).not.toHaveBeenCalled()
  })
})

describe("refreshSession", () => {
  it("sends a legacy refresh token once, in the body, then deletes it (SEC F13 migration)", async () => {
    // Prepare: a session the old client opened, its refresh token in localStorage
    signIn("old-access")
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")
    server.on(REFRESH, freshPair("new-1"), freshPair("new-2"))

    // Act
    const first = await refreshSession()
    const second = await refreshSession()

    // Assert
    expect(first.status).toBe("ok")
    expect(second.status).toBe("ok")
    expect(server.calls(REFRESH).map((c) => c.body)).toEqual([{ refresh_token: "legacy-refresh" }, null])
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBe("new-2")
  })

  it("tries the cookie once when a stale legacy token is refused", async () => {
    signIn("old-access")
    localStorage.setItem(LEGACY_REFRESH_KEY, "stale-legacy")
    server.on(REFRESH, tokenRefused, freshPair("new-access"))

    const outcome = await refreshSession()

    expect(outcome.status).toBe("ok")
    expect(server.calls(REFRESH).map((c) => c.body)).toEqual([{ refresh_token: "stale-legacy" }, null])
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
  })

  it("keeps a legacy token through a rate limit, and spends no second request on it", async () => {
    signIn("old-access")
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")
    server.on(REFRESH, json(429, { error_key: "errors.api.rateLimitExceeded" }, { "retry-after": "20" }))

    const outcome = await refreshSession()

    expect(outcome).toEqual({ status: "unavailable", retryAfterMs: 20_000 })
    expect(server.calls(REFRESH)).toHaveLength(1)
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBe("legacy-refresh")
  })

  it("does not ask again while the server's Retry-After runs", async () => {
    signIn("old-access")
    server.on(REFRESH, json(429, {}, { "retry-after": "30" }), freshPair("new-access"))

    await refreshSession()
    const during = await refreshSession()

    expect(during.status).toBe("unavailable")
    expect(server.calls(REFRESH)).toHaveLength(1)
  })

  it("says a revoked session is revoked, and does not try the cookie after it", async () => {
    signIn("old-access")
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")
    server.on(REFRESH, json(401, { error_key: "errors.api.sessionRevoked" }))

    const outcome = await refreshSession()

    expect(outcome).toEqual({ status: "unauthorized", revoked: true })
    expect(server.calls(REFRESH)).toHaveLength(1)
  })

  it("lets two tabs whose tokens expire together spend ONE refresh (SEC F01)", async () => {
    // Prepare: two tabs are two copies of this module sharing localStorage and the
    // browser's Web Locks; the refresh is held so both reach the lock while it is taken
    vi.stubGlobal("navigator", { ...navigator, locks: fakeWebLocks() })
    signIn("expired-access", 30_000)
    const refresh = held(freshPair("new-access"))
    server.on(REFRESH, refresh.answer)
    vi.resetModules()
    const tabA = await import("./client")
    vi.resetModules()
    const tabB = await import("./client")
    expect(tabA.refreshSession).not.toBe(tabB.refreshSession)

    // Act
    const a = tabA.refreshSession({ staleToken: "expired-access" })
    const b = tabB.refreshSession({ staleToken: "expired-access" })
    await vi.waitFor(() => expect(server.calls(REFRESH)).toHaveLength(1))
    refresh.release()
    const outcomes = await Promise.all([a, b])

    // Assert: the second tab found the first tab's token and asked nothing
    expect(outcomes.map((o) => o.status)).toEqual(["ok", "ok"])
    expect(server.calls(REFRESH)).toHaveLength(1)
    expect(localStorage.getItem(TOKEN_KEY)).toBe("new-access")
  })
})

/** navigator.locks, as the browser shares it between the tabs of an origin: one holder per name. */
function fakeWebLocks() {
  const tails = new Map<string, Promise<unknown>>()
  return {
    request(name: string, ...rest: unknown[]) {
      const task = rest[rest.length - 1] as () => Promise<unknown>
      const previous = tails.get(name) ?? Promise.resolve()
      const run = previous.then(() => task())
      tails.set(
        name,
        run.catch(() => undefined),
      )
      return run
    },
  }
}
