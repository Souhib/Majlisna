import { HTTPError, type NormalizedOptions } from "ky"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The error reporter (FR-9, FP-03): the Sentry SDK is ~23 kB gzip, so it is imported after
 * the first paint, and whatever fails before that waits in a short queue.
 */
type Module = typeof import("./report-error")

function fakeSdk() {
  return { init: vi.fn(), captureException: vi.fn() }
}

/** A fresh copy of the module, as a page load gets. */
async function freshModule(): Promise<Module> {
  vi.resetModules()
  return import("./report-error")
}

/** Lets the idle callback's dynamic import and its then() settle. */
async function settle() {
  for (let i = 0; i < 5; i++) await Promise.resolve()
}

function httpError(status: number): HTTPError {
  return new HTTPError(new Response(null, { status }), new Request("http://localhost/api/v1/rooms"), {} as NormalizedOptions)
}

describe("report-error", () => {
  beforeEach(() => {
    vi.spyOn(console, "error").mockImplementation(() => {})
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("loads the SDK only once the page is idle, and sends what failed before, in order", async () => {
    // Prepare
    const { reportError, startErrorReporting } = await freshModule()
    const sdk = fakeSdk()
    const loadSdk = vi.fn(async () => sdk)
    let idle: (() => void) | undefined
    startErrorReporting({ dsn: "https://key@errors.example/7", loadSdk, whenIdle: (run) => (idle = run) })
    const first = new Error("first")
    const second = new Error("second")

    // Act: two failures before the first paint is over
    reportError(first, { source: "Query failed", extra: { queryKey: ["a"] } })
    reportError(second)

    // Assert: nothing downloaded yet
    expect(loadSdk).not.toHaveBeenCalled()

    // Act: the page goes idle
    idle?.()
    await settle()

    // Assert: initialised with the DSN, then the queue sent in order
    expect(sdk.init).toHaveBeenCalledWith(expect.objectContaining({ dsn: "https://key@errors.example/7" }))
    expect(sdk.captureException.mock.calls.map(([error]) => error)).toEqual([first, second])
    expect(sdk.captureException.mock.calls[0][1]).toEqual(expect.objectContaining({ extra: { queryKey: ["a"] } }))
  })

  it("sends later reports straight to the SDK", async () => {
    // Prepare
    const { reportError, startErrorReporting } = await freshModule()
    const sdk = fakeSdk()
    startErrorReporting({ dsn: "https://key@errors.example/7", loadSdk: async () => sdk, whenIdle: (run) => run() })
    await settle()
    const error = new Error("late")

    // Act
    reportError(error, { source: "ErrorBoundary caught" })

    // Assert
    expect(sdk.captureException).toHaveBeenCalledTimes(1)
    expect(sdk.captureException).toHaveBeenCalledWith(error, expect.objectContaining({ tags: { source: "ErrorBoundary caught" } }))
    expect(console.error).toHaveBeenCalledWith("ErrorBoundary caught:", error)
  })

  it("keeps the page's own uncaught errors until the SDK takes over, then lets the SDK catch them", async () => {
    // Prepare
    const { startErrorReporting } = await freshModule()
    const sdk = fakeSdk()
    let idle: (() => void) | undefined
    startErrorReporting({ dsn: "https://key@errors.example/7", loadSdk: async () => sdk, whenIdle: (run) => (idle = run) })
    const thrown = new Error("thrown at boot")
    const rejected = new Error("rejected at boot")

    // Act: an uncaught error and an unhandled rejection before the SDK is there
    window.dispatchEvent(new ErrorEvent("error", { error: thrown, message: thrown.message }))
    window.dispatchEvent(Object.assign(new Event("unhandledrejection"), { reason: rejected }))
    idle?.()
    await settle()

    // Assert: both were kept and sent
    expect(sdk.captureException.mock.calls.map(([error]) => error)).toEqual([thrown, rejected])

    // Act: once the SDK is in, its own global handlers catch the next one
    window.dispatchEvent(new ErrorEvent("error", { error: new Error("after"), message: "after" }))

    // Assert: not sent a second time by us
    expect(sdk.captureException).toHaveBeenCalledTimes(2)
  })

  it("without a DSN never downloads the SDK and keeps nothing", async () => {
    // Prepare
    const { reportError, startErrorReporting } = await freshModule()
    const loadSdk = vi.fn(async () => fakeSdk())
    startErrorReporting({ dsn: "", loadSdk, whenIdle: (run) => run() })
    const error = new Error("no tracker")

    // Act
    reportError(error, { source: "Mutation failed" })
    await settle()

    // Assert: said in the console, nothing else
    expect(loadSdk).not.toHaveBeenCalled()
    expect(console.error).toHaveBeenCalledWith("Mutation failed:", error)
  })

  it("keeps at most a short queue while the SDK loads", async () => {
    // Prepare
    const { reportError, startErrorReporting, MAX_QUEUED_REPORTS } = await freshModule()
    const sdk = fakeSdk()
    let idle: (() => void) | undefined
    startErrorReporting({ dsn: "https://key@errors.example/7", loadSdk: async () => sdk, whenIdle: (run) => (idle = run) })

    // Act: a loop of failures before the SDK is in
    for (let i = 0; i < MAX_QUEUED_REPORTS + 30; i++) reportError(new Error(`e${i}`))
    idle?.()
    await settle()

    // Assert: the first ones (the cause, usually), and no more
    expect(sdk.captureException).toHaveBeenCalledTimes(MAX_QUEUED_REPORTS)
    expect((sdk.captureException.mock.calls[0][0] as Error).message).toBe("e0")
  })

  it("gives up quietly when the SDK cannot be downloaded", async () => {
    // Prepare
    const { reportError, startErrorReporting } = await freshModule()
    startErrorReporting({
      dsn: "https://key@errors.example/7",
      loadSdk: () => Promise.reject(new TypeError("Failed to fetch dynamically imported module")),
      whenIdle: (run) => run(),
    })
    await settle()

    // Act / Assert: reporting still never throws
    expect(() => reportError(new Error("after the failed load"))).not.toThrow()
    expect(console.warn).toHaveBeenCalledTimes(1)
  })

  it("treats a 4xx as the server's verdict, and anything else as a fault", async () => {
    // Prepare
    const { isReportableRequestError } = await freshModule()

    // Act / Assert
    expect(isReportableRequestError(httpError(400))).toBe(false)
    expect(isReportableRequestError(httpError(401))).toBe(false)
    expect(isReportableRequestError(httpError(404))).toBe(false)
    expect(isReportableRequestError(httpError(429))).toBe(false)
    expect(isReportableRequestError(httpError(500))).toBe(true)
    expect(isReportableRequestError(httpError(502))).toBe(true)
    expect(isReportableRequestError(new TypeError("Failed to fetch"))).toBe(true)
    expect(isReportableRequestError(new Error("Cannot read properties of undefined"))).toBe(true)
  })

  it("names the running commit as the release, and no release in a build that names none", async () => {
    // Prepare: a production image (index.html stamped) and a development build
    const stamped = await freshModule()
    const stampedSdk = fakeSdk()
    stamped.startErrorReporting({ dsn: "https://key@errors.example/10", release: COMMIT, loadSdk: async () => stampedSdk, whenIdle: (run) => run() })
    const unstamped = await freshModule()
    const unstampedSdk = fakeSdk()
    unstamped.startErrorReporting({ dsn: "https://key@errors.example/10", loadSdk: async () => unstampedSdk, whenIdle: (run) => run() })

    // Act
    await settle()

    // Assert
    expect(stampedSdk.init).toHaveBeenCalledWith(expect.objectContaining({ dsn: "https://key@errors.example/10", release: COMMIT }))
    expect(unstampedSdk.init.mock.calls[0][0]).not.toHaveProperty("release")
  })

  it("reads the release from the page's majlisna-release meta, and only a commit", async () => {
    // Prepare
    const { readRelease } = await freshModule()

    // Act / Assert
    expect(readRelease(pageStamped(COMMIT))).toBe(COMMIT)
    expect(readRelease(pageStamped("unknown"))).toBeUndefined()
    expect(readRelease(pageStamped(COMMIT.toUpperCase()))).toBeUndefined()
    expect(readRelease(pageStamped(COMMIT.slice(0, 7)))).toBeUndefined()
    expect(readRelease(pageStamped(` ${COMMIT}`))).toBeUndefined()
    expect(readRelease(pageStamped(null))).toBeUndefined()
  })
})

const COMMIT = "146c7ca180e4c1f2a80bb3771b075eae476ae5b5"

/** A page whose index.html the image stamped with `content` (null: no meta at all). */
function pageStamped(content: string | null): Document {
  const page = document.implementation.createHTMLDocument("Majlisna")
  if (content !== null) {
    const meta = page.createElement("meta")
    meta.name = "majlisna-release"
    meta.content = content
    page.head.append(meta)
  }
  return page
}
