import { afterEach, describe, expect, it, vi } from "vitest"
import type { RoomRiddle } from "@/api/generated"
import { answerRoomRiddle, LOBBY_RIDDLE_SCOPE, readRiddleRecord, riddleAskKey, type RiddleRecord, settleRiddleRecord, writeRiddleRecord } from "../samar-riddle"

/**
 * The samar riddle's rules without a screen: what a tab keeps of the riddle on screen, how
 * the riddle of an earlier wait becomes "the last riddle", the question for each theme, and
 * which lines may never be swept (a name of Allah, the Prophet ﷺ).
 */
const riddle = (id: string, hint = "A great patriarch"): RoomRiddle => ({
  id,
  category: "prophets",
  hint,
  answer: { word_display: "Ibrahim / Abraham", word_ar: "إبراهيم", word_ar_vocalized: null },
})

const shown = (id: string, over: Partial<NonNullable<RiddleRecord["current"]>> = {}): RiddleRecord => ({
  current: { riddle: riddle(id), lang: "en", waitKey: "lobby", shownAt: 1_000, revealed: false, ...over },
  last: null,
})

afterEach(() => {
  vi.unstubAllGlobals()
  sessionStorage.clear()
})

describe("the riddle a tab keeps", () => {
  it("is kept per room and per wait scope, across a reload", () => {
    // Prepare
    writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, shown("w1"))

    // Act
    const lobby = readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)
    const game = readRiddleRecord("room-1", "game:g1")
    const otherRoom = readRiddleRecord("room-2", LOBBY_RIDDLE_SCOPE)

    // Assert
    expect(lobby.current?.riddle.id).toBe("w1")
    expect(game).toEqual({ current: null, last: null })
    expect(otherRoom).toEqual({ current: null, last: null })
  })

  it("reads nothing from a malformed or refused storage, and never throws", () => {
    // Prepare
    sessionStorage.setItem("majlisna-riddle:room-1:lobby", "{not json")
    const malformed = readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)
    sessionStorage.setItem("majlisna-riddle:room-1:lobby", JSON.stringify({ current: { riddle: { id: 3 } } }))
    const wrongShape = readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)
    const denied = () => {
      throw new Error("denied")
    }
    vi.stubGlobal("sessionStorage", { getItem: denied, setItem: denied, removeItem: denied, clear: () => {} })

    // Act / Assert
    expect(malformed).toEqual({ current: null, last: null })
    expect(wrongShape).toEqual({ current: null, last: null })
    expect(() => writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, shown("w1"))).not.toThrow()
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)).toEqual({ current: null, last: null })
  })
})

describe("the riddle of an earlier wait", () => {
  it("is answered at the next wait, and a new one is asked", () => {
    // Act
    const next = settleRiddleRecord(shown("w1", { waitKey: "1" }), "2", "en")

    // Assert
    expect(next.current).toBeNull()
    expect(next.last?.riddle.id).toBe("w1")
  })

  it("goes on as it was while the wait is the same (a remount, a reload)", () => {
    // Prepare
    const record = shown("w1", { waitKey: "3", shownAt: 42 })

    // Act / Assert
    expect(settleRiddleRecord(record, "3", "en")).toBe(record)
  })

  it("needs no 'last riddle' once the player has read its answer", () => {
    // Act
    const next = settleRiddleRecord(shown("w1", { waitKey: "1", revealed: true }), "2", "en")

    // Assert
    expect(next).toEqual({ current: null, last: null })
  })

  it("is asked again in another language: its words are of the language it was read in", () => {
    // Prepare
    const record: RiddleRecord = { ...shown("w2"), last: { riddle: riddle("w1"), lang: "en" } }

    // Act
    const next = settleRiddleRecord(record, "lobby", "ar")

    // Assert
    expect(next).toEqual({ current: null, last: null })
  })

  it("is answered when the lobby's game starts (the lobby follows the table at once)", () => {
    // Prepare
    writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, shown("w1"))

    // Act
    answerRoomRiddle("room-1")

    // Assert
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)).toEqual({ current: null, last: { riddle: riddle("w1"), lang: "en" } })
  })

  it("leaves an answered lobby as it is when no riddle is on screen", () => {
    // Prepare
    const record: RiddleRecord = { current: null, last: { riddle: riddle("w1"), lang: "en" } }
    writeRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE, record)

    // Act
    answerRoomRiddle("room-1")

    // Assert
    expect(readRiddleRecord("room-1", LOBBY_RIDDLE_SCOPE)).toEqual(record)
  })
})

describe("the question for each theme", () => {
  it("asks who for a person, where for a place, what for anything else", () => {
    expect(riddleAskKey("prophets")).toBe("room.riddle.askWho")
    expect(riddleAskKey("companions")).toBe("room.riddle.askWho")
    expect(riddleAskKey("places")).toBe("room.riddle.askWhere")
    expect(riddleAskKey("quran")).toBe("room.riddle.askWhat")
    expect(riddleAskKey(null)).toBe("room.riddle.askWhat")
  })
})
