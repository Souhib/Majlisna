import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest"
import { PlayerScoreboard } from "../PlayerScoreboard"

const players = [
  { user_id: "u1", username: "Alice", total_score: 10, current_round_answered: true, current_round_points: 3 },
  { user_id: "u2", username: "Bob", total_score: 20, current_round_answered: false, current_round_points: 0 },
  { user_id: "u3", username: "Charlie", total_score: 15, current_round_answered: true, current_round_points: 5 },
]

const rows = () => within(screen.getByTestId("quiz-scoreboard")).getAllByRole("listitem")

describe("PlayerScoreboard", () => {
  it("renders the scores heading", () => {
    render(<PlayerScoreboard players={players} />)
    expect(screen.getByRole("heading", { name: "game.quiz.scores" })).toBeInTheDocument()
  })

  it("lists players by total score, descending, with their scores and what this round earned them", () => {
    render(<PlayerScoreboard players={players} />)
    expect(rows().map((r) => r.textContent)).toEqual(["1Bob20", "2Charlie15+5", "3Alice10+3"])
  })

  it("lets a tie share its place", () => {
    render(<PlayerScoreboard players={[...players, { ...players[0], user_id: "u4", username: "Dina", total_score: 15 }]} />)
    expect(rows().map((r) => r.firstElementChild?.textContent)).toEqual(["1", "2", "2", "4"])
  })

  it("marks your own row", () => {
    render(<PlayerScoreboard players={players} currentUserId="u2" />)
    expect(rows()[0]).toHaveAttribute("data-you", "true")
    expect(rows()[0]).toHaveTextContent("game.quiz.you")
    expect(rows()[1]).not.toHaveAttribute("data-you")
  })

  it("says who has answered this round, in words, only when asked to", () => {
    const { rerender } = render(<PlayerScoreboard players={players} />)
    expect(screen.queryByRole("img", { name: "game.quiz.hasAnswered" })).not.toBeInTheDocument()
    rerender(<PlayerScoreboard players={players} showAnswered />)
    expect(screen.getAllByRole("img", { name: "game.quiz.hasAnswered" })).toHaveLength(2)
    expect(screen.getAllByRole("img", { name: "game.quiz.stillThinking" })).toHaveLength(1)
    expect(screen.getByText("game.quiz.answeredCount")).toBeInTheDocument()
  })

  it("shows the totals the server sends, without taking this round’s points off again", () => {
    // The Quiz's server already holds a round's points back while its question is open;
    // the scoreboard must not subtract `current_round_points` a second time.
    render(<PlayerScoreboard players={players} />)
    expect(rows().map((r) => r.querySelector(".score-total")?.textContent)).toEqual(["20", "15", "10"])
  })

  it("keeps the gain's slot on every row, gained or not, so a first gain moves no total", () => {
    // Prepare: nobody has gained yet (Kalimat mid-round, before anyone finds the word)
    const none = players.map((p) => ({ ...p, current_round_points: 0 }))
    const { rerender } = render(<PlayerScoreboard players={none} />)
    const slots = rows().map((r) => r.querySelector(".score-gain-slot"))
    expect(slots.every((slot) => slot !== null && slot.textContent === "")).toBe(true)

    // Act: a player finds the word
    rerender(<PlayerScoreboard players={none.map((p) => (p.user_id === "u1" ? { ...p, total_score: 30, current_round_points: 3 } : p))} />)

    // Assert: the same slots, still on every row; only the finder's holds a gain
    const after = rows()
    expect(after.map((r) => r.querySelector(".score-gain-slot"))).toEqual(expect.arrayContaining(slots))
    expect(after.map((r) => r.querySelector(".score-gain")?.textContent ?? null)).toEqual(["+3", null, null])
  })

  it("renders with empty players array", () => {
    render(<PlayerScoreboard players={[]} />)
    expect(screen.getByRole("heading", { name: "game.quiz.scores" })).toBeInTheDocument()
  })
})

/**
 * Scores, woven (motion spec 9): when the totals change, the list is already in its new
 * order (truth first) and each row travels from where it was; then each player's thread is
 * written longer by what they earned, and the gain appears. happy-dom has no layout and no
 * Web Animations: `offsetTop` is stubbed from the row's place in the list, `Element.animate`
 * is a recording fake.
 */
interface FakeAnimation {
  cancel: Mock
}

interface AnimateCall {
  el: Element
  keyframes: Keyframe[]
  options: KeyframeAnimationOptions
  anim: FakeAnimation
}

const ROW = 48
let calls: AnimateCall[] = []

