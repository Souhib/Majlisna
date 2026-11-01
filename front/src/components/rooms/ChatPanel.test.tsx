import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { queryKeys } from "@/api/queryKeys"
import { answer, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"
import { type ChatMessage, ChatPanel } from "./ChatPanel"

// the real generated functions and hooks run; every request is answered by the fake client
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)

const HISTORY = "GET /api/v1/rooms/room-1/messages"
const SEND = "POST /api/v1/rooms/room-1/messages"

function line(id: string, message: string, over: Partial<ChatMessage> = {}): ChatMessage {
  return { id, room_id: "room-1", user_id: "user-2", username: "Alice", message, created_at: "2026-01-01T00:00:00Z", ...over }
}

function defaultProps(overrides: Partial<{ incomingMessage: ChatMessage | null }> = {}) {
  return {
    roomId: "room-1",
    currentUserId: "user-1",
    incomingMessage: null,
    ...overrides,
  }
}

/**
 * Render the panel and let its history load settle inside act: the load resolves after
 * the first render, and asserting before it left a state update outside act (a warning
 * per test, and assertions made against a half-rendered panel).
 */
async function renderPanel(props: ReturnType<typeof defaultProps>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let result!: ReturnType<typeof render>
  await act(async () => {
    result = render(
      <QueryClientProvider client={queryClient}>
        <ChatPanel {...props} />
      </QueryClientProvider>,
    )
  })
  const rerender = (next: ReturnType<typeof defaultProps>) =>
    result.rerender(
      <QueryClientProvider client={queryClient}>
        <ChatPanel {...next} />
      </QueryClientProvider>,
    )
  return { ...result, queryClient, rerender }
}

/** The lines on screen, in their order. */
const shownLines = () => Array.from(document.querySelectorAll('[role="log"] li p')).map((p) => p.textContent)

beforeEach(() => {
  resetFakeApi()
  answer(HISTORY, () => [])
  answer(SEND, () => ({}))
})

