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
vi.mock("@/lib/auth", () => ({
  clearAuthData: () => mockClearAuthData(),
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
  })

  it("starts in loading state", () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    expect(result.current.isLoading).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
  })

  it("finishes loading when no stored auth", async () => {
    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it("restores auth from localStorage when /me fails", async () => {
    mockGetStoredToken.mockReturnValue("stored-token")
    mockGetStoredUserData.mockReturnValue({ id: "u1", username: "Alice", email: "a@b.com", is_active: true, is_admin: false })
    mockGetTokenExpiry.mockReturnValue(Date.now() + 300_000) // 5 min from now

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
  })

  it("authenticates via /me endpoint (cookie auth)", async () => {
    const userData = { id: "u2", username: "Bob", email: "b@b.com", is_active: true, is_admin: false }
    mockApiClient.mockResolvedValueOnce({ data: userData })

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Bob")
  })

  it("mints a fresh token pair after cookie auth so the session can outlive the access token", async () => {
    // Regression guard: the cookie path used to set a "cookie-auth" sentinel and
    // return without scheduling any refresh. Every reloaded tab then ran on
    // whatever access token happened to be in localStorage, and once that expired
    // the next request 401'd and bounced the player to /auth/login mid-game. It
    // also left a stale token behind, which is what useSocket authenticates the
    // Socket.IO handshake with — so real-time silently fell back to polling.
    const userData = { id: "u3", username: "Cookie", email: "c@b.com", is_active: true, is_admin: false }
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

  it("falls back to the cookie-auth sentinel when the refresh call fails", async () => {
    const userData = { id: "u4", username: "Dana", email: "d@b.com", is_active: true, is_admin: false }
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

    const userData = { id: "u1", username: "Alice", email: "a@b.com", is_active: true, is_admin: false }
    act(() => {
      result.current.login("access-tok", "refresh-tok", 3600, userData)
    })

    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.username).toBe("Alice")
    expect(mockStoreAuthData).toHaveBeenCalledWith("access-tok", "refresh-tok", 3600, userData)
  })

  it("logout clears auth state", async () => {
    // Start authenticated via /me
    const userData = { id: "u1", username: "Alice", email: "a@b.com", is_active: true, is_admin: false }
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