function stubReducedMotion(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: reduce && query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

/** translateX(…%) → the number of percent. */
function shiftX(keyframe: Keyframe): number {
  const match = /^translateX\((-?[\d.]+)%\)$/.exec(String(keyframe.transform))
  if (!match) throw new Error(`not a translateX keyframe: ${String(keyframe.transform)}`)
  return Number(match[1])
}

function row(container: HTMLElement, name: string) {
  const li = [...container.querySelectorAll("li")].find((el) => el.textContent?.includes(name))
  if (!li) throw new Error(`no row for ${name}`)
  return li as HTMLLIElement
}

const rowMoves = (container: HTMLElement, name: string) => calls.filter((c) => c.el === row(container, name))
const threadMoves = (container: HTMLElement, name: string) => calls.filter((c) => c.el === row(container, name).querySelector(".score-yarn > i"))
const gainFades = (container: HTMLElement, name: string) => calls.filter((c) => c.el === row(container, name).querySelector(".score-gain"))

/** A table of three after `round` rounds of The Quiz (3 points a question at most, 10 questions). */
function table(scores: Record<string, [number, number]>) {
  return Object.entries(scores).map(([username, [total, gained]], i) => ({
    user_id: `u${i + 1}`,
    username,
    total_score: total,
    current_round_answered: true,
    current_round_points: gained,
  }))
}

describe("PlayerScoreboard, the woven scores", () => {
  beforeEach(() => {
    calls = []
    stubReducedMotion(false)
    Object.defineProperty(HTMLElement.prototype, "animate", {
      configurable: true,
      writable: true,
      value: vi.fn(function (this: Element, keyframes: Keyframe[], options: KeyframeAnimationOptions) {
        const anim: FakeAnimation = { cancel: vi.fn() }
        calls.push({ el: this, keyframes, options, anim })
        return anim
      }),
    })
    // a row's layout place is its place in the list
    Object.defineProperty(HTMLLIElement.prototype, "offsetTop", {
      configurable: true,
      get(this: HTMLLIElement) {
        return this.parentElement ? [...this.parentElement.children].indexOf(this) * ROW : 0
      },
    })
  })

  afterEach(() => {
    delete (HTMLElement.prototype as { animate?: unknown }).animate
    delete (HTMLLIElement.prototype as { offsetTop?: unknown }).offsetTop
    vi.unstubAllGlobals()
    document.documentElement.removeAttribute("dir")
  })

  // Before the reveal: Bob 6, Charlie 5, Alice 4. The reveal: Alice +3, Charlie +2, Bob 0.
  const before = table({ Alice: [4, 0], Bob: [6, 0], Charlie: [5, 0] })
  const after = table({ Alice: [7, 3], Bob: [6, 0], Charlie: [7, 2] })

  it("draws each player's thread as their share of the most the game can give", () => {
    const { container } = render(<PlayerScoreboard players={before} maxScore={30} />)

    expect(row(container, "Bob").style.getPropertyValue("--share")).toBe(String(6 / 30))
    expect(row(container, "Alice").style.getPropertyValue("--share")).toBe(String(4 / 30))
    expect(row(container, "Bob").querySelector(".score-yarn")).toHaveAttribute("aria-hidden", "true")
  })

  it("measures against the leader when it is not told the game's maximum", () => {
    const { container } = render(<PlayerScoreboard players={before} />)

    expect(row(container, "Bob").style.getPropertyValue("--share")).toBe("1")
    expect(row(container, "Alice").style.getPropertyValue("--share")).toBe(String(4 / 6))
  })

  it("moves nothing on the first state (a page load) nor on the same scores sent again", () => {
    // Act: a load, then a refetch and a socket push of the same totals
    const { rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)
    rerender(<PlayerScoreboard players={before.map((p) => ({ ...p }))} maxScore={30} />)
    rerender(<PlayerScoreboard players={before.map((p) => ({ ...p }))} maxScore={30} showAnswered />)

    // Assert
    expect(calls).toHaveLength(0)
  })

  it("puts the list in its new order at once, and each row travels there from its old place", () => {
    // Prepare: Bob, Charlie, Alice
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)

    // Act: the reveal
    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    // Assert: the DOM is final (Alice, Charlie, Bob) before anything moves
    expect(rows().map((r) => r.querySelector(".score-total")?.textContent)).toEqual(["7", "7", "6"])
    expect(rows()[0]).toHaveTextContent("Alice")
    // Alice comes up from the third row, Bob goes down from the first, Charlie stays
    const [alice] = rowMoves(container, "Alice")
    // ending on the identity the row rests at (quiz.css), so its end lays nothing out
    expect(alice.keyframes).toEqual([{ transform: `translateY(${2 * ROW}px)` }, { transform: "translateY(0px)" }])
    expect(alice.options).toEqual({ duration: 320, easing: "cubic-bezier(0.22, 1, 0.36, 1)", delay: 0, fill: "backwards" })
    const [bob] = rowMoves(container, "Bob")
    expect(bob.keyframes).toEqual([{ transform: `translateY(${-2 * ROW}px)` }, { transform: "translateY(0px)" }])
    expect(bob.options.delay).toBe(60)
    expect(rowMoves(container, "Charlie")).toHaveLength(0)
  })

  it("finds a row's old place in the layout of the moment, not in one remembered from an earlier change", () => {
    // Prepare: Bob, Charlie, Alice in 48 px rows
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)
    // ...then the rows grow (the Arabic interface sets rem at 110 %, a font arrives late)
    Object.defineProperty(HTMLLIElement.prototype, "offsetTop", {
      configurable: true,
      get(this: HTMLLIElement) {
        return this.parentElement ? [...this.parentElement.children].indexOf(this) * 60 : 0
      },
    })

    // Act: the reveal
    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    // Assert: Alice comes up two of today's rows, not two of yesterday's
    expect(rowMoves(container, "Alice")[0].keyframes[0]).toEqual({ transform: "translateY(120px)" })
    expect(rowMoves(container, "Bob")[0].keyframes[0]).toEqual({ transform: "translateY(-120px)" })
  })

  it("writes each thread longer by what was earned, from the reading start, once the rows have arrived", () => {
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)

    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    // Alice 4 → 7 of 30, Charlie 5 → 7: 640 ms on the qalam's curve, 320 ms after the row starts
    const [alice] = threadMoves(container, "Alice")
    expect(alice.keyframes).toHaveLength(2)
    expect(shiftX(alice.keyframes[0])).toBeCloseTo(-(1 - 4 / 30) * 100, 2)
    expect(shiftX(alice.keyframes[1])).toBeCloseTo(-(1 - 7 / 30) * 100, 2)
    expect(alice.options).toEqual({ duration: 640, easing: "cubic-bezier(0.45, 0.05, 0.2, 1)", delay: 320, fill: "backwards" })
    const [charlie] = threadMoves(container, "Charlie")
    expect(shiftX(charlie.keyframes[0])).toBeCloseTo(-(1 - 5 / 30) * 100, 2)
    expect(charlie.options.delay).toBe(320 + 30)
    // Bob earned nothing: his thread stays
    expect(threadMoves(container, "Bob")).toHaveLength(0)
  })

  it("fades the gain in after 320 ms", () => {
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)

    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    expect(row(container, "Alice").querySelector(".score-gain")).toHaveTextContent("+3")
    const [fade] = gainFades(container, "Alice")
    expect(fade.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(fade.options).toEqual({ duration: 180, easing: "cubic-bezier(0.16, 1, 0.3, 1)", delay: 320, fill: "backwards" })
    expect(gainFades(container, "Charlie")).toHaveLength(1)
    expect(row(container, "Bob").querySelector(".score-gain")).toBeNull()
  })

  it("staggers the rows 30 ms apart, 240 ms at most", () => {
    // Prepare: twelve players, the last climbs to the top
    const many = Array.from({ length: 12 }, (_, i) => ({
      user_id: `p${i}`,
      username: `Player ${String.fromCharCode(65 + i)}`,
      total_score: 30 - i,
      current_round_answered: true,
      current_round_points: 0,
    }))
    const { rerender } = render(<PlayerScoreboard players={many} maxScore={60} />)

    // Act: everyone earns 1 and Player L earns 30
    rerender(
      <PlayerScoreboard
        players={many.map((p, i) => ({ ...p, total_score: p.total_score + (i === 11 ? 30 : 1), current_round_points: i === 11 ? 30 : 1 }))}
        maxScore={60}
      />,
    )

    // Assert: the threads start at 320 + the row's stagger, never later than 320 + 240
    const threadDelays = calls.filter((c) => (c.el as HTMLElement).tagName === "I").map((c) => c.options.delay)
    expect(threadDelays).toHaveLength(12)
    expect(Math.max(...(threadDelays as number[]))).toBe(320 + 240)
    expect(threadDelays.slice(0, 4)).toEqual([320, 350, 380, 410])
  })

  it("waits for the reveal's authored moment when told to: rows, threads and gains all start after it", () => {
    // Prepare: The Quiz's reveal, whose tally threads take 730 ms (640 + 3 × 30)
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} weaveAfter={730} />)

    // Act
    rerender(<PlayerScoreboard players={after} maxScore={30} weaveAfter={730} />)

    // Assert: the same weave, every part 730 ms later
    expect(rowMoves(container, "Alice")[0].options.delay).toBe(730)
    expect(rowMoves(container, "Bob")[0].options.delay).toBe(730 + 60)
    expect(threadMoves(container, "Alice")[0].options.delay).toBe(730 + 320)
    expect(threadMoves(container, "Charlie")[0].options.delay).toBe(730 + 320 + 30)
    expect(gainFades(container, "Alice")[0].options.delay).toBe(730 + 320)
    for (const call of calls) expect(call.options.fill).toBe("backwards")
  })

  it("does not wait under reduced motion: only the gains fade, at once", () => {
    stubReducedMotion(true)
    const { rerender } = render(<PlayerScoreboard players={before} maxScore={30} weaveAfter={730} />)

    rerender(<PlayerScoreboard players={after} maxScore={30} weaveAfter={730} />)

    expect(calls).toHaveLength(2)
    for (const call of calls) expect(call.options.delay ?? 0).toBe(0)
  })

  it("writes the thread from the right in Arabic", () => {
    document.documentElement.setAttribute("dir", "rtl")
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)

    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    const [alice] = threadMoves(container, "Alice")
    expect(shiftX(alice.keyframes[0])).toBeCloseTo((1 - 4 / 30) * 100, 2)
    expect(shiftX(alice.keyframes[1])).toBeCloseTo((1 - 7 / 30) * 100, 2)
  })

  it("under reduced motion shows the final state at once, only the gain fading in", () => {
    // Prepare
    stubReducedMotion(true)
    const { container, rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)

    // Act
    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    // Assert: no row and no thread moves; the two gains fade, at once
    expect(calls.every((c) => c.keyframes.every((k) => !("transform" in k)))).toBe(true)
    expect(calls).toHaveLength(2)
    const [fade] = gainFades(container, "Alice")
    expect(fade.keyframes).toEqual([{ opacity: 0 }, { opacity: 1 }])
    expect(fade.options.delay ?? 0).toBe(0)
  })

  it("never animates anything that lays the page out", () => {
    const { rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)
    rerender(<PlayerScoreboard players={after} maxScore={30} />)

    expect(calls.length).toBeGreaterThan(0)
    for (const call of calls) for (const keyframe of call.keyframes) for (const key of Object.keys(keyframe)) expect(["transform", "opacity"]).toContain(key)
    for (const li of rows()) expect(li.style.width).toBe("")
  })

  it("cancels a weave still running when the next change arrives, and starts from there", () => {
    // Prepare: a first change in flight
    const { rerender } = render(<PlayerScoreboard players={before} maxScore={30} />)
    rerender(<PlayerScoreboard players={after} maxScore={30} />)
    const first = calls.map((c) => c.anim)
    expect(first.length).toBeGreaterThan(0)

    // Act: a second change (Kalimat: another player finds the word)
    rerender(<PlayerScoreboard players={table({ Alice: [7, 3], Bob: [12, 6], Charlie: [7, 2] })} maxScore={30} />)

    // Assert
    for (const anim of first) expect(anim.cancel).toHaveBeenCalled()
    expect(calls.length).toBeGreaterThan(first.length)
  })
})

