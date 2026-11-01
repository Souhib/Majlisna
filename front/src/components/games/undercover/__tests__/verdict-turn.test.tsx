import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { render, screen } from "@testing-library/react"
import type { ComponentProps } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { DescriptionList } from "../DescriptionList"
import { MrWhiteGuessPanel } from "../MrWhiteGuessPanel"
import { RoundOverPanel } from "../RoundOverPanel"
import { stopRecordingAnimations, stubReducedMotion } from "./record-animations"

/**
 * The lawh turns over (ANIM-2, spec 4): when the vote resolves ON SCREEN (the table's list
 * leaves in the commit the verdict arrives), the verdict plays its turn once: the bare-warp
 * cover parts from the reading start, the role band is woven in at the foot, the role chip's
 * lozenge is pressed. A page loaded on the verdict, a refetch, a socket push, or Mr. White's
 * guess resolving play nothing. The gestures are CSS (`data-turn` on the verdict), so these
 * tests check the attribute; undercover.css is read below.
 */

const ROUND = {
  round: 2,
  votes: [{ voter: "Maryam", voter_id: "u1", target: "Bilal", target_id: "u4" }],
  eliminated: { username: "Bilal", role: "undercover", user_id: "u4" },
}

function panelProps(over: Partial<ComponentProps<typeof RoundOverPanel>> = {}): ComponentProps<typeof RoundOverPanel> {
  return {
    round: ROUND,
    roundNumber: 2,
    currentUserId: "u1",
    myWord: null,
    isHost: true,
    canMarkReady: false,
    isReady: false,
    readyCount: 0,
    readyQuorum: 2,
    isStarting: false,
    onNextRound: vi.fn(),
    ...over,
  }
}

const order = [
  { user_id: "u1", username: "Maryam" },
  { user_id: "u4", username: "Bilal" },
]
const players = [
  { id: "u1", username: "Maryam", is_alive: true },
  { id: "u4", username: "Bilal", is_alive: true },
]

/** The page's swap, reduced to its two phases: the vote's list, then the verdict. */
function Table({ phase, panel }: { phase: "playing" | "round_over" | "mr_white_guessing"; panel?: Partial<ComponentProps<typeof RoundOverPanel>> }) {
  if (phase === "playing") return <DescriptionList order={order} descriptions={{}} currentIndex={2} mode="voting" players={players} voted={[]} />
  if (phase === "mr_white_guessing")
    return <MrWhiteGuessPanel isGuesser={false} round={ROUND} currentUserId="u1" guess="" isSubmitting={false} onGuessChange={vi.fn()} onSubmit={vi.fn()} />
  return <RoundOverPanel {...panelProps(panel)} />
}

const verdict = () => screen.getByTestId("elimination-overlay")

beforeEach(() => {
  stubReducedMotion(false)
})

afterEach(() => {
  stopRecordingAnimations()
})

