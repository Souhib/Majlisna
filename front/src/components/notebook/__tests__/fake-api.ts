/**
 * A fake `@/api/client` for the notebook tests: the real generated functions and hooks
 * run, and every request is answered by a handler registered per "METHOD /url".
 * An unregistered route answers 404, so a test can assert what was (not) requested.
 *
 *   vi.mock("@/api/client", async () => (await import("./fake-api")).clientModule)
 *   answer("GET /api/v1/notebook/games/g1", () => gameWords)
 *   answer("POST /api/v1/notebook/games/g1/keep", () => { throw httpError(429, { error_key: "errors.api.rateLimitExceeded" }) })
 */
import { vi } from "vitest"

export interface FakeRequest {
  method: string
  url: string
  params?: Record<string, unknown>
  data?: unknown
}

type Handler = (request: FakeRequest) => unknown

const routes = new Map<string, Handler>()
export const requests: FakeRequest[] = []

export class FakeHttpError extends Error {
  response: { status: number; data: unknown }
  constructor(status: number, data: unknown = {}) {
    super(`HTTP ${status}`)
    this.response = { status, data }
  }
}

export function httpError(status: number, data: unknown = {}) {
  return new FakeHttpError(status, data)
}

export function answer(route: string, handler: Handler) {
  routes.set(route, handler)
}

export function resetFakeApi() {
  routes.clear()
  requests.length = 0
}

/** Requests made to a route ("METHOD /url"). */
export function requestsTo(route: string): FakeRequest[] {
  return requests.filter((r) => `${r.method} ${r.url}` === route)
}

const fakeClient = vi.fn(async (config: FakeRequest) => {
  requests.push(config)
  const handler = routes.get(`${config.method} ${config.url}`)
  if (!handler) throw httpError(404)
  return { data: await handler(config), status: 200, statusText: "OK" }
})

export const clientModule = {
  default: fakeClient,
  // the translated message is the error key in these tests (t returns keys)
  getApiErrorMessage: (err: unknown, fallback = "Error") =>
    ((err as FakeHttpError | null)?.response?.data as { error_key?: string } | undefined)?.error_key ?? fallback,
}

/** The generated notebook functions and hooks, for a `vi.mock("@/api/generated", …)` factory. */
export async function notebookGenerated() {
  return {
    ...(await import("@/api/generated/hooks/useGetNotebookGameWordsApiV1NotebookGamesGameIdGet")),
    ...(await import("@/api/generated/hooks/useKeepNotebookGameWordsApiV1NotebookGamesGameIdKeepPost")),
    ...(await import("@/api/generated/hooks/useKeepNotebookWordApiV1NotebookEntriesPost")),
    ...(await import("@/api/generated/hooks/useDeleteNotebookEntryApiV1NotebookEntriesEntryIdDelete")),
    ...(await import("@/api/generated/hooks/useListNotebookEntriesApiV1NotebookGet")),
  }
}
