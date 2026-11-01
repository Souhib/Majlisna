// @vitest-environment node
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it, vi } from "vitest"

/**
 * public/sw.js, run in a fake worker scope: its listeners are captured, `caches` is an
 * in-memory CacheStorage and `fetch` answers what each test says.
 */
const SOURCE = readFileSync(resolve(process.cwd(), "public/sw.js"), "utf8")
const SHELL_HTML = '<!doctype html><html><head></head><body><div id="root"></div></body></html>'

type Listener = (event: unknown) => void

function loadWorker(fetchImpl: (request: unknown) => Promise<Response>) {
  const listeners = new Map<string, Listener>()
  const stores = new Map<string, Map<string, Response>>()
  const cacheFor = (name: string) => {
    if (!stores.has(name)) stores.set(name, new Map())
    const store = stores.get(name) as Map<string, Response>
    return {
      put: vi.fn(async (key: string, response: Response) => void store.set(key, response)),
      addAll: vi.fn(async (keys: string[]) => keys.forEach((k) => store.set(k, new Response('<div id="root"></div> (install)')))),
      match: vi.fn(async (key: string) => store.get(key)?.clone()),
    }
  }
  const caches = {
    open: vi.fn(async (name: string) => cacheFor(name)),
    keys: vi.fn(async () => [...stores.keys()]),
    delete: vi.fn(async (name: string) => stores.delete(name)),
    match: vi.fn(async (key: string) => {
      for (const store of stores.values()) if (store.has(key)) return store.get(key)?.clone()
      return undefined
    }),
  }
  const self = {
    addEventListener: (type: string, listener: Listener) => listeners.set(type, listener),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  }
  new Function("self", "caches", "fetch", "Response", SOURCE)(self, caches, vi.fn(fetchImpl), Response)
  return { listeners, stores, caches }
}

/** Dispatches a fetch event and waits for everything the worker hands to the browser. */
async function navigate(listeners: Map<string, Listener>, url: string, mode = "navigate") {
  const pending: Promise<unknown>[] = []
  let answer: Promise<Response> | undefined
  listeners.get("fetch")?.({
    request: { url, mode },
    respondWith: (p: Promise<Response>) => {
      answer = p
      pending.push(p)
    },
    waitUntil: (p: Promise<unknown>) => pending.push(p),
  })
  // waitUntil may be called once the response is in: settle twice
  await Promise.allSettled(pending)
  await Promise.allSettled(pending)
  return answer
}

describe("service worker: the offline shell", () => {
  it("stores the fresh '/' from every successful navigation", async () => {
    // Prepare: a deploy has happened since the worker was installed
    const fresh = '<!doctype html><html><head><script src="/assets/index-NEW.js"></script></head><body><div id="root"></div></body></html>'
    const { listeners, caches } = loadWorker(async () => new Response(fresh, { status: 200, headers: { "content-type": "text/html" } }))

    // Act: an online navigation to any page of the app
    const response = await navigate(listeners, "https://majlisna.app/rooms")

    // Assert: the page got the network answer and the shell is the new build's
    expect(await response?.text()).toBe(fresh)
    const cached = await caches.match("/")
    expect(await cached?.text()).toBe(fresh)
  })

  it("answers an offline navigation with the stored shell", async () => {
    // Prepare: one online navigation, then the network goes away
    let online = true
    const { listeners } = loadWorker(async () => {
      if (!online) throw new TypeError("Failed to fetch")
      return new Response(SHELL_HTML, { status: 200, headers: { "content-type": "text/html" } })
    })
    await navigate(listeners, "https://majlisna.app/")
    online = false

    // Act
    const response = await navigate(listeners, "https://majlisna.app/today")

    // Assert
    expect(await response?.text()).toBe(SHELL_HTML)
  })

  it("never stores an error page or a page that is not the app (the API docs share the origin)", async () => {
    // Prepare
    const answers = [
      new Response("Bad gateway", { status: 502, headers: { "content-type": "text/html" } }),
      new Response("<!doctype html><title>Scalar</title><script id=api-reference></script>", { status: 200, headers: { "content-type": "text/html" } }),
    ]
    const { listeners, caches } = loadWorker(async () => answers.shift() as Response)
    const installed = await caches.match("/")

    // Act
    await navigate(listeners, "https://majlisna.app/rooms")
    await navigate(listeners, "https://majlisna.app/scalar")

    // Assert: the shell is still the one from install (none here), never the 502 or Scalar
    expect(installed).toBeUndefined()
    expect(await caches.match("/")).toBeUndefined()
  })

  it("leaves requests that are not navigations to the browser", async () => {
    // Prepare
    const fetchImpl = vi.fn(async () => new Response("x"))
    const { listeners } = loadWorker(fetchImpl)

    // Act
    const response = await navigate(listeners, "https://majlisna.app/assets/index.js", "cors")

    // Assert
    expect(response).toBeUndefined()
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it("names its cache with a version, and drops the older caches when it activates", async () => {
    // Prepare: the first worker's cache is still there
    const { listeners, stores, caches } = loadWorker(async () => new Response(SHELL_HTML))
    stores.set("majlisna-shell-v1", new Map())
    const name = /const CACHE_NAME = "([^"]+)"/.exec(SOURCE)?.[1]

    // Act
    const pending: Promise<unknown>[] = []
    listeners.get("activate")?.({ waitUntil: (p: Promise<unknown>) => pending.push(p) })
    await Promise.all(pending)

    // Assert
    expect(name).toMatch(/^majlisna-shell-v\d+$/)
    expect(name).not.toBe("majlisna-shell-v1")
    expect(caches.delete).toHaveBeenCalledWith("majlisna-shell-v1")
  })
})
