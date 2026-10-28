import { describe, expect, it } from "vitest"
import type { AchievementWithProgress } from "@/api/generated"
import {
  cardGlyph,
  fillDays,
  formatDuration,
  gameName,
  groupVotes,
  latnLocale,
  orderAchievements,
  percentOf,
  phoneColumns,
  roleLozenge,
  secondsBetween,
  teamOf,
  timeLeft,
  winnerLine,
} from "../format"

// echoes the key and its options, so a test can see what was asked for
const t = (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key)

describe("fillDays", () => {
  it("gives every one of the last N UTC days a slot, keeping the days that had games", () => {
    // Prepare
    const now = new Date("2026-10-28T09:00:00Z")
    const records = [
      { date: "2026-10-28", wins: 2, losses: 1 },
      { date: "2026-10-26", wins: 0, losses: 3 },
      { date: "2026-09-01", wins: 5, losses: 0 },
    ]

    // Act
    const days = fillDays(records, 3, now)

    // Assert
    expect(days).toEqual([
      { date: "2026-10-26", wins: 0, losses: 3 },
      { date: "2026-10-27", wins: 0, losses: 0 },
      { date: "2026-10-28", wins: 2, losses: 1 },
    ])
  })

  it("returns 30 empty days when nothing was played", () => {
    expect(fillDays([], 30, new Date("2026-03-01T00:00:00Z"))).toHaveLength(30)
  })
})

describe("formatDuration", () => {
  it("speaks seconds alone, minutes with seconds, and says nothing it does not know", () => {
    expect(formatDuration(42, t)).toBe('stats.durationS {"s":42}')
    expect(formatDuration(754.4, t)).toBe('stats.durationMS {"m":12,"s":34}')
    expect(formatDuration(null, t)).toBe("—")
    expect(formatDuration(0, t)).toBe("—")
  })

  it("measures the time between two timestamps", () => {
    expect(secondsBetween("2026-10-28T10:00:00Z", "2026-10-28T10:12:30Z")).toBe(750)
    expect(secondsBetween("2026-10-28T10:00:00Z", null)).toBeNull()
  })
})

describe("groupVotes", () => {
  it("groups voters by the player they named, most-named first", () => {
    // Prepare
    const votes = [
      { voter: "Khadija", target: "Maryam" },
      { voter: "Maryam", target: "Khadija" },
      { voter: "Idris", target: "Khadija" },
    ]

    // Act
    const lines = groupVotes(votes)

    // Assert
    expect(lines).toEqual([
      { target: "Khadija", voters: ["Maryam", "Idris"] },
      { target: "Maryam", voters: ["Khadija"] },
    ])
  })
})

describe("names and marks", () => {
  it("names all four games and keeps an unknown type as it came", () => {
    expect(gameName("word_quiz", t)).toBe("games.wordQuiz.name")
    expect(gameName("mcq_quiz", t)).toBe("games.mcqQuiz.name")
    expect(gameName("chess", t)).toBe("chess")
  })

  it("marks Undercover roles with their wool and leaves Codenames roles undyed", () => {
    expect(roleLozenge("civilian")).toBe("undyed")
    expect(roleLozenge("undercover")).toBe("madder")
    expect(roleLozenge("mr_white")).toBe("open")
    expect(roleLozenge("spymaster")).toBeNull()
  })

  it("maps the API's red/blue onto madder/indigo and cards onto glyphs", () => {
    expect(teamOf("red")).toBe("madder")
    expect(teamOf("blue")).toBe("indigo")
    expect(teamOf(null)).toBeNull()
    expect(cardGlyph("assassin")).toBe("assassin")
    expect(cardGlyph("neutral")).toBe("bystander")
  })

  it("words the result of each kind of game", () => {
    expect(winnerLine("undercover", "civilians", t)).toBe("stats.result.civilians")
    expect(winnerLine("undercover", "undercovers", t)).toBe("stats.result.undercovers")
    expect(winnerLine("codenames", "red", t)).toBe('stats.result.team {"team":"game.codenames.teams.red"}')
    expect(winnerLine("word_quiz", "Maryam", t)).toBe('stats.result.player {"name":"Maryam"}')
    expect(winnerLine("undercover", null, t)).toBeNull()
  })
})

describe("figures", () => {
  it("rounds a share and never divides by zero", () => {
    expect(percentOf(1, 3)).toBe(33)
    expect(percentOf(5, 0)).toBe(0)
  })

  it("keeps Western digits in every language", () => {
    expect(latnLocale("ar")).toBe("ar-u-nu-latn")
    expect(new Date("2026-10-28T00:00:00Z").toLocaleDateString(latnLocale("ar"), { day: "numeric", timeZone: "UTC" })).toBe("28")
  })

  it("counts down to a challenge's end in days, hours or minutes", () => {
    const now = Date.parse("2026-10-28T10:00:00Z")
    expect(timeLeft("2026-10-30T13:00:00Z", t, now)).toBe('challenges.time.days {"d":2,"h":3}')
    expect(timeLeft("2026-10-28T15:30:00Z", t, now)).toBe('challenges.time.hours {"h":5,"m":30}')
    expect(timeLeft("2026-10-28T10:20:00Z", t, now)).toBe('challenges.time.minutes {"m":20}')
    expect(timeLeft("2026-10-28T09:00:00Z", t, now)).toBe("challenges.time.expired")
  })
})

describe("orderAchievements", () => {
  const a = (code: string, over: Partial<AchievementWithProgress>): AchievementWithProgress => ({
    code,
    name: code,
    description: "",
    icon: "",
    category: "beginner",
    tier: 1,
    threshold: 10,
    progress: 0,
    unlocked: false,
    ...over,
  })

  it("puts earned seals first, then the nearest to earning, then the lower tier", () => {
    // Prepare
    const list = [a("far", { progress: 1 }), a("earned", { unlocked: true, progress: 10 }), a("near", { progress: 8 }), a("hard", { progress: 1, tier: 3 })]

    // Act
    const order = orderAchievements(list).map((x) => x.code)

    // Assert
    expect(order).toEqual(["earned", "near", "far", "hard"])
  })
})

describe("phoneColumns", () => {
  it("keeps wins and the sorted column on a phone", () => {
    expect([...phoneColumns("total_games_won")]).toEqual(["wins"])
    expect([...phoneColumns("win_rate")].sort()).toEqual(["rate", "wins"])
    expect([...phoneColumns("longest_win_streak")].sort()).toEqual(["streak", "wins"])
  })
})
