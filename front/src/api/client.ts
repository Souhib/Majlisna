/**
 * Custom ky client for API requests.
 * Used by Kubb-generated hooks for type-safe API communication.
 */

import ky, { type HTTPError, type KyResponse, type NormalizedOptions } from "ky"
import i18n from "@/i18n"
import {
  accessTokenIsFresh,
  blockRefreshFor,
  clearAuthData,
  clearLegacyRefreshToken,
  getLegacyRefreshToken,
  getStoredToken,
  hasStoredSession,
  noteSessionRevoked,
  refreshBlockedForMs,
  sendToLogin,
  storeAuthData,
} from "@/lib/auth"
import { noteServerDate } from "@/lib/server-clock"

const API_BASE_URL = import.meta.env.VITE_API_URL || window.location.origin

export type RequestConfig<TData = unknown> = {
  url?: string
  method?: "GET" | "PUT" | "PATCH" | "POST" | "DELETE" | "OPTIONS" | "HEAD"
  params?: object
  data?: TData
  responseType?: "arraybuffer" | "blob" | "document" | "json" | "text" | "stream"
  signal?: AbortSignal
  headers?: Record<string, string>
}

export type ResponseConfig<TData = unknown> = {
  data: TData
  status: number
  statusText: string
}

export type ResponseErrorConfig<TError = unknown> = HTTPError & {
  response?: KyResponse & { data?: TError }
}

type ApiErrorResponse = {
  error?: string
  error_key?: string
  message?: string
  frontend_message?: string
  error_params?: Record<string, string | number>
  detail?: string | { type: string; loc: (string | number)[]; msg: string }[]
  timestamp?: string
}

/** The session was signed out on the server (logout, a password reset, a reused refresh token). */
export const SESSION_REVOKED_KEY = "errors.api.sessionRevoked"
/** A password re-checked by the action itself (password change, account deletion) was wrong. */
const INVALID_CREDENTIALS_KEY = "errors.api.invalidCredentials"

/**
 * Extract a human-readable, translated error message from API errors.
 *
 * Only the server's JSON envelope is ever read. A request that got no such answer (offline,
 * a timeout, the proxy's HTML 502 during a deploy) says the caller's fallback, or the
 * translated "connection lost" line: never ky's or the browser's own words ("Failed to
 * fetch", "Request failed with status code 502: POST http://…"), which are English and
 * name internal URLs (FR-8).
 */
export function getApiErrorMessage(error: unknown, fallback?: string): string {
  const data = (error as ResponseErrorConfig<ApiErrorResponse> | null)?.response?.data
  const envelope = data && typeof data === "object" ? data : null
  if (!envelope) return fallback ?? i18n.t("errors.network")

  // 1. Try i18n translation via error_key
  if (envelope.error_key) {
    const translated = i18n.t(envelope.error_key, {
      ...envelope.error_params,
      defaultValue: "",
    })
    if (translated) return translated
  }

  // 2. Fall back to frontend_message
  if (typeof envelope.frontend_message === "string" && envelope.frontend_message) {
    return envelope.frontend_message
  }

  // 3. Fall back to message field
  if (typeof envelope.message === "string" && envelope.message) {
    return envelope.message
  }

  // 4. Fall back to detail field (FastAPI validation errors)
  const detail = envelope.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) {
    return detail[0].msg
  }

  return fallback ?? i18n.t("common.error")
}

/** Whether a request got no API answer at all: offline, a timeout, or a proxy's own error page. */
export function gotNoApiAnswer(error: unknown): boolean {
  const data = (error as ResponseErrorConfig | null)?.response?.data
  return !(data && typeof data === "object")
}

/** Whether an API error says the session was revoked on the server. */
export function isSessionRevokedError(error: unknown): boolean {
  return (error as ResponseErrorConfig<ApiErrorResponse> | null)?.response?.data?.error_key === SESSION_REVOKED_KEY
}

