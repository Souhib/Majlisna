import { act, renderHook, waitFor } from "@testing-library/react"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

// Mock apiClient
const mockApiClient = vi.fn()
vi.mock("@/api/client", () => ({
  default: (...args: unknown[]) => mockApiClient(...args),
}))

// Mock auth helpers
const mockClearAuthData = vi.fn()
const mockGetStoredToken = vi.fn()
const mockGetStoredUserData = vi.fn()
const mockGetTokenExpiry = vi.fn()
const mockStoreAuthData = vi.fn()
const mockHasStoredSession = vi.fn()
vi.mock("@/lib/auth", () => ({
  clearAuthData: () => mockClearAuthData(),
  getStoredRefreshToken: () => null,
  hasStoredSession: () => mockHasStoredSession(),
  getStoredToken: () => mockGetStoredToken(),
  getStoredUserData: () => mockGetStoredUserData(),
  getTokenExpiry: () => mockGetTokenExpiry(),
  storeAuthData: (...args: unknown[]) => mockStoreAuthData(...args),
}))

// Import after mocks
const { AuthProvider, useAuth } = await import("./AuthProvider")

function wrapper({ children }: { children: ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    // Default: /me fails (no cookie auth), no stored tokens
    mockApiClient.mockRejectedValue(new Error("Unauthorized"))
    mockGetStoredToken.mockReturnValue(null)
    mockGetStoredUserData.mockReturnValue(null)
    mockGetTokenExpiry.mockReturnValue(null)
    // a session is stored unless a test says otherwise (the cookie paths need /me)
    mockHasStoredSession.mockReturnValue(true)
  })

  it("does not ask /me when this browser holds no session", async () => {
    // A logged-out visitor's every page load used to spend a 401 on GET /auth/me.
    mockHasStoredSession.mockReturnValue(false)

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(false)
    expect(mockApiClient).not.toHaveBeenCalled()
  })

  it("starts in loading state", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
    // Let the initial /me check settle inside act, so its state update is not left dangling
    await waitFor(() => expect(result.current.isLoading).toBe(false))
  })

  it("finishes loading when no stored auth", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it("restores auth from localStorage when /me fails", async () => {
    mockGetStoredToken.mockReturnValue("stored-token")
    mockGetStoredUserData.mockReturnValue({ id: "u1", username: "Alice", email: "a@b.com" })
    mockGetTokenExpiry.mockReturnValue(Date.now() + 300_000) // 5 min from now

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
  })

  it("authenticates via /me endpoint (cookie auth)", async () => {
    const userData = { id: "u2", username: "Bob", email_address: "b@b.com" }
    mockApiClient.mockResolvedValueOnce({ data: userData })

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Bob")
  })

  it("reads the address from /me's email_address, so a reloaded tab still knows the player's email", async () => {
    // Prepare: GET /me answers a UserView, whose field is email_address (not email)
    mockApiClient.mockResolvedValueOnce({ data: { id: "u5", username: "Eve", email_address: "eve@b.com", email_verified: true } })

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert
    expect(result.current.user).toEqual({ id: "u5", username: "Eve", email: "eve@b.com" })
  })

  it("mints a fresh token pair after cookie auth so the session can outlive the access token", async () => {
    // Regression guard: the cookie path used to set a "cookie-auth" sentinel and
    // return without scheduling any refresh. Every reloaded tab then ran on
    // whatever access token happened to be in localStorage, and once that expired
    // the next request 401'd and bounced the player to /auth/login mid-game. It
    // also left a stale token behind, which is what useSocket authenticates the
    // Socket.IO handshake with — so real-time silently fell back to polling.
    const userData = { id: "u3", username: "Cookie", email_address: "c@b.com" }
    mockApiClient.mockResolvedValueOnce({ data: userData }) // GET /me
    mockApiClient.mockResolvedValueOnce({
      data: { access_token: "fresh-access", refresh_token: "fresh-refresh", expires_in: 900 },
    }) // POST /auth/refresh

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Cookie")
    // A real token, not the sentinel — otherwise useSocket can't authenticate.
    expect(result.current.token).toBe("fresh-access")
    expect(mockStoreAuthData).toHaveBeenCalledWith("fresh-access", "fresh-refresh", 900)
  })

  it("refreshes an expired access token before asking /me, so a returning visitor stays signed in", async () => {
    // Regression guard: /me used to go first with the stale bearer; its 401 made the
    // client clear the session and send the visitor to the login page (from any page,
    // the public /today included) and the refresh token, still good, was never tried.
    // Prepare: an access token past its expiry, a refresh that works, then /me
    mockGetStoredToken.mockReturnValue("expired-access")
    mockGetTokenExpiry.mockReturnValueOnce(Date.now() - 60_000)
    const urls: string[] = []
    mockApiClient.mockImplementation(async ({ url }: { url: string }) => {
      urls.push(url)
      if (url.endsWith("/auth/refresh")) return { data: { access_token: "fresh-access", refresh_token: "fresh-refresh", expires_in: 900 } }
      if (url.endsWith("/auth/me")) return { data: { id: "u6", username: "Back", email_address: "back@b.com" } }
      throw new Error(`unexpected ${url}`)
    })

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert: one refresh, then /me with the fresh token, and no second refresh
    expect(urls).toEqual(["/api/v1/auth/refresh", "/api/v1/auth/me"])
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe("fresh-access")
    expect(result.current.user).toEqual({ id: "u6", username: "Back", email: "back@b.com" })
    expect(mockStoreAuthData).toHaveBeenCalledWith("fresh-access", "fresh-refresh", 900)
    expect(mockClearAuthData).not.toHaveBeenCalled()
  })

  it("ends signed out, without asking /me, when an expired session cannot be refreshed", async () => {
    // Prepare: an access token past its expiry and a refresh token the server refuses
    mockGetStoredToken.mockReturnValue("expired-access")
    mockGetTokenExpiry.mockReturnValue(Date.now() - 60_000)
    const urls: string[] = []
    mockApiClient.mockImplementation(async ({ url }: { url: string }) => {
      urls.push(url)
      throw new Error("Unauthorized")
    })

    // Act
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    // Assert
    expect(urls.every((url) => url.endsWith("/auth/refresh"))).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(mockClearAuthData).toHaveBeenCalled()
  })

  it("falls back to the cookie-auth sentinel when the refresh call fails", async () => {
    const userData = { id: "u4", username: "Dana", email_address: "d@b.com" }
    mockApiClient.mockResolvedValueOnce({ data: userData }) // GET /me
    // Every later call rejects (default mock) → both refresh attempts fail.

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.token).toBe("cookie-auth")
  })

  it("login stores auth data and sets state", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const userData = { id: "u1", username: "Alice", email: "a@b.com" }
    act(() => {
      result.current.login("access-tok", "refresh-tok", 3600, userData)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
    expect(mockStoreAuthData).toHaveBeenCalledWith("access-tok", "refresh-tok", 3600, userData)
  })

  it("logout clears auth state", async () => {
    // Start authenticated via /me
    const userData = { id: "u1", username: "Alice", email: "a@b.com" }
    mockApiClient.mockResolvedValueOnce({ data: userData }) // /me success
    mockApiClient.mockResolvedValueOnce({}) // /logout success

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true))

    await act(async () => {
      await result.current.logout()
    })

    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
    expect(mockClearAuthData).toHaveBeenCalled()
  })

  it("useAuth throws when used outside provider", () => {
    expect(() => {
      renderHook(() => useAuth())
    }).toThrow("useAuth must be used within an AuthProvider")
  })
})
