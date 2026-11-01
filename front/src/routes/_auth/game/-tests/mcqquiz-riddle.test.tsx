import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

/**
 * The Quiz between two questions: the samar riddle sits under the results while the table
 * waits for the host or the ready quorum, never while a question is open (nor in Kalimat:
 * its words are drawn round by round, so a riddle could be a later round's). The riddle
 * itself is `SamarRiddle`'s (its own tests); here, a recording stand-in says where the page
 * puts it and what it hands it.
 */
const api = vi.hoisted(() => ({ state: null as Record<string, unknown> | null }))
const riddles = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }))

vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => ({ gameId: "g1" }) }),
  useNavigate: () => vi.fn(),
}))
vi.mock("@/api/generated", () => ({
  useGetMcqquizStateApiV1McqquizGamesGameIdStateGet: () => ({ data: api.state, isLoading: false, error: null }),
  useSubmitAnswerApiV1McqquizGamesGameIdAnswerPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useTimerExpiredApiV1McqquizGamesGameIdTimerExpiredPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useNextRoundApiV1McqquizGamesGameIdNextRoundPost: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useLeaveRoomApiV1RoomsLeavePatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  getMcqquizStateApiV1McqquizGamesGameIdStateGetQueryKey: ({ game_id }: { game_id: string }) => [{ url: "/mcqquiz/state", params: { game_id } }],
  getRoomStateApiV1RoomsRoomIdStateGetQueryKey: ({ room_id }: { room_id: string }) => [{ url: "/rooms/state", params: { room_id } }],
}))
vi.mock("@/components/rooms/SamarRiddle", () => ({
  SamarRiddle: (props: Record<string, unknown>) => {
    riddles.props.push(props)
    return <section aria-label="samar riddle" />
  },
}))
vi.mock("@/api/client", () => ({ getApiErrorMessage: (_err: unknown, fallback: string) => fallback }))
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => ({ user: { id: "u1" } }) }))
vi.mock("@/hooks/use-socket", () => ({ useSocket: () => ({ connected: true }) }))
vi.mock("@/lib/analytics", () => ({ trackEvent: vi.fn() }))
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn() } }))
vi.mock("@/components/ConnectionStatus", () => ({ ConnectionStatus: () => null }))
vi.mock("@/components/ErrorBoundary", () => ({ ErrorBoundary: ({ children }: { children: ReactNode }) => children }))
vi.mock("@/components/games/shared/PhaseTimer", () => ({ PhaseTimer: () => null }))
vi.mock("@/components/games/shared/prayer-pause", async () => ({
  ...(await import("@/components/games/shared/prayer-pause/pause-utils")),
  AdhanSuggestion: () => null,
  PauseControl: () => null,
  PauseLayer: () => null,
  usePrayerPause: () => ({ canPause: false, canResume: false, pause: vi.fn(), resume: vi.fn(), refresh: vi.fn(), isPausing: false, isResuming: false }),
  useAdhanSuggestion: () => ({ prayer: null, answer: vi.fn() }),
}))

const { Route } = await import("@/routes/_auth/game/mcqquiz.$gameId")
const Page = (Route as unknown as { options: { component: ComponentType } }).options.component

function mcqState(over: Record<string, unknown> = {}) {
  return {
    game_id: "g1",
    room_id: "r1",
    is_host: false,
    is_spectator: false,
    current_round: 2,
    total_rounds: 3,
    round_phase: "results",
    question: "Which prophet was swallowed by a whale?",
    choices: ["Yunus", "Musa", "Isa", "Nuh"],
    turn_duration_seconds: 30,
    round_started_at: new Date(Date.now() - 4_000).toISOString(),
    players: [
      { user_id: "u1", username: "Yusuf", total_score: 3, current_round_answered: true, current_round_points: 3 },
      { user_id: "u2", username: "Maryam", total_score: 1, current_round_answered: true, current_round_points: 1 },
    ],
    my_answered: true,
    my_points: 3,
    round_results: [],
    correct_answer_index: 0,
    choice_tallies: [1, 1, 0, 0],
    my_choice_index: 0,
    explanation: "Prophet Yunus was swallowed by a whale.",
    winner: null,
    leaderboard: [],
    game_over: false,
    paused: null,
    ready_players: [],
    ready_count: 0,
    total_players: 1,
    ...over,
  }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <Page />
    </QueryClientProvider>,
  )
}

const riddle = () => screen.queryByRole("region", { name: "samar riddle" })

beforeEach(() => {
  riddles.props.length = 0
})

describe("The Quiz page: the samar riddle between two questions", () => {
  it("asks one under the results, for this game and this question, after the host's controls", () => {
    // Prepare
    api.state = mcqState()

    // Act
    renderPage()

    // Assert
    expect(riddle()).toBeInTheDocument()
    expect(riddles.props.at(-1)).toMatchObject({ roomId: "r1", scope: "game:g1", waitKey: "2", note: "round", ask: true })
  })

  it("after the last question only answers the riddle before: there is no next question to wait for", () => {
    // Prepare
    api.state = mcqState({ current_round: 3 })

    // Act
    renderPage()

    // Assert
    expect(riddles.props.at(-1)).toMatchObject({ waitKey: "3", ask: false })
  })

  it("is not there while a question is open", () => {
    // Prepare
    api.state = mcqState({ round_phase: "playing", my_answered: false, correct_answer_index: null })

    // Act
    renderPage()

    // Assert
    expect(riddle()).toBeNull()
    expect(riddles.props).toHaveLength(0)
  })

  it("is shown to a spectator too", () => {
    // Prepare
    api.state = mcqState({ is_spectator: true, my_choice_index: null })

    // Act
    renderPage()

    // Assert
    expect(riddle()).toBeInTheDocument()
  })
})
