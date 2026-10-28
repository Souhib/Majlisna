import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { NotebookEntryView } from "@/api/generated"
import { toast } from "sonner"
import { UNDO_WINDOW_MS } from "../use-notebook-entries"
import { answer, httpError, requestsTo, resetFakeApi } from "./fake-api"

const i18nState = vi.hoisted(() => ({ language: "en" }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: i18nState.language },
  }),
}))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options }),
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("@/api/generated", async () => (await import("./fake-api")).notebookGenerated())
vi.mock("@/api/client", async () => (await import("./fake-api")).clientModule)
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

const { Route } = await import("@/routes/_auth/notebook")
const NotebookPage = (Route as unknown as { options: { component: ComponentType } }).options.component

const LIST = "GET /api/v1/notebook"

const entry = (over: Partial<NotebookEntryView>): NotebookEntryView => ({
  id: "e1",
  word: "Sabr",
  word_display: "Sabr",
  game_type: "undercover",
  word_ar: "صبر",
  word_ar_vocalized: "صَبْر",
  hint: "Patience: staying steady when it is hard.",
  source_game_id: "g1",
  kept_at: "2026-10-28T20:00:00+00:00",
  ...over,
})

const firstPage = (over: { next_cursor?: string | null; entries?: NotebookEntryView[] } = {}) => ({
  entries: over.entries ?? [
    entry({}),
    entry({ id: "e2", word: "Hilm", word_display: "Hilm", word_ar: "حلم", word_ar_vocalized: "حِلْم", hint: "Forbearance" }),
    entry({ id: "e3", word: "Uhud", word_display: "Uhud", word_ar: "أحد", word_ar_vocalized: "أُحُد", hint: null, game_type: "codenames", source_game_id: "g2" }),
  ],
  total: over.entries?.length ?? 3,
  next_cursor: over.next_cursor ?? null,
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <NotebookPage />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  resetFakeApi()
  i18nState.language = "en"
})

afterEach(() => {
  vi.useRealTimers()
})

