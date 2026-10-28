import { renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useAchievementSeals } from "../achievement-seals"

const players = [
  { user_id: "u1", username: "Maryam" },
  { user_id: "u2", username: "Idris" },
  { user_id: "u3", username: "Bilal" },
]

describe("useAchievementSeals", () => {
  it("presses one seal per achievement, captioned with everyone who earned it, you first", () => {
    const notifications = [
      { user_id: "u1", achievements: [{ code: "first_game", name: "First Steps", tier: 1 }] },
      {
        user_id: "u2",
        achievements: [
          { code: "first_game", name: "First Steps", tier: 1 },
          { code: "first_game", name: "First Steps", tier: 1 },
        ],
      },
      { user_id: "u3", achievements: [{ code: "first_game", name: "First Steps", tier: 1 }] },
    ]
    const { result } = renderHook(() => useAchievementSeals(notifications, players, "u2"))
    expect(result.current).toHaveLength(1)
    expect(result.current[0].title).toBe("achievements.items.first_game.name")
    // en list format: "you, Maryam, and Bilal", then the tier
    expect(result.current[0].caption).toBe("game.quiz.you, Maryam, and Bilal · achievements.tiers.1")
  })

  it("puts the seals you earned first", () => {
    const notifications = [
      { user_id: "u1", achievements: [{ code: "first_win", name: "Taste of Victory", tier: 1 }] },
      { user_id: "u2", achievements: [{ code: "first_game", name: "First Steps", tier: 1 }] },
    ]
    const { result } = renderHook(() => useAchievementSeals(notifications, players, "u2"))
    expect(result.current.map((s) => s.title)).toEqual(["achievements.items.first_game.name", "achievements.items.first_win.name"])
    expect(result.current[1].caption).toBe("Maryam · achievements.tiers.1")
  })

  it("is empty without achievements", () => {
    const { result } = renderHook(() => useAchievementSeals(undefined, players, "u1"))
    expect(result.current).toEqual([])
  })
})
