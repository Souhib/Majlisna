import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChoiceButtons } from "./ChoiceButtons"

const choices = ["Makkah", "Madinah", "Jerusalem", "Damascus"]

function defaultProps(overrides: Record<string, unknown> = {}) {
  return {
    choices,
    onSelect: vi.fn(),
    disabled: false,
    selectedIndex: null,
    correctIndex: null,
    roundPhase: "playing",
    ...overrides,
  }
}

describe("ChoiceButtons", () => {
  it("renders the four choices as radio buttons in a group", () => {
    render(<ChoiceButtons {...defaultProps()} />)
    expect(screen.getByRole("radiogroup")).toBeInTheDocument()
    expect(screen.getAllByRole("radio")).toHaveLength(4)
    expect(screen.getByText("Makkah")).toBeInTheDocument()
    expect(screen.getByText("Damascus")).toBeInTheDocument()
  })

  it("letters them A, B, C, D in a Latin interface", () => {
    render(<ChoiceButtons {...defaultProps()} />)
    expect(screen.getByLabelText("A: Makkah")).toBeInTheDocument()
    expect(screen.getByLabelText("B: Madinah")).toBeInTheDocument()
    expect(screen.getByLabelText("C: Jerusalem")).toBeInTheDocument()
    expect(screen.getByLabelText("D: Damascus")).toBeInTheDocument()
  })

  it("calls onSelect with index when choice is clicked", () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect })} />)
    fireEvent.click(screen.getByLabelText("B: Madinah"))
    expect(onSelect).toHaveBeenCalledWith(1)
  })

  it("does not call onSelect when disabled", () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect, disabled: true })} />)
    fireEvent.click(screen.getByLabelText("A: Makkah"))
    expect(onSelect).not.toHaveBeenCalled()
  })

  it("marks the chosen one with aria-checked and the chosen state", () => {
    render(<ChoiceButtons {...defaultProps({ selectedIndex: 2 })} />)
    expect(screen.getByLabelText("C: Jerusalem")).toHaveAttribute("aria-checked", "true")
    expect(screen.getByLabelText("C: Jerusalem")).toHaveAttribute("data-state", "chosen")
    expect(screen.getByLabelText("A: Makkah")).toHaveAttribute("aria-checked", "false")
  })

  it("is one tab stop, and the arrow keys move between the choices and choose", () => {
    const onSelect = vi.fn()
    render(<ChoiceButtons {...defaultProps({ onSelect, selectedIndex: 1 })} />)
    const radios = screen.getAllByRole("radio")
    expect(radios.map((r) => r.getAttribute("tabindex"))).toEqual(["-1", "0", "-1", "-1"])
    radios[1].focus()
    fireEvent.keyDown(radios[1], { key: "ArrowDown" })
    expect(onSelect).toHaveBeenLastCalledWith(2)
    expect(document.activeElement).toBe(radios[2])
    fireEvent.keyDown(radios[2], { key: "ArrowUp" })
    expect(onSelect).toHaveBeenLastCalledWith(1)
    fireEvent.keyDown(radios[1], { key: "End" })
    expect(onSelect).toHaveBeenLastCalledWith(3)
    fireEvent.keyDown(radios[3], { key: "ArrowRight" })
    expect(onSelect).toHaveBeenLastCalledWith(0)
  })

  it("after the reveal: a list, the right one in brass, a wrong pick struck on its letter", () => {
    const { container } = render(<ChoiceButtons {...defaultProps({ roundPhase: "results", correctIndex: 0, selectedIndex: 1 })} />)
    expect(screen.queryByRole("radio")).not.toBeInTheDocument()
    const items = container.querySelectorAll("li.quiz-choice")
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveAttribute("data-state", "right")
    expect(items[1]).toHaveAttribute("data-state", "wrong")
    expect(items[2]).not.toHaveAttribute("data-state")
    // the choice's words carry no strike: only the letter does (CSS ::after on .choice-letter)
    expect(items[1].querySelector(".choice-text")).toHaveTextContent("Madinah")
    expect(items[0]).toHaveTextContent("game.quiz.mcq.rightAnswer")
    expect(items[1]).toHaveTextContent("game.quiz.mcq.yourWrongAnswer")
  })

  it("prints the tags at the end of each choice", () => {
    render(<ChoiceButtons {...defaultProps({ roundPhase: "results", correctIndex: 2, tags: [null, "you", "3 players", null] })} />)
    expect(screen.getByText("you")).toBeInTheDocument()
    expect(screen.getByText("3 players")).toBeInTheDocument()
  })
})