describe("/notebook (the Kunnash)", () => {
  it("titles the page with the Arabic name, counts the words, and reads them newest first by game", async () => {
    // Prepare
    answer(LIST, () => firstPage())

    // Act
    renderPage()

    // Assert
    const title = screen.getByRole("heading", { level: 1 })
    expect(title).toHaveTextContent("notebook.title")
    expect(within(title).getByText("كُنّاش")).toHaveAttribute("lang", "ar")
    expect(await screen.findByText("notebook.count(count=3)")).toBeInTheDocument()
    const groups = screen.getAllByRole("heading", { level: 2 })
    expect(groups.map((h) => h.textContent)).toEqual([
      expect.stringContaining("games.undercover.name"),
      expect.stringContaining("games.codenames.name"),
    ])
    expect(groups[0]).toHaveTextContent("notebook.keptOn(count=2,date=October 28, 2026)")
    expect(screen.getByText("صَبْر")).toHaveAttribute("lang", "ar")
    expect(screen.getByText("Sabr")).toBeInTheDocument()
    expect(screen.getByText("Patience: staying steady when it is hard.")).toBeInTheDocument()
    expect(requestsTo(LIST)[0].params).toEqual({ lang: "en", limit: 30 })
  })

  it("lets the Arabic lead in the Arabic UI: no transliteration, the Arabic names the eraser", async () => {
    // Prepare
    i18nState.language = "ar"
    answer(LIST, () => firstPage())

    // Act
    renderPage()

    // Assert
    expect(await screen.findByText("صَبْر")).toBeInTheDocument()
    expect(screen.queryByText("Sabr")).not.toBeInTheDocument()
    expect(screen.queryByText("كُنّاش")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "notebook.remove(word=صَبْر)" })).toBeInTheDocument()
    expect(requestsTo(LIST)[0].params).toEqual({ lang: "ar", limit: 30 })
  })

  it("says an empty notebook plainly, with a room to open", async () => {
    // Prepare
    answer(LIST, () => firstPage({ entries: [] }))

    // Act
    renderPage()

    // Assert
    expect(await screen.findByRole("heading", { level: 2, name: "notebook.emptyTitle" })).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "notebook.openRoom" })).toHaveAttribute("href", "/rooms/create")
    expect(screen.getByRole("link", { name: "notebook.joinRoom" })).toHaveAttribute("href", "/rooms")
  })

  it("offers to try again when the notebook cannot be read", { timeout: 8000 }, async () => {
    // Prepare
    answer(LIST, () => {
      throw httpError(500)
    })

    // Act
    renderPage()

    // Assert (a 5xx is read once more, as every query of the app, before it is said)
    expect(await screen.findByRole("alert", undefined, { timeout: 4000 })).toHaveTextContent("notebook.loadFailed")
    answer(LIST, () => firstPage())
    fireEvent.click(screen.getByRole("button", { name: "notebook.retry" }))
    expect(await screen.findByText("صَبْر")).toBeInTheDocument()
  })

  it("removes a word only when its undo window closes; Undo brings it back untouched", async () => {
    // Prepare
    vi.useFakeTimers({ shouldAdvanceTime: true })
    answer(LIST, () => firstPage())
    answer("DELETE /api/v1/notebook/entries/e1", () => undefined)
    renderPage()
    const eraser = await screen.findByRole("button", { name: "notebook.remove(word=Sabr)" })

    // Act: remove, then undo
    fireEvent.click(eraser)

    // Assert: the row says so, focus is on Undo, nothing sent yet
    const undo = await screen.findByRole("button", { name: "notebook.undoNamed(word=Sabr)" })
    expect(screen.getByText("notebook.removed(word=Sabr)")).toBeInTheDocument()
    await waitFor(() => expect(undo).toHaveFocus())
    expect(requestsTo("DELETE /api/v1/notebook/entries/e1")).toHaveLength(0)

    fireEvent.click(undo)
    const back = await screen.findByRole("button", { name: "notebook.remove(word=Sabr)" })
    await waitFor(() => expect(back).toHaveFocus())
    act(() => {
      vi.advanceTimersByTime(UNDO_WINDOW_MS + 100)
    })
    expect(requestsTo("DELETE /api/v1/notebook/entries/e1")).toHaveLength(0)

    // Act: remove for good
    fireEvent.click(back)
    await screen.findByRole("button", { name: "notebook.undoNamed(word=Sabr)" })
    act(() => {
      vi.advanceTimersByTime(UNDO_WINDOW_MS + 100)
    })

    // Assert: deleted, gone, counted, and focus handed to the next word's eraser
    await waitFor(() => expect(requestsTo("DELETE /api/v1/notebook/entries/e1")).toHaveLength(1))
    await waitFor(() => expect(screen.queryByText("notebook.removed(word=Sabr)")).not.toBeInTheDocument())
    expect(screen.queryByText("Sabr")).not.toBeInTheDocument()
    expect(screen.getByText("notebook.count(count=2)")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "notebook.remove(word=Hilm)" })).toHaveFocus()
  })

  it("counts the 204 as removed, and says a real failure", async () => {
    // Prepare
    vi.useFakeTimers({ shouldAdvanceTime: true })
    answer(LIST, () => firstPage())
    answer("DELETE /api/v1/notebook/entries/e1", () => undefined)
    answer("DELETE /api/v1/notebook/entries/e2", () => {
      throw httpError(500)
    })
    renderPage()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.remove(word=Sabr)" }))
    fireEvent.click(screen.getByRole("button", { name: "notebook.remove(word=Hilm)" }))
    act(() => {
      vi.advanceTimersByTime(UNDO_WINDOW_MS + 100)
    })

    // Assert: Sabr is gone; Hilm failed, so it is back, and the failure is said
    await waitFor(() => expect(screen.queryByText("notebook.removed(word=Sabr)")).not.toBeInTheDocument())
    expect(screen.queryByText("Sabr")).not.toBeInTheDocument()
    expect(await screen.findByRole("button", { name: "notebook.remove(word=Hilm)" })).toBeInTheDocument()
    expect(vi.mocked(toast.error)).toHaveBeenCalledWith("notebook.removeFailed")
    expect(screen.getByText("notebook.count(count=2)")).toBeInTheDocument()
  })

  it("sends a pending removal when the page is left during its undo window", async () => {
    // Prepare
    answer(LIST, () => firstPage())
    answer("DELETE /api/v1/notebook/entries/e2", () => undefined)
    const { unmount } = renderPage()
    fireEvent.click(await screen.findByRole("button", { name: "notebook.remove(word=Hilm)" }))
    await screen.findByRole("button", { name: "notebook.undoNamed(word=Hilm)" })

    // Act
    unmount()

    // Assert
    await waitFor(() => expect(requestsTo("DELETE /api/v1/notebook/entries/e2")).toHaveLength(1))
  })

  it("loads the next page by its cursor, and stops at the last", async () => {
    // Prepare
    answer(LIST, (request) =>
      request.params?.cursor === "c1"
        ? firstPage({ entries: [entry({ id: "e9", word: "Tawba", word_display: "Tawba", word_ar: "توبة", word_ar_vocalized: "تَوْبَة", source_game_id: "g7" })] })
        : firstPage({ next_cursor: "c1" }),
    )
    renderPage()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "notebook.more" }))

    // Assert
    expect(await screen.findByText("تَوْبَة")).toBeInTheDocument()
    expect(requestsTo(LIST).map((r) => r.params?.cursor)).toEqual([undefined, "c1"])
    expect(screen.queryByRole("button", { name: "notebook.more" })).not.toBeInTheDocument()
  })

  it("shows bare warp while the first page loads", () => {
    // Prepare
    answer(LIST, () => new Promise(() => {}))

    // Act
    renderPage()

    // Assert
    expect(screen.getByText("notebook.loading")).toHaveAttribute("role", "status")
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument()
  })
})
