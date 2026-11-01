import { describe, expect, it } from "vitest"
import type { DailyWordState, NotebookGameWord } from "@/api/generated"
import { formatDailyDate } from "@/components/daily/daily"
import { dailyCardFileName, dailyCardInput, dailyCardTitle } from "../daily-card"
import { gameCardFileName, gameCardInput, gameShareLine, SHARE_URL } from "../game-card"
import { layoutCard, MAX_CARD_WORDS } from "../model"

/** t names its parameters, so a test sees what was asked for in which words. */
const t = (key: string, opts?: Record<string, unknown>) => {
  const params = Object.entries(opts ?? {}).map(([k, v]) => `${k}=${String(v)}`)
  return params.length ? `${key}(${params.join(",")})` : key
}

const measure = (text: string, font: { size: number }) => [...text].length * font.size * 0.5

const FSI = "⁨"
const PDI = "⁩"

const word = (over: Partial<NotebookGameWord> = {}): NotebookGameWord => ({
  word: "Sabr",
  word_display: "Sabr",
  word_ar: "صبر",
  word_ar_vocalized: "صَبْر",
  hint: "Patience: holding firm.",
  kept: false,
  entry_id: null,
  ...over,
})

const finished = (over: Partial<DailyWordState> = {}): DailyWordState => ({
  day: "2026-10-29",
  number: 2,
  category: "places",
  max_hints: 6,
  hints: ["An oasis in the Hijaz", "A battle in year 7", "Its fortresses fell"],
  hints_revealed: 3,
  status: "solved",
  attempts: 2,
  guesses: ["Badr", "Khaybar"],
  score: 4,
  streak: 2,
  best_streak: 5,
  solvers_today: 3,
  next_day_at: "2026-10-29T21:00:00Z",
  answer: { word_display: "Khaybar", word_ar: "خيبر", word_ar_vocalized: "خَيْبَر", explanation: "An oasis north of Madinah.", kept: false, entry_id: null },
  ...over,
})

const SHARE = { game: "undercover", host: "Yusuf", count: "3 rounds", startedAt: "2026-10-28T20:00:00Z", endedAt: "2026-10-28T20:21:40Z" } as const

describe("a game as a card", () => {
  it("names the game in Arabic (the games list's large form) and in the interface language, then the colophon's meta line", () => {
    // Act
    const input = gameCardInput(SHARE, [word()], t, "en")

    // Assert
    expect(input).toMatchObject({
      kind: "game",
      dir: "ltr",
      arabicName: "home.fihrist.undercover.arabic",
      latinName: "games.undercover.name",
      footer: SHARE_URL,
    })
    expect(input.meta).toEqual(["games.undercover.name", `game.colophon.majlis(name=${FSI}Yusuf${PDI})`, "3 rounds", "21:40"])
  })

  it("leaves out what the state does not carry, as the colophon does", () => {
    const input = gameCardInput({ game: "mcqquiz", count: "10 questions" }, undefined, t, "fr")
    expect(input.meta).toEqual(["games.mcqQuiz.name", "10 questions"])
    expect(input.arabicName).toBe("home.fihrist.mcqQuiz.arabic")
    expect(input.words).toEqual([])
  })

  it("sets every word the game dealt, the vocalised Arabic first, with its form in the interface language", () => {
    // Act
    const input = gameCardInput(
      { ...SHARE, game: "wordquiz" },
      [
        word(),
        word({ word: "Hilm", word_display: "Ḥilm", word_ar: "حلم", word_ar_vocalized: null }),
        word({ word: "Tasbih", word_display: "Tasbih", word_ar: null, word_ar_vocalized: null }),
      ],
      t,
      "en",
    )

    // Assert
    expect(input.words).toEqual([{ arabic: "صَبْر", display: "Sabr" }, { arabic: "حلم", display: "Ḥilm" }, { display: "Tasbih" }])
  })

  it("reads the Arabic alone in the Arabic interface, right to left, and no Latin name", () => {
    // Act
    const input = gameCardInput({ ...SHARE, game: "codenames" }, [word(), word({ word_ar: null, word_ar_vocalized: null, word_display: "Tasbih" })], t, "ar")

    // Assert
    expect(input.dir).toBe("rtl")
    expect(input.latinName).toBeUndefined()
    expect(input.words).toEqual([{ arabic: "صَبْر" }, { display: "Tasbih" }])
  })

  it(`keeps ${MAX_CARD_WORDS - 1} words of a longer game and says how many more`, () => {
    // Act
    const input = gameCardInput(
      { ...SHARE, game: "wordquiz" },
      Array.from({ length: 30 }, (_, i) => word({ word: `w${i}`, word_display: `w${i}` })),
      t,
      "en",
    )

    // Assert
    expect(input.words).toHaveLength(MAX_CARD_WORDS - 1)
    expect(input.more).toBe("game.colophon.share.more(count=6)")
  })

  it("copies a line where the image cannot be shared: the meta line and the address", () => {
    expect(gameShareLine(SHARE, t)).toBe(
      `game.colophon.share.line(meta=games.undercover.name · game.colophon.majlis(name=${FSI}Yusuf${PDI}) · 3 rounds · 21:40,url=${SHARE_URL})`,
    )
  })

  it("names the file after the game, in plain ASCII", () => {
    expect(gameCardFileName(SHARE)).toBe("majlisna-undercover.png")
    expect(dailyCardFileName(finished())).toBe("majlisna-word-of-the-day-2.png")
  })
})

