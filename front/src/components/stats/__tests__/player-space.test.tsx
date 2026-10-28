import { fireEvent, render, screen, within } from "@testing-library/react"
import type { ComponentType, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { GameSummary, LeaderboardEntry } from "@/api/generated"

const summaryHook = vi.fn()
const leaderboardHook = vi.fn()
vi.mock("@/api/generated", () => ({
  useGetGameSummaryApiV1GamesGameIdSummaryGet: (...args: unknown[]) => summaryHook(...args),
  useGetLeaderboardApiV1StatsLeaderboardGet: (...args: unknown[]) => leaderboardHook(...args),
}))
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "me", username: "Maryam", email: "m@test.com" } }),
}))
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (opts: Record<string, unknown>) => opts,
  Link: ({ children, to, params: _params, ...rest }: { children: ReactNode; to: string; params?: unknown }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))

const { GameDetailModal } = await import("../GameDetailModal")
const { RoleDistributionChart } = await import("../RoleDistributionChart")
const { Route: LeaderboardRoute } = await import("@/routes/leaderboard")
const LeaderboardPage = (LeaderboardRoute as unknown as { component: ComponentType }).component
const { RemoveFriendButton } = await import("@/components/friends/RemoveFriendButton")
const { FriendRow } = await import("@/components/friends/FriendRow")

const undercover: GameSummary = {
  id: "g1",
  type: "undercover",
  start_time: "2026-10-28T10:00:00Z",
  end_time: "2026-10-28T10:12:00Z",
  number_of_players: 3,
  winner: "civilians",
  game_status: "finished",
  players: [
    { user_id: "a", username: "Maryam", role: "civilian" },
    { user_id: "b", username: "Idris", role: "civilian" },
    { user_id: "c", username: "Khadija", role: "undercover" },
  ],
  vote_history: [
    {
      round: 1,
      votes: [
        { voter: "Maryam", target: "Khadija" },
        { voter: "Idris", target: "Khadija" },
        { voter: "Khadija", target: "Maryam" },
      ],
      eliminated: { username: "Khadija", role: "undercover" },
    },
  ],
  clue_history: null,
  word_explanations: {
    civilian_word: "Abu Bakr",
    civilian_word_ar: "أبو بكر",
    civilian_word_hint: "The first caliph.",
    undercover_word: "Umar",
    undercover_word_ar: "عمر",
  },
}

const codenames: GameSummary = {
  id: "g2",
  type: "codenames",
  start_time: "2026-10-28T10:00:00Z",
  end_time: "2026-10-28T10:20:00Z",
  number_of_players: 4,
  winner: "red",
  game_status: "finished",
  players: [
    { user_id: "a", username: "Maryam", role: "operative", team: "blue" },
    { user_id: "b", username: "Idris", role: "spymaster", team: "red" },
  ],
  vote_history: null,
  clue_history: [
    {
      team: "blue",
      clue_word: "Knowledge",
      clue_number: 2,
      guesses: [
        { word: "Wara", word_ar: "ورع", card_type: "blue", correct: true },
        { word: "Aqeedah", word_ar: "عقيدة", card_type: "assassin", correct: false },
      ],
    },
  ],
  word_explanations: null,
}

describe("GameDetailModal", () => {
  beforeEach(() => summaryHook.mockReset())

  it("shows an Undercover game's result, both words with their Arabic, and every role", () => {
    // Prepare
    summaryHook.mockReturnValue({ data: undercover, isLoading: false, error: null })

    // Act
    render(<GameDetailModal gameId="g1" gameType="undercover" onClose={() => {}} />)
    const dialog = screen.getByRole("dialog")

    // Assert
    expect(within(dialog).getByRole("heading", { name: "games.undercover.name" })).toBeInTheDocument()
    expect(within(dialog).getByText("stats.result.civilians")).toBeInTheDocument()
    expect(within(dialog).getByText("أبو بكر")).toHaveAttribute("lang", "ar")
    expect(within(dialog).getByText("Umar")).toBeInTheDocument()
    // the meaning, read in the player's language (the summary is asked for with `lang`)
    expect(within(dialog).getByText("The first caliph.")).toBeInTheDocument()
    expect(summaryHook).toHaveBeenCalledWith({ game_id: "g1" }, { lang: "en" })
    expect(within(dialog).getAllByText("games.undercover.roles.civilian").length).toBeGreaterThanOrEqual(2)
    expect(within(dialog).getAllByText("games.undercover.roles.undercover").length).toBeGreaterThanOrEqual(2)
  })

  it("names each card a Codenames clue turned by its glyph, not only its colour", () => {
    // Prepare
    summaryHook.mockReturnValue({ data: codenames, isLoading: false, error: null })

    // Act
    render(<GameDetailModal gameId="g2" gameType="codenames" onClose={() => {}} />)

    // Assert
    expect(screen.getByText("Knowledge")).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "stats.card.assassin" })).toBeInTheDocument()
    expect(screen.getByRole("img", { name: "game.codenames.teams.blue" })).toBeInTheDocument()
    expect(screen.getByText("عقيدة")).toHaveAttribute("lang", "ar")
  })

  it("says the summary could not be loaded instead of showing an empty dialog", () => {
    // Prepare
    summaryHook.mockReturnValue({ data: undefined, isLoading: false, error: null })

    // Act
    render(<GameDetailModal gameId="g3" gameType="undercover" onClose={() => {}} />)

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("errors.loadFailed")
  })

  it("closes with Escape", () => {
    // Prepare
    summaryHook.mockReturnValue({ data: undercover, isLoading: false, error: null })
    const onClose = vi.fn()
    render(<GameDetailModal gameId="g1" gameType="undercover" onClose={onClose} />)

    // Act
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })

    // Assert
    expect(onClose).toHaveBeenCalled()
  })
})

