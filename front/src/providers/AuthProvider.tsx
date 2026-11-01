import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { isSessionRevokedError, refreshSession, type RefreshOutcome, type ResponseErrorConfig } from "@/api/client"
import { getMeApiV1AuthMeGet, logoutApiV1AuthLogoutPost } from "@/api/generated"
import type { UserView } from "@/api/generated"
import i18n from "@/i18n"
import {
  accessTokenIsFresh,
  accessTokenIsStale,
  clearAuthData,
  getStoredToken,
  getStoredUserData,
  getTokenExpiry,
  hasStoredSession,
  noteSessionRevoked,
  onSessionEndedElsewhere,
  onTokenStored,
  REFRESH_BUFFER_MS,
  sendToLogin,
  storeAuthData,
  takeAuthNotice,
} from "@/lib/auth"

/**
 * The shape the app actually gets back from the API.
 *
 * `is_active` and `is_admin` used to be declared here too, and every call site
 * fabricated them (`is_admin: false` at login, `updated.is_admin` from a PATCH
 * response that has no such field). The backend's UserView has never carried
 * either one, so both were permanently `undefined` behind a `boolean` type — a
 * lie waiting for the first piece of code that trusted it. Authorization is
 * decided server-side; see get_current_admin_user.
 */
interface UserData {
  id: string
  username: string
  email: string
}

/**
 * `GET /auth/me` answers a `UserView`, which names the address `email_address`; the
 * login and register responses (and `UserData`) say `email`. The cookie path used to
 * cast the view straight to `UserData`, so after any reload `user.email` was
 * `undefined` and the profile never showed the address.
 */
export function userFromView(view: Pick<UserView, "id" | "username" | "email_address">): UserData {
  return { id: view.id, username: view.username ?? "", email: view.email_address }
}

interface AuthContextValue {
  isAuthenticated: boolean
  isLoading: boolean
  user: UserData | null
  token: string | null
  /**
   * Open the session a login answered. There is no refresh token to hand over: the answer
   * set it as an httpOnly cookie, its only carrier, and no body holds one (SEC F13).
   */
  login: (accessToken: string, expiresIn: number, userData?: UserData) => void
  logout: () => void
  setUser: (user: UserData | null) => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

/** Signed in while the access token lives only in the httpOnly cookie (nothing stored here yet). */
const COOKIE_AUTH = "cookie-auth"
/** A refresh that got no verdict is tried again after 5 s, 10 s, 20 s… up to 5 min (or the server's Retry-After). */
const REFRESH_RETRY_BASE_MS = 5_000
const REFRESH_RETRY_MAX_MS = 5 * 60_000
/** Spreads the retries of the phones of one majlis, which all hit the same limit together. */
const REFRESH_RETRY_JITTER_MS = 1_000

function statusOf(error: unknown): number | undefined {
  return (error as ResponseErrorConfig | null)?.response?.status
}

interface AuthProviderProps {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [token, setToken] = useState<string | null>(null)
  const [user, setUser] = useState<UserData | null>(null)
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Refreshes in a row that got no verdict: the backoff's exponent. */
  const retryAttemptRef = useRef(0)
  /** The latest `refreshNow`, for the timer (the two refer to each other). */
  const refreshNowRef = useRef<() => Promise<void>>(async () => {})

  const clearTimer = useCallback(() => {
    if (refreshTimerRef.current) clearTimeout(refreshTimerRef.current)
    refreshTimerRef.current = null
  }, [])

  const scheduleIn = useCallback(
    (delayMs: number) => {
      clearTimer()
      refreshTimerRef.current = setTimeout(
        () => {
          refreshTimerRef.current = null
          void refreshNowRef.current()
        },
        Math.max(0, delayMs),
      )
    },
    [clearTimer],
  )

  /** The next refresh, the buffer before the stored token expires. */
  const scheduleFromExpiry = useCallback(() => {
    const expiry = getTokenExpiry()
    if (expiry != null) scheduleIn(expiry - REFRESH_BUFFER_MS - Date.now())
  }, [scheduleIn])

  /**
   * A refresh got no verdict (a rate limit, a deploy, no network): try again with backoff,
   * never sooner than the server's Retry-After. The session stands meanwhile. This used to
   * fall back to the "cookie-auth" sentinel with nothing scheduled, and the next request
   * after the access token expired logged the player out (FR-3).
   */
  const scheduleRetry = useCallback(
    (retryAfterMs: number | null) => {
      const backoff = Math.min(REFRESH_RETRY_MAX_MS, REFRESH_RETRY_BASE_MS * 2 ** retryAttemptRef.current)
      retryAttemptRef.current += 1
      scheduleIn(Math.max(backoff, retryAfterMs ?? 0) + Math.random() * REFRESH_RETRY_JITTER_MS)
    },
    [scheduleIn],
  )

  /** The session is over. A revoked one sends the player to the login page, with the notice. */
  const endSession = useCallback(
    (revoked: boolean) => {
      clearTimer()
      clearAuthData()
      setToken(null)
      setUser(null)
      if (!revoked) return
      if (window.location.pathname.startsWith("/auth/")) {
        toast.info(i18n.t("auth.sessionRevoked"), { id: "session-revoked" })
        return
      }
      noteSessionRevoked()
      sendToLogin()
    },
    [clearTimer],
  )

  /** Carry on with what this browser stored, while the server cannot be asked. */
  const resumeFromStorage = useCallback(() => {
    const stored = getStoredToken()
    const storedUser = getStoredUserData() as UserData | null
    if (stored) setToken(stored)
    if (storedUser) setUser(storedUser)
  }, [])