describe("the word of the day as a card", () => {
  it("never carries the word, its forms, its explanation, a hint or a guess", () => {
    // Prepare
    const state = finished()
    const secrets = ["Khaybar", "خيبر", "خَيْبَر", "An oasis north of Madinah.", ...state.hints, ...state.guesses]

    // Act
    const input = dailyCardInput(state, t, "en")
    const drawn = JSON.stringify(layoutCard(input, measure))

    // Assert
    for (const secret of secrets) {
      expect(JSON.stringify(input), secret).not.toContain(secret)
      expect(drawn, secret).not.toContain(secret)
    }
  })

  it("names the day as the page does, then the strip with the rung it was found at", () => {
    // Act
    const input = dailyCardInput(finished(), t, "en")

    // Assert
    expect(input).toMatchObject({
      kind: "daily",
      dir: "ltr",
      arabicName: "كلمة اليوم",
      latinName: "daily.name",
      rungs: { total: 6, revealed: 3, found: 3 },
      result: "daily.reveal.foundAt(number=3) · game.quiz.kalimat.pointsSr(count=4)",
      footer: "majlisna.app/today",
      streak: [
        { label: "daily.reveal.streak", value: 2 },
        { label: "daily.reveal.bestStreak", value: 5 },
      ],
    })
    // the Makkah day as the page writes it ("Thursday 29 October 2026"), Western digits
    expect(input.meta).toEqual(["daily.number(number=2)", formatDailyDate("2026-10-29", "en"), "game.quiz.kalimat.category.places"])
    expect(input.meta[1]).toMatch(/2026/)
  })

  it("has no found rung for a day given up", () => {
    const input = dailyCardInput(finished({ status: "gave_up", score: 0, hints_revealed: 4, streak: 0 }), t, "fr")
    expect(input.rungs).toEqual({ total: 6, revealed: 4, found: null })
    expect(input.result).toBe("daily.reveal.gaveUp")
  })

  it("reads the Arabic name alone in the Arabic interface", () => {
    const input = dailyCardInput(finished(), t, "ar")
    expect(input.dir).toBe("rtl")
    expect(input.latinName).toBeUndefined()
  })

  it("titles the share sheet with the day's name and number", () => {
    expect(dailyCardTitle(finished(), t)).toBe("daily.name · daily.number(number=2)")
  })
})
