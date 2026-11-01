import { act, fireEvent, render, screen } from "@testing-library/react"
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from "@tanstack/react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The root boundary around <Outlet/> (FR-10): one crash used to leave every page on
 * "Something went wrong" until a manual reload, and "Try again" could not recover a lazy
 * chunk whose failed import the router keeps. Rendered here inside a real router, the way
 * __root.tsx mounts it.
 */
const reportError = vi.hoisted(() => vi.fn())
vi.mock("@/lib/report-error", () => ({ reportError }))

const { ErrorBoundary } = await import("../ErrorBoundary")

const CHUNK_RELOAD_KEY = "majlisna-chunk-reload"
const crash = vi.hoisted(() => ({ error: new Error("boom") as Error | null }))

function Stats() {
  if (crash.error) throw crash.error
  return <p>The stats</p>
}

function renderApp(initialPath: string) {
  const rootRoute = createRootRoute({
    component: () => (
      <ErrorBoundary>
        <Outlet />
      </ErrorBoundary>
    ),
  })
  const stats = createRoute({ getParentRoute: () => rootRoute, path: "/stats", component: Stats })
  const rooms = createRoute({ getParentRoute: () => rootRoute, path: "/rooms", component: () => <p>The rooms</p> })
  const router = createRouter({
    routeTree: rootRoute.addChildren([stats, rooms]),
    history: createMemoryHistory({ initialEntries: [initialPath] }),
  })
  render(<RouterProvider router={router} />)
  return router
}

describe("ErrorBoundary", () => {
  beforeEach(() => {
    crash.error = new Error("boom")
    reportError.mockClear()
    sessionStorage.clear()
    // React and the router say a caught render error out loud; the test does not need it
    vi.spyOn(console, "error").mockImplementation(() => {})
    vi.spyOn(console, "warn").mockImplementation(() => {})
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("lets the next page render after a crash, once the player navigates away", async () => {
    // Prepare: /stats crashes while rendering
    const router = renderApp("/stats")
    expect(await screen.findByText("ui.errorTitle")).toBeInTheDocument()

    // Act: the nav takes the player to /rooms
    await act(() => router.navigate({ to: "/rooms" }))

    // Assert: the rooms page is drawn, the fallback is gone
    expect(await screen.findByText("The rooms")).toBeInTheDocument()
    expect(screen.queryByText("ui.errorTitle")).not.toBeInTheDocument()
  })

  it("reports what it caught", async () => {
    // Prepare / Act
    renderApp("/stats")
    await screen.findByText("ui.errorTitle")

    // Assert: the crash went to the error reporter, with the component stack
    expect(reportError).toHaveBeenCalledWith(
      crash.error,
      expect.objectContaining({ source: "ErrorBoundary caught", extra: expect.objectContaining({ componentStack: expect.any(String) }) }),
    )
  })

  it("keeps the technical message behind a details toggle", async () => {
    // Prepare
    renderApp("/stats")
    await screen.findByText("ui.errorTitle")

    // Act
    const message = screen.getByText("boom")
    const details = message.closest("details")

    // Assert: folded away by default, under a "Technical details" summary
    expect(details).not.toBeNull()
    expect(details?.open).toBe(false)
    expect(details?.querySelector("summary")).toHaveTextContent("ui.errorDetails")
  })

  it("reloads the page once when 'Try again' meets a chunk that failed to load", async () => {
    // Prepare: the page's chunk is gone (a deploy happened since this tab loaded)
    crash.error = new TypeError("Failed to fetch dynamically imported module: https://majlisna.app/assets/stats-AbC123.js")
    const reload = vi.spyOn(window.location, "reload").mockImplementation(() => {})
    renderApp("/stats")
    await screen.findByText("ui.errorTitle")

    // Act: Try again
    fireEvent.click(screen.getByRole("button", { name: "ui.tryAgain" }))

    // Assert: a reload (a lazy import that failed is never tried again in place), guarded
    expect(reload).toHaveBeenCalledTimes(1)
    expect(sessionStorage.getItem(CHUNK_RELOAD_KEY)).not.toBeNull()

    // Act: the reloaded page fails the same way, and the player tries again
    fireEvent.click(screen.getByRole("button", { name: "ui.tryAgain" }))

    // Assert: no second reload from this button in this tab: the fallback stays, with Reload
    expect(reload).toHaveBeenCalledTimes(1)
    expect(await screen.findByText("ui.errorTitle")).toBeInTheDocument()
  })

  it("does not reload for an ordinary render error: 'Try again' renders the page again", async () => {
    // Prepare: /stats crashed once; its next render succeeds
    const reload = vi.spyOn(window.location, "reload").mockImplementation(() => {})
    renderApp("/stats")
    await screen.findByText("ui.errorTitle")
    crash.error = null

    // Act
    fireEvent.click(screen.getByRole("button", { name: "ui.tryAgain" }))

    // Assert: no reload, no guard spent; the page is back
    expect(await screen.findByText("The stats")).toBeInTheDocument()
    expect(reload).not.toHaveBeenCalled()
    expect(sessionStorage.getItem(CHUNK_RELOAD_KEY)).toBeNull()
  })
})
