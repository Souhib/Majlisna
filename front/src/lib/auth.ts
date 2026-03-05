const TOKEN_KEY = "ipg-token"
const REFRESH_TOKEN_KEY = "ipg-refresh-token"
const TOKEN_EXPIRY_KEY = "ipg-token-expiry"
const USER_DATA_KEY = "ipg-user-data"

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

export function storeAuthData(
  accessToken: string,
  refreshToken: string,
  expiresIn: number,
  userData?: unknown,
): void {
  const expiryTime = Date.now() + expiresIn * 1000
  localStorage.setItem(TOKEN_KEY, accessToken)
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
  localStorage.setItem(TOKEN_EXPIRY_KEY, String(expiryTime))
  if (userData) {
    localStorage.setItem(USER_DATA_KEY, JSON.stringify(userData))
  }
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
