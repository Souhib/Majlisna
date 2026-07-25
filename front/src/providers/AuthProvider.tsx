import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react"
import { getMeApiV1AuthMeGet, refreshTokenApiV1AuthRefreshPost, logoutApiV1AuthLogoutPost } from "@/api/generated"
import {
  clearAuthData,
  getStoredToken,
  getStoredUserData,
  getTokenExpiry,
  storeAuthData,
} from "@/lib/auth"

interface UserData {
  id: string
  username: string
  email: string
  is_active: boolean
  is_admin: boolean
}

interface AuthContextValue {
  isAuthenticated: boolean
  isLoading: boolean
  user: UserData | null
  token: string | null
  login: (accessToken: string, refreshToken: string, expiresIn: number, userData?: UserData) => void
  logout: () => void
  setUser: (user: UserData | null) => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

const REFRESH_BUFFER_MS = 60 * 1000

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<UserData | null>(null)
  const refreshTimerRef = useRef<number | null>(null)
  const isRefreshingRef = useRef(false)

  const refreshAccessToken = useCallback(async (): Promise<boolean> => {
    if (isRefreshingRef.current) return false
    const storedRefreshToken = localStorage.getItem("majlisna-refresh-token")

    isRefreshingRef.current = true
    try {
      let data: unknown
      try {
        data = await refreshTokenApiV1AuthRefreshPost(
          storedRefreshToken ? { refresh_token: storedRefreshToken } : undefined,
        )
      } catch (bodyTokenError) {
        // The backend prefers the token in the body over the httpOnly cookie, so
        // a stale localStorage value shadows a perfectly good refresh cookie.
        // Retry cookie-only before giving up and logging the user out.
        if (!storedRefreshToken) throw bodyTokenError
        data = await refreshTokenApiV1AuthRefreshPost(undefined)
      }

      const { access_token, refresh_token, expires_in } = data as {
        access_token: string
        refresh_token: string
        expires_in: number
      }

      storeAuthData(access_token, refresh_token, expires_in)
      setToken(access_token)
      return true
    } catch {
      return false
    } finally {
      isRefreshingRef.current = false
    }
  }, [])

  const scheduleTokenRefresh = useCallback(
    (expiryTime: number) => {
      if (refreshTimerRef.current) {
        clearTimeout(refreshTimerRef.current)
      }

      const now = Date.now()
      const refreshTime = expiryTime - REFRESH_BUFFER_MS
      const delay = refreshTime - now

      if (delay <= 0) {
        refreshAccessToken().then((success) => {
          if (!success) {
            clearAuthData()
            setToken(null)
            setUser(null)
          }
        })
        return
      }

      refreshTimerRef.current = setTimeout(async () => {
        const success = await refreshAccessToken()
        if (success) {
          const newExpiry = getTokenExpiry()
          if (newExpiry) scheduleTokenRefresh(newExpiry)
        } else {
          clearAuthData()
          setToken(null)
          setUser(null)
        }
      }, delay)
    },
    [refreshAccessToken],
  )

  // Initialize auth state — try /me endpoint (uses cookies), fall back to localStorage
  useEffect(() => {
    const initAuth = async () => {
      // First, try cookie-based auth via /me
      try {
        const userData = await getMeApiV1AuthMeGet() as UserData
        setUser(userData)

        // Mint a fresh token pair right away and schedule the next refresh from
        // its expires_in.
        //
        // This path used to just set a "cookie-auth" sentinel and return, which
        // scheduled NO refresh at all. Every reloaded tab therefore ran on the
        // access token it happened to find — and once that expired (15 min in
        // production) the very next request 401'd and the response interceptor
        // bounced the player to the login page, mid-game. It also left a stale
        // token in localStorage, which is what useSocket authenticates the
        // Socket.IO handshake with, so real-time silently degraded to 2s polling.
        const refreshed = await refreshAccessToken()
        if (refreshed) {
          const expiry = getTokenExpiry()
          if (expiry) scheduleTokenRefresh(expiry)
        } else {
          setToken("cookie-auth") // sentinel — the access token lives in the httpOnly cookie
        }
        setIsLoading(false)
        return
      } catch {
        // Cookie auth failed, try localStorage fallback
      }

      // Fallback: localStorage tokens (for transition compatibility)
      const storedToken = getStoredToken()
      const storedUserData = getStoredUserData() as UserData | null
      const storedExpiry = getTokenExpiry()

      if (storedToken) {
        setToken(storedToken)
        if (storedUserData) setUser(storedUserData)
        if (storedExpiry) scheduleTokenRefresh(storedExpiry)
      }

      setIsLoading(false)
    }

    initAuth()

    return () => {
      if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    }
  }, [refreshAccessToken, scheduleTokenRefresh])

  // Refresh on tab refocus when the token is at/near expiry.
  //
  // setTimeout is throttled (or frozen) in a backgrounded tab, so the scheduled
  // refresh above is not reliable on mobile — which is where a party game spends
  // most of its time. Without this, coming back to the tab after a phone call
  // lands on an expired token and an immediate forced logout.
  useEffect(() => {
    const handleVisibilityChange = async () => {
      if (document.visibilityState !== "visible") return
      const expiry = getTokenExpiry()
      if (!expiry) return
      if (expiry - Date.now() > REFRESH_BUFFER_MS) return

      const success = await refreshAccessToken()
      if (success) {
        const newExpiry = getTokenExpiry()
        if (newExpiry) scheduleTokenRefresh(newExpiry)
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange)
  }, [refreshAccessToken, scheduleTokenRefresh])

  const login = useCallback(
    (accessToken: string, refreshToken: string, expiresIn: number, userData?: UserData) => {
      storeAuthData(accessToken, refreshToken, expiresIn, userData)
      setToken(accessToken)
      if (userData) setUser(userData)

      const expiryTime = Date.now() + expiresIn * 1000
      scheduleTokenRefresh(expiryTime)
    },
    [scheduleTokenRefresh],
  )

  const logout = useCallback(async () => {
    if (refreshTimerRef.current) {
      clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
    // Call backend logout to clear cookies
    try {
      await logoutApiV1AuthLogoutPost()
    } catch {
      // Ignore — we clear local state regardless
    }
    clearAuthData()
    setToken(null)
    setUser(null)
  }, [])

  const setUserData = useCallback((userData: UserData | null) => {
    setUser(userData)
    if (userData) {
      localStorage.setItem("majlisna-user-data", JSON.stringify(userData))
    }
  }, [])

  const isAuthenticated = !!token

  return (
    <AuthContext.Provider
      value={{
        isAuthenticated,
        isLoading,
        user,
        token,
        login,
        logout,
        setUser: setUserData,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
