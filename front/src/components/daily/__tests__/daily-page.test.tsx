import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { type ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { DailyWordState } from "@/api/generated"
import { answer, httpError, requestsTo, resetFakeApi } from "@/components/notebook/__tests__/fake-api"

const i18nState = vi.hoisted(() => ({ language: "en" }))
const auth = vi.hoisted(() => ({ isAuthenticated: false, isLoading: false, user: null as { id: string } | null }))
const toasts = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), plain: vi.fn() }))

// t names its parameters, so a test sees what was asked for in which words
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
      return params.length ? `${key}(${params.join(",")})` : key
    },
    i18n: { language: i18nState.language },
  }),
  Trans: ({ i18nKey }: { i18nKey: string }) => i18nKey,
}))

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, search, children, ...rest }: { to: string; search?: { redirect?: string }; children: ReactNode }) => (
    <a href={search?.redirect ? `${to}?redirect=${search.redirect}` : to} {...rest}>
      {children}
    </a>
  ),
}))

vi.mock("@/api/client", async () => (await import("@/components/notebook/__tests__/fake-api")).clientModule)
vi.mock("@/providers/AuthProvider", () => ({ useAuth: () => auth }))
vi.mock("sonner", () => ({ toast: Object.assign(toasts.plain, { error: toasts.error, success: toasts.success }) }))

const { DailyWordPage } = await import("../DailyWordPage")

const GET = "GET /api/v1/daily-word"
const DAY = "2026-10-29"

const state = (over: Partial<DailyWordState> = {}): DailyWordState => ({
  day: DAY,
  number: 2,
  category: "places",
  max_hints: 6,
  hints: ["An oasis in the Hijaz"],
  hints_revealed: 1,
  status: "not_started",
  attempts: 0,
  guesses: [],
  score: null,
  streak: null,
  best_streak: null,
  solvers_today: 3,
  next_day_at: "2099-01-01T21:00:00Z",
  answer: null,
  ...over,
})

const finished = (over: Partial<DailyWordState> = {}): DailyWordState =>
  state({
    status: "solved",
    hints: ["An oasis in the Hijaz", "A battle in year 7", "Its fortresses fell"],
    hints_revealed: 3,
    attempts: 2,
    guesses: ["Badr", "Khaybar"],
    score: 4,
    streak: 2,
    best_streak: 5,
    answer: { word_display: "Khaybar", word_ar: "خيبر", word_ar_vocalized: "خَيْبَر", explanation: "An oasis north of Madinah.", kept: false, entry_id: null },
    ...over,
  })

function signIn() {
  auth.isAuthenticated = true
  auth.user = { id: "u1" }
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <DailyWordPage />
    </QueryClientProvider>,
  )
}

const ladder = () => screen.getByRole("list", { name: "game.quiz.kalimat.ladder" })

beforeEach(() => {
  resetFakeApi()
  i18nState.language = "en"
  auth.isAuthenticated = false
  auth.isLoading = false
  auth.user = null
  toasts.error.mockReset()
  toasts.plain.mockReset()
})

describe("/today, signed out", () => {
  it("shows the number, the day, the theme and hint 1, and Sign in to play where the field would be", async () => {
    // Prepare
    answer(GET, () => state())

    // Act
    renderPage()

    // Assert
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("daily.name")
    expect(await screen.findByText("An oasis in the Hijaz")).toBeInTheDocument()
    expect(screen.getByText("daily.number(number=2)")).toBeInTheDocument()
    expect(screen.getByText("game.quiz.kalimat.category.places")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /daily\.play\.signIn/ })).toHaveAttribute("href", "/auth/login?redirect=/today")
    expect(screen.queryByLabelText("game.quiz.kalimat.answerLabel")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /daily\.ladder\.another/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /daily\.play\.giveUp/ })).not.toBeInTheDocument()
    expect(screen.getByText("daily.foundToday(count=3)")).toBeInTheDocument()
  })

  it("waits for the sign-in to settle before reading, so a stale token is never sent", async () => {
    // Prepare
    auth.isLoading = true
    answer(GET, () => state())

    // Act
    const { rerender } = renderPage()
    await act(async () => {})

    // Assert: nothing asked while the provider refreshes; asked once it has
    expect(requestsTo(GET)).toHaveLength(0)
    auth.isLoading = false
    rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <DailyWordPage />
      </QueryClientProvider>,
    )
    await screen.findByText("An oasis in the Hijaz")
    expect(requestsTo(GET)[0].params).toEqual({ lang: "en" })
  })
})