describe("RoleDistributionChart", () => {
  it("draws nothing before a role has been played", () => {
    const { container } = render(<RoleDistributionChart timesCivilian={0} timesUndercover={0} timesMrWhite={0} timesSpymaster={0} timesOperative={0} />)
    expect(container).toBeEmptyDOMElement()
  })

  it("lists every role with its count as text", () => {
    // Act
    render(<RoleDistributionChart timesCivilian={4} timesUndercover={2} timesMrWhite={1} timesSpymaster={0} timesOperative={3} civilianWins={3} />)

    // Assert
    const row = screen.getByRole("row", { name: /games.undercover.roles.civilian/ })
    expect(within(row).getByText("4")).toBeInTheDocument()
    expect(within(row).getByText("3")).toBeInTheDocument()
    expect(screen.getAllByRole("row", { name: /roles\./ })).toHaveLength(5)
  })
})

describe("Leaderboard", () => {
  const entry = (user_id: string, username: string, won: number): LeaderboardEntry => ({
    user_id,
    username,
    total_games_played: won * 2,
    total_games_won: won,
    win_rate: 50,
    current_win_streak: 1,
    longest_win_streak: 2,
  })

  beforeEach(() => leaderboardHook.mockReset())

  it("keeps its six columns, the sort buttons, and marks the reader's own row", () => {
    // Prepare
    leaderboardHook.mockReturnValue({ data: [entry("x", "Yusuf", 9), entry("me", "Maryam", 4)], isLoading: false })

    // Act
    render(<LeaderboardPage />)

    // Assert
    expect(screen.getByTestId("leaderboard")).toBeInTheDocument()
    expect(screen.getByTestId("leaderboard").querySelectorAll("thead th")).toHaveLength(6)
    expect(screen.getByRole("button", { name: "leaderboard.wins" })).toHaveAttribute("aria-pressed", "true")
    const mine = screen.getAllByRole("row").find((r) => r.getAttribute("aria-current") === "true")
    expect(mine).toHaveTextContent("Maryam")
    expect(mine).toHaveTextContent("leaderboard.you")
  })

  it("asks the server for the chosen order", () => {
    // Prepare
    leaderboardHook.mockReturnValue({ data: [], isLoading: false })
    render(<LeaderboardPage />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "leaderboard.winRate" }))

    // Assert
    expect(leaderboardHook).toHaveBeenLastCalledWith({ stat_field: "win_rate", limit: 50 })
    expect(screen.getByRole("button", { name: "leaderboard.winRate" })).toHaveAttribute("aria-pressed", "true")
    expect(screen.getByText("leaderboard.noPlayers")).toBeInTheDocument()
  })
})

describe("Friends", () => {
  it("asks before removing a friend, and removes only on confirmation", () => {
    // Prepare
    const onConfirm = vi.fn()
    render(<RemoveFriendButton compact name="Idris" onConfirm={onConfirm} />)

    // Act
    fireEvent.click(screen.getByRole("button", { name: "friends.removeNamed" }))
    const dialog = screen.getByRole("alertdialog")
    fireEvent.click(within(dialog).getByRole("button", { name: "common.cancel" }))

    // Assert
    expect(onConfirm).not.toHaveBeenCalled()

    // Act
    fireEvent.click(screen.getByRole("button", { name: "friends.removeNamed" }))
    fireEvent.click(within(screen.getByRole("alertdialog")).getByRole("button", { name: "friends.removeFriend" }))

    // Assert
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it("links a friend's name to their page without repeating it for screen readers", () => {
    // Act
    render(
      <ul>
        <FriendRow userId="u1" username="Idris" sub="wants" />
      </ul>,
    )

    // Assert
    const link = screen.getByRole("link")
    expect(link).toHaveAccessibleName("Idris wants")
    expect(screen.getAllByText("Idris")).toHaveLength(1)
  })
})
