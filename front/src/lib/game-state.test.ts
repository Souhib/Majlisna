import { describe, expect, it } from "vitest"
import {
  deriveUndercoverPhase,
  derivePlayerList,
  deriveVotedPlayers,
  type DerivePhaseInput,
} from "./game-state"

describe("deriveUndercoverPhase", () => {
  const base: DerivePhaseInput = {
    winner: null,
    turn_phase: null,
    turn_number: 0,
    my_role: "civilian",
    roleRevealed: false,
  }

  it("returns game_over when winner exists", () => {
    expect(deriveUndercoverPhase({ ...base, winner: "civilians" })).toBe("game_over")
  })

  it("returns role_reveal for turn 1 describing phase before reveal", () => {
    expect(
      deriveUndercoverPhase({ ...base, turn_phase: "describing", turn_number: 1, roleRevealed: false }),
    ).toBe("role_reveal")
  })

  it("returns describing for turn 1 after role revealed", () => {
    expect(
      deriveUndercoverPhase({ ...base, turn_phase: "describing", turn_number: 1, roleRevealed: true }),
    ).toBe("describing")
  })

  it("returns describing for turn > 1 even if not revealed", () => {
    expect(
      deriveUndercoverPhase({ ...base, turn_phase: "describing", turn_number: 2, roleRevealed: false }),
    ).toBe("describing")
  })

  it("returns describing for spectator on turn 1 without reveal", () => {
    expect(
      deriveUndercoverPhase({
        ...base,
        turn_phase: "describing",
        turn_number: 1,
        my_role: "spectator",
        roleRevealed: false,
      }),
    ).toBe("describing")
  })

  it("returns playing when turn_number > 0 and not describing", () => {
    expect(deriveUndercoverPhase({ ...base, turn_phase: "voting", turn_number: 1 })).toBe("playing")
  })

  it("returns round_over when the voting turn is resolved", () => {
    expect(deriveUndercoverPhase({ ...base, turn_phase: "voting", turn_number: 1, round_resolved: true })).toBe(
      "round_over",
    )
  })

  it("returns mr_white_guessing while an eliminated Mr. White owes his guess", () => {
    expect(
      deriveUndercoverPhase({ ...base, turn_phase: "mr_white_guessing", turn_number: 2, round_resolved: true }),
    ).toBe("mr_white_guessing")
  })

  it("returns describing for the next round even though the previous one resolved", () => {
    expect(
      deriveUndercoverPhase({ ...base, turn_phase: "describing", turn_number: 2, round_resolved: false }),
    ).toBe("describing")
  })

  it("returns role_reveal for initial state (turn 0, non-spectator)", () => {
    expect(deriveUndercoverPhase(base)).toBe("role_reveal")
  })

  it("returns describing for spectator at initial state", () => {
    expect(deriveUndercoverPhase({ ...base, my_role: "spectator" })).toBe("describing")
  })

  it("game_over takes priority over everything", () => {
    expect(
      deriveUndercoverPhase({
        winner: "undercover",
        turn_phase: "describing",
        turn_number: 3,
        my_role: "civilian",
        roleRevealed: true,
      }),
    ).toBe("game_over")
  })
})

describe("derivePlayerList", () => {
  it("maps server player format to UI format", () => {
    const players = [
      { user_id: "u1", username: "Alice", is_alive: true, is_mayor: false },
      { user_id: "u2", username: "Bob", is_alive: false, is_mayor: true },
    ]
    const result = derivePlayerList(players)
    expect(result).toEqual([
      { id: "u1", username: "Alice", is_alive: true, is_mayor: false },
      { id: "u2", username: "Bob", is_alive: false, is_mayor: true },
    ])
  })

  it("returns empty array for empty input", () => {
    expect(derivePlayerList([])).toEqual([])
  })
})

describe("deriveVotedPlayers", () => {
  it("extracts keys from votes object", () => {
    expect(deriveVotedPlayers({ u1: "u2", u3: "u2" })).toEqual(["u1", "u3"])
  })

  it("returns empty array for null", () => {
    expect(deriveVotedPlayers(null)).toEqual([])
  })

  it("returns empty array for undefined", () => {
    expect(deriveVotedPlayers(undefined)).toEqual([])
  })

  it("returns empty array for empty object", () => {
    expect(deriveVotedPlayers({})).toEqual([])
  })
})
