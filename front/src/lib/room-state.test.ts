import { describe, expect, it } from "vitest"
import { newerRoomState } from "./room-state"

/**
 * Two reads of a room can reach the page out of order: on CI (2026-11-01) a guest's
 * socket read the room on connect just before the host picked Kalimat, and sent it after
 * the pick's own push, so the lobby stayed on Undercover for good (no polling while the
 * socket is up). The server stamps every state with when it was read (`as_of_ms`); the
 * page keeps the one read last.
 */
describe("newerRoomState", () => {
  const read = (asOf: number | undefined, gameType: string) => ({ id: "room-1", game_type: gameType, ...(asOf === undefined ? {} : { as_of_ms: asOf }) })

  it("never lets a state read earlier replace the one on screen", () => {
    // Prepare
    const onScreen = read(2_000, "word_quiz")

    // Act
    const kept = newerRoomState(onScreen, read(1_000, "undercover"))

    // Assert
    expect(kept).toBe(onScreen)
  })

  it("takes a state read later, or at the same moment", () => {
    expect(newerRoomState(read(1_000, "undercover"), read(2_000, "word_quiz")).game_type).toBe("word_quiz")
    expect(newerRoomState(read(2_000, "undercover"), read(2_000, "word_quiz")).game_type).toBe("word_quiz")
  })

  it("takes the first state, and a state from a server that does not stamp it", () => {
    expect(newerRoomState(undefined, read(1_000, "undercover")).game_type).toBe("undercover")
    expect(newerRoomState(read(2_000, "undercover"), read(undefined, "word_quiz")).game_type).toBe("word_quiz")
    expect(newerRoomState(read(undefined, "undercover"), read(1_000, "word_quiz")).game_type).toBe("word_quiz")
  })
})