describe("PlayerScoreboard, the CSS of the woven scores", () => {
  // vitest runs with `css: false`: read the file.
  const css = readFileSync(resolve(process.cwd(), "src/styles/pages/quiz.css"), "utf8")

  /** One CSS rule's body, by its exact selector. */
  function rule(selector: string) {
    const at = css.indexOf(`${selector} {`)
    if (at < 0) return null
    return css.slice(at + selector.length + 2, css.indexOf("}", at))
  }

  it("places a full-length thread by a transform in a clipped yarn box, never by its width", () => {
    expect(rule(".score-yarn")).toMatch(/overflow: hidden;/)
    const thread = rule(".score-yarn > i") ?? ""
    expect(thread).toMatch(/transform: translateX\(calc\(\(var\(--share, 0\) - 1\) \* 100%\)\);/)
    expect(thread).toMatch(/var\(--band-khayt\)/)
    expect(thread).not.toMatch(/width|transition|will-change/)
    expect(rule('[dir="rtl"] .score-yarn > i')).toMatch(/transform: translateX\(calc\(\(1 - var\(--share, 0\)\) \* 100%\)\);/)
  })

  it("rests every row on an identity transform, so a row's travel ending lays nothing out", () => {
    expect(rule(".score-row")).toMatch(/transform: translateY\(0\);/)
  })

  it("gives the gain a box and a layer at rest, so its fade's end lays nothing out", () => {
    // an inline gaining and losing an animated opacity re-laid its line out when the fade ended
    const gain = rule(".score-gain") ?? ""
    expect(gain).toMatch(/display: inline-block;/)
    expect(gain).toMatch(/transform: translateY\(0\);/)
  })

  it("weaves the viewer's own thread with the madd band", () => {
    expect(rule(".score-row[data-you] .score-yarn > i")).toMatch(/var\(--band-madd\)/)
  })
})
