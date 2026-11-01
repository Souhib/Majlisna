import { act, render, renderHook, screen, waitFor } from "@testing-library/react"
import { type ReactNode, useEffect } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { held, installFakeFetch, json, offline, type FakeServer } from "@/api/__tests__/fake-fetch"

/**
 * The provider on the real ky client (api/client.ts) and the real storage (lib/auth.ts),
 * over a fake server behind `fetch`: what is asserted is what a browser would send.
 */
vi.mock("@/i18n", () => ({ default: { t: (key: string) => key } }))
const toast = vi.hoisted(() => ({ info: vi.fn() }))
vi.mock("sonner", () => ({ toast }))

const { AuthProvider, useAuth } = await import("./AuthProvider")
const { client } = await import("@/api/client")

const TOKEN_KEY = "majlisna-token"
const EXPIRY_KEY = "majlisna-token-expiry"
const USER_KEY = "majlisna-user-data"
const LEGACY_REFRESH_KEY = "majlisna-refresh-token"
const ME = "GET /api/v1/auth/me"
const REFRESH = "POST /api/v1/auth/refresh"
const ROOMS = "GET /api/v1/rooms"
const REFRESH_BUFFER_MS = 60_000

const me = (username = "Bob") => json(200, { id: "u1", username, email_address: `${username.toLowerCase()}@b.com` })
// The server's answer: the refresh token is only ever the httpOnly cookie (SEC F13).
const freshPair = (access: string, expiresIn = 900) => json(200, { access_token: access, expires_in: expiresIn })
const tokenRefused = json(401, { error_key: "errors.api.invalidToken" })
const rateLimited = (retryAfterSeconds: number) => json(429, { error_key: "errors.api.rateLimitExceeded" }, { "retry-after": String(retryAfterSeconds) })

/** A tab signed in earlier: an access token, its expiry, the player, the session marker. */
function signedInEarlier({ token = "stored-access", expiresInMs = 600_000, expiry = true } = {}) {
  localStorage.setItem(TOKEN_KEY, token)
  if (expiry) localStorage.setItem(EXPIRY_KEY, String(Date.now() + expiresInMs))
  localStorage.setItem(USER_KEY, JSON.stringify({ id: "u1", username: "Alice", email: "a@b.com" }))
  localStorage.setItem("majlisna-session", "1")
}

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

/** Advance the fake clock and let every promise it releases settle. */
async function elapse(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

let server: FakeServer
let assign: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  window.history.replaceState(null, "", "/rooms")
  server = installFakeFetch()
  assign = vi.spyOn(window.location, "assign").mockImplementation(() => {})
})

afterEach(() => {
  vi.useRealTimers()
  assign.mockRestore()
  vi.unstubAllGlobals()
})