describe("ChatPanel", () => {
  it("renders the chat title as the toggle of an open panel", async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText("chat.title")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /chat\.title/ })).toHaveAttribute("aria-expanded", "true")
  })

  it("shows empty state message when no messages", async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText("chat.noMessages")).toBeInTheDocument()
  })

  it("renders the message input", async () => {
    await renderPanel(defaultProps())
    expect(screen.getByPlaceholderText("chat.placeholder")).toBeInTheDocument()
  })

  it("send button is disabled when input is empty", async () => {
    await renderPanel(defaultProps())
    expect(screen.getByRole("button", { name: "chat.send" })).toBeDisabled()
  })

  it("sends the trimmed message and clears the field", async () => {
    // Prepare
    await renderPanel(defaultProps())
    const input = screen.getByPlaceholderText("chat.placeholder")

    // Act
    fireEvent.change(input, { target: { value: "  Salam  " } })
    fireEvent.click(screen.getByRole("button", { name: "chat.send" }))

    // Assert
    await waitFor(() => expect(input).toHaveValue(""))
    expect(requestsTo(SEND).map((r) => r.data)).toEqual([{ message: "Salam" }])
  })

  it("collapses and expands the panel", async () => {
    await renderPanel(defaultProps())
    expect(screen.getByText("chat.noMessages")).toBeVisible()

    fireEvent.click(screen.getByText("chat.title"))
    expect(screen.queryByText("chat.noMessages")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: /chat\.title/ })).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(screen.getByText("chat.title"))
    expect(screen.getByText("chat.noMessages")).toBeVisible()
  })

  it("renders incoming messages", async () => {
    await renderPanel(defaultProps({ incomingMessage: line("msg-1", "Salam everyone!") }))
    expect(screen.getByText("Salam everyone!")).toBeInTheDocument()
    expect(screen.getByText("Alice")).toBeInTheDocument()
  })

  it("keeps a message that arrives while the history is loading", async () => {
    // Prepare
    answer(HISTORY, () => [line("old", "Earlier")])

    // Act
    await renderPanel(defaultProps({ incomingMessage: line("live", "Just now", { created_at: "2026-01-01T00:01:00Z" }) }))

    // Assert
    expect(await screen.findByText("Earlier")).toBeInTheDocument()
    expect(screen.getByText("Just now")).toBeInTheDocument()
  })

  it("leaves out the last line of another room's lobby", async () => {
    // the lobby keeps its last pushed line across a move to another room's lobby
    await renderPanel(defaultProps({ incomingMessage: line("other", "In the other room", { room_id: "room-2" }) }))
    expect(screen.queryByText("In the other room")).not.toBeInTheDocument()
    expect(screen.getByText("chat.noMessages")).toBeInTheDocument()
  })

  it("does not show username for own messages", async () => {
    await renderPanel(defaultProps({ incomingMessage: line("msg-1", "My own message", { user_id: "user-1", username: "Me" }) }))
    expect(screen.getByText("My own message")).toBeInTheDocument()
    expect(screen.queryByText("Me")).not.toBeInTheDocument()
  })

  it("reads the history from the room's chat query", async () => {
    // useSocket invalidates this key on a reconnect: the panel must be the one reading it
    // Prepare
    answer(HISTORY, () => [line("m1", "Salam")])

    // Act
    const { queryClient } = await renderPanel(defaultProps())

    // Assert
    expect(await screen.findByText("Salam")).toBeInTheDocument()
    expect(queryClient.getQueryCache().findAll({ queryKey: queryKeys.room.messages("room-1") })).toHaveLength(1)
    expect(requestsTo(HISTORY)[0].params).toEqual({ limit: 50 })
  })

  it("shows the lines said while the socket was down once the history is read again", async () => {
    // FR-6: python-socketio replays nothing, so a line sent during a blip only comes
    // back through the history, which used to be read once per mount.
    // Prepare
    answer(HISTORY, () => [line("m1", "before the drop")])
    const { queryClient } = await renderPanel(defaultProps())
    await screen.findByText("before the drop")
    answer(HISTORY, () => [line("m1", "before the drop"), line("m2", "while you were away", { created_at: "2026-01-01T00:01:00Z" })])

    // Act: what useSocket does on a reconnect
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.room.messages("room-1") })
    })

    // Assert
    expect(await screen.findByText("while you were away")).toBeInTheDocument()
    expect(shownLines()).toEqual(["before the drop", "while you were away"])
  })

  it("keeps every line once and in the order it was said", async () => {
    // Prepare: a line arrived live just before the drop, another was missed
    answer(HISTORY, () => [line("m1", "first")])
    const { queryClient, rerender } = await renderPanel(defaultProps())
    await screen.findByText("first")
    rerender(defaultProps({ incomingMessage: line("m3", "third", { created_at: "2026-01-01T00:03:00Z" }) }))
    await screen.findByText("third")
    answer(HISTORY, () => [
      line("m1", "first"),
      line("m2", "second", { created_at: "2026-01-01T00:02:00Z" }),
      line("m3", "third", { created_at: "2026-01-01T00:03:00Z" }),
    ])

    // Act
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.room.messages("room-1") })
    })

    // Assert
    await screen.findByText("second")
    expect(shownLines()).toEqual(["first", "second", "third"])
  })

  it("counts the lines caught up while the panel is closed as unread", async () => {
    // Prepare
    answer(HISTORY, () => [line("m1", "first")])
    const { queryClient } = await renderPanel(defaultProps())
    await screen.findByText("first")
    fireEvent.click(screen.getByText("chat.title"))
    answer(HISTORY, () => [line("m1", "first"), line("m2", "second", { created_at: "2026-01-01T00:02:00Z" })])

    // Act
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.room.messages("room-1") })
    })

    // Assert
    expect(await screen.findByText("chat.unread")).toBeInTheDocument()
    expect(screen.getByText("1")).toBeInTheDocument()
  })
})