describe("ChoiceButtons, the reveal's tally threads", () => {
  /** The question open, then the server's reveal: four players, one chose A, two C, one D. */
  function reveal(overrides: Record<string, unknown> = {}) {
    return defaultProps({ roundPhase: "results", correctIndex: 2, selectedIndex: 0, tallies: [1, 0, 2, 1], players: 4, ...overrides })
  }

  const items = (container: HTMLElement) => [...container.querySelectorAll<HTMLLIElement>("li.quiz-choice")]
  const thread = (li: Element) => li.querySelector<HTMLElement>(".choice-tally")

  it("draws each choice's share of the players as a thread under it; the tally text stays the words", () => {
    // Prepare: the question open
    const { container, rerender } = render(<ChoiceButtons {...defaultProps({ selectedIndex: 0 })} />)

    // Act: the server reveals
    rerender(<ChoiceButtons {...reveal({ tags: ["you", "0", "2 players", "1 player"] })} />)

    // Assert: a thread per choice, at its share, a picture only (the tags carry the counts)
    const rows = items(container)
    expect(rows.map((li) => thread(li)?.style.getPropertyValue("--share"))).toEqual(["0.25", "0", "0.5", "0.25"])
    expect(rows.map((li) => thread(li)?.style.getPropertyValue("--i"))).toEqual(["0", "1", "2", "3"])
    for (const li of rows) expect(thread(li)).toHaveAttribute("aria-hidden", "true")
    // a choice nobody picked keeps its bare warp: no thread to weave (an animation with no
    // visible change is one the compositor refuses)
    expect(rows.map((li) => !!thread(li)?.querySelector("i"))).toEqual([true, false, true, true])
    expect(screen.getByText("2 players")).toBeInTheDocument()
    // the thread is under the words, never over them (a choice may be a sacred name)
    for (const li of rows) expect(li.querySelector(".choice-text .choice-tally")).toBeNull()
    // the right one in brass (CSS on data-state), your wrong pick keeps its struck letter
    expect(rows[2]).toHaveAttribute("data-state", "right")
    expect(rows[0]).toHaveAttribute("data-state", "wrong")
  })

  it("weaves the threads in and presses the right letter only when the reveal happens on screen", () => {
    // Prepare
    const { container, rerender } = render(<ChoiceButtons {...defaultProps({ selectedIndex: 0 })} />)

    // Act: the reveal arrives
    rerender(<ChoiceButtons {...reveal()} />)

    // Assert: the list weaves; the right choice's letter is a seal pressed after the crossfade
    const list = container.querySelector("ul")
    expect(list).toHaveAttribute("data-weave", "true")
    const letter = items(container)[2].querySelector(".choice-letter")
    expect(letter).toHaveClass("seal-press")
    expect(letter).toHaveAttribute("data-seal-index", "0")
    // only the right one presses
    expect(items(container).filter((li) => li.querySelector(".choice-letter.seal-press"))).toHaveLength(1)

    // Act: a refetch or a socket push of the same reveal
    rerender(<ChoiceButtons {...reveal({ tags: ["you", null, null, null] })} />)

    // Assert: the same list, still marked: nothing restarts
    expect(container.querySelector("ul")).toBe(list)
    expect(list).toHaveAttribute("data-weave", "true")
  })

  it("does not weave on a page opened (or reloaded) at the reveal", () => {
    const { container } = render(<ChoiceButtons {...reveal()} />)

    expect(container.querySelector("ul")).not.toHaveAttribute("data-weave")
    expect(container.querySelector(".seal-press")).toBeNull()
    // the final lengths are there all the same
    expect(items(container).map((li) => thread(li)?.style.getPropertyValue("--share"))).toEqual(["0.25", "0", "0.5", "0.25"])
  })

  it("weaves again at the next question's reveal", () => {
    // Prepare: a first reveal seen, then the next question
    const { container, rerender } = render(<ChoiceButtons {...defaultProps()} />)
    rerender(<ChoiceButtons {...reveal()} />)
    rerender(<ChoiceButtons {...defaultProps()} />)
    expect(container.querySelector("ul")).toBeNull()

    // Act
    rerender(<ChoiceButtons {...reveal({ tallies: [0, 4, 0, 0], correctIndex: 1 })} />)

    // Assert
    expect(container.querySelector("ul")).toHaveAttribute("data-weave", "true")
    expect(items(container)[1].querySelector(".choice-letter")).toHaveClass("seal-press")
  })

  it("draws no thread without the server's tallies", () => {
    const { container } = render(<ChoiceButtons {...reveal({ tallies: null })} />)
    expect(container.querySelector(".choice-tally")).toBeNull()
    expect(items(container)[0]).not.toHaveAttribute("data-tally")
  })
})

