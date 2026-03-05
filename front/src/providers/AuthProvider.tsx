import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react"
import apiClient from "@/api/client"
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
    const storedRefreshToken = localStorage.getItem("ipg-refresh-token")

    isRefreshingRef.current = true
    try {
      const response = await apiClient({
        method: "POST",
        url: "/api/v1/auth/refresh",
        // Send refresh token as param if available (cookie is sent automatically)
        params: storedRefreshToken ? { refresh_token: storedRefreshToken } : undefined,
      })

      const { access_token, refresh_token, expires_in } = response.data as {
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
        const response = await apiClient({
          method: "GET",
          url: "/api/v1/auth/me",
        })
        const userData = response.data as UserData
        setUser(userData)
        setToken("cookie-auth") // sentinel value — actual token is in httpOnly cookie
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
  }, [scheduleTokenRefresh])

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
      await apiClient({ method: "POST", url: "/api/v1/auth/logout" })
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
      localStorage.setItem("ipg-user-data", JSON.stringify(userData))
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
