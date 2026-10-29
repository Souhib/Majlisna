import { act, fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ANSWER_MAX_LENGTH, AnswerInput } from "./AnswerInput"

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    onSubmit: vi.fn().mockResolvedValue({ correct: false, points_earned: 0 }),
    disabled: false,
    answered: false,
    pointsEarned: 0,
    ...overrides,
  }
}

const field = () => screen.getByLabelText("game.quiz.kalimat.answerLabel")
const answerButton = () => screen.getByRole("button", { name: "game.quiz.kalimat.answer" })

describe("AnswerInput", () => {
  it("renders a labelled text field with the existing placeholder, and the Answer button", () => {
    render(<AnswerInput {...defaultProps()} />)
    expect(field()).toHaveAttribute("type", "text")
    expect(field()).toHaveAttribute("placeholder", "game.wordQuiz.typeYourAnswer")
    expect(answerButton()).toBeInTheDocument()
  })

  it("says that every spelling counts", () => {
    render(<AnswerInput {...defaultProps()} />)
    expect(screen.getByText("game.quiz.kalimat.spellings")).toBeInTheDocument()
  })

  it("takes no more than the server accepts, so a long answer never earns a bare 422", () => {
    const { unmount } = render(<AnswerInput {...defaultProps()} />)
    expect(field()).toHaveAttribute("maxlength", String(ANSWER_MAX_LENGTH))
    unmount()
    render(<AnswerInput {...defaultProps({ maxLength: 40 })} />)
    expect(field()).toHaveAttribute("maxlength", "40")
  })

  it("words its hint and a wrong guess as the page asks", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ correct: false, points_earned: 0 })
    render(
      <AnswerInput
        {...defaultProps({ onSubmit, hint: "A wrong try opens the next hint.", wrongGuessMessage: (guess: string) => `${guess}: hint 2 is out` })}
      />,
    )
    expect(screen.getByText("A wrong try opens the next hint.")).toBeInTheDocument()
    fireEvent.change(field(), { target: { value: "Zakari" } })
    await act(async () => {
      fireEvent.submit(field().closest("form")!)
    })
    expect(screen.getByRole("alert")).toHaveTextContent("Zakari: hint 2 is out")
  })

  it("keeps the button disabled while the field is empty", () => {
    render(<AnswerInput {...defaultProps()} />)
    expect(answerButton()).toBeDisabled()
    fireEvent.change(field(), { target: { value: "Quran" } })
    expect(answerButton()).not.toBeDisabled()
  })

  it("submits the trimmed answer", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ correct: true, points_earned: 5 })
    render(<AnswerInput {...defaultProps({ onSubmit })} />)
    fireEvent.change(field(), { target: { value: "  Quran  " } })
    await act(async () => {
      fireEvent.submit(field().closest("form")!)
    })
    expect(onSubmit).toHaveBeenCalledWith("Quran")
  })

  it("names a wrong guess in an alert, clears the field, and drops the alert when typing again", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ correct: false, points_earned: 0 })
    render(<AnswerInput {...defaultProps({ onSubmit })} />)
    fireEvent.change(field(), { target: { value: "Zakari" } })
    await act(async () => {
      fireEvent.submit(field().closest("form")!)
    })
    expect(screen.getByRole("alert")).toHaveTextContent("game.quiz.kalimat.wrongGuess")
    expect(field()).toHaveValue("")
    expect(field()).toHaveAttribute("aria-invalid", "true")
    fireEvent.change(field(), { target: { value: "Z" } })
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("does not submit twice while the first answer is in flight", async () => {
    let resolve: (v: { correct: boolean; points_earned: number }) => void = () => {}
    const onSubmit = vi.fn().mockReturnValue(new Promise((r) => (resolve = r)))
    render(<AnswerInput {...defaultProps({ onSubmit })} />)
    fireEvent.change(field(), { target: { value: "Musa" } })
    fireEvent.submit(field().closest("form")!)
    fireEvent.submit(field().closest("form")!)
    expect(onSubmit).toHaveBeenCalledOnce()
    await act(async () => resolve({ correct: true, points_earned: 4 }))
  })

  it("locks once found: a status with the points, and no field", () => {
    render(<AnswerInput {...defaultProps({ answered: true, pointsEarned: 5, answeredNote: "2 of 5 answered" })} />)
    const status = screen.getByRole("status")
    expect(status).toHaveTextContent("game.quiz.kalimat.found")
    expect(status).toHaveTextContent("+5")
    expect(status).toHaveTextContent("2 of 5 answered")
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument()
  })

  it("disables the field when disabled", () => {
    render(<AnswerInput {...defaultProps({ disabled: true })} />)
    expect(field()).toBeDisabled()
  })
})
