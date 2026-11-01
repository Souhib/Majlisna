import { describe, it, expect, beforeEach, vi } from "vitest"
import { storedValues } from "@/api/__tests__/fake-fetch"
import {
  clearAuthData,
  clearLegacyRefreshToken,
  getLegacyRefreshToken,
  getStoredToken,
  getStoredUserData,
  getTokenExpiry,
  hasStoredSession,
  noteSessionRevoked,
  onSessionEndedElsewhere,
  onTokenStored,
  scrubTokenFromUrl,
  storeAuthData,
  takeAuthNotice,
} from "./auth"

const LEGACY_REFRESH_KEY = "majlisna-refresh-token"

describe("auth token storage", () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
  })

  it("returns null when no token is stored", () => {
    expect(getStoredToken()).toBeNull()
    expect(getLegacyRefreshToken()).toBeNull()
    expect(getTokenExpiry()).toBeNull()
    expect(getStoredUserData()).toBeNull()
  })

  it("stores the access token and its expiry", () => {
    storeAuthData("access-123", 3600)

    expect(getStoredToken()).toBe("access-123")
    expect(getTokenExpiry()).toBeGreaterThan(Date.now())
  })

  it("never writes the refresh token where a script can read it: it lives in the httpOnly cookie (SEC F13)", () => {
    // Prepare: a session opened by the old client, its refresh token still in localStorage
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")

    // Act: a login or a refresh stores the new access token
    storeAuthData("access-123", 3600, { id: "user-1" })

    // Assert: no refresh token in JS-readable storage, the legacy one included
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
    expect(storedValues()).not.toContain("legacy-refresh")
    expect(getLegacyRefreshToken()).toBeNull()
  })

  it("reads a legacy refresh token until it is cleared, for the one-time migration", () => {
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")
    expect(getLegacyRefreshToken()).toBe("legacy-refresh")

    clearLegacyRefreshToken()

    expect(getLegacyRefreshToken()).toBeNull()
    expect(localStorage.getItem(LEGACY_REFRESH_KEY)).toBeNull()
  })

  it("stores and retrieves user data", () => {
    storeAuthData("access-123", 3600, { id: "user-1", username: "test" })

    const userData = getStoredUserData() as { id: string; username: string }
    expect(userData).toEqual({ id: "user-1", username: "test" })
  })

  it("handles corrupted JSON in user data gracefully", () => {
    localStorage.setItem("majlisna-user-data", "not-valid-json{")

    expect(getStoredUserData()).toBeNull()
  })

  it("clears all auth data, a legacy refresh token included", () => {
    storeAuthData("access-123", 3600, { id: "user-1" })
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")

    clearAuthData()

    expect(getStoredToken()).toBeNull()
    expect(getLegacyRefreshToken()).toBeNull()
    expect(getTokenExpiry()).toBeNull()
    expect(getStoredUserData()).toBeNull()
    expect(hasStoredSession()).toBe(false)
  })

  it("calculates token expiry correctly", () => {
    const before = Date.now()
    storeAuthData("access", 60)
    const after = Date.now()

    const expiry = getTokenExpiry()!
    expect(expiry).toBeGreaterThanOrEqual(before + 60000)
    expect(expiry).toBeLessThanOrEqual(after + 60000)
  })

  it("announces every stored token, until unsubscribed", () => {
    const listener = vi.fn()
    const off = onTokenStored(listener)

    storeAuthData("access-1", 60)
    storeAuthData("access-2", 60)
    off()
    storeAuthData("access-3", 60)

    expect(listener).toHaveBeenCalledTimes(2)
  })

  it("hears a token another tab stored, and a session another tab ended", () => {
    // Prepare
    const stored = vi.fn()
    const ended = vi.fn()
    const offStored = onTokenStored(stored)
    const offEnded = onSessionEndedElsewhere(ended)

    // Act: the storage events another tab's writes raise here
    window.dispatchEvent(new StorageEvent("storage", { key: "majlisna-token", newValue: "from-tab-b", oldValue: "old" }))
    window.dispatchEvent(new StorageEvent("storage", { key: "majlisna-token", newValue: null, oldValue: "from-tab-b" }))
    window.dispatchEvent(new StorageEvent("storage", { key: "majlisna-language", newValue: "ar" }))
    offStored()
    offEnded()
    window.dispatchEvent(new StorageEvent("storage", { key: "majlisna-token", newValue: "again" }))

    // Assert
    expect(stored).toHaveBeenCalledTimes(1)
    expect(ended).toHaveBeenCalledTimes(1)
  })

  it("knows whether there is a session to resume", () => {
    expect(hasStoredSession()).toBe(false)
    storeAuthData("access", 60)
    expect(hasStoredSession()).toBe(true)
    // the access token alone gone: the marker says the refresh cookie can mint a new one
    localStorage.removeItem("majlisna-token")
    expect(hasStoredSession()).toBe(true)
    clearAuthData()
    expect(hasStoredSession()).toBe(false)
    // a session the old client opened (no marker yet) still counts
    localStorage.setItem(LEGACY_REFRESH_KEY, "legacy-refresh")
    expect(hasStoredSession()).toBe(true)
  })
})

describe("the session-revoked notice", () => {
  beforeEach(() => sessionStorage.clear())

  it("is said once, after the page that noted it has gone", () => {
    expect(takeAuthNotice()).toBeNull()

    noteSessionRevoked()

    expect(takeAuthNotice()).toBe("sessionRevoked")
    expect(takeAuthNotice()).toBeNull()
  })
})

describe("scrubTokenFromUrl", () => {
  it("drops the token from the address, keeping the rest and the router's history state (SEC F06)", () => {
    // Prepare: a link from an email, as the router left it
    window.history.replaceState({ __TSR_key: "k1" }, "", "/auth/reset-password?token=secret-abc&lang=fr#top")

    // Act
    scrubTokenFromUrl()

    // Assert
    expect(window.location.search).toBe("?lang=fr")
    expect(window.location.href).not.toContain("secret-abc")
    expect(window.location.hash).toBe("#top")
    expect(window.history.state).toEqual({ __TSR_key: "k1" })
  })

  it("leaves an address without a token untouched", () => {
    window.history.replaceState(null, "", "/auth/verify-email")
    const replace = vi.spyOn(window.history, "replaceState")

    scrubTokenFromUrl()

    expect(replace).not.toHaveBeenCalled()
    replace.mockRestore()
  })
})
