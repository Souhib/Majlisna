/**
 * The one door to the error tracker (GlitchTip, through the Sentry SDK).
 *
 * The SDK is about 23 kB gzip, so it is never on the critical path: `startErrorReporting`
 * (main.tsx) imports it once the page has loaded and gone idle, and only when the build
 * has a DSN (`VITE_SENTRY_DSN`). Until then every report, and the page's own uncaught
 * errors and unhandled rejections, wait in a short queue that is sent as soon as the SDK
 * is in; from then on the SDK's own global handlers catch the uncaught ones. Without a DSN
 * nothing is downloaded and a report is only said in the console.
 *
 * Callers: the error boundary, and the query and mutation caches (QueryProvider), which
 * skip a 4xx (`isReportableRequestError`): a refusal is the server's verdict, said on the
 * page, not a fault.
 *
 * Every event carries the release, the commit the image was built from (`readRelease`), so
 * the tracker tells which deploy it came from, as the backend's do (settings.git_sha).
 */

/** What a report carries besides the error: where it was caught, and anything that helps. */
export interface ReportContext {
  /** Where it was caught ("ErrorBoundary caught", "Query failed"…): the console line and a tag. */
  source?: string
  extra?: Record<string, unknown>
}

/** The part of `@sentry/react` this module uses. */
export interface ErrorTrackerSdk {
  init: (options: { dsn: string; release?: string; tracesSampleRate: number }) => unknown
  captureException: (error: unknown, hint?: { tags?: Record<string, string>; extra?: Record<string, unknown> }) => unknown
}

export interface StartOptions {
  dsn?: string
  /** The running commit (`readRelease()`); none in a build that names none. */
  release?: string
  /** How the SDK is fetched (a test passes a fake). */
  loadSdk?: () => Promise<ErrorTrackerSdk>
  /** When to fetch it (a test runs it by hand). Default: after `load`, when the page is idle. */
  whenIdle?: (run: () => void) => void
}

/** Reports kept while the SDK loads; the first ones, which are usually the cause. */
export const MAX_QUEUED_REPORTS = 20
/** The longest an idle callback may wait on a page that is never idle. */
const IDLE_TIMEOUT_MS = 5_000
/** Without requestIdleCallback (Safari), how long after `load` the SDK is fetched. */
const IDLE_FALLBACK_DELAY_MS = 1_500
const TRACES_SAMPLE_RATE = 0.1
/** index.html's meta that the image's last build step stamps with the commit (front/Dockerfile). */
const RELEASE_META_SELECTOR = 'meta[name="majlisna-release"]'
/** A commit: exactly 40 lowercase hex digits ("unknown" until the image stamps one). */
const COMMIT_PATTERN = /^[0-9a-f]{40}$/

type Pending = { error: unknown; context?: ReportContext }
type Phase = "waiting" | "loading" | "ready" | "off"

let phase: Phase = "waiting"
let sdk: ErrorTrackerSdk | null = null
let queue: Pending[] = []

function enqueue(pending: Pending) {
  if (queue.length < MAX_QUEUED_REPORTS) queue.push(pending)
}

function send(sdkNow: ErrorTrackerSdk, { error, context }: Pending) {
  try {
    sdkNow.captureException(error, {
      ...(context?.source ? { tags: { source: context.source } } : {}),
      ...(context?.extra ? { extra: context.extra } : {}),
    })
  } catch {
    // the tracker failing must never become the page's own error
  }
}

/** Report an error: always said in the console, sent to the tracker when there is one. */
export function reportError(error: unknown, context?: ReportContext): void {
  if (context?.source) console.error(`${context.source}:`, error)
  else console.error(error)
  if (phase === "ready" && sdk) send(sdk, { error, context })
  else if (phase === "waiting" || phase === "loading") enqueue({ error, context })
}

/**
 * The release of this build: the commit index.html's `majlisna-release` meta names, which the
 * image's last build step stamps (front/Dockerfile: the GIT_SHA build arg, else the clone's
 * git metadata). Undefined for anything but a commit: a development build says "unknown".
 */
export function readRelease(page: Document = document): string | undefined {
  const content = page.querySelector<HTMLMetaElement>(RELEASE_META_SELECTOR)?.content ?? ""
  return COMMIT_PATTERN.test(content) ? content : undefined
}

/** A request error worth reporting: anything but a 4xx answer (the server's verdict). */
export function isReportableRequestError(error: unknown): boolean {
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status
  return !(typeof status === "number" && status >= 400 && status < 500)
}

function onWindowError(event: ErrorEvent) {
  enqueue({ error: event.error ?? event.message, context: { source: "Uncaught error" } })
}

function onUnhandledRejection(event: PromiseRejectionEvent) {
  enqueue({ error: event.reason, context: { source: "Unhandled rejection" } })
}

function stopListening() {
  window.removeEventListener("error", onWindowError)
  window.removeEventListener("unhandledrejection", onUnhandledRejection)
}

function afterLoadWhenIdle(run: () => void) {
  const schedule = () => {
    if (typeof window.requestIdleCallback === "function") window.requestIdleCallback(run, { timeout: IDLE_TIMEOUT_MS })
    else setTimeout(run, IDLE_FALLBACK_DELAY_MS)
  }
  if (document.readyState === "complete") schedule()
  else window.addEventListener("load", schedule, { once: true })
}

function loadSentry(): Promise<ErrorTrackerSdk> {
  // destructured, so the bundler keeps only what these two need from the SDK
  return import("@sentry/react").then(({ init, captureException }) => ({ init, captureException }))
}

/**
 * Start reporting. With a DSN: listen for early uncaught errors, then fetch the SDK when the
 * page is idle, initialise it and send the queue. Without one: drop the queue, stay quiet.
 */
export function startErrorReporting({ dsn, release, loadSdk = loadSentry, whenIdle = afterLoadWhenIdle }: StartOptions = {}): void {
  if (phase !== "waiting") return
  if (!dsn) {
    phase = "off"
    queue = []
    return
  }
  phase = "loading"
  window.addEventListener("error", onWindowError)
  window.addEventListener("unhandledrejection", onUnhandledRejection)
  whenIdle(() => {
    loadSdk()
      .then((loaded) => {
        loaded.init({ dsn, tracesSampleRate: TRACES_SAMPLE_RATE, ...(release ? { release } : {}) })
        // the SDK's global handlers catch uncaught errors from here on
        stopListening()
        sdk = loaded
        phase = "ready"
        const pending = queue
        queue = []
        for (const report of pending) send(loaded, report)
      })
      .catch((error: unknown) => {
        stopListening()
        phase = "off"
        queue = []
        console.warn("The error tracker could not be loaded", error)
      })
  })
}