describe("/today, playing", () => {
  beforeEach(signIn)

  it("offers the next rung with the points at stake, and moves focus to the hint it reveals", async () => {
    // Prepare
    answer(GET, () => state())
    answer("POST /api/v1/daily-word/hint", () => state({ status: "playing", hints: ["An oasis in the Hijaz", "A battle in year 7"], hints_revealed: 2 }))
    renderPage()
    const offer = await screen.findByRole("button", { name: "daily.ladder.another(from=6,count=5)" })

    // Act
    fireEvent.click(offer)

    // Assert
    await screen.findByText("A battle in year 7")
    const rung = within(ladder()).getAllByRole("listitem")[1]
    await waitFor(() => expect(document.activeElement).toBe(rung))
    expect(rung).toHaveAttribute("aria-current", "step")
    expect(requestsTo("POST /api/v1/daily-word/hint")[0].params).toEqual({ lang: "en", day: DAY })
    expect(screen.getByRole("button", { name: "daily.ladder.another(from=5,count=4)" })).toBeInTheDocument()
  })

  it("lists a wrong try, says which hint it opened, and keeps focus in the field for the next one", async () => {
    // Prepare: the server opens rung 2 on a wrong try
    answer(GET, () => state({ status: "playing" }))
    answer("POST /api/v1/daily-word/guess", () => ({
      correct: false,
      state: state({ status: "playing", attempts: 1, guesses: ["Badr"], hints: ["An oasis in the Hijaz", "A battle in year 7"], hints_revealed: 2 }),
    }))
    renderPage()
    const field = await screen.findByLabelText("game.quiz.kalimat.answerLabel")
    expect(field).toHaveAttribute("maxlength", "100")
    expect(screen.getByText("daily.play.fieldHint")).toBeInTheDocument()

    // Act
    field.focus()
    fireEvent.change(field, { target: { value: "Badr" } })
    await act(async () => {
      fireEvent.submit(field.closest("form")!)
    })

    // Assert
    expect(requestsTo("POST /api/v1/daily-word/guess")[0]).toMatchObject({ data: { answer: "Badr" }, params: { lang: "en", day: DAY } })
    expect(screen.getByRole("alert")).toHaveTextContent("daily.play.wrongTry(guess=Badr,number=2)")
    expect(within(ladder()).getByText("A battle in year 7")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "daily.ladder.another(from=5,count=4)" })).toBeInTheDocument()
    const tries = screen.getByRole("region", { name: "daily.play.tries(count=1)" })
    expect(within(tries).getByText("Badr")).toBeInTheDocument()
    expect(document.activeElement).toBe(screen.getByLabelText("game.quiz.kalimat.answerLabel"))
  })

  it("says a wrong try on the last rung opened nothing", async () => {
    // Prepare: every rung is out already
    const six = ["1", "2", "3", "4", "5", "6"].map((n) => `Hint ${n}`)
    answer(GET, () => state({ status: "playing", hints: six, hints_revealed: 6 }))
    answer("POST /api/v1/daily-word/guess", () => ({
      correct: false,
      state: state({ status: "playing", hints: six, hints_revealed: 6, attempts: 6, guesses: ["Badr"] }),
    }))
    renderPage()
    const field = await screen.findByLabelText("game.quiz.kalimat.answerLabel")

    // Act
    fireEvent.change(field, { target: { value: "Badr" } })
    await act(async () => {
      fireEvent.submit(field.closest("form")!)
    })

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("daily.play.wrongTryLast(guess=Badr)")
  })

  it("reveals the word on a right guess and moves focus to the reveal", async () => {
    // Prepare
    answer(GET, () => state({ status: "playing" }))
    answer("POST /api/v1/daily-word/guess", () => ({ correct: true, state: finished() }))
    renderPage()
    const field = await screen.findByLabelText("game.quiz.kalimat.answerLabel")

    // Act
    fireEvent.change(field, { target: { value: "khaybar" } })
    await act(async () => {
      fireEvent.submit(field.closest("form")!)
    })

    // Assert
    const title = await screen.findByRole("heading", { name: "daily.reveal.solvedTitle" })
    await waitFor(() => expect(document.activeElement).toBe(title))
    expect(screen.getByText("خَيْبَر")).toBeInTheDocument()
    expect(screen.getByText("daily.reveal.foundAt(number=3) · game.quiz.kalimat.pointsSr(count=4)")).toBeInTheDocument()
    expect(screen.getByText("An oasis north of Madinah.")).toBeInTheDocument()
  })

  it("gives up only once confirmed, then reveals the word", async () => {
    // Prepare
    answer(GET, () => state({ status: "playing" }))
    answer("POST /api/v1/daily-word/give-up", () => finished({ status: "gave_up", score: 0, streak: 0 }))
    renderPage()

    // Act: open the confirmation, then confirm
    fireEvent.click(await screen.findByRole("button", { name: "daily.play.giveUp" }))
    const dialog = await screen.findByRole("alertdialog")
    expect(requestsTo("POST /api/v1/daily-word/give-up")).toHaveLength(0)
    fireEvent.click(within(dialog).getByRole("button", { name: "daily.play.giveUpConfirm" }))

    // Assert
    const title = await screen.findByRole("heading", { name: "daily.reveal.gaveUpTitle" })
    await waitFor(() => expect(document.activeElement).toBe(title))
    expect(screen.getByText("daily.reveal.gaveUp")).toBeInTheDocument()
    expect(requestsTo("POST /api/v1/daily-word/give-up")[0].params).toEqual({ lang: "en", day: DAY })
  })

  it("reads the new day when the server says a new word is out", async () => {
    // Prepare
    answer(GET, () => state({ status: "playing" }))
    answer("POST /api/v1/daily-word/guess", () => {
      throw httpError(409, { error_key: "errors.api.dailyWordNotToday" })
    })
    renderPage()
    const field = await screen.findByLabelText("game.quiz.kalimat.answerLabel")

    // Act
    fireEvent.change(field, { target: { value: "Badr" } })
    await act(async () => {
      fireEvent.submit(field.closest("form")!)
    })

    // Assert: said once, not as an error, and the day read again
    expect(toasts.plain).toHaveBeenCalledWith("errors.api.dailyWordNotToday")
    expect(toasts.error).not.toHaveBeenCalled()
    await waitFor(() => expect(requestsTo(GET)).toHaveLength(2))
  })
})

