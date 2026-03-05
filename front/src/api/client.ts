/**
 * Custom ky client for API requests.
 * Used by Kubb-generated hooks for type-safe API communication.
 */

import ky, { type HTTPError, type KyResponse } from "ky"
import i18n from "@/i18n"

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

/**
 * Extract a human-readable, translated error message from API errors.
 */
export function getApiErrorMessage(error: unknown, fallback = "An error occurred"): string {
  if (!error) return fallback

  const responseError = error as ResponseErrorConfig<ApiErrorResponse>
  const data = responseError?.response?.data

  // 1. Try i18n translation via error_key
  if (data?.error_key) {
    const translated = i18n.t(data.error_key, {
      ...data.error_params,
      defaultValue: "",
    })
    if (translated) return translated
  }

  // 2. Fall back to frontend_message
  if (typeof data?.frontend_message === "string" && data.frontend_message) {
    return data.frontend_message
  }

  // 3. Fall back to message field
  if (typeof data?.message === "string" && data.message) {
    return data.message
  }

  // 4. Fall back to detail field (FastAPI validation errors)
  const detail = data?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail) && detail.length > 0 && detail[0]?.msg) {
    return detail[0].msg
  }

  // 5. Handle standard Error objects
  if (error instanceof Error) return error.message || fallback

  return fallback
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
  credentials: "include",
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
        const token = localStorage.getItem("ipg-token")
        if (token) {
          request.headers.set("Authorization", `Bearer ${token}`)
        }
      },
    ],
    afterResponse: [
      async (_request, _options, response) => {
        if (!response.ok && response.status === 401) {
          const hadToken = !!localStorage.getItem("ipg-token")

          localStorage.removeItem("ipg-token")
          localStorage.removeItem("ipg-refresh-token")
          localStorage.removeItem("ipg-token-expiry")
          localStorage.removeItem("ipg-user-data")

          if (hadToken && typeof window !== "undefined" && !window.location.pathname.includes("/auth/login")) {
            window.location.href = "/auth/login"
          }
        }
        return response
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

async function client<TData, _TError = unknown, TVariables = unknown>(
  config: RequestConfig<TVariables>,
): Promise<ResponseConfig<TData>> {
  const { url = "", method = "GET", params, data, signal, headers } = config

  const searchParams = params ? serializeParams(params) : undefined
  const normalizedUrl = url.startsWith("/") ? url.slice(1) : url

  const options: Parameters<typeof kyInstance>[1] = {
    method: method.toLowerCase(),
    searchParams,
    signal,
    headers,
  }

  if (data && ["POST", "PUT", "PATCH"].includes(method)) {
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

  if (contentType?.includes("application/json")) {
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
