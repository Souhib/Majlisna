const TOKEN_KEY = "majlisna-token"
const REFRESH_TOKEN_KEY = "majlisna-refresh-token"
const TOKEN_EXPIRY_KEY = "majlisna-token-expiry"
const USER_DATA_KEY = "majlisna-user-data"

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
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
 * Call `listener` each time a fresh access token is stored. The Socket.IO clients use
 * it: the server refuses an expired token and socket.io-client never retries a refused
 * connection, so a socket that lost its link after the token expired comes back only
 * when there is a new token to show. Returns the unsubscribe.
 */
export function onTokenStored(listener: () => void): () => void {
  window.addEventListener(TOKEN_STORED_EVENT, listener)
  return () => window.removeEventListener(TOKEN_STORED_EVENT, listener)
}

/**
 * Whether this browser holds a session to resume: a stored access or refresh token.
 * Every login writes both (next to the httpOnly cookies), so without either there is
 * no session to ask `/auth/me` about, and a logged-out visitor's page load does not
 * spend a request on a 401.
 */
export function hasStoredSession(): boolean {
  return !!(localStorage.getItem(TOKEN_KEY) || localStorage.getItem(REFRESH_TOKEN_KEY))
}

export function storeAuthData(accessToken: string, refreshToken: string, expiresIn: number, userData?: unknown): void {
  const expiryTime = Date.now() + expiresIn * 1000
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiryTime))
  if (userData) {
    localStorage.setItem(USER_DATA_KEY, JSON.stringify(userData))
  }
  window.dispatchEvent(new Event(TOKEN_STORED_EVENT))
}

export function clearAuthData(): void {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(REFRESH_TOKEN_KEY)
  localStorage.removeItem(TOKEN_EXPIRY_KEY)
  localStorage.removeItem(USER_DATA_KEY)
}

export function getTokenExpiry(): number | null {
  const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY)
  return expiry ? parseInt(expiry, 10) : null
}