/**
 * The auth endpoints. They set, read and clear the httpOnly cookies, so they are sent with
 * credentials (a cross-origin `VITE_API_URL`, like the E2E stack's :5049 beside :3049,
 * would otherwise never store or send them). Their own 401s belong to their callers:
 * `/auth/me` and `/auth/refresh` are AuthProvider's session probes, and `/auth/login`
 * answers a wrong password with one.
 */
const AUTH_PATH_PREFIX = "/api/v1/auth/"
const REFRESH_URL = "api/v1/auth/refresh"

function isAuthPath(path: string): boolean {
  return `/${path.replace(/^\//, "")}`.includes(AUTH_PATH_PREFIX)
}

/** Whether a 401 on `requestUrl` sends the visitor to the login page. */
export function redirectsToLoginOn401(requestUrl: string, { hadToken, pathname }: { hadToken: boolean; pathname: string }): boolean {
  if (!hadToken || pathname.includes("/auth/login")) return false
  return !isAuthPath(new URL(requestUrl, "http://localhost").pathname)
}

export type RefreshOutcome =
  | { status: "ok" }
  /** The server refused: the session is over. `revoked`: it was signed out on the server. */
  | { status: "unauthorized"; revoked: boolean }
  /** No verdict (a rate limit, a 5xx, no network): the session stands, ask again later. */
  | { status: "unavailable"; retryAfterMs: number | null }

/** A tab waits this long for another tab's refresh before refreshing anyway. */
const REFRESH_LOCK_WAIT_MS = 15_000
const REFRESH_LOCK_NAME = "majlisna-auth-refresh"
/** A Retry-After beyond this is read as this. */
const RETRY_AFTER_MAX_MS = 10 * 60 * 1000

/** The refresh in flight in this tab, shared by every caller (AuthProvider, the 401 replay). */
let refreshInFlight: Promise<RefreshOutcome> | null = null

/**
 * Mint a new access token from the refresh cookie. One refresh at a time per tab (a
 * concurrent caller gets the same promise) and, through Web Locks, per browser: two tabs
 * scheduled from the same shared expiry fire together, and every refresh rotates the
 * cookie (SEC F01), so the second tab waits, then finds the first one's token and asks
 * nothing. A browser without Web Locks relies on the server's reuse grace for that overlap.
 *
 * `staleToken` is the token the caller found wanting; when the stored one differs from it
 * and is fresh, someone else has refreshed meanwhile and the server is not asked.
 */
