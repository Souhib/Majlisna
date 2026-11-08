import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { type ComponentType, type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

/**
 * The player-space pages when the API fails (FR-7). A failed read is not an empty
 * list: during an incident "No games played" told a player with hundreds of games that
 * their history was gone. Each page says the read failed and offers Retry, on the real
 * generated hooks over a fake client. The folder starts with "-" so the router's file
 * scan leaves it alone.
 */
const params = vi.hoisted(() => ({ userId: "u2" }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en", dir: () => "ltr" } }),
  Trans: ({ i18nKey }: { i18nKey: string }) => i18nKey,
}))
vi.mock("@tanstack/react-router", () => ({
  createFileRoute: () => (options: { component: ComponentType }) => ({ options, useParams: () => params }),
  Link: ({ to, children, params: _params, ...rest }: { to: string; children: ReactNode; params?: unknown }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
  useNavigate: () => vi.fn(),
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({
  useAuth: () => ({ user: { id: "u1", username: "Yusuf", email: "yusuf@example.com" }, setUser: vi.fn(), logout: vi.fn() }),
}))
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

const componentOf = (route: unknown) => (route as { options: { component: ComponentType } }).options.component

const StatsPage = componentOf((await import("@/routes/_auth/stats")).Route)
const AchievementsPage = componentOf((await import("@/routes/_auth/achievements")).Route)
const ChallengesPage = componentOf((await import("@/routes/_auth/challenges")).Route)
const FriendsPage = componentOf((await import("@/routes/_auth/friends")).Route)
const LeaderboardPage = componentOf((await import("@/routes/leaderboard")).Route)
const ProfilePage = componentOf((await import("@/routes/_auth/profile")).Route)
const PlayerPage = componentOf((await import("@/routes/_auth/players/$userId")).Route)

const STATS = "GET /api/v1/stats/users/u1/stats"
const GAMES = "GET /api/v1/games/user/u1"
const ACHIEVEMENTS = "GET /api/v1/stats/users/u1/achievements"
const CHALLENGES = "GET /api/v1/challenges/active"
const FRIENDS = "GET /api/v1/friends"
const PENDING = "GET /api/v1/friends/pending"
const LEADERBOARD = "GET /api/v1/stats/leaderboard"
const MY_DETAILS = "GET /api/v1/users/u1"
const PROFILE = "GET /api/v1/profiles/users/u2"
const THEIR_DETAILS = "GET /api/v1/users/u2"
const FRIENDSHIP = "GET /api/v1/friends/status/u2"
const H2H = "GET /api/v1/stats/users/u1/vs/u2"

// the backend's envelope for an unhandled exception (app.py); the fake client's
// getApiErrorMessage says the error key
const SERVER_ERROR = "errors.api.internalServer"
const serverError = () => httpError(500, { error: "InternalServerError", error_key: SERVER_ERROR })

/** Every listed route answers 500. */
function failAll(...routes: string[]) {
  for (const route of routes) {
    answer(route, () => {
      throw serverError()
    })
  }
}

async function renderPage(Page: ComponentType) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <Page />
      </QueryClientProvider>,
    )
  })
}

/** The page said the read failed: the server's reason in an alert, and a Retry button. */
async function expectLoadFailed() {
  const alert = await screen.findByRole("alert")
  expect(alert).toHaveTextContent(SERVER_ERROR)
  expect(screen.getByRole("button", { name: "common.retry" })).toBeInTheDocument()
}

async function retry() {
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "common.retry" }))
  })
}

const emptyStats = {
  user_id: "u1",
  total_games_played: 0,
  total_games_won: 0,
  current_win_streak: 0,
  longest_win_streak: 0,
}

const leaderboardEntry = {
  user_id: "u3",
  username: "Maryam",
  total_games_played: 12,
  total_games_won: 7,
  win_rate: 58.3,
  longest_win_streak: 3,
}

const publicProfile = {
  user_id: "u2",
  username: "Maryam",
  bio: null,
  favorite_game: null,
  total_games_played: 4,
  undercover_games_played: 2,
  codenames_games_played: 1,
  wordquiz_games_played: 1,
}