describe("The lawh turns over when the vote resolves on screen", () => {
  it("plays the turn when the verdict replaces the vote", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)

    // Act
    rerender(<Table phase="round_over" />)

    // Assert
    expect(verdict()).toHaveAttribute("data-turn", "turn")
    // truth first: the sentence, the role and the votes are in the DOM from the first frame
    expect(screen.getByRole("heading", { level: 2, name: "game.undercover.verdict.chose" })).toBeInTheDocument()
    expect(screen.getByText("games.undercover.roles.undercover")).toBeInTheDocument()
    expect(screen.getByRole("group", { name: "game.undercover.lawh.turnedLabel" })).toHaveAttribute("data-role", "undercover")
  })

  it("plays nothing on a page loaded on the verdict", () => {
    // Prepare / Act
    render(<Table phase="round_over" />)

    // Assert
    expect(verdict()).not.toHaveAttribute("data-turn")
    expect(screen.getByText("games.undercover.roles.undercover")).toBeInTheDocument()
  })

  it("replays nothing on a refetch or a socket push of the same verdict", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)
    rerender(<Table phase="round_over" />)

    // Act: the ready count moves, the same round comes again
    rerender(<Table phase="round_over" panel={{ readyCount: 1, round: { ...ROUND } }} />)

    // Assert: the attribute keeps its value, so the CSS animations are not restarted
    expect(verdict()).toHaveAttribute("data-turn", "turn")
  })

  it("turns Mr. White's tablet over when the vote finds him on screen, while he guesses", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)

    // Act: the vote resolves; everyone but him reads the compact verdict while he guesses
    rerender(<Table phase="mr_white_guessing" />)

    // Assert: the compact verdict turns (it has no band at its foot: the cover and the lozenge)
    expect(verdict()).toHaveAttribute("data-compact")
    expect(verdict()).toHaveAttribute("data-turn", "turn")
    expect(verdict()).not.toHaveAttribute("data-word")
    expect(screen.getByRole("group", { name: "game.undercover.lawh.turnedLabel" }).querySelector(".sadu-band")).toBeNull()
  })

  it("plays nothing when Mr. White's guess resolves: his tablet turned over when he was voted out", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)
    rerender(<Table phase="mr_white_guessing" />)
    expect(verdict()).toHaveAttribute("data-turn", "turn")

    // Act
    rerender(<Table phase="round_over" />)

    // Assert
    expect(verdict()).not.toHaveAttribute("data-turn")
  })

  it("plays nothing on a page loaded while Mr. White guesses, nor on a push of the same state", () => {
    // Prepare / Act
    const { rerender } = render(<Table phase="mr_white_guessing" />)
    rerender(<Table phase="mr_white_guessing" />)

    // Assert
    expect(verdict()).not.toHaveAttribute("data-turn")
  })

  it("only fades Mr. White's cover under reduced motion", () => {
    stubReducedMotion(true)
    const { rerender } = render(<Table phase="playing" />)

    rerender(<Table phase="mr_white_guessing" />)

    expect(verdict()).toHaveAttribute("data-turn", "fade")
  })

  it("under reduced motion, only fades the cover", () => {
    // Prepare
    stubReducedMotion(true)
    const { rerender } = render(<Table phase="playing" />)

    // Act
    rerender(<Table phase="round_over" />)

    // Assert
    expect(verdict()).toHaveAttribute("data-turn", "fade")
  })

  it("never passes the cover over a word: your own tablet's cover only fades", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)

    // Act: the seat that emptied is yours, so the face shows your word (it may be a sacred name)
    rerender(<Table phase="round_over" panel={{ currentUserId: "u4", myWord: { arabic: "الرحمن", latin: "Ar-Rahman" } }} />)

    // Assert
    expect(verdict()).toHaveAttribute("data-turn", "turn")
    expect(verdict()).toHaveAttribute("data-word")
    expect(screen.getByText("الرحمن")).toBeInTheDocument()
  })

  it("a verdict with nobody voted out has no tablet to turn", () => {
    // Prepare
    const { rerender } = render(<Table phase="playing" />)

    // Act
    rerender(<Table phase="round_over" panel={{ round: { round: 2, votes: [], eliminated: null } }} />)

    // Assert
    expect(screen.queryByRole("group")).toBeNull()
    expect(screen.getByRole("heading", { level: 2, name: "game.undercover.verdict.noOne" })).toBeInTheDocument()
  })
})

