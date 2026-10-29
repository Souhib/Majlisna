import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import { type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DailyWordState } from "@/api/generated"
import { answer, httpError, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

const auth = vi.hoisted(() => ({ isAuthenticated: false, isLoading: false, user: null as { id: string } | null }))

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: "en" },
  }),
}))
vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children, ...rest }: { to: string; children: ReactNode }) => (
    <a href={to} {...rest}>
      {children}
    </a>
  ),
}))
vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => auth }))

const { DailyWordCard } = await import("../DailyWordCard")

const GET = "GET /api/v1/daily-word"

const state = (over: Partial<DailyWordState> = {}): DailyWordState => ({
  day: "2026-10-29",
  number: 2,
  category: "prophets",
  max_hints: 6,
  hints: ["He built the Ka‘ba with his son"],
  hints_revealed: 1,
  status: "not_started",
  attempts: 0,
  guesses: [],
  score: null,
  streak: 0,
  best_streak: 0,
  solvers_today: 0,
  next_day_at: "2026-10-29T21:00:00Z",
  answer: null,
  ...over,
})

function renderCard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DailyWordCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  resetFakeApi()
  auth.isAuthenticated = false
  auth.user = null
})

describe("DailyWordCard (home)", () => {
  it("names the day's number and theme, shows hint 1 worth 6, and leads to /today", async () => {
    // Prepare
    answer(GET, () => state())

    // Act
    renderCard()

    // Assert
    expect(await screen.findByText("He built the Ka‘ba with his son")).toBeInTheDocument()
    expect(screen.getByText("game.quiz.kalimat.rungLabel(number=1,total=6,points=6)")).toBeInTheDocument()
    expect(screen.getByText("daily.home.rung(number=1)")).toBeInTheDocument()
    expect(screen.getByRole("heading", { level: 2, name: "daily.name" })).toBeInTheDocument()
    expect(screen.getByText("daily.number(number=2)")).toBeInTheDocument()
    expect(screen.getByText(/game\.quiz\.kalimat\.category\.prophets/)).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "daily.home.find" })).toHaveAttribute("href", "/today")
  })

  it("shows a player under way the hint they reached, at what a right answer is worth now", async () => {
    // Prepare: three rungs open, so a right answer is worth 4
    auth.isAuthenticated = true
    auth.user = { id: "u1" }
    answer(GET, () =>
      state({ status: "playing", hints: ["He built the Ka‘ba with his son", "Second", "His fire turned cool"], hints_revealed: 3, attempts: 1 }),
    )

    // Act
    renderCard()

    // Assert
    expect(await screen.findByText("His fire turned cool")).toBeInTheDocument()
    expect(screen.queryByText("He built the Ka‘ba with his son")).not.toBeInTheDocument()
    expect(screen.getByText("game.quiz.kalimat.rungLabel(number=3,total=6,points=4)")).toBeInTheDocument()
    expect(screen.getByText("daily.home.rung(number=3)")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "daily.home.continue" })).toHaveAttribute("href", "/today")
  })

  it("tells a player who gave up so, and offers to see the word", async () => {
    // Prepare
    auth.isAuthenticated = true
    auth.user = { id: "u1" }
    answer(GET, () => state({ status: "gave_up", score: 0, hints_revealed: 2, hints: ["He built the Ka‘ba with his son", "Second"] }))

    // Act
    renderCard()

    // Assert
    expect(await screen.findByText("daily.home.gaveUp")).toBeInTheDocument()
    expect(screen.getByText("He built the Ka‘ba with his son")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "daily.home.see" })).toHaveAttribute("href", "/today")
  })

  it("tells a player who found today's word how it went instead of inviting them to start", async () => {
    // Prepare
    auth.isAuthenticated = true
    auth.user = { id: "u1" }
    answer(GET, () => state({ status: "solved", score: 4 }))

    // Act
    renderCard()

    // Assert
    expect(await screen.findByText("daily.home.solved(count=4)")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "daily.home.see" })).toHaveAttribute("href", "/today")
  })

  it("leaves no card when the day cannot be read", async () => {
    // Prepare
    answer(GET, () => {
      throw httpError(500)
    })

    // Act
    const { container } = renderCard()

    // Assert: after the read's one retry on a server error (a second later)
    await waitFor(() => expect(container).toBeEmptyDOMElement(), { timeout: 3000 })
  })
})
