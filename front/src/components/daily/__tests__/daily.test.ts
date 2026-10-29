import { describe, expect, it } from "vitest"
import type { DailyWordAnswer, DailyWordState } from "@/api/generated"
import {
  answerForms,
  categoryKey,
  countdownDuration,
  DAILY_SHARE_URL,
  dailyWordKey,
  formatCountdown,
  formatDailyDate,
  isFinished,
  msUntil,
  promptKey,
  resultLine,
  shareLine,
  stakes,
  triesOf,
} from "../daily"

// t names its parameters, so a test sees what was asked for in which words
const t = (key: string, opts?: Record<string, unknown>) => {
  const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
  return params.length ? `${key}(${params.join(",")})` : key
}

const answer = (over: Partial<DailyWordAnswer> = {}): DailyWordAnswer => ({
  word_display: "Khaybar",
  word_ar: "خيبر",
  word_ar_vocalized: "خَيْبَر",
  explanation: "An oasis north of Madinah.",
  kept: false,
  entry_id: null,
  ...over,
})

const state = (over: Partial<DailyWordState> = {}): DailyWordState => ({
  day: "2026-10-28",
  number: 1,
  category: "places",
  max_hints: 6,
  hints: ["An oasis"],
  hints_revealed: 1,
  status: "playing",
  attempts: 0,
  guesses: [],
  score: null,
  streak: 0,
  best_streak: 0,
  solvers_today: 0,
  next_day_at: "2026-10-28T21:00:00+00:00",
  answer: null,
  ...over,
})

describe("stakes", () => {
  it("is Kalimat's rule: 6 at the first hint, one less per hint, and what the next would leave", () => {
    expect(stakes({ max_hints: 6, hints_revealed: 1 })).toEqual({ now: 6, next: 5 })
    expect(stakes({ max_hints: 6, hints_revealed: 3 })).toEqual({ now: 4, next: 3 })
  })

  it("offers nothing more once every hint is out", () => {
    expect(stakes({ max_hints: 6, hints_revealed: 6 })).toEqual({ now: 1, next: null })
  })
})

describe("the day and its clock", () => {
  it("writes the Makkah day in the interface language with Western digits, whatever the device's zone", () => {
    // Prepare / Act
    const en = formatDailyDate("2026-10-28", "en")
    const ar = formatDailyDate("2026-10-28", "ar")

    // Assert: the calendar date the server named, never moved by a time zone
    expect(en).toBe("Wednesday, October 28, 2026")
    expect(ar).toContain("28")
    expect(ar).toContain("2026")
    expect(ar).not.toMatch(/[٠-٩]/)
    expect(formatDailyDate("nope", "en")).toBe("")
  })

  it("counts down in hours, minutes and seconds, never below zero", () => {
    expect(formatCountdown(5 * 3_600_000 + 12 * 60_000 + 33_000)).toBe("05:12:33")
    expect(formatCountdown(999)).toBe("00:00:01")
    expect(formatCountdown(-4000)).toBe("00:00:00")
    expect(countdownDuration(5 * 3_600_000 + 12 * 60_000 + 33_000)).toBe("PT5H12M33S")
  })

  it("measures the time left to the next word on the clock it is given", () => {
    const at = "2026-10-28T21:00:00+00:00"
    expect(msUntil(at, Date.parse("2026-10-28T20:59:00Z"))).toBe(60_000)
    expect(msUntil(at, Date.parse("2026-10-28T21:00:05Z"))).toBe(0)
    expect(msUntil("not a date", 0)).toBe(0)
  })
})

describe("words of the state", () => {
  it("knows a finished day from an open one", () => {
    expect(isFinished("solved")).toBe(true)
    expect(isFinished("gave_up")).toBe(true)
    expect(isFinished("playing")).toBe(false)
    expect(isFinished("not_started")).toBe(false)
    expect(isFinished(undefined)).toBe(false)
  })

  it("names the theme as Kalimat does, and asks for a person or a place as such", () => {
    expect(categoryKey("prophets")).toBe("game.quiz.kalimat.category.prophets")
    expect(categoryKey("nonsense")).toBeNull()
    expect(categoryKey(null)).toBeNull()
    expect(promptKey("companions")).toBe("game.quiz.kalimat.askWho")
    expect(promptKey("places")).toBe("game.quiz.kalimat.askWhere")
    expect(promptKey("quran")).toBe("game.quiz.kalimat.askWhat")
  })

  it('says how the day went: "found at hint 3 · 4 points", or "given up"', () => {
    expect(resultLine(state({ status: "solved", hints_revealed: 3, score: 4 }), t)).toBe("daily.reveal.foundAt(number=3) · game.quiz.kalimat.pointsSr(count=4)")
    expect(resultLine(state({ status: "gave_up", score: 0 }), t)).toBe("daily.reveal.gaveUp")
    expect(resultLine(state(), t)).toBe("")
  })

  it("shares a plain line with the number and the hint, never the answer", () => {
    // Prepare
    const solved = state({ status: "solved", number: 12, hints_revealed: 3, score: 4, answer: answer() })

    // Act
    const line = shareLine(solved, t)
    const gaveUp = shareLine(state({ status: "gave_up", number: 12, answer: answer() }), t)

    // Assert
    expect(line).toBe(`daily.share.solved(number=12,url=${DAILY_SHARE_URL},hint=3,total=6)`)
    expect(gaveUp).toBe(`daily.share.gaveUp(number=12,url=${DAILY_SHARE_URL})`)
    for (const text of [line, gaveUp]) {
      expect(text).not.toContain("Khaybar")
      expect(text).not.toContain("خيبر")
    }
  })

  it("lists the tries oldest first, the right one last on a solved day", () => {
    expect(triesOf(state({ guesses: ["Badr", "Uhud"] }))).toEqual([
      { text: "Badr", right: false },
      { text: "Uhud", right: false },
    ])
    expect(triesOf(state({ status: "solved", guesses: ["Badr", "خيبر"] }))).toEqual([
      { text: "Badr", right: false },
      { text: "خيبر", right: true },
    ])
    expect(triesOf(state({ status: "gave_up", guesses: ["Badr"] }))).toEqual([{ text: "Badr", right: false }])
  })
})

describe("answerForms", () => {
  it("leads with the vocalised Arabic and adds the word as Kalimat shows it", () => {
    expect(answerForms(answer(), false)).toEqual({ arabic: "خَيْبَر", display: "Khaybar", label: "Khaybar" })
  })

  it("falls back to the plain Arabic when no vocalised form is known", () => {
    expect(answerForms(answer({ word_ar_vocalized: null }), false).arabic).toBe("خيبر")
  })

  it("reads the Arabic alone in the Arabic interface, never a transliteration", () => {
    expect(answerForms(answer(), true)).toEqual({ arabic: "خَيْبَر", display: undefined, label: "خَيْبَر" })
  })

  it("does not say the same Arabic twice", () => {
    expect(answerForms(answer({ word_display: "خيبر" }), false).display).toBeUndefined()
  })
})

describe("dailyWordKey", () => {
  it("keeps a signed-out and a signed-in read of the same day apart, under the endpoint's prefix", () => {
    const anonymous = dailyWordKey("en", null)
    const player = dailyWordKey("en", "u1")
    expect(anonymous).not.toEqual(player)
    expect(anonymous[0]).toEqual({ url: "/api/v1/daily-word" })
    expect(player).toEqual([{ url: "/api/v1/daily-word" }, { lang: "en" }, { viewer: "u1" }])
  })
})