export function refreshSession({ staleToken }: { staleToken?: string | null } = {}): Promise<RefreshOutcome> {
  if (!refreshInFlight) {
    refreshInFlight = withRefreshLock(() => refreshUnlessDone(staleToken)).finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function withRefreshLock<T>(task: () => Promise<T>): Promise<T> {
  const locks = typeof navigator === "undefined" ? undefined : navigator.locks
  if (typeof locks?.request !== "function") return task()
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REFRESH_LOCK_WAIT_MS)
  let started = false
  try {
    return await locks.request(REFRESH_LOCK_NAME, { signal: controller.signal }, () => {
      started = true
      clearTimeout(timer)
      return task()
    })
  } catch (error) {
    if (started) throw error
    // A tab frozen in the background holds the lock: go ahead; the server's reuse grace covers an overlap.
    return task()
  } finally {
    clearTimeout(timer)
  }
}

async function refreshUnlessDone(staleToken: string | null | undefined): Promise<RefreshOutcome> {
  if (staleToken !== undefined) {
    const current = getStoredToken()
    if (current && current !== staleToken && accessTokenIsFresh()) return { status: "ok" }
  }
  // another tab ended the session while this one waited
  if (!hasStoredSession()) return { status: "unauthorized", revoked: false }
  const blockedMs = refreshBlockedForMs()
  if (blockedMs > 0) return { status: "unavailable", retryAfterMs: blockedMs }
  return requestNewToken()
}

/**
 * POST /auth/refresh with the cookie, and no token in the body. A session the old client
 * opened still has its refresh token in localStorage: it is sent once in the body, then
 * deleted as soon as the server has given a verdict (kept through a rate limit or an
 * outage, so the session survives them). A refused copy may only be stale beside a good
 * cookie, which is then tried, once.
 */
async function requestNewToken(): Promise<RefreshOutcome> {
  const legacy = getLegacyRefreshToken()
  let outcome = await postRefresh(legacy)
  if (legacy && outcome.status !== "unavailable") {
    clearLegacyRefreshToken()
    if (outcome.status === "unauthorized" && !outcome.revoked) outcome = await postRefresh(null)
  }
  return outcome
}

async function postRefresh(bodyToken: string | null): Promise<RefreshOutcome> {
  let response: KyResponse
  try {
    response = await kyInstance.post(REFRESH_URL, {
      credentials: "include",
      json: bodyToken ? { refresh_token: bodyToken } : undefined,
      throwHttpErrors: false,
      retry: 0,
    })
  } catch {
    return { status: "unavailable", retryAfterMs: null } // offline, or a timeout
  }
  if (response.ok) {
    const pair = (await response.json().catch(() => null)) as { access_token?: string; expires_in?: number } | null
    if (!pair?.access_token || typeof pair.expires_in !== "number") return { status: "unavailable", retryAfterMs: null }
    storeAuthData(pair.access_token, pair.expires_in)
    return { status: "ok" }
  }
  if (isRefusal(response.status)) {
    return { status: "unauthorized", revoked: (await errorKeyOf(response)) === SESSION_REVOKED_KEY }
  }
  const retryAfterMs = parseRetryAfter(response.headers.get("retry-after"))
  if (retryAfterMs) blockRefreshFor(retryAfterMs)
  return { status: "unavailable", retryAfterMs }
}

/** A 4xx is the server's verdict on the token; 408 and 429 are only "not now". */
function isRefusal(status: number): boolean {
  return status >= 400 && status < 500 && status !== 408 && status !== 429
}

function parseRetryAfter(value: string | null): number | null {
  if (!value) return null
  const seconds = Number(value)
  const ms = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(value) - Date.now()
  if (!Number.isFinite(ms) || ms <= 0) return null
  return Math.min(ms, RETRY_AFTER_MAX_MS)
}

async function errorKeyOf(response: Response): Promise<string | undefined> {
  const data = (await response
    .clone()
    .json()
    .catch(() => null)) as ApiErrorResponse | null
  return typeof data?.error_key === "string" ? data.error_key : undefined
}

function bearerTokenOf(request: Request): string | null {
  return request.headers.get("authorization")?.replace(/^Bearer /, "") ?? null
}

/** The session is over: forget it, and say so on the login page when the server revoked it. */
function endSession(requestUrl: string, revoked: boolean): void {
  const hadToken = hasStoredSession()
  clearAuthData()
  if (revoked) noteSessionRevoked()
  if (redirectsToLoginOn401(requestUrl, { hadToken, pathname: window.location.pathname })) sendToLogin()
}

/** Marks the one replay of a request after a refresh, which never refreshes again. */
const REPLAYED = "majlisnaReplayedAfterRefresh"

/**
 * A 401 on an ordinary request: the access token was refused (expired early, or a tab that
 * slept through its refresh). One refresh, shared by every request refused meanwhile, then
 * the request is replayed once with the new token. The session ends, and the player goes to
 * the login page, only when the refresh itself is refused, when the server says the session
 * was revoked (no refresh then: it cannot succeed), or when the replay is refused too. A
 * rate-limited or unanswered refresh fails this request and keeps the session: it used to
 * delete a refresh token that was still good and bounce the player out mid-game (FR-3).
 */
async function recoverFromRefusedToken(request: Request, options: NormalizedOptions, response: KyResponse): Promise<Response | undefined> {
  if (isAuthPath(new URL(request.url).pathname) || !hasStoredSession()) return undefined
  const key = await errorKeyOf(response)
  // a wrong password re-checked by the action (changing it, deleting the account): the form says so
  if (key === INVALID_CREDENTIALS_KEY) return undefined
  if (key === SESSION_REVOKED_KEY || options.context[REPLAYED]) {
    endSession(request.url, key === SESSION_REVOKED_KEY)
    return undefined
  }
  const outcome = await refreshSession({ staleToken: bearerTokenOf(request) })
  if (outcome.status === "ok") return kyInstance(request, { context: { [REPLAYED]: true }, throwHttpErrors: false })
  if (outcome.status === "unauthorized") endSession(request.url, outcome.revoked)
  return undefined
}

/**
 * Serialize params for FastAPI compatibility.
 */
function serializeParams(params: object): URLSearchParams {
  const searchParams = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === null || value === undefined) return
    if (Array.isArray(value)) {
      searchParams.append(key, value.join(","))
    } else {
      searchParams.append(key, String(value))
    }
  })
  return searchParams
}

