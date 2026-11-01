/**
 * What this browser keeps of a session, and nothing more.
 *
 * The refresh token is NOT here: the server sets it as an httpOnly cookie on login,
 * refresh and Google sign-in, and `/auth/refresh` reads that cookie when the body names
 * no token (SEC F13). A script, an injected one included, can therefore read the
 * 15-minute access token (the sockets need it) but never the 7-day refresh token.
 * `majlisna-session` is a non-secret marker saying a session was opened here, so a
 * page load knows there is a cookie worth asking the server about.
 */
const TOKEN_KEY = "majlisna-token"
const TOKEN_EXPIRY_KEY = "majlisna-token-expiry"
const USER_DATA_KEY = "majlisna-user-data"
const SESSION_MARKER_KEY = "majlisna-session"
/**
 * Where the old client kept the refresh token. Read once, to migrate a session opened
 * before the change (api/client.ts sends it in the body once, then deletes it).
 */
const LEGACY_REFRESH_TOKEN_KEY = "majlisna-refresh-token"
/** Until when the server asked not to be asked for a refresh (its Retry-After), shared by the tabs. */
const REFRESH_BLOCKED_UNTIL_KEY = "majlisna-refresh-blocked-until"
/** A notice for the next page (sessionStorage: this tab only, gone with it). */
const AUTH_NOTICE_KEY = "majlisna-auth-notice"

export type AuthNotice = "sessionRevoked"

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getLegacyRefreshToken(): string | null {
  return localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY)
}

export function clearLegacyRefreshToken(): void {
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
}

export function getStoredUserData(): unknown | null {
  const data = localStorage.getItem(USER_DATA_KEY)
  if (!data) return null
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

/** Fired on `window` whenever a fresh access token is stored (login or refresh). */
export const TOKEN_STORED_EVENT = "majlisna:token-stored"

/**
 * Call `listener` each time a fresh access token is stored, in this tab or in another
 * one (the `storage` event). The Socket.IO clients use it: the server refuses an expired
 * token and socket.io-client never retries a refused connection, so a socket that lost
 * its link after the token expired comes back only when there is a new token to show.
 * AuthProvider uses it to follow a refresh another tab made. Returns the unsubscribe.
 */
export function onTokenStored(listener: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === TOKEN_KEY && event.newValue) listener()
  }
  window.addEventListener(TOKEN_STORED_EVENT, listener)
  window.addEventListener("storage", onStorage)
  return () => {
    window.removeEventListener(TOKEN_STORED_EVENT, listener)
    window.removeEventListener("storage", onStorage)
  }
}

/**
 * Call `listener` when another tab ended the session (logout, or a refused refresh):
 * its access token disappeared from the storage the tabs share. Returns the unsubscribe.
 */
export function onSessionEndedElsewhere(listener: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    // `key` is null for a `localStorage.clear()`
    if ((event.key === TOKEN_KEY || event.key === null) && !event.newValue && !localStorage.getItem(TOKEN_KEY)) listener()
  }
  window.addEventListener("storage", onStorage)
  return () => window.removeEventListener("storage", onStorage)
}

/**
 * Whether this browser holds a session to resume: the session marker, an access token,
 * or a refresh token the old client stored. Without any of them there is no session to
 * ask `/auth/me` about, and a logged-out visitor's page load does not spend a request
 * on a 401.
 */
export function hasStoredSession(): boolean {
  return !!(localStorage.getItem(SESSION_MARKER_KEY) || localStorage.getItem(TOKEN_KEY) || localStorage.getItem(LEGACY_REFRESH_TOKEN_KEY))
}

/**
 * Store a fresh access token (login, register, Google sign-in, refresh). The refresh token
 * that came with it stays in its httpOnly cookie, and a legacy copy is dropped: the cookie
 * the same answer set has replaced it.
 */
export function storeAuthData(accessToken: string, expiresIn: number, userData?: unknown): void {
  const expiryTime = Date.now() + expiresIn * 1000
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiryTime))
  localStorage.setItem(SESSION_MARKER_KEY, "1")
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
  localStorage.removeItem(REFRESH_BLOCKED_UNTIL_KEY)
  if (userData) {
    localStorage.setItem(USER_DATA_KEY, JSON.stringify(userData))
  }
  window.dispatchEvent(new Event(TOKEN_STORED_EVENT))
}

export function clearAuthData(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(LEGACY_REFRESH_TOKEN_KEY)
  localStorage.removeItem(TOKEN_EXPIRY_KEY)
  localStorage.removeItem(USER_DATA_KEY)
  localStorage.removeItem(SESSION_MARKER_KEY)
  localStorage.removeItem(REFRESH_BLOCKED_UNTIL_KEY)
}

export function getTokenExpiry(): number | null {
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY)
  return expiry ? parseInt(expiry, 10) : null
}

/** A token is refreshed this long before its expiry, and judged stale from then on. */
export const REFRESH_BUFFER_MS = 60 * 1000

/** Whether the stored access token still has more than the refresh buffer to live. */
export function accessTokenIsFresh(now = Date.now()): boolean {
  const expiry = getTokenExpiry()
  return !!getStoredToken() && expiry != null && expiry - now > REFRESH_BUFFER_MS
}

/**
 * Whether presenting the stored access token would only earn a 401: there is none (a
 * session the cookie alone holds), or it is past, or within the buffer of, its expiry.
 * A token with no recorded expiry is not judged.
 */
export function accessTokenIsStale(now = Date.now()): boolean {
  const expiry = getTokenExpiry()
  return !getStoredToken() || (expiry != null && expiry - now <= REFRESH_BUFFER_MS)
}

/** How long the server asked not to be asked for a refresh, from now (0: ask away). */
export function refreshBlockedForMs(now = Date.now()): number {
  const until = Number(localStorage.getItem(REFRESH_BLOCKED_UNTIL_KEY))
  return Number.isFinite(until) && until > now ? until - now : 0
}

export function blockRefreshFor(ms: number, now = Date.now()): void {
  localStorage.setItem(REFRESH_BLOCKED_UNTIL_KEY, String(now + ms))
}

/** Leave the "you were signed out" notice for the page the player is sent to. */
export function noteSessionRevoked(): void {
  try {
    sessionStorage.setItem(AUTH_NOTICE_KEY, "sessionRevoked")
  } catch {
    // storage blocked: the login page simply says nothing
  }
}

/** The notice left for this page, if any; reading it clears it. */
export function takeAuthNotice(): AuthNotice | null {
  try {
    const notice = sessionStorage.getItem(AUTH_NOTICE_KEY)
    sessionStorage.removeItem(AUTH_NOTICE_KEY)
    return notice === "sessionRevoked" ? notice : null
  } catch {
    return null
  }
}

/**
 * Send the player to the login page, coming back to where they were. A full load on
 * purpose: it is called from outside React (the API client) and after a session ended,
 * when nothing on the page should survive.
 */
export function sendToLogin(): void {
  const back = window.location.pathname + window.location.search
  window.location.assign(`/auth/login?redirect=${encodeURIComponent(back)}`)
}

/**
 * Drop a token from the address bar, keeping the rest of it and the router's history
 * state. The reset and verification pages call it right after reading `?token=`, so
 * the browser history, an analytics page view and a screenshot never hold a token that
 * still works (SEC F06). TanStack Router hears the change (it wraps replaceState), so
 * the page must keep the token it read in memory.
 */
export function scrubTokenFromUrl(param = "token"): void {
  const url = new URL(window.location.href)
  if (!url.searchParams.has(param)) return
  url.searchParams.delete(param)
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`)
}