describe("AuthProvider", () => {
  it("does not ask /me when this browser holds no session", async () => {
    // A logged-out visitor's every page load used to spend a 401 on GET /auth/me.
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(false)
    expect(server.calls()).toHaveLength(0)
  })

  it("starts in loading state", async () => {
    signedInEarlier()
    server.on(ME, me())
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
    await waitFor(() => expect(result.current.isLoading).toBe(false))
  })

  it("lets a page with a fresh token fetch its data before any refresh (FP-11)", async () => {
    // Prepare: a token with ten minutes left; the page asks for its data once signed in
    signedInEarlier({ expiresInMs: 600_000 })
    server.on(ME, me())
    server.on(ROOMS, json(200, []))
    server.on(REFRESH, freshPair("fresh-access"))
    function Page() {
      const { isLoading, isAuthenticated } = useAuth()
      useEffect(() => {
        if (!isLoading && isAuthenticated) void client({ url: "/api/v1/rooms" })
      }, [isLoading, isAuthenticated])
      return <p>{isLoading ? "loading" : "ready"}</p>
    }

    // Act
    render(<Page />, { wrapper })
    await waitFor(() => expect(server.calls(ROOMS)).toHaveLength(1))

    // Assert: /me, then the data; the refresh waits for its time
    expect(server.order()).toEqual([ME, ROOMS])
    expect(screen.getByText("ready")).toBeInTheDocument()
  })

  it("schedules the refresh before expiry, and sends it with the cookie and no token in the body", async () => {
    // Prepare
    vi.useFakeTimers({ shouldAdvanceTime: true })
    signedInEarlier({ expiresInMs: 600_000 })
    server.on(ME, me())
    server.on(REFRESH, freshPair("fresh-access"))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(server.calls(REFRESH)).toHaveLength(0)

    // Act: up to the refresh buffer before expiry
    await elapse(600_000 - REFRESH_BUFFER_MS)

    // Assert
    const refreshes = server.calls(REFRESH)
    expect(refreshes).toHaveLength(1)
    expect(refreshes[0].credentials).toBe("include")
    expect(refreshes[0].body).toBeNull()
    expect(result.current.token).toBe("fresh-access")
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
  })

  it("reads the address from /me's email_address, so a reloaded tab still knows the player's email", async () => {
    // Prepare: GET /me answers a UserView, whose field is email_address (not email)
    signedInEarlier()
    server.on(ME, json(200, { id: "u5", username: "Eve", email_address: "eve@b.com", email_verified: true }))

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert
    expect(result.current.user).toEqual({ id: "u5", username: "Eve", email: "eve@b.com" })
  })

  it("learns the token's life in the background when none is recorded", async () => {
    // Prepare: a session whose expiry was never recorded
    signedInEarlier({ expiry: false })
    server.on(ME, me())
    server.on(REFRESH, freshPair("fresh-access"))

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.token).toBe("fresh-access"))

    // Assert
    expect(result.current.isAuthenticated).toBe(true)
    expect(Number(localStorage.getItem(EXPIRY_KEY))).toBeGreaterThan(Date.now())
  })

  it("retries a load-time refresh that was rate-limited, after the server's Retry-After (FR-3)", async () => {
    // Prepare: /me works; the refresh at load answers 429 Retry-After: 30, then works
    vi.useFakeTimers({ shouldAdvanceTime: true })
    signedInEarlier({ expiry: false })
    server.on(ME, me())
    server.on(REFRESH, rateLimited(30), freshPair("fresh-access"))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(server.calls(REFRESH)).toHaveLength(1))

    // Act
    await elapse(29_000)
    expect(server.calls(REFRESH)).toHaveLength(1) // the server's 30 s are respected
    await elapse(5_000)

    // Assert: retried, and the tab now runs on a real, scheduled token
    expect(server.calls(REFRESH)).toHaveLength(2)
    expect(result.current.token).toBe("fresh-access")
    expect(result.current.isAuthenticated).toBe(true)
  })

  it("keeps a player signed in through a rate-limited refresh and an expired access token (FR-3, the probe's scenario)", async () => {
    // Prepare: the access token has 120 s left (refresh_429_logout2.mjs); every refresh is
    // rate-limited for now; past expiry the server refuses the access token
    vi.useFakeTimers({ shouldAdvanceTime: true })
    signedInEarlier({ token: "stored-access", expiresInMs: 120_000 })
    server.on(ME, me())
    server.on(REFRESH, rateLimited(60))
    server.on("GET /api/v1/games/user/u1", tokenRefused)
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Act: 128 s later, the stats page asks for its data
    await elapse(128_000)
    const error = await client({ url: "/api/v1/games/user/u1" }).catch((e: unknown) => e)

    // Assert: the request failed, the session did not, and a retry is on its way
    expect((error as { response?: { status: number } }).response?.status).toBe(401)
    expect(assign).not.toHaveBeenCalled()
    expect(localStorage.getItem(TOKEN_KEY)).toBe("stored-access")
    expect(result.current.isAuthenticated).toBe(true)
    const triedSoFar = server.calls(REFRESH).length
    expect(triedSoFar).toBeGreaterThanOrEqual(1)

    // Act: the rate limit lifts
    server.on(REFRESH, freshPair("fresh-access"))
    server.on("GET /api/v1/games/user/u1", json(200, []))
    await elapse(5 * 60_000)

    // Assert: the retry found the server and the session goes on
    expect(server.calls(REFRESH).length).toBeGreaterThan(triedSoFar)
    expect(result.current.token).toBe("fresh-access")
    expect((await client({ url: "/api/v1/games/user/u1" })).status).toBe(200)
    expect(assign).not.toHaveBeenCalled()
  })

  it("refreshes an expired access token before asking /me, so a returning visitor stays signed in", async () => {
    // Regression guard: /me used to go first with the stale bearer; its 401 made the
    // client clear the session and send the visitor to the login page (from any page,
    // the public /today included) and the refresh token, still good, was never tried.
    signedInEarlier({ token: "expired-access", expiresInMs: -60_000 })
    server.on(REFRESH, freshPair("fresh-access"))
    server.on(ME, me("Back"))

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert: one refresh, then /me with the fresh token, and no second refresh
    expect(server.order()).toEqual([REFRESH, ME])
    expect(server.calls(ME)[0].authorization).toBe("Bearer fresh-access")
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe("fresh-access")
    expect(result.current.user).toEqual({ id: "u1", username: "Back", email: "back@b.com" })
  })

  it("ends signed out, without asking /me, when an expired session cannot be refreshed", async () => {
    // Prepare: an access token past its expiry and a refresh the server refuses
    signedInEarlier({ token: "expired-access", expiresInMs: -60_000 })
    server.on(REFRESH, tokenRefused)

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert
    expect(server.calls(ME)).toHaveLength(0)
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(assign).not.toHaveBeenCalled()
  })

  it("keeps an expired session whose refresh got no answer, and tries again (FR-3)", async () => {
    // Prepare: the server is down for the first refresh (a deploy), up for the next
    vi.useFakeTimers({ shouldAdvanceTime: true })
    signedInEarlier({ token: "expired-access", expiresInMs: -60_000 })
    server.on(REFRESH, json(503, { error_key: "errors.api.serviceUnavailable" }), freshPair("fresh-access"))
    server.on(ME, me())
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert: not signed out over an outage
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
    expect(localStorage.getItem(TOKEN_KEY)).toBe("expired-access")

    // Act
    await elapse(60_000)

    // Assert
    expect(server.calls(REFRESH)).toHaveLength(2)
    expect(result.current.token).toBe("fresh-access")
  })

  it("sends a revoked session to the login page with the notice, and asks no second refresh (SEC F01)", async () => {
    // Prepare: the scheduled refresh learns the session was signed out elsewhere
    vi.useFakeTimers({ shouldAdvanceTime: true })
    window.history.replaceState(null, "", "/game/undercover/g1")
    signedInEarlier({ expiresInMs: 120_000 })
    server.on(ME, me())
    server.on(REFRESH, json(401, { error_key: "errors.api.sessionRevoked" }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Act
    await elapse(120_000 - REFRESH_BUFFER_MS)
    await elapse(10 * 60_000)

    // Assert
    expect(server.calls(REFRESH)).toHaveLength(1)
    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
    expect(sessionStorage.getItem("majlisna-auth-notice")).toBe("sessionRevoked")
    expect(assign).toHaveBeenCalledTimes(1)
    expect(assign).toHaveBeenCalledWith(`/auth/login?redirect=${encodeURIComponent("/game/undercover/g1")}`)
  })

  it("says the revoked-session notice on the page it was sent to, once", async () => {
    // Prepare: the previous page noted it before sending the player here
    sessionStorage.setItem("majlisna-auth-notice", "sessionRevoked")

    // Act
    const { result, unmount } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    unmount()
    renderHook(() => useAuth(), { wrapper })

    // Assert
    expect(toast.info).toHaveBeenCalledTimes(1)
    expect(toast.info).toHaveBeenCalledWith("auth.sessionRevoked", expect.anything())
  })

  it("lets two tabs whose tokens expire together spend ONE refresh", async () => {
    // Prepare: two providers sharing one storage, scheduled from the same expiry
    vi.useFakeTimers({ shouldAdvanceTime: true })
    signedInEarlier({ expiresInMs: 120_000 })
    server.on(ME, me())
    const refresh = held(freshPair("fresh-access"))
    server.on(REFRESH, refresh.answer)
    const tabA = renderHook(() => useAuth(), { wrapper })
    const tabB = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(tabA.result.current.isLoading).toBe(false))
    await waitFor(() => expect(tabB.result.current.isLoading).toBe(false))

    // Act
    await elapse(120_000 - REFRESH_BUFFER_MS)
    refresh.release()
    await elapse(1_000)

    // Assert
    expect(server.calls(REFRESH)).toHaveLength(1)
    expect(tabA.result.current.token).toBe("fresh-access")
    expect(tabB.result.current.token).toBe("fresh-access")
  })

  it("restores auth from localStorage when /me gets no answer", async () => {
    signedInEarlier({ expiresInMs: 300_000 })
    server.on(ME, offline())

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
    expect(result.current.token).toBe("stored-access")
  })

  it("tries one refresh when /me refuses a token it thought fresh, then ends signed out", async () => {
    signedInEarlier({ expiresInMs: 300_000 })
    server.on(ME, tokenRefused)
    server.on(REFRESH, tokenRefused)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(server.order()).toEqual([ME, REFRESH])
    expect(result.current.isAuthenticated).toBe(false)
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it("signs this tab out when another tab signed out", async () => {
    signedInEarlier()
    server.on(ME, me())
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    act(() => {
      localStorage.clear()
      window.dispatchEvent(new StorageEvent("storage", { key: TOKEN_KEY, newValue: null, oldValue: "stored-access" }))
    })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it("login stores the access token and sets state (no refresh token reaches the page)", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const userData = { id: "u1", username: "Alice", email: "a@b.com" }
    act(() => {
      result.current.login("access-tok", 3600, userData)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
    expect(localStorage.getItem(TOKEN_KEY)).toBe("access-tok")
  })

  it("logout asks the server to end the session, with the cookie, then clears local state", async () => {
    // Start authenticated via /me
    signedInEarlier()
    server.on(ME, me())
    server.on("POST /api/v1/auth/logout", json(200, { status: "ok" }))
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    await act(async () => {
      await result.current.logout()
    })

    const [logout] = server.calls("POST /api/v1/auth/logout")
    expect(logout.credentials).toBe("include")
    expect(logout.authorization).toBe("Bearer stored-access")
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull()
  })

  it("useAuth throws when used outside provider", () => {
    expect(() => {
      renderHook(() => useAuth())
    }).toThrow("useAuth must be used within an AuthProvider")
  })
})