describe("/today, finished", () => {
  beforeEach(signIn)

  it("shows a solved day's reveal without taking focus on load, with the streaks and the ladder as played", async () => {
    // Prepare
    answer(GET, () => finished())

    // Act
    renderPage()

    // Assert
    const title = await screen.findByRole("heading", { name: "daily.reveal.solvedTitle" })
    expect(document.activeElement).not.toBe(title)
    expect(screen.getByText("daily.reveal.streak").parentElement).toHaveTextContent("2")
    expect(screen.getByText("daily.reveal.bestStreak").parentElement).toHaveTextContent("5")
    expect(within(ladder()).getAllByRole("listitem")[2]).toHaveTextContent("daily.ladder.found")
    expect(screen.getByText("daily.play.rightTry")).toBeInTheDocument()
    expect(screen.queryByLabelText("game.quiz.kalimat.answerLabel")).not.toBeInTheDocument()
  })

  it("settles the ladder of a day given up: no rung is in play", async () => {
    // Prepare
    answer(GET, () => finished({ status: "gave_up", score: 0, streak: 0, guesses: ["Badr"] }))

    // Act
    renderPage()

    // Assert
    await screen.findByRole("heading", { name: "daily.reveal.gaveUpTitle" })
    expect(within(ladder()).queryByRole("listitem", { current: "step" })).not.toBeInTheDocument()
    expect(screen.queryByText("daily.play.rightTry")).not.toBeInTheDocument()
  })

  it("keeps the word in the kunnash, then links to it with focus following", async () => {
    // Prepare
    answer(GET, () => finished())
    answer("POST /api/v1/daily-word/keep", () => ({ added: 1, already_kept: 0, entries: [{ id: "e1" }] }))
    renderPage()

    // Act
    fireEvent.click(await screen.findByRole("button", { name: "daily.reveal.keep" }))

    // Assert
    const kept = await screen.findByRole("link", { name: "daily.reveal.kept" })
    expect(kept).toHaveAttribute("href", "/notebook")
    await waitFor(() => expect(document.activeElement).toBe(kept))
    expect(requestsTo("POST /api/v1/daily-word/keep")[0].params).toEqual({ lang: "en", day: DAY })
  })

  it("copies a share line that never carries the answer", async () => {
    // Prepare
    const writeText = vi.fn(async () => {})
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true })
    answer(GET, () => finished())
    renderPage()

    const share = await screen.findByRole("button", { name: "daily.share.action" })

    // Act
    fireEvent.click(share)

    // Assert (findBy* waits on its own: inside act() it switches act's environment off)
    expect(await screen.findByRole("button", { name: "daily.share.copied" })).toBeInTheDocument()
    expect(writeText).toHaveBeenCalledWith("daily.share.solved(number=2,url=majlisna.app/today,hint=3,total=6)")
  })
})