beforeEach(() => {
  resetFakeApi()
  params.userId = "u2"
})

describe("/stats", () => {
  it("says the read failed, not 'No games played'", async () => {
    // Prepare
    failAll(STATS, GAMES)

    // Act
    await renderPage(StatsPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("stats.noGames")).not.toBeInTheDocument()
  })

  it("fails as a whole when only the game list fails (its recent games would read as none)", async () => {
    // Prepare
    answer(STATS, () => ({ ...emptyStats, total_games_played: 120, total_games_won: 60 }))
    failAll(GAMES)

    // Act
    await renderPage(StatsPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("stats.noGames")).not.toBeInTheDocument()
  })

  it("asks again on Retry, and a real empty record is then the empty state", async () => {
    // Prepare
    failAll(STATS, GAMES)
    await renderPage(StatsPage)
    await expectLoadFailed()
    answer(STATS, () => emptyStats)
    answer(GAMES, () => [])

    // Act
    await retry()

    // Assert
    expect(await screen.findByText("stats.noGames")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(requestsTo(STATS)).toHaveLength(2)
    expect(requestsTo(GAMES)).toHaveLength(2)
  })
})

describe("/achievements", () => {
  it("says the read failed, not 'No achievements yet'", async () => {
    // Prepare
    failAll(ACHIEVEMENTS)

    // Act
    await renderPage(AchievementsPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("achievements.noAchievements")).not.toBeInTheDocument()
  })

  it("asks again on Retry", async () => {
    // Prepare
    failAll(ACHIEVEMENTS)
    await renderPage(AchievementsPage)
    await expectLoadFailed()
    answer(ACHIEVEMENTS, () => [])

    // Act
    await retry()

    // Assert
    expect(await screen.findByText("achievements.noAchievements")).toBeInTheDocument()
    expect(requestsTo(ACHIEVEMENTS)).toHaveLength(2)
  })
})

describe("/challenges", () => {
  it("says the read failed, not 'No challenges yet'", async () => {
    // Prepare
    failAll(CHALLENGES)

    // Act
    await renderPage(ChallengesPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("challenges.emptyTitle")).not.toBeInTheDocument()
    expect(screen.queryByText("challenges.noChallenges")).not.toBeInTheDocument()
  })

  it("asks again on Retry", async () => {
    // Prepare
    failAll(CHALLENGES)
    await renderPage(ChallengesPage)
    await expectLoadFailed()
    answer(CHALLENGES, () => [])

    // Act
    await retry()

    // Assert
    expect(await screen.findByText("challenges.emptyTitle")).toBeInTheDocument()
    expect(requestsTo(CHALLENGES)).toHaveLength(2)
  })
})

describe("/friends", () => {
  it("says the read failed, not 'No friends yet', and counts nothing it does not know", async () => {
    // Prepare
    failAll(FRIENDS, PENDING)

    // Act
    await renderPage(FriendsPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("friends.noFriends")).not.toBeInTheDocument()
    // the tabs used to read "My friends 0 · Pending 0"
    const tabs = screen.getByRole("group", { name: "friends.title" })
    expect(within(tabs).queryByText("0")).not.toBeInTheDocument()
  })

  it("says so on the pending tab when only the requests failed", async () => {
    // Prepare
    answer(FRIENDS, () => [{ friendship_id: "f1", user_id: "u3", username: "Maryam" }])
    failAll(PENDING)
    await renderPage(FriendsPage)
    expect(await screen.findByText("Maryam")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()

    // Act
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /friends\.pendingRequests/ }))
    })

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("friends.noPending")).not.toBeInTheDocument()
  })

  it("asks again on Retry", async () => {
    // Prepare
    failAll(FRIENDS, PENDING)
    await renderPage(FriendsPage)
    await expectLoadFailed()
    answer(FRIENDS, () => [])
    answer(PENDING, () => [])

    // Act
    await retry()

    // Assert
    expect(await screen.findByText("friends.noFriends")).toBeInTheDocument()
    expect(requestsTo(FRIENDS)).toHaveLength(2)
  })
})