describe("undercover.css: the turn and the erase", () => {
  const css = readFileSync(resolve(process.cwd(), "src/styles/pages/undercover.css"), "utf8")

  /** One CSS rule's body, by its exact selector. */
  function rule(selector: string) {
    const at = css.indexOf(`${selector} {`)
    if (at < 0) return null
    return css.slice(at + selector.length + 2, css.indexOf("}", at))
  }
  /** One @keyframes block. */
  function keyframes(name: string) {
    const at = css.indexOf(`@keyframes ${name} {`)
    if (at < 0) return null
    return css.slice(at, css.indexOf("}\n}", at) + 3)
  }

  it("weaves the role band at the verdict tablet's foot: madder, undyed, goat-hair", () => {
    expect(rule('.lawh-turned[data-role="undercover"]')).toMatch(/--uc-role-band: var\(--band-teeth\);/)
    expect(rule('.lawh-turned[data-role="civilian"]')).toMatch(/--uc-role-band: var\(--band-plain\);/)
    expect(rule('.lawh-turned[data-role="mr_white"]')).toMatch(/--uc-role-band: var\(--band-goat\);/)
    expect(rule(".uc-verdict > .lawh-turned > .sadu-band")).toMatch(/overflow: hidden;/)
    // an unknown role reads as a Civilian everywhere (roleLabelKey): the undyed band
    expect(rule(".uc-verdict > .lawh-turned > .sadu-band::before")).toMatch(/background: var\(--uc-role-band, var\(--band-plain\)\) left center/)
    expect(rule('.uc-verdict[data-turn="turn"] > .lawh-turned > .sadu-band::before')).toMatch(
      /animation: uc-weave var\(--dur-authored\) var\(--ease-ink\) var\(--dur-state\) backwards;/,
    )
    expect(keyframes("uc-weave")).toMatch(/from \{\s*transform: translateX\(var\(--uc-from-reading-start\)\);/)
  })

  it("parts the bare-warp cover from the reading start, after the phase crossfade, inside clipped boxes", () => {
    const covers = ".uc-verdict[data-turn] > .lawh-turned :is(.lawh-role, .lawh-face)"
    expect(rule(covers)).toMatch(/overflow: hidden;/)
    expect(rule(`${covers}::after`)).toMatch(/repeating-linear-gradient\(90deg, var\(--warp\) 0 1px, transparent 1px 6px\)/)
    expect(rule('.uc-verdict[data-turn="turn"] > .lawh-turned :is(.lawh-role, .lawh-face)::after')).toMatch(
      /animation: uc-cover-part var\(--dur-move\) var\(--ease-settle\) var\(--dur-state\) backwards;/,
    )
    expect(keyframes("uc-cover-part")).toMatch(/to \{\s*transform: translateX\(var\(--uc-to-reading-end\)\);/)
  })

  it("sets the reading direction by custom properties, never by a second animation-name", () => {
    // the direction's values, the reading end at the right in LTR and at the left in RTL
    expect(rule(".uc-verdict")).toMatch(/--uc-to-reading-end: 100%;/)
    expect(rule(".uc-verdict")).toMatch(/--uc-from-reading-start: -100%;/)
    expect(rule('[dir="rtl"] .uc-verdict')).toMatch(/--uc-to-reading-end: -100%;/)
    expect(rule('[dir="rtl"] .uc-verdict')).toMatch(/--uc-from-reading-start: 100%;/)
    // a language switch mid-turn restarts nothing: a new animation-name would be a new animation
    expect(css).not.toMatch(/@keyframes uc-(cover-part|weave)-rtl/)
    for (const match of css.matchAll(/\[dir="rtl"\][^{]*\{([^}]*)\}/g)) expect(match[1]).not.toMatch(/animation(-name)?:/)
  })

  it("only fades a cover over a word, and under reduced motion fades it in 140 ms", () => {
    expect(rule('.uc-verdict[data-turn="turn"][data-word] > .lawh-turned :is(.lawh-role, .lawh-face)::after')).toMatch(
      /animation: uc-cover-fade var\(--dur-move\) var\(--ease-settle\) var\(--dur-state\) backwards;/,
    )
    expect(rule('.uc-verdict[data-turn="fade"] > .lawh-turned :is(.lawh-role, .lawh-face)::after')).toMatch(
      /animation: uc-cover-fade 140ms linear var\(--dur-state\) backwards;/,
    )
  })

  it("presses the role chip's lozenge once the cover has parted", () => {
    expect(rule('.uc-verdict[data-turn="turn"] > .lawh-turned .lawh-role .loz')).toMatch(
      /animation: seal-press 330ms var\(--ease-press\) calc\(var\(--dur-state\) \+ var\(--dur-move\)\) backwards;/,
    )
  })

  it("holds no fill once the turn is over: each layer's resting style IS its last frame", () => {
    const turn = css.slice(css.indexOf("/* --- the lawh turns over"), css.indexOf("@keyframes lawh-fade"))
    expect(turn).toMatch(/animation: /)
    expect(turn).not.toMatch(/\b(both|forwards);/)
  })

  it("moves only transform and opacity: no width, height, inset, mask or clip-path animated", () => {
    const frames = [...css.matchAll(/@keyframes [\w-]+ \{[\s\S]*?\n\}/g)].map((m) => m[0])
    // lawh-fade, uc-cover-part, uc-cover-fade, uc-weave (one per gesture: the direction is a custom property)
    expect(frames.length).toBeGreaterThanOrEqual(4)
    for (const block of frames) {
      const props = [...block.matchAll(/^\s+([a-z-]+):/gm)].map((m) => m[1])
      for (const prop of props) expect(["transform", "opacity"]).toContain(prop)
    }
    expect(css).not.toMatch(/transition:[^;]*(width|height|clip-path|mask)/)
  })

  it("keeps one row height while a voter chooses, so a candidate who leaves does not pull the rows under the finger", () => {
    expect(rule(".uc-seat")).toMatch(/min-height: var\(--uc-seat-h\);/)
    expect(rule(".uc-seat")).toMatch(/margin-block: var\(--uc-seat-gap\);/)
    expect(rule(".uc-descs[data-choosing] > li:not([data-candidate])")).toMatch(/min-height: calc\(var\(--uc-seat-h\) \+ 2 \* var\(--uc-seat-gap\) \+ 1px\);/)
  })

  it("recedes an emptied seat by opacity alone, its name at the muted token's level", () => {
    expect(rule('.uc-descs > li[data-out] [data-erase="ink"]')).toMatch(/color: var\(--text\);\s*opacity: var\(--erase-ink\);/)
    expect(rule('.uc-descs > li[data-out] [data-erase="mark"]')).toMatch(/opacity: var\(--erase-mark\);/)
    expect(rule('.uc-table > li[data-out] [data-erase="ink"]')).toMatch(/color: var\(--text\);\s*opacity: var\(--erase-ink\);/)
    expect(rule('.uc-table > li[data-out] [data-erase="mark"]')).toMatch(/opacity: var\(--erase-mark\);/)
  })
})