describe("ChoiceButtons, the CSS of the tally threads", () => {
  // vitest runs with `css: false`: read the file.
  const css = readFileSync(resolve(process.cwd(), "src/styles/pages/quiz.css"), "utf8")

  /** One CSS rule's body, by its exact selector. */
  function rule(selector: string) {
    const at = css.indexOf(`${selector} {`)
    if (at < 0) return null
    return css.slice(at + selector.length + 2, css.indexOf("}", at))
  }

  it("places a full-length thread by a transform inside a clipped box, never by its width", () => {
    expect(rule(".quiz-choice .choice-tally")).toMatch(/overflow: hidden;/)
    expect(rule(".quiz-choice .choice-tally")).toMatch(/height: 3px;/)
    const thread = rule(".quiz-choice .choice-tally > i") ?? ""
    expect(thread).toMatch(/transform: translateX\(calc\(\(var\(--share, 0\) - 1\) \* 100%\)\);/)
    expect(thread).toMatch(/var\(--band-khayt\)/)
    expect(thread).not.toMatch(/width|transition/)
    expect(rule('[dir="rtl"] .quiz-choice .choice-tally > i')).toMatch(/transform: translateX\(calc\(\(1 - var\(--share, 0\)\) \* 100%\)\);/)
    expect(rule('.quiz-choice[data-state="right"] .choice-tally > i')).toMatch(/background: var\(--brass\);/)
  })

  it("weaves it in from the reading start over 640 ms on the qalam's curve, 30 ms apart", () => {
    const weave = rule('.quiz-choices[data-weave="true"] .choice-tally > i') ?? ""
    // backwards only: the end is the thread's own place, so nothing lingers once it has landed
    expect(weave).toMatch(/animation: quiz-tally var\(--dur-authored\) var\(--ease-ink\) backwards;/)
    expect(weave).toMatch(/animation-delay: calc\(var\(--i, 0\) \* var\(--stagger\)\);/)
    // one keyframes for both directions: the reading start is a custom property the direction sets
    expect(rule("@keyframes quiz-tally")).toMatch(/transform: translateX\(var\(--tally-from\)\);/)
    expect(rule(".quiz-choices")).toMatch(/--tally-from: -100%;/)
    expect(rule('[dir="rtl"] .quiz-choices')).toMatch(/--tally-from: 100%;/)
  })

  it("changes no animation's name with the direction: a language switch mid-reveal restarts nothing", () => {
    // a new animation-name is a new animation: the thread would be woven again from the start
    expect(css).not.toMatch(/@keyframes quiz-tally-rtl/)
    for (const match of css.matchAll(/\[dir="rtl"\][^{]*\{([^}]*)\}/g)) expect(match[1]).not.toMatch(/animation(-name)?:/)
  })

  it("under reduced motion, shows the final lengths with a 140 ms fade", () => {
    const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"))
    expect(reduced).toMatch(/\.quiz-choices\[data-weave="true"\] \.choice-tally > i \{\s*animation: fade-in 140ms linear both;/)
  })
})