describe("/leaderboard", () => {
  it("says the read failed, not 'No players yet', under its test id", async () => {
    // Prepare
    failAll(LEADERBOARD)

    // Act
    await renderPage(LeaderboardPage)

    // Assert
    await expectLoadFailed()
    expect(screen.getByTestId("leaderboard-error")).toBeInTheDocument()
    expect(screen.queryByText("leaderboard.noPlayers")).not.toBeInTheDocument()
    expect(screen.queryAllByTestId("leaderboard-row")).toHaveLength(0)
  })

  it("asks again on Retry, and each player is a leaderboard-row of the table", async () => {
    // Prepare
    failAll(LEADERBOARD)
    await renderPage(LeaderboardPage)
    await expectLoadFailed()
    answer(LEADERBOARD, () => [leaderboardEntry])

    // Act
    await retry()

    // Assert
    const rows = await screen.findAllByTestId("leaderboard-row")
    expect(rows).toHaveLength(1)
    expect(within(screen.getByTestId("leaderboard")).getByText("Maryam")).toBeInTheDocument()
    expect(screen.queryByTestId("leaderboard-error")).not.toBeInTheDocument()
    expect(requestsTo(LEADERBOARD)).toHaveLength(2)
  })
})

describe("/profile", () => {
  it("says the read failed instead of a skeleton that never ends", async () => {
    // Prepare
    failAll(MY_DETAILS)

    // Act
    await renderPage(ProfilePage)

    // Assert
    await expectLoadFailed()
    const identity = screen.getByRole("region", { name: "Yusuf" })
    expect(identity.querySelector('[data-slot="skeleton"]')).toBeNull()
  })

  it("asks again on Retry and shows the saved details", async () => {
    // Prepare
    failAll(MY_DETAILS)
    await renderPage(ProfilePage)
    await expectLoadFailed()
    answer(MY_DETAILS, () => ({ id: "u1", username: "Yusuf", country: null, bio: "Plays every Friday", profile_picture_url: null }))

    // Act
    await retry()

    // Assert
    expect(await screen.findByText("Plays every Friday")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(requestsTo(MY_DETAILS)).toHaveLength(2)
  })
})

describe("/players/$userId", () => {
  it("says the read failed on a 500, not 'This player cannot be found'", async () => {
    // Prepare
    failAll(PROFILE, THEIR_DETAILS, FRIENDSHIP, H2H)

    // Act
    await renderPage(PlayerPage)

    // Assert
    await expectLoadFailed()
    expect(screen.queryByText("profile.playerNotFound")).not.toBeInTheDocument()
  })

  it("says 'not found' on a 404, with no Retry (asking again will not make them exist)", async () => {
    // Prepare
    answer(PROFILE, () => {
      throw httpError(404, { error: "UserNotFoundError", error_key: "errors.api.userNotFound" })
    })

    // Act
    await renderPage(PlayerPage)

    // Assert
    expect(await screen.findByText("profile.playerNotFound")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "common.retry" })).not.toBeInTheDocument()
  })

  it("says 'not found' for an id that is not one (422)", async () => {
    // Prepare
    params.userId = "not-a-uuid"
    answer("GET /api/v1/profiles/users/not-a-uuid", () => {
      throw httpError(422, { detail: [{ type: "uuid_parsing", loc: ["path", "user_id"], msg: "Input should be a valid UUID" }] })
    })

    // Act
    await renderPage(PlayerPage)

    // Assert
    expect(await screen.findByText("profile.playerNotFound")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "common.retry" })).not.toBeInTheDocument()
  })

  it("asks again on Retry and shows the player", async () => {
    // Prepare
    failAll(PROFILE)
    await renderPage(PlayerPage)
    await expectLoadFailed()
    answer(PROFILE, () => publicProfile)

    // Act
    await retry()

    // Assert
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Maryam"))
    expect(screen.queryByText("profile.playerNotFound")).not.toBeInTheDocument()
    expect(requestsTo(PROFILE)).toHaveLength(2)
  })
})
