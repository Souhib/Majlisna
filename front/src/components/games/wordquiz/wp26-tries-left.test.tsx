import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { AnswerInput } from "./AnswerInput"

/**
 * Owner rule (e), the field's half (WP-26, BR-10): a Kalimat round allows five tries. The
 * field says how many are left (the state's `my_attempts_left`), stops at none, and a
 * refusal of a try (409 `errors.api.answerAttemptsExhausted`) is said in the field, in the
 * player's language. The keys are shown with their count so the countdown can be read.
 */
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { count?: number; max?: number; guess?: string }) => {
      if (opts?.count != null) return `${key}:${opts.count}`
      if (opts?.max != null) return `${key}:${opts.max}`
      if (opts?.guess != null) return `${key}:${opts.guess}`
      return key
    },
    i18n: { language: "en" },
  }),
}))

type Result = { correct: boolean; points_earned: number } | { refused: string } | null

function props(overrides: Record<string, unknown> = {}) {
  return {
    onSubmit: vi.fn<(answer: string) => Promise<Result>>().mockResolvedValue({ correct: false, points_earned: 0 }),
    disabled: false,
    answered: false,
    pointsEarned: 0,
    maxAttempts: 5,
    ...overrides,
  }
}

const field = () => screen.getByLabelText("game.quiz.kalimat.answerLabel")
const answerButton = () => screen.getByRole("button", { name: "game.quiz.kalimat.answer" })

async function submit(value: string) {
  fireEvent.change(field(), { target: { value } })
  await act(async () => {
    fireEvent.submit(field().closest("form") as HTMLFormElement)
  })
}

describe("AnswerInput: the tries left (owner rule (e))", () => {
  it("counts the tries down 5, 4, 3, 2, 1 as the state says, the field open throughout", () => {
    // Prepare
    const base = props()
    const { rerender } = render(<AnswerInput {...base} attemptsLeft={5} />)

    for (const left of [5, 4, 3, 2, 1]) {
      // Act
      rerender(<AnswerInput {...base} attemptsLeft={left} />)

      // Assert
      expect(screen.getByText(`game.wordQuiz.triesLeft:${left}`)).toBeInTheDocument()
      expect(field()).not.toBeDisabled()
    }
  })

  it("at 0 the field and the button are disabled, and say that no try is left", () => {
    // Prepare / Act
    render(<AnswerInput {...props()} attemptsLeft={0} />)
    fireEvent.change(field(), { target: { value: "Yunus" } })

    // Assert
    expect(screen.getByText("game.wordQuiz.triesLeft:0")).toBeInTheDocument()
    expect(field()).toBeDisabled()
    expect(answerButton()).toBeDisabled()
  })

  it("sends nothing once no try is left", async () => {
    // Prepare
    const base = props()
    render(<AnswerInput {...base} attemptsLeft={0} />)

    // Act: Enter in a field that still holds a word
    await submit("Yunus")

    // Assert
    expect(base.onSubmit).not.toHaveBeenCalled()
  })

  it("after the last wrong try says the tries are used, never 'try again'", async () => {
    // Prepare: one try left, and it is wrong
    const base = props()
    const { rerender } = render(<AnswerInput {...base} attemptsLeft={1} />)
    await submit("Zakari")

    // Act: the state that follows says none is left
    rerender(<AnswerInput {...base} attemptsLeft={0} />)

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("errors.api.answerAttemptsExhausted:5")
    expect(screen.queryByText(/game\.quiz\.kalimat\.wrongGuess/)).not.toBeInTheDocument()
  })

  it("says a refused try (409) in the field with the server's translated message, and keeps what was typed", async () => {
    // Prepare: the page answers a refusal with its translated text
    const base = props({ onSubmit: vi.fn().mockResolvedValue({ refused: "You have used your 5 tries for this round." }) })
    render(<AnswerInput {...base} attemptsLeft={2} />)

    // Act
    await submit("Yunus")

    // Assert
    expect(screen.getByRole("alert")).toHaveTextContent("You have used your 5 tries for this round.")
    expect(field()).toHaveValue("Yunus")
    expect(field()).toHaveAttribute("aria-invalid", "true")
  })

  it("links the tries left to the field, so it is read with it", () => {
    // Prepare / Act
    render(<AnswerInput {...props()} attemptsLeft={3} />)

    // Assert
    const tries = screen.getByText("game.wordQuiz.triesLeft:3")
    expect(field().getAttribute("aria-describedby")?.split(" ")).toContain(tries.id)
    expect(screen.getByText("game.quiz.kalimat.spellings")).toBeInTheDocument()
  })

  it("keeps focus in the game when the last try closes the field", async () => {
    // Prepare: the player is typing their last try
    const base = props()
    const { rerender } = render(<AnswerInput {...base} attemptsLeft={1} />)
    field().focus()
    await submit("Zakari")

    // Act
    rerender(<AnswerInput {...base} attemptsLeft={0} />)

    // Assert: focus is on what the field now says, not lost to the page
    expect(document.activeElement).not.toBe(document.body)
    expect(document.activeElement).toHaveTextContent("game.wordQuiz.triesLeft:0")
  })

  it("shows no count where the page gives none (a spectator, the word of the day)", () => {
    // Prepare / Act
    render(<AnswerInput {...props()} />)

    // Assert
    expect(screen.queryByText(/game\.wordQuiz\.triesLeft/)).not.toBeInTheDocument()
    expect(field()).not.toBeDisabled()
  })
})
