/**
 * A fake server behind `fetch`, for the tests that run the real ky client (api/client.ts)
 * and the real auth storage (lib/auth.ts): every request is recorded, and answered by the
 * responses queued for its "METHOD /path" (the last one repeats). An unregistered route
 * answers 404.
 *
 *   const server = installFakeFetch()
 *   server.on("POST /api/v1/auth/refresh", json(200, { access_token: "new", expires_in: 900 }))
 *   server.on("GET /api/v1/rooms", json(401, { error_key: "errors.api.tokenExpired" }), json(200, []))
 *   server.calls("POST /api/v1/auth/refresh") // what was sent
 */
import { vi } from "vitest"

export interface RecordedCall {
  method: string
  path: string
  /** The Authorization header, if any. */
  authorization: string | null
  credentials: RequestCredentials
  /** The parsed JSON body, or null without one. */
  body: unknown
}

type Answer = (request: Request) => Response | Promise<Response>

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Answer {
  return () => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } })
}

export function html(status: number, body = "<html><body>Bad Gateway</body></html>"): Answer {
  return () => new Response(body, { status, headers: { "content-type": "text/html" } })
}

/** No answer at all: what `fetch` does offline. */
export function offline(): Answer {
  return () => {
    throw new TypeError("Failed to fetch")
  }
}

/** An answer that waits until `release()` is called, to hold requests in flight. */
export function held(answer: Answer): { answer: Answer; release: () => void } {
  let release = () => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  return {
    answer: async (request) => {
      await gate
      return answer(request)
    },
    release: () => release(),
  }
}

export function installFakeFetch() {
  const routes = new Map<string, Answer[]>()
  const recorded: RecordedCall[] = []

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = input instanceof Request ? input : new Request(input, init)
    const url = new URL(request.url)
    const text = await request.clone().text()
    recorded.push({
      method: request.method,
      path: url.pathname,
      authorization: request.headers.get("authorization"),
      credentials: request.credentials,
      body: text ? JSON.parse(text) : null,
    })
    const queue = routes.get(`${request.method} ${url.pathname}`)
    if (!queue || queue.length === 0)
      return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404, headers: { "content-type": "application/json" } })
    const answer = queue.length > 1 ? (queue.shift() as Answer) : queue[0]
    return answer(request)
  })
  vi.stubGlobal("fetch", fetchMock)

  return {
    fetchMock,
    /** Queue the answers of a route, in order; the last one repeats. */
    on(route: string, ...answers: Answer[]) {
      routes.set(route, answers)
    },
    /** Every recorded call, or those of one route ("METHOD /path"). */
    calls(route?: string): RecordedCall[] {
      return route ? recorded.filter((c) => `${c.method} ${c.path}` === route) : [...recorded]
    },
    /** The routes called, in order ("METHOD /path"). */
    order(): string[] {
      return recorded.map((c) => `${c.method} ${c.path}`)
    },
  }
}

export type FakeServer = ReturnType<typeof installFakeFetch>

/** Every value in localStorage (a Storage's items are not its own properties, so no spread). */
export function storedValues(): string[] {
  return Array.from({ length: localStorage.length }, (_, i) => localStorage.getItem(localStorage.key(i) ?? "") ?? "")
}