  /** Act on a refresh's outcome; true when there is a fresh token. */
  const settle = useCallback(
    (outcome: RefreshOutcome): boolean => {
      if (outcome.status === "ok") {
        retryAttemptRef.current = 0
        setToken(getStoredToken())
        scheduleFromExpiry()
        return true
      }
      if (outcome.status === "unauthorized") endSession(outcome.revoked)
      else scheduleRetry(outcome.retryAfterMs)
      return false
    },
    [endSession, scheduleFromExpiry, scheduleRetry],
  )

  const refreshNow = useCallback(async () => {
    // another tab refreshed since this timer was set: follow its token
    if (accessTokenIsFresh()) {
      setToken(getStoredToken())
      scheduleFromExpiry()
      return
    }
    settle(await refreshSession({ staleToken: getStoredToken() }))
  }, [scheduleFromExpiry, settle])

  useEffect(() => {
    refreshNowRef.current = refreshNow
  }, [refreshNow])

  /** Keep the token alive: schedule its refresh, or, with no known expiry, refresh now in the background. */
  const keepFresh = useCallback(() => {
    if (accessTokenIsFresh()) scheduleFromExpiry()
    else void refreshNow()
  }, [refreshNow, scheduleFromExpiry])

  // The notice a previous page left for this one ("You were signed out"), said once.
  useEffect(() => {
    if (takeAuthNotice() === "sessionRevoked") toast.info(i18n.t("auth.sessionRevoked"), { id: "session-revoked" })
  }, [])

  // Resume the session at load.
  useEffect(() => {
    const initAuth = async () => {
      // A visitor with nothing stored has never signed in here: asking /me only
      // answered 401 on every public page load and logged an error in the console.
      if (!hasStoredSession()) {
        setIsLoading(false)
        return
      }

      // A returning visitor whose access token has expired (the normal state after an
      // hour away: the access cookie expires with it) is refreshed BEFORE /me. Asking /me
      // first sent the stale bearer and the refresh, still good, was never tried.
      let refreshed = false
      if (accessTokenIsStale()) {
        const outcome = await refreshSession({ staleToken: getStoredToken() })
        if (outcome.status === "unavailable") {
          // not refused, only not answered: the session stands, and is asked again
          resumeFromStorage()
          scheduleRetry(outcome.retryAfterMs)
          setIsLoading(false)
          return
        }
        if (!settle(outcome)) {
          setIsLoading(false)
          return
        }
        refreshed = true
      }

      for (;;) {
        try {
          setUser(userFromView(await getMeApiV1AuthMeGet()))
          break
        } catch (error) {
          if (statusOf(error) !== 401) {
            // /me got no answer (offline, a deploy): the stored session stands
            resumeFromStorage()
            keepFresh()
            setIsLoading(false)
            return
          }
          // a token the server refuses although it looked fresh earns ONE refresh
          if (refreshed || isSessionRevokedError(error)) {
            endSession(isSessionRevokedError(error))
            setIsLoading(false)
            return
          }
          refreshed = true
          const outcome = await refreshSession({ staleToken: getStoredToken() })
          if (outcome.status === "unavailable") {
            resumeFromStorage()
            scheduleRetry(outcome.retryAfterMs)
            setIsLoading(false)
            return
          }
          if (!settle(outcome)) {
            setIsLoading(false)
            return
          }
        }
      }

      // Signed in. A token with time left is not refreshed now, only scheduled: the page
      // used to wait for /me AND a refresh before its first data request (FP-11).
      setToken(getStoredToken() ?? COOKIE_AUTH)
      setIsLoading(false)
      keepFresh()
    }

    void initAuth()

    return clearTimer
  }, [clearTimer, endSession, keepFresh, resumeFromStorage, scheduleRetry, settle])

  // Follow a token stored elsewhere: the API client's 401 replay, or another tab's refresh
  // or login (the tabs share one storage and one refresh cookie).
  useEffect(
    () =>
      onTokenStored(() => {
        const stored = getStoredToken()
        if (!stored) return
        retryAttemptRef.current = 0
        setToken(stored)
        setUser((current) => current ?? (getStoredUserData() as UserData | null))
        scheduleFromExpiry()
      }),
    [scheduleFromExpiry],
  )

  // Another tab signed out (or its refresh was refused): so is this one.
  useEffect(
    () =>
      onSessionEndedElsewhere(() => {
        clearTimer()
        setToken(null)
        setUser(null)
      }),
    [clearTimer],
  )

  // Refresh on tab refocus when the token is at/near expiry.
  //
  // setTimeout is throttled (or frozen) in a backgrounded tab, so the scheduled
  // refresh above is not reliable on mobile — which is where a party game spends
  // most of its time. Without this, coming back to the tab after a phone call
  // lands on an expired token and an immediate forced logout.
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState !== "visible") return
      const expiry = getTokenExpiry()
      if (!expiry || expiry - Date.now() > REFRESH_BUFFER_MS) return
      void refreshNow()
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange)
  }, [refreshNow])

  const login = useCallback(
    (accessToken: string, expiresIn: number, userData?: UserData) => {
      storeAuthData(accessToken, expiresIn, userData)
      retryAttemptRef.current = 0
      setToken(accessToken)
      if (userData) setUser(userData)
      scheduleFromExpiry()
    },
    [scheduleFromExpiry],
  )

  const logout = useCallback(async () => {
    clearTimer()
    // The server ends the session (and clears the cookies): send it before forgetting it here.
    try {
      await logoutApiV1AuthLogoutPost()
    } catch {
      // Ignore — we clear local state regardless
    }
    clearAuthData()
    setToken(null)
    setUser(null)
  }, [clearTimer])

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
