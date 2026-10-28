import { describe, expect, it } from "vitest"
import type { NotebookEntryView } from "@/api/generated"
import { arabicOf, entryForms, formatKeptDate, groupEntries, uniqueEntries } from "../entries"
import { notebookGameFromPath } from "../route-game"
import { withoutEntry } from "../use-notebook-entries"

const entry = (over: Partial<NotebookEntryView>): NotebookEntryView => ({
  id: "e",
  word: "Sabr",
  word_display: "Sabr",
  game_type: "undercover",
  word_ar: "صبر",
  word_ar_vocalized: "صَبْر",
  hint: "Patience",
  source_game_id: "g1",
  kept_at: "2026-10-28T20:00:00+00:00",
  ...over,
})

describe("groupEntries", () => {
  it("runs consecutive words of one game, kept the same day, under one heading", () => {
    // Prepare
    const entries = [
      entry({ id: "a", source_game_id: "g2", game_type: "codenames" }),
      entry({ id: "b", source_game_id: "g2", game_type: "codenames" }),
      entry({ id: "c", source_game_id: "g1" }),
      entry({ id: "d", source_game_id: "g2", game_type: "codenames" }),
    ]

    // Act
    const groups = groupEntries(entries)

    // Assert: g2 is said twice, because g1's word was kept between its runs
    expect(groups.map((g) => [g.gameType, g.entries.map((e) => e.id)])).toEqual([
      ["codenames", ["a", "b"]],
      ["undercover", ["c"]],
      ["codenames", ["d"]],
    ])
    expect(new Set(groups.map((g) => g.key)).size).toBe(groups.length)
  })

  it("splits one game's words kept on two days, and groups a deleted game's words by type", () => {
    // Prepare
    const entries = [
      entry({ id: "a", kept_at: "2026-10-28T12:00:00+00:00" }),
      entry({ id: "b", kept_at: "2026-10-20T12:00:00+00:00" }),
      entry({ id: "c", source_game_id: null, kept_at: "2026-10-20T12:00:00+00:00" }),
      entry({ id: "d", source_game_id: null, kept_at: "2026-10-20T11:00:00+00:00" }),
    ]

    // Act
    const groups = groupEntries(entries)

    // Assert
    expect(groups.map((g) => g.entries.map((e) => e.id))).toEqual([["a"], ["b"], ["c", "d"]])
    expect(groups[0].keptAt).toBe("2026-10-28T12:00:00+00:00")
  })

  it("is empty for an empty notebook", () => {
    expect(groupEntries([])).toEqual([])
  })
})

describe("uniqueEntries", () => {
  it("keeps the first of repeated ids", () => {
    const entries = [entry({ id: "a", word: "x" }), entry({ id: "b" }), entry({ id: "a", word: "y" })]
    expect(uniqueEntries(entries).map((e) => `${e.id}${e.word}`)).toEqual(["ax", "bSabr"])
  })
})

describe("formatKeptDate", () => {
  it("writes the day in the interface language, with Western digits in Arabic too", () => {
    expect(formatKeptDate("2026-10-28T12:00:00+00:00", "en")).toBe("October 28, 2026")
    expect(formatKeptDate("2026-10-28T12:00:00+00:00", "fr")).toBe("28 octobre 2026")
    expect(formatKeptDate("2026-10-28T12:00:00+00:00", "ar")).toMatch(/28/)
    expect(formatKeptDate("2026-10-28T12:00:00+00:00", "ar")).not.toMatch(/[٠-٩]/)
  })

  it("says nothing for an unreadable date", () => {
    expect(formatKeptDate("not a date", "en")).toBe("")
  })
})

describe("entryForms", () => {
  it("leads with the vocalised Arabic and adds the game's word outside the Arabic UI", () => {
    expect(entryForms(entry({}), false)).toEqual({ arabic: "صَبْر", display: "Sabr", label: "Sabr" })
  })

  it("never transliterates in the Arabic UI", () => {
    expect(entryForms(entry({}), true)).toEqual({ arabic: "صَبْر", display: undefined, label: "صَبْر" })
  })

  it("does not repeat a Kalimat word whose display is its own Arabic", () => {
    const quiz = entry({ game_type: "word_quiz", word: "Patience", word_display: "صبر", word_ar_vocalized: null })
    expect(entryForms(quiz, false)).toEqual({ arabic: "صبر", display: undefined, label: "صبر" })
  })

  it("shows the word alone when it has no Arabic form", () => {
    const latin = entry({ word: "Sand", word_display: "Sand", word_ar: null, word_ar_vocalized: null })
    expect(entryForms(latin, true)).toEqual({ arabic: undefined, display: "Sand", label: "Sand" })
  })
})

describe("arabicOf", () => {
  it("prefers the vocalised form, ignores blanks", () => {
    expect(arabicOf({ word_ar: "صبر", word_ar_vocalized: " " })).toBe("صبر")
    expect(arabicOf({ word_ar: null, word_ar_vocalized: null })).toBeUndefined()
  })
})

describe("notebookGameFromPath", () => {
  it("reads the game of a game page; MCQ and other pages have none", () => {
    expect(notebookGameFromPath("/game/undercover/g1")).toEqual({ gameType: "undercover", gameId: "g1" })
    expect(notebookGameFromPath("/game/codenames/g2/")).toEqual({ gameType: "codenames", gameId: "g2" })
    expect(notebookGameFromPath("/game/wordquiz/k1")).toEqual({ gameType: "word_quiz", gameId: "k1" })
    expect(notebookGameFromPath("/game/mcqquiz/m1")).toBeNull()
    expect(notebookGameFromPath("/rooms/r1")).toBeNull()
  })
})

describe("withoutEntry", () => {
  it("takes the entry out of whichever page holds it and lowers the count", () => {
    // Prepare
    const pages = {
      pageParams: [null, "c1"],
      pages: [
        { entries: [entry({ id: "a" }), entry({ id: "b" })], total: 3, next_cursor: "c1" },
        { entries: [entry({ id: "c" })], total: 3, next_cursor: null },
      ],
    }

    // Act
    const after = withoutEntry(pages, "c")

    // Assert
    expect(after?.pages.map((p) => p.entries.map((e) => e.id))).toEqual([["a", "b"], []])
    expect(after?.pages.map((p) => p.total)).toEqual([2, 2])
    expect(withoutEntry(pages, "zzz")).toBe(pages)
  })
})