const kyInstance = ky.create({
  prefixUrl: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  retry: {
    limit: 2,
    statusCodes: [408, 500, 502, 503, 504],
    methods: ["get", "head", "options"],
  },
  timeout: 30000,
  hooks: {
    beforeRequest: [
      (request) => {
        const token = getStoredToken()
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`)
        }
      },
    ],
    afterResponse: [
      async (request, options, response) => {
        // the server's clock, for timers and the Kalimat ladder (lib/server-clock)
        noteServerDate(response.headers.get("date"))
        if (response.status === 401) return recoverFromRefusedToken(request, options, response)
        return undefined
      },
    ],
    beforeError: [
      async (error) => {
        const { response } = error
        let responseData: unknown = null

        try {
          responseData = await response?.json()
        } catch {
          // Response is not JSON
        }

        if (response) {
          ;(error as ResponseErrorConfig).response = Object.assign(response, {
            data: responseData,
          })
        }

        return error
      },
    ],
  },
})

let clientConfig: Partial<RequestConfig<unknown>> = {}

async function client<TData, _TError = unknown, TVariables = unknown>(config: RequestConfig<TVariables>): Promise<ResponseConfig<TData>> {
  const { url = "", method = "GET", params, data, signal, headers } = config

  const searchParams = params ? serializeParams(params) : undefined
  const normalizedUrl = url.startsWith("/") ? url.slice(1) : url

  const options: Parameters<typeof kyInstance>[1] = {
    method: method.toLowerCase(),
    searchParams,
    signal,
    headers,
    ...(isAuthPath(normalizedUrl) ? { credentials: "include" as const } : {}),
  }

  // DELETE too: account deletion carries its confirmation (the password, or a Google
  // token) in the body, and dropping it made every deletion a 422 (WP-20, e2e account-delete)
  if (data && ["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    if (headers?.["Content-Type"] === "application/x-www-form-urlencoded") {
      const formData = new URLSearchParams()
      for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
        if (value !== undefined && value !== null) {
          formData.append(key, String(value))
        }
      }
      options.body = formData
    } else {
      options.json = data
    }
  }

  const response = await kyInstance(normalizedUrl, options)

  let responseData: TData
  const contentType = response.headers.get("content-type")

  if (response.status === 204 || response.status === 205) {
    // FastAPI labels a No Content answer application/json; there is no body to parse
    responseData = undefined as TData
  } else if (contentType?.includes("application/json")) {
    responseData = await response.json()
  } else if (contentType?.includes("text/")) {
    responseData = (await response.text()) as unknown as TData
  } else {
    responseData = (await response.blob()) as unknown as TData
  }

  return {
    data: responseData,
    status: response.status,
    statusText: response.statusText,
  }
}

client.getConfig = (): Partial<RequestConfig<unknown>> => {
  return clientConfig
}

client.setConfig = (config: RequestConfig<unknown>): Partial<RequestConfig<unknown>> => {
  clientConfig = config
  return clientConfig
}

export { client }
export default client
